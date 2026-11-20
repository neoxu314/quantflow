# Market data

- `base.py` defines `StockCode`, the adapter interfaces and the fundamental fact model.
  Use standard exchange suffixes at the public boundary, for example `600000.SH`,
  `AAPL.US`, `7203.T` and `005930.KS`. Adapters translate to provider symbols.
- `factory.py` routes by market and provider capability through `ADAPTER_MAP`.
  Single and batch requests enforce common validation, provenance and fallback. A fallback
  replaces a stock's whole window. Keep failed or inadequate requests distinguishable.
- Calendar helpers decide the last completed exchange session. Weekly/intraday
  calculation is outside the current execution contract. See
  [reliability and data contracts](../../../docs/reliability-and-data-contracts.md)
  for inclusive dates, coverage, provenance and adjustment.
- Tushare converts provider lots to shares. Prices and fundamental values retain
  currency and unit semantics documented in the contract.
- `fetch_indices.py` and `fetch_cn_indices.py` regenerate US and A-share index
  watchlists. See [watchlist maintenance](../../../docs/stock-watchlist.md).
  `sector_cache.py` maintains local sector data from AKShare.
- See [adapter notes](adapters/AGENTS.md) for source-specific implementation.
  Use `python -m pytest tests/data` offline and add `--live-market -m integration`
  to request providers separately.
