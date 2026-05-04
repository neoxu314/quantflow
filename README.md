# Quantflow

Stock Quantitative Analysis System for A-share, US, and HK markets.

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

1. **Python Environment**: Python 3.9 or higher.
2. **Dependencies**:
   ```bash
   pip install pandas numpy pyyaml baostock yfinance
   ```
3. **Stock Code Format**:
   The system strictly requires standard formats. Do **not** use standalone codes (e.g., just `MSFT`).
   *   **A-Share**: `{code}.{exchange}` (e.g., `600519.SH` or `002594.SZ`)
   *   **US/HK**: `{code}.{market}` (e.g., `NVDA.US` or `00700.HK`)

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
├── watchlists/          # 👈 Stock lists go here
│   ├── us_tech.yaml
│   └── a_value.yaml
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
    output: "output/us_signals"            # Result save path
    # days_back: 300                        # Optional: override auto-calculated lookback
```
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
    chunk_size: 50              # tickers per yf.download() call
    sleep_min: 5                # minimum seconds between batches
    sleep_max: 12               # maximum seconds (jitter for human-like behavior)
```

For a watchlist of 700 mixed stocks, the system partitions by data source:
- **yFinance stocks** (HK/US/JP/KR): fetched in batches of 50 with 5–12s random sleep between batches.
- **BaoStock stocks** (A-share): fetched sequentially (unchanged).

This means a 700-stock list with 200 yFinance stocks takes ~6-8 minutes with jittered delays, avoiding rate-limit detection.

## 2. Execution (Commands)

You can run scans manually or via automation. Run these from the project root directory (`quantflow/`).

### Command 1: Single Stock Scan
For quick, ad-hoc analysis of one stock (outputs indicator values).
```bash
python -m quantflow.cli stock_scan --code NVDA.US
```
- `--code`: Stock code (Standard format, e.g., `600519.SH` for A-share, `NVDA.US` for US).
- `--start`: Start date for data (YYYY-MM-DD). Default: 1 year ago.
- `--end`: End date. Default: Today.
- `--indicator`: Indicators to calculate (default: `kdj,dual_line`).

### Command 2: Run Orchestration Tasks (Recommended)
This runs the strategies defined in your `tasks_*.yaml` file, producing both **per-task** and **combined** outputs.
```bash
# Default: outputs per-task to paths defined in tasks_*.yaml
python -m quantflow.cli task_run --config config/tasks_us_mac.yaml

# Combined: specify a combined-report base directory
python -m quantflow.cli task_run --config config/tasks_us_mac.yaml --output ./summary

# Daily Archive: inject today's date into ALL output paths
python -m quantflow.cli task_run --config config/tasks_us_mac.yaml --output ./summary --daily
```

**Parameters:**

| Parameter | Required | Description |
| :--- | :--- | :--- |
| `--config` | Yes | Path to your task orchestration YAML file (e.g., `config/tasks_asia_mac.yaml`). |
| `--output` | No | Base directory for combined report. Default: `reports`. |
| `--daily` | No | **Auto-archive**: appends today's date (`YYYY-MM-DD`) to all output paths (both sub-task and combined). |
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

## 3. Output & Results

The system produces **two tiers** of output for each run:

### Tier 1: Per-Task Output (Sub-task level)
Each task in your config file generates its own JSON + Markdown report to its configured `output` path.
*   **Path**: `{tasks output}/{task_name}.json` (or `{output}/{date}/` if `--daily`)
*   **Contains**: Raw results + individual Markdown report for that specific task.

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

## 4. Automation (Cron)

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

## 5. Web UI

QuantFlow provides an optional web UI for managing watchlists, tasks, and system settings visually.

```bash
# Install dependencies (includes fastapi, uvicorn)
pip install -e .

# Start the Web UI
python -m quantflow.cli web
```

- **Default URL**: http://127.0.0.1:8080 (auto-opens in browser)
- **Configuration**: Set port/host in `config/quantflow.yaml` under `web:` section

### UI Features

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
   - Fixed-width table columns with text wrapping/truncation

3. **Settings** (Interactive Form):
   - **Editable sections**: Data Sources, Lookback Period, YFinance Batch, Web Server, Tushare Token, Logging Level
   - **Read-only display**: Config file path
   - **Token management**: Toggle visibility (👁️) and copy (📋)
   - **Save/Reset**: Save button appears on modification; requires restart for Web/Port changes
   - **API**: `GET /api/config` (read), `PUT /api/config` (update YAML)
4. **Library** (Strategy & Indicator Catalog):
   - **Strategy Library**: View all registered strategies with descriptions, signal types, required indicators, and lookback days
   - **Indicator Library**: Browse all available indicators with parameters, inputs/outputs, and lookback requirements
   - **Parameter Editing**: Click "Edit Params" on any indicator to modify its configuration, persisted to `config/indicators.yaml`
5. **Runs Panel** (New Run History):
   - **New Run Wizard**: Create runs for `stock_scan`, `watchlist_run`, or `task_run` via guided form
   - **Stock Scan**: Outputs indicator calculation results (KDJ, MACD, DualLine, etc.), not strategy signals — consistent with CLI `stock_scan`
   - **Watchlist Run**: Runs watchlist with selected strategies, outputs JSON + Markdown report — consistent with CLI `watchlist_run`
   - **Task Run**: Executes task file via Orchestrator — consistent with CLI `task_run`
   - **Run History**: List of all runs with status, signal count, config details, progress log, report/files browser
   - **Run Details**: 4 sub-tabs — Config, Progress (SSE real-time log), Report (indicator table for stock_scan, Markdown for others), Files

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/watchlists/` | GET, POST, PUT, DELETE | Watchlist CRUD |
| `/api/watchlists/search` | POST | Search stock across all lists |
| `/api/tasks` | GET, POST, PUT, DELETE | Task CRUD |
| `/api/task-files` | GET, POST, DELETE | Task file management |
| `/api/config` | GET, **PUT** | System configuration (read + **write**) |
| `/api/strategies` | GET | Available strategy list |
| `/api/library/strategies` | GET | Strategy catalog with descriptions, indicators, lookback |
| `/api/library/indicators` | GET | Indicator catalog with params, fields, lookback |
| `/api/library/indicators/params` | PUT | Update indicator parameter configuration |
| `/api/runs/` | GET, POST, DELETE | Run history CRUD + create runs |
| `/api/runs/{id}` | GET | Single run details |
| `/api/runs/{id}/indicator-data` | GET | Indicator results for stock_scan runs |
| `/api/runs/{id}/report` | GET | Markdown report for watchlist/task runs |
| `/api/runs/{id}/files` | GET | Output file listing |
| `/api/runs/{id}/logs:sse` | GET | SSE real-time progress log |
| `/api/runs/{id}/cancel` | POST | Cancel running/queued run |
| `/api/browse/` | GET | Directory browsing for file picker |
