# DATA ADAPTERS - QUANTFLOW

**Scope:** `src/quantflow/data/adapters/`

## OVERVIEW

Individual data source implementations, each extending `DataSourceBase`. 5 adapters: BaoStock, Tushare, YFinance, YahooQuery, AKShare.

## ADAPTERS

| Adapter | File | Markets | Auth | Key Methods |
|---------|------|---------|------|-------------|
| BaoStock | `baostock.py` | A-share CN | None | `login()`, `query()`, `logout()` |
| Tushare | `tushare.py` | A-share CN | Token required | `pro_api()`, `daily()` |
| YFinance | `yfinance.py` | Global (HK/US/JP/KR) | None | `fetch_ohlcv()`, `fetch_batch_ohlcv()` **(chunked)**, `check_version()` |
| YahooQuery | `yahooquery.py` | Global (HK/US/JP/KR) | None | `fetch_ohlcv()`, `fetch_batch_ohlcv()` **(sequential)**, `fetch_fundamental()`, `_fetch_single_with_retry()` |
| AKShare | `akshare.py` | Sectors (EM/THS/SW) | None | `get_industry_list()`, `get_industry_constituents()` |

## CONVENTIONS

- **Common interface**: All implement `fetch_ohlcv(code, start, end, period, adjust)` → `DataFrame`
- **Inheritance**: BaoStock/Tushare/YFinance → `DataSourceBase`; AKShare → `DataSourceBase + SectorDataSource`
- **StockCode conversion**: Each adapter converts to its native format internally
- **Error handling**: Network errors wrapped, retry decorator applied

## YFINANCE SPECIAL

- Rate limits: 60/min, 360/hr, 8000/day. **Batch fetch auto-chunks to 35/ticker** with jittered sleep 10-20s to avoid 429.
- `YFinanceDataSource.__init__(chunk_size, sleep_min, sleep_max, retry_max_attempts, retry_base_delay, cooldown_base, recovery_max_passes, recovery_chunk_size)` — values passed from `DataSourceFactory` via `yfinance_config`.
- `fetch_batch_ohlcv(codes, ...)` uses `yf.download(tickers, group_by='ticker', threads=True, timeout=30)` with retry wrapper. Includes 3-layer rate-limit recovery:
  1. **Adaptive cooling**: Detects empty-DataFrame rate-limit signal, inserts exponential cooldown (60s base, 2x per consecutive limit) between chunks.
  2. **Chunk sub-division**: When a chunk fails entirely, splits tickers into ≤10-ticker sub-chunks for retry.
  3. **Global recovery pass**: After main loop, retries all missed tickers with conservative parameters (≤10/chunk, max 3 passes).
- Internal chunking: splits N tickers into batches of `chunk_size`, sleeps `random(sleep_min, sleep_max)` between batches.
- Returns `Dict[str, DataFrame]` with same column format as single-stock `fetch_ohlcv`.
- Uses `curl_cffi` for Chrome TLS fingerprint bypass
- **Market suffix mapping**: KR→.KS (Korean), JP→.T (Japanese), HK→.HK (Hong Kong), US→no suffix
- Hong Kong: `hk` prefix handling, USD conversion needed for `total_mv`
- Fundamental data: `pe_ttm`, `pb`, `total_mv` (ps_ttm not available)
- **Retry mechanism**: `_download_chunk()` retries empty results up to `retry_max_attempts` with exponential backoff (30s, 60s, 120s). `_retry_with_backoff()` handles YFRateLimitError separately for single-stock fetches.
- **Config parameters**: `retry_max_attempts` (default 3), `retry_base_delay` (default 30s), `cooldown_base` (default 60s), `recovery_max_passes` (default 3), `recovery_chunk_size` (default 10)
- **SSL detection**: `_check_ssl_compatibility()` logs warning for LibreSSL users. **Fix**: use Homebrew Python (linked with OpenSSL) in a venv: `brew install python@3.12 && /opt/homebrew/bin/python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .`
- **Log suppression**: `_suppress_yfinance_logs()` / `_restore_yfinance_logs()` temporarily elevate yfinance logger to CRITICAL during `yf.download()`, suppressing misleading internal errors (`possibly delisted`, `OperationalError`). Data is still retrieved successfully from the returned DataFrame.
- **Enhanced logging**: Detailed per-symbol failure logging with error classification

## YAHOOQUERY SPECIAL

- **Sequential batch mode**: Uses `asynchronous=False` (changed from `asynchronous=True`) — YahooQuery's async concurrent mode triggers Yahoo API anti-scraping (HTTP 404) for >4 concurrent tickers, causing 100% batch failure. Sequential per-ticker fetch avoids this.
- **Less reliable than yfinance for batch data**: YahooQuery serves as primary source with yfinance as fallback, but batch reliability is now lower due to per-ticker sequential fetch + Yahoo API instability.
- `YahooQueryDataSource.__init__(chunk_size, sleep_min, sleep_max, max_workers)` — values passed from `DataSourceFactory` via `yahooquery_config`. `max_workers` retained for API compat but unused in batch mode.
- `fetch_batch_ohlcv(codes, ...)` iterates tickers sequentially using `_fetch_single_with_retry()`. Each ticker fetched individually via `Ticker(code, asynchronous=False).history(period, interval)`.
- **Monkey-patch**: Applies `_historical_data_to_dataframe` monkey-patch to handle error dicts gracefully (prevents `KeyError` crash when YahooQuery returns `{'finance': {'error': ...}}` instead of expected data structure).
- **Retry mechanism**: `_fetch_single_with_retry()` retries failed single-ticker fetches up to `_MAX_RETRIES=5` with `_RETRY_DELAY=3.0` seconds between attempts.
- **Adjust handling**: `adj_ohlc=True` for qfq (uses `adjclose` instead of `close`).
- **Chunk strategy**: Default 100/chunk (configurable via `chunk_size`), with short jitter sleep 0.5-2s between chunks (no rate-limit concern).
- **Fundamental data**: Combines `key_stats` (PB, forwardPE) + `summary_detail` (marketCap, trailingPE) for PE/PB/MCap.
- **Market suffix mapping**: Same as yfinance — KR→.KS, JP→.T, HK→.HK, US→no suffix.
- **Removed methods**: `_fetch_chunk` (recursive chunk splitting) and `_normalize_multiindex` (MultiIndex normalization) removed — no longer needed with sequential single-ticker fetch.

## ANTI-PATTERNS

- Do NOT instantiate adapters directly - use `DataSourceFactory`
- Do NOT hardcode API credentials - use env vars or config
- Do NOT skip retry logic on network calls

## 2026-11-18 RELIABILITY CONTRACT

Project `docs/reliability-and-data-contracts.md` supersedes legacy output, adjustment and state details above. Outputs are run-owned manifest artifacts; analyzed/no-data/stale/insufficient/error are distinct. Tushare uses explicit factors and shares, Yahoo adapters reject hfq, and facts preserve units, source and time. Task summaries expose failures. API tests isolate runtime state and do not start unmanaged workers.
