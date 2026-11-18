# WEB RUN ENGINE

Authoritative contract: project `docs/reliability-and-data-contracts.md`.

- Worker owns the active slot until its finally block calls `queue.finish(run_id)`.
- Cancellation requests mark cancelling; active-run cancellation never dequeues. Checkpoints and required outputs stay available for inspection/retry.
- Initialization, logging setup, checkpoint loading and dispatch are inside the lifecycle exception/finally boundary.
- Run states: queued, running, cancelling, completed, partial, failed, cancelled, interrupted.
- Original RunHistory.config is immutable. Runtime output_path is a unique `<base>/[date/]runs/<id>` directory, separate from config.output_path.
- Manifest owns output files; no cleanup by mutable config names or broad directory deletion. Legacy shared files are preserved.
- CLI/Web stock scans share execution.scanner. Watchlist/task executions use explicit ScanResults coverage.
- API tests use temporary state; worker tests call _execute_run explicitly and join their threads.
- SSE fetch messages are stage logs; only completed analysis units advance stock completion progress.
