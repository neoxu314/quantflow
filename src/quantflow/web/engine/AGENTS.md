## OVERVIEW
Core execution engine for the Web UI. Manages run lifecycle: creation  queuing  execution  history. Runs stock_scan, watchlist_run, and task_run in background threads with real-time SSE progress reporting.

## STRUCTURE
```
engine/
├── run_engine.py           # RunEngine — main executor
├── run_history.py          # RunHistory — SQLite persistence
├── run_queue.py            # RunQueue — active/pending queue
├── sse.py                  # SSEManager — Server-Sent Events
├── preflight.py            # PreflightChecker — run config validation
└── presets.py              # PresetManager — save/load run configurations
```

## KEY COMPONENTS

### RunEngine (run_engine.py)
- Entry: `start_processing(run_id)` spawns background thread
- Execution methods: `_exec_stock_scan()`, `_exec_watchlist_run()`, `_exec_task_run()`
  - **stock_scan**: Output to `{output_path}/{run_id}/` (isolated subdirectory)
  - **watchlist_run**: Output to `{output_path}/{run_id}/` (isolated subdirectory)
  - **task_run**: Output directly to `{output_path}/` (NO run_id subdirectory, user manages output)
    - Daily mode: Output to `{output_path}/{YYYY-MM-DD}/`
- Date handling: stock_scan fetches data from `fetch_start` (user start_date minus lookback warmup) to `end_date`, then trims result to user-specified date range using `df["date"]` column filter
- Cancellation: `CancellationFlag` per run, checked between stock processing
- Progress: calls `on_progress` callback with `ProgressEvent` objects (type=current/total/code/message/level)
- Output paths:
  - stock_scan: `{output_path}/{run_id}/{code}_indicators.json`
  - watchlist_run: `{output_path}/{run_id}/` (JSON + Markdown)
  - task_run: `{output_path}/` or `{output_path}/{date}/` (per-task + combined files)

### RunHistory (run_history.py)
- SQLite-backed persistent storage at `~/.quantflow/runs.db`
- `RunRecord` dataclass: id, name, run_type, config, status, timestamps, signal_count, output_path, report_path, error
- Methods: `create_run()`, `get_run()`, `list_runs()`, `update_status()`, `delete_run()`

### RunQueue (run_queue.py)
- In-memory queue with active/pending states
- `enqueue(run_id)` → returns True if became active, False if queued
- `dequeue()` → pops next pending run
- `cancel(run_id)` → removes from queue
- `on_run_available` callback for notification

### SSEManager (sse.py)
- Manages SSE connections per run_id
- `subscribe(run_id)` → returns Queue for log/progress/status events
- `publish_log()`, `publish_progress()`, `publish_status()` → broadcasts to subscribers
- Custom disconnect mechanism via sentinel object

### PreflightChecker (preflight.py)
- Validates run configs BEFORE execution
- stock_scan: validates code format (REGEX), date format + order, known indicators
- watchlist_run: validates watchlist file exists + non-empty, strategy IDs
- task_run: validates task config file exists + parseable
- output_path: validates createable
- Returns `ValidationResult` with `ok` property and list of `errors`

### PresetManager (presets.py)
- JSON-file persistence for saved run configurations
- `create(name, run_type, config)` → returns preset_id
- `list_presets()`, `get(id)`, `update(id, ...)`, `delete(id)`
- Presets allow re-running with same parameters via `/api/presets/{id}/run`

## TASK_RUN OUTPUT BEHAVIOR

**Output directory** (user-specified, default `./output`):
- No run_id subdirectory (unlike stock_scan/watchlist_run)
- All output files in same directory, differentiated by filename

**Generated files**:
- `{task_name}.md` — per-task Markdown report
- `{task_name}.json` — per-task JSON results (from Executor)
- `Daily_Report.md` — combined Markdown report
- `Combined_Results.json` — combined JSON results

**Daily mode** (`daily=True`):
- Date subdirectory: `{output_path}/{YYYY-MM-DD}/`
- All files in date subdirectory

**Delete behavior** (runs.py `delete_run`):
- Only deletes task output files, preserves user files
- Safe: Never deletes entire output directory

## CONVENTIONS
- RunEngine singleton pattern: API modules call `_set_engine()` / `_get_engine()` from server.py
- SSE event types: `log`, `progress`, `status` — each carries a JSON payload
- Validation is synchronous and fast; no network calls in preflight
- Cancellation is cooperative: checked only between items, not mid-fetch

## ANTI-PATTERNS
- Do NOT share RunEngine instances across requests — use singleton via `_get_engine()`
- Do NOT mutate run config after creation — treat as immutable
- Do NOT bypass SSE unsubscribe on client disconnect — causes memory leak
- Do NOT write runs directly to SQLite — always use `RunHistory` methods

This file should be treated as a lightweight, practical reference for how the web engine executes and coordinates runs, monitors progress, stores history, and validates configurations prior to execution.
