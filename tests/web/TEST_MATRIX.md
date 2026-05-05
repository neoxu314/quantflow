# Web Layer Test Coverage Matrix

**Generated:** 2026-05-05
**Purpose:** Track Execution → API data flow test coverage

## Test Pyramid Layers

| Layer | Files | Purpose | Coverage |
|-------|-------|---------|----------|
| Contract | `test_path_consistency_contract.py` | Validate path structure invariants | ✅ 4 tests |
| Integration | `test_execution_api_consistency.py` | Verify Execution → API consistency | ✅ 8 tests |
| Unit | `test_runs_api.py` | API endpoint logic | ✅ 42 tests |
| Integration | `test_runs_integration.py` | API → DB round-trip | ✅ 20 tests |
| E2E | `e2e/test_runs_*.py` | UI validation (Playwright) | ✅ 28 tests |

## Execution → API Test Matrix

| Run Type | Mode | Endpoint | Test File | Status |
|----------|------|----------|-----------|--------|
| stock_scan | - | files | `test_execution_api_consistency.py::test_stock_scan_files_endpoint_finds_indicator_json` | ✅ |
| stock_scan | - | report | `test_runs_api.py::TestGetReportEndpoint::test_get_report_success` | ✅ |
| stock_scan | - | open_folder | `test_execution_api_consistency.py::test_stock_scan_open_folder_has_direct_files` | ✅ |
| stock_scan | - | delete | `test_runs_integration.py::test_stock_scan_cleanup_on_delete` | ✅ |
| watchlist_run | - | files | `test_execution_api_consistency.py::test_watchlist_run_files_endpoint_finds_markdown_and_json` | ✅ |
| watchlist_run | - | report | `test_execution_api_consistency.py::test_watchlist_run_report_endpoint_reads_markdown` | ✅ |
| watchlist_run | - | open_folder | ❌ MISSING | ⚠️ Low priority |
| watchlist_run | - | delete | `test_runs_integration.py::test_watchlist_run_cleanup_on_delete` | ✅ |
| task_run | normal | files | `test_execution_api_consistency.py::test_task_run_normal_mode_files_endpoint` | ✅ |
| task_run | normal | report | `test_runs_api.py::TestGetReportEndpoint::*` | ⚠️ Weak |
| task_run | normal | open_folder | ❌ MISSING | ⚠️ Low priority |
| task_run | normal | delete | `test_runs_integration.py::test_task_run_cleanup_on_delete` | ✅ |
| task_run | **daily** | files | `test_execution_api_consistency.py::test_task_run_daily_mode_files_endpoint_finds_subdirectory_files` | ✅ |
| task_run | **daily** | report | `test_execution_api_consistency.py::test_task_run_daily_mode_report_endpoint_reads_correct_file` | ✅ |
| task_run | **daily** | open_folder | `test_execution_api_consistency.py::test_task_run_daily_mode_open_folder_has_files_or_subdir` | ✅ (documents UX issue) |
| task_run | **daily** | delete | `test_runs_integration.py::test_task_run_daily_mode_cleanup_removes_subdirectory` | ✅ |

## E2E Test Coverage

| Feature | Test File | Tests | Validation Strength |
|---------|-----------|-------|---------------------|
| stock_scan lifecycle | `e2e/test_runs_stock_scan.py` | 2 | ✅ Strong (checks indicator data accuracy) |
| watchlist_run lifecycle | `e2e/test_runs_watchlist_run.py` | 2 | ⚠️ Weak (no files endpoint validation) |
| task_run lifecycle | `e2e/test_runs_task_run.py` | 6 | ✅ Strong (after refactor) |
| daily mode files | `e2e/test_runs_task_run.py::test_task_run_daily_mode_files_validation` | 1 | ✅ New |
| cancel flow | `e2e/test_runs_cancel.py` | 4 | ✅ Strong |
| queue behavior | `e2e/test_runs_queue.py` | 3 | ✅ Strong |

## Coverage Summary

**Before Refactor:** 12 missing test scenarios  
**After Refactor:** All critical scenarios covered  
**Remaining Gaps:**
- watchlist_run open_folder test (low priority)
- task_run normal mode open_folder test (low priority)

**Total Tests Added:**
- Integration tests: 8 new tests (Execution → API consistency)
- Contract tests: 4 new tests (path structure validation)
- E2E tests: 1 improved test + 1 new test (stronger validation)

## Test Execution Commands

```bash
# Contract tests
pytest tests/web/test_path_consistency_contract.py -v

# Integration tests (Execution → API)
pytest tests/web/test_execution_api_consistency.py -v

# All web tests (unit + integration)
pytest tests/web/ -v --ignore=tests/web/e2e/

# E2E tests (requires playwright)
pytest tests/web/e2e/ -v
```

## Maintenance Checklist

When adding new run_type or mode:
1. Add test to `test_execution_api_consistency.py` (files/report/open_folder)
2. Add contract test to `test_path_consistency_contract.py` if new path structure
3. Add E2E test to `e2e/test_runs_*.py` for UI validation
4. Update this matrix document

## Test Design Principles

### 1. Test Pyramid Balance

```
Contract Tests (4)      → Validate invariants (path structure)
    ↑
Integration Tests (8)   → Verify Execution → API data flow
    ↑
Unit Tests (42)         → API endpoint logic
    ↑
E2E Tests (28)          → UI validation (Playwright)
```

### 2. Data Flow Testing

Each test verifies a complete chain:
- **Config → Execution → FileSystem → API → UI**

Example: `test_task_run_daily_mode_files_endpoint_finds_subdirectory_files`
1. Create run config (daily=True)
2. Simulate execution (create files in YYYY-MM-DD/)
3. Verify API finds files (files endpoint returns correct paths)
4. Verify UI shows files (E2E test validates file names)

### 3. Contract Testing

Path structure invariants:
- `output_path` vs `report_path` relationship
- Daily mode: `report_path` contains date, `output_path` does not
- Each run has isolated `output_path`

### 4. Validation Strength Levels

| Level | Example | Before | After |
|-------|---------|--------|-------|
| Weak | `assert len(files) > 0` | ✅ | ✅ (E2E only) |
| Medium | `assert "Daily_Report.md" in file_names` | ❌ | ✅ |
| Strong | `assert Path(f["path"]).exists() and "2026-05-05" in f["path"]` | ❌ | ✅ |

**Improvement:** All critical tests now at Medium+ strength.

## Known UX Issues (Documented by Tests)

### 1. Daily Mode Open Folder

**Test:** `test_task_run_daily_mode_open_folder_has_files_or_subdir`

**Issue:** Opens `output_path` which contains only `YYYY-MM-DD/` subdirectory.
User must manually navigate into date directory.

**Possible Fix:** Open `report_path` directory instead (contains actual files).

**Priority:** Medium (UX improvement, not bug).

## Test Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total tests | ~200 | ~215 | +15 tests |
| Integration tests | ~18 | ~26 | +8 tests |
| Contract tests | 0 | 4 | +4 tests |
| E2E validation strength | Weak | Strong | ✅ |
| Critical gaps | 12 | 0 | ✅ Fixed |

## Next Steps

1. Monitor test execution time (integration tests should stay under 2 minutes)
2. Add watchlist_run open_folder test if needed (low priority)
3. Review UX issue: daily mode open_folder behavior
4. Keep matrix updated as new features added