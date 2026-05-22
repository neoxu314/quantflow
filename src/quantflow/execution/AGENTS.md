# EXECUTION - QUANTFLOW

**Scope:** `src/quantflow/execution/`

## OVERVIEW

Execution layer for processing strategy jobs. Accepts `ExecutionJob` objects, fetches data, calculates indicators, runs strategies, and persists results.

## STRUCTURE

```
execution/
├── executor.py        # Executor - core processing logic
├── job.py             # ExecutionJob - input data model
├── storage.py         # Storage - JSON persistence
├── watchlist.py       # Watchlist management
└── alerts/
    └── base.py        # Alert interfaces
```

## KEY CLASSES

- `Executor`: Main class. Loads `ConfigLoader` at init, partitions items into batch (non-A-share) and sequential (A-share) groups. `execute(job)` order:
  1. Partition items by primary data source batch support: `batch_items` (non-A-share, e.g. US/HK/JP/KR via YahooQuery/YFinance) vs `sequential_items` (A-share via BaoStock/Tushare).
  2. Batch items → `fetch_batch_ohlcv()` (YahooQuery sequential per-ticker internally, or YFinance chunked download as fallback).
  3. Batch signals processed in-memory.
  4. Sequential items (A-share) → individual `fetch_ohlcv()` calls with primary/fallback (BaoStock → Tushare).
  - **Progress Logging**: Via optional `on_progress` callback emitting `ProgressEvent` objects (`type="stock_start"|"stock_done"`, with `current`, `total`, `code`, `message`, `level`). Used by Web UI RunEngine for SSE real-time updates.
  - **Summary Logging**: At end of `execute()`, logs task summary: `Task {name} complete: {total} stocks | {data_ok} analyzed, {no_data} no data, {errors} errors | {len(results)} with signals`.
  - **Helper**: `_process_single()` for indicator + signal generation per stock.
  - **Enrichment**: Extracts `matched_*_strategies` lists and passes `name` from `WatchlistItem`.

- `ExecutionJob`: Dataclass containing list of stocks, strategies, config, and `days_back`.

- `Storage`: Handles saving `ExecutionResultItem` to JSON.
  - `ExecutionResultItem`: Now includes `name`, `matched_buy_strategies`, and `matched_sell_strategies` to support Markdown report grouping and resonance analysis.

## CONVENTIONS

- Executor is stateless regarding strategy logic; it only orchestrates the pipeline.
- Strategies must be fully instantiated before passing to the Job.