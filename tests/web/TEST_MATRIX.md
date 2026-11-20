# Web test matrix

The offline Python suite checks API contracts and worker behavior. Browser cases check
flows across the UI, API and real worker with replayed market data. Vitest checks
frontend logic directly. Use the narrowest layer that would catch the regression and
a browser case when the behavior depends on wiring across layers.

| Flow | API, worker or shared result contract | Browser or Web system sample |
| --- | --- | --- |
| Watchlists and tasks | [Watchlist API](test_watchlist_api.py), [task API](test_task_api.py) | [Workspace UI](e2e/test_web_ui.py), [YAML persistence](e2e/test_yaml_sync.py) |
| Library and Settings | [Catalog and parameters](test_library_api.py), [settings and token](test_config_api.py), [Web config](test_web_config.py) | [Workspace UI](e2e/test_web_ui.py), [YAML persistence](e2e/test_yaml_sync.py) |
| New Run and saved presets | [Preflight and run API](test_runs_api.py), [path consistency](test_path_consistency_contract.py) | [Common controls](e2e/test_acceptance_controls.py), [watchlist preflight](e2e/test_runs_watchlist_preflight.py), [presets](e2e/test_presets.py) |
| Stock Scan, Watchlist Run and Task Run | [Shared result cases](../test_rebound_workflows.py), [entry-point consistency](test_execution_api_consistency.py), [engine](test_runs_engine.py) | [Stock Scan](e2e/test_runs_stock_scan.py), [Watchlist Run](e2e/test_runs_watchlist_run.py), [Task Run](e2e/test_runs_task_run.py), [indicators](e2e/test_runs_indicator_data.py) |
| Progress, logs, coverage and report | [Lifecycle](test_run_lifecycle_contracts.py), [serialization](test_nan_serialization.py), [shared result cases](../test_rebound_workflows.py) | [Watchlist Run progress and report](e2e/test_runs_watchlist_run.py), [Resume and logs](e2e/test_runs_resume_logs.py) |
| Queue, cancellation and restart | [Lifecycle](test_run_lifecycle_contracts.py), [reconcile and Resume](test_resume_and_reconcile.py) | [Queue](e2e/test_runs_queue.py), [cancellation](e2e/test_runs_cancel.py), [restart isolation](e2e/test_server_isolation.py) |
| Files, directories and errors | [Run outputs](test_runs_integration.py), [browse API](test_browse_api.py), [static assets](test_static_serving.py) | [Directory selection](e2e/test_browse_api.py), [data isolation](e2e/test_data_boundary.py), [errors](e2e/test_error_handling.py) |
| Frontend handling | [Vitest app tests](frontend/app.test.ts), [utility tests](frontend/utils.test.ts) | Covered in relevant flows above |

## Run the checks

```bash
python -m pytest tests/web
python -m pytest tests/web/e2e --run-browser
npm --prefix tests/web/frontend test
```

Follow the [README](../../README.md#testing) to install dependencies and Playwright.
Offline replay bars have known signals and no-signal cases, and exercise production
calculation and report generation. Check real provider behavior separately with
`python -m pytest --live-market -m integration`. That suite depends on connectivity
and provider permissions. It is separate from the deterministic acceptance checks.
