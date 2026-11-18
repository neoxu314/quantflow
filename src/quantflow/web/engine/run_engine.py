"""Serial, cooperative run lifecycle with immutable output ownership."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from quantflow.artifacts import (
    atomic_json,
    create_run_directory,
    finish_manifest,
    register_artifact,
)
from quantflow.config.logging import setup_logging
from quantflow.control import ExecutionCancelled, cancellation_scope, check_cancelled
from quantflow.execution.scanner import build_indicators, scan_stock

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[4]


class CancellationFlag:
    def __init__(self):
        self._flag = threading.Event()

    def cancel(self):
        self._flag.set()

    @property
    def is_set(self):
        return self._flag.is_set()


class RunEngine:
    def __init__(self, queue, history, sse):
        self._queue, self._history, self._sse = queue, history, sse
        self._cancellations, self._checkpoints = {}, {}
        self._state_lock = threading.RLock()
        self._workers = set()
        self._outputs = {}

    def start_processing(self, run_id):
        threading.Thread(target=self._execute_run, args=(run_id,), daemon=True).start()

    def enqueue(self, run_id):
        from quantflow.web.engine.run_queue import QueueFullError

        try:
            active = self._queue.enqueue(run_id)
        except QueueFullError:
            self._history.delete_run(run_id)
            raise
        if active:
            self.start_processing(run_id)
        return active

    def cancel(self, run_id):
        with self._state_lock:
            run = self._history.get_run(run_id)
            if run is None or run.status not in ("queued", "running", "cancelling"):
                return False
            self._history.update_status(run_id, "cancelling")
            if run_id in self._cancellations:
                self._cancellations[run_id].cancel()
            self._sse.publish_status(run_id, "cancelling")
            return True

    def _execute_run(self, run_id):
        with self._state_lock:
            if run_id in self._workers:
                return
            run = self._history.get_run(run_id)
            if run is None or run.status not in ("queued", "cancelling"):
                return
            self._workers.add(run_id)
            flag = CancellationFlag()
            if run.status == "cancelling":
                flag.cancel()
            self._cancellations[run_id] = flag
        output = None
        try:
            with cancellation_scope(flag):
                self._history.update_status(
                    run_id, "running", started_at=datetime.now(timezone.utc).isoformat()
                )
                defaults = {
                    "stock_scan": "./output/manual_scans",
                    "watchlist_run": "./output/manual_watchlist",
                    "task_run": "./output",
                }
                base = Path(run.config.get("output_path") or defaults[run.run_type])
                if not base.is_absolute():
                    base = PROJECT_ROOT / base
                if run.config.get("daily"):
                    base /= datetime.now().strftime("%Y-%m-%d")
                # Original user configuration remains unchanged in RunHistory.
                output = create_run_directory(base, run_id, config=run.config)
                self._outputs[run_id] = output
                self._history.update_status(run_id, "running", output_path=str(output))
                log = setup_logging(output, f"{run.run_type}_{run_id}")
                if log:
                    register_artifact(log)
                    self._history.update_status(run_id, "running", log_path=str(log))
                self._sse.publish_status(run_id, "running")
                checkpoint = None
                if run.run_type in ("watchlist_run", "task_run"):
                    from quantflow.execution.checkpoint import Checkpoint

                    # The resume API already copied its checkpoint exactly once.
                    checkpoint = Checkpoint.load_or_create(run_id, dict(run.config))
                self._checkpoints[run_id] = checkpoint
                check_cancelled()
                if run.run_type == "stock_scan":
                    self._exec_stock_scan(run_id, run, flag)
                elif run.run_type == "watchlist_run":
                    self._exec_watchlist_run(run_id, run, flag, checkpoint)
                elif run.run_type == "task_run":
                    self._exec_task_run(run_id, run, flag, checkpoint)
                else:
                    raise ValueError(f"Unknown run type: {run.run_type}")
        except ExecutionCancelled:
            self._mark_done(run_id, "cancelled")
        except Exception as exc:
            logger.exception("Run %s failed", run_id)
            self._mark_done(run_id, "failed", error=str(exc))
        finally:
            try:
                if output:
                    final = self._history.get_run(run_id)
                    finish_manifest(output, final.status if final else "failed")
            except Exception as exc:
                logger.exception("Could not finalize run manifest")
                self._mark_done(run_id, "failed", error=f"Manifest finalization failed: {exc}")
            finally:
                with self._state_lock:
                    self._cancellations.pop(run_id, None)
                    self._checkpoints.pop(run_id, None)
                    self._outputs.pop(run_id, None)
                    self._workers.discard(run_id)
                nxt = self._queue.finish(run_id)
                if nxt:
                    self.start_processing(nxt)

    def _progress_cb(self, run_id, flag):
        def callback(event):
            if flag.is_set:
                raise ExecutionCancelled()
            if event.type == "fetch":
                self._sse.publish_log(run_id, event.message)
            else:
                self._sse.publish_progress(run_id, event.current, event.total)
                self._sse.publish_log(run_id, event.message, event.level)

        return callback

    def _mark_done(self, run_id, status, **fields):
        with self._state_lock:
            flag = self._cancellations.get(run_id)
            if status in ("completed", "partial") and flag and flag.is_set:
                status = "cancelled"
            self._history.update_status(
                run_id, status, finished_at=datetime.now(timezone.utc).isoformat(), **fields
            )
            self._sse.publish_status(run_id, status)

    def _output(self, run_id, run):
        return self._outputs.get(run_id) or Path(
            run.output_path or run.config.get("output_path") or "./output"
        )

    def _exec_stock_scan(self, run_id, run, flag):
        with cancellation_scope(flag):
            output = self._output(run_id, run)
            path, bars, metadata = scan_stock(run.config, output)
            self._sse.publish_progress(run_id, 1, 1)
            self._mark_done(
                run_id, "completed", signal_count=bars, output_path=str(output), report_path=path
            )

    def _build_indicators_for_run(self, names, run_id=None):
        return build_indicators(names)

    def _exec_watchlist_run(self, run_id, run, flag, checkpoint=None):
        from quantflow.config.lookback import compute_days_back
        from quantflow.execution.executor import Executor
        from quantflow.execution.job import ExecutionJob
        from quantflow.execution.watchlist import Watchlist
        from quantflow.orchestration.registry import get_strategy_class
        from quantflow.reports.markdown import MarkdownReporter

        with cancellation_scope(flag):
            cfg = run.config
            wp = Path(cfg["watchlist"])
            wl = Watchlist.load(str(wp if wp.is_absolute() else PROJECT_ROOT / wp))
            strategies = [
                get_strategy_class(s)()
                for s in (cfg.get("strategies") or ["daily_bull_oversold", "daily_bull_mid_range"])
            ]
            output = self._output(run_id, run)
            job = ExecutionJob(
                f"web-{wl.name}",
                wl.items,
                strategies,
                str(output),
                compute_days_back(strategies, cfg.get("days_back")),
            )
            kwargs = {"on_progress": self._progress_cb(run_id, flag)}
            if checkpoint:
                kwargs.update(checkpoint=checkpoint, task_key="watchlist")
            results = Executor().execute(job, **kwargs)
            check_cancelled()
            path = MarkdownReporter().generate(
                job.name, strategies, results, wl, str(output), datetime.now().strftime("%Y-%m-%d")
            )
            summary = results.summary
            atomic_json(output / "Run_Summary.json", summary)
            self._mark_done(
                run_id,
                summary["status"],
                signal_count=len(results),
                output_path=str(output),
                report_path=path,
            )

    def _exec_task_run(self, run_id, run, flag, checkpoint=None):
        from quantflow.orchestration.app import Orchestrator
        from quantflow.orchestration.loader import TaskConfig

        with cancellation_scope(flag):
            tp = Path(run.config["task_config"])
            tasks = TaskConfig.load(str(tp if tp.is_absolute() else PROJECT_ROOT / tp))
            output = self._output(run_id, run)
            orch = Orchestrator(
                tasks,
                output_override=str(output),
                isolated=False,
                on_progress=self._progress_cb(run_id, flag),
                checkpoint=checkpoint,
            )
            count = orch.run()
            check_cancelled()
            self._mark_done(
                run_id,
                orch.last_summary["status"],
                signal_count=count,
                output_path=str(output),
                report_path=orch.report_path,
            )
