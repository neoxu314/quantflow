# CLI Layer Integration Tests - TODO List

**Generated:** 2026-05-05
**Status:** Pending expected results from real execution

## Overview

CLI layer tests (`tests/test_cli.py`) have completed:
- ✅ Structural validation (27 tests)
- ✅ stock_scan expected values (3 tests with BYD/AAPL reference)

Pending:
- ❌ watchlist_run expected values (2 tests)
- ❌ task_run expected values (2 tests)

## Missing Tests

### 1. watchlist_run Expected Results

**Test class:** `TestCLIWatchlistRunWithExpectedValues`
**Location:** `tests/test_cli.py` (marked `@pytest.mark.skip`)
**Status:** Pending

#### Test Cases:

**a) test_cli_watchlist_run_us_djia_expected_signals**
- **Purpose:** Verify watchlist_run for US DJIA produces expected signals
- **Needed data:**
  - Watchlist file: `watchlists/us_djia.yaml`
  - Strategy: `daily_bull_oversold`
  - Expected: buy_signals count, matched strategies list
- **Suggested approach:**
  - Run real execution: `python -m quantflow.cli monitor --watchlist watchlists/us_djia.yaml --strategies daily_bull_oversold`
  - Capture results JSON
  - Use counts as reference values

**b) test_cli_watchlist_run_multiple_strategies_expected**
- **Purpose:** Verify watchlist_run with multiple strategies
- **Needed data:**
  - Strategies: `daily_bull_oversold,daily_bull_mid_range`
  - Expected: total signal count, per-strategy breakdown
- **Suggested approach:**
  - Run real execution with multiple strategies
  - Capture per-strategy results

#### How to implement:

1. Run CLI command and capture JSON output:
```bash
python -m quantflow.cli monitor \
  --watchlist watchlists/us_djia.yaml \
  --strategies daily_bull_oversold \
  --output /tmp/ref_results
```

2. Read JSON file and extract expected values:
```python
import json
data = json.loads(Path("/tmp/ref_results/us_djia_results.json").read_text())
buy_count = sum(r.get("buy_signals", 0) for r in data)
matched_codes = [r["code"] for r in data if r.get("buy_signals") > 0]
```

3. Add to test:
```python
expected_buy_signals = <captured_value>
expected_matched_codes = [<list_of_codes>]

assert len(results) == expected_buy_signals
assert all(code in matched_codes for code in expected_matched_codes)
```

---

### 2. task_run Expected Results

**Test class:** `TestCLITaskRunWithExpectedValues`
**Location:** `tests/test_cli.py` (marked `@pytest.mark.skip`)
**Status:** Pending

#### Test Cases:

**a) test_cli_task_run_single_task_expected_results**
- **Purpose:** Verify task_run for single task produces expected results
- **Needed data:**
  - Task config: single task with known watchlist
  - Expected: Combined_Results.json length, Daily_Report.md structure
- **Suggested approach:**
  - Create simple test task config
  - Run real execution
  - Capture combined results

**b) test_cli_task_run_multiple_tasks_expected_total**
- **Purpose:** Verify task_run for multiple tasks produces expected total
- **Needed data:**
  - Task config: multiple tasks (e.g., US + Asia)
  - Expected: total signal count, per-task output directories
- **Suggested approach:**
  - Use existing task config like `config/tasks_us_mac.yaml`
  - Run real execution
  - Capture total signals from orchestrator output

#### How to implement:

1. Run CLI command and capture output:
```bash
python -m quantflow.cli tasks \
  --config config/tasks_us_mac.yaml \
  --output /tmp/ref_task_results
```

2. Read Combined_Results.json:
```python
import json
combined = json.loads(Path("/tmp/ref_task_results/Combined_Results.json").read_text())
total_signals = len(combined)
```

3. Check Markdown report:
```python
report_path = Path("/tmp/ref_task_results/Daily_Report.md")
assert report_path.exists()
content = report_path.read_text()
assert "# " in content  # Markdown header
assert "## Signals" in content
```

4. Add to test:
```python
expected_total_signals = <captured_value>

combined_json = output_dir / "Combined_Results.json"
data = json.loads(combined_json.read_text())
assert len(data) == expected_total_signals
```

---

## Alternative Approach: Use Mock Data

If real execution is too slow or unstable, can use mock patterns from:

- `tests/execution/test_executor.py::TestExecutorProcessSingle::test_process_single_with_buy_signal`
- `tests/orchestration/test_orchestrator.py::TestOrchestratorRun::test_run_returns_total_signals`

Example:
```python
mock_results = [
    MagicMock(buy_signals=1, sell_signals=0, code="NVDA.US"),
    MagicMock(buy_signals=2, sell_signals=1, code="AAPL.US"),
]
expected_total = sum(r.buy_signals for r in mock_results)  # = 3
```

---

## Quick Reference Commands

### Run skipped tests:
```bash
pytest tests/test_cli.py -v --tb=no
# Shows: 27 passed, 4 skipped
```

### Run only skipped tests (to see TODO items):
```bash
pytest tests/test_cli.py -m "skip" -v
```

### Check test coverage without skipped:
```bash
pytest tests/test_cli.py -m "not skip" -v
```

---

## Next Steps

1. Choose test case to implement (watchlist_run or task_run)
2. Decide approach: real execution or mock data
3. Run CLI command and capture reference results
4. Add expected values to test code
5. Remove `@pytest.mark.skip` decorator
6. Verify test passes

---

## File Locations

- Test file: `tests/test_cli.py`
- TODO documentation: `tests/CLI_TODO_TESTS.md`
- Main project doc: `AGENTS.md` (line 70-79)

---

**Contact:** When ready to implement, reference this file and update tests accordingly.