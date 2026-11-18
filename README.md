# Quantflow

Stock Quantitative Analysis System for A-share, US, HK, KR, and JP markets.

## Architecture

Quantflow adopts a layered architecture designed for flexibility and extensibility:

```
src/quantflow/
├── data/               # Data fetching (BaoStock, Tushare, YFinance, etc.)
├── indicators/         # Technical analysis (KDJ, MACD, DualLine, etc.)
├── strategies/         # Signal generation (Buy/Sell logic)
├── execution/          # Execution layer: runs jobs and saves results
├── orchestration/      # Orchestration layer: manages tasks via YAML
├── web/                # Web UI server (FastAPI + frontend)
└── reports/            # Report layer: generates human-readable Markdown reports
```

## 0. Prerequisites

Before running tasks, ensure your environment is ready:

1. **Python Environment**: Python 3.9 or higher. **macOS users must use Homebrew Python + venv** (system Python 3.9 ships with LibreSSL 2.8.3, which is incompatible with urllib3 v2 and causes intermittent yfinance batch download errors):
   ```bash
   # macOS: Install Homebrew Python (linked with OpenSSL, not LibreSSL)
   brew install python@3.12

   # Create and activate a virtual environment
   /opt/homebrew/bin/python3.12 -m venv .venv
   source .venv/bin/activate
   ```
2. **Dependencies**:
   ```bash
   pip install -e .
   ```
3. **TypeScript Compiler (Web UI only)**: The Web UI frontend is written in TypeScript (`app.ts`, `utils.ts`) and served as compiled JavaScript. The generated `utils.js` is **gitignored**, so it is NOT present after cloning — you must compile the frontend before starting the Web UI, or the buttons will not respond (the browser fails to load `./utils.js`).
   ```bash
   # Install the TypeScript compiler (once):
   npm install -g typescript     # or: brew install typescript

   # From the project root, compile the frontend:
   tsc --project src/quantflow/web/static/tsconfig.json
   ```
   This generates `app.js` and `utils.js` in `src/quantflow/web/static/`. Re-run the `tsc` command after editing any `.ts` file.
4. **Stock Code Format**:
    The system strictly requires standard formats. Do **not** use standalone codes (e.g., just `MSFT`).
    *   **A-Share**: `{code}.{exchange}` (e.g., `600519.SH` or `002594.SZ`)
    *   **US/HK**: `{code}.{market}` (e.g., `NVDA.US` or `00700.HK`)
    *   **KR (Korea)**: `{code}.KR` (e.g., `000660.KR` for SK Hynix, auto-converted to `000660.KS`)
    *   **JP (Japan)**: `{code}.JP` (e.g., `8035.JP` for Tokyo Electron, auto-converted to `8035.T`)

## 1. Configuration

The system is driven by configuration files. All your "what to monitor" logic goes here.

### Directory Layout
It is recommended to store your input files as follows:

```text
quantflow/
├── config/              # System configs
│   ├── tasks_*.yaml     # Task orchestration files (e.g., tasks_asia_mac.yaml, tasks_us_mac.yaml)
│   ├── quantflow.yaml   # Global settings (lookback, etc.)
│   └── indicators.yaml  # Indicator parameter overrides
├── watchlists/          # 👈 Stock lists go here (includes pre-built A-share indices)
│   ├── us_tech.yaml
│   ├── a_value.yaml
│   ├── hushen_300.yaml       # CSI 300 constituents (280 stocks)
│   ├── zhongzheng_500.yaml   # CSI 500 constituents (425 stocks)
│   └── chuangyeban.yaml      # ChiNext index constituents (100 stocks)
├── output/              # 👈 Sub-task results (per-task JSON + MD)
│   ├── a_stocks/
│   │   └── 2026-05-01/  # Auto-created with --daily
│   └── us_stocks/
├── scripts/            # Build verification utilities
└── reports/             # 👈 Combined daily reports (--output + --daily)
    └── 2026-05-01/
        ├── Daily_Report.md
        └── Combined_Results.json
```

### Pre-built Watchlists

The system includes pre-built A-share index constituent watchlists:

| Watchlist | Index | Constituents | Update Method |
|-----------|-------|-------------|---------------|
| `hushen_300.yaml` | CSI 300 (沪深300) | 280 stocks | `python -m quantflow.data.fetch_cn_indices` |
| `zhongzheng_500.yaml` | CSI 500 (中证500) | 425 stocks | `python -m quantflow.data.fetch_cn_indices` |
| `chuangyeban.yaml` | ChiNext (创业板指) | 100 stocks | `python -m quantflow.data.fetch_cn_indices` |

**Update all A-share indices:**
```bash
python -m quantflow.data.fetch_cn_indices
```

This fetches latest constituents from akshare API and updates the YAML files.

### Watchlist Configuration
A watchlist defines **which stocks** to monitor.
Create a YAML file in `watchlists/`, e.g., `us_tech.yaml`:

```yaml
# watchlists/us_tech.yaml
name: "US_Tech_Leaders"
items:
  - code: "MSFT.US"
  - code: "NVDA.US"
    name: "Nvidia"
    tags: ["AI"]
```

> **Note**: Codes must follow the strict format defined in **Prerequisites** (e.g., `NVDA.US`). Using `NVDA` or `MSFT` alone will cause data fetching errors.

### Task Orchestration Configuration
A task file defines **how** to process a watchlist (which strategy to use, where to save results).
Create a YAML file in `config/`, e.g., `tasks_us.yaml`:

```yaml
# config/tasks_us.yaml
tasks:
  - name: "US-Tech-Oversold"
    watchlist: "watchlists/us_tech.yaml"   # Path to watchlist file
    strategies: 
      - "daily_bull_oversold"              # Strategy ID
    # days_back: 300                        # Optional: override auto-calculated lookback
```

**Output Path**: Specified via CLI/Web `--output` parameter (default: `./output`). All tasks output to the same directory, differentiated by file names.
- **Available Strategy IDs:**
- `daily_bull_oversold`: Buy when KDJ(J)<20 in a bullish channel.
- `daily_bull_mid_range`: Buy when price stabilizes between trend lines in a bull channel.
- `kdj_dead_cross`: KDJ Dead Cross (sell signal).
- `dual_line_bear`: DualLine Bear Zone Exit (sell signal).

### Data Lookback (Auto-Calculation)
The system automatically calculates how many calendar days of historical data to fetch based on each indicator's `lookback_bars` requirement:

```
actual_days = ceil(max_indicators_bars × calendar_multiplier) + buffer_days
```

These values are configured in **`config/quantflow.yaml`** (defaults: `calendar_multiplier: 2`, `buffer_days: 30`). You can override per-task by setting `days_back` in your task config file.

### Rate Limit Protection (YFinance)
Yahoo Finance enforces strict rate limits (60 req/min, 360/hr). The system automatically protects against 429 errors by chunking batch requests with randomized jitter sleep:

```yaml
# config/quantflow.yaml
yfinance:
  batch:
    chunk_size: 35              # tickers per yf.download() call
    sleep_min: 10               # minimum seconds between batches
    sleep_max: 20               # maximum seconds (jitter for human-like behavior)
```

For a watchlist of 700 mixed stocks, the system partitions by data source:
- **yFinance stocks** (HK/US/JP/KR): fetched in batches of 35 with 10–20s random sleep between batches.
- **BaoStock stocks** (A-share): fetched sequentially (unchanged).

This means a 700-stock list with 200 yFinance stocks takes ~8-12 minutes with jittered delays, avoiding rate-limit detection.

## 2. Execution (Commands)

You can run scans manually or via automation. Run these from the project root directory (`quantflow/`).

### Command 1: Single Stock Scan
For quick, ad-hoc analysis of one stock (outputs indicator values to JSON file).
```bash
python -m quantflow.cli stock_scan --code NVDA.US
python -m quantflow.cli stock_scan --code 002594.SZ --indicator kdj,macd --output ./my_results
```
- `--code`: Stock code (Standard format, e.g., `600519.SH` for A-share, `NVDA.US` for US).
- `--start`: Start date for data (YYYY-MM-DD). Default: 1 year ago.
- `--end`: End date. Default: Today.
- `--indicator`: Indicators to calculate (default: `kdj,dual_line`).
- `--output`: Output directory for JSON results (default: `output/cli_scans/`).

> **Note on date range**: `--start` / `--end` define the **report output date range**. The system automatically fetches additional historical data before `--start` as warmup for indicator calculation, based on the lookback formula. Only data within the user-specified range appears in the output.

> **Output format**: Generates `{code}_indicators.json` containing OHLCV + indicator values (K, D, J, MACD, etc.), consistent with Web UI stock_scan output.

### Command 2: Run Orchestration Tasks (Recommended)
This runs the strategies defined in your `tasks_*.yaml` file, producing both **per-task** and **combined** outputs.
```bash
# Default: outputs all tasks to ./output/
python -m quantflow.cli task_run --config config/tasks_us_mac.yaml

# Custom: specify output directory
python -m quantflow.cli task_run --config config/tasks_us_mac.yaml --output ./summary

# Daily Archive: inject today's date into output path
python -m quantflow.cli task_run --config config/tasks_us_mac.yaml --output ./summary --daily
```

**Parameters:**

| Parameter | Required | Description |
| :--- | :--- | :--- |
| `--config` | Yes | Path to your task orchestration YAML file (e.g., `config/tasks_asia_mac.yaml`). |
| `--output` | No | Base directory for all task outputs. Default: `./output`. All tasks output to this directory, differentiated by file names (`{task_name}.md`, `Daily_Report.md`, `Combined_Results.json`). |
| `--daily` | No | **Auto-archive**: appends today's date (`YYYY-MM-DD`) to output path (e.g., `./output/2026-05-05/`). |
| `-h` | No | Display help information. |

*Note: If your tasks config file contains multiple tasks, this command will run them sequentially. A combined Markdown report is generated at the end of all tasks.*

### Command 3: Run Single Watchlist
For running a specific watchlist with strategies, saving JSON results + Markdown report.
```bash
python -m quantflow.cli watchlist_run --watchlist watchlists/us_tech.yaml --output ./output/manual_test
python -m quantflow.cli watchlist_run --watchlist watchlists/us_tech.yaml --strategies kdj_dead_cross --days-back 180
```
- `--watchlist`: Path to specific watchlist file.
- `--output`: Directory to save results (default: `./output`).
- `--strategies`: Comma-separated strategy IDs (default: `daily_bull_oversold,daily_bull_mid_range`).
- `--days-back`: Override auto-calculated lookback days (optional).

## 3. Web UI (Visual Interface)

QuantFlow provides an optional web UI for managing watchlists, tasks, runs, and viewing results.

### Starting the Web Server

```bash
# Install dependencies (includes fastapi, uvicorn)
pip install -e .

# Compile the TypeScript frontend (required on first run and after any .ts change).
# The generated utils.js is gitignored — without this step the UI buttons won't work.
npm install -g typescript          # one-time, if tsc is not installed
tsc --project src/quantflow/web/static/tsconfig.json

# Start the Web UI
python -m quantflow.cli web
```

> **Note**: `tsc --project ...` regenerates `app.js` and `utils.js` in `src/quantflow/web/static/`. `utils.js` is intentionally gitignored (build artifact), so every fresh clone must run this compile step. If you skip it, the page loads but every button is dead because the browser gets a 404 on `./utils.js`.

- **Default URL**: http://127.0.0.1:{port} (auto-opens in browser). Port configured in `config/quantflow.yaml` (default: 8082).
- **Configuration**: Set port/host in `config/quantflow.yaml` under `web:` section

### Web UI Features

1. **Watchlists Management**:
   - CRUD on `watchlists/*.yaml` files
   - Search stocks across all watchlists
   - Batch import
   - **Inline delete button** (×) on each watchlist in the left sidebar

2. **Tasks Management** (Left-Right Layout):
   - **Left sidebar**: List of task config files (`config/tasks_*.yaml`) with inline delete (×)
   - **Right panel**: Tasks table for the selected file
   - Create, edit, and delete tasks via a simplified form
   - Auto-select first task file on page load

3. **Runs Panel** (Run History & Execution):
   - **New Run Wizard**: Create runs for `stock_scan`, `watchlist_run`, or `task_run` via guided form
   - **Stock Scan**: Outputs indicator calculation results (KDJ, MACD, DualLine, etc.), not strategy signals
   - **Watchlist Run**: Runs watchlist with selected strategies, outputs JSON + Markdown report
   - **Task Run**: Executes task file via Orchestrator
   - **Run History**: List of all runs with status, signal count, config details
   - **Run Details**: 4 sub-tabs — Config, Progress, Report, Files
   - **Progress tab**: real-time progress bar (SSE) + the **actual on-disk log file** shown in the black box. The box displays the same content as `<output>/logs/*.log` (last 500 lines, refreshed every 2s while running) and is also available for finished/interrupted runs. Statuses: `queued`, `running`, `completed`, `failed`, `cancelled`, `interrupted`.
   - **Resume**: a failed/cancelled/interrupted `watchlist_run` or `task_run` gets a **⏵ Resume** button in the Config tab. It creates a new run that continues from a checkpoint, skipping stocks already completed (data window is frozen to the original run). Checkpoints live in `~/.quantflow/checkpoints/<run-id>.json`.
   - **Startup reconciliation**: on server start, any run left `running`/`queued` by a previous process (e.g. laptop lid closed) is marked `interrupted` so dead tasks don't linger in a running state.
   - **Presets**: Save and reuse run configurations

4. **Settings** (Interactive Form):
   - Editable sections: Data Sources, Lookback Period, YFinance Batch, Web Server, Tushare Token
   - Token management: Toggle visibility (👁️) and copy (📋)
   - Save/Reset: Save button appears on modification
   - API: `GET /api/config` (read), `PUT /api/config` (update YAML)

5. **Library** (Strategy & Indicator Catalog):
   - **Strategy Library**: View all registered strategies with descriptions, signal types, required indicators
   - **Indicator Library**: Browse all available indicators with parameters, inputs/outputs, lookback requirements
   - **Parameter Editing**: Click "Edit Params" on any indicator to modify configuration

6. **Directory Browser** (File Picker):
   - Navigate filesystem to select output paths
   - Create new directories inline
   - Available via browse icon in run wizard

### Web UI vs CLI: Output Paths

**Web UI uses different default output paths** to distinguish from CLI runs:

| Run Type | CLI Default | Web UI Default | Key Difference |
|----------|-------------|----------------|----------------|
| **stock_scan** | `PROJECT_ROOT/output/cli_scans` | `./output/manual_scans` | Absolute vs Relative |
| **watchlist_run** | `./output` | `./output/manual_watchlist` | Web adds `manual_watchlist` |
| **task_run** | `./output` | `./output` | Same (no difference) |

**Web UI File Naming:**
- stock_scan: `{code}_indicators.json` (same as CLI)
- watchlist_run: `web-{wl_name}.json` and `web-{wl_name}.md` (hyphen instead of colon, Windows-safe)
- task_run: Same as CLI

**Delete Behavior:**
When deleting run history from Web UI, the system uses **precise file deletion**:
- ✅ Deletes only generated output files (JSON, Markdown)
- ✅ Preserves output directory and user files
- ✅ Safe for shared output directories

**Example:**
```text
Web UI watchlist_run output:
  ./output/manual_watchlist/web-US_Tech.json
  ./output/manual_watchlist/web-US_Tech.md

Delete run from history:
  ✅ Deletes: web-US_Tech.json, web-US_Tech.md
  ✅ Preserves: ./output/manual_watchlist/ directory
  ✅ Preserves: Other user files in same directory
```

### Why Different Paths?

- **CLI**: Absolute paths for `stock_scan` (PROJECT_ROOT) ensure predictable location regardless of working directory
- **Web UI**: Relative paths (`./output`) provide flexibility and align with user's working directory
- **manual_ prefix**: Distinguishes Web UI runs from scheduled/CLI runs, prevents accidental overwrites

### Using Web UI for Runs

Via Web UI "Runs" panel:

1. **Create Run**:
   - Select run type (stock_scan, watchlist_run, task_run)
   - Configure parameters (code, watchlist, strategies)
   - Optionally specify custom `output_path`
   
2. **Execute**:
   - Run starts immediately or queues if another run is active
   - Real-time progress via SSE (Server-Sent Events)
   - View logs, progress bar, signal count
   
3. **View Results**:
   - Indicator data (stock_scan): JSON with calculated indicators
   - Files list: All generated JSON/Markdown files
   - Report: Markdown report content
   - Open folder: System file browser integration

4. **Manage History**:
   - Delete runs: Removes database record + output files
   - Preset system: Save run configuration for reuse

### FAQ: Output Paths

**Q: Why does Web UI use different paths than CLI?**

A: Web UI uses relative paths (`./output/manual_*`) to provide flexibility and align with the user's working directory. CLI uses `PROJECT_ROOT` for stock_scan to ensure predictable location regardless of working directory. The `manual_` prefix distinguishes manual Web runs from scheduled/CLI runs.

**Q: Can I use the same output_path for multiple runs?**

A: Yes, but files will be overwritten. Use different `output_path` values or the preset system to save configurations with unique output paths. RunHistory database tracks all runs regardless of output_path.

**Q: What happens when I delete a run from Web UI history?**

A: Web UI deletes only generated output files (JSON, Markdown), preserving the output directory and user files. This prevents accidental data loss in shared directories.

**Q: Why does watchlist_run use `web-{wl_name}` instead of `{wl_name}`?**

A: The `web-` prefix distinguishes Web UI runs from CLI runs. Hyphens replace colons for Windows filename compatibility (e.g., `web-US_Tech.json` instead of `web:US_Tech.json`).

**Q: How do I find files from a specific run?**

A: Use Web UI "Runs" panel → click run → "Files" tab to see all generated files. Click "Open Folder" to open the output directory in system file browser.

## 4. Output & Results

The system produces **two tiers** of output for each run:

### Tier 1: Per-Task Output (Sub-task level)
Each task generates its own Markdown report to the output directory.
*   **Path**: `{--output}/{task_name}.md` (or `{--output}/{date}/{task_name}.md` if `--daily`)
*   **Contains**: Individual Markdown report for that specific task.

### Tier 2: Combined Output (Aggregated level)
After all tasks complete, a combined JSON and `Daily_Report.md` are generated.
*   **Path**: `{--output}/` (or `{--output}/{date}/` if `--daily`)
*   **Files**: `Combined_Results.json`, `Daily_Report.md`
*   **Contains**: All signals aggregated across all tasks, grouped by task with summary statistics.
*   **Signal Grouping**: Signals are categorized by the combination of triggered strategies (e.g., **Oversold & MidRange** resonance is displayed before single-strategy signals). Stock names are included for readability.

### Markdown Report Example
The generated Markdown reports are structured for quick scanning:
```text
### 🔵 Buy - daily_bull_oversold & daily_bull_mid_range (1 stock)
| Code       | Name   | Market | Resonance | Reasons | Tags    |
|------------|--------|--------|-----------|---------|---------|
| 002594.SZ  | BYD    | SZ     | x2        | ...     | growth  |

### 🔵 Buy - daily_bull_oversold (5 stocks)
| Code       | Name   | Market | Resonance | Reasons | Tags    |
|------------|--------|--------|-----------|---------|---------|
| 000977.SZ  | Inspur | SZ     | -         | ...     | ai      |
```

### How to read the data?
The JSON file contains an array of signals with enriched strategy matching info:

```json
[
    {
        "code": "002594.SZ",
        "name": "BYD",
        "buy_signals": 2,
        "matched_buy_strategies": ["daily_bull_oversold", "daily_bull_mid_range"],
        "reasons": ["Oversold J=14.2 in bull channel"],
        "timestamp": "2026-05-01T10:16:13.373241"
    }
]
```

## 5. Automation (Cron)

To monitor daily with automatic date-based archiving:

1. **Crontab entry** (`crontab -e`):
```bash
# Run A-shares at 20:00 (Beijing Time) — auto-archives by date
00 20 * * * cd /path/to/quantflow && python -m quantflow.cli task_run --config config/tasks_asia_mac.yaml --output ./reports --daily >> /var/log/quantflow.log 2>&1
```

2. **Resulting structure** (each day creates a new folder):
```text
output/
└── a_stocks/
    ├── 2026-05-01/   # Today's sub-task results
    └── 2026-05-02/   # Tomorrow's
reports/
└── 2026-05-01/
    ├── Combined_Results.json
    └── Daily_Report.md
```

## 6. Testing

The project has comprehensive test coverage across all layers. Run tests with pytest:

```bash
# Run all tests
pytest tests/

# Run tests excluding integration (network-dependent)
pytest tests/ -m "not integration"

# Run CLI layer tests only
pytest tests/test_cli.py -v

# Run with coverage
pytest tests/ --cov=quantflow
```

### Test Coverage Summary

| Layer | Unit Tests | Integration Tests | Total |
|-------|-----------|------------------|-------|
| Data | 151 | 10 | 161 |
| Indicators | 112 | 14 | 126 |
| Config | 30 | 1 | 31 |
| Orchestration | 35 | 11 | 46 |
| Reports | 18 | 0 | 18 |
| CLI | 16 | 11 | 27 |
| Web | 42 + 26 + 4 | 137 (E2E) | 209 |
| **Total** | **354** | **174** | **528** |

### CLI Test Highlights

- **Structural validation**: 26 tests covering parameter parsing, command routing, output format
- **Reference value validation**: BYD (002594.SZ) 2026-04-01 KDJ values verified against TongDaXin reference (error <0.02%)
- **Pending tests**: watchlist_run and task_run expected signal counts (4 tests marked as `@pytest.mark.skip`, see `tests/CLI_TODO_TESTS.md`)

For detailed test coverage, see `AGENTS.md` and `tests/web/TEST_MATRIX.md`.
