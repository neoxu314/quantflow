## OVERVIEW
- Web UI module: FastAPI backend + TypeScript frontend. Provides visual management of watchlists, tasks, runs, and system settings.

## STRUCTURE
```
web/
├── server.py            # FastAPI app creation and startup logic
├── config.py            # WebConfig - port/host loading from quantflow.yaml
├── api/                 # REST API routes
│   ├── watchlists.py    # GET/POST/PUT/DELETE watchlists, search, inline editing
│   ├── tasks.py         # GET/POST/PUT/DELETE tasks (NO output field)
│   ├── config.py        # GET/PUT system config
│   ├── library.py       # Strategy/indicator catalog, parameter updates
│   ├── runs.py          # Run CRUD, safe delete, file logs + SSE, checkpoint/resume, indicator data, files
│   ├── presets.py       # Preset CRUD + run from preset
│   └── browse.py        # Directory browsing + mkdir
├── engine/              # Core execution engine
│   ├── run_engine.py    # RunEngine - wraps execution in background threads
│   ├── run_history.py   # SQLite persistence for run records
│   ├── run_queue.py     # Run queue with active/pending states
│   ├── sse.py           # Server-Sent Events manager
│   ├── preflight.py     # Pre-flight validation for run configs
│   └── presets.py       # PresetManager - save/load run configurations
└── static/              # Frontend (TypeScript → JavaScript)
    ├── index.html       # Single-page app
    ├── app.ts           # Main frontend logic, UI rendering, inline stock editing
    ├── utils.ts         # Pure utility functions (getNestedValue, setNestedValue, formatStockCode)
    └── tsconfig.json    # TypeScript config
```

## KEY COMPONENTS
- `create_app()`: Wires all API routers, initializes RunEngine/RunHistory/RunQueue/SSEManager, mounts static files, and calls `RunHistory.reconcile_stale_runs()` once at startup to mark orphaned `running`/`queued` runs as `interrupted`
- `start_server()`: Loads WebConfig, opens browser, starts uvicorn
- `updateCliPreview()`: Real-time CLI command preview generator for New Run modal (all run types)
- Architecture: API routes are stateless; RunEngine manages execution state via SQLite + in-memory queue

## API DETAILS

### runs.py (Run Management)
- `delete_run(run_id)`: **CRITICAL SAFETY** - unified precise file deletion
  - **stock_scan**: Delete `{code}_indicators.json` only
  - **watchlist_run**: Delete `{run.name}.json` + `{run.name}.md`
  - **task_run**: Delete Daily_Report.md, Combined_Results.json, and per-task files
  - **Safety guarantee**: Never deletes entire directory or user files
- `_delete_task_run_outputs()`: Helper function for safe task_run deletion
  - Reads task config to get task names
  - Deletes only task-generated files
  - Fallback: Delete `{run.name}.json` if task config missing

## Runs API

### Delete Run Endpoint
- **Path**: `/api/runs/{run_id}`
- **Method**: DELETE
- **Behavior**: Unified precise file deletion for all run types
  - stock_scan: Deletes indicator JSON only
  - watchlist_run: Deletes Executor JSON + Markdown report
  - task_run: Deletes Daily_Report.md, Combined_Results.json, and per-task files
  - Also removes the run's checkpoint file (`~/.quantflow/checkpoints/<run_id>.json`)
- **Safety**: Does NOT delete entire directory to prevent user file loss

### Logs & Resume Endpoints
- `GET /api/runs/{id}/logs?tail=N` — returns the real on-disk log file (`run_history.log_path`), `tail=0` for full text. Progress tab polls this (2s while running); it is the same content as `<output>/logs/*.log`, NOT the SSE summary events.
- `GET /api/runs/{id}/checkpoint` — checkpoint summary (exists / done count / updated_at).
- `POST /api/runs/{id}/resume` — resumes a `watchlist_run`/`task_run` in `failed|cancelled|interrupted`: creates a new run, copies the checkpoint (`resumed_from`), returns 400 for other types/states. `stock_scan` is not resumable.
- `GET /api/runs/{id}/logs:sse` — SSE `progress` events (bar) + `log` summary events; the frontend no longer feeds summary logs into the black log box.

### tasks.py (Task Management)
- Task YAML format: **NO output field** (controlled by CLI/Web `--output`)
- `TaskModel`: `name`, `watchlist`, `strategies`, optional `days_back`
- Duplicate task names rejected with 409 error

### watchlists.py (Watchlist Management)
- Inline editing: Name and tags cells are clickable in the stock table — click to edit, Enter/blur to save, Escape to cancel
- Editing updates in-memory state, marks dirty, requires explicit Save (PUT full replacement)
- **No backend API changes** — reuses existing `PUT /api/watchlists/{filename}` full-replacement endpoint

## CONVENTIONS
- API routers use prefix (e.g., `/api/runs`), grouped by domain
- SSE uses custom endpoint format: `/api/runs/{id}/logs:sse` (colon in path)
- Frontend TypeScript compiled to JS in same directory via `tsc --project tsconfig.json`
- Static files served with SPA fallback
- RunEngine singleton pattern: `_set_engine()` / `_get_engine()` in API modules
- **Event delegation**: Use for dynamically generated elements (e.g., `#run-strategy-checkboxes`) to avoid rebinding listeners
- **Inline editing**: Name/tags cells use `e.currentTarget` (not `e.target`) in click handlers to correctly resolve `data-idx` when clicking child elements (tag pills)
- **Safety first**: Never write to production paths in tests (use tmp_path fixture)

## ANTI-PATTERNS
- Do NOT modify `app.ts` without re-running `tsc` to compile to `app.js`
- Do NOT add API endpoints without registering router in `server.py`
- Do NOT bypass PreflightChecker for run validation
- Do NOT write tests that modify production data (watchlists/, config/)
- Do NOT use production file paths in test code (use tmp_path)
