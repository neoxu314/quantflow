# Web test maintenance

See the [test matrix](TEST_MATRIX.md) for the coverage map and the
[README](../../README.md#testing) for installation and commands.

- Use the default offline pytest suite for FastAPI, worker, state and persistence
  contracts. Use the test project and state paths rather than paths from a live checkout.
  Explicit worker tests wait for their workers to exit.
- Browser and Web system cases in `e2e/` opt in with `--run-browser`. The fixtures
  start per-test loopback servers with a temporary project, home directory and
  a free port. A restart test stops only its own server.
- Use fixed market inputs for deterministic assertions. Market fixtures replace
  provider I/O so indicators, strategies, progress, reports and storage follow the
  production flow. Use an `integration` marker and `--live-market` for actual provider checks.
- Use `frontend/` for Vitest coverage of actual frontend modules. Browser cases should
  check the user-visible result and, where necessary, the corresponding persisted state.
- For run regressions verify the terminal status, progress or error, coverage,
  and the owned output files relevant to the behavior. A successful HTTP response
  alone only proves request handling.
