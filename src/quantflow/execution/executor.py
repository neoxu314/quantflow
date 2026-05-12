"""Stock Executor for processing execution jobs."""

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

    def execute(
        self,
        job: ExecutionJob,
        on_progress: Optional[Callable[[ProgressEvent], None]] = None,
    ) -> List[ExecutionResultItem]:
        total = len(job.items)
        def _emit(code: str, msg: str, level: str = "info",
                  etype: str = "log", idx: int = 0):
            if on_progress:
                on_progress(ProgressEvent(
                    type=etype, current=idx, total=total,
                    code=code, message=msg, level=level,
                ))
        logger.info(f"Starting execution: {job.name} ({total} items)")
        results = []
        start_date = (datetime.now() - timedelta(days=job.days_back)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        yfinance_items: List[tuple] = []
        other_items: List[tuple] = []

        for item in job.items:
            code = item.code
            if isinstance(code, str):
                code = StockCode.from_standard(code)
            market = self.factory._detect_market(code)
            primary = self.factory.config.get_primary(market)
            if self.factory.has_batch_support(primary, market):
                yfinance_items.append((item, code))
            else:
                other_items.append((item, code))

        yf_data: Dict[str, pd.DataFrame] = {}
        if yfinance_items:
            yf_codes = [code for _, code in yfinance_items]
            batch_result = self.factory.fetch_batch_ohlcv(
                yf_codes, start_date, end_date
            )
            for code_str, (df, _src) in batch_result.items():
                yf_data[code_str] = df
            logger.info(
                f"Batch complete: {len(yf_data)}/{len(yfinance_items)} stocks"
            )

        data_ok = 0
        no_data = 0
        errors = 0
        for idx, (item, code) in enumerate(yfinance_items, 1):
            df = yf_data.get(code.standard)
            _emit(code.standard, f"[{idx}/{total}] {code.standard}",
                  "info", "stock_start", idx)
            if df is None or df.empty:
                no_data += 1
                logger.warning(f"No data for {item.code}")
                _emit(code.standard, f"No data: {code.standard}",
                      "warning", "stock_done", idx)
                continue
            data_ok += 1
            result = self._process_single(item, code, df, job)
            sigs = result.buy_signals + result.sell_signals if result else 0
            if result:
                results.append(result)
                _emit(code.standard, f"Done: {code.standard} ({sigs} signals)",
                      "info", "stock_done", idx)
            else:
                _emit(code.standard, f"Done: {code.standard} (0 signals)",
                      "info", "stock_done", idx)

        for idx, (item, code) in enumerate(other_items, 1):
            try:
                _emit(code.standard, f"[{idx}/{total}] {code.standard}",
                      "info", "stock_start", idx)
                logger.info(f"Processing [{idx}/{total}]: {item.code}")
                df, _ = self.factory.fetch_ohlcv(
                    code, start_date=start_date, end_date=end_date
                )
                if df.empty:
                    no_data += 1
                    logger.warning(f"No data for {item.code}")
                    _emit(code.standard, f"No data: {code.standard}",
                          "warning", "stock_done", idx)
                    continue
                data_ok += 1
                result = self._process_single(item, code, df, job)
                sigs = result.buy_signals + result.sell_signals if result else 0
                if result:
                    results.append(result)
                    _emit(code.standard, f"Done: {code.standard} ({sigs} signals)",
                          "info", "stock_done", idx)
                else:
                    _emit(code.standard, f"Done: {code.standard} (0 signals)",
                          "info", "stock_done", idx)
            except Exception as e:
                errors += 1
                logger.error(f"Failed {item.code}: {e}")
                _emit(code.standard, f"Failed: {code.standard} - {e}",
                      "error", "stock_done", idx)

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
