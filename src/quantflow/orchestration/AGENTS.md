# Task orchestration

- `loader.py` reads task YAML as `TaskConfig` objects with `name`, `watchlist_path`,
  `strategy_names` and optional `days_back`. Names must be unique in the file.
  Task YAML has no output field. A relative watchlist path is first looked up beside
  the task file if it exists there.
- `registry.py` maps the four registered strategy IDs to implementations. Keep task
  validation and the Web Library consistent with this registry.
- `app.py` resolves strategies and lookback, sets a single market-data cutoff,
  dispatches execution jobs and aggregates task coverage. `Orchestrator.run()` returns
  the number of result items across tasks. One result item can contain several signals.
- Task Run writes each task's report, results, coverage and context under
  `tasks/<number>/`, using its one-based position in the frozen plan. The run root
  holds `Combined_Results.json`, `Daily_Report.md` and `Run_Summary.json`.
  The summary maps display names to folders in `task_directories`. The output base
  comes from the caller. Daily mode inserts the date before `runs/<run_id>/`.
- `discovery.py` exposes standard and custom indicator metadata to the Web Library.
  External schedulers invoke the CLI as described in
  [the daily-run guide](../../../docs/daily_run.md).
- Run `python -m pytest tests/orchestration tests/test_rebound_workflows.py`.
