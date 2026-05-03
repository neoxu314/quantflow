# WEB MODULE TESTS

## Run

```bash
pytest tests/web/ -v                          # All tests (API + Integration + E2E)
pytest tests/web/ -v --ignore=tests/web/e2e/  # API + Integration only (fast)
pytest tests/web/e2e/ -v                      # E2E browser tests only (slow)
pytest tests/web/e2e/test_data_boundary.py -v # Data boundary tests only
pytest tests/web/e2e/test_yaml_sync.py -v     # YAML sync tests only
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
├── test_library_api.py      # Library API unit tests (strategies + indicators + params)
└── e2e/
    ├── conftest.py          # Shared E2E fixtures: web_server, base_url, protect_production_configs
    ├── test_web_ui.py       # 22 basic UI tests (page load, create, navigation)
    ├── test_data_boundary.py # 8 data boundary tests (cancel without save, switch tab, refresh)
    ├── test_yaml_sync.py    # 11 YAML sync tests (edit→YAML consistency, format preservation)
    └── test_error_handling.py # 7 error handling tests (500 error, network fail, validation)
```

**Total: 48 E2E tests + 11 API test files**

## Test Categories

| Category | File | Tests | Purpose |
|----------|------|-------|---------|
| Basic UI | `test_web_ui.py` | 22 | Page loads, tab navigation, create/delete operations |
| Data Boundary | `test_data_boundary.py` | 8 | Cancel without save, switch tab mid-edit, sequential saves |
| YAML Sync | `test_yaml_sync.py` | 11 | Edit→YAML round-trip, unicode, field order preservation |
| Error Handling | `test_error_handling.py` | 7 | Server 500, network disconnect, invalid input |

## Fixtures

### API tests (use tmp_path - never touch production data)

| Fixture | Returns | Module | File isolation |
|---------|---------|--------|---------------|
| `config_client` | `(TestClient, config_path)` | `tests/web/conftest.py` | Copies real `config/quantflow.yaml` to tmp_path, patches CONFIG_PATH |
| `task_client` | `(TestClient, config_dir)` | `tests/web/conftest.py` | Creates empty tmp config dir, patches CONFIG_DIR |
| `watchlist_dir` | `(TestClient, wl_dir)` | `tests/web/conftest.py` | Creates empty tmp watchlists dir, patches WATCHLISTS_DIR |

### E2E tests (use production web server)

| Fixture | Scope | Module | Purpose |
|---------|-------|--------|---------|
| `web_server` | session | `e2e/conftest.py` | Starts QuantFlow web server on port 8080 |
| `base_url` | session | `e2e/conftest.py` | Returns `http://127.0.0.1:8080` |
| `protect_production_configs` | function | `e2e/conftest.py` | Backup/restore quantflow.yaml + indicators.yaml |
| `page` | function | pytest-playwright builtin | Playwright browser page |

## Production Safety

### API + Integration tests
**Zero risk.** All file operations target `tmp_path` via monkey-patched module constants (`CONFIG_PATH`, `CONFIG_DIR`, `WATCHLISTS_DIR`). Temp dirs are destroyed by pytest after each test.

### E2E tests
Four-layer protection via `protect_production_configs` autouse fixture in `e2e/conftest.py`:

1. **Before each test**: 
   - Backup `config/quantflow.yaml` → `quantflow.yaml.bak`
   - Backup `config/indicators.yaml` → `indicators.yaml.bak`
2. **After each test**: 
   - Restore `quantflow.yaml.bak` → `quantflow.yaml`
   - Restore `indicators.yaml.bak` → `indicators.yaml`
3. **Cleanup test data**: Delete `watchlists/_test_e2e_wl.yaml` and `config/tasks_e2e_test.yaml`
4. **Atomic restore**: Uses `shutil.move()` for atomic file replacement

This guarantees production configs are byte-identical to pre-test state even if tests are interrupted (SIGKILL, power loss, etc.).

**Protected files:**
- `config/quantflow.yaml` (Settings)
- `config/indicators.yaml` (Library indicator params)

**Test-only files (created/deleted per test):**
- `watchlists/_test_e2e_wl.yaml`
- `config/tasks_e2e_test.yaml`

## Add New Test

1. **API endpoint changed?** → Add test to the matching `test_*_api.py` file
2. **New file I/O behavior?** → Add round-trip test to `test_integration.py`
3. **UI/frontend changed?** → Add Playwright test to `e2e/test_web_ui.py`
4. **New data boundary case?** → Add to `e2e/test_data_boundary.py`
5. **YAML sync issue?** → Add to `e2e/test_yaml_sync.py`
6. **Error handling?** → Add to `e2e/test_error_handling.py`
7. **New static file?** → Add test to `test_static_serving.py`
