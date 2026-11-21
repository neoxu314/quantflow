"""Task orchestration with explicit task failures and a run-owned output directory."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from quantflow.artifacts import (
    ArtifactWriteError,
    atomic_json,
    create_run_directory,
    finish_manifest,
    register_artifact,
)
from quantflow.config.logging import setup_logging
from quantflow.config.lookback import compute_days_back
from quantflow.control import ExecutionCancelled, check_cancelled
from quantflow.execution.executor import Executor, ProgressEvent
from quantflow.execution.job import ExecutionJob
from quantflow.execution.storage import ScanResults, StockOutcome, Storage
from quantflow.execution.watchlist import Watchlist
from quantflow.indicators.factory import IndicatorFactory
from quantflow.orchestration.registry import get_strategy_class
from quantflow.reports.markdown import MarkdownReporter

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        tasks_config,
        output_override=None,
        daily_mode=False,
        on_progress=None,
        checkpoint=None,
        isolated=True,
        as_of=None,
    ):
        self.tasks = tasks_config
        self.executor = Executor()
        self.reporter = MarkdownReporter()
        self.output_override = output_override
        self.daily_mode = daily_mode
        self.on_progress = on_progress
        self.checkpoint = checkpoint
        self.isolated = isolated
        self.as_of = as_of or datetime.now(timezone.utc).isoformat()
        self.last_summary = None
        self.output_dir = None
        self.report_path = None

    def prepare_tasks(self, output_dir):
        """Resolve the ordered task inputs once, before processing any stock."""
        prepared = []
        for number, cfg in enumerate(self.tasks, start=1):
            check_cancelled()
            path = Path(cfg.watchlist_path)
            if not path.is_absolute() and not path.exists():
                path = Path(__file__).resolve().parents[3] / path
            watchlist, job, error = None, None, None
            try:
                watchlist = Watchlist.load(str(path))
                strategies = [get_strategy_class(name)() for name in cfg.strategy_names]
                if not strategies:
                    raise ValueError("Task has no strategies")
                self.executor._indicators(strategies)
                job = ExecutionJob(
                    cfg.name, watchlist.items, strategies, str(output_dir),
                    compute_days_back(strategies, cfg.days_back), as_of=self.as_of, task_number=number,
                )
            except Exception as exc:
                error = exc
            prepared.append((cfg, path.resolve(), watchlist, job, error))
        return prepared

    def run_plan(self, prepared):
        return {"tasks": [
            {
                "name": cfg.name,
                "watchlist_path": str(path),
                "watchlist": watchlist.to_dict() if watchlist else None,
                "strategy_ids": cfg.strategy_names,
                "configured_days_back": cfg.days_back,
                "execution": self.executor.execution_identity(job) if job else None,
            }
            for cfg, path, watchlist, job, _ in prepared
        ]}

    @IndicatorFactory.snapshot()
    def run(self):
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        base = Path(self.output_override or "./output")
        if self.daily_mode:
            base /= self.date_str
        self.output_dir = create_run_directory(base) if self.isolated else base.resolve()
        tasks, errors, combined = [], [], ScanResults()
        unreadable_watchlists = 0
        try:
            if self.checkpoint:
                frozen_as_of = self.checkpoint.get_context("orchestration:as_of")
                if frozen_as_of is None:
                    self.checkpoint.set_context("orchestration:as_of", self.as_of)
                    self.checkpoint.save()
                else:
                    self.as_of = frozen_as_of
            if self.isolated:
                logfile = setup_logging(self.output_dir, "task_run")
                if logfile:
                    register_artifact(logfile)
            prepared = self.prepare_tasks(self.output_dir)
            if self.checkpoint:
                self.checkpoint.freeze_run_plan(self.run_plan(prepared))
            offset = 0
            total = sum(len(watchlist.items) for _, _, watchlist, _, _ in prepared if watchlist)
            for cfg, _, wl, job, input_error in prepared:
                check_cancelled()
                if wl is None:
                    errors.append({"task": cfg.name, "error": str(input_error)})
                    unreadable_watchlists += 1
                    continue
                try:
                    if input_error is not None:
                        raise input_error
                    strategies = job.strategies

                    def progress(event, base_offset=offset):
                        check_cancelled()
                        if event.type == "fetch":
                            self.on_progress(event)
                            return
                        self.on_progress(
                            ProgressEvent(
                                event.type,
                                base_offset + event.current,
                                total,
                                event.code,
                                event.message,
                                event.level,
                            )
                        )

                    kwargs = {}
                    if self.on_progress:
                        kwargs["on_progress"] = progress
                    if self.checkpoint:
                        kwargs.update(checkpoint=self.checkpoint, task_key=cfg.name)
                    results = self.executor.execute(job, **kwargs)
                    check_cancelled()
                    self.reporter.generate(
                        cfg.name, strategies, results, wl, str(job.artifact_dir), self.date_str,
                        file_stem="report",
                    )
                    combined.extend(results)
                    if isinstance(results, ScanResults):
                        combined.outcomes.extend(results.outcomes)
                    tasks.append((cfg.name, results, wl, strategies))
                except ArtifactWriteError:
                    raise
                except Exception as exc:
                    logger.exception("Task %s failed", cfg.name)
                    errors.append({"task": cfg.name, "error": str(exc)})
                    combined.outcomes.extend(
                        StockOutcome(item.code.standard, "error", error=str(exc))
                        for item in wl.items
                    )
                offset += len(wl.items)
            check_cancelled()
            summary = combined.summary
            if errors or len(tasks) != len(self.tasks):
                summary["status"] = "partial" if summary["analyzed"] else "failed"
            summary.update(
                tasks_requested=len(self.tasks), tasks_completed=len(tasks), task_errors=errors,
                as_of=self.as_of,
                task_directories={
                    cfg.name: job.artifact_dir.relative_to(self.output_dir).as_posix()
                    for cfg, _, _, job, _ in prepared if job is not None
                },
            )
            if unreadable_watchlists:
                summary["enumerated_coverage"] = summary["coverage"] if summary["total"] else None
                summary["coverage"] = None
                summary["unreadable_watchlists"] = unreadable_watchlists
            elif errors and not summary["total"]:
                summary["coverage"] = 0.0
            self.last_summary = summary
            storage = Storage()
            storage.save_results(self.output_dir / "Combined_Results.json", combined)
            atomic_json(self.output_dir / "Run_Summary.json", summary)
            self.report_path = self.reporter.generate_combined(
                self.date_str, tasks, str(self.output_dir), summary=summary
            )
            if self.isolated:
                finish_manifest(self.output_dir, summary["status"], summary=summary)
            return len(combined)
        except ExecutionCancelled:
            if self.isolated:
                finish_manifest(self.output_dir, "cancelled")
            raise
        except Exception:
            if self.isolated:
                finish_manifest(self.output_dir, "failed")
            raise
