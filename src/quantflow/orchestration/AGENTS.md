# ORCHESTRATION - QUANTFLOW

**Scope:** `src/quantflow/orchestration/`

## OVERVIEW

The brain of the monitoring system. Determines **what** to run (watchlists), **when** to run it (CRON/Cli), and **how** (strategies). It delegates execution to the `Execution Layer`.

## STRUCTURE

```
orchestration/
├── app.py           # Orchestrator - loops through tasks and dispatches jobs
├── registry.py      # Strategy Registry - maps string names to Strategy objects
├── loader.py        # TaskConfig loader - parses `tasks_*.yaml`
└── __init__.py
```

## KEY CLASSES

- `Orchestrator`: Loads YAML, resolves strategies, computes `days_back` from lookbacks, dispatches jobs, and aggregates results for combined reporting.
- `_compute_days_back()`: Calculates calendar days = `max(lookback_bars) * calendar_multiplier + buffer_days`.
- `_resolve_task_dir()` / `_resolve_combined_dir()`: Returns path with or without date suffix based on CLI `--daily`.
- `STRATEGY_REGISTRY`: Centralized dictionary mapping `"daily_bull_oversold"` to class.

## DEPENDENCIES

- Reads `config/tasks_*.yaml` to determine execution parameters. Optional `days_back` field can override auto-computed value.
- Calls `Executor.execute(job)` from the Execution Layer.
- Uses `MarkdownReporter` to generate both per-task and combined reports.
- Uses `Storage` to save `Combined_Results.json`.