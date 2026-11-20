"""Web UI server - FastAPI application and startup logic."""
import sqlite3
import webbrowser
from contextlib import asynccontextmanager, closing, contextmanager
from pathlib import Path
from threading import Timer

import uvicorn

from quantflow.web.config import WebConfig


@contextmanager
def _exclusive_runs_database(db_path):
    """Reserve the database for one Web instance without blocking its writes."""
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = db_path.with_name(f"{db_path.name}.server-lock")
    with closing(sqlite3.connect(lock_path, timeout=0)) as lock:
        try:
            lock.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if str(exc) != "database is locked":
                raise
            raise RuntimeError(
                f"QuantFlow Web is already running with database {db_path}"
            ) from exc
        yield


def create_app():
    """Create the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    from quantflow.web.api import presets as presets_api
    from quantflow.web.api import runs as runs_api
    from quantflow.web.engine import RunEngine, RunHistory, RunQueue, SSEManager, run_history

    @asynccontextmanager
    async def lifespan(_app):
        with _exclusive_runs_database(run_history.DB_PATH):
            history = RunHistory()
            history.reconcile_stale_runs()
            engine = RunEngine(queue=RunQueue(), history=history, sse=SSEManager())
            runs_api._set_engine(engine)
            presets_api._set_engine(engine)
            try:
                yield
            finally:
                engine.stop_processing()

    app = FastAPI(
        title="QuantFlow Web",
        description="Web UI for QuantFlow stock monitoring system",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Register API routes
    from quantflow.web.api.browse import router as browse_router
    from quantflow.web.api.config import router as config_router

    # Library endpoints (Phase 1)
    from quantflow.web.api.library import router as library_router
    from quantflow.web.api.tasks import router as task_router
    from quantflow.web.api.watchlists import router as watchlist_router

    app.include_router(config_router)
    app.include_router(watchlist_router)
    app.include_router(task_router)
    app.include_router(library_router)
    app.include_router(browse_router)

    app.include_router(runs_api.router)
    app.include_router(presets_api.router)

    # Serve static files (frontend)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def start_server(config: WebConfig = None):
    """Start the web server."""
    if config is None:
        config = WebConfig.load()

    server = uvicorn.Server(uvicorn.Config(
        create_app(), host=config.host, port=config.port, log_level="info",
        timeout_graceful_shutdown=5,
    ))
    # Reserve the port before starting the app or reconciling any run states.
    with server.config.bind_socket() as listener:
        host, port = listener.getsockname()[:2]
        url = f"http://{'[' + host + ']' if ':' in host else host}:{port}"
        timer = Timer(1.5, webbrowser.open, args=(url,))
        timer.start()
        try:
            server.run(sockets=[listener])
        finally:
            timer.cancel()
    if not server.started:
        raise SystemExit(1)
