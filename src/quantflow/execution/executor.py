"""Stock Executor for processing execution jobs.

Partitions stocks into two groups based on data source capabilities:
- batch_items: Non-A-share stocks (US/HK/JP/KR) fetched via YahooQuery/YFinance batch API
- sequential_items: A-share stocks fetched individually via BaoStock/Tushare
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd

from quantflow.config.loader import ConfigLoader
from quantflow.data import DataSourceFactory, StockCode
from quantflow.execution.storage import ExecutionResultItem, Storage
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.custom import DualLineIndicator
from quantflow.indicators.standard import KDJIndicator, MACDIndicator

from .job import ExecutionJob

logger = logging.getLogger(__name__)


@dataclass
class ProgressEvent:
    type: str          # "stock_start" | "stock_done" | "log"
    current: int       # Current stock index (0-based)
    total: int         # Total stocks
    code: str          # Current stock code
    message: str       # Human-readable message
    level: str         # "info" | "warning" | "error"

class Executor:
    def __init__(self):
        config = ConfigLoader()
        self.factory = DataSourceFactory(
            tushare_token=config.get_tushare_token(),
            yfinance_config=config.get_yfinance_config(),
            yahooquery_config=config.get_yahooquery_config(),
        )
        self.storage = Storage()
        self.composer = IndicatorComposer([
            KDJIndicator(),
            MACDIndicator(),
            DualLineIndicator()
        ])

    def _process_single(
        self, item, code: StockCode, df: pd.DataFrame, job
    ) -> Optional[ExecutionResultItem]:
        df = self.composer.compose(df)

        buy_signals = 0
        sell_signals = 0
        signal_reasons = []
        matched_buy_strategies = []
        matched_sell_strategies = []

        for strategy in job.strategies:
            df = strategy.generate_signals(df)
            latest_day = df.iloc[-1]
            s_name = strategy.name

            if latest_day.get("buy_signal", False):
                buy_signals += 1
                reason = latest_day.get("signal_reason", "Triggered")
                if pd.notna(reason) and str(reason):
                    signal_reasons.append(str(reason))
                matched_buy_strategies.append(s_name)

            if latest_day.get("sell_signal", False):
                sell_signals += 1
                reason = latest_day.get("signal_reason", "Triggered")
                if pd.notna(reason) and str(reason):
                    signal_reasons.append(str(reason))
                matched_sell_strategies.append(s_name)

        if buy_signals > 0 or sell_signals > 0:
            return ExecutionResultItem(
                code=item.code.standard if hasattr(item.code, "standard") else item.code,
                name=getattr(item, "name", ""),
                buy_signals=buy_signals,
                sell_signals=sell_signals,
                reasons=signal_reasons[:5],
                matched_buy_strategies=matched_buy_strategies,
                matched_sell_strategies=matched_sell_strategies,
            )
        return None

    @staticmethod
    def _code_str(code) -> str:
        if hasattr(code, "standard"):
            return code.standard
        return str(code)

    def _checkpoint_unit(self, checkpoint, task_key, code,
                         result: Optional[ExecutionResultItem]) -> None:
        if checkpoint is None:
            return
        stats = {"done_at": datetime.now().isoformat(),
                 "signals": (result.buy_signals + result.sell_signals)
                 if result else 0}
        checkpoint.mark_done(
            task_key, code, stats=stats,
            result=result.to_dict() if result is not None else None)

    def execute(
        self,
        job: ExecutionJob,
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
        checkpoint=None,
        task_key: str = "",
    ) -> List[ExecutionResultItem]:
        """Execute a job, optionally resuming from a Checkpoint.

        ``checkpoint`` / ``task_key`` are optional and default to ``None`` /
        ``""`` so existing callers (and test mocks accepting only ``job``)
        are unaffected.  When provided, already-completed stock codes are
        skipped and their cached results are folded back into the output.
        """
        total = len(job.items)
        done_codes: set = set()
        cached_results: List[ExecutionResultItem] = []
        if checkpoint is not None:
            done_codes = checkpoint.get_done(task_key)
            cached_results = [
                ExecutionResultItem.from_dict(d)
                for d in checkpoint.get_results(task_key)
            ]
            # Only treat codes as resumable when we actually have a record for
            # them; avoids re-using stale results after a config change.
            if done_codes:
                logger.info(
                    "Resuming %s: %d/%d items already done (checkpoint)",
                    job.name, len(done_codes), total)

        pending = [it for it in job.items
                   if self._code_str(it.code) not in done_codes]
        results: List[ExecutionResultItem] = list(cached_results)
        # Position lookup keeps progress monotonic on resume: a pending item
        # reports its original index in ``job.items``, not a restarted 1..n.
        position = {id(it): pos for pos, it in enumerate(job.items, 1)}

        def _emit(code: str, msg: str, level: str = "info",
                  etype: str = "log", item=None, idx: int = 0):
            current = position.get(id(item), idx) if item is not None else idx
            if on_progress:
                on_progress(ProgressEvent(
                    type=etype, current=current, total=total,
                    code=code, message=msg, level=level,
                ))

        # Advance the progress bar for resumed items without re-doing work.
        if done_codes:
            for it in job.items:
                c = self._code_str(it.code)
                if c in done_codes:
                    _emit(c, "resumed (cached)", "info", "stock_done", it)

        logger.info(f"Starting execution: {job.name} ({total} items, "
                    f"{len(pending)} pending)")
        # Freeze the data window across a resume: a run interrupted today and
        # continued a week later must still use the *original* dates so the
        # cached stocks and the freshly processed ones are comparable.
        frozen = None
        if checkpoint is not None:
            frozen = checkpoint.get_context(f"dates:{task_key}")
        if frozen and frozen.get("start_date") and frozen.get("end_date"):
            start_date, end_date = frozen["start_date"], frozen["end_date"]
            logger.info("Using frozen date window %s -> %s (resume)",
                        start_date, end_date)
        else:
            start_date = (datetime.now() - timedelta(days=job.days_back)).strftime("%Y-%m-%d")
            end_date = datetime.now().strftime("%Y-%m-%d")
            if checkpoint is not None:
                checkpoint.set_context(f"dates:{task_key}",
                                       {"start_date": start_date,
                                        "end_date": end_date})

        batch_items: List[tuple] = []
        sequential_items: List[tuple] = []

        for item in pending:
            code = item.code
            if isinstance(code, str):
                code = StockCode.from_standard(code)
            market = self.factory._detect_market(code)
            primary = self.factory.config.get_primary(market)
            if self.factory.has_batch_support(primary, market):
                batch_items.append((item, code))
            else:
                sequential_items.append((item, code))

        batch_data: Dict[str, pd.DataFrame] = {}
        if batch_items:
            batch_codes = [code for _, code in batch_items]
            # Progress during the (potentially multi-minute) batch download.
            # The adapter calls this per ticker/chunk so the Web UI bar moves
            # in real time rather than jumping only when the batch returns.
            def _fetch_progress(idx, batch_total, code):
                if on_progress:
                    on_progress(ProgressEvent(
                        type="fetch", current=idx, total=batch_total,
                        code=str(code), message=f"Fetching [{idx}/{batch_total}]",
                        level="info",
                    ))

            fetch_kwargs = {}
            if on_progress is not None:
                import inspect
                try:
                    accepts = "progress_cb" in inspect.signature(
                        self.factory.fetch_batch_ohlcv).parameters
                except (TypeError, ValueError):
                    accepts = False
                if accepts:
                    fetch_kwargs["progress_cb"] = _fetch_progress
            batch_result = self.factory.fetch_batch_ohlcv(
                batch_codes, start_date, end_date, **fetch_kwargs
            )
            for code_str, (df, _src) in batch_result.items():
                batch_data[code_str] = df
            logger.info(
                f"Batch complete: {len(batch_data)}/{len(batch_items)} stocks"
            )

        data_ok = 0
        no_data = 0
        errors = 0
        for _i, (item, code) in enumerate(batch_items, 1):
            df = batch_data.get(code.standard)
            _emit(code.standard, f"[{_i}/{len(pending)}] {code.standard}",
                  "info", "stock_start", item)
            if df is None or df.empty:
                no_data += 1
                logger.warning(f"No data for {item.code}")
                _emit(code.standard, f"No data: {code.standard}",
                      "warning", "stock_done", item)
                self._checkpoint_unit(checkpoint, task_key, code.standard, None)
                continue
            data_ok += 1
            result = self._process_single(item, code, df, job)
            sigs = result.buy_signals + result.sell_signals if result else 0
            if result:
                results.append(result)
                _emit(code.standard, f"Done: {code.standard} ({sigs} signals)",
                      "info", "stock_done", item)
            else:
                _emit(code.standard, f"Done: {code.standard} (0 signals)",
                      "info", "stock_done", item)
            self._checkpoint_unit(checkpoint, task_key, code.standard, result)

        for _i, (item, code) in enumerate(sequential_items, 1):
            try:
                _emit(code.standard, f"[{_i}/{len(pending)}] {code.standard}",
                      "info", "stock_start", item)
                logger.info(f"Processing [{_i}/{len(pending)}]: {item.code}")
                df, _ = self.factory.fetch_ohlcv(
                    code, start_date=start_date, end_date=end_date
                )
                if df.empty:
                    no_data += 1
                    logger.warning(f"No data for {item.code}")
                    _emit(code.standard, f"No data: {code.standard}",
                          "warning", "stock_done", item)
                    self._checkpoint_unit(checkpoint, task_key, code.standard, None)
                    continue
                data_ok += 1
                result = self._process_single(item, code, df, job)
                sigs = result.buy_signals + result.sell_signals if result else 0
                if result:
                    results.append(result)
                    _emit(code.standard, f"Done: {code.standard} ({sigs} signals)",
                          "info", "stock_done", item)
                else:
                    _emit(code.standard, f"Done: {code.standard} (0 signals)",
                          "info", "stock_done", item)
                self._checkpoint_unit(checkpoint, task_key, code.standard, result)
            except Exception as e:
                errors += 1
                logger.error(f"Failed {item.code}: {e}")
                _emit(code.standard, f"Failed: {code.standard} - {e}",
                      "error", "stock_done", item)

        # Always write JSON (even empty arrays for zero-signal runs)
        path = f"{job.output_dir}/{job.name}.json"
        self.storage.save_results(path, results)
        logger.info(f"Saved results to {path}")

        logger.info(
            f"Task {job.name} complete: {total} stocks | "
            f"{data_ok} analyzed, {no_data} no data, {errors} errors | "
            f"{len(results)} with signals"
        )

        return results
