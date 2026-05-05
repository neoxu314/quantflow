# QUANTFLOW PROJECT KNOWLEDGE

**Generated:** 2026-04-25 / Updated: 2026-05-05
**Scope:** `quantflow/` - Main quant analysis system

## OVERVIEW

Layered Python package: data fetching → indicator calculation → strategy signals → orchestration → execution.

## STRUCTURE

```
quantflow/
├── src/quantflow/
│   ├── data/            # Multi-source data layer
│   ├── indicators/      # Technical indicators
│   │   ├── factory.py      # IndicatorFactory - config-based instantiation
│   ├── strategies/      # Buy/sell strategies
│   ├── execution/       # Execution layer (formerly monitoring)
│   ├── orchestration/   # Task orchestration layer
│   ├── config/          # YAML loader + lookback config
│   │   ├── loader.py       # ConfigLoader - token, yfinance settings
│   │   └── lookback.py     # compute_days_back() - shared lookback logic
│   ├── backtest/        # Reserved - stub (__init__.py only)
│   ├── risk/            # Reserved - stub (__init__.py only)
│   ├── web/             # Web UI server (FastAPI + frontend)
│   ├── reports/         # Markdown report generation
│   └── cli.py           # Entry: `python -m quantflow.cli` (stock_scan, watchlist_run, task_run, web)
├── config/tasks_*.yaml  # Orchestration task configs (tasks_asia_mac.yaml, tasks_us_mac.yaml, etc.)
├── config/indicators.yaml  # Indicator parameter defaults
├── scripts/              # Build verification utilities
...
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Run scan | `cli.py` | `stock_scan` (alias: `scan`), supports `--output` for JSON results (default: `output/cli_scans/`) |
| Run watchlist | `cli.py` | `watchlist_run` (alias: `monitor`), supports `--strategies` and `--days-back` |
| Run task file | `cli.py` | `task_run` (alias: `tasks`) |
| Output logic | See below | CLI vs Web UI default paths differ; see OUTPUT LOGIC section |
| Lookback calc | `config/lookback.py` | Shared `compute_days_back()`, used by CLI + Web + Orchestrator |
| Config loading | `config/loader.py` | `ConfigLoader.get_tushare_token()`, `get_yfinance_config()` |
| Sector cache | `data/sector_cache.py` | `SectorCache.refresh_all()` |
| Indicator composition | `indicators/composer.py` | Chain multiple indicators |
| Composite strategies | `strategies/composite.py` | `mode="any"` or `"all"` |
| Indicator creation | `indicators/factory.py` | `IndicatorFactory.create("KDJ")` merges config with defaults |
| Indicator discovery | `web/api/library.py` | `get_library_indicators()` discovers indicators from standard/custom packages |
| Indicator params | `config/indicators.yaml` | Per-indicator parameter overrides |
| Web UI - library | `web/api/library.py` | Strategy + indicator catalog API |
| Web UI - library tab | `web/static/app.ts` | Library panel rendering + param editor |
| Task orchestration | `orchestration/app.py` | Parses `tasks_*.yaml` |
| Web UI - watchlists | `web/api/watchlists.py` | CRUD + search + inline delete |
| Web UI - tasks | `web/api/tasks.py` | Multi-file task CRUD |
| Web UI - task-files | `web/api/tasks.py` | List/create/delete task config files |
| Web UI - config | `web/api/config.py` | GET (read) + PUT (write) system config |
| Web UI - settings | `web/static/app.ts` | Settings form logic, token toggle/copy |
| Execution engine | `execution/executor.py` | Batch yFinance fetch with chunking; sequential A-share; loads config via `ConfigLoader` |
| Alerts | `execution/alerts/base.py` | Abstract `AlertChannel` (reserved, not actively used) |
| Report generation | `reports/markdown.py` | Per-task + combined Markdown reports |
| Runs API | `web/api/runs.py` | Run history CRUD, preflight check, SSE logs, indicator data, files, open-folder |
| Runs engine | `web/engine/run_engine.py` | stock_scan (indicator output), watchlist_run, task_run |
| Run history | `web/engine/run_history.py` | SQLite persistence for execution history |

## CONVENTIONS

- **Build**: `pip install -e .`, setuptools with `src/` layout
- **Linting**: ruff, line-length 100, py310 target, rules: E,F,I,N,W
- **Tests**: pytest, `testpaths=["tests"]`, `@pytest.mark.integration` for network tests
  - Data layer: 80 unit + 17 integration (sector cache) = 97 tests
  - Indicator layer: 112 unit + 14 integration (TDX reference values) = 126 tests
  - Config layer: 30 unit + 1 sanity (production config parsing) = 31 tests
  - Orchestration layer: 35 unit + 11 integration (discovery, Orchestrator flow) = 46 tests
  - Reports layer: 18 unit = 18 tests
  - CLI layer: 16 unit + 8 integration (command routing) + 3 integration (TDX reference values) + 4 skipped (pending) = 27 tests
  - Web layer: 209 tests (42 unit + 26 integration + 4 contract + 137 E2E)
  - Run: `pytest tests/` or `pytest tests/ -m "not integration"` to skip network tests
  - See `tests/web/TEST_MATRIX.md` for Execution → API test coverage details
  - CLI reference values: BYD (002594.SZ) 2026-04-01 KDJ validation vs TongDaXin (error <0.02%)
  - CLI TODO tests: watchlist_run/task_run expected signal counts (marked @pytest.mark.skip in test_cli.py)
- **CLI entry**: `python -m quantflow.cli`, also `quantflow-scan` / `quantflow-monitor` scripts
- **Type hints**: `py.typed` marker present, ruff linting enforces
- **Lookback**: `config/lookback.py` provides shared `compute_days_back()` used by CLI + Web + Orchestrator. Data fetch days = `max(lookback_bars) * calendar_multiplier + buffer_days`
- **YFinance batch**: Auto-chunked (50 tickers/chunk, jitter sleep 5–12s) via `fetch_batch_ohlcv()` to avoid Yahoo rate limits
- **YAML**: Use `sort_keys=False` and `default_flow_style=False` when emitting YAML configuration

## ANTI-PATTERNS

- Do NOT add dependencies without updating `pyproject.toml`
- Do NOT bypass `DataSourceFactory` - it handles primary/fallback logic
- Do NOT hardcode `adjustflag` - use config defaults (`qfq`)
- Do NOT mix BaoStock format (`sh.600000`) with standard format (`600000.SH`)

## OUTPUT LOGIC

### Overview

CLI and Web UI use **different default output paths** and **delete strategies**.

### CLI Default Paths

| Run Type | Default Path | Path Type | Output Files |
|----------|--------------|-----------|--------------|
| **stock_scan** | `PROJECT_ROOT/output/cli_scans` | Absolute (PROJECT_ROOT) | `{code}_indicators.json` |
| **watchlist_run** | `./output` | Relative | `{watchlist_name}_results.json`<br>`{watchlist_name}_report.md` |
| **task_run** | `./output` | Relative | `{task_name}.json`<br>`{task_name}.md`<br>`Daily_Report.md`<br>`Combined_Results.json` |

### Web UI Default Paths

| Run Type | Default Path | Path Type | Output Files |
|----------|--------------|-----------|--------------|
| **stock_scan** | `./output/manual_scans` | Relative | `{code}_indicators.json` |
| **watchlist_run** | `./output/manual_watchlist` | Relative | `web-{wl_name}.json`<br>`web-{wl_name}.md` |
| **task_run** | `./output` | Relative | Same as CLI |

**Key Differences:**
- CLI stock_scan uses `PROJECT_ROOT` (absolute), Web uses relative `./output/manual_scans`
- Web UI adds `manual_` prefix to distinguish from CLI runs
- Web watchlist_run uses `web-{wl_name}` prefix (Windows-safe, no colons)

### Delete Behavior

**Unified Strategy (All Run Types):**

Web UI uses **precise file deletion** - only deletes generated files, preserves directory and user files.

| Run Type | Deleted Files | Preserved |
|----------|---------------|-----------|
| **stock_scan** | `{code}_indicators.json` | Directory + user files |
| **watchlist_run** | `web-{wl_name}.json`<br>`web-{wl_name}.md` | Directory + user files |
| **task_run** | `Daily_Report.md`<br>`Combined_Results.json`<br>`{task_name}.md/.json` | Directory + user files |

**Safety Guarantee:** Never deletes entire directory to prevent accidental loss of user files.

### User Responsibility

- **Output isolation**: Users control via different `output_path` values
- **Preset system**: Save different output configurations for reuse
- **RunHistory**: Database tracks all runs regardless of output_path

### Implementation Details

- **stock_scan**: File name from `run.config.code` (safe_code replacement)
- **watchlist_run**: File name from `wl.name` (loaded from YAML, not file stem!)
- **task_run**: File names from `task_config` task_names

**Critical Note:** watchlist_run deletion must load YAML to get `wl.name` field, not use `Path(file).stem` (see runs.py:272-283).

## COMMANDS

```bash
# Install
pip install -e .

# Install dev deps
pip install -e ".[dev]"

# Run tests
pytest tests/
pytest tests/ -m "not integration"  # skip network tests
pytest tests/ --cov=quantflow        # coverage

# Frontend unit tests (Vitest)
cd tests/web/frontend && npm install  # install deps
cd tests/web/frontend && npm test     # run tests

# Lint
ruff check src/

# Start Web UI
python -m quantflow.cli web
```

## WEB UI
- **Path**: `src/quantflow/web/`
- **Endpoints**: 
  - `/api/watchlists/...` (CRUD)
  - `/api/tasks/...` (CRUD, multi-file)
  - `/api/task-files/...` (list/create/delete)
  - `/api/config` (GET + PUT system config)
  - `/api/strategies` (read-only)
  - `/api/library/*` (library catalog: strategies + indicators + param updates)
  - `/api/runs/` (GET list, POST create, DELETE, SSE logs, indicator data, files, cancel, queue, open-folder)
  - `/api/presets/` (GET, POST, PUT, DELETE, run from preset)
  - `/api/browse/` (directory browsing for file picker, mkdir)
- **Static files**: `src/quantflow/web/static/` (TypeScript compiled to `.js`)
- **Frontend tests**: `tests/web/frontend/` (Vitest unit tests for pure functions in `utils.ts`)
- **Config**: `config/quantflow.yaml` → `web: { port, host }`, `tushare: { token }`, `lookback: { ... }`, `yfinance: { batch: { ... } }`

## NOTES

- `backtest/` and `risk/` are reserved, currently empty stubs
- Sector data: SW (申万) works fully, THS has list-only API, EM blocked by network
- Tushare requires token: env `TUSHARE_TOKEN`, `.env` file, or `config/quantflow.yaml`
- YFinance has rate limits (60/min, 360/hr, 8000/day) + anti-scraping; uses `curl_cffi` for TLS fingerprint; batch auto-chunks via `yfinance.batch` config (jitter sleep)
