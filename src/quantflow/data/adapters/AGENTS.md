# DATA ADAPTERS - QUANTFLOW

**Scope:** `src/quantflow/data/adapters/`

## OVERVIEW

Individual data source implementations, each extending `DataSourceBase`. 4 adapters: BaoStock, Tushare, YFinance, AKShare.

## ADAPTERS

| Adapter | File | Markets | Auth | Key Methods |
|---------|------|---------|------|-------------|
| BaoStock | `baostock.py` | A-share CN | None | `login()`, `query()`, `logout()` |
| Tushare | `tushare.py` | A-share CN | Token required | `pro_api()`, `daily()` |
| YFinance | `yfinance.py` | Global (HK/US/JP/KR) | None | `fetch_ohlcv()`, `fetch_batch_ohlcv()` **(chunked)**, `check_version()` |
| AKShare | `akshare.py` | Sectors (EM/THS/SW) | None | `get_industry_list()`, `get_industry_constituents()` |

## CONVENTIONS

- **Common interface**: All implement `fetch_ohlcv(code, start, end, period, adjust)` → `DataFrame`
- **Inheritance**: BaoStock/Tushare/YFinance → `DataSourceBase`; AKShare → `DataSourceBase + SectorDataSource`
- **StockCode conversion**: Each adapter converts to its native format internally
- **Error handling**: Network errors wrapped, retry decorator applied

## YFINANCE SPECIAL

- Rate limits: 60/min, 360/hr, 8000/day. **Batch fetch auto-chunks to 35/ticker** with jittered sleep 10-20s to avoid 429.
- `YFinanceDataSource.__init__(chunk_size, sleep_min, sleep_max, retry_max_attempts, retry_base_delay)` — values passed from `DataSourceFactory` via `yfinance_config`.
- `fetch_batch_ohlcv(codes, ...)` uses `yf.download(tickers, group_by='ticker', threads=True, timeout=30)` with retry wrapper.
- Internal chunking: splits N tickers into batches of `chunk_size`, sleeps `random(sleep_min, sleep_max)` between batches.
- Returns `Dict[str, DataFrame]` with same column format as single-stock `fetch_ohlcv`.
- Uses `curl_cffi` for Chrome TLS fingerprint bypass
- **Market suffix mapping**: KR→.KS (Korean), JP→.T (Japanese), HK→.HK (Hong Kong), US→no suffix
- Hong Kong: `hk` prefix handling, USD conversion needed for `total_mv`
- Fundamental data: `pe_ttm`, `pb`, `total_mv` (ps_ttm not available)
- **Retry mechanism**: `_retry_with_backoff()` handles YFRateLimitError with exponential backoff (30s, 60s, 120s for 3 attempts)
- **Config parameters**: `retry_max_attempts` (default 3), `retry_base_delay` (default 30s)
- **SSL detection**: `_check_ssl_compatibility()` logs warning for LibreSSL users. **Fix**: use Homebrew Python (linked with OpenSSL) in a venv: `brew install python@3.12 && /opt/homebrew/bin/python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .`
- **Enhanced logging**: Detailed per-symbol failure logging with error classification

## ANTI-PATTERNS

- Do NOT instantiate adapters directly - use `DataSourceFactory`
- Do NOT hardcode API credentials - use env vars or config
- Do NOT skip retry logic on network calls
