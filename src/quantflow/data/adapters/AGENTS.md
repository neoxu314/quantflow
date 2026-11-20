# Provider adapters

Implement `DataSourceBase` and register new providers in `DataSourceFactory.ADAPTER_MAP`.
Convert symbols, inclusive dates and fields at this boundary. Keep network errors and partial
results visible to the factory. The
[data contracts](../../../../docs/reliability-and-data-contracts.md) define normalized output.

| Provider | Current role |
| --- | --- |
| BaoStock | A-share daily prices. Maps qfq/hfq/none to flags 2/1/3. |
| Tushare | A-share daily prices and fundamental data with a token. Applies adjustment factors and converts lots to shares. |
| YFinance | Yahoo daily prices and selected fundamentals. Uses configured download chunks, bounded retry, cooldown and missed-symbol recovery. |
| YahooQuery | Yahoo daily prices and selected fundamentals. Fetches batch symbols sequentially, with up to five attempts and a three-second retry delay. |
| AKShare | Sector data and HK daily prices. Supported sector operations depend on the selected classification. |

- Yahoo accepts qfq and unadjusted requests. Provider adjustment semantics and upstream
  access can differ by market. HK uses `.HK`, JP uses `.T`, KR uses `.KS`, and US
  removes the project suffix when translating to Yahoo symbols.
- YFinance uses the values under `yfinance.batch` for chunking and delays. Empty or failed
  results may trigger cooling, smaller chunks or a bounded recovery pass. These settings
  control only local request behavior.
- YahooQuery uses synchronous per-symbol requests with configured inter-symbol delay.
  `chunk_size` and `max_workers` are accepted for compatibility with existing configuration.
  Preserve the historical-data conversion guard for provider error responses.
- Verify shared behavior with `python -m pytest tests/data`. Vendor behavior needs the
  separately enabled live-market suite.
