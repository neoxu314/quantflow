# Markdown reports

- `MarkdownReporter.generate()` renders one task or watchlist, and
  `generate_combined()` renders the combined task report. Both consume execution
  results and watchlist metadata in memory.
- Separate buy and sell signals. Within each direction group stocks by the set of
  matched strategies and show multi-strategy groups first. Names and tags are taken
  from the watchlist when available.
- Retain coverage and per-stock issue information when there are zero signals.
  Coverage distinguishes analyzed no-signal stocks from failed or inadequate inputs.
- Task Run supplies a numbered task directory and the `report` file stem to
  `generate()`. The task name remains the report title. Watchlist Run uses its
  job name as the file stem. Write via the shared atomic writer and retain
  manifest ownership, following the
  [run artifact contract](../../../docs/reliability-and-data-contracts.md).
- Run `python -m pytest tests/reports tests/test_rebound_workflows.py`.
