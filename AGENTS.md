# QuantFlow development guide

The installed package lives in `src/quantflow/`. See the [README](README.md) for usage,
[architecture](docs/架构.md) for the module map, and
[reliability and data contracts](docs/reliability-and-data-contracts.md) for behavior
shared across CLI, Web and storage.

## Working in the repository

- Install with `python -m pip install -e .` on Python 3.10 or newer. Install test dependencies
  from `requirements-test.txt`. On macOS use an OpenSSL-linked Python in a virtual environment.
- Declare dependencies and packaging changes in `pyproject.toml`. Preserve the `py.typed`
  marker. Ruff settings live in `pyproject.toml`.
- Use `sort_keys=False` and `default_flow_style=False` for emitted configuration YAML.
- Use `DataSourceFactory` for market routing, `StockCode` for normalized codes, and the
  configured adjustment mode. Keep provider symbols at the adapter boundary.
- Use `IndicatorFactory` and shared lookback calculation. Keep each strategy's required
  indicators explicit and evaluate strategies independently.
- Frontend source is `src/quantflow/web/static/{app,utils}.ts`. Rebuild the tracked
  JavaScript when emitted code changes. The [README](README.md#testing) has the commands.

## Runtime invariants

- Put artifacts under `<base>/[date/]runs/<run_id>/`. Register owned outputs in the manifest.
  Delete only manifest-owned, unchanged files after the worker exits. Preserve user additions,
  user edits, symlinks and legacy shared outputs.
- Distinguish analyzed no-signal from missing, stale, insufficient or erroneous data.
  Propagate failures to persist required output, and keep the queue slot until the active
  worker stops.
- Freeze run configuration, strategy parameters and completed trading days. Resume validates
  the run plan and execution identity, including a hash of Python source bytes, and requires
  valid snapshots for completed stocks.
- Data windows are inclusive, daily execution uses complete trading sessions, and adapters
  normalize volume to shares. Keep adjustment, provider, dates and value units traceable.

## Verification

`python -m pytest` runs the offline Python suite against isolated project and home directories.
Opt into browser checks with `--run-browser` and live-provider checks with
`--live-market -m integration`. Frontend Vitest cases run from `tests/web/frontend/`.

Choose the layer that proves the behavior. Use fixed bars for expected signals, backend tests
for validation and persistence, and browser tests for cross-layer flows. See the
[Web test matrix](tests/web/TEST_MATRIX.md) and [CLI result tests](tests/CLI_TODO_TESTS.md).
