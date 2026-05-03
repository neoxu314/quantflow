# QUANTFLOW PROJECT KNOWLEDGE

**Generated:** 2026-04-25 / Updated: 2026-05-03
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
│   │   ├── library.py        # Library API endpoints
│   ├── strategies/      # Buy/sell strategies
│   ├── execution/       # Execution layer (formerly monitoring)
│   ├── orchestration/   # Task orchestration layer
│   ├── config/          # YAML loader + defaults
│   ├── backtest/        # Reserved - stub (__init__.py only)
│   ├── risk/            # Reserved - stub (__init__.py only)
│   ├── web/             # Web UI server (FastAPI + frontend)
│   ├── reports/         # Markdown report generation
│   └── cli.py           # Entry: `python -m quantflow.cli` (scan, monitor, tasks, web)
├── config/tasks_*.yaml  # Orchestration task configs (tasks_asia_mac.yaml, tasks_us_mac.yaml, etc.)
├── config/indicators.yaml  # Indicator parameter defaults
├── scripts/              # Build verification utilities
...
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Run scan | `cli.py` | `scan`, `monitor`, or `tasks` subcommands |
| Config loading | `config/loader.py` | `ConfigLoader.get_tushare_token()`, `get_yfinance_config()` |
| Sector cache | `data/sector_cache.py` | `SectorCache.refresh_all()` |
| Indicator composition | `indicators/composer.py` | Chain multiple indicators |
| Composite strategies | `strategies/composite.py` | `mode="any"` or `"all"` |
| Indicator creation | `indicators/factory.py` | `IndicatorFactory.create("KDJ")` merges config with defaults |
| Indicator discovery | `orchestration/discovery.py` | `discover_indicators()` returns metadata |
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
| Alerts | `execution/alerts/base.py` | Abstract `AlertChannel` |
| Report generation | `reports/markdown.py` | Per-task + combined Markdown reports |

## CONVENTIONS

- **Build**: `pip install -e .`, setuptools with `src/` layout
- **Linting**: ruff, line-length 100, py310 target, rules: E,F,I,N,W
- **Tests**: pytest, `testpaths=["tests"]`, `@pytest.mark.integration` for network tests
- **CLI entry**: `python -m quantflow.cli`, also `quantflow-scan` / `quantflow-monitor` scripts
- **Type hints**: `py.typed` marker present, ruff linting enforces
- **Lookback**: Data fetch days derived from indicator `lookback_bars` → aggregated by strategy → max computed in orchestration, multiplied by `calendar_multiplier` + `buffer_days` from `config/quantflow.yaml`
- **YFinance batch**: Auto-chunked (50 tickers/chunk, jitter sleep 5–12s) via `fetch_batch_ohlcv()` to avoid Yahoo rate limits
- **YAML**: Use `sort_keys=False` and `default_flow_style=False` when emitting YAML configuration

## ANTI-PATTERNS

- Do NOT add dependencies without updating `pyproject.toml`
- Do NOT bypass `DataSourceFactory` - it handles primary/fallback logic
- Do NOT hardcode `adjustflag` - use config defaults (`qfq`)
- Do NOT mix BaoStock format (`sh.600000`) with standard format (`600000.SH`)

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
- **Static files**: `src/quantflow/web/static/` (TypeScript compiled to `.js`)
- **Frontend tests**: `tests/web/frontend/` (Vitest unit tests for pure functions in `utils.ts`)
- **Config**: `config/quantflow.yaml` → `web: { port, host }`, `tushare: { token }`, `lookback: { ... }`, `yfinance: { batch: { ... } }`

## NOTES

- `backtest/` and `risk/` are reserved, currently empty stubs
- Sector data: SW (申万) works fully, THS has list-only API, EM blocked by network
- Tushare requires token: env `TUSHARE_TOKEN`, `.env` file, or `config/quantflow.yaml`
- YFinance has rate limits (60/min, 360/hr, 8000/day) + anti-scraping; uses `curl_cffi` for TLS fingerprint; batch auto-chunks via `yfinance.batch` config (jitter sleep)
