# QUANTFLOW PROJECT KNOWLEDGE

**Generated:** 2026-04-25
**Scope:** `quantflow/` - Main quant analysis system

## OVERVIEW

Layered Python package: data fetching → indicator calculation → strategy signals → orchestration → execution.

## STRUCTURE

```
quantflow/
├── src/quantflow/
│   ├── data/            # Multi-source data layer
│   ├── indicators/      # Technical indicators
│   ├── strategies/      # Buy/sell strategies
│   ├── execution/       # Execution layer (formerly monitoring)
│   ├── orchestration/   # Task orchestration layer
│   ├── config/          # YAML loader + defaults
│   ├── backtest/        # Reserved - empty
│   ├── risk/            # Reserved - empty
│   └── cli.py           # Entry: `python -m quantflow.cli`
├── config/tasks.yaml    # Orchestration task config
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
| Task orchestration | `orchestration/app.py` | Parses `tasks.yaml` |
| Execution engine | `execution/executor.py` | Batch yFinance fetch with chunking; sequential A-share; loads config via `ConfigLoader` |
| Alerts | `execution/alerts/base.py` | Abstract `AlertChannel` |
...

## CONVENTIONS

- **Build**: `pip install -e .`, setuptools with `src/` layout
- **Linting**: ruff, line-length 100, py310 target, rules: E,F,I,N,W
- **Tests**: pytest, `testpaths=["tests"]`, `@pytest.mark.integration` for network tests
- **CLI entry**: `python -m quantflow.cli`, also `quantflow-scan` / `quantflow-monitor` scripts
- **Type hints**: `py.typed` marker present, ruff linting enforces
- **Lookback**: Data fetch days derived from indicator `lookback_bars` → aggregated by strategy → max computed in orchestration, multiplied by `calendar_multiplier` + `buffer_days` from `config/quantflow.yaml`
- **YFinance batch**: Auto-chunked (30 tickers/chunk, 15s sleep) via `fetch_batch_ohlcv()` to avoid Yahoo rate limits

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

# Lint
ruff check src/
```

## NOTES

- `backtest/` and `risk/` are reserved, currently empty stubs
- Sector data: SW (申万) works fully, THS has list-only API, EM blocked by network
- Tushare requires token: env `TUSHARE_TOKEN`, `.env` file, or `config/quantflow.yaml`
- YFinance has rate limits (60/min, 360/hr, 8000/day) + anti-scraping; uses `curl_cffi` for TLS fingerprint; batch auto-chunks via `yfinance.batch` config
