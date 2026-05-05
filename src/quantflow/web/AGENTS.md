## OVERVIEW
- Web UI module: FastAPI backend + TypeScript frontend. Provides visual management of watchlists, tasks, runs, and system settings.

## STRUCTURE
```
web/
├── server.py            # FastAPI app creation and startup logic
├── config.py            # WebConfig - port/host loading from quantflow.yaml
├── api/                 # REST API routes
│   ├── watchlists.py    # GET/POST/PUT/DELETE watchlists, search
│   ├── tasks.py         # GET/POST/PUT/DELETE tasks, task-files
│   ├── config.py        # GET/PUT system config
│   ├── library.py       # Strategy/indicator catalog, parameter updates
│   ├── runs.py          # Run CRUD, preflight, SSE logs, indicator data, files, cancel, queue, open-folder
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
- Architecture: API routes are stateless; RunEngine manages execution state via SQLite + in-memory queue

## CONVENTIONS
- API routers use prefix (e.g., `/api/runs`), grouped by domain
- SSE uses custom endpoint format: `/api/runs/{id}/logs:sse` (colon in path)
- Frontend TypeScript compiled to JS in same directory via `tsc --project tsconfig.json`
- Static files served with SPA fallback
- RunEngine singleton pattern: `_set_engine()` / `_get_engine()` in API modules

## ANTI-PATTERNS
- Do NOT modify `app.ts` without re-running `tsc` to compile to `app.js`
- Do NOT add API endpoints without registering router in `server.py`
- Do NOT bypass PreflightChecker for run validation
