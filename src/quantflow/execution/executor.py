"""Strategy execution with isolated signals, explicit coverage and replayable inputs."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from quantflow.artifacts import ArtifactWriteError, atomic_json, safe_name
from quantflow.config.loader import ConfigLoader
from quantflow.control import check_cancelled
from quantflow.data import StockCode
from quantflow.data.quality import prepare_daily_frame
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


class Executor:
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

    @IndicatorFactory.snapshot()
    def execute(self, job, on_progress=None, checkpoint=None, task_key=""):
        check_cancelled()
        name = safe_name(job.name)
        indicators = self._indicators(job.strategies)
        adjust = job.adjust or self.adjust
        identity = {
            "items": [
                getattr(i, "to_dict", lambda: {"code": self._code_str(i.code)})() for i in job.items
            ],
            "strategies": [s.name for s in job.strategies],
            "indicators": {i.name: i.params for i in indicators},
            "adjust": adjust,
            "days_back": job.days_back,
            "data_config": asdict(self.factory.config),
        }
        source_root = Path(__file__).resolve().parents[1]
        identity["code_hash"] = hashlib.sha256(
            b"".join(p.read_bytes() for p in sorted(source_root.rglob("*.py")))
        ).hexdigest()
        fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        key = f"execution:{task_key}"
        frozen = checkpoint.get_context(key) if checkpoint else None
        done = checkpoint.get_done(task_key) if checkpoint else set()
        if done and (not frozen or frozen.get("fingerprint") != fingerprint):
            raise ValueError("Checkpoint configuration/code changed; start a new run")
        if not frozen:
            now = job.as_of or datetime.now(timezone.utc).isoformat()
            end = job.end_date or pd.Timestamp(now).date().isoformat()
            frozen = {
                "fingerprint": fingerprint,
                "as_of": now,
                "end_date": end,
                "start_date": (pd.Timestamp(end) - timedelta(days=job.days_back))
                .date()
                .isoformat(),
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
        results = ScanResults()
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
        batch_items, sequential = [], []
        for item, code in pending:
            check_cancelled()
            try:
                market = self.factory._detect_market(code)
                primary = self.factory.config.get_primary(market)
                (
                    batch_items if self.factory.has_batch_support(primary, market) else sequential
                ).append((item, code))
            except Exception as exc:
                results.outcomes.append(StockOutcome(code.standard, "error", error=str(exc)))
                completed += 1
                emit("stock_done", code.standard, str(exc), "error")
        batch = {}
        if batch_items:

            def fetch_progress(index, count, code):
                check_cancelled()
                if on_progress:
                    on_progress(
                        ProgressEvent(
                            "fetch", index, count, str(code), f"Fetching {index}/{count}", "info"
                        )
                    )

            try:
                batch = self.factory.fetch_batch_ohlcv(
                    [c for _, c in batch_items],
                    frozen["start_date"],
                    frozen["end_date"],
                    adjust=adjust,
                    progress_cb=fetch_progress,
                )
            except Exception as exc:
                logger.exception("Batch download failed")
                batch = {c.standard: (None, str(exc)) for _, c in batch_items}
        for is_batch, pairs in ((True, batch_items), (False, sequential)):
            for item, code in pairs:
                emit("stock_start", code.standard, f"Analyzing {code.standard}")
                outcome = StockOutcome(code.standard, "error")
                result = None
                try:
                    if is_batch:
                        df, source = batch.get(code.standard, (pd.DataFrame(), None))
                        if df is None:
                            raise RuntimeError(source)
                    else:
                        df, source = self.factory.fetch_ohlcv(
                            code, frozen["start_date"], frozen["end_date"], adjust=adjust
                        )
                    check_cancelled()
                    outcome.source = source
                    if df is None or df.empty:
                        errors = self.factory.failures.get(code.standard, [])
                        outcome.status = "error" if errors else "no_data"
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
                                "rows": df.to_dict("records"),
                            },
                        )
                        outcome.snapshot_path = str(path)
                        outcome.snapshot_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
                        clean, expected, quality = prepare_daily_frame(
                            df, code, frozen["end_date"], frozen["as_of"]
                        )
                        clean.attrs.update(source=source, adjust=adjust)
                        outcome.expected_session = expected
                        outcome.bar_date = (
                            clean.date.iloc[-1].strftime("%Y-%m-%d") if not clean.empty else None
                        )
                        if quality != "ok":
                            outcome.status = quality
                        else:
                            result = self._process_single(
                                item, code, clean, job, indicators=indicators
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
