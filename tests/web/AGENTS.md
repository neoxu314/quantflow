# WEB MODULE TESTS

## Run

```bash
pytest tests/web/ -v                          # All tests (API + Integration + E2E)
pytest tests/web/ -v --ignore=tests/web/e2e/  # API + Integration only (fast)
pytest tests/web/e2e/ -v                      # E2E browser tests only (slow)
pytest tests/web/test_config_api.py -v        # Single file
```

## Prerequisites

E2E tests require:
```bash
pip install pytest-playwright
playwright install chromium
```

Unit + Integration tests have no extra dependencies.

## Structure

```
tests/web/
├── conftest.py              # Shared fixtures: config_client, task_client, watchlist_dir
├── test_config_api.py       # Config API unit tests (GET/PUT round-trip)
├── test_task_api.py         # Task API unit tests (CRUD + security)
├── test_watchlist_api.py    # Watchlist API unit tests (CRUD + search)
├── test_integration.py      # API→filesystem→API round-trip integration tests
├── test_static_serving.py   # Static file serving + 404 + security tests
├── test_library_api.py       # Library API unit tests (strategies + indicators + params)
└── e2e/
    ├── conftest.py          # Playwright browser fixture (Chrome for Testing)
    └── test_web_ui.py       # 18 Playwright E2E browser UI tests
        # (watchlist/task create → YAML disk verification,
        #  Settings round-trip + restart persistence)
```

## Fixtures

### API tests (use tmp_path - never touch production data)

| Fixture | Returns | Module | File isolation |
|---------|---------|--------|---------------|
| `config_client` | `(TestClient, config_path)` | `tests/web/conftest.py` | Copies real `config/quantflow.yaml` to tmp_path, patches CONFIG_PATH |
| `task_client` | `(TestClient, config_dir)` | `tests/web/conftest.py` | Creates empty tmp config dir, patches CONFIG_DIR |
| `watchlist_dir` | `(TestClient, wl_dir)` | `tests/web/conftest.py` | Creates empty tmp watchlists dir, patches WATCHLISTS_DIR |

### E2E tests (use production web server)

| Fixture | Scope | Module |
|---------|-------|--------|
| `web_server` | session | `e2e/test_web_ui.py` |
| `page` | function | pytest-playwright builtin |

## Production Safety

### API + Integration tests
**Zero risk.** All file operations target `tmp_path` via monkey-patched module constants (`CONFIG_PATH`, `CONFIG_DIR`, `WATCHLISTS_DIR`). Temp dirs are destroyed by pytest after each test.

### E2E tests
Three-layer protection via `cleanup_test_data` autouse fixture in `e2e/test_web_ui.py`:

1. **Before each test**: `shutil.copy2(config/quantflow.yaml, config/quantflow.yaml.bak)`
2. **After each test**: `shutil.move(config/quantflow.yaml.bak, config/quantflow.yaml)` — atomic restore to exact pre-test state
3. **Always cleanup**: Deletes `watchlists/_test_e2e_wl.yaml` and `config/tasks_e2e_test.yaml`

This guarantees production config is byte-identical to pre-test state even if the test is interrupted (SIGKILL, power loss, etc.).

## Add New Test

1. **API endpoint changed?** → Add test to the matching `test_*_api.py` file
2. **New file I/O behavior?** → Add round-trip test to `test_integration.py`
3. **UI/frontend changed?** → Add Playwright test to `e2e/test_web_ui.py`
4. **New static file?** → Add test to `test_static_serving.py`
