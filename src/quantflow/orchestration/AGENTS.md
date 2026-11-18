# ORCHESTRATION - QUANTFLOW

**Scope:** `src/quantflow/orchestration/`

## OVERVIEW

The brain of the monitoring system. Determines **what** to run (watchlists), **when** to run it (CRON/Cli), and **how** (strategies). It delegates execution to the `Execution Layer`.

## STRUCTURE

```
orchestration/
├── app.py           # Orchestrator - loops through tasks and dispatches jobs
├── registry.py      # Strategy Registry - maps string names to Strategy objects
├── discovery.py     # Indicator discovery - introspects __all__ exports
├── loader.py        # TaskConfig loader - parses `tasks_*.yaml` (no output field)
└── __init__.py
```

## KEY CLASSES

- `Orchestrator`: Loads YAML, resolves strategies, computes `days_back` via `config.lookback`, dispatches jobs, and aggregates results for combined reporting. Returns total signal count from `.run()`. Logs overall summary at end: `All tasks complete: {completed}/{task_count} tasks, {total_stocks} stocks scanned, {total_signals} signals`.
- `TaskConfig`: Dataclass with `name`, `watchlist_path`, `strategy_names`, `days_back`. **NO output_dir field** (output controlled by CLI/Web `--output` parameter).
  - **Validation**: Rejects duplicate task names in same file with ValueError.
- `compute_days_back()` (shared): Located in `config/lookback.py`. Calculates calendar days = `max(lookback_bars) * calendar_multiplier + buffer_days`. Used by CLI, Web, and Orchestrator.
- `_resolve_task_dir()`: Returns output path. Uses `output_override` (from CLI/Web `--output`) or default `"./output"`. Date suffix added if `daily_mode=True`.
- `_resolve_combined_dir()`: Returns path for combined reports. Uses `output_override` or `"reports"` default.
- `STRATEGY_REGISTRY`: Centralized dictionary mapping `"daily_bull_oversold"` to class.
- `discover_indicators()`: Returns metadata (name, category, params, fields, lookback) for all indicators discovered from standard and custom package `__all__` exports. Used by the Web UI Library API.

## DEPENDENCIES

- Reads `config/tasks_*.yaml` to determine execution parameters. 
  - **Task YAML format**: `name`, `watchlist`, `strategies`, optional `days_back`. **NO output field**.
  - Output directory controlled by CLI/Web `--output` parameter (default: `./output`).
- Calls `Executor.execute(job)` from the Execution Layer.
- Uses `MarkdownReporter` to generate both per-task and combined reports.
- Uses `Storage` to save `Combined_Results.json` and per-task `{task_name}.json`.

## OUTPUT BEHAVIOR

**Task YAML (no output field)**:
```yaml
tasks:
- name: task_name
  watchlist: watchlists/file.yaml
  strategies: [strategy_id]
  # NO output field
```

**CLI/Web output control**:
- CLI: `--output ./custom_dir` (default: `./output`)
- Web: Output Directory field (default: `./output`)
- All tasks output to same directory, differentiated by filenames:
  - `{task_name}.md` (per-task Markdown)
  - `{task_name}.json` (per-task JSON from Executor)
  - `Daily_Report.md` (combined Markdown)
  - `Combined_Results.json` (combined JSON)

**Daily mode**:
- Output path: `{output_dir}/{YYYY-MM-DD}/`
- Date subdirectory auto-created, contains all output files.

## TESTS

| Category | Test File(s) | Tests | Type |
|----------|--------------|-------|------|
| Strategy registry | `tests/orchestration/test_registry.py` | 12 | Unit (lookup, invalid IDs, inheritance) |
| Task config loader | `tests/orchestration/test_task_config.py` | 10 | Unit (YAML parsing, duplicate name rejection, defaults) |
| Orchestrator flow | `tests/orchestration/test_orchestrator.py` | 15 | Integration (run loop, daily mode, task failure, output override) |
| Indicator discovery | `tests/orchestration/test_discovery.py` | 7 | Integration (standard + custom indicator metadata) |
| Lookback integration | `tests/orchestration/test_orchestration.py` | 4 | Integration (real indicator instances with formula) |

Run: `pytest tests/orchestration/ -v` for all orchestration tests.

## 2026-11-18 RELIABILITY CONTRACT

Project `docs/reliability-and-data-contracts.md` supersedes legacy output, adjustment and state details above. Outputs are run-owned manifest artifacts; analyzed/no-data/stale/insufficient/error are distinct. Tushare uses explicit factors and shares, Yahoo adapters reject hfq, and facts preserve units, source and time. Task summaries expose failures. API tests isolate runtime state and do not start unmanaged workers.
