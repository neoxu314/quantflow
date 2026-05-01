# REPORTS - QUANTFLOW

**Scope:** `src/quantflow/reports/`

## OVERVIEW

The reporting layer transforms raw execution results (JSON) into human-readable Markdown reports. Triggered by the Orchestration layer after each task execution.

## STRUCTURE

```
reports/
├── base.py           # Reporter interface
├── markdown.py       # Markdown implementation
└── __init__.py
```

## KEY CLASSES

- `MarkdownReporter`: Generates per-task `.md` reports.
  - **Grouping Logic**: Uses `_group_by_strategy()` to split Buy/Sell signals into sub-tables based on which strategies triggered (e.g., "Oversold & MidRange Resonance").
  - **Enrichment**: Looks up stock names and tags from the `watchlist` to enhance reports.
  - `generate_combined()`: Aggregates `task_runs` into `Daily_Report.md` with global stats.

## REPORT STRUCTURE

1.  **Single Task Report**:
    *   Task Coverage -> Statistics -> **Signal Groups by Strategy Combination** -> Data Availability.
    *   Signal Groups are sorted by number of matching strategies (Resonance count).

2.  **Combined Report**:
    *   Daily Summary -> Task Sections -> **Signal Groups per Task**.

## DEPENDENCIES

- Receives results from `Executor.execute()` via `Orchestrator`.
- `Orchestrator` collects `task_runs` tuples: `(name, results, watchlist, strategies)`.
- Writes output: per-task to `_resolve_task_dir()`, combined to `_resolve_combined_dir()`.
