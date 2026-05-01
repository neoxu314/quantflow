# DATA ADAPTERS - QUANTFLOW

**Scope:** `src/quantflow/data/adapters/`

## OVERVIEW

Individual data source implementations, each extending `DataSourceBase`. 4 adapters: BaoStock, Tushare, YFinance, AKShare.

## ADAPTERS

| Adapter | File | Markets | Auth | Key Methods |
|---------|------|---------|------|-------------|
| BaoStock | `baostock.py` | A-share CN | None | `login()`, `query()`, `logout()` |
| Tushare | `tushare.py` | A-share CN | Token required | `pro_api()`, `daily()` |
| YFinance | `yfinance.py` | Global (HK/US/JP/KR) | None | `Ticker()`, `history()` |
| AKShare | `akshare.py` | Sectors (EM/THS/SW) | None | `get_industry_list()`, `get_industry_constituents()` |

## CONVENTIONS

- **Common interface**: All implement `fetch_ohlcv(code, start, end, period, adjust)` → `DataFrame`
- **Inheritance**: BaoStock/Tushare/YFinance → `DataSourceBase`; AKShare → `DataSourceBase + SectorDataSource`
- **StockCode conversion**: Each adapter converts to its native format internally
- **Error handling**: Network errors wrapped, retry decorator applied

## YFINANCE SPECIAL

- Rate limits: 60/min, 360/hr, 8000/day
- Uses `curl_cffi` for Chrome TLS fingerprint bypass
- Hong Kong: `hk` prefix handling, USD conversion needed for `total_mv`
- Fundamental data: `pe_ttm`, `pb`, `total_mv` (ps_ttm not available)

## ANTI-PATTERNS

- Do NOT instantiate adapters directly - use `DataSourceFactory`
- Do NOT hardcode API credentials - use env vars or config
- Do NOT skip retry logic on network calls
