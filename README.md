# QuantFlow

Daily-bar research and watchlist monitoring for mainland China, Hong Kong, the US, Japan and
South Korea. QuantFlow computes technical indicators and strategy signals, then saves Markdown
reports, structured results and the inputs used to produce them.

- [Architecture and module map](docs/架构.md)
- [Run, data and recovery contracts](docs/reliability-and-data-contracts.md)
- [Daily operation and scheduling](docs/daily_run.md)
- [Maintenance backlog and report review](docs/follow-up-and-ai-review.md)

## Installation

The package requires Python 3.10 or later. The pinned test environment uses Python 3.12.
From a source checkout:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On macOS, `brew install python@3.12` is one way to obtain a suitable Python. The wheel includes
Web assets and command entry points. Run the Web UI from the checkout to edit its YAML files.

For frontend changes, install the pinned TypeScript toolchain and rebuild both JavaScript files.

```bash
npm ci --prefix tests/web/frontend
tests/web/frontend/node_modules/.bin/tsc --project src/quantflow/web/static/tsconfig.json --removeComments
```

## Configuration

| File | Purpose |
| --- | --- |
| `config/quantflow.yaml` | Market sources, adjustment, lookback, logging, provider retry settings and Web host/port |
| `config/indicators.yaml` | Enabled indicators and parameter overrides |
| `config/tasks_*.yaml` | Named tasks with a watchlist, strategy IDs and optional `days_back` |
| `watchlists/*.yaml` | Stock lists with codes, optional names and tags |

Use stock codes such as `600519.SH`, `002594.SZ`, `NVDA.US`, `00700.HK`, `000660.KS`
and `8035.T`. Input aliases `.KR` and `.JP` normalize to `.KS` and `.T`.
Adapters translate the normalized code to provider symbols.

The default primary/fallback pairs are BaoStock/Tushare for mainland China and
YahooQuery/YFinance for Hong Kong, the US, Japan and South Korea. An explicit YAML
`fallback: null` disables that market's fallback. A non-empty exported
`TUSHARE_TOKEN` takes precedence over `tushare.token` in the project configuration.
[Environment variable example](.env.example)

The executor derives lookback days from
`ceil(max_indicator_bars × calendar_multiplier) + buffer_days`, unless a positive override is
provided. Each market uses the most recent completed exchange session. See the data contracts
for daily-bar validation, provider-specific adjustment and bounded retry behavior.

The following example creates `watchlists/us_tech.yaml`.

```yaml
name: US_Tech_Leaders
items:
  - code: MSFT.US
  - code: NVDA.US
    name: Nvidia
    tags: [AI]
```

A task file can reference that watchlist.

```yaml
tasks:
  - name: US-Tech-Oversold
    watchlist: watchlists/us_tech.yaml
    strategies: [daily_bull_oversold]
    # days_back: 300
```

| Strategy ID | Signal |
| --- | --- |
| `daily_bull_oversold` | Short trend above the bull/bear line, KDJ J < 20 and close at or above the bull/bear line |
| `daily_bull_mid_range` | Bullish arrangement with close between the bull/bear and short trend lines, inclusive |
| `kdj_dead_cross` | KDJ K crosses below D |
| `dual_line_bear` | First bearish bar after a non-bearish bar (short trend below the bull/bear line) |

[Watchlist contents and index refresh commands](docs/stock-watchlist.md)

## Run from the command line

Run from the checkout root. Choose a small watchlist for a first live run.

```bash
python -m quantflow.cli scan --code NVDA.US --indicator kdj,dual_line
python -m quantflow.cli monitor --watchlist watchlists/personal_focus_us.yaml --strategies daily_bull_oversold
python -m quantflow.cli tasks --config config/tasks_test.yaml --output ./output --daily
```

The long subcommands are `stock_scan`, `watchlist_run` and `task_run`. The installed
commands are `quantflow-scan`, `quantflow-monitor`, `quantflow-tasks` and `quantflow-web`.
Use `--help` after a research subcommand for its arguments.

- **Scan** accepts `--start` and `--end` as inclusive output dates. The default end is the
  latest completed session and the default start is 365 days before the end. The scanner
  fetches warmup history and exports eligible bars within the interval.
- **Monitor** accepts `--days-back` and comma-separated `--strategies`. The default strategies
  are `daily_bull_oversold,daily_bull_mid_range`. It evaluates the latest completed bar.
- **Tasks** reads the specified YAML in order. `--daily` adds a local date directory above
  `runs/`. Task failures are reflected in combined coverage and the exit status.

Exit codes are `0` for completed, `2` for partial, `1` for failed and `130` for cancelled.

## Web UI

```bash
python -m quantflow.cli web
```

The repository config uses `127.0.0.1:8082`. Without Web settings the code defaults to
`127.0.0.1:8080`. On macOS, `start.command` launches using the existing `.venv`.
Restart an idle Web service to load updated Python code, then refresh the browser.

- **Watchlists** supports search, market-aware entry, batch import and in-place edits. Click
  **Save** to persist item changes.
- **Tasks** manages task files and their watchlists and strategies. Set the output base when
  submitting a Run.
- **Library** displays registered strategies and indicator parameters. Indicator changes apply
  to later calculations.
- **Settings** edits the project configuration. The API exposes whether a YAML Token is set.
  A blank Token field preserves the saved value. Reveal and copy act on the value entered in the form.
- **Runs** offers scan, watchlist and task forms, preflight, progress, logs, results, files and a
  directory picker. Presets and explicit Run cancellation are available through the API.

Download and analysis progress use separate counts. The Progress panel reads the real log
file and can recover its progress snapshot after a refresh. A partial, failed, cancelled or
interrupted strategy Run shows **Resume** when its checkpoint passes validation. Resume
creates a new Run with the original data cutoff and reuses verified results for completed
stocks. **Run Again** fills a form for a new run at a new cutoff.

Keep the service on loopback for local use. The Web app supports filesystem browsing and
editing project configuration and has no authentication layer.

## Outputs and history

| Run type | CLI default base | Web default base |
| --- | --- | --- |
| Stock scan | `<project>/output/cli_scans` | `<project>/output/manual_scans` |
| Watchlist run | `./output` from the working directory | `<project>/output/manual_watchlist` |
| Task run | `./output` from the working directory | `<project>/output` |

Each run owns `<base>/runs/<run_id>/`. Daily mode uses
`<base>/YYYY-MM-DD/runs/<run_id>/`. Web resolves a relative base from the checkout.
Use the Run's **Files** tab to locate its output folder.

| Artifact | Contents |
| --- | --- |
| `manifest.json` | Run ID, status and hashes of owned files |
| `<code>_indicators.json`, `<code>_context.json`, `<code>_snapshot.json` | Scan values, metadata and daily input |
| `cli-<watchlist>.json/.md` or `web-<watchlist>.json/.md` | Structured signal results and Markdown |
| `<task>.json/.md`, `Combined_Results.json`, `Daily_Report.md` | Per-task and combined strategy results |
| `Run_Summary.json`, `*_coverage.json`, `snapshots/` | Strategy run coverage, per-stock outcomes and inputs |
| `logs/` | Run log files when file logging is enabled |

Strategy JSON rows include the normalized code, trading date, actual provider, adjustment,
strategy names, indicator values and reasons. A completed run can contain zero signals.
Inspect coverage before interpreting a partial report.

Deleting a Web run removes its record and eligible unchanged files owned by its manifest.
User additions, edited files and unverifiable legacy shared files are preserved.
Web history, checkpoints and presets live under `~/.quantflow/`. Use the backup command
and verify the resulting directory.

```bash
python -m quantflow.backup
python -m quantflow.backup --verify /path/to/backup
```

[Operation and scheduling](docs/daily_run.md) ·
[Daily data, recovery and rebound study](docs/reliability-and-data-contracts.md)

## Testing

Install the pinned test tools from the repository root. This baseline was verified on Python 3.12.

```bash
python -m pip install -r requirements-test.txt
python -m pytest
```

By default, pytest runs offline Python tests, including a wheel smoke test. The test session
loads QuantFlow from a temporary copy with test configuration and a separate home directory.
Offline Python requests to external hosts fail the test, including attempts caught by
application code. Tests may communicate with local fixture servers over loopback.

```bash
# Run a focused test or measure Python coverage
python -m pytest tests/test_packaging.py
python -m pytest --cov

# Run live provider checks explicitly
python -m pytest --live-market -m integration

# Set up Playwright Chromium and run Web system and browser tests without live market data
python -m playwright install chromium
python -m pytest --run-browser tests/web/e2e

# Use installed Chrome if preferred
python -m pytest --run-browser tests/web/e2e --browser-channel chrome

```

Browser workflow tests replay fixed daily bars and use local visibility styles for panels and
dialogs. Live provider checks run separately. Use `TUSHARE_TOKEN` in the test process
environment only when running live Tushare checks. The wheel smoke test builds and installs into a
temporary directory, verifies the installed command entry points, and loads the homepage and
JavaScript from the installed package.

```bash
cd tests/web/frontend
npm ci
npm test
```

The GitHub Actions workflow is configured to run these offline and browser checks on pushes and pull requests.
It also compares bundled JavaScript against a fresh TypeScript build and saves test reports.

See [the Web test matrix](tests/web/TEST_MATRIX.md) for end-to-end paths and
[the CLI test notes](tests/CLI_TODO_TESTS.md) for the fixed-market signal and backtest cases.
