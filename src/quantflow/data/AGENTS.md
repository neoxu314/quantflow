# DATA LAYER - QUANTFLOW

**Scope:** `src/quantflow/data/`

## OVERVIEW

Multi-source data fetching with primary/fallback orchestration. BaoStock (A-share), Tushare (A-share), YFinance (global), YahooQuery (global), AKShare (sectors), and Wikipedia (Index Constituents).

## STRUCTURE

```
data/
├── base.py           # StockCode, DataSourceBase, SectorDataSource, FundamentalData
├── factory.py        # DataSourceFactory - primary/fallback selection
├── config.py         # MarketDataSourceConfig
├── fetch_indices.py  # Fetches S&P 500, Nasdaq, DJIA from Wikipedia -> generates watchlists
├── fetch_cn_indices.py  # Fetches HS 300, CSI 500, ChiNext from akshare -> generates watchlists
├── sector_cache.py   # SectorCache - JSON cache management
├── adapters/
│   ├── baostock.py   # BaoStock adapter (adjustflag="2" for qfq)
│   ├── tushare.py    # Tushare adapter (requires token)
│   ├── yfinance.py   # YFinance adapter (rate-limited, curl_cffi)
│   ├── yahooquery.py # YahooQuery adapter (sequential per-ticker, with retry)
│   └── akshare.py    # AKShare adapter (sector classification)
└── __init__.py
```

## WHERE TO LOOK

| Task | Location | Key Classes/Methods |
|------|----------|---------------------|
| Fetch OHLCV | `factory.py` | `DataSourceFactory.fetch_ohlcv()` single stock, `fetch_batch_ohlcv()` generic batch with fallback |
| Fetch fundamental | `factory.py` | `DataSourceFactory.fetch_fundamental()` |
| Generate Watchlists | `fetch_indices.py` | `fetch_and_save()` - Downloads index components (S&P500, Nasdaq100) |
| Generate CN Watchlists | `fetch_cn_indices.py` | `fetch_cn_index()` - Downloads CSI 500 & ChiNext constituents |
| BaoStock adapter | `adapters/baostock.py` | `BaoStockDataSource` - `adjust_map = {"qfq": "2", "hfq": "1", "none": "3"}` |
| YFinance adapter | `adapters/yfinance.py` | `YFinanceDataSource` - handles `hk` prefix, **batch fetch with chunking** (chunk_size=35, jitter sleep 10–20s) |
| YahooQuery adapter | `adapters/yahooquery.py` | `YahooQueryDataSource` - `asynchronous=False` sequential per-ticker fetch with retry, `_fetch_single_with_retry()` (_MAX_RETRIES=5) |
| Tushare adapter | `adapters/tushare.py` | `TushareDataSource` - token required, `daily()` API |
| AKShare adapter | `adapters/akshare.py` | `AKShareDataSource` - `get_industry_list()`, `get_industry_constituents()` |
| Sector classification | `adapters/akshare.py` | `SectorClassification` enum: em, ths, sw_l1, sw_l2, sw_l3 |

## CONVENTIONS

- **StockCode**: Abstracts code format. `StockCode.from_standard("600000.SH")` → internally converts to BaoStock `sh.600000`
- **Adapter pattern**: All adapters inherit `DataSourceBase(ABC)` with `fetch_ohlcv()`, `get_name()`, `supports_market()`
- **Retry**: Decorator `@retry(max_retries=3)` on network-critical methods
- **Format**: BaoStock uses `sh.600000`, all others use `600000.SH` - adapters handle conversion
- **Watchlist Format**: Generated YAMLs follow `{name, description, items: [{code, name, tags}]}` schema.

## ANTI-PATTERNS

- Do NOT bypass `DataSourceFactory` - it orchestrates primary/fallback logic
- Do NOT hardcode stock code format - always use `StockCode` abstraction
- Do NOT mix BaoStock format with standard format in the same call
- Do NOT add new adapters without registering in factory's `_source_map`

## DATA SOURCE DIFFERENCES

| Difference | BaoStock | Tushare | YFinance | YahooQuery |
|---|---|---|---|---|
| **复权** | Static forward (静态前复权) | Dynamic forward | Market-specific | `adj_ohlc=True` for qfq |
| **Volume unit** | Shares (股) | Lots (手=100股) | Shares | Shares |
| **Adjust flag** | `"2"` for qfq | API default | `qfq`/`hfq`/`none` | `adj_ohlc` param |

## YFINANCE SPECIAL

- Rate limits: 60/min, 360/hr, 8000/day. **Batch fetch auto-chunks to 35/ticker** (down from 50) with jittered sleep 10-20s to avoid 429.
- `YFinanceDataSource.__init__(chunk_size, sleep_min, sleep_max, retry_max_attempts, retry_base_delay, cooldown_base, recovery_max_passes, recovery_chunk_size)` — values passed from `DataSourceFactory` via `yfinance_config`.
- **Retry mechanism**: On YFRateLimitError (empty DataFrame), retries up to `retry_max_attempts` (default 3) with exponential backoff: `base_delay * 2^(attempt-1)` (30s, 60s, 120s). Three additional recovery layers:
  1. **Adaptive cooling** — exponential cooldown between chunks when rate-limited
  2. **Chunk sub-division** — failed chunks split into ≤10-ticker sub-chunks and retried
  3. **Global recovery pass** — all missed tickers retried up to 3 passes after main loop
- **Enhanced logging**: Per-symbol success/failure logging, SSL compatibility warnings for LibreSSL users.
- **SSL compatibility**: LibreSSL 2.8.3 incompatible with urllib3 v2. This causes `TypeError("'NoneType' object is not subscriptable")` and `OperationalError('unable to open database file')` in yfinance batch downloads. **Fix**: use Homebrew Python (linked with OpenSSL) in a venv: `brew install python@3.12 && /opt/homebrew/bin/python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .`
- `fetch_batch_ohlcv(codes, ...)` uses `yf.download(tickers, group_by='ticker', threads=True, timeout=30)` with retry wrapper.

## TESTS

| Category | Test File(s) | Test Count | Type |
|----------|--------------|------------|------|
| Base classes | `test_base.py` | 15 | Unit (StockCode, FundamentalData, DataSourceBase/SectorDataSource contracts) |
| Factory | `test_factory.py` | 19 | Unit (source routing, batch OHLCV, fundamental, fallback, market detection) |
| Config | `test_factory.py` | — | Indirect (via factory tests) |
| BaoStock adapter | `test_baostock.py` | 3 | Unit |
| YFinance batch | `test_yfinance_batch.py` | 16 | Unit (chunking, version check, jitter, adaptive cooling, recovery) |
| YahooQuery | `test_yahooquery.py` | 30 | Unit (basic, symbol mapping, normalize single, batch, single fetch, fundamental, jitter, retry) |
| AKShare adapter | `test_akshare.py` | 27 | Unit (sector classification, industry/concept, constituents, HK OHLCV) |
| fetch_indices | `test_fetch_indices.py` | 26 | Unit (clean_ticker, INDICES structure, YAML output) + 3 Integration (mocked HTTP) |
| fetch_cn_indices | `test_fetch_cn_indices.py` | 14 | Unit (convert_cn_code, CN_INDICES structure, fetch_cn_index with mock) |
| Sector cache | `test_sector_data.py` | 17 | Integration (EM/THS/SW sector lists, constituents, cache I/O) |
| Data fetch (real data) | `test_data_fetch.py` | 24 | Integration (BaoStock/Tushare/YFinance/YahooQuery against known reference values) |

**Total: 186 unit + 10 integration = 196 tests**

Run: `pytest tests/data/ -m "not integration"` for unit, `-m integration` for network tests.

## NOTES

- Sector constituents: SW works fully, THS list-only, EM blocked by network
- YFinance: 60 req/min rate limit, **batch fetch uses chunking** (35 tickers/batch, jitter sleep 10–20s) configured in `quantflow.yaml`
- YahooQuery: Sequential per-ticker fetch (`asynchronous=False`) with retry (`_MAX_RETRIES=5`, `_RETRY_DELAY=3.0s`); async concurrent mode triggers Yahoo anti-scraping (HTTP 404) for >4 tickers; monkey-patches `_historical_data_to_dataframe` for error dict handling; less reliable than yfinance for batch data, serves as primary with yfinance fallback
- Tushare: Token required - `TUSHARE_TOKEN` env var or config file
- `DataSourceFactory` accepts `yfinance_config` and `yahooquery_config` dicts to pass adapter parameters
- `fetch_indices.py` uses `pandas.read_html` and handles User-Agent rotation to bypass 403 errors from Wikipedia.
