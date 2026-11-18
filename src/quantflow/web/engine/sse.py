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
            q.put_nowait({
                "run_id": run_id, "event": "progress",
                "data": dict(last), "timestamp": datetime.now().isoformat(),
            })
        return q

    def unsubscribe(self, run_id: str, queue: Queue) -> None:
        with self._lock:
            if run_id in self._subs:
                self._subs[run_id] = [
                    q for q in self._subs[run_id] if q is not queue
                ]
                if not self._subs[run_id]:
                    del self._subs[run_id]

    def publish(self, run_id: str, event_type: str,
                data: dict[str, Any]) -> None:
        message = {
            "run_id": run_id, "event": event_type,
            "data": data, "timestamp": datetime.now().isoformat(),
        }
        with self._lock:
            queues = list(self._subs.get(run_id, []))
        for q in queues:
            try:
                q.put_nowait(message)
            except Exception:
                pass

    def publish_log(self, run_id: str, message: str, level: str = "info"):
        self.publish(run_id, "log", {"level": level, "message": message})

    def publish_progress(self, run_id: str, current: int, total: int):
        # Progress must never go backwards. With batch data sources the
        # adapter reports per-ticker progress during the (slow) download
        # (e.g. 1..101), then the executor re-emits stock_start/done with
        # task-local indices after the batch returns. Without this guard the
        # bar would jump back to a small value right after reaching the end.
        with self._lock:
            prev = self._last_progress.get(run_id)
            if prev is not None:
                prev_pct = prev.get("percentage", 0)
                pct = round(current / total * 100) if total > 0 else 0
                if pct < prev_pct:
                    return
                # Same percentage but a lower raw count: keep the better one.
                if pct == prev_pct and current < prev.get("current", 0):
                    return
            pct = round(current / total * 100) if total > 0 else 0
            data = {"current": current, "total": total, "percentage": pct}
            self._last_progress[run_id] = dict(data)
        self.publish(run_id, "progress", data)

    def publish_status(self, run_id: str, status: str, **extra):
        if status in ("completed", "partial", "failed", "cancelled", "interrupted"):
            with self._lock:
                self._last_progress.pop(run_id, None)
        self.publish(run_id, "status", {"status": status, **extra})

    def disconnect_all(self, run_id: str) -> None:
        with self._lock:
            self._last_progress.pop(run_id, None)
            queues = self._subs.pop(run_id, [])
        for q in queues:
            try:
                q.put_nowait(_DISCONNECTED)
            except Exception:
                pass
