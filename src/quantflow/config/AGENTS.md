# Configuration and logging

- `loader.py` reads `config/quantflow.yaml` by default and caches the parsed mapping per
  `ConfigLoader` instance. A missing file uses built-in defaults. An existing empty
  file yields an empty mapping, and getters supply their own defaults where defined.
- `get_tushare_token()` checks the process environment before YAML. A local `.env` file
  needs to be sourced by the shell or loaded by the caller. Keep actual tokens out of
  samples, tests and logs.
- Provider getters pass options to the factory. A-share defaults to BaoStock and the
  configured Tushare fallback. HK, US, JP and KR default to YahooQuery with YFinance fallback.
- `compute_days_back()` uses an explicit override first. Otherwise, it applies
  `ceil(max(lookback_bars) × calendar_multiplier) + buffer_days`. An empty
  strategy collection defaults to 365 days. The result is a calendar-day window.
  Share this path across CLI, Web and orchestration.
- `setup_logging()` replaces its earlier handlers before adding the current console
  and optional file handler. The run log lives under that run's `logs/` directory.
  Web persists its resolved location in RunHistory.
- Exercise changes with `python -m pytest tests/config tests/orchestration`.
