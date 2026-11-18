"""Serial FIFO task queue — one active run at a time."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional


class QueueFullError(ValueError):
    pass


@dataclass
class QueueState:
    active_run_id: Optional[str] = None
    pending_count: int = 0
    total_queued: int = 0


class RunQueue:
    """Thread-safe FIFO queue. Only one run active at a time."""

    def __init__(self, on_run_available: Optional[Callable[[str], None]] = None,
                 max_pending: int = 100):
        self._lock = threading.Lock()
        self._pending: deque[str] = deque()
        self._active: Optional[str] = None
        self._on_available = on_run_available
        self._total_queued = 0
        self._max = max_pending

    def enqueue(self, run_id: str) -> bool:
        """Returns True if it became active immediately."""
        with self._lock:
            if self._active is None:
                self._active = run_id
                self._total_queued += 1
                if self._on_available:
                    self._on_available(run_id)
                return True
            if len(self._pending) >= self._max:
                raise QueueFullError("Run queue is full")
            self._pending.append(run_id)
            self._total_queued += 1
            return False

    def dequeue(self) -> Optional[str]:
        """Mark active done, promote next. Returns new active or None."""
        with self._lock:
            self._active = None
            if self._pending:
                nxt = self._pending.popleft()
                self._active = nxt
                if self._on_available:
                    self._on_available(nxt)
                return nxt
            return None

    def finish(self, run_id: str) -> Optional[str]:
        """Only the owner can finish the active slot, exactly once."""
        with self._lock:
            if self._active != run_id:
                return None
            self._active = self._pending.popleft() if self._pending else None
            return self._active

    def get_state(self) -> QueueState:
        with self._lock:
            return QueueState(self._active, len(self._pending), self._total_queued)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            if self._active == run_id:
                return False
            try:
                self._pending.remove(run_id)
                return True
            except ValueError:
                return False

    @property
    def active(self) -> Optional[str]:
        with self._lock:
            return self._active
