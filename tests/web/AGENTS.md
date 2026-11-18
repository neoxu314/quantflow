# WEB MODULE TESTS

## Run

```bash
# Python tests
pytest tests/web/ -v                          # All tests (API + Integration + E2E)
pytest tests/web/ -v --ignore=tests/web/e2e/  # API + Integration only (fast)
pytest tests/web/e2e/ -v                      # E2E browser tests only (slow)
pytest tests/web/e2e/test_runs_stock_scan.py -v    # Stock scan E2E only
pytest tests/web/e2e/test_runs_cancel.py -v       # Cancel flow E2E only
pytest tests/web/e2e/test_runs_indicator_data.py -v # Indicator data E2E only
pytest tests/web/e2e/test_presets.py -v             # Presets E2E only
pytest tests/web/e2e/test_runs_queue.py -v          # Queue E2E only
pytest tests/web/e2e/test_browse_api.py -v          # Browse E2E only
pytest tests/web/e2e/test_data_boundary.py -v       # Data boundary tests only
pytest tests/web/e2e/test_yaml_sync.py -v           # YAML sync tests only
pytest tests/web/test_runs_api.py -v            # Runs API tests only
pytest tests/web/test_browse_api.py -v          # Browse API tests only
pytest tests/web/test_config_api.py -v          # Single file

# Frontend TypeScript unit tests (Vitest)
cd tests/web/frontend && npm install   # Install dependencies
cd tests/web/frontend && npm test      # Run all frontend tests
cd tests/web/frontend && npm run test:watch  # Watch mode
```

## Prerequisites

E2E tests require:
```bash
pip install pytest-playwright
playwright install chromium
```

Frontend unit tests require:
```bash
cd src/quantflow/web/static
npm install
```

Unit + Integration tests have no extra dependencies.

## Structure

```
tests/web/
├── conftest.py              # Shared fixtures: config_client, task_client, watchlist_dir
├── test_config_api.py       # Config API unit tests (GET/PUT round-trip)
├── test_task_api.py         # Task API unit tests (CRUD + security)
├── test_watchlist_api.py    # Watchlist API unit tests (CRUD + search + inline editing)
├── test_integration.py      # API→filesystem→API round-trip integration tests
├── test_static_serving.py   # Static file serving + 404 + security tests
├── test_library_api.py      # Library API unit tests (strategies + indicators + params)
├── test_browse_api.py       # Browse API unit tests (directory listing + mkdir)
├── test_runs_api.py         # Runs API unit tests (CRUD, report, indicator-data, cancel, presets)
├── test_runs_engine.py      # Engine unit tests (RunHistory, RunQueue, SSE, Preflight, Presets)
├── test_runs_integration.py # Runs integration tests (API→DB→API round-trip, file cleanup)
├── test_execution_api_consistency.py # Execution→API data flow integration tests (NEW)
├── test_path_consistency_contract.py # Path structure contract tests (NEW)
├── test_nan_serialization.py # NaN handling in indicator DataFrame serialization
├── test_web_config.py       # WebConfig loading tests
├── TEST_MATRIX.md           # Execution→API test coverage documentation (NEW)
├── frontend/                # Frontend TypeScript unit tests (Vitest)
│   ├── utils.test.ts        # 49 unit tests for pure functions
│   ├── app.test.ts          # 33 unit tests for app pure functions
│   ├── vitest.config.ts     # Vitest configuration with @utils alias
│   ├── tsconfig.json        # TypeScript configuration
│   └── package.json         # npm dependencies (vitest, typescript)
└── e2e/
    ├── conftest.py          # Shared E2E fixtures: web_server, base_url, protect_production_configs
    ├── test_web_ui.py       # 22 basic UI tests (page load, create, navigation)
    ├── test_data_boundary.py # 8 data boundary tests (cancel without save, switch tab, refresh)
    ├── test_yaml_sync.py    # 11 YAML sync tests (edit→YAML consistency, format preservation)
    ├── test_error_handling.py # 7 error handling tests (500 error, network fail, validation)
    ├── test_runs_stock_scan.py     # 2 stock scan lifecycle E2E tests
    ├── test_runs_watchlist_run.py  # 2 watchlist run lifecycle E2E tests
    ├── test_runs_task_run.py       # 6 task run lifecycle E2E tests (updated: +1 daily mode)
    ├── test_runs_cancel.py         # 4 cancel flow E2E tests
    ├── test_runs_indicator_data.py # 6 indicator data accuracy E2E tests
    ├── test_runs_watchlist_preflight.py # 4 watchlist preflight validation E2E tests
    ├── test_runs_queue.py          # 3 queue ordering E2E tests
    ├── test_browse_api.py          # 8 browse API E2E tests
    └── test_presets.py             # 8 presets CRUD + run-from-preset E2E tests

src/quantflow/web/static/
├── app.ts                   # Main frontend app (imports from utils.ts)
├── utils.ts                 # Pure utility functions module
└── tsconfig.json            # TypeScript configuration for compilation
```

**Total: 101 E2E tests (13 files) + 212 Python tests (14 files) + 113 frontend tests (2 files)**

## Test Categories

| Category | File | Tests | Purpose |
|----------|------|-------|---------|
| Config API | `test_config_api.py` | 12 | GET/PUT round-trip, YAML format preservation |
| Watchlist API | `test_watchlist_api.py` | 10 | CRUD, search, fuzzy match, path traversal, inline editing round-trip |
| Task API | `test_task_api.py` | 10 | CRUD, duplicate rejection, path traversal |
| Library API | `test_library_api.py` | 9 | Strategies, indicators, param updates + round-trip |
| Browse API | `test_browse_api.py` | 19 | Directory listing, mkdir, permissions, sorting |
| Runs API | `test_runs_api.py` | 43 | CRUD, report, indicator-data, cancel, presets, open-folder, helpers |
| Runs Engine | `test_runs_engine.py` | 34 | RunHistory, RunQueue, SSE, Preflight, Presets |
| Runs Integration | `test_runs_integration.py` | 20 | API→DB→API, file cleanup, output isolation |
| **Execution API Consistency** | `test_execution_api_consistency.py` | **8** | **Execution→API data flow (files/report/open_folder)** |
| **Path Contract Tests** | `test_path_consistency_contract.py` | **4** | **Path structure invariants (output_path/report_path)** |
| NaN Serialization | `test_nan_serialization.py` | 11 | NaN/datetime/integer/string/inf handling |
| Integration | `test_integration.py` | 13 | Watchlist + Task API→filesystem round-trip |
| Static Serving | `test_static_serving.py` | 4 | HTML/JS serving, 404, path traversal |
| Web Config | `test_web_config.py` | 3 | WebConfig loading from YAML |
| Basic UI | `test_web_ui.py` | 22 | Page loads, tab navigation, create/delete |
| Data Boundary | `test_data_boundary.py` | 8 | Cancel without save, switch tab, sequential saves |
| YAML Sync | `test_yaml_sync.py` | 18 | Edit→YAML round-trip, unicode, inline name/tags editing, multi-stock regression |
| Error Handling | `test_error_handling.py` | 7 | Server 500, network disconnect, invalid input |
| Stock Scan E2E | `test_runs_stock_scan.py` | 2 | Full lifecycle + modal reset |
| Watchlist Run E2E | `test_runs_watchlist_run.py` | 2 | Full lifecycle + type lock |
| Task Run E2E | `test_runs_task_run.py` | 6 | Full lifecycle, daily mode, progress, file isolation |
| Cancel E2E | `test_runs_cancel.py` | 4 | Cancel active/queued runs, delete cancelled |
| Indicator Data E2E | `test_runs_indicator_data.py` | 6 | JSON validity, NaN check, bar_count, files |
| Preflight E2E | `test_runs_watchlist_preflight.py` | 4 | Empty watchlist, invalid strategy, validate_only |
| Queue E2E | `test_runs_queue.py` | 3 | Active+pending status, sequential completion |
| Browse E2E | `test_browse_api.py` | 8 | Directory listing, mkdir, parent nav |
| Presets E2E | `test_presets.py` | 8 | CRUD, run from preset, persistence, validation |
| Frontend Utils | `utils.test.ts` | 49 | Pure functions (MARKET_SUFFIX, get/setNestedValue, formatStockCode) |
| Frontend App | `app.test.ts` | 43 | Pure app functions (render helpers, formatters, CLI preview event listeners) |

**Note**: See `TEST_MATRIX.md` for detailed Execution → API test coverage per run_type × endpoint combination.

### Frontend Unit Tests (utils.test.ts)

| Test Suite | Tests | Coverage |
|------------|-------|----------|
| `MARKET_SUFFIX` | 8 | All 6 markets + unknown market handling |
| `SETTINGS_FIELD_MAP` | 8 | All 16 field path mappings |
| `getNestedValue` | 12 | Single/multi-level paths, undefined cases, type handling |
| `setNestedValue` | 11 | Path creation, value overwrite, field preservation |
| `formatStockCode` | 10 | All markets, already-formatted codes, edge cases |

### Frontend Unit Tests (app.test.ts - inline editing)

| Test Suite | Tests | Coverage |
|------------|-------|----------|
| `tag editing helpers` | 11 | parseTagInput, mergeTags, removeTagAt |
| `inline editing DOM structure` | 7 | editable-name/tags rendering, multi-row data-idx, currentTarget resolution |

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

### Session-level protection (conftest.py)
Two safety hooks verify production files are never modified by tests:

1. **pytest_sessionstart**: Snapshot file hashes for all production configs
   - Snapshots: `config/quantflow.yaml`, `config/indicators.yaml`, `watchlists/*.yaml`
   - Stores SHA256 hashes in-memory for later verification

2. **pytest_sessionfinish**: Verify all hashes match
   - Fails test session if any production file changed
   - Catches accidental writes to production paths

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
- All `watchlists/*.yaml` files

**Test-only files (created/deleted per test):**
- `watchlists/_test_e2e_wl.yaml`
- `config/tasks_e2e_test.yaml`

### Historical incident (resolved)
**Commit 276996b**: Test code overwrote `watchlists/djia.yaml` (30 stocks → 1 stock) by writing to production path instead of tmp_path. Root cause: hardcoded path in test code.

**Fix**: 
- Added session-level hash verification (conftest.py)
- Added E2E autouse fixture (e2e/conftest.py)
- Restored djia.yaml from initial commit a78fec7
- All tests now use tmp_path for file operations

## Add New Test

1. **API endpoint changed?** → Add test to the matching `test_*_api.py` file
2. **New file I/O behavior?** → Add round-trip test to `test_integration.py`
3. **UI/frontend changed?** → Add Playwright test to `e2e/test_web_ui.py`
4. **New data boundary case?** → Add to `e2e/test_data_boundary.py`
5. **YAML sync issue?** → Add to `e2e/test_yaml_sync.py`
6. **Error handling?** → Add to `e2e/test_error_handling.py`
7. **New static file?** → Add test to `test_static_serving.py`
8. **New frontend utility function?** → Add to `src/quantflow/web/static/utils.ts` + `tests/web/frontend/utils.test.ts`
9. **Run/execution logic changed?** → Add to `test_runs_api.py` (API) or `test_runs_engine.py` (engine)
10. **New run lifecycle scenario?** → Add E2E to `e2e/test_runs_*.py`
11. **Browse API changed?** → Add to `test_browse_api.py` (unit) or `e2e/test_browse_api.py` (E2E)
12. **Preset behavior changed?** → Add to `test_runs_api.py` (unit) or `e2e/test_presets.py` (E2E)
13. **Indicator serialization changed?** → Add to `test_nan_serialization.py`
14. **Watchlist inline editing changed?** → Add to `test_watchlist_api.py` (unit), `e2e/test_yaml_sync.py` (E2E), `tests/web/frontend/app.test.ts` (frontend)

## 2026-11-18 RELIABILITY CONTRACT

Project `docs/reliability-and-data-contracts.md` supersedes legacy output, adjustment and state details above. Outputs are run-owned manifest artifacts; analyzed/no-data/stale/insufficient/error are distinct. Tushare uses explicit factors and shares, Yahoo adapters reject hfq, and facts preserve units, source and time. Task summaries expose failures. API tests isolate runtime state and do not start unmanaged workers.
