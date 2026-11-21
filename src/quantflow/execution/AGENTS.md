# Execution

`ExecutionJob` supplies items, strategies, an output directory and a calendar-day lookback.
It can also specify an adjustment, as-of time or end date.
`scanner.py` handles individual indicator scans, while `Executor` handles watchlist and task
jobs. Both use the market contract for the last completed trading day and normalized inputs.

- Fetch in bounded batches of up to 50 where the configured provider supports batch
  requests. Process and persist each batch before fetching the next. Fetch other items
  individually. The provider may split execution batches into smaller requests.
- Instantiate indicators from the frozen configuration for the strategy dependencies.
  Evaluate each strategy separately. Classify every stock outcome, including those
  missing data or prerequisites. `ScanResults` is a list of signal items with additional
  per-stock outcomes and summary counters.
- Publish download and analysis progress separately. `ProgressEvent` carries enough
  information for the Web engine to update the current phase and counters.
- `Storage` and the shared artifact writer persist outputs. Required writes propagate failures.
  `Checkpoint` stores per-task analyzed codes and their results in
  `~/.quantflow/checkpoints/<run_id>.json`. See `run:plan`, `execution:<task_key>`
  and `orchestration:as_of` for plan, execution identity and shared cutoff.
  Task Run inputs live in `snapshots/<number>/<code>.json` under the run directory. Watchlist Run uses the watchlist job name in place of the number.
- Resume verifies the recorded plan and calculation fingerprint, then clones snapshots before enqueue.
  Reuse successful items only after validating their saved input snapshots. Retry unfinished
  stocks against the original cutoff. Separate manifests track each run's artifact ownership.
- Run `python -m pytest tests/execution tests/test_rebound_workflows.py`.
  See [reliability and data contracts](../../../docs/reliability-and-data-contracts.md).
