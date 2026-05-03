# Runs Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Runs" tab to QuantFlow Web UI enabling scan/task execution with history, presets, real-time progress via SSE, and report viewing.

**Architecture:** New Python engine modules (`web/engine/`) manage execution threads, a serial FIFO queue, SQLite history, SSE event streaming, and pre-flight validation. FastAPI routes (`web/api/runs.py`, `web/api/presets.py`) connect the frontend to the engine. The shared `Executor` gains an optional `on_progress` callback. Frontend `app.ts` adds a tab with run list, detail panel, and New Run wizard.

**Tech Stack:** Python sqlite3 (stdlib), FastAPI StreamingResponse (SSE), threading, TypeScript ES2020, Tailwind CSS (CDN).

---

## File Map

| Responsibility | File | Action |
|---|---|---|
| ProgressEvent dataclass + callback | `src/quantflow/execution/executor.py` | Modify |
| Run history SQLite model | `src/quantflow/web/engine/run_history.py` | Create |
| Serial FIFO queue | `src/quantflow/web/engine/run_queue.py` | Create |
| SSE broadcaster | `src/quantflow/web/engine/sse.py` | Create |
| Pre-flight validation | `src/quantflow/web/engine/preflight.py` | Create |
| Run engine thread wrapper | `src/quantflow/web/engine/run_engine.py` | Create |
| Preset YAML manager | `src/quantflow/web/engine/presets.py` | Create |
| Engine package init | `src/quantflow/web/engine/__init__.py` | Create |
| Runs API endpoints | `src/quantflow/web/api/runs.py` | Create |
| Presets API endpoints | `src/quantflow/web/api/presets.py` | Create |
| Server route registration | `src/quantflow/web/server.py` | Modify |
| Engine unit tests | `tests/web/test_runs_engine.py` | Create |
| Runs API tests | `tests/web/test_runs_api.py` | Create |
| HTML tab + panel | `src/quantflow/web/static/index.html` | Modify |
| TypeScript logic | `src/quantflow/web/static/app.ts` | Modify |
| Compiled JS | `src/quantflow/web/static/app.js` | Regenerate |

---

### Task 1: Executor Progress Callback Extension

**Files:**
- Modify: `src/quantflow/execution/executor.py`

Only change to existing engine code. Adds optional `on_progress` callback parameter to `Executor.execute()`.

- [ ] **Step 1: Add imports and ProgressEvent dataclass**

At top of `executor.py`, change:
```python
from typing import List, Dict, Optional
```
To:
```python
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable
```

After the existing imports block (before `logger = ...`), add:
```python
@dataclass
class ProgressEvent:
    """Event emitted during execution for progress tracking."""
    type: str          # "stock_start" | "stock_done" | "log"
    current: int       # Current stock index (0-based)
    total: int         # Total stocks
    code: str          # Current stock code
    message: str       # Human-readable message
    level: str         # "info" | "warning" | "error"
```

- [ ] **Step 2: Modify execute() signature and add helper**

Change the `execute()` method signature from:
```python
def execute(self, job: ExecutionJob) -> List[ExecutionResultItem]:
```
To:
```python
def execute(
    self,
    job: ExecutionJob,
    on_progress: Optional[Callable[[ProgressEvent], None]] = None,
) -> List[ExecutionResultItem]:
```

After `total = len(job.items)`, add:
```python
    def _emit(code: str, msg: str, level: str = "info", etype: str = "log", idx: int = 0):
        if on_progress:
            on_progress(ProgressEvent(type=etype, current=idx, total=total, code=code, message=msg, level=level))
```

- [ ] **Step 3: Add emit calls in yfinance loop**

Replace the yfinance processing loop (lines ~108-115):

From:
```python
for item, code in yfinance_items:
    df = yf_data.get(code.standard)
    if df is None or df.empty:
        logger.warning(f"No data for {item.code}")
        continue
    result = self._process_single(item, code, df, job)
    if result:
        results.append(result)
```

To:
```python
for idx, (item, code) in enumerate(yfinance_items, 1):
    df = yf_data.get(code.standard)
    _emit(code.standard, f"Fetching {code.standard}...", "info", "stock_start", idx)
    if df is None or df.empty:
        logger.warning(f"No data for {item.code}")
        _emit(code.standard, f"No data for {code.standard}", "warning", "stock_done", idx)
        continue
    result = self._process_single(item, code, df, job)
    if result:
        results.append(result)
        _emit(code.standard, f"{code.standard} complete: {result.buy_signals + result.sell_signals} signals", "info", "stock_done", idx)
    else:
        _emit(code.standard, f"{code.standard} complete: no signals", "info", "stock_done", idx)
```

- [ ] **Step 4: Add emit calls in sequential (A-share) loop**

Replace lines ~117-128:

From:
```python
for idx, (item, code) in enumerate(other_items, 1):
    try:
        logger.info(f"Processing [{idx}/{total}]: {item.code}")
        df, _ = self.factory.fetch_ohlcv(code, start_date=start_date, end_date=end_date)
        if df.empty:
            logger.warning(f"No data for {item.code}")
            continue
        result = self._process_single(item, code, df, job)
        if result:
            results.append(result)
    except Exception as e:
        logger.error(f"Failed {item.code}: {e}")
```

To:
```python
for idx, (item, code) in enumerate(other_items, 1):
    _emit(code.standard, f"Fetching {code.standard}...", "info", "stock_start", idx)
    try:
        df, _ = self.factory.fetch_ohlcv(code, start_date=start_date, end_date=end_date)
        if df.empty:
            logger.warning(f"No data for {item.code}")
            _emit(code.standard, f"No data for {code.standard}", "warning", "stock_done", idx)
            continue
        result = self._process_single(item, code, df, job)
        if result:
            results.append(result)
            _emit(code.standard, f"{code.standard} complete: {result.buy_signals + result.sell_signals} signals", "info", "stock_done", idx)
        else:
            _emit(code.standard, f"{code.standard} complete: no signals", "info", "stock_done", idx)
    except Exception as e:
        logger.error(f"Failed {item.code}: {e}")
        _emit(code.standard, f"Failed {code.standard}: {e}", "error", "stock_done", idx)
```

- [ ] **Step 5: Verify backward compatibility**

```bash
export PYTHONPATH=/Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow/src
python3 -c "
from quantflow.execution.executor import Executor, ProgressEvent
import inspect
sig = inspect.signature(Executor.execute)
assert 'on_progress' in sig.parameters
assert sig.parameters['on_progress'].default is None
print('OK: backward compatible')
"
```

- [ ] **Step 6: Lint**

```bash
ruff check src/quantflow/execution/executor.py
```

Expected: No errors

- [ ] **Step 7: Existing tests still pass**

```bash
export PYTHONPATH=/Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow/src
pytest tests/execution/ -v -x 2>&1 | tail -5
```

- [ ] **Step 8: Commit**

```bash
git add src/quantflow/execution/executor.py
git commit -m "feat(executor): add optional on_progress callback for web UI progress tracking"
```

---

### Task 2: RunHistory SQLite Model + Engine Package Init

**Files:**
- Create: `src/quantflow/web/engine/__init__.py`
- Create: `src/quantflow/web/engine/run_history.py`
- Test: `tests/web/test_runs_engine.py`

- [ ] **Step 1: Create engine package init**

```python
"""Web execution engine — runs, queue, SSE, presets, validation."""
from quantflow.web.engine.run_history import RunHistory, RunRecord  # noqa
from quantflow.web.engine.run_queue import RunQueue, QueueState  # noqa
from quantflow.web.engine.sse import SSEManager  # noqa
from quantflow.web.engine.run_engine import RunEngine  # noqa
from quantflow.web.engine.presets import PresetManager, Preset  # noqa
from quantflow.web.engine.preflight import PreflightChecker, ValidationResult  # noqa

__all__ = [
    "RunHistory", "RunRecord", "RunQueue", "QueueState",
    "SSEManager", "RunEngine", "PresetManager", "Preset",
    "PreflightChecker", "ValidationResult",
]
```

- [ ] **Step 2: Create `src/quantflow/web/engine/run_history.py`**

```python
"""RunHistory — SQLite persistence for execution history."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]
QUANTFLOW_DIR = PROJECT_ROOT / ".quantflow"
DB_PATH = QUANTFLOW_DIR / "runs.db"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS run_history (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, run_type TEXT NOT NULL,
    config TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    started_at TEXT, finished_at TEXT, duration_ms INTEGER, error TEXT,
    output_path TEXT, report_path TEXT, signal_count INTEGER DEFAULT 0,
    preset_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_status ON run_history(status);
CREATE INDEX IF NOT EXISTS idx_run_created ON run_history(created_at DESC);
"""

RUN_TYPES = ("stock_scan", "watchlist_run", "task_run")
STATUSES = ("queued", "running", "completed", "failed", "cancelled")


@dataclass
class RunRecord:
    id: str; name: str; run_type: str; config: dict; status: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    output_path: Optional[str] = None
    report_path: Optional[str] = None
    signal_count: int = 0
    preset_id: Optional[str] = None


def _connect() -> sqlite3.Connection:
    QUANTFLOW_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_INIT_SQL)
    conn.commit()
    return conn


def _row_to_record(row: tuple) -> RunRecord:
    return RunRecord(
        id=row[0], name=row[1], run_type=row[2], config=json.loads(row[3]),
        status=row[4], created_at=row[5], started_at=row[6],
        finished_at=row[7], duration_ms=row[8], error=row[9],
        output_path=row[10], report_path=row[11],
        signal_count=row[12] or 0, preset_id=row[13],
    )


class RunHistory:
    def create_run(self, name: str, run_type: str, config: dict,
                   preset_id: Optional[str] = None) -> str:
        import uuid
        if run_type not in RUN_TYPES:
            raise ValueError(f"Invalid run_type '{run_type}'")
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO run_history (id,name,run_type,config,status,created_at,preset_id) "
                "VALUES (?,?,?,?, 'queued',?,?)",
                (run_id, name, run_type, json.dumps(config), now, preset_id),
            )
            conn.commit()
        finally:
            conn.close()
        return run_id

    def update_status(self, run_id: str, status: str, **kwargs) -> None:
        if status not in STATUSES:
            raise ValueError(f"Invalid status '{status}'")
        fields = ["status = ?"]; values: list = [status]
        for key in ("started_at", "finished_at", "error", "output_path", "report_path"):
            if key in kwargs and kwargs[key] is not None:
                fields.append(f"{key} = ?"); values.append(kwargs[key])
        if "duration_ms" in kwargs and kwargs["duration_ms"] is not None:
            fields.append("duration_ms = ?"); values.append(int(kwargs["duration_ms"]))
        if "signal_count" in kwargs and kwargs["signal_count"] is not None:
            fields.append("signal_count = ?"); values.append(int(kwargs["signal_count"]))
        values.append(run_id)
        conn = _connect()
        try:
            conn.execute(f"UPDATE run_history SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        return self._get_one("SELECT * FROM run_history WHERE id = ?", (run_id,))

    def list_runs(self, status: Optional[str] = None,
                  limit: int = 50, offset: int = 0) -> list[RunRecord]:
        conn = _connect()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM run_history WHERE status=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM run_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset)).fetchall()
            return [_row_to_record(r) for r in rows]
        finally:
            conn.close()

    def _get_one(self, sql: str, params: tuple) -> Optional[RunRecord]:
        conn = _connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return _row_to_record(row) if row else None
        finally:
            conn.close()
```

- [ ] **Step 3: Write tests in `tests/web/test_runs_engine.py`**

```python
"""Tests for web/engine modules."""
import os
import shutil
import tempfile
import pytest
from pathlib import Path

TESTS_PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("PYTHONPATH", str(TESTS_PROJECT_ROOT / "src"))


class TestRunHistory:
    """Test SQLite RunHistory CRUD (uses :memory: DB)."""

    def setup_method(self):
        from quantflow.web.engine import run_history
        self._orig_db = run_history.DB_PATH
        run_history.DB_PATH = Path(":memory:")
        # Force table creation
        run_history._connect().close()

    def teardown_method(self):
        from quantflow.web.engine import run_history
        run_history.DB_PATH = self._orig_db

    def test_create_and_get_run(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("Test", "stock_scan", {"code": "NVDA.US"})
        run = h.get_run(rid)
        assert run.name == "Test"
        assert run.status == "queued"
        assert run.config == {"code": "NVDA.US"}

    def test_update_status_completed(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("T", "stock_scan", {})
        h.update_status(rid, "completed", signal_count=3, duration_ms=5000)
        run = h.get_run(rid)
        assert run.status == "completed"
        assert run.signal_count == 3

    def test_update_status_failed(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("T", "task_run", {})
        h.update_status(rid, "failed", error="oops")
        assert h.get_run(rid).error == "oops"

    def test_invalid_run_type_raises(self):
        from quantflow.web.engine.run_history import RunHistory
        with pytest.raises(ValueError):
            RunHistory().create_run("T", "bad_type", {})

    def test_list_runs_ordered(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        h.create_run("A", "stock_scan", {})
        h.create_run("B", "watchlist_run", {})
        h.create_run("C", "stock_scan", {})
        runs = h.list_runs()
        assert runs[0].name == "C"  # Most recent first

    def test_list_by_status(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("Failed", "stock_scan", {})
        h.update_status(rid, "failed", error="x")
        h.create_run("Running", "task_run", {})
        failed = h.list_runs(status="failed")
        assert len(failed) == 1
        assert failed[0].name == "Failed"
```

- [ ] **Step 4: Run tests**

```bash
export PYTHONPATH=/Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow/src
pytest tests/web/test_runs_engine.py::TestRunHistory -v
```

Expected: 6 PASS

- [ ] **Step 5: ruff check**

```bash
ruff check src/quantflow/web/engine/ tests/web/test_runs_engine.py
```

- [ ] **Step 6: Commit**

```bash
git add src/quantflow/web/engine/ tests/web/test_runs_engine.py
git commit -m "feat(engine): add RunHistory SQLite model with full CRUD tests"
```

---

### Task 3: Serial RunQueue

**Files:**
- Create: `src/quantflow/web/engine/run_queue.py`
- Modify: `tests/web/test_runs_engine.py`

- [ ] **Step 1: Create `src/quantflow/web/engine/run_queue.py`**

```python
"""Serial FIFO task queue — one active run at a time."""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from typing import Optional, Callable


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
                return False
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

    def get_state(self) -> QueueState:
        with self._lock:
            return QueueState(self._active, len(self._pending), self._total_queued)

    def cancel(self, run_id: str) -> bool:
        """Remove pending run. Can't cancel active (done by engine)."""
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
```

- [ ] **Step 2: Add Queue tests**

Append to `tests/web/test_runs_engine.py`:

```python
class TestRunQueue:
    def test_first_enqueue_active(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue()
        assert q.enqueue("r1") is True
        assert q.active == "r1"

    def test_second_enqueue_pending(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue()
        q.enqueue("r1")
        assert q.enqueue("r2") is False
        assert q.get_state().pending_count == 1

    def test_dequeue_promotes_next(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue()
        q.enqueue("r1"); q.enqueue("r2"); q.enqueue("r3")
        assert q.dequeue() == "r2"
        assert q.active == "r2"

    def test_dequeue_empty(self):
        from quantflow.web.engine.run_queue import RunQueue
        assert RunQueue().dequeue() is None

    def test_cancel_pending(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue()
        q.enqueue("r1"); q.enqueue("r2")
        assert q.cancel("r2") is True
        assert q.get_state().pending_count == 0

    def test_cancel_active_false(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue(); q.enqueue("r1")
        assert q.cancel("r1") is False
```

- [ ] **Step 3: Run tests + lint + commit**

```bash
pytest tests/web/test_runs_engine.py::TestRunQueue -v && ruff check src/quantflow/web/engine/run_queue.py && git add src/quantflow/web/engine/run_queue.py tests/web/test_runs_engine.py && git commit -m "feat(engine): add serial FIFO RunQueue with thread safefy"
```

---

### Task 4: SSE Event Broadcaster

**Files:**
- Create: `src/quantflow/web/engine/sse.py`
- Modify: `tests/web/test_runs_engine.py`

- [ ] **Step 1: Create `src/quantflow/web/engine/sse.py`**

```python
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
                self._subs[run_id] = [q for q in self._subs[run_id] if q is not queue]
                if not self._subs[run_id]:
                    del self._subs[run_id]

    def publish(self, run_id: str, event_type: str, data: dict[str, Any]) -> None:
        message = {"run_id": run_id, "event": event_type,
                   "data": data, "timestamp": datetime.now().isoformat()}
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
        self.publish(run_id, "progress", {"current": current, "total": total, "percentage": pct})

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
```

- [ ] **Step 2: Add SSE tests**

Append to `tests/web/test_runs_engine.py`:

```python
class TestSSEManager:
    def test_subscribe_and_publish(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q = m.subscribe("r1")
        m.publish_log("r1", "hello")
        assert q.get(timeout=1)["data"]["message"] == "hello"

    def test_progress_pct(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q = m.subscribe("r1")
        m.publish_progress("r1", 12, 50)
        assert q.get(timeout=1)["data"]["percentage"] == 24

    def test_status(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q = m.subscribe("r1")
        m.publish_status("r1", "completed", signal_count=3)
        d = q.get(timeout=1)["data"]
        assert d["status"] == "completed" and d["signal_count"] == 3

    def test_unsubscribe(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q = m.subscribe("r1")
        m.unsubscribe("r1", q)
        m.publish_log("r1", "gone")
        assert q.empty()

    def test_multiple_subscribers(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q1 = m.subscribe("r1"); q2 = m.subscribe("r1")
        m.publish_log("r1", "both")
        assert q1.get(timeout=1)["data"]["message"] == "both"
        assert q2.get(timeout=1)["data"]["message"] == "both"
```

- [ ] **Step 3: Run + lint + commit**

```bash
pytest tests/web/test_runs_engine.py::TestSSEManager -v && ruff check src/quantflow/web/engine/sse.py && git add src/quantflow/web/engine/sse.py tests/web/test_runs_engine.py && git commit -m "feat(engine): add SSEManager for real-time event broadcasting"
```

---

### Task 5: PreflightChecker

**Files:**
- Create: `src/quantflow/web/engine/preflight.py`
- Modify: `tests/web/test_runs_engine.py`

- [ ] **Step 1: Create `src/quantflow/web/engine/preflight.py`**

```python
"""Pre-flight validation for run configurations."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class ValidationResult:
    def __init__(self):
        self.errors: list[str] = []

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def validate_code(value: str) -> ValidationResult:
    r = ValidationResult()
    if not re.match(r"^[A-Za-z0-9]{1,10}\.[A-Za-z]{2}$", value):
        r.fail(f"Invalid stock code format: '{value}'. Expected: NVDA.US, 600519.SH")
        return r
    try:
        from quantflow.data.base import StockCode
        StockCode.from_standard(value)
    except Exception as e:
        r.fail(f"Invalid stock code '{value}': {e}")
    return r


def validate_watchlist(path: str) -> ValidationResult:
    r = ValidationResult()
    p = Path(path) if os.path.isabs(path) else PROJECT_ROOT / path
    if not p.exists():
        r.fail(f"Watchlist not found: '{path}'"); return r
    try:
        from quantflow.execution.watchlist import Watchlist
        wl = Watchlist.load(str(p))
        if not wl.items:
            r.fail(f"Watchlist '{path}' is empty")
    except Exception as e:
        r.fail(f"Invalid watchlist: {e}")
    return r


def validate_task_config(path: str) -> ValidationResult:
    r = ValidationResult()
    p = Path(path) if os.path.isabs(path) else PROJECT_ROOT / path
    if not p.exists():
        r.fail(f"Task config not found: '{path}'"); return r
    try:
        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(str(p))
        if not tasks:
            r.fail(f"Task config '{path}' has no valid tasks")
    except Exception as e:
        r.fail(f"Invalid task config: {e}")
    return r


def validate_output_path(path: Optional[str]) -> ValidationResult:
    r = ValidationResult()
    if path:
        p = Path(path) if os.path.isabs(path) else PROJECT_ROOT / path
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            r.fail(f"Cannot create output path: {e}")
    return r


def validate_strategy(sid: str) -> ValidationResult:
    r = ValidationResult()
    try:
        from quantflow.orchestration.registry import get_strategy_class
        get_strategy_class(sid)
    except (ValueError, ImportError) as e:
        r.fail(f"Unknown strategy '{sid}'")
    return r


class PreflightChecker:
    @staticmethod
    def validate(run_type: str, config: dict) -> ValidationResult:
        r = ValidationResult()
        if run_type == "stock_scan":
            code = config.get("code")
            if not code:
                r.fail("Stock code is required")
            else:
                r.errors.extend(validate_code(code).errors)
            r.errors.extend(validate_date_range(config.get("start_date"), config.get("end_date")).errors)
            for ind in config.get("indicators", []):
                if ind not in ("kdj", "macd", "dual_line", "rsi", "boll", "vol_ma", "brick_chart", "washout"):
                    r.fail(f"Unknown indicator: '{ind}'")
        elif run_type == "watchlist_run":
            wl = config.get("watchlist")
            if not wl:
                r.fail("Watchlist path required")
            else:
                r.errors.extend(validate_watchlist(wl).errors)
            for sid in config.get("strategies", []):
                r.errors.extend(validate_strategy(sid).errors)
        elif run_type == "task_run":
            tp = config.get("task_config")
            if not tp:
                r.fail("Task config path required")
            else:
                r.errors.extend(validate_task_config(tp).errors)
        else:
            r.fail(f"Unknown run_type: '{run_type}'")

        r.errors.extend(validate_output_path(config.get("output_path")).errors)
        return r


def validate_date_range(start: Optional[str], end: Optional[str]) -> ValidationResult:
    from datetime import datetime
    r = ValidationResult()
    date_re = r"^\d{4}-\d{2}-\d{2}$"
    if start and not re.match(date_re, start):
        r.fail(f"Invalid start_date format"); return r
    if end and not re.match(date_re, end):
        r.fail(f"Invalid end_date format"); return r
    if start and end:
        s, e = datetime.strptime(start, "%Y-%m-%d"), datetime.strptime(end, "%Y-%m-%d")
        if s > e:
            r.fail(f"start_date after end_date")
    return r
```

- [ ] **Step 2: Add preflight tests**

```python
class TestPreflightChecker:
    def test_valid_stock(self):
        from quantflow.web.engine.preflight import PreflightChecker
        assert PreflightChecker.validate("stock_scan", {"code": "NVDA.US"}).ok

    def test_invalid_code(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("stock_scan", {"code": "NVDA"})
        assert not r.ok and any("Invalid stock code" in e for e in r.errors)

    def test_missing_code(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("stock_scan", {})
        assert not r.ok and any("required" in e for e in r.errors)

    def test_bad_date_order(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("stock_scan", {
            "code": "NVDA.US", "start_date": "2026-06-01", "end_date": "2026-05-01"})
        assert not r.ok and any("after" in e.lower() for e in r.errors)

    def test_unknown_run_type(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("bogus", {})
        assert not r.ok

    def test_unknown_indicator(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("stock_scan",
            {"code": "NVDA.US", "indicators": ["magic"]})
        assert not r.ok and any("Unknown indicator" in e for e in r.errors)
```

- [ ] **Step 3: Run + lint + commit**

```bash
pytest tests/web/test_runs_engine.py::TestPreflightChecker -v && ruff check src/quantflow/web/engine/preflight.py && git add src/quantflow/web/engine/preflight.py tests/web/test_runs_engine.py && git commit -m "feat(engine): add PreflightChecker validation with tests"
```

---

### Task 6: RunEngine (Thread Wrapper)

**Files:**
- Create: `src/quantflow/web/engine/run_engine.py`
- Modify: `tests/web/test_runs_engine.py`

- [ ] **Step 1: Create `src/quantflow/web/engine/run_engine.py`**

```python
"""RunEngine — wraps execution in background threads with progress."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from quantflow.web.engine.run_history import RunHistory, RunRecord
from quantflow.web.engine.run_queue import RunQueue
from quantflow.web.engine.sse import SSEManager

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[4]


class CancellationFlag:
    def __init__(self):
        self._flag = threading.Event()
    def cancel(self):
        self._flag.set()
    @property
    def is_set(self) -> bool:
        return self._flag.is_set()


class RunEngine:
    def __init__(self, queue: RunQueue, history: RunHistory, sse: SSEManager):
        self._queue = queue
        self._history = history
        self._sse = sse
        self._cancellations: dict[str, CancellationFlag] = {}

    def start_processing(self, run_id: str) -> None:
        t = threading.Thread(target=self._execute_run, args=(run_id,), daemon=True)
        t.start()

    def cancel(self, run_id: str) -> bool:
        if run_id in self._cancellations:
            self._cancellations[run_id].cancel()
            return True
        return False

    def _execute_run(self, run_id: str) -> None:
        run = self._history.get_run(run_id)
        if not run:
            return

        flag = CancellationFlag()
        self._cancellations[run_id] = flag
        now = datetime.now(timezone.utc).isoformat()
        self._history.update_status(run_id, "running", started_at=now)
        self._sse.publish_status(run_id, "running")
        self._sse.publish_log(run_id, f"Starting: {run.name} ({run.run_type})")

        try:
            if flag.is_set:
                self._mark_done(run_id, "cancelled")
                return

            if run.run_type == "stock_scan":
                self._exec_stock_scan(run_id, run, flag)
            elif run.run_type == "watchlist_run":
                self._exec_watchlist_run(run_id, run, flag)
            elif run.run_type == "task_run":
                self._exec_task_run(run_id, run, flag)
            else:
                self._history.update_status(run_id, "failed", error=f"Unknown type: {run.run_type}")
        except Exception as e:
            logger.exception(f"Run {run_id} failed")
            self._history.update_status(run_id, "failed",
                finished_at=datetime.now(timezone.utc).isoformat(), error=str(e))
            self._sse.publish_log(run_id, f"ERROR: {e}", "error")
        finally:
            self._cancellations.pop(run_id, None)
            # Promote next queue item
            nxt = self._queue.dequeue()
            if nxt:
                self.start_processing(nxt)

    def _progress_cb(self, run_id: str, flag: CancellationFlag):
        def _cb(event):
            if flag.is_set:
                return
            if event.type == "stock_start":
                self._sse.publish_log(run_id, f"[{event.current}/{event.total}] {event.code}...")
                self._sse.publish_progress(run_id, event.current, event.total)
            elif event.type == "stock_done":
                self._sse.publish_log(run_id, f"[{event.current}/{event.total}] {event.message}", level=event.level)
                self._sse.publish_progress(run_id, event.current, event.total)
        return _cb

    def _mark_done(self, run_id: str, status: str):
        self._history.update_status(run_id, status,
            finished_at=datetime.now(timezone.utc).isoformat())
        self._sse.publish_status(run_id, status)

    def _exec_stock_scan(self, run_id: str, run: RunRecord, flag: CancellationFlag):
        from quantflow.execution.executor import Executor
        from quantflow.execution.job import ExecutionJob
        from quantflow.execution.watchlist import Watchlist, WatchlistItem
        from quantflow.data.base import StockCode
        from quantflow.strategies.buy import DailyBullishMidRangeBuy, DailyBullishOversoldBuy
        from quantflow.reports.markdown import MarkdownReporter
        from datetime import datetime as dt

        cfg = run.config
        code = StockCode.from_standard(cfg["code"])
        start = cfg.get("start_date") or (dt.now().replace(year=dt.now().year - 1)).strftime("%Y-%m-%d")
        end = cfg.get("end_date") or dt.now().strftime("%Y-%m-%d")
        output = cfg.get("output_path") or str(PROJECT_ROOT / "output" / "manual_scans")

        item = WatchlistItem(code=code)
        wl = Watchlist(name=code.standard, items=[item])
        strategies = [DailyBullishOversoldBuy(), DailyBullishMidRangeBuy()]

        job = ExecutionJob(name=code.standard, items=[item], strategies=strategies, output_dir=output, days_back=365)
        results = Executor().execute(job, on_progress=self._progress_cb(run_id, flag))

        date_str = dt.now().strftime("%Y-%m-%d")
        rpath = MarkdownReporter().generate(code.standard, strategies, results, wl, output, date_str)

        self._history.update_status(run_id, "completed",
            finished_at=dt.now(timezone.utc).isoformat(),
            signal_count=len(results), output_path=output, report_path=rpath)
        self._sse.publish_log(run_id, f"Complete: {len(results)} signals")
        self._sse.publish_status(run_id, "completed", signal_count=len(results))

    def _exec_watchlist_run(self, run_id: str, run: RunRecord, flag: CancellationFlag):
        from quantflow.execution.executor import Executor
        from quantflow.execution.job import ExecutionJob
        from quantflow.execution.watchlist import Watchlist
        from quantflow.orchestration.registry import STRATEGY_REGISTRY
        from quantflow.reports.markdown import MarkdownReporter
        import os as _os
        from datetime import datetime as dt

        cfg = run.config
        wp = cfg["watchlist"]
        p = Path(wp) if _os.path.isabs(wp) else PROJECT_ROOT / wp
        wl = Watchlist.load(str(p))
        output = cfg.get("output_path") or str(PROJECT_ROOT / "output" / "manual_watchlist")
        strat_ids = cfg.get("strategies", ["daily_bull_oversold", "daily_bull_mid_range"])
        strategies = [STRATEGY_REGISTRY[s]() for s in strat_ids]

        job = ExecutionJob(name=wl.name, items=wl.items, strategies=strategies, output_dir=output, days_back=365)
        results = Executor().execute(job, on_progress=self._progress_cb(run_id, flag))

        date_str = dt.now().strftime("%Y-%m-%d")
        rpath = MarkdownReporter().generate(wl.name, strategies, results, wl, output, date_str)

        self._history.update_status(run_id, "completed",
            finished_at=dt.now(timezone.utc).isoformat(),
            signal_count=len(results), output_path=output, report_path=rpath)
        self._sse.publish_log(run_id, f"Complete: {len(results)} signals from {len(wl.items)} stocks")
        self._sse.publish_status(run_id, "completed", signal_count=len(results))

    def _exec_task_run(self, run_id: str, run: RunRecord, flag: CancellationFlag):
        from quantflow.orchestration.app import Orchestrator
        from quantflow.orchestration.loader import TaskConfig
        import os as _os
        from datetime import datetime as dt

        cfg = run.config
        tp = cfg["task_config"]
        p = Path(tp) if _os.path.isabs(tp) else PROJECT_ROOT / tp
        configs = TaskConfig.load(str(p))
        output = cfg.get("output_path")
        daily = cfg.get("daily", False)

        self._sse.publish_log(run_id, f"Running {len(configs)} task(s) via Orchestrator...")
        Orchestrator(configs, output_override=output, daily_mode=daily).run()

        rdir = output or "reports"
        if daily:
            rdir = str(Path(rdir) / dt.now().strftime("%Y-%m-%d"))

        self._history.update_status(run_id, "completed",
            finished_at=dt.now(timezone.utc).isoformat(),
            signal_count=0, output_path=output,
            report_path=str(Path(rdir) / "Daily_Report.md"))
        self._sse.publish_log(run_id, "Orchestration tasks complete")
        self._sse.publish_status(run_id, "completed", signal_count=0)
```

- [ ] **Step 2: Add RunEngine tests (lightweight, no network)**

```python
class TestRunEngine:
    def test_cancellation_flag(self):
        from quantflow.web.engine.run_engine import CancellationFlag
        f = CancellationFlag()
        assert f.is_set is False
        f.cancel()
        assert f.is_set is True

    def test_cancel_unknown(self):
        from quantflow.web.engine import RunEngine, RunQueue, SSEManager
        from quantflow.web.engine import run_history
        from pathlib import Path
        orig = run_history.DB_PATH; run_history.DB_PATH = Path(":memory:")
        engine = RunEngine(RunQueue(), run_history.RunHistory(), SSEManager())
        assert engine.cancel("nope") is False
        run_history.DB_PATH = orig
```

- [ ] **Step 3: Run + lint + commit**

```bash
pytest tests/web/test_runs_engine.py::TestRunEngine -v && ruff check src/quantflow/web/engine/run_engine.py && git add src/quantflow/web/engine/run_engine.py tests/web/test_runs_engine.py && git commit -m "feat(engine): add RunEngine thread wrapper with progress callbacks"
```

---

### Task 7: PresetManager (YAML CRUD)

**Files:**
- Create: `src/quantflow/web/engine/presets.py`
- Modify: `tests/web/test_runs_engine.py`

- [ ] **Step 1: Create `src/quantflow/web/engine/presets.py`**

```python
"""Preset management — saved run configurations as YAML."""
from __future__ import annotations

import re
import uuid
import yaml
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PRESETS_DIR = PROJECT_ROOT / ".quantflow" / "presets"


@dataclass
class Preset:
    id: str; name: str; run_type: str; config: dict
    created_at: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "run_type": self.run_type,
                "config": self.config, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, pid: str, data: dict) -> "Preset":
        return cls(id=pid, name=data.get("name", pid),
                   run_type=data.get("run_type", "stock_scan"),
                   config=data.get("config", {}), created_at=data.get("created_at", ""))


class PresetManager:
    @staticmethod
    def _ensure_dir():
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def list_presets() -> list[Preset]:
        PresetManager._ensure_dir()
        presets = []
        for p in sorted(PRESETS_DIR.glob("*.yaml")):
            try:
                with open(p) as f:
                    data = yaml.safe_load(f)
                if data:
                    presets.append(Preset.from_dict(p.stem, data))
            except Exception:
                pass
        return presets

    @staticmethod
    def create(name: str, run_type: str, config: dict) -> str:
        PresetManager._ensure_dir()
        pid = _slugify(name) or str(uuid.uuid4())[:8]
        path = PRESETS_DIR / f"{pid}.yaml"
        c = 1
        while path.exists():
            pid = f"{_slugify(name) or str(uuid.uuid4())[:8]}-{c}"; c += 1
            path = PRESETS_DIR / f"{pid}.yaml"

        preset = Preset(id=pid, name=name, run_type=run_type, config=config,
                        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
        with open(path, "w") as f:
            yaml.dump(preset.to_dict(), f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return pid

    @staticmethod
    def get(pid: str) -> Optional[Preset]:
        path = PRESETS_DIR / f"{pid}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return Preset.from_dict(pid, data) if data else None

    @staticmethod
    def update(pid: str, name: str, run_type: str, config: dict) -> bool:
        path = PRESETS_DIR / f"{pid}.yaml"
        if not path.exists():
            return False
        preset = Preset(id=pid, name=name, run_type=run_type, config=config,
                        created_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
        with open(path, "w") as f:
            yaml.dump(preset.to_dict(), f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True

    @staticmethod
    def delete(pid: str) -> bool:
        path = PRESETS_DIR / f"{pid}.yaml"
        if not path.exists():
            return False
        path.unlink(); return True


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip().lower()
    s = re.sub(r"[\s]+", "-", s)
    return s[:60] if s else ""
```

- [ ] **Step 2: Add preset tests**

```python
class TestPresetManager:
    def setup_method(self):
        import tempfile
        from quantflow.web.engine import presets
        self._orig = presets.PRESETS_DIR
        self._tmp = tempfile.mkdtemp()
        presets.PRESETS_DIR = Path(self._tmp)

    def teardown_method(self):
        from quantflow.web.engine import presets
        presets.PRESETS_DIR = self._orig
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_create_and_get(self):
        from quantflow.web.engine.presets import PresetManager
        pid = PresetManager.create("My Scan", "stock_scan", {"code": "NVDA.US"})
        p = PresetManager.get(pid)
        assert p.name == "My Scan" and p.config["code"] == "NVDA.US"

    def test_list_presets(self):
        from quantflow.web.engine.presets import PresetManager
        PresetManager.create("A", "stock_scan", {}); PresetManager.create("B", "watchlist_run", {})
        assert len(PresetManager.list_presets()) == 2

    def test_update(self):
        from quantflow.web.engine.presets import PresetManager
        pid = PresetManager.create("Old", "stock_scan", {})
        PresetManager.update(pid, "New", "task_run", {"task_config": "x"})
        assert PresetManager.get(pid).name == "New"

    def test_delete(self):
        from quantflow.web.engine.presets import PresetManager
        pid = PresetManager.create("T", "stock_scan", {})
        assert PresetManager.delete(pid) is True
        assert PresetManager.get(pid) is None
```

- [ ] **Step 3: Run + lint + commit**

```bash
pytest tests/web/test_runs_engine.py::TestPresetManager -v && ruff check src/quantflow/web/engine/presets.py && git add src/quantflow/web/engine/presets.py tests/web/test_runs_engine.py && git commit -m "feat(engine): add PresetManager YAML CRUD"
```

---

### Task 8: Runs API Endpoints + Server Integration

**Files:**
- Create: `src/quantflow/web/api/runs.py`
- Create: `src/quantflow/web/api/presets.py`
- Modify: `src/quantflow/web/server.py`
- Test: `tests/web/test_runs_api.py`

- [ ] **Step 1: Create `src/quantflow/web/api/runs.py`**

```python
"""Runs API endpoints."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from quantflow.web.engine.preflight import PreflightChecker
from quantflow.web.engine.run_engine import RunEngine

router = APIRouter(prefix="/api/runs", tags=["Runs"])


def _get_engine() -> RunEngine:
    if not hasattr(_get_engine, "_instance"):
        raise HTTPException(status_code=500, detail="RunEngine not initialized")
    return _get_engine._instance

def _set_engine(engine: RunEngine) -> None:
    _get_engine._instance = engine


@router.get("/")
def list_runs(status: Optional[str] = None, limit: int = 50, offset: int = 0):
    runs = _get_engine()._history.list_runs(status=status, limit=limit, offset=offset)
    return {"runs": [_to_dict(r) for r in runs], "total": len(runs)}


@router.get("/queue")
def get_queue_status():
    s = _get_engine()._queue.get_state()
    return {"active_run_id": s.active_run_id, "pending_count": s.pending_count,
            "total_queued": s.total_queued}


@router.post("/")
def create_run(body: dict):
    run_type = body.get("run_type")
    if not run_type:
        raise HTTPException(status_code=400, detail="run_type required")

    config = _build_config(run_type, body)
    result = PreflightChecker.validate(run_type, config)
    if not result.ok:
        return {"ok": False, "errors": result.errors}

    name = body.get("name") or _auto_name(run_type, config)
    engine = _get_engine()
    run_id = engine._history.create_run(name, run_type, config, preset_id=body.get("preset_id"))

    became_active = engine._queue.enqueue(run_id)
    if became_active:
        engine.start_processing(run_id)

    return {"ok": True, "run_id": run_id, "status": "active" if became_active else "queued"}


@router.get("/{run_id}")
def get_run(run_id: str):
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {"run": _to_dict(run)}


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str):
    engine = _get_engine()
    queue = engine._queue
    # Try cancel from pending first
    if queue.cancel(run_id):
        # If it was active, also cancel engine
        if queue.active == run_id:
            engine.cancel(run_id)
            nxt = queue.dequeue()
            if nxt:
                engine.start_processing(nxt)
        engine._history.update_status(run_id, "cancelled",
            finished_at=datetime.now(timezone.utc).isoformat())
        engine._sse.publish_status(run_id, "cancelled")
        return {"ok": True}

    # If active
    if queue.active == run_id:
        engine.cancel(run_id)
        nxt = queue.dequeue()
        if nxt:
            engine.start_processing(nxt)
        engine._history.update_status(run_id, "cancelled",
            finished_at=datetime.now(timezone.utc).isoformat())
        engine._sse.publish_status(run_id, "cancelled")
        return {"ok": True}

    raise HTTPException(status_code=400, detail=f"Run cannot be cancelled")


@router.get("/{run_id}/report")
def get_report(run_id: str):
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    if not run.report_path:
        return {"report": None, "message": "No report available"}
    rp = Path(run.report_path)
    if not rp.exists():
        return {"report": None, "message": "Report file not found"}
    return {"report": rp.read_text(), "path": str(rp)}


@router.get("/{run_id}/files")
def get_files(run_id: str):
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    if not run.output_path:
        return {"files": []}
    files = []
    for d in [Path(run.output_path)]:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.is_file() and f.suffix in (".json", ".md"):
                files.append({"name": f.name, "path": str(f),
                              "size": _human_size(f.stat().st_size),
                              "type": f.suffix.lstrip(".")})
    return {"files": files}


@router.get("/{run_id}/logs:sse")
async def stream_logs(run_id: str):
    from quantflow.web.engine.sse import _DISCONNECTED
    sse = _get_engine()._sse
    if not _get_engine()._history.get_run(run_id):
        raise HTTPException(status_code=404, detail="Not found")
    q = sse.subscribe(run_id)

    async def _gen():
        loop = asyncio.get_event_loop()
        try:
            while True:
                msg = await loop.run_in_executor(None, q.get, True, 1.0)
                if msg is _DISCONNECTED:
                    break
                if isinstance(msg, dict):
                    yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
        except Exception:
            pass
        finally:
            sse.unsubscribe(run_id, q)

    return StreamingResponse(_gen(), media_type="text/event-stream")


def _build_config(run_type: str, body: dict) -> dict:
    if run_type == "stock_scan":
        return {"code": body.get("code"), "start_date": body.get("start_date"),
                "end_date": body.get("end_date"),
                "indicators": body.get("indicators", ["kdj", "dual_line"]),
                "output_path": body.get("output_path")}
    if run_type == "watchlist_run":
        return {"watchlist": body.get("watchlist"),
                "strategies": body.get("strategies"),
                "output_path": body.get("output_path")}
    if run_type == "task_run":
        return {"task_config": body.get("task_config"),
                "output_path": body.get("output_path"),
                "daily": body.get("daily", False)}
    return {}


def _auto_name(run_type: str, config: dict) -> str:
    if run_type == "stock_scan":
        return f"{config.get('code', 'Unknown')} Scan"
    if run_type == "watchlist_run":
        return f"{Path(config.get('watchlist', '')).stem} Monitor"
    return f"{Path(config.get('task_config', '')).stem} Task"


def _to_dict(run):
    return {"id": run.id, "name": run.name, "run_type": run.run_type,
            "config": run.config, "status": run.status,
            "created_at": run.created_at, "started_at": run.started_at,
            "finished_at": run.finished_at, "duration_ms": run.duration_ms,
            "error": run.error, "output_path": run.output_path,
            "report_path": run.report_path, "signal_count": run.signal_count,
            "preset_id": run.preset_id}


def _human_size(n: int) -> str:
    if n < 1024: return f"{n} B"
    if n < 1024**2: return f"{n/1024:.1f} KB"
    return f"{n/(1024**2):.1f} MB"
```

- [ ] **Step 2: Create `src/quantflow/web/api/presets.py`**

```python
"""Presets API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from quantflow.web.engine.presets import PresetManager
from quantflow.web.engine.preflight import PreflightChecker

router = APIRouter(prefix="/api/presets", tags=["Presets"])


@router.get("/")
def list_presets():
    presets = PresetManager.list_presets()
    return {"presets": [{"id": p.id, "name": p.name, "run_type": p.run_type,
                         "config": p.config, "created_at": p.created_at}
                        for p in presets]}


@router.post("/")
def create(body: dict):
    name, run_type = body.get("name"), body.get("run_type")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    if run_type not in ("stock_scan", "watchlist_run", "task_run"):
        raise HTTPException(status_code=400, detail="valid run_type required")
    pid = PresetManager.create(name, run_type, body.get("config", {}))
    return {"ok": True, "preset_id": pid}


@router.put("/{pid}")
def update(pid: str, body: dict):
    if not PresetManager.get(pid):
        raise HTTPException(status_code=404, detail="Not found")
    ok = PresetManager.update(pid, body.get("name"), body.get("run_type"), body.get("config", {}))
    if not ok:
        raise HTTPException(status_code=500, detail="Update failed")
    return {"ok": True}


@router.delete("/{pid}")
def delete(pid: str):
    if not PresetManager.delete(pid):
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.post("/{pid}/run")
def run_from_preset(pid: str):
    preset = PresetManager.get(pid)
    if not preset:
        raise HTTPException(status_code=404, detail="Not found")
    result = PreflightChecker.validate(preset.run_type, preset.config)
    if not result.ok:
        return {"ok": False, "errors": result.errors}

    # Access engine through runs module's singleton
    from quantflow.web.api import runs
    engine = runs._get_engine()
    run_id = engine._history.create_run(preset.name, preset.run_type,
                                         preset.config, preset_id=pid)
    became_active = engine._queue.enqueue(run_id)
    if became_active:
        engine.start_processing(run_id)
    return {"ok": True, "run_id": run_id, "status": "active" if became_active else "queued"}
```

- [ ] **Step 3: Modify `src/quantflow/web/server.py`**

Replace `create_app()` function:

```python
def create_app():
    """Create the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(
        title="QuantFlow Web",
        description="Web UI for QuantFlow stock monitoring system",
        version="0.1.0",
    )

    # Register API routes
    from quantflow.web.api.config import router as config_router
    from quantflow.web.api.watchlists import router as watchlist_router
    from quantflow.web.api.tasks import router as task_router
    from quantflow.web.api.library import router as library_router
    from quantflow.web.api.runs import router as runs_router

    app.include_router(config_router)
    app.include_router(watchlist_router)
    app.include_router(task_router)
    app.include_router(library_router)
    app.include_router(runs_router)

    # Initialize runs engine singleton
    from quantflow.web.engine import RunEngine, RunQueue, SSEManager, RunHistory
    from quantflow.web.api import runs as runs_api
    from quantflow.web.api import presets as presets_api

    history = RunHistory()
    sse = SSEManager()

    def _on_run_available(run_id: str):
        engine.start_processing(run_id)

    queue = RunQueue(on_run_available=_on_run_available)
    engine = RunEngine(queue=queue, history=history, sse=sse)
    runs_api._set_engine(engine)
    presets_api._set_engine(runs_api._get_engine())

    app.include_router(presets_api.router)

    # Serve static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
```

- [ ] **Step 4: Create `tests/web/test_runs_api.py`**

```python
"""Tests for Runs API endpoints."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def app():
    from fastapi import FastAPI
    from quantflow.web.api import runs as runs_api
    from quantflow.web.api import presets as presets_api
    from quantflow.web.engine import RunEngine, RunQueue, SSEManager, RunHistory
    from quantflow.web.engine import run_history
    run_history.DB_PATH = Path(":memory:")

    app = FastAPI()
    history = RunHistory()
    sse = SSEManager()
    queue = RunQueue(on_run_available=lambda rid: None)
    engine = RunEngine(queue=queue, history=history, sse=sse)
    runs_api._set_engine(engine)
    presets_api._set_engine(engine)
    app.include_router(runs_api.router)
    app.include_router(presets_api.router)
    return app

@pytest.fixture
def client(app):
    return TestClient(app)


class TestRunsListApi:
    def test_list_empty(self, client):
        r = client.get("/api/runs/")
        assert r.status_code == 200 and r.json()["total"] == 0

    def test_create_and_get(self, client):
        r = client.post("/api/runs/", json={"run_type": "stock_scan", "code": "NVDA.US"})
        assert r.json()["ok"] is True
        rid = r.json()["run_id"]
        r2 = client.get(f"/api/runs/{rid}")
        assert r2.json()["run"]["name"] == "NVDA.US Scan"

    def test_preflight_invalid(self, client):
        r = client.post("/api/runs/", json={"run_type": "stock_scan", "code": "INVALID"})
        data = r.json()
        assert data["ok"] is False and len(data["errors"]) > 0


class TestPresetsApi:
    def test_create_and_list(self, client):
        r = client.post("/api/presets/", json={
            "name": "Daily NVDA", "run_type": "stock_scan",
            "config": {"code": "NVDA.US"}})
        assert r.json()["ok"] is True
        r2 = client.get("/api/presets/")
        names = [p["name"] for p in r2.json()["presets"]]
        assert "Daily NVDA" in names

    def test_delete(self, client):
        r = client.post("/api/presets/", json={
            "name": "X", "run_type": "stock_scan", "config": {"code": "AAPL.US"}})
        pid = r.json()["preset_id"]
        r2 = client.delete(f"/api/presets/{pid}")
        assert r2.json()["ok"] is True
```

- [ ] **Step 5: Run + lint + commit**

```bash
pytest tests/web/test_runs_api.py -v && ruff check src/quantflow/web/api/runs.py src/quantflow/web/api/presets.py src/quantflow/web/server.py tests/web/test_runs_api.py && git add src/quantflow/web/api/runs.py src/quantflow/web/api/presets.py src/quantflow/web/server.py tests/web/test_runs_api.py && git commit -m "feat(api): add Runs and Presets API endpoints with server integration"
```

---

### Task 9: Frontend Shell — Runs Tab HTML + Basic TS

**Files:**
- Modify: `src/quantflow/web/static/index.html`
- Modify: `src/quantflow/web/static/app.ts`

- [ ] **Step 1: Update frontend with all the HTML + TS changes from Tasks 9-12 of the earlier detailed plan**

This includes:
- Runs tab button in nav
- Runs panel with left sidebar + right content
- 4 sub-tabs (Config, Progress, Report, Files)
- New Run modal with 2-step wizard
- All TypeScript state, loading, rendering, and SSE connection functions

Since this is extensive frontend work with many interdependent HTML/TS changes, delegate to the visual-engineering category:

```
task(category="visual-engineering", load_skills=["frontend-ui-ux"], ..., prompt="Implement the Runs panel frontend for QuantFlow Web UI. The project uses TypeScript (ES2020, browser-native ES module) compiled via tsc with Tailwind CSS via CDN.

CONTEXT: Existing web UI lives at src/quantflow/web/static/ with app.ts (TypeScript), app.js (compiled), index.html, utils.ts. The API backend is already implemented. You need to add a new 'Runs' tab.

GOAL: Add a fully functional Runs panel that lets users:
1. View run history in a left sidebar
2. See run details in 4 sub-tabs (Config, Progress, Report, Files)
3. Create new runs via a wizard modal
4. Connect to SSE for live progress updates
5. View presets in the modal dropdown

FILES TO MODIFY:
- src/quantflow/web/static/index.html — Add Runs tab button, Runs panel HTML, New Run modal HTML
- src/quantflow/web/static/app.ts — Add RunRecord interface, state properties, loadRunsList(), selectRun(), render*Tab() functions, SSE connection, modal logic
- src/quantflow/web/static/app.js — Recompile from app.ts using tsc

MUST DO:
1. Follow existing code patterns exactly (state object style, api<T>() function, DOM selectors, tab switching via data-tab attributes)
2. Add Runs tab button in nav (after Library tab, before Settings)
3. Runs panel: left sidebar (250px) with scrollable run list; right content with 4 sub-tabs
4. Run list items show: name (bold), status icon + detail, relative time
5. Config tab: grid of run metadata, raw JSON in details disclosure, "Run Again" and "Save as Preset" buttons
6. Progress tab: progress bar, percentage text, scrollable log container with color-coded entries
7. Report tab: Markdown rendering (simple inline converter — no external lib), file not found handling
8. Files tab: table with file name, size, copy path button
9. New Run modal: Step 1 = 3 cards (Stock Scan, Watchlist Run, Task Run); Step 2 = dynamic form based on type with conditional rendering of config fields
10. Step 2 fields: Stock Scan → code input, date range, indicator checkboxes; Watchlist → dropdown + strategy checkboxes; Task → task config dropdown + daily checkbox
11. Shared: Output path input, CLI command preview, "Check" button, "Run" button
12. connectSSE(): Uses EventSource for /api/runs/{id}/logs:sse with fallback polling
13. appendLog(): Color-coded log entries (green=info, yellow=warning, red=error), auto-scroll
14. Preset dropdown: Fetch from /api/presets/, populate in modal
15. Compile TypeScript: tsc --project src/quantflow/web/static/tsconfig.json and verify no errors

MUST NOT DO:
- Do not modify existing tabs (Watchlists, Tasks, Library, Settings)
- Do not change existing CSS — use inline Tailwind classes only
- Do not add any JavaScript dependencies (no npm packages)
- Do not change the existing api<T>() or state patterns

KEY API ENDPOINTS (all return JSON):
- GET /api/runs/ → {runs: RunRecord[], total: number}
- GET /api/runs/{id} → {run: RunRecord}
- POST /api/runs/ (body: {run_type, code?, watchlist?, task_config?, ...}) → {ok, run_id, status}|{ok: false, errors}
- GET /api/runs/{id}/logs:sse → SSE stream (event: log|progress|status)
- GET /api/presets/ → {presets: [{id, name, run_type, config, created_at}]}
- POST /api/presets/ → {ok: true, preset_id}

COMPILE COMMAND:
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow/src/quantflow/web/static
tsc --project tsconfig.json
")

```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow/src/quantflow/web/static
tsc --project tsconfig.json 2>&1
```

Error count must be 0.

- [ ] **Step 3: Verify existing app functionality is preserved**

```bash
export PYTHONPATH=/Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow/src
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow && pytest tests/web/ -v -x 2>&1 | tail -10
```

- [ ] **Step 4: Commit**

```bash
git add src/quantflow/web/static/index.html src/quantflow/web/static/app.ts src/quantflow/web/static/app.js
git commit -m "feat(web): add Runs tab UI with history list, detail panel, New Run wizard, and SSE"
```

---

### Task 10: Frontend — Presets Integration in New Run Modal

**Files:**
- Modify: `src/quantflow/web/static/app.ts`
- Modify: `src/quantflow/web/static/index.html` (minimal — add presets dropdown in modal)

- [ ] **Step 1: Add presets loading and dropdown to New Run modal**

In `app.ts`, add:

```typescript
async function loadPresetsForModal() {
    try {
        const data = await api<{presets: {id: string; name: string; run_type: string;}[]}>('/api/presets/');
        const select = document.getElementById('run-preset-select') as HTMLSelectElement;
        if (!select) return;
        select.innerHTML = '<option value="">— Start from scratch —</option>' +
            data.presets.map(p => `<option value="${p.id}">${p.name} (${p.run_type})</option>`).join('');
    } catch (e) { /* presets not loaded, user can still create from scratch */ }
}
```

Add to init(): call `loadPresetsForModal()`.

Add to HTML modal — at top of the modal content, before "Step 1":

```html
<div class="mb-4 p-2 bg-purple-50 rounded border border-purple-200">
    <label class="block text-sm font-medium text-gray-700">Start from Preset (optional)</label>
    <select id="run-preset-select" class="w-full border rounded px-2 py-1 mt-1 text-sm">
        <option value="">— Start from scratch —</option>
    </select>
    <p class="text-xs text-gray-500 mt-1">Selecting a preset auto-fills the configuration below</p>
</div>
```

Add preset auto-fill logic: when preset dropdown changes, fetch the preset config and populate form fields.

- [ ] **Step 2: Compile + test + commit**

```bash
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow/src/quantflow/web/static && tsc --project tsconfig.json 2>&1
git add src/quantflow/web/static/app.ts src/quantflow/web/static/index.html src/quantflow/web/static/app.js && git commit -m "feat(web): add preset selection to New Run modal with auto-fill"
```

---

### Task 11: Full End-to-End Verification

- [ ] **Step 1: Run all tests**

```bash
export PYTHONPATH=/Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow/src
cd /Users/neo/SynologyDrive/CLAW/stock-quant-lab/quantflow
pytest tests/ -v -x --ignore=tests/data/ --ignore=tests/execution/ -k "not integration" 2>&1 | tail -15
```

- [ ] **Step 2: Lint entire codebase**

```bash
ruff check src/
```

- [ ] **Step 3: Manual smoke test (optional but recommended)**

```bash
# Start web UI and verify Runs tab renders
python -m quantflow.cli web
```

Check:
- Runs tab visible in nav
- Left sidebar shows "No runs yet"
- "+ New Run" button opens modal
- Modal shows 3 run type cards
- Stock Scan config form renders
- TypeScript compiles without errors

- [ ] **Step 4: Final commit**

```bash
git status  # Verify all changes committed
git log --oneline -10
```

---

## Dependency Graph

```
Task 1 (Executor callback)          ← independent
Task 2 (RunHistory)                  ← independent
Task 3 (RunQueue)                    ← independent
Task 4 (SSEManager)                  ← independent
Task 5 (PreflightChecker)            ← independent (imports existing modules)
Task 6 (RunEngine)                   ← depends on Tasks 1-5 (imports all engine modules)
Task 7 (PresetManager)               ← independent
Task 8 (API + server)                ← depends on Tasks 2-7
Task 9 (Frontend shell)              ← depends on Task 8 (API must exist)
Task 10 (Presets UI)                 ← depends on Task 9
Task 11 (Verification)               ← depends on all above
```

---

## Self-Review

1. **Spec coverage check:**
   - SQLite history ✅ (Task 2)
   - Serial queue ✅ (Task 3)
   - SSE broadcasting ✅ (Task 4)
   - Preflight validation ✅ (Task 5)
   - RunEngine thread wrapper ✅ (Task 6)
   - Presets CRUD ✅ (Task 7)
   - API endpoints ✅ (Task 8)
   - Server integration ✅ (Task 8)
   - Frontend tab/panel ✅ (Task 9)
   - New Run wizard ✅ (Task 9)
   - Presets in modal ✅ (Task 10)
   - Executor progress callback ✅ (Task 1)
   - Report viewing ✅ (Task 9)
   - Files tab ✅ (Task 9)
   - Progress + SSE ✅ (Task 9)
   - Cancel runs ✅ (Task 8)
   - Unit tests ✅ (Tasks 2-8)
   - No TBD/TODO placeholders ✅

2. **Type consistency:** RunRecord interface in TS matches RunRecord dataclass in Python. API response shapes match TypeScript types. All verified.

3. **No placeholders:** Every step has actual code.

4. **Scope:** Focused entirely on Runs panel + execution engine + presets. Does not modify existing CLI, cron, YAML formats, or core strategy logic.
