"""Strategy execution with isolated signals, explicit coverage and replayable inputs."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import pandas as pd

from quantflow.artifacts import ArtifactWriteError, atomic_json, safe_name
from quantflow.config.loader import ConfigLoader
from quantflow.control import ExecutionCancelled, check_cancelled
from quantflow.data import StockCode
from quantflow.data.quality import inspect_daily_bars, normalize_ohlcv, tradable_bars
from quantflow.data.trading_calendar import CALENDARS, completed_session
from quantflow.execution.identity import execution_hash
from quantflow.execution.storage import ExecutionResultItem, ScanResults, StockOutcome, Storage
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.factory import IndicatorFactory

logger = logging.getLogger(__name__)


class InsufficientHistoryError(ValueError):
    pass


@dataclass
class ProgressEvent:
    type: str
    current: int
    total: int
    code: str
    message: str
    level: str
    task: str | None = None


class Executor:
    # Persist analyzed work before downloading the next group in a large run.
    BATCH_SIZE = 50

    def __init__(self, config=None):
        self.config = config or ConfigLoader()
        self.factory = self.config.create_data_factory()
        self.adjust = self.config.get_adjust()
        self.storage = Storage()
        self.composer = IndicatorComposer([])

    def _indicators(self, strategies):
        indicators = {}
        for strategy in strategies:
            if strategy.get_required_period() != "d":
                raise ValueError("Daily executor cannot evaluate a non-daily strategy")
            for indicator in strategy.get_required_indicators():
                if (
                    indicator.name in indicators
                    and indicators[indicator.name].params != indicator.params
                ):
                    raise ValueError(f"Conflicting parameters for {indicator.name}")
                indicators[indicator.name] = indicator
        return list(indicators.values())

    def _process_single(self, item, code, df, job, indicators=None):
        indicators = self._indicators(job.strategies) if indicators is None else indicators
        self.composer.indicators = indicators
        df = self.composer.compose(df)
        for ind in indicators:
            if len(df) < ind.lookback_bars or df[ind.get_output_fields()].iloc[-1].isna().any():
                raise InsufficientHistoryError(f"Insufficient valid bars for {ind.name}")
        if len(df) < max((s.get_lookback_bars() for s in job.strategies), default=1):
            raise InsufficientHistoryError("Insufficient warmed history for strategy transition")
        # The immutable indicator frame is the input to EVERY strategy.
        base = df.drop(columns=["buy_signal", "sell_signal", "signal_reason"], errors="ignore")
        buys, sells, reasons = [], [], []
        for strategy in job.strategies:
            check_cancelled()
            evaluated = strategy.generate_signals(base.copy())
            row = evaluated.iloc[-1]
            directions = (
                ("buy", "sell") if strategy.signal_type == "mixed" else (strategy.signal_type,)
            )
            for direction in directions:
                value = row.get(f"{direction}_signal", False)
                if pd.notna(value) and bool(value):
                    (buys if direction == "buy" else sells).append(strategy.name)
                    reason = row.get("signal_reason", "")
                    if pd.notna(reason) and reason:
                        reasons.append(str(reason))
        if not buys and not sells:
            return None
        latest = df.iloc[-1]
        fields = dict.fromkeys(f for ind in indicators for f in ind.get_output_fields())
        return ExecutionResultItem(
            code=code.standard,
            name=code.name or getattr(item, "name", "") or "",
            buy_signals=len(buys),
            sell_signals=len(sells),
            reasons=list(dict.fromkeys(reasons)),
            matched_buy_strategies=buys,
            matched_sell_strategies=sells,
            bar_date=pd.Timestamp(latest["date"]).strftime("%Y-%m-%d") if "date" in df else None,
            source=df.attrs.get("source"),
            market=code.exchange,
            adjust=job.adjust or self.adjust,
            price=float(latest["close"]),
            indicators={f: latest[f] for f in fields},
            strategy_params={ind.name: ind.params for ind in indicators},
        )

    @staticmethod
    def _code_str(code):
        return code.standard if hasattr(code, "standard") else str(code)

    def execution_identity(self, job, indicators=None):
        indicators = self._indicators(job.strategies) if indicators is None else indicators
        dependencies = {}
        for package in ("exchange-calendars", "pandas", "numpy", *self.factory.ADAPTER_MAP):
            try:
                dependencies[package] = version(package)
            except PackageNotFoundError:
                dependencies[package] = None
        return {
            "items": [
                getattr(item, "to_dict", lambda: {"code": self._code_str(item.code)})()
                for item in job.items
            ],
            "strategies": [strategy.name for strategy in job.strategies],
            "indicators": {indicator.name: indicator.params for indicator in indicators},
            "adjust": job.adjust or self.adjust,
            "days_back": job.days_back,
            "end_date": job.end_date,
            "data_config": asdict(self.factory.config),
            "batch_config": {
                "yfinance": self.config.get_yfinance_config(),
                "yahooquery": self.config.get_yahooquery_config(),
            },
            "code_hash": execution_hash(),
            "dependencies": dependencies,
        }

    @IndicatorFactory.snapshot()
    def execute(self, job, on_progress=None, checkpoint=None, task_key=""):
        check_cancelled()
        name = safe_name(job.name)
        indicators = self._indicators(job.strategies)
        min_history_bars = max((s.get_lookback_bars() for s in job.strategies), default=1)
        adjust = job.adjust or self.adjust
        identity = self.execution_identity(job, indicators)
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        key = f"execution:{task_key}"
        frozen = checkpoint.get_context(key) if checkpoint else None
        done = checkpoint.get_done(task_key) if checkpoint else set()
        if not frozen or frozen.get("fingerprint") != fingerprint:
            if done:
                raise ValueError("Checkpoint configuration/code changed; start a new run")
            frozen = None
        if not frozen:
            now = job.as_of or datetime.now(timezone.utc).isoformat()
            frozen = {
                "fingerprint": fingerprint,
                "as_of": now,
                "end_date": job.end_date,
            }
            if checkpoint:
                checkpoint.set_context(key, frozen)
                checkpoint.save()
        atomic_json(Path(job.output_dir) / f"{name}_context.json", dict(frozen, execution=identity))
        cached = (
            {d["code"]: ExecutionResultItem.from_dict(d) for d in checkpoint.get_results(task_key)}
            if checkpoint
            else {}
        )
        results = ScanResults(as_of=frozen["as_of"])
        pending, total = [], len(job.items)
        # Completion count, rather than original item indices, remains monotonic across markets.
        completed = 0

        def emit(kind, code, message, level="info"):
            check_cancelled()
            if on_progress:
                on_progress(ProgressEvent(kind, completed, total, code, message, level))
            check_cancelled()

        for item in job.items:
            code = (
                item.code
                if isinstance(item.code, StockCode)
                else StockCode.from_standard(item.code)
            )
            if code.standard in done:
                stats = checkpoint.get_stats(task_key, code.standard)
                outcome = StockOutcome(**stats["outcome"])
                snapshot = Path(outcome.snapshot_path)
                if not snapshot.is_file():
                    raise ValueError("Checkpoint input snapshot is missing; start a new run")
                digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
                if digest != outcome.snapshot_sha256:
                    raise ValueError("Checkpoint input snapshot was modified; start a new run")
                dest = (
                    Path(job.output_dir) / "snapshots" / name / f"{safe_name(code.standard)}.json"
                )
                if dest.resolve() != snapshot.resolve():
                    atomic_json(dest, json.loads(snapshot.read_text(encoding="utf-8")))
                    outcome.snapshot_path = str(dest)
                    checkpoint.mark_done(
                        task_key,
                        code.standard,
                        stats={"outcome": asdict(outcome)},
                        result=cached[code.standard].to_dict() if code.standard in cached else None,
                    )
                results.outcomes.append(outcome)
                if code.standard in cached:
                    results.append(cached[code.standard])
                completed += 1
                emit("stock_done", code.standard, "Resumed from frozen snapshot")
            else:
                pending.append((item, code))
        batch_groups, sequential, sessions = defaultdict(list), [], {}
        for item, code in pending:
            check_cancelled()
            try:
                calendar = CALENDARS[code.exchange]
                if calendar not in sessions:
                    session_info = completed_session(code, frozen["end_date"], frozen["as_of"])
                    start = (
                        pd.Timestamp(session_info.date) - timedelta(days=job.days_back)
                    ).date().isoformat()
                    sessions[calendar] = start, session_info
                start, session_info = sessions[calendar]
                session = session_info.date
                market = self.factory._detect_market(code)
                primary = self.factory.config.get_primary(market)
                (
                    batch_groups[(start, session)]
                    if self.factory.has_batch_support(primary, market)
                    else sequential
                ).append((item, code, start, session))
            except Exception as exc:
                results.outcomes.append(StockOutcome(code.standard, "error", error=str(exc)))
                completed += 1
                emit("stock_done", code.standard, str(exc), "error")
        batch_total = sum(map(len, batch_groups.values()))

        def batches():
            offset = 0
            for (start, session), group in batch_groups.items():
                for first in range(0, len(group), self.BATCH_SIZE):
                    pairs = group[first:first + self.BATCH_SIZE]
                    codes = [code for _, code, _, _ in pairs]

                    def fetch_progress(index, _count, code):
                        check_cancelled()
                        current = offset + index
                        if on_progress:
                            on_progress(ProgressEvent(
                                "fetch", current, batch_total, str(code),
                                f"Fetch progress {current}/{batch_total}", "info", job.name,
                            ))

                    try:
                        batch = self.factory.fetch_batch_ohlcv(
                            codes, start, session, adjust=adjust, progress_cb=fetch_progress,
                            require_end_session=True, min_history_bars=min_history_bars,
                        )
                    except ExecutionCancelled:
                        raise
                    except Exception as exc:
                        logger.exception("Batch download failed")
                        batch = {code.standard: (None, str(exc)) for code in codes}
                    offset += len(pairs)
                    yield batch, pairs
            yield None, sequential

        for batch, pairs in batches():
            for item, code, start, session in pairs:
                emit("stock_start", code.standard, f"Analyzing {code.standard}")
                calendar_warning = sessions[CALENDARS[code.exchange]][1].calendar_warning
                outcome = StockOutcome(
                    code.standard, "error", expected_session=session, calendar_warning=calendar_warning
                )
                result = None
                try:
                    if batch is not None:
                        df, source = batch.get(code.standard, (pd.DataFrame(), None))
                        if df is None:
                            raise RuntimeError(source)
                    else:
                        df, source = self.factory.fetch_ohlcv(
                            code, start, session, adjust=adjust, require_end_session=True,
                            min_history_bars=min_history_bars,
                        )
                    check_cancelled()
                    outcome.source = source
                    if df is None or df.empty:
                        errors = self.factory.failures.get(code.standard, [])
                        outcome.status = "error" if errors else "no_data"
                        outcome.retryable_download = code.standard in self.factory.pending_network
                        outcome.error = "; ".join(errors) or "No data returned"
                    else:
                        path = (
                            Path(job.output_dir)
                            / "snapshots"
                            / name
                            / f"{safe_name(code.standard)}.json"
                        )
                        atomic_json(
                            path,
                            {
                                "schema_version": 1,
                                "code": code.standard,
                                "source": source,
                                "adjust": adjust,
                                "period": "d",
                                "volume_unit": "shares",
                                "fetched_at": datetime.now(timezone.utc).isoformat(),
                                "as_of": frozen["as_of"],
                                "query_start": start,
                                "expected_session": session,
                                "calendar_warning": calendar_warning,
                                "trading_status_source": df.attrs.get("trading_status_source"),
                                "listing_date": df.attrs.get("listing_date"),
                                "listing_date_source": df.attrs.get("listing_date_source"),
                                "price_adjustment_basis": df.attrs.get("price_adjustment_basis"),
                                "rows": df.to_dict("records"),
                            },
                        )
                        outcome.snapshot_path = str(path)
                        outcome.snapshot_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                        clean = normalize_ohlcv(df, start, session)
                        clean.attrs.update(source=source, adjust=adjust)
                        quality = inspect_daily_bars(clean, code, session)
                        outcome.missing_sessions = quality.missing_sessions
                        outcome.unexpected_dates = quality.unexpected_dates
                        outcome.confirmed_suspensions = quality.confirmed_suspensions
                        outcome.listing_date = df.attrs.get("listing_date")
                        outcome.bar_date = (
                            clean.date.iloc[-1].strftime("%Y-%m-%d") if not clean.empty else None
                        )
                        if quality.status != "ok":
                            outcome.status = quality.status
                        else:
                            result = self._process_single(
                                item, code, tradable_bars(clean), job, indicators=indicators
                            )
                            outcome.status = "signal" if result else "no_signal"
                except ArtifactWriteError:
                    raise
                except InsufficientHistoryError as exc:
                    outcome.status, outcome.error = "insufficient", str(exc)
                except Exception as exc:
                    outcome.status, outcome.error = "error", str(exc)
                    logger.exception("Failed %s", code.standard)
                check_cancelled()
                results.outcomes.append(outcome)
                if result:
                    results.append(result)
                # Temporary data failures and stale/short history remain retryable.
                if checkpoint and outcome.status in ("signal", "no_signal"):
                    checkpoint.mark_done(
                        task_key,
                        code.standard,
                        stats={"outcome": asdict(outcome)},
                        result=result.to_dict() if result else None,
                    )
                completed += 1
                emit(
                    "stock_done",
                    code.standard,
                    f"{code.standard}: {outcome.status}",
                    "info" if outcome.status in ("signal", "no_signal") else "warning",
                )
        check_cancelled()
        self.storage.save_results(Path(job.output_dir) / f"{name}.json", results)
        self.storage.save_coverage(Path(job.output_dir) / f"{name}_coverage.json", results)
        logger.info("Task %s: %s", name, results.summary)
        return results
