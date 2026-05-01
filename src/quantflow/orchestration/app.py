"""Orchestrator Application."""

import logging
import math
import yaml
from pathlib import Path
from typing import Optional
from datetime import datetime
from .registry import get_strategy_class
from .loader import TaskConfig
from quantflow.execution.executor import Executor
from quantflow.execution.job import ExecutionJob
from quantflow.execution.watchlist import Watchlist
from quantflow.execution.storage import Storage
from quantflow.reports.markdown import MarkdownReporter

logger = logging.getLogger(__name__)


def _load_lookback_config() -> dict:
    defaults = {"calendar_multiplier": 2, "buffer_days": 30}
    config_path = Path(__file__).parents[3] / "config" / "quantflow.yaml"
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
        if "lookback" in data:
            defaults.update(data["lookback"])
    return defaults


def _compute_days_back(strategies, override: Optional[int]) -> int:
    if override is not None:
        return override
    if not strategies:
        return 365
    cfg = _load_lookback_config()
    multiplier = cfg.get("calendar_multiplier", 2)
    buffer_days = cfg.get("buffer_days", 30)
    max_bars = max(s.get_lookback_bars() for s in strategies)
    return math.ceil(max_bars * multiplier) + buffer_days


class Orchestrator:
    def __init__(self, tasks_config: list, output_override: str = None, daily_mode: bool = False):
        self.tasks = tasks_config
        self.executor = Executor()
        self.reporter = MarkdownReporter()
        self.output_override = output_override
        self.daily_mode = daily_mode

    def _resolve_task_dir(self, cfg):
        base = cfg.output_dir
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
                    strategies = [get_strategy_class(s)() for s in cfg.strategy_names]
                except Exception as e:
                    logger.error(f"Strategy resolution failed: {e}")
                    continue

                days_back = _compute_days_back(strategies, cfg.days_back)
                task_dir = self._resolve_task_dir(cfg)
                logger.info(f"   Lookback: {days_back} calendar days | Output: {task_dir}")

                watchlist = Watchlist.load(cfg.watchlist_path)
                job = ExecutionJob(
                    name=cfg.name,
                    items=watchlist.items,
                    strategies=strategies,
                    output_dir=task_dir,
                    days_back=days_back
                )
                results = self.executor.execute(job)
                self.reporter.generate(cfg.name, strategies, results, watchlist, task_dir, self.date_str)
                
                task_runs.append((cfg.name, results, watchlist, strategies))
            except Exception as e:
                logger.error(f"Task {cfg.name} failed: {e}")

        if task_runs:
            combined_dir = self._resolve_combined_dir()
            all_results = [r for _, results, _, _ in task_runs for r in results] if task_runs else []
            combined_json_path = f"{combined_dir}/Combined_Results.json"
            storage.save_results(combined_json_path, all_results)
            self.reporter.generate_combined(self.date_str, task_runs, combined_dir)
            logger.info(f"Combined report saved to {combined_dir}")
