"""Web UI server - FastAPI application and startup logic."""
import webbrowser
from pathlib import Path
from threading import Timer

import uvicorn

from quantflow.web.config import WebConfig


def create_app():
    """Create the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(
        title="QuantFlow Web",
        description="Web UI for QuantFlow stock monitoring system",
        version="0.1.0",
    )

    # Register API routes
    from quantflow.web.api.config import router as config_router

    # Library endpoints (Phase 1)
    from quantflow.web.api.library import router as library_router
    from quantflow.web.api.tasks import router as task_router
    from quantflow.web.api.watchlists import router as watchlist_router

    app.include_router(config_router)
    app.include_router(watchlist_router)
    app.include_router(task_router)
    app.include_router(library_router)

    # Initialize Runs and Presets API engines and wire them to routers
    from quantflow.web.api.presets import router as presets_router
    from quantflow.web.api.runs import router as runs_router
    from quantflow.web.engine import RunEngine, RunHistory, RunQueue, SSEManager
    # Build singletons for the web app
    history = RunHistory()
    sse = SSEManager()
    queue = RunQueue(on_run_available=lambda rid: None)
    engine = RunEngine(queue=queue, history=history, sse=sse)
    # Expose engine to API modules
    from quantflow.web.api import presets as presets_api
    from quantflow.web.api import runs as runs_api
    runs_api._set_engine(engine)
    presets_api._set_engine(engine)
    # Register runs and presets routers as part of app routes
    app.include_router(runs_router)
    app.include_router(presets_router)

    # Serve static files (frontend)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def start_server(config: WebConfig = None):
    """Start the web server."""
    if config is None:
        config = WebConfig.load()

    app = create_app()

    url = f"http://{config.host}:{config.port}"
    print(f"\n{'='*50}")
    print("  QuantFlow Web UI")
    print(f"  URL: {url}")
    print(f"{'='*50}\n")

    # Open browser after a short delay (so server is ready)
    def _open_browser():
        webbrowser.open(url)

    Timer(1.5, _open_browser).start()

    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
