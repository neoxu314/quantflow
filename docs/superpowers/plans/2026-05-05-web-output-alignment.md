# Web Output Logic Alignment Implementation Plan

> **历史资料。** 以下内容保留文件名所示日期的方案和假设。当前入口、路径与约束见 [项目文档](../../../README.md) 和 [运行契约](../../reliability-and-data-contracts.md)。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align Web output logic across stock_scan/watchlist_run/task_run to use direct output paths without run_id subdirectory isolation, matching task_run's "所见即所得" model.

**Architecture:** Remove run_id subdirectory injection for stock_scan/watchlist_run in RunEngine; unify delete logic to precise file deletion (参考task_run); align default paths to `./output` (相对路径); handle filename colon sanitization.

**Tech Stack:** Python (FastAPI, pathlib), pytest, TypeScript frontend (无改动)

---

## File Structure

### Modified Files

| File | Responsibility | Changes |
|------|---------------|---------|
| `src/quantflow/web/engine/run_engine.py` | Core execution engine | Remove run_id隔离, fix default paths, sanitize colons |
| `src/quantflow/web/api/runs.py` | Delete run API endpoint | Unify delete logic for all run types |
| `tests/web/test_execution_api_consistency.py` | Execution→API contract tests | Update path assumptions (remove run_id subdirectory) |
| `tests/web/test_path_consistency_contract.py` | Path structure invariants | Remove "output_path unique per run" test |
| `tests/web/test_runs_integration.py` | Integration tests | Update delete behavior expectations |
| `tests/web/e2e/test_runs_stock_scan.py` | E2E stock scan | Update file path verification |
| `tests/web/e2e/test_runs_watchlist_run.py` | E2E watchlist run | Update file path verification |
| `tests/web/e2e/test_runs_task_run.py` | E2E task run | Verify unchanged behavior (already aligned) |
| `src/quantflow/web/engine/AGENTS.md` | Engine documentation | Document new output logic |

### Key Design Decisions

1. **Default paths统一**: All run types default to `./output` (相对路径)
2. **Run_id移除**: stock_scan/watchlist_run不再创建 `{run_id}` 子目录
3. **文件删除**: 精确删除特定文件，不删除整个目录（参考task_run）
4. **冒号处理**: watchlist_run job.name中的冒号替换为 `-` (Windows兼容)

---

## Phase 1: run_engine.py Core Logic Changes

### Task 1.1: Remove run_id subdirectory for stock_scan

**Files:**
- Modify: `src/quantflow/web/engine/run_engine.py:125-128`

- [ ] **Step 1: Read current implementation**

Run: Read file to understand current logic
Expected: Line 125-128 contains `output = str(Path(base_output) / run_id)`

- [ ] **Step 2: Remove run_id subdirectory injection**

```python
# BEFORE (line 125-128):
base_output = cfg.get("output_path") or str(PROJECT_ROOT / "output" / "manual_scans")
output = str(Path(base_output) / run_id)  # 强制 run_id 隔离

# AFTER:
output = cfg.get("output_path") or str(PROJECT_ROOT / "output" / "manual_scans")
# 直接使用 output，不追加 run_id
```

- [ ] **Step 3: Change default path to relative**

```python
# Line 125 (继续修改):
# BEFORE:
output = cfg.get("output_path") or str(PROJECT_ROOT / "output" / "manual_scans")

# AFTER:
output = cfg.get("output_path") or "./output/manual_scans"
```

- [ ] **Step 4: Verify indicator file path logic**

Current line 198: `data_file = Path(output) / f"{safe_code}_indicators.json"`
This remains unchanged - file will be directly in `./output/manual_scans/{code}_indicators.json`

- [ ] **Step 5: Commit Phase 1.1**

```bash
git add src/quantflow/web/engine/run_engine.py
git commit -m "feat(web): remove run_id subdirectory for stock_scan, align to ./output"
```

---

### Task 1.2: Remove run_id subdirectory for watchlist_run

**Files:**
- Modify: `src/quantflow/web/engine/run_engine.py:276-278`

- [ ] **Step 1: Read current implementation**

Run: Read file lines 262-308 to understand watchlist_run execution

- [ ] **Step 2: Remove run_id subdirectory injection**

```python
# BEFORE (line 276-278):
base_output = cfg.get("output_path") or str(PROJECT_ROOT / "output" / "manual_watchlist")
output = str(Path(base_output) / run_id)  # 强制 run_id 隔离

# AFTER:
output = cfg.get("output_path") or "./output/manual_watchlist"
# 直接使用 output，不追加 run_id
```

- [ ] **Step 3: Commit Phase 1.2**

```bash
git add src/quantflow/web/engine/run_engine.py
git commit -m "feat(web): remove run_id subdirectory for watchlist_run"
```

---

### Task 1.3: Sanitize colon in watchlist_run job.name

**Files:**
- Modify: `src/quantflow/web/engine/run_engine.py:290`

- [ ] **Step 1: Identify job.name construction**

Current line 290: `name=f"web:{wl.name}", items=wl.items, ...`

- [ ] **Step 2: Replace colon with hyphen**

```python
# BEFORE (line 290):
job = ExecutionJob(
    name=f"web:{wl.name}", items=wl.items, strategies=strategies,
    output_dir=output, days_back=days_back)

# AFTER:
job = ExecutionJob(
    name=f"web-{wl.name}", items=wl.items, strategies=strategies,
    output_dir=output, days_back=days_back)
```

**Note:** This ensures generated files are `web-{wl_name}.json` and `web-{wl_name}.md` (Windows compatible)

- [ ] **Step 3: Update MarkdownReporter call to match**

Current line 296-297: `MarkdownReporter().generate(f"web:{wl.name}", ...)`
Change to match job.name:

```python
# BEFORE (line 296):
rpath = MarkdownReporter().generate(
    f"web:{wl.name}", strategies, results, wl, output, date_str)

# AFTER:
rpath = MarkdownReporter().generate(
    f"web-{wl.name}", strategies, results, wl, output, date_str)
```

- [ ] **Step 4: Commit Phase 1.3**

```bash
git add src/quantflow/web/engine/run_engine.py
git commit -m "feat(web): sanitize colon in watchlist_run job.name for Windows compatibility"
```

---

### Task 1.4: Verify stock_scan/watchlist_run execution produces correct paths

**Files:**
- Test: Manual verification (no test file changes yet)

- [ ] **Step 1: Run stock_scan execution simulation**

Create temporary test to verify path logic:
```python
# Temp test (delete after verification)
from pathlib import Path
run_id = "abc123"
output = "./output/manual_scans"  # New logic
expected_file = Path(output) / "600000.SH_indicators.json"
print(f"Expected path: {expected_file}")  # Should NOT contain run_id
```

- [ ] **Step 2: Run watchlist_run execution simulation**

```python
# Temp test (delete after verification)
wl_name = "test_watchlist"
job_name = f"web-{wl_name}"  # New logic with hyphen
expected_files = [
    Path(output) / f"{job_name}.json",
    Path(output) / f"{job_name}.md"
]
print(f"Expected paths: {expected_files}")  # Should NOT contain run_id
```

- [ ] **Step 3: Delete temporary verification code**

---

## Phase 2: runs.py Delete Logic Unification

### Task 2.1: Create unified delete function for stock_scan/watchlist_run

**Files:**
- Modify: `src/quantflow/web/api/runs.py:130-227`

- [ ] **Step 1: Read current delete logic**

Run: Read `runs.py` lines 107-228 to understand current delete behavior

- [ ] **Step 2: Create unified delete helper function**

Insert new function before `_delete_task_run_outputs` (around line 148):

```python
def _delete_stock_scan_outputs(run, output_dir: Path):
    """Delete stock_scan generated files without deleting entire directory.
    
    For stock_scan, output_path contains only indicator JSON file.
    File name: {safe_code}_indicators.json
    """
    code = run.config.get("code", "")
    safe_code = code.replace("/", "_").replace("\\", "_")
    indicator_file = output_dir / f"{safe_code}_indicators.json"
    
    if indicator_file.exists():
        indicator_file.unlink()


def _delete_watchlist_run_outputs(run, output_dir: Path):
    """Delete watchlist_run generated files without deleting entire directory.
    
    For watchlist_run, files are named based on run.name (Executor job.name).
    Files: {run.name}.json and {run.name}.md
    
    Note: run.name may contain colon (web:{wl_name}), sanitized to web-{wl_name}
    """
    run_name = run.name.replace(":", "-").replace("/", "_")
    
    files_to_delete = [
        output_dir / f"{run_name}.json",  # Executor output
        output_dir / f"{run_name}.md",    # Markdown report
    ]
    
    for f in files_to_delete:
        if f.exists():
            f.unlink()
```

- [ ] **Step 3: Update delete_run endpoint to use unified logic**

```python
# BEFORE (line 130-141):
if run.run_type == "task_run":
    # only delete task output files, not entire directory
    if op.exists() and op.is_dir():
        _delete_task_run_outputs(run, op)
else:
    # stock_scan, watchlist_run: safe to delete entire directory
    # (output_path contains run_id subdirectory)
    if op.exists() and op.is_dir():
        import shutil
        shutil.rmtree(op, ignore_errors=True)

# AFTER:
if op.exists() and op.is_dir():
    if run.run_type == "stock_scan":
        _delete_stock_scan_outputs(run, op)
    elif run.run_type == "watchlist_run":
        _delete_watchlist_run_outputs(run, op)
    elif run.run_type == "task_run":
        _delete_task_run_outputs(run, op)
```

- [ ] **Step 4: Commit Phase 2.1**

```bash
git add src/quantflow/web/api/runs.py
git commit -m "feat(web): unify delete logic for all run types - precise file deletion"
```

---

### Task 2.2: Verify delete logic handles missing files gracefully

**Files:**
- Test: Manual verification

- [ ] **Step 1: Test stock_scan delete with missing file**

```python
# Verify _delete_stock_scan_outputs handles non-existent files:
from pathlib import Path
output_dir = Path("./output/manual_scans")
run.config = {"code": "600000.SH"}
# File doesn't exist
_delete_stock_scan_outputs(run, output_dir)
# Should not throw error
```

- [ ] **Step 2: Test watchlist_run delete with missing files**

```python
# Verify _delete_watchlist_run_outputs handles non-existent files:
run.name = "web-test"
output_dir = Path("./output/manual_watchlist")
# Files don't exist
_delete_watchlist_run_outputs(run, output_dir)
# Should not throw error
```

---

## Phase 3: Test Updates

### Task 3.1: Update execution API consistency tests

**Files:**
- Modify: `tests/web/test_execution_api_consistency.py`

- [ ] **Step 1: Read current test assumptions**

Run: Read test file to identify run_id assumptions

- [ ] **Step 2: Update test_stock_scan_files_endpoint**

```python
# BEFORE (line 60-64):
output_dir = tmp_path / rid  # Assumes run_id subdirectory
output_dir.mkdir()
indicator_file = output_dir / "NVDA.US_indicators.json"

# AFTER:
output_dir = tmp_path / "manual_scans"  # Direct output, no run_id
output_dir.mkdir()
indicator_file = output_dir / "NVDA.US_indicators.json"
```

- [ ] **Step 3: Update test_watchlist_run_files_endpoint**

```python
# BEFORE (line 100-101):
output_dir = tmp_path / rid
output_dir.mkdir()

# AFTER:
output_dir = tmp_path / "manual_watchlist"
output_dir.mkdir()
```

- [ ] **Step 4: Update test_task_run_normal_mode (verify unchanged)**

Verify this test already assumes no run_id (line 141-142):
```python
output_dir = tmp_path / rid  # THIS IS WRONG - should be tmp_path directly
```

Actually, task_run current logic uses Orchestrator which doesn't add run_id.
But after Phase 1 changes, task_run should also align to direct output.

Check run_engine.py line 320: `output = cfg.get("output_path") or "./output"`
This is already correct - no run_id added.

But the test assumes tmp_path / rid. Fix this:

```python
# BEFORE (line 141):
output_dir = tmp_path / rid

# AFTER:
output_dir = tmp_path  # Direct output for task_run too
```

- [ ] **Step 5: Update test_task_run_daily_mode (verify unchanged)**

Line 184: `output_dir = tmp_path / rid`
Should be: `output_dir = tmp_path`

```python
# BEFORE:
output_dir = tmp_path / rid
date_dir = output_dir / "2026-05-05"

# AFTER:
output_dir = tmp_path
date_dir = output_dir / "2026-05-05"
```

- [ ] **Step 6: Run tests to verify failures (预期失败)**

```bash
pytest tests/web/test_execution_api_consistency.py -v
```

Expected: Tests fail because they still use old run_id logic

- [ ] **Step 7: Commit test updates**

```bash
git add tests/web/test_execution_api_consistency.py
git commit -m "test(web): update execution consistency tests - remove run_id assumptions"
```

---

### Task 3.2: Update path consistency contract tests

**Files:**
- Modify: `tests/web/test_path_consistency_contract.py`

- [ ] **Step 1: Remove "output_path unique per run" test**

This test assumes each run has unique output_path (run_id隔离).
After alignment, multiple runs can have same output_path.

```python
# DELETE entire test (line 120-140):
def test_output_path_unique_per_run(self, setup_db, tmp_path):
    """Each run must have unique output_path (isolated directories)."""
    # ... entire test body ...
```

- [ ] **Step 2: Update test_all_run_types_report_path_exists_if_completed**

```python
# BEFORE (line 97-98):
output_dir = tmp_path / f"{run_type}_{rid}"
output_dir.mkdir()

# AFTER:
output_dir = tmp_path / f"{run_type}_output"  # No run_id, use run_type suffix
output_dir.mkdir()
```

- [ ] **Step 3: Run tests to verify**

```bash
pytest tests/web/test_path_consistency_contract.py -v
```

Expected: Tests pass (contract updated)

- [ ] **Step 4: Commit test updates**

```bash
git add tests/web/test_path_consistency_contract.py
git commit -m "test(web): remove output_path uniqueness contract, update for alignment"
```

---

### Task 3.3: Update runs integration tests

**Files:**
- Modify: `tests/web/test_runs_integration.py`

- [ ] **Step 1: Find delete behavior tests**

Search for tests that verify delete cleans entire directory.

- [ ] **Step 2: Update test_delete_run_removes_files (if exists)**

```python
# BEFORE:
# Verify entire directory deleted
assert not d.exists(), "output_path directory should be deleted"

# AFTER:
# Verify only specific files deleted, directory remains
assert d.exists(), "output_path directory should remain"
assert not (d / "report.md").exists(), "Generated files should be deleted"
```

- [ ] **Step 3: Run tests to verify**

```bash
pytest tests/web/test_runs_integration.py -v
```

- [ ] **Step 4: Commit test updates**

```bash
git add tests/web/test_runs_integration.py
git commit -m "test(web): update delete behavior tests - precise file deletion"
```

---

### Task 3.4: Update E2E tests for stock_scan/watchlist_run

**Files:**
- Modify: `tests/web/e2e/test_runs_stock_scan.py`
- Modify: `tests/web/e2e/test_runs_watchlist_run.py`

- [ ] **Step 1: Read stock_scan E2E test**

Run: Read test file to find file path assertions

- [ ] **Step 2: Update file path expectations**

```python
# BEFORE:
# Verify file in run_id subdirectory
assert "abc123" in file_path  # run_id

# AFTER:
# Verify file directly in output
assert "manual_scans" in file_path
assert "abc123" not in file_path  # No run_id
```

- [ ] **Step 3: Update watchlist_run E2E test**

Similar updates to remove run_id expectations.

- [ ] **Step 4: Run E2E tests**

```bash
pytest tests/web/e2e/test_runs_stock_scan.py -v
pytest tests/web/e2e/test_runs_watchlist_run.py -v
```

- [ ] **Step 5: Commit E2E test updates**

```bash
git add tests/web/e2e/test_runs_stock_scan.py tests/web/e2e/test_runs_watchlist_run.py
git commit -m "test(e2e): update stock_scan/watchlist_run tests - remove run_id paths"
```

---

### Task 3.5: Verify task_run E2E tests unchanged

**Files:**
- Verify: `tests/web/e2e/test_runs_task_run.py`

- [ ] **Step 1: Read task_run E2E test**

Run: Read test file to verify no changes needed

- [ ] **Step 2: Verify test assumptions match new logic**

Current test should already assume:
- output_path = tmp_path (no run_id)
- files directly in output or date subdirectory

If tests already correct, no changes needed.

---

## Phase 4: Documentation Updates

### Task 4.1: Update AGENTS.md for web/engine

**Files:**
- Modify: `src/quantflow/web/engine/AGENTS.md`

- [ ] **Step 1: Read current documentation**

Run: Read AGENTS.md to find output logic documentation

- [ ] **Step 2: Update output logic section**

Add new section or update existing:

```markdown
## Output Logic (Unified)

All run types follow "所见即所得" model:
- **stock_scan**: Output directly to `./output/manual_scans/{code}_indicators.json`
- **watchlist_run**: Output directly to `./output/manual_watchlist/{name}.json` and `.md`
- **task_run**: Output directly to `./output` (or `./output/YYYY-MM-DD` if daily mode)

**Key changes from previous version:**
- No run_id subdirectory injection (previously stock_scan/watchlist_run added `{run_id}/`)
- Default paths: stock_scan uses `./output/manual_scans`, watchlist_run uses `./output/manual_watchlist`, task_run uses `./output`
- User-specified paths: when `output_path` is provided, all types use it directly (consistent behavior)
- Unified delete logic: precise file deletion (not entire directory)

**User responsibility:**
- Users control output isolation via different `output_path` values
- Users can use preset system to save different output configurations
- RunHistory database tracks all runs regardless of output_path

**Delete behavior:**
All run types use precise file deletion:
- stock_scan: Delete `{code}_indicators.json`
- watchlist_run: Delete `{run.name}.json` and `{run.name}.md`
- task_run: Delete Daily_Report.md, Combined_Results.json, and per-task files

This prevents accidental deletion of user files in output directory.
```

- [ ] **Step 3: Update file structure documentation**

Update the structure section to reflect new file naming:
```markdown
### Watchlist run files
- `{run.name}.json` - Executor output (e.g., `web-test_watchlist.json`)
- `{run.name}.md` - Markdown report (e.g., `web-test_watchlist.md`)
Note: job.name uses hyphen instead of colon for Windows compatibility
```

- [ ] **Step 4: Commit documentation updates**

```bash
git add src/quantflow/web/engine/AGENTS.md
git commit -m "docs(web): update output logic documentation for alignment"
```

---

### Task 4.2: Update AGENTS.md for web/api

**Files:**
- Modify: `src/quantflow/web/AGENTS.md`

- [ ] **Step 1: Update runs API documentation**

Add note about unified delete logic:

```markdown
## Runs API

### Delete Run Endpoint
- **Path**: `/api/runs/{run_id}`
- **Method**: DELETE
- **Behavior**: Unified precise file deletion for all run types
  - stock_scan: Deletes indicator JSON only
  - watchlist_run: Deletes Executor JSON + Markdown report
  - task_run: Deletes Daily_Report.md, Combined_Results.json, and per-task files
- **Safety**: Does NOT delete entire directory to prevent user file loss
```

- [ ] **Step 2: Commit documentation updates**

```bash
git add src/quantflow/web/AGENTS.md
git commit -m "docs(web-api): update delete endpoint documentation"
```

---

## Verification & Final Commit

### Task 5.1: Run full test suite

- [ ] **Step 1: Run all web tests**

```bash
pytest tests/web/ -v --ignore=tests/web/e2e/
```

Expected: All unit + integration tests pass

- [ ] **Step 2: Run E2E tests (if environment available)**

```bash
pytest tests/web/e2e/ -v
```

Note: E2E tests require playwright setup

- [ ] **Step 3: Fix any failing tests**

If tests fail, debug and fix inline.

---

### Task 5.2: Manual verification via Web UI

- [ ] **Step 1: Start web server**

```bash
python -m quantflow.cli web
```

- [ ] **Step 2: Create stock_scan run**

Via Web UI:
- Set code: `600000.SH`
- Set output_path: `./output/manual_scans`
- Run

Verify file created at: `./output/manual_scans/600000.SH_indicators.json`
Verify NO run_id subdirectory

- [ ] **Step 3: Create watchlist_run**

Via Web UI:
- Select watchlist
- Set output_path: `./output/manual_watchlist`
- Run

Verify files created at: `./output/manual_watchlist/web-{wl_name}.json` and `.md`
Verify NO run_id subdirectory
Verify colon sanitized to hyphen

- [ ] **Step 4: Delete runs and verify precise deletion**

Via Web UI:
- Delete stock_scan run
- Verify directory remains, only JSON deleted

- Delete watchlist_run
- Verify directory remains, only .json and .md deleted

- [ ] **Step 5: Run multiple runs with same output_path**

Create two stock_scans with same output_path:
- Verify second run overwrites first run's file
- Verify RunHistory database has both records

---

### Task 5.3: Final commit and summary

- [ ] **Step 1: Review all changes**

```bash
git status
git log --oneline -10
```

- [ ] **Step 2: Create summary commit if needed**

If multiple small commits exist, consider squash:
```bash
git rebase -i HEAD~N  # Squash related commits
```

Or create final summary commit:
```bash
git commit --allow-empty -m "feat(web): complete output logic alignment

Aligned all run types to task_run model:
- Removed run_id subdirectory for stock_scan/watchlist_run
- Unified default paths to ./output (相对路径)
- Unified delete logic to precise file deletion
- Sanitized colon in watchlist_run filenames

Tests updated: execution consistency, path contract, integration, E2E
Docs updated: AGENTS.md for web/engine and web/api"
```

---

## Self-Review Checklist

After completing all tasks, verify:

1. **Spec coverage**: ✓ All decisions implemented
   - Default paths aligned to `./output`
   - Run_id removed for stock_scan/watchlist_run
   - Delete logic unified
   - Colon sanitized

2. **Placeholder scan**: No TBD/TODO in plan

3. **Type consistency**: 
   - `run.name` used consistently across delete functions
   - Path handling uses `Path()` consistently
   - Colon sanitization applied uniformly

4. **Test coverage**: All test categories updated
   - Execution consistency tests
   - Path contract tests
   - Integration tests
   - E2E tests (stock_scan/watchlist_run)
   - task_run tests verified unchanged

---

**Plan complete. Execution options:**

1. **Subagent-Driven (推荐)** - I dispatch fresh subagent per task, review between tasks
2. **Inline Execution** - Execute tasks in current session with checkpoints

**Which approach?**