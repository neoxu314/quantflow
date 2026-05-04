# QuantFlow Runs Panel Design

**Date:** 2026-05-03
**Author:** Sisyphus
**Scope:** Add "Runs" panel to Web UI for executing scans/tasks/monitoring, with execution history, presets, real-time progress, and report viewing.

---

## 1. Overview

A new **"Runs"** tab in the QuantFlow Web UI enables users to:

1. **Execute** quant analysis directly from the browser (no CLI needed)
2. **Manage presets** — saved run configurations for one-click re-execution
3. **Track history** — persistent execution log with status, results, and timing
4. **Monitor progress** — real-time percentage progress + live log stream via SSE
5. **View results** — inline Markdown reports + file access (open folder/copy path)

**Key principles:**
- Web and CLI are **independent entry points** sharing the same Python engine layer
- No modification to existing YAML formats, CLI commands, or cron behavior
- Existing `Executor` and `Orchestrator` classes are reused, extended with progress callbacks
- SQLite stores execution metadata; the engine layer remains unchanged in its core logic

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    QuantFlow Web Server                       │
│                                                               │
│  / Runs Tab (frontend)                                        │
│  ├── Left sidebar: Run history list                          │
│  ├── Right content: 4-tab detail panel                       │
│  │   ├── Config    (run params, "Run Again", "Save Preset")   │
│  │   ├── Progress  (progress bar + SSE log stream)            │
│  │   ├── Report    (rendered Markdown)                        │
│  │   └── Files     (output files, open folder, copy path)     │
│  └── Modal: New Run wizard (type → config → preview → run)    │
│                                                               │
│  / API Endpoints                                              │
│  ├── POST /api/runs/          — Create + execute run          │
│  ├── GET  /api/runs/          — List history (paginatable)    │
│  ├── GET  /api/runs/{id}      — Run detail + status           │
│  ├── POST /api/runs/{id}/cancel — Cancel running run          │
│  ├── GET  /api/runs/{id}/report — Get Markdown report         │
│  ├── GET  /api/runs/{id}/files  — List output files           │
│  ├── GET  /api/runs/{id}/logs:sse — SSE log stream           │
│  ├── GET  /api/runs/queue     — Queue status                  │
│  ├── CRUD /api/presets/       — Preset management             │
│  └── POST /api/presets/{id}/run — Execute from preset         │
│                                                               │
│  / Backend Services (new Python modules)                      │
│  ├── RunEngine        — Runs executor/orchestrator in thread   │
│  ├── RunQueue         — Serial FIFO queue                     │
│  ├── RunHistory       — SQLite read/write wrapper             │
│  ├── Presets          — YAML preset loader/saver              │
│  ├── PreflightChecker — Pre-execution validation             │
│  └── SSEManager       — SSE connection broadcaster            │
│                                                               │
├───────────────────────────────────────────────────────────────┤
│              Shared Python Engine Layer (existing)             │
│  data │ indicators │ strategies │ execution │ orchestration   │
│  [Extended with optional `on_progress` callback]                │
├───────────────────────────────────────────────────────────────┤
│  CLI / Cron (existing, unaffected)                            │
│  python -m quantflow.cli {scan|monitor|tasks}                  │
└───────────────────────────────────────────────────────────────┘
```

---

## 3. New Files

### 3.1 Backend Python

| File | Purpose |
|------|---------|
| `src/quantflow/web/api/runs.py` | Runs API endpoints (CRUD, execute, cancel, report, files, logs) |
| `src/quantflow/web/api/presets.py` | Presets CRUD API + preset-based execution |
| `src/quantflow/web/engine/run_engine.py` | RunEngine: wraps `Executor`/`Orchestrator` in thread with progress callback |
| `src/quantflow/web/engine/run_queue.py` | Serial FIFO queue: manages pending/active/completed runs |
| `src/quantflow/web/engine/preflight.py` | Pre-flight validation for run configurations |
| `src/quantflow/web/engine/sse.py` | SSE (Server-Sent Events) broadcaster for real-time logs |
| `src/quantflow/web/engine/history.py` | SQLite wrapper for execution history persistence |
| `src/quantflow/web/engine/presets.py` | YAML preset management (load/save/delete from `.quantflow/presets/`) |
| `src/quantflow/web/engine/__init__.py` | Engine package init |

### 3.2 Schema & Data

| File | Purpose |
|------|---------|
| `.quantflow/runs.db` | SQLite database (created on first run) |
| `.quantflow/presets/*.yaml` | Preset configuration files |
| `.quantflow/` | Created at project root if absent during server startup |

### 3.3 Frontend

| File | Change |
|------|--------|
| `src/quantflow/web/static/index.html` | Add Runs tab button + Runs panel HTML + New Run modal + Presets modal |
| `src/quantflow/web/static/app.ts` | Add Runs tab logic (history list, new run wizard, SSE connection, progress rendering) |

### 3.4 Modified Files

| File | Change |
|------|--------|
| `src/quantflow/web/server.py` | Register new API routes, initialize RunEngine/SSEManager/RunQueue on startup |
| `src/quantflow/execution/executor.py` | Add optional `on_progress` callback to `Executor.execute()` |

---

## 4. SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS run_history (
    id          TEXT PRIMARY KEY,     -- UUID4
    name        TEXT NOT NULL,         -- Run display name
    run_type    TEXT NOT NULL,         -- 'stock_scan' | 'watchlist_run' | 'task_run'
    config      TEXT NOT NULL,         -- JSON of run parameters
    status      TEXT NOT NULL,         -- 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
    created_at  TEXT NOT NULL,         -- ISO 8601 timestamp
    started_at  TEXT,                  -- ISO 8601 timestamp
    finished_at TEXT,                  -- ISO 8601 timestamp
    duration_ms INTEGER,               -- Execution duration
    error       TEXT,                  -- Error message if failed
    output_path TEXT,                  -- Path to output files
    report_path TEXT,                  -- Path to Markdown report
    signal_count INTEGER DEFAULT 0,    -- Number of signals triggered
    preset_id   TEXT                   -- If run from preset, the preset name
);

CREATE INDEX IF NOT EXISTS idx_run_status ON run_history(status);
CREATE INDEX IF NOT EXISTS idx_run_created ON run_history(created_at DESC);
```

---

## 5. Backend API Spec

### 5.1 Runs Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/runs` | List runs (query: `?status=running&limit=50&offset=0`) |
| `POST` | `/api/runs` | Create + execute run (body: `RunRequest`) |
| `GET` | `/api/runs/{run_id}` | Get run detail + current status |
| `POST` | `/api/runs/{run_id}/cancel` | Cancel a queued or running run |
| `GET` | `/api/runs/{run_id}/report` | Get rendered Markdown report content |
| `GET` | `/api/runs/{run_id}/files` | List output files with paths |
| `GET` | `/api/runs/{run_id}/logs:sse` | SSE stream for real-time logs |
| `GET` | `/api/runs/queue` | Get current queue status (active + pending count) |

**RunRequest body:**
```typescript
interface RunRequest {
  run_type: "stock_scan" | "watchlist_run" | "task_run";
  name?: string;                    // Custom name, auto-generated if omitted
  preset_id?: string;               // If creating from preset

  // stock_scan fields
  code?: string;
  start_date?: string;              // YYYY-MM-DD
  end_date?: string;                // YYYY-MM-DD
  indicators?: string[];            // ["kdj", "macd", "dual_line"]

  // watchlist_run fields
  watchlist?: string;               // Path to watchlist YAML
  strategies?: string[];            // Strategy IDs (default: oversold + midrange)

  // task_run fields
  task_config?: string;             // Path to tasks YAML
  daily?: boolean;                  // Daily archive mode

  // shared
  output_path?: string;             // Output directory override
}
```

### 5.2 Presets Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/presets` | List all presets |
| `POST` | `/api/presets` | Create new preset (body: `PresetRequest`) |
| `PUT` | `/api/presets/{preset_id}` | Update preset |
| `DELETE` | `/api/presets/{preset_id}` | Delete preset YAML file |
| `POST` | `/api/presets/{preset_id}/run` | Execute immediately with preset config (creates run, returns run_id) |

**PresetRequest body:**
```typescript
interface PresetRequest {
  name: string;
  run_type: "stock_scan" | "watchlist_run" | "task_run";
  config: Record<string, any>;  // Same as RunRequest fields (minus run_type)
}
```

### 5.3 SSE Event Format

```
event: log
data: {"run_id": "uuid", "timestamp": "2026-05-03T14:32:00", "level": "info", "message": "Processing NVDA.US..."}

event: progress
data: {"run_id": "uuid", "current": 12, "total": 50, "percentage": 24}

event: status
data: {"run_id": "uuid", "status": "completed", "signal_count": 3}

event: error
data: {"run_id": "uuid", "error": "Connection timeout"}
```

---

## 6. Run Types and Parameter Mapping

### 6.1 Stock Scan (`stock_scan`)

Maps to: `cli scan --code X`

| Parameter | Required | Default | Validation |
|-----------|----------|---------|------------|
| `code` | Yes | - | Valid format (600519.SH, NVDA.US, etc.) |
| `start_date` | No | 1 year ago | Valid YYYY-MM-DD, ≤ end_date |
| `end_date` | No | Today | Valid YYYY-MM-DD, ≥ start_date |
| `indicators` | No | ["kdj", "dual_line"] | Each in registered indicators |
| `output_path` | No | `output/manual_scans/` | Writable path |

### 6.2 Watchlist Run (`watchlist_run`)

Maps to: `cli monitor --watchlist X`

| Parameter | Required | Default | Validation |
|-----------|----------|---------|------------|
| `watchlist` | Yes | - | File exists, non-empty items |
| `strategies` | No | ["daily_bull_oversold", "daily_bull_mid_range"] | Each in strategy registry |
| `output_path` | No | `output/manual_watchlist/` | Writable path |

### 6.3 Orchestration Run (`task_run`)

Maps to: `cli tasks --config X`

| Parameter | Required | Default | Validation |
|-----------|----------|---------|------------|
| `task_config` | Yes | - | File exists, contains ≥1 valid tasks |
| `output_path` | No | `reports/` | Writable path |
| `daily` | No | false | Boolean |

---

## 7. Pre-flight Validation

All runs go through `PreflightChecker.validate()` before entering the queue.

**Checks performed:**

1. **Stock code format** — Regex validation against known formats (A-share: `{6digits}.{SH|SZ}`, US: `{ticker}.US`, HK: `{5digits}.HK`, JP: `{4digits}.JP`, KR: `{6digits}.KR`)
2. **Watchlist exists and non-empty** — Load YAML, verify `items` array has ≥1 entry
3. **Task config valid** — Load YAML via `TaskConfig.load()`, verify ≥1 valid tasks
4. **Output path writable** — `os.makedirs(output, exist_ok=True)`, catch permission errors
5. **Data source available** — If Tushare needed but token missing, return error with link to Settings
6. **Strategies registered** — Each strategy ID must exist in strategy registry
7. **Indicators registered** — Each indicator name must be a known indicator
8. **Date range valid** — start ≤ end, neither in future

**Response format:**
```json
{
  "ok": false,
  "errors": [
    "Watchlist 'us_demo.yaml' not found",
    "Output path '/invalid/dir' cannot be created"
  ]
}
```

Pre-flight runs synchronously on `POST /api/runs`. If it fails, the request returns 400 with errors — no run is created.

---

## 8. Execution Engine Design

### 8.1 RunEngine

```python
class RunEngine:
    """Wraps the shared execution/orchestration layer in a thread with progress tracking."""

    def __init__(self, queue: RunQueue, history: RunHistory, sse: SSEManager): ...
    def start_run(self, run_id: str, config: dict):
        """Spawn a background thread to execute the run."""

    def _execute_stock_scan(self, run_id, config): ...
    def _execute_watchlist_run(self, run_id, config): ...
    def _execute_task_run(self, run_id, config): ...
    def cancel_run(self, run_id: str):
        """Signal cancellation to a running or queued run."""
```

### 8.2 Execution Thread Model

```
Main Thread (FastAPI uvicorn)
  └── POST /api/runs/
       └── RunQueue.enqueue(run_id)
            └── If no active run → trigger RunEngine.start_run()

Background Thread (RunEngine)
  ├── Update status → 'running' (SQLite)
  ├── Execute via Executor/Orchestrator with on_progress callback
  │    └── Callback → SSEManager.broadcast(progress + log events)
  ├── On success → status 'completed', signal_count, report_path
  └── On failure → status 'failed', error message
  └── After completion → RunQueue.dequeue() → start next if pending
```

**Thread safety:** SQLite uses `check_same_thread=False` + a queue-based connection pattern to avoid concurrent access issues. All SQLite writes go through a single writer thread (the RunEngine itself).

### 8.3 Progress Callback Extension

The `Executor.execute()` method gains an optional callback parameter:

```python
def execute(
    self,
    job: ExecutionJob,
    on_progress: Optional[Callable[[ProgressEvent], None]] = None
) -> list[ExecutionResultItem]:
    """Execute job with optional progress reporting."""
```

`ProgressEvent` is a simple dataclass:
```python
@dataclass
class ProgressEvent:
    type: str          # "stock_start" | "stock_done" | "batch_complete" | "log"
    current: int       # Current stock index (0-based)
    total: int         # Total stocks
    code: str          # Current stock code
    message: str       # Human-readable message
    level: str         # "info" | "warning" | "error"
```

**Impact on existing callers:** Zero. The callback is optional and defaults to `None`. CLI calls `executor.execute(job)` unchanged.

---

## 9. Frontend Spec

### 9.1 Runs Tab Layout

```
┌─────────────────────────────────────────────────────────┐
│ Runs                                  [+ New Run]  [▼]  │
├──────────────┬──────────────────────────────────────────┤
│ LEFT SIDEBAR │ RIGHT CONTENT                            │
│              │                                          │
│ ── All Runs  │ [Config] [Progress] [Report] [Files]     │
│ ── Presets   │                                          │
│              │ (Content based on selected run)           │
│  NVDA.US     │                                          │
│  🟢 Done · 2 │                                          │
│  May 3 14:32 │                                          │
│              │                                          │
│  US_Tech     │                                          │
│  🟡 Run 24/50│                                          │
│  May 3 14:30 │                                          │
│              │                                          │
│  tasks_us    │                                          │
│  🟢 Done · 5 │                                          │
│  May 2 20:00 │                                          │
├──────────────┴──────────────────────────────────────────┤
```

- **Top bar:** "Runs" title + `+ New Run` button (with dropdown for quick access to presets)
- **Left sidebar:** Subtabs "All Runs" / "Presets" — filtered list of runs or presets
- **Right panel:** 4 subtabs (Config, Progress, Report, Files) for selected run

### 9.2 New Run Modal (3-Step Wizard)

**Step 1: Run Type** — Three large cards to choose from

**Step 2: Configuration** — Dynamic form based on type:
- Stock scan: code selector (searchable), date range, indicator checkboxes, output path
- Watchlist run: watchlist dropdown (loaded from `/api/watchlists`), strategy multi-select, output path
- Task run: task config dropdown (from `/api/task-files`), daily checkbox, output path

**Step 3: Preview & Execute** — Shows equivalent CLI command, with buttons:
- `[Cancel]` — Close modal
- `[Save as Preset]` — Opens sub-form to name + save preset, then optionally run
- `[🔍 Check]` — Trigger pre-flight validation inline
- `[▶ Run]` — Execute (disabled until pre-flight passes)

### 9.3 Progress Tab

```
┌──────────────────────────────────────────────────────┐
│ ████████████████░░░░░░░░░░  62% (31/50 stocks)       │
│                                                      │
│ Currently processing: 000977.SZ                       │
│ Last completed:    NVDA.US ✅  (1 signal)              │
│                                                      │
│ ── Live Log ──────────────────────────────────────── │
│ 14:32:01  INFO  Starting execution of US_Tech_Leaders │
│ 14:32:03  INFO  Fetching data for NVDA.US...          │
│ 14:32:05  INFO  NVDA.US complete: 1 signals found     │
│ 14:32:06  INFO  Fetching data for AAPL.US...          │
│ 14:32:07  WARN  Rate limit approaching, slowing down  │
│ 14:32:08  INFO  Fetching data for 000977.SZ...        │
└──────────────────────────────────────────────────────┘
```

- Progress bar updates via SSE `progress` events
- Log entries append via SSE `log` events
- Auto-scroll to latest log entry
- Log entries color-coded by level (info=gray, warning=yellow, error=red)

### 9.4 Report Tab

- If run completed successfully and report file exists → fetch and render Markdown inline
- If no signals → show "No signals triggered for this run" with an info icon
- If run failed → show error message from run history
- If run still in progress → show "Report will be available after completion"

### 9.5 Files Tab

- Table listing all output files for the run:
  - File path
  - File size (human-readable)
  - Type (JSON / Markdown)
  - Actions: `[📂 Open Folder]` `[📋 Copy Path]`

---

## 10. Error Handling

| Scenario | Handling |
|----------|----------|
| Pre-flight fails | 400 with error array, modal shows inline errors |
| Queue full | Rare, but return 503 if queue has >100 pending runs |
| Duplicate run name | Allowed — names are display-only, IDs are UUID |
| Cancel running job | Thread receives cancellation signal, sets status to 'cancelled', partial results preserved |
| SSE disconnect | Frontend auto-reconnects with last-event-id, replays missed events |
| SQLite locked | Retry with exponential backoff (max 3 attempts) |
| Output path missing at report time | Report tab shows "Report file not found" |
| Server restart mid-execution | Active run marked as 'failed' on startup, queue persists in SQLite and resumes |

---

## 11. Security

- Local-only binding (127.0.0.1 default) — same as existing web UI
- File path validation: all paths resolved relative to project root, no `..` traversal
- Preset files restricted to `.quantflow/presets/` directory
- Output paths validated to be within or under project directory (configurable)
- No authentication (personal use, same as existing web UI)

---

## 12. Migration Path

### Phase 1: Infrastructure (backend only, no UI visible)
- SQLite schema + `RunHistory` class
- `RunQueue` + `SSEManager`
- `PreflightChecker`
- `Executor.execute()` progress callback extension

### Phase 2: API Layer
- `/api/runs/*` endpoints
- `/api/presets/*` endpoints
- SSE log endpoint

### Phase 3: Frontend — Shell
- Tab button + empty panel in `index.html`
- Tab switching logic in `app.ts`

### Phase 4: Frontend — New Run Flow
- Run type selector modal
- Dynamic configuration forms
- Preview + pre-flight + execute

### Phase 5: Frontend — History + Progress
- Left sidebar run list
- SSE connection and progress rendering
- Config/Progress/Report/Files tabs

### Phase 6: Frontend — Presets
- Preset list in sidebar
- Create/edit/delete preset modal
- Dropdown in "New Run" to run from preset

### Phase 7: Verification
- Manual testing of all 3 run types
- Concurrent request safety
- SSE reconnection behavior
- `lsp_diagnostics` clean
- `pytest` (add unit tests for PreflightChecker, RunQueue, RunHistory)

---

## 13. Self-Review

**Placeholder check:** No TBD/TODO in core sections. Future enhancements (cron history sync) explicitly out of scope.
**Consistency:** Run request body fields match CLI parameter semantics. SQLite schema matches API responses.
**Scope:** Focused on web-based execution only. Does not modify cron, CLI output format, or YAML structures.
**Ambiguity check:**
- Run names are auto-generated from type + primary identifier (e.g., "NVDA.US Scan", "us_tech.yaml Monitor")
- IDs are UUID4 to guarantee uniqueness
- SSE endpoint uses `event-stream` content type, standard `retry:` directive for reconnect
- Pre-flight is synchronous; failure blocks run creation (returns 400, no DB record)
- Thread model: single execution thread (serial queue), SSEManager is thread-safe via queue-based message passing
- SQLite writes happen on the execution thread only; reads happen on FastAPI thread (SQLite handles read concurrency)
- "Open Folder" uses OS-specific command (macOS: `open`, Linux: `xdg-open`, Windows: `start`) — but runs client-side via link protocol, backend returns the path

---

## 14. Spec Ready for Review

Please review the spec and let me know if you want to make any changes before we start writing out the implementation plan.
