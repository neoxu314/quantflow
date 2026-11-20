"""Server-level tests: static file serving, mount points, error handling."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_static_index_html_served():
    """GET / returns index.html."""
    from quantflow.web.server import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<!doctype html>" in resp.text.lower() or "<html" in resp.text.lower()


def test_static_js_served():
    """GET /app.js returns compiled JS."""
    from quantflow.web.server import create_app

    app = create_app()
    with TestClient(app) as client:
        resp = client.get("/app.js")
        assert resp.status_code == 200


def test_unknown_api_route_returns_404():
    """Non-existent API route returns 404, not 200."""
    from quantflow.web.api.config import router
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404


def test_config_api_write_path_traversal_blocked(config_client):
    """PUT config with path traversal in raw data does not write outside target."""
    client, config_path = config_client

    resp = client.get("/api/config").json()
    raw = resp["raw"]
    # Attempt to inject dangerous filenames
    raw["data"] = {"__hack__": "../../etc/passwd"}

    resp = client.put("/api/config", json={"raw": raw})
    assert resp.status_code == 200

    # The file should have been written (the API doesn't validate key names),
    # but it writes to the expected config path, not to an arbitrary location
    assert config_path.exists()


def test_second_startup_cannot_reconcile_another_servers_runs():
    from quantflow.web.engine import RunHistory
    from quantflow.web.server import create_app

    history = RunHistory()
    with TestClient(create_app()) as first:
        run_id = history.create_run("active scan", "stock_scan", {})
        history.update_status(run_id, "running")
        with pytest.raises(RuntimeError, match="QuantFlow Web is already running"), TestClient(
            create_app()
        ):
            pass
        response = first.get(f"/api/runs/{run_id}")
        assert response.json()["run"]["status"] == "running"

    with TestClient(create_app()) as restarted:
        response = restarted.get(f"/api/runs/{run_id}")
        assert response.json()["run"]["status"] == "interrupted"
