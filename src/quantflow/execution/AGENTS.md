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

- `Executor`: Main class. Method `execute(job)` processes all items in the job. Uses `job.days_back` (computed by orchestrator) for data fetch range.
  - **Progress Logging**: Emits `Processing [x/y]: ...` for visibility.
  - **Enrichment**: Extracts `matched_*_strategies` lists for report grouping and passes `name` from `WatchlistItem`.

- `ExecutionJob`: Dataclass containing list of stocks, strategies, config, and `days_back`.

- `Storage`: Handles saving `ExecutionResultItem` to JSON.
  - `ExecutionResultItem`: Now includes `name`, `matched_buy_strategies`, and `matched_sell_strategies` to support Markdown report grouping and resonance analysis.

## CONVENTIONS

- Executor is stateless regarding strategy logic; it only orchestrates the pipeline.
- Strategies must be fully instantiated before passing to the Job.