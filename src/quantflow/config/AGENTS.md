# CONFIG LAYER - QUANTFLOW

**Scope:** `src/quantflow/config/`

## OVERVIEW

Configuration loading and lookback computation. YAML-based config parsing with environment variable fallback, shared across all layers.

## STRUCTURE

```
config/
├── __init__.py       # Re-exports ConfigLoader
├── loader.py         # ConfigLoader - loads quantflow.yaml
└── lookback.py       # compute_days_back(), load_lookback_config()
```

## WHERE TO LOOK

| Task | Location | Key Classes/Methods |
|------|----------|---------------------|
| Load config | `loader.py` | `ConfigLoader.load()` |
| Get data config | `loader.py` | `ConfigLoader.get_data_config()` → `MarketDataSourceConfig` |
| Get Tushare token | `loader.py` | `ConfigLoader.get_tushare_token()` - env `TUSHARE_TOKEN` > config file |
| Get YFinance config | `loader.py` | `ConfigLoader.get_yfinance_config()` - batch chunking/sleep settings |
| Load lookback | `lookback.py` | `load_lookback_config()` - reads `lookback:` section from quantflow.yaml |
| Compute days | `lookback.py` | `compute_days_back(strategies, override)` - formula: `ceil(max_bars × multiplier) + buffer` |

## CONVENTIONS

- **Config path**: `config/quantflow.yaml` (relative to project root); env var `TUSHARE_TOKEN` overrides file
- **Lookback formula**: `actual_days = ceil(max(lookback_bars) × calendar_multiplier) + buffer_days`
- **Caching**: `ConfigLoader.load()` caches result in `_config`; subsequent calls return same dict object
- **Empty file**: Falls back to `_get_defaults()` which provides market defaults (cn→baostock, us→yfinance, etc.)

## ANTI-PATTERNS

- Do NOT bypass `ConfigLoader` for token/yfinance access — it handles env var priority and caching
- Do NOT hardcode lookback values — use `compute_days_back()` which respects config overrides
- Do NOT mix BaoStock format (`sh.600000`) with standard format (`600000.SH`) in config

## TESTS

| Category | Test File(s) | Test Count | Type |
|----------|--------------|------------|------|
| ConfigLoader init/load | `tests/config/test_config.py` | 7 | Unit (default/custom path, missing file, caching) |
| Market data config | `tests/config/test_config.py` | 3 | Unit (full config, defaults fallback, empty data section) |
| Tushare token | `tests/config/test_config.py` | 4 | Unit (env priority, yaml fallback, missing all) |
| YFinance config | `tests/config/test_config.py` | 3 | Unit (batch config, missing section, missing file) |
| Defaults | `tests/config/test_config.py` | 3 | Unit (structure, primary sources, cn fallback) |
| Lookback config | `tests/config/test_config.py` | 4 | Unit (missing file, with/without lookback, partial override) |
| compute_days_back | `tests/config/test_config.py` | 7 | Unit (override, empty, None, formula, max, custom, fractional) |
| Production sanity | `tests/config/test_config.py` | 1 | Sanity (quantflow.yaml exists and parses) |
| Integration | `tests/orchestration/test_orchestration.py` | 4 | Integration (real indicator instances with formula) |

Run: `pytest tests/config/ -v` for config unit tests, `pytest tests/orchestration/test_orchestration.py` for integration.

## CONSUMERS

| Consumer | Uses |
|----------|------|
| `execution/executor.py` | `ConfigLoader()`, `.get_yfinance_config()`, `.get_tushare_token()` |
| `orchestration/app.py` | `compute_days_back()` |
| `cli.py` | `load_lookback_config()`, `compute_days_back()` |
| `web/engine/run_engine.py` | `load_lookback_config()`, `compute_days_back()` |

## NOTES

- `ConfigLoader.get_tushare_token()` checks `os.environ["TUSHARE_TOKEN"]` first, then config file
- `MarketDataSourceConfig` (from `data/config.py`) is returned by `get_data_config()`
- `compute_days_back()` returns 365 when strategies is None or empty
