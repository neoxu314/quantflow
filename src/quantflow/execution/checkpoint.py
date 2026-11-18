"""Per-run execution checkpoints for resumable runs.

A checkpoint is a small JSON document stored outside the user's output
directory (``~/.quantflow/checkpoints/{run_id}.json``).  It records which
work units (watchlist/task stocks) have already been processed and their
results, so an interrupted run can continue from where it stopped instead
of re-downloading and re-computing everything.

Design notes
------------
* Results from the data layer are **not** re-fetched on resume: only the
  final per-stock ``ExecutionResultItem`` values are cached.  This keeps the
  checkpoint small and avoids stale-ohlcv problems.
* Each write is atomic (temp file + ``os.replace``) so a hard kill (closed
  laptop lid / power loss) can never leave a half-written checkpoint.
* Checkpoints are keyed by run id.  Resuming creates a *new* run record and
  copies the checkpoint forward, preserving the original run in history.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path.home() / ".quantflow" / "checkpoints"
VERSION = 1


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
            "context": {},          # frozen date window / days_back per task
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
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                prefix=".checkpoint-", suffix=".tmp", dir=str(self.path.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass

    def delete(self) -> bool:
        with self._lock:
            if self.path.exists():
                self.path.unlink()
                return True
            return False

    @classmethod
    def copy_to(cls, src_run_id: str, dst_run_id: str) -> bool:
        """Copy a checkpoint to a new run id (used when resuming)."""
        src = checkpoint_path(src_run_id)
        if not src.exists():
            return False
        dst = checkpoint_path(dst_run_id)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            data = json.loads(dst.read_text(encoding="utf-8"))
            data["run_id"] = dst_run_id
            data["resumed_from"] = src_run_id
            tmp = dst.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            os.replace(tmp, dst)
            return True
        except (OSError, ValueError) as e:
            logger.warning("Failed to copy checkpoint %s -> %s: %s",
                           src_run_id, dst_run_id, e)
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

    def get_done(self, task_key: str) -> Set[str]:
        return set(self._data.get("work", {}).get(task_key, {}).get("done", {}))

    def is_done(self, task_key: str, code: str) -> bool:
        return code in self.get_done(task_key)

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
