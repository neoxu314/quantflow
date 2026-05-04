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

    def subscribe(self, run_id: str) -> Queue:
        q: Queue = Queue()
        with self._lock:
            self._subs[run_id].append(q)
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
        pct = round(current / total * 100) if total > 0 else 0
        self.publish(run_id, "progress", {
            "current": current, "total": total, "percentage": pct,
        })

    def publish_status(self, run_id: str, status: str, **extra):
        self.publish(run_id, "status", {"status": status, **extra})

    def disconnect_all(self, run_id: str) -> None:
        with self._lock:
            queues = self._subs.pop(run_id, [])
        for q in queues:
            try:
                q.put_nowait(_DISCONNECTED)
            except Exception:
                pass
