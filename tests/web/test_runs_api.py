"""Tests for Runs API endpoints."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pytest
from fastapi.testclient import TestClient
from quantflow.web.engine import run_history
run_history.DB_PATH = Path(":memory:")


@pytest.fixture
def app():
    from fastapi import FastAPI
    from quantflow.web.api import runs as runs_api
    from quantflow.web.api import presets as presets_api
    from quantflow.web.engine import (
        RunEngine, RunQueue, SSEManager, RunHistory)

    # Reset memory connection for each test
    run_history._MEMORY_CONN = None
    run_history.DB_PATH = Path(":memory:")

    app = FastAPI()

    # Use sqlite:// memory connection (not file)
    import sqlite3
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript(run_history._INIT_SQL)
    run_history._MEMORY_CONN = conn

    history = RunHistory()
    sse = SSEManager()
    queue = RunQueue(on_run_available=lambda rid: None)
    engine = RunEngine(queue=queue, history=history, sse=sse)
    runs_api._set_engine(engine)
    presets_api._set_engine(engine)
    app.include_router(runs_api.router)
    app.include_router(presets_api.router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRunsListApi:
    def test_list_empty(self, client):
        r = client.get("/api/runs/")
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_create_and_get(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        assert r.json()["ok"] is True
        rid = r.json()["run_id"]
        r2 = client.get(f"/api/runs/{rid}")
        assert r2.json()["run"]["name"] == "NVDA.US Scan"

    def test_preflight_invalid(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "INVALID",
        })
        data = r.json()
        assert data["ok"] is False
        assert len(data["errors"]) > 0


class TestPresetsApi:
    def test_create_and_list(self, client, tmp_path):
        from quantflow.web.engine import presets
        orig = presets.PRESETS_DIR
        presets.PRESETS_DIR = tmp_path
        try:
            r = client.post("/api/presets/", json={
                "name": "Daily NVDA",
                "run_type": "stock_scan",
                "config": {"code": "NVDA.US"},
            })
            assert r.json()["ok"] is True
            r2 = client.get("/api/presets/")
            names = [p["name"]
                     for p in r2.json()["presets"]]
            assert "Daily NVDA" in names
        finally:
            presets.PRESETS_DIR = orig

    def test_delete(self, client, tmp_path):
        from quantflow.web.engine import presets
        orig = presets.PRESETS_DIR
        presets.PRESETS_DIR = tmp_path
        try:
            r = client.post("/api/presets/", json={
                "name": "X",
                "run_type": "stock_scan",
                "config": {"code": "AAPL.US"},
            })
            pid = r.json()["preset_id"]
            r2 = client.delete(f"/api/presets/{pid}")
            assert r2.json()["ok"] is True
        finally:
            presets.PRESETS_DIR = orig
