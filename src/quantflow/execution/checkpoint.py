"""Per-run checkpoint metadata and results for watchlist and task runs.

The JSON file in `~/.quantflow/checkpoints/` records analyzed stocks, their
results and frozen execution context. Validated OHLCV inputs live separately
in the run directory. Resume verifies the plan, execution identity and inputs,
then copies completed work into a new run and fetches unfinished stocks at the
original cutoff. The checkpoint itself is saved with the shared atomic writer.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from quantflow.artifacts import atomic_json

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path.home() / ".quantflow" / "checkpoints"
VERSION = 1


class ResumePlanError(ValueError):
    """The saved work cannot be reused with the requested run inputs."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def checkpoint_path(run_id: str) -> Path:
    return CHECKPOINT_DIR / f"{run_id}.json"


class Checkpoint:
    """Thread-safe, atomically-persisted per-run progress checkpoint."""

    def __init__(self, run_id: str, path: Optional[Path] = None):
        self.run_id = run_id
        self.path = Path(path) if path else checkpoint_path(run_id)
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {
            "version": VERSION,
            "run_id": run_id,
            "created_at": _utcnow(),
            "updated_at": _utcnow(),
            "config": {},
            "context": {},          # run plan, cutoff and per-task execution context
            "work": {},             # task_key -> {"done": {code: stats}}
            "results": {},          # task_key -> [result dict, ...]
        }

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls, run_id: str, path: Optional[Path] = None) -> Optional["Checkpoint"]:
        p = Path(path) if path else checkpoint_path(run_id)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.warning("Checkpoint %s unreadable, ignoring: %s", p, e)
            return None
        if (
            not isinstance(data, dict) or data.get("run_id", run_id) != run_id
            or any(not isinstance(data.get(key, {}), dict)
                   for key in ("config", "context", "work", "results"))
            or any(not isinstance(task, dict) or not isinstance(task.get("done", {}), dict)
                   for task in data.get("work", {}).values())
        ):
            logger.warning("Checkpoint %s has invalid structure", p)
            return None
        cp = cls(run_id, p)
        # Merge the full payload so custom metadata (e.g. ``resumed_from``)
        # survives; defaults only fill in keys missing from older versions.
        defaults = dict(cp._data)
        cp._data = dict(data)
        for k, v in defaults.items():
            cp._data.setdefault(k, v)
        cp._data.setdefault("version", VERSION)
        cp._data.setdefault("work", {})
        cp._data.setdefault("results", {})
        cp._data.setdefault("context", {})
        return cp

    @classmethod
    def load_or_create(cls, run_id: str, config: Optional[dict] = None) -> "Checkpoint":
        cp = cls.load(run_id)
        if cp is None:
            cp = cls(run_id)
            if config is not None:
                cp.set_config(config)
        elif config is not None and not cp._data.get("config"):
            cp.set_config(config)
        return cp

    # -------------------------------------------------------------- persist
    def save(self) -> None:
        with self._lock:
            self._data["updated_at"] = _utcnow()
            atomic_json(self.path, self._data, register=False)

    def delete(self) -> bool:
        with self._lock:
            if self.path.exists():
                self.path.unlink()
                return True
            return False

    @classmethod
    def copy_to(cls, src_run_id: str, dst_run_id: str) -> bool:
        """Copy a checkpoint to a new run id (used when resuming)."""
        checkpoint = cls.load(src_run_id)
        if checkpoint is None:
            return False
        destination = cls(dst_run_id)
        destination._data = checkpoint._data
        destination._data["run_id"] = dst_run_id
        destination._data["resumed_from"] = src_run_id
        try:
            destination.save()
            return True
        except OSError as exc:
            logger.warning("Failed to copy checkpoint %s -> %s: %s", src_run_id, dst_run_id, exc)
            return False

    @classmethod
    def exists(cls, run_id: str) -> bool:
        return checkpoint_path(run_id).exists()

    # ----------------------------------------------------------------- data
    def set_config(self, config: dict) -> None:
        with self._lock:
            self._data["config"] = dict(config)

    @property
    def config(self) -> dict:
        return self._data.get("config", {})

    def get_context(self, key: str) -> Any:
        return self._data.get("context", {}).get(key)

    def set_context(self, key: str, value: Any) -> None:
        with self._lock:
            self._data.setdefault("context", {})[key] = value

    def check_run_plan(self, plan: dict) -> None:
        saved = self.get_context("run:plan")
        if saved is None:
            if self.done_count():
                raise ResumePlanError("Checkpoint lacks a verified run plan. Start a new run.")
            return
        if json.dumps(saved, sort_keys=True) != json.dumps(plan, sort_keys=True):
            raise ResumePlanError(
                "Run configuration or calculation inputs changed. Start a new run."
            )

    def freeze_run_plan(self, plan: dict) -> None:
        self.check_run_plan(plan)
        if self.get_context("run:plan") is None:
            self.set_context("run:plan", plan)
            self.save()

    def get_done(self, task_key: str) -> Set[str]:
        return set(self._data.get("work", {}).get(task_key, {}).get("done", {}))

    def is_done(self, task_key: str, code: str) -> bool:
        return code in self.get_done(task_key)

    def get_stats(self, task_key: str, code: str) -> dict:
        return dict(self._data.get("work", {}).get(task_key, {}).get("done", {}).get(code, {}))

    def mark_done(self, task_key: str, code: str,
                  stats: Optional[dict] = None,
                  result: Optional[dict] = None) -> None:
        with self._lock:
            work = self._data.setdefault("work", {}).setdefault(task_key, {})
            done = work.setdefault("done", {})
            done[code] = stats or {"done_at": _utcnow()}
            if result is not None:
                results = self._data.setdefault("results", {}).setdefault(
                    task_key, [])
                results[:] = [r for r in results if r.get("code") != code]
                results.append(result)
            # Persist every unit — a hard kill can happen at any moment.
            self.save()

    def get_results(self, task_key: str) -> List[dict]:
        return list(self._data.get("results", {}).get(task_key, []))

    def done_count(self, task_key: Optional[str] = None) -> int:
        if task_key is not None:
            return len(self.get_done(task_key))
        return sum(len(w.get("done", {})) for w in
                   self._data.get("work", {}).values())

    @property
    def updated_at(self) -> str:
        return self._data.get("updated_at", "")

    def summary(self) -> dict:
        return {
            "version": self._data.get("version"),
            "run_id": self.run_id,
            "resumed_from": self._data.get("resumed_from"),
            "created_at": self._data.get("created_at"),
            "updated_at": self._data.get("updated_at"),
            "done_count": self.done_count(),
            "tasks": {
                k: len(v.get("done", {}))
                for k, v in self._data.get("work", {}).items()
            },
        }
