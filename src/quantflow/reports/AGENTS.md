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

## TESTS

| Category | Test File(s) | Tests | Type |
|----------|--------------|-------|------|
| Signal grouping | `tests/reports/test_reports.py` | 3 | Unit (resonance, single strategy, name fallback) |
| Combined reports | `tests/reports/test_reports.py` | 4 | Unit (multi-task, empty, single task, statistics aggregation) |
| Edge cases | `tests/reports/test_reports.py` | 3 | Unit (empty results, sell-only, auto-create output dir) |
| Group-by-strategy | `tests/reports/test_reports.py` | 3 | Unit (empty list, resonance sorting, sell grouping) |
| Helper methods | `tests/reports/test_reports.py` | 5 | Unit (format strategy name, count watched with/without length) |

Run: `pytest tests/reports/ -v` for all reports tests. All tests use `tmp_path` fixtures — zero production data dependency.
