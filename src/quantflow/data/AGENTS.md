# DATA LAYER - QUANTFLOW

**Scope:** `src/quantflow/data/`

## OVERVIEW

Multi-source data fetching with primary/fallback orchestration. BaoStock (A-share), Tushare (A-share), YFinance (global), AKShare (sectors), and Wikipedia (Index Constituents).

## STRUCTURE

```
data/
├── base.py           # StockCode, DataSourceBase, SectorDataSource, FundamentalData
├── factory.py        # DataSourceFactory - primary/fallback selection
├── config.py         # MarketDataSourceConfig
├── fetch_indices.py  # Fetches S&P 500, Nasdaq, DJIA from Wikipedia -> generates watchlists
├── sector_cache.py   # SectorCache - JSON cache management
├── adapters/
│   ├── baostock.py   # BaoStock adapter (adjustflag="2" for qfq)
│   ├── tushare.py    # Tushare adapter (requires token)
│   ├── yfinance.py   # YFinance adapter (rate-limited, curl_cffi)
│   └── akshare.py    # AKShare adapter (sector classification)
└── __init__.py
```

## WHERE TO LOOK

| Task | Location | Key Classes/Methods |
|------|----------|---------------------|
| Fetch OHLCV | `factory.py` | `DataSourceFactory.fetch_ohlcv()` single stock, `fetch_batch_ohlcv()` yFinance batch |
| Fetch fundamental | `factory.py` | `DataSourceFactory.fetch_fundamental()` |
| Generate Watchlists | `fetch_indices.py` | `fetch_and_save()` - Downloads index components (S&P500, Nasdaq100) |
| BaoStock adapter | `adapters/baostock.py` | `BaoStockDataSource` - `adjust_map = {"qfq": "2", "hfq": "1", "none": "3"}` |
| YFinance adapter | `adapters/yfinance.py` | `YFinanceDataSource` - handles `hk` prefix, **batch fetch with chunking** (chunk_size=30, sleep=15s) |
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

| Difference | BaoStock | Tushare | YFinance |
|---|---|---|---|
| **复权** | Static forward (静态前复权) | Dynamic forward | Market-specific |
| **Volume unit** | Shares (股) | Lots (手=100股) | Shares |
| **Adjust flag** | `"2"` for qfq | API default | `qfq`/`hfq`/`none` |

## NOTES

- Sector constituents: SW works fully, THS list-only, EM blocked by network
- YFinance: 60 req/min rate limit, **batch fetch uses chunking** (30 tickers/batch, 15s sleep) configured in `quantflow.yaml`
- Tushare: Token required - `TUSHARE_TOKEN` env var or config file
- `DataSourceFactory` accepts `yfinance_config` dict to pass chunk size/sleep to adapter
- `fetch_indices.py` uses `pandas.read_html` and handles User-Agent rotation to bypass 403 errors from Wikipedia.
