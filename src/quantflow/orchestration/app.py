"""Orchestrator Application."""

import logging
from datetime import datetime
from pathlib import Path

from quantflow.config.lookback import compute_days_back
from quantflow.execution.executor import Executor
from quantflow.execution.job import ExecutionJob
from quantflow.execution.storage import Storage
from quantflow.execution.watchlist import Watchlist
from quantflow.orchestration.registry import get_strategy_class
from quantflow.reports.markdown import MarkdownReporter

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, tasks_config: list,
                 output_override: str = None,
                 daily_mode: bool = False):
        self.tasks = tasks_config
        self.executor = Executor()
        self.reporter = MarkdownReporter()
        self.output_override = output_override
        self.daily_mode = daily_mode

    def _resolve_task_dir(self, cfg):
        base = self.output_override or "./output"
        if self.daily_mode:
            return str(Path(base) / self.date_str)
        return base

    def _resolve_combined_dir(self):
        base = self.output_override or "reports"
        if self.daily_mode:
            return str(Path(base) / self.date_str)
        return base

    def run(self):
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        task_runs = []
        storage = Storage()

        for cfg in self.tasks:
            try:
                logger.info(f"--> Task: {cfg.name}")
                try:
                    strategies = [
                        get_strategy_class(s)()
                        for s in cfg.strategy_names
                    ]
                except Exception as e:
                    logger.error(f"Strategy resolution failed: {e}")
                    continue

                days_back = compute_days_back(
                    strategies=strategies, override=cfg.days_back)
                task_dir = self._resolve_task_dir(cfg)
                logger.info(
                    f"   Lookback: {days_back} calendar days "
                    f"| Output: {task_dir}")

                watchlist = Watchlist.load(cfg.watchlist_path)
                job = ExecutionJob(
                    name=cfg.name,
                    items=watchlist.items,
                    strategies=strategies,
                    output_dir=task_dir,
                    days_back=days_back
                )
                results = self.executor.execute(job)
                self.reporter.generate(
                    cfg.name, strategies, results, watchlist,
                    task_dir, self.date_str)

                task_runs.append(
                    (cfg.name, results, watchlist, strategies))
            except Exception as e:
                logger.error(f"Task {cfg.name} failed: {e}")

        if task_runs:
            combined_dir = self._resolve_combined_dir()
            all_results = [
                r for _, results, _, _ in task_runs for r in results
            ] if task_runs else []
            combined_json_path = (
                f"{combined_dir}/Combined_Results.json")
            storage.save_results(combined_json_path, all_results)
            self.reporter.generate_combined(
                self.date_str, task_runs, combined_dir)
            logger.info(f"Combined report saved to {combined_dir}")

        total_signals = sum(
            len(r) for _, r, _, _ in task_runs)

        task_count = len(self.tasks)
        completed = len(task_runs)
        total_stocks = sum(len(wl.items) for _, _, wl, _ in task_runs)
        logger.info(
            f"All tasks complete: {completed}/{task_count} tasks, "
            f"{total_stocks} stocks scanned, {total_signals} signals"
        )

        return total_signals
