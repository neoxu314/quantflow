"""Execution Job definition."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List

from quantflow.artifacts import safe_name


@dataclass
class ExecutionJob:
    name: str
    items: List[Any]
    strategies: List[Any]
    output_dir: str
    days_back: int = 365
    end_date: str = None
    as_of: str = None
    adjust: str = None
    task_number: int | None = None

    @property
    def artifact_dir(self) -> Path:
        root = Path(self.output_dir)
        if self.task_number is None:
            return root
        return root / "tasks" / f"{self.task_number:04d}"

    def result_path(self, kind: str) -> Path:
        if self.task_number is not None:
            return self.artifact_dir / f"{kind}.json"
        name = safe_name(self.name)
        if name.casefold() in {"manifest", "run_summary", "combined_results", "daily_report"}:
            raise ValueError(f"Reserved run artifact name: {self.name}")
        stem = name if kind == "results" else f"{name}_{kind}"
        return self.artifact_dir / f"{stem}.json"

    @property
    def snapshot_dir(self) -> Path:
        key = safe_name(self.name) if self.task_number is None else f"{self.task_number:04d}"
        return Path(self.output_dir) / "snapshots" / key
