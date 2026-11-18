# Run Logging Design — Persistent Log Files for All Run Types

**Date:** 2026-05-18
**Status:** Draft

> **Implementation update (2026-11-18):** File logging is implemented. `setup_logging()` now removes prior quantflow handlers before adding new ones (prevents cross-run log leakage in the long-running Web server), and the resolved path is persisted to `run_history.log_path`. The Web UI Progress tab reads this file directly via `GET /api/runs/{id}/logs?tail=N` — the black log box shows byte-exact on-disk content, no longer the SSE `log` summary events. See root `AGENTS.md` and `src/quantflow/web/AGENTS.md` for the current behavior.

## Problem

CLI and Web UI runs produce no persistent log files. All logging goes to stderr/stdout (CLI) or ephemeral SSE events (Web). After a run completes, there is no way to review what happened — which stocks failed to fetch, which data sources fell back, whether timeouts occurred, etc. This makes debugging difficult.

## Goal

After every `stock_scan`, `watchlist_run`, or `task_run` execution (via CLI or Web UI), create a structured log file in the same output directory containing all terminal output and more (DEBUG-level detail). The log file can be shared for post-mortem analysis.

## Approach: Hybrid — print→logger Migration + Dual Handler

Migrate CLI `print()` calls to `logger.info()`, then configure root logger with two handlers:

- **StreamHandler** (console): level controlled by `console_level` config (default INFO)
- **FileHandler** (file): level controlled by `file_level` config (default DEBUG)

This ensures the terminal stays clean while the log file captures everything.

## Design

### 1. Configuration Layer

**Activate dead `logging` config in `quantflow.yaml`:**

```yaml
logging:
  console_level: INFO    # Renamed from "level" — terminal StreamHandler level
  file_enabled: true     # New — whether to write log files
  file_level: DEBUG      # New — FileHandler level
  format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'  # Existing, now activated
```

**New module `config/logging.py`:**

- Function `setup_logging(output_dir: Path, run_label: str) -> Path | None`
  - Reads config via `ConfigLoader.get_logging_config()`
  - Configures root logger with StreamHandler (`console_level`) + FileHandler (`file_level`) if `file_enabled`
  - FileHandler path: `output_dir / logs / {run_label}_{YYYYMMDD_HHMMSS}.log`
  - Applies `format` to both handlers
  - Returns the log file path (or None if file logging disabled)
  - Creates `logs/` subdirectory if it doesn't exist

**`ConfigLoader` changes:**

- Add `get_logging_config() -> dict` method
- Rename default key `"level"` → `"console_level"` in `_get_defaults()`

### 2. CLI Layer

**print → logger migration in `cli.py`:**

- All `print()` calls → `logger.info()` (scan results, file paths, execution summaries, warnings)
- Exception: argparse `--help` output (handled by argparse itself, not our code)

**Log initialization:**

- Replace `logging.basicConfig(level=logging.INFO)` with `setup_logging(output_dir, run_label)` at the start of each command function
- `run_label` values:

| Command | run_label |
|---------|-----------|
| `stock_scan` | `stock_scan_{code}` |
| `watchlist_run` | `watchlist_run_{watchlist_name}` |
| `task_run` | `task_run_{config_stem}` |

**Log file examples:**

```
output/cli_scans/logs/stock_scan_600000.SH_20260518_143052.log
output/logs/watchlist_run_沪深300_20260518_143052.log
output/logs/task_run_tasks_us_mac_20260518_143052.log
```

### 3. Web Layer

**`RunEngine` changes:**

- Call `setup_logging(output_dir, run_label)` at the start of `_execute_run()`
- SSE publishing logic unchanged — browser gets real-time updates as before
- All `logger.*` calls automatically write to the log file via the FileHandler
- Run label follows the same naming convention as CLI

**Web log file examples:**

```
output/manual_scans/logs/stock_scan_600000.SH_20260518_143052.log
output/manual_watchlist/logs/watchlist_run_沪深300_20260518_143052.log
output/logs/task_run_tasks_us_mac_20260518_143052.log
```

### 4. Log File Naming & Lifecycle

**Naming pattern:** `{run_type}_{identifier}_{YYYYMMDD_HHMMSS}.log`

| Run Type | Example Filename |
|----------|-----------------|
| stock_scan | `stock_scan_600000.SH_20260518_143052.log` |
| watchlist_run | `watchlist_run_沪深300_20260518_143052.log` |
| task_run | `task_run_tasks_us_mac_20260518_143052.log` |

**Location:** Always in `logs/` subdirectory under the output directory, co-located with but separated from result files.

**Cleanup:** No automatic cleanup. Users manage manually. Web UI delete operations only remove result files, not the `logs/` directory.

### 5. Error Handling

- If log file creation fails (permissions, disk full), log a warning to stderr and continue without file logging — never block the actual run
- `setup_logging()` catches `OSError` and falls back gracefully

## Files Changed

| File | Change |
|------|--------|
| `config/quantflow.yaml` | Update `logging` section (rename `level`→`console_level`, add `file_enabled`, `file_level`) |
| `src/quantflow/config/loader.py` | Add `get_logging_config()`, update `_get_defaults()` |
| `src/quantflow/config/logging.py` | **New** — `setup_logging()` |
| `src/quantflow/cli.py` | Migrate `print()` → `logger.info()`, replace `basicConfig` with `setup_logging()` |
| `src/quantflow/web/engine/run_engine.py` | Add `setup_logging()` call at run start |

## Out of Scope

- Log rotation / size limits (YAGNI — runs are finite duration)
- Structured/JSON logging format
- Remote log shipping
- Log viewer UI in Web
