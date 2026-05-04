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

- `Executor`: Main class. Loads `ConfigLoader` at init, dispatches yFinance items to batch fetch, processes sequential items individually. `execute(job)` order:
  1. Partition items by primary data source.
  2. yFinance items → `fetch_batch_ohlcv()` (internal chunking: 50/batch, jitter sleep 5–12s to avoid 429).
  3. yFinance signals processed in-memory.
  4. Other items (A-share) → sequential `fetch_ohlcv()`.
  - **Progress Logging**: Via optional `on_progress` callback emitting `ProgressEvent` objects (`type="stock_start"|"stock_done"`, with `current`, `total`, `code`, `message`, `level`). Used by Web UI RunEngine for SSE real-time updates.
  - **Helper**: `_process_single()` for indicator + signal generation per stock.
  - **Enrichment**: Extracts `matched_*_strategies` lists and passes `name` from `WatchlistItem`.

- `ExecutionJob`: Dataclass containing list of stocks, strategies, config, and `days_back`.

- `Storage`: Handles saving `ExecutionResultItem` to JSON.
  - `ExecutionResultItem`: Now includes `name`, `matched_buy_strategies`, and `matched_sell_strategies` to support Markdown report grouping and resonance analysis.

## CONVENTIONS

- Executor is stateless regarding strategy logic; it only orchestrates the pipeline.
- Strategies must be fully instantiated before passing to the Job.