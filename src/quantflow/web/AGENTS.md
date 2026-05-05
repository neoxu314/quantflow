## OVERVIEW
- Web UI module: FastAPI backend + TypeScript frontend. Provides visual management of watchlists, tasks, runs, and system settings.

## STRUCTURE
```
web/
├── server.py            # FastAPI app creation and startup logic
├── config.py            # WebConfig - port/host loading from quantflow.yaml
├── api/                 # REST API routes
│   ├── watchlists.py    # GET/POST/PUT/DELETE watchlists, search
│   ├── tasks.py         # GET/POST/PUT/DELETE tasks (NO output field)
│   ├── config.py        # GET/PUT system config
│   ├── library.py       # Strategy/indicator catalog, parameter updates
│   ├── runs.py          # Run CRUD, safe delete, SSE logs, indicator data, files
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
    ├── app.ts           # Main frontend logic, UI rendering
    ├── utils.ts         # Pure utility functions (getNestedValue, setNestedValue, formatStockCode)
    └── tsconfig.json    # TypeScript config
```

## KEY COMPONENTS
- `create_app()`: Wires all API routers, initializes RunEngine/RunHistory/RunQueue/SSEManager, mounts static files
- `start_server()`: Loads WebConfig, opens browser, starts uvicorn
- `updateCliPreview()`: Real-time CLI command preview generator for New Run modal (all run types)
- Architecture: API routes are stateless; RunEngine manages execution state via SQLite + in-memory queue

## API DETAILS

### runs.py (Run Management)
- `delete_run(run_id)`: **CRITICAL SAFETY** - safe delete logic
  - **stock_scan/watchlist_run**: Delete entire output directory (contains run_id subdirectory)
  - **task_run**: Only delete task output files, preserve user files
    - Deleted: `Daily_Report.md`, `Combined_Results.json`, `{task_name}.md`, `{task_name}.json`
    - Preserved: All other files in output directory (user photos, documents, etc.)
    - Daily mode: Delete date subdirectory if empty
  - **Safety guarantee**: Never delete user's non-task files
- `_delete_task_run_outputs()`: Helper function for safe task_run deletion
  - Reads task config to get task names
  - Deletes only task-generated files
  - Fallback: Delete `{run.name}.json` if task config missing

### tasks.py (Task Management)
- Task YAML format: **NO output field** (controlled by CLI/Web `--output`)
- `TaskModel`: `name`, `watchlist`, `strategies`, optional `days_back`
- Duplicate task names rejected with 409 error

## CONVENTIONS
- API routers use prefix (e.g., `/api/runs`), grouped by domain
- SSE uses custom endpoint format: `/api/runs/{id}/logs:sse` (colon in path)
- Frontend TypeScript compiled to JS in same directory via `tsc --project tsconfig.json`
- Static files served with SPA fallback
- RunEngine singleton pattern: `_set_engine()` / `_get_engine()` in API modules
- **Event delegation**: Use for dynamically generated elements (e.g., `#run-strategy-checkboxes`) to avoid rebinding listeners
- **Safety first**: Never write to production paths in tests (use tmp_path fixture)

## ANTI-PATTERNS
- Do NOT modify `app.ts` without re-running `tsc` to compile to `app.js`
- Do NOT add API endpoints without registering router in `server.py`
- Do NOT bypass PreflightChecker for run validation
- Do NOT write tests that modify production data (watchlists/, config/)
- Do NOT use production file paths in test code (use tmp_path)
