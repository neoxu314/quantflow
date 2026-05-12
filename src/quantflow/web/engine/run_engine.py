"""RunEngine — wraps execution in background threads with progress."""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from quantflow.web.engine.run_history import RunHistory
from quantflow.web.engine.run_queue import RunQueue
from quantflow.web.engine.sse import SSEManager

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[4]


class CancellationFlag:
    def __init__(self):
        self._flag = threading.Event()

    def cancel(self):
        self._flag.set()

    @property
    def is_set(self) -> bool:
        return self._flag.is_set()


class RunEngine:
    def __init__(self, queue: RunQueue, history: RunHistory,
                 sse: SSEManager):
        self._queue = queue
        self._history = history
        self._sse = sse
        self._cancellations: dict[str, CancellationFlag] = {}

    def start_processing(self, run_id: str) -> None:
        t = threading.Thread(target=self._execute_run, args=(run_id,),
                             daemon=True)
        t.start()

    def cancel(self, run_id: str) -> bool:
        if run_id in self._cancellations:
            self._cancellations[run_id].cancel()
            return True
        return False

    def _execute_run(self, run_id: str) -> None:
        run = self._history.get_run(run_id)
        if not run:
            return

        flag = CancellationFlag()
        self._cancellations[run_id] = flag
        now = datetime.now(timezone.utc).isoformat()
        self._history.update_status(run_id, "running", started_at=now)
        self._sse.publish_status(run_id, "running")
        self._sse.publish_log(run_id, f"Starting: {run.name} ({run.run_type})")

        try:
            if flag.is_set:
                self._mark_done(run_id, "cancelled")
                return

            if run.run_type == "stock_scan":
                self._exec_stock_scan(run_id, run, flag)
            elif run.run_type == "watchlist_run":
                self._exec_watchlist_run(run_id, run, flag)
            elif run.run_type == "task_run":
                self._exec_task_run(run_id, run, flag)
            else:
                self._history.update_status(
                    run_id, "failed",
                    error=f"Unknown type: {run.run_type}")
        except Exception as e:
            logger.exception(f"Run {run_id} failed")
            self._history.update_status(
                run_id, "failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                error=str(e))
            self._sse.publish_log(run_id, f"ERROR: {e}", "error")
        finally:
            self._cancellations.pop(run_id, None)
            nxt = self._queue.dequeue()
            if nxt:
                self.start_processing(nxt)

    def _progress_cb(self, run_id: str, flag: CancellationFlag):
        def _cb(event):
            if flag.is_set:
                return
            if event.type == "stock_start":
                self._sse.publish_log(
                    run_id,
                    f"[{event.current}/{event.total}] {event.code}...")
                self._sse.publish_progress(run_id, event.current, event.total)
            elif event.type == "stock_done":
                self._sse.publish_log(
                    run_id, f"[{event.current}/{event.total}] {event.message}",
                    level=event.level)
                self._sse.publish_progress(run_id, event.current, event.total)
        return _cb

    def _mark_done(self, run_id: str, status: str):
        finished = datetime.now(timezone.utc).isoformat()
        self._history.update_status(run_id, status, finished_at=finished)
        self._sse.publish_status(run_id, status)

    def _exec_stock_scan(self, run_id: str, run, flag: CancellationFlag):
        import math
        from datetime import datetime as dt
        from datetime import timedelta

        import pandas as pd

        from quantflow.config.loader import ConfigLoader
        from quantflow.config.lookback import load_lookback_config
        from quantflow.data.base import StockCode
        from quantflow.data.factory import DataSourceFactory
        from quantflow.indicators.composer import IndicatorComposer

        cfg = run.config
        code = StockCode.from_standard(cfg["code"])
        output = cfg.get("output_path") or "./output/manual_scans"

        start_date = cfg.get("start_date") or (
            dt.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        end_date = cfg.get("end_date") or dt.now().strftime("%Y-%m-%d")

        indicator_names = cfg.get("indicators", ["kdj", "dual_line"])
        indicators = self._build_indicators_for_run(indicator_names, run_id)

        # Calculate warm-up period using system lookback config
        if indicators:
            lookback_cfg = load_lookback_config()
            multiplier = lookback_cfg.get("calendar_multiplier", 2)
            buffer = lookback_cfg.get("buffer_days", 30)
            max_lookback = max(ind.lookback_bars for ind in indicators)

            fetch_start_date = dt.strptime(start_date, "%Y-%m-%d") - timedelta(
                days=math.ceil(max_lookback * multiplier) + buffer)
            fetch_start = fetch_start_date.strftime("%Y-%m-%d")
        else:
            fetch_start = start_date

        config_loader = ConfigLoader()
        factory = DataSourceFactory(
            yfinance_config=config_loader.get_yfinance_config(),
            yahooquery_config=config_loader.get_yahooquery_config(),
        )
        df, source = factory.fetch_ohlcv(code, fetch_start, end_date)

        if df.empty:
            raise ValueError(f"No data for {cfg['code']} from {source}")

        actual_end = factory._latest_date(df)
        if actual_end < end_date:
            self._sse.publish_log(
                run_id,
                f"⚠️ No data on {end_date}. Using latest available: {actual_end}",
                "warning")

        self._sse.publish_log(
            run_id, f"Data source: {source}, bars: {len(df)}")

        self._sse.publish_log(
            run_id,
            f"Indicators: {', '.join(i.name for i in indicators)}, calculating...")

        df = IndicatorComposer(indicators).compose(df)

        if "date" in df.columns:
            # YFinance adds exchange-local timezone; strip it so date comparison
            # with user-supplied strings works uniformly across all markets.
            dt_col = pd.to_datetime(df["date"]).dt.tz_localize(None)
            mask = (dt_col >= pd.Timestamp(start_date)) & (dt_col <= pd.Timestamp(end_date))
            matched = mask.sum()
            if matched > 0:
                result_rows = df.loc[mask]
            else:
                self._sse.publish_log(
                    run_id,
                    f"⚠️ Date filter returned 0 rows for {start_date} to {end_date}, using full data ({len(df)} bars)",
                    "warning",
                )
                result_rows = df
        else:
            self._sse.publish_log(
                run_id, "⚠️ No 'date' column found in DataFrame, using full data", "warning"
            )
            result_rows = df

        is_single_day = (start_date == end_date)
        if is_single_day:
            result_rows = result_rows.tail(1)

        Path(output).mkdir(parents=True, exist_ok=True)
        safe_code = cfg["code"].replace("/", "_").replace("\\", "_")
        data_file = Path(output) / f"{safe_code}_indicators.json"

        def _serialize_df(df):
            import math
            out = []
            for row in df.to_dict(orient="records"):
                clean = {}
                for k, v in row.items():
                    if hasattr(v, "isoformat"):
                        clean[k] = v.isoformat()
                    elif hasattr(v, "item"):
                        try:
                            val = v.item()
                            if isinstance(val, float) and math.isnan(val):
                                val = None
                            clean[k] = val
                        except Exception:
                            clean[k] = str(v)
                    elif isinstance(v, float):
                        import math as _math
                        clean[k] = None if _math.isnan(v) else v
                    else:
                        clean[k] = v
                out.append(clean)
            return out

        indicator_data = _serialize_df(result_rows)
        data_file.write_text(json.dumps(indicator_data, indent=2))

        total_bars = len(result_rows)
        self._history.update_status(
            run_id, "completed",
            finished_at=dt.now(timezone.utc).isoformat(),
            signal_count=total_bars, output_path=str(output),
            report_path=str(data_file))
        self._sse.publish_log(
            run_id, f"Complete: {total_bars} bars saved")
        self._sse.publish_status(run_id, "completed",
                                 signal_count=total_bars)

    def _build_indicators_for_run(self, names: list[str],
                                  run_id: str = None):
        name_map = {
            "kdj": "KDJ", "macd": "MACD", "rsi": "RSI",
            "boll": "BOLL", "vol_ma": "VolumeMA",
            "dual_line": "DualLine",
            "brick_chart": "BrickChart", "washout": "Washout",
        }
        from quantflow.indicators.factory import IndicatorFactory
        indicators = []
        for name in names:
            canonical = name_map.get(name, name)
            try:
                indicators.append(IndicatorFactory.create(canonical))
            except Exception as e:
                self._sse.publish_log(
                    run_id, f"Skipped {name}: {e}", "warning")
        if not indicators:
            indicators = [
                IndicatorFactory.create("KDJ"),
                IndicatorFactory.create("DualLine"),
            ]
        return indicators

    def _exec_watchlist_run(self, run_id: str, run, flag: CancellationFlag):
        from datetime import datetime as dt

        from quantflow.config.lookback import compute_days_back
        from quantflow.execution.executor import Executor
        from quantflow.execution.job import ExecutionJob
        from quantflow.execution.watchlist import Watchlist
        from quantflow.orchestration.registry import STRATEGY_REGISTRY
        from quantflow.reports.markdown import MarkdownReporter

        cfg = run.config
        wp = cfg["watchlist"]
        p = Path(wp) if os.path.isabs(wp) else PROJECT_ROOT / wp
        wl = Watchlist.load(str(p))
        output = cfg.get("output_path") or "./output/manual_watchlist"
        sids = cfg.get("strategies", [
            "daily_bull_oversold", "daily_bull_mid_range"])
        strategies = [STRATEGY_REGISTRY[s]() for s in sids]

        days_back = compute_days_back(
            strategies=strategies, override=cfg.get("days_back"))

        self._sse.publish_log(
            run_id, f"Lookback: {days_back} days for {len(wl.items)} stocks")

        job = ExecutionJob(
            name=f"web-{wl.name}", items=wl.items, strategies=strategies,
            output_dir=output, days_back=days_back)
        results = Executor().execute(
            job, on_progress=self._progress_cb(run_id, flag))

        date_str = dt.now().strftime("%Y-%m-%d")
        rpath = MarkdownReporter().generate(
            f"web-{wl.name}", strategies, results, wl, output, date_str)

        self._history.update_status(
            run_id, "completed",
            finished_at=dt.now(timezone.utc).isoformat(),
            signal_count=len(results), output_path=output,
            report_path=rpath)
        self._sse.publish_log(
            run_id,
            f"Complete: {len(results)} signals from {len(wl.items)} stocks")
        self._sse.publish_status(run_id, "completed",
                                 signal_count=len(results))

    def _exec_task_run(self, run_id: str, run, flag: CancellationFlag):
        from datetime import datetime as dt

        from quantflow.orchestration.app import Orchestrator
        from quantflow.orchestration.loader import TaskConfig

        cfg = run.config
        tp = cfg["task_config"]
        p = Path(tp) if os.path.isabs(tp) else PROJECT_ROOT / tp
        configs = TaskConfig.load(str(p))
        output = cfg.get("output_path") or "./output"
        daily = cfg.get("daily", False)

        self._sse.publish_log(
            run_id,
            f"Running {len(configs)} task(s) via Orchestrator...")
        signal_count = Orchestrator(
            configs, output_override=output, daily_mode=daily).run()

        rdir = output
        if daily:
            rdir = str(Path(rdir) / dt.now().strftime("%Y-%m-%d"))

        rpath = str(Path(rdir) / "Daily_Report.md")
        if not Path(rpath).exists():
            rpath = None
        self._history.update_status(
            run_id, "completed",
            finished_at=dt.now(timezone.utc).isoformat(),
            signal_count=signal_count, output_path=output,
            report_path=rpath)
        self._sse.publish_log(
            run_id, f"Orchestration tasks complete: {signal_count} signals")
        self._sse.publish_status(
            run_id, "completed", signal_count=signal_count)
