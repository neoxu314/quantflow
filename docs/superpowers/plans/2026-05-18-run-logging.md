# Run Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create persistent log files for all run types in both CLI and Web UI.

**Architecture:** Add `config/logging.py` with `setup_logging()` (dual handler: StreamHandler + FileHandler). Activate dead logging config in `quantflow.yaml`. Migrate CLI `print()` to `logger.info()`. Call `setup_logging()` at run start.

**Spec:** `docs/superpowers/specs/2026-05-18-run-logging-design.md`

**Tech Stack:** Python stdlib `logging`, existing `ConfigLoader`

---

### Task 1: Update `quantflow.yaml` and `ConfigLoader`

**Files:**
- Modify: `config/quantflow.yaml:25-27`
- Modify: `src/quantflow/config/loader.py:74-96`
- Test: `tests/config/test_config.py`

- [ ] **Step 1: Update `quantflow.yaml` logging section**

Change `level: INFO` to `console_level: INFO`, add `file_enabled: true` and `file_level: DEBUG`.

- [ ] **Step 2: Update `ConfigLoader._get_defaults()`**

Change `"logging": {"level": "INFO"}` to:
```python
"logging": {
    "console_level": "INFO",
    "file_enabled": True,
    "file_level": "DEBUG",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
},
```

- [ ] **Step 3: Add `ConfigLoader.get_logging_config()` method**

```python
def get_logging_config(self) -> dict:
    config = self.load()
    return config.get("logging", {})
```

- [ ] **Step 4: Update tests in `tests/config/test_config.py`**

- Add `TestConfigLoaderGetLoggingConfig` class with 3 tests: config from YAML, defaults when no section, defaults when missing file
- Update `TestConfigLoaderGetDefaults.test_defaults_structure`: `"level"` -> `"console_level"`
- Update `TestConfigLoaderLoad.test_missing_file_returns_defaults`: `"level"` -> `"console_level"`

- [ ] **Step 5: Run tests**

Run: `pytest tests/config/test_config.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add config/quantflow.yaml src/quantflow/config/loader.py tests/config/test_config.py
git commit -m "feat: update logging config, add ConfigLoader.get_logging_config()"
```

---

### Task 2: Create `config/logging.py` — `setup_logging()`

**Files:**
- Create: `src/quantflow/config/logging.py`
- Modify: `src/quantflow/config/__init__.py`
- Test: `tests/config/test_config.py`

- [ ] **Step 1: Write failing tests for `setup_logging()`**

Add `TestSetupLogging` class to `tests/config/test_config.py` with tests:
- `test_creates_log_file` — verifies path is `output_dir / logs / {run_label}_*.log`
- `test_log_file_receives_output` — writes via logger, reads file, checks content
- `test_creates_logs_subdirectory` — `(tmp_path / "logs").is_dir()`
- `test_returns_none_when_file_disabled` — mock ConfigLoader with `file_enabled: False`
- `test_log_filename_contains_timestamp` — regex `r"\d{8}_\d{6}"` in middle
- `test_file_handler_uses_file_level` — logger.debug() appears in file
- `test_graceful_fallback_on_permission_error` — mock Path.mkdir to raise OSError, returns None

- [ ] **Step 2: Create `src/quantflow/config/logging.py`**

Function signature: `setup_logging(output_dir: Path, run_label: str) -> Optional[Path]`

Logic:
1. Read config via `ConfigLoader().get_logging_config()`
2. Set root logger to DEBUG level
3. Add StreamHandler at `console_level` (default INFO)
4. If `file_enabled` (default True): create `output_dir / logs /` dir, add FileHandler at `file_level` (default DEBUG) with path `{run_label}_{YYYYMMDD_HHMMSS}.log`
5. Apply `format` to both handlers
6. OSError during dir/file creation: log warning, return None
7. Return log file path or None

- [ ] **Step 3: Update `src/quantflow/config/__init__.py`**

Add `from .logging import setup_logging` and update `__all__`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/config/test_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantflow/config/logging.py src/quantflow/config/__init__.py tests/config/test_config.py
git commit -m "feat: add config/logging.py with setup_logging() for dual handler logging"
```

---

### Task 3: Migrate CLI `print()` to `logger.info()` and add `setup_logging()`

**Files:**
- Modify: `src/quantflow/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Add `TestCLILogFile` class to `tests/test_cli.py`:
- `test_stock_scan_creates_log_file` — mock DataSourceFactory, run stock_scan with --output, verify `logs/stock_scan_NVDA.US_*.log` exists and contains "Scan Result" and "Data source:"
- `test_watchlist_run_creates_log_file` — mock Executor + MarkdownReporter, verify `logs/watchlist_run_WL_*.log` exists and contains "Execution complete"
- `test_task_run_creates_log_file` — mock Orchestrator, verify `logs/task_run_test_tasks_*.log` exists

- [ ] **Step 2: Modify `cli.py`**

Changes:
1. Add `from quantflow.config.logging import setup_logging` import
2. Remove `logging.basicConfig(level=logging.INFO)`
3. `stock_scan()`: move `output_dir` calc before fetch, add `setup_logging(output_dir, f"stock_scan_{safe_code}")`, replace all `print()` with `logger.info()`, remove duplicated empty-data check (lines 69-75)
4. `watchlist_run()`: add `setup_logging(Path(args.output), f"watchlist_run_{watchlist.name}")` after loading watchlist, replace `print()` with `logger.info()`
5. `task_run()`: add `setup_logging(Path(args.output or "./output"), f"task_run_{Path(args.config).stem}")`, keep `logger.error()`
6. `web()` and `__main__`: keep `print()` as-is

- [ ] **Step 3: Update existing CLI tests**

After print->logger migration, messages go to stderr (StreamHandler), not stdout. Update:
- `TestCLICommandRouting`: check `result.stderr` or combined output
- `TestCLIOutputFormat`: patch stderr instead of stdout, or check logger output
- `TestCLIExecutionIntegration`: check combined `result.stdout + result.stderr`

- [ ] **Step 4: Run CLI tests**

Run: `pytest tests/test_cli.py -v -k "not integration"`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/quantflow/cli.py tests/test_cli.py
git commit -m "feat: migrate CLI print() to logger.info(), add setup_logging() calls"
```

---

### Task 4: Add `setup_logging()` to Web RunEngine

**Files:**
- Modify: `src/quantflow/web/engine/run_engine.py`
- Test: `tests/web/test_runs_engine.py`

- [ ] **Step 1: Write failing test**

Add `TestRunEngineLogging` to `tests/web/test_runs_engine.py`:
- `test_stock_scan_creates_log_file` — create RunHistory entry, mock DataSourceFactory, call `_exec_stock_scan()`, verify `logs/stock_scan_NVDA.US_*.log` exists

- [ ] **Step 2: Modify `run_engine.py`**

Add at the start of `_execute_run()`, after getting the run object:

```python
from quantflow.config.logging import setup_logging

output_path = run.config.get("output_path", "./output")
if run.run_type == "stock_scan":
    label = f"stock_scan_{run.config.get('code', 'unknown').replace('/', '_').replace(chr(92), '_')}"
elif run.run_type == "watchlist_run":
    wl_name = Path(run.config.get("watchlist", "unknown")).stem
    label = f"watchlist_run_{wl_name}"
elif run.run_type == "task_run":
    label = f"task_run_{Path(run.config.get('task_config', 'unknown')).stem}"
else:
    label = run.run_type
setup_logging(Path(output_path), label)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/web/test_runs_engine.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/quantflow/web/engine/run_engine.py tests/web/test_runs_engine.py
git commit -m "feat: add setup_logging() to Web RunEngine for persistent log files"
```

---

### Task 5: Full test suite + lint verification

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v -k "not integration" --timeout=60`
Expected: All PASS

- [ ] **Step 2: Run ruff lint**

Run: `ruff check src/`
Expected: No errors

- [ ] **Step 3: Final commit if any fixes needed**
