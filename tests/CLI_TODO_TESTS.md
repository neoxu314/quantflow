# CLI and Web result tests

The fixed-market cases in [test_rebound_workflows.py](test_rebound_workflows.py) replace
the skipped Watchlist Run and Task Run placeholders. Both entry points run the real
indicators, strategy, executor, artifact writer and report generator. The Web cases also
start real workers and write checkpoints.

The fictional market in [replay_market.py](support/replay_market.py) has a rising baseline and
an explicit six-session pullback for AAPL.US. On 2025-06-04, the close is 139.50, the DualLine
support is approximately 136.63, the short trend line is approximately 140.01, and KDJ J is
approximately 4.40. Those inputs meet all three conditions. The trend-only MSFT.US
series produces no signal. A symbol with no bars tests partial and failed status.

[The backtest cases](backtest/test_rebound.py) check entry on the next session, 5/10-session
exits, costs, overlap, the market holiday and the cutoff at the end of a sample. The CLI case
also verifies the saved input hash. These assertions cover calculation and report contracts.
Provider checks use the separate live-market command in the [README](../README.md).
