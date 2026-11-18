"""Cooperative cancellation shared by orchestration, adapters and retry loops."""

import time
from contextlib import contextmanager
from contextvars import ContextVar


class ExecutionCancelled(BaseException):
    """A control-flow interruption; ordinary per-stock error handlers must not swallow it."""


_cancellation = ContextVar("quantflow_cancellation", default=None)


def check_cancelled():
    flag = _cancellation.get()
    if flag is not None and flag.is_set:
        raise ExecutionCancelled("Run cancelled")


@contextmanager
def cancellation_scope(flag):
    token = _cancellation.set(flag)
    try:
        check_cancelled()
        yield
    finally:
        _cancellation.reset(token)


def cancellable_sleep(seconds):
    if _cancellation.get() is None:
        time.sleep(seconds)
        return
    deadline = time.monotonic() + seconds
    while True:
        check_cancelled()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.1))
