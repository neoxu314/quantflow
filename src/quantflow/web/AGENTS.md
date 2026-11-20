# QuantFlow Web app

`server.py` registers FastAPI routes, initializes the run engine and mounts static
assets from `static/`. The frontend is served as a single page at the root.
Keep the checked-in JavaScript in sync with `static/app.ts` and `static/utils.ts`.
The [README](../../../README.md#testing) contains the build and test commands.

## Application boundaries

- `api/watchlists.py` lists, searches, saves and deletes YAML watchlists. Name and
  tag edits update the in-page draft. The Save action submits a full replacement.
- `api/tasks.py` manages task files and the task records within them. Task records
  select a watchlist, strategies and optional `days_back`. Output belongs to the run.
- `api/library.py` provides the strategy and indicator catalog and indicator settings.
  `api/config.py` reads and writes system settings. The token is write-only.
  Omission or an empty string preserves it, and explicit `null` clears the file value.
- `api/runs.py` handles runs, queues, reports, log streams, checkpoints and outputs.
  `api/presets.py` launches saved configurations through the run creation path.
  Validate both paths with the shared preflight checker.
- `api/browse.py` lists directories and creates folders. This is a local application
  with access to the user's filesystem. The default Web bind address is loopback.

## Run detail and persistence

- The Progress tab reads file logs from `GET /api/runs/{id}/logs?tail=N`
  (`tail=0` requests the full file). SSE `GET /api/runs/{id}/logs:sse`
  provides progress and status. The run detail API carries the current progress
  snapshot for polling when the stream is unavailable.
- Resume is for watchlist and task runs in `failed`, `partial`, `cancelled` or
  `interrupted` with a usable checkpoint. It creates a new run and verifies the
  recorded plan and data before reusing results. Run Again starts a fresh run.
- Delete follows verified manifest ownership. Preserve changed and unregistered
  files and legacy shared outputs. The worker must leave the active slot before
  deletion can finish.
- See [run engine rules](engine/AGENTS.md), the
  [data and artifact contract](../../../docs/reliability-and-data-contracts.md),
  and the [Web test matrix](../../../tests/web/TEST_MATRIX.md).
