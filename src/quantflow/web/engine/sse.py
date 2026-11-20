"""SSE (Server-Sent Events) broadcaster for real-time run logs."""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime
from queue import Queue
from typing import Any

_DISCONNECTED = object()


class SSEManager:
    """Thread-safe event broadcaster per run_id."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: dict[str, list[Queue]] = defaultdict(list)
        # Latest progress per run, replayed to new subscribers so the bar
        # doesn't sit at 0% when the tab is opened mid-run.
        self._last_progress: dict[str, dict[str, Any]] = {}

    def subscribe(self, run_id: str) -> Queue:
        q: Queue = Queue()
        with self._lock:
            self._subs[run_id].append(q)
            last = self._last_progress.get(run_id)
            if last is not None:
                q.put_nowait(self._event(run_id, "progress", dict(last)))
        return q

    def unsubscribe(self, run_id: str, queue: Queue) -> None:
        with self._lock:
            if run_id in self._subs:
                self._subs[run_id] = [
                    q for q in self._subs[run_id] if q is not queue
                ]
                if not self._subs[run_id]:
                    del self._subs[run_id]

    @staticmethod
    def _event(run_id, event_type, data):
        return {"run_id": run_id, "event": event_type,
                "data": data, "timestamp": datetime.now().isoformat()}

    def _broadcast_locked(self, run_id, event_type, data):
        message = self._event(run_id, event_type, data)
        for queue in self._subs.get(run_id, []):
            queue.put_nowait(message)

    def publish(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._broadcast_locked(run_id, event_type, data)

    def publish_log(self, run_id: str, message: str, level: str = "info"):
        self.publish(run_id, "log", {"level": level, "message": message})

    def progress(self, run_id: str):
        with self._lock:
            last = self._last_progress.get(run_id)
            return dict(last) if last is not None else None

    def publish_progress(self, run_id: str, current: int, total: int, *,
                         phase="analysis", task=None):
        with self._lock:
            prev = self._last_progress.get(run_id) or {}
            if (prev.get("phase"), prev.get("task")) == (phase, task):
                if current < prev["current"]:
                    return
            pct = round(current / total * 100) if total > 0 else 0
            data = {
                "current": current, "total": total, "percentage": pct,
                "phase": phase, "task": task, "sequence": prev.get("sequence", 0) + 1,
            }
            self._last_progress[run_id] = data
            self._broadcast_locked(run_id, "progress", data)

    def publish_status(self, run_id: str, status: str, **extra):
        with self._lock:
            if status in ("completed", "partial", "failed", "cancelled", "interrupted"):
                self._last_progress.pop(run_id, None)
            self._broadcast_locked(run_id, "status", {"status": status, **extra})

    def disconnect_all(self, run_id: str) -> None:
        with self._lock:
            self._last_progress.pop(run_id, None)
            queues = self._subs.pop(run_id, [])
        for q in queues:
            try:
                q.put_nowait(_DISCONNECTED)
            except Exception:
                pass
