"""Runs integration: API → DB → API verification."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from quantflow.web.engine import run_history


@pytest.fixture
def app():
    """Create test app with clean in-memory DB per test."""
    from fastapi import FastAPI
    from quantflow.web.api import runs as runs_api
    from quantflow.web.api import presets as presets_api
    from quantflow.web.engine import (
        RunEngine, RunQueue, SSEManager, RunHistory)

    import sqlite3

    run_history._MEMORY_CONN = None
    run_history.DB_PATH = Path(":memory:")

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript(run_history._INIT_SQL)
    run_history._MEMORY_CONN = conn

    api_app = FastAPI()

    history = RunHistory()
    sse = SSEManager()
    queue = RunQueue(on_run_available=lambda rid: None)
    engine = RunEngine(queue=queue, history=history, sse=sse)

    runs_api._set_engine(engine)
    presets_api._set_engine(engine)

    api_app.include_router(runs_api.router)
    api_app.include_router(presets_api.router)
    return api_app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestRunsAPIDBRoundTrip:

    def test_create_writes_db_record(self, client):
        resp = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        assert resp.json()["ok"] is True
        rid = resp.json()["run_id"]

        h = run_history.RunHistory()
        record = h.get_run(rid)
        assert record is not None
        assert record.run_type == "stock_scan"
        assert record.config["code"] == "NVDA.US"
        assert record.status in ("queued", "running")

    def test_list_reflects_db_state(self, client):
        for code in ["NVDA.US", "AAPL.US", "TSLA.US"]:
            client.post("/api/runs/", json={
                "run_type": "stock_scan", "code": code})

        resp = client.get("/api/runs/")
        data = resp.json()
        assert data["total"] == 3
        names = [r["name"] for r in data["runs"]]
        assert "NVDA.US Scan" in names
        assert "AAPL.US Scan" in names
        assert "TSLA.US Scan" in names

    def test_delete_removes_db_record(self, client):
        resp = client.post("/api/runs/", json={
            "run_type": "stock_scan", "code": "NVDA.US"})
        rid = resp.json()["run_id"]

        h = run_history.RunHistory()
        assert h.get_run(rid) is not None

        del_resp = client.delete(f"/api/runs/{rid}")
        assert del_resp.json()["ok"] is True

        assert h.get_run(rid) is None
        assert client.get(f"/api/runs/{rid}").status_code == 404

    def test_preflight_failure_creates_no_db_record(self, client):
        resp = client.post("/api/runs/", json={
            "run_type": "stock_scan", "code": "INVALID"})
        assert resp.json()["ok"] is False

        runs_resp = client.get("/api/runs/")
        assert runs_resp.json()["total"] == 0

    def test_status_update_persists(self, client):
        resp = client.post("/api/runs/", json={
            "run_type": "stock_scan", "code": "NVDA.US"})
        rid = resp.json()["run_id"]

        h = run_history.RunHistory()
        h.update_status(rid, "completed", signal_count=42)

        fetched = client.get(f"/api/runs/{rid}").json()
        assert fetched["run"]["status"] == "completed"
        assert fetched["run"]["signal_count"] == 42

    def test_list_filtered_by_status(self, client):
        r1 = client.post("/api/runs/", json={
            "run_type": "stock_scan", "code": "NVDA.US"})
        r2 = client.post("/api/runs/", json={
            "run_type": "stock_scan", "code": "TSLA.US"})
        rid1 = r1.json()["run_id"]
        rid2 = r2.json()["run_id"]

        h = run_history.RunHistory()
        h.update_status(rid1, "completed")
        h.update_status(rid2, "failed", error="test")

        completed = client.get("/api/runs/?status=completed").json()
        assert len(completed["runs"]) == 1
        assert completed["runs"][0]["id"] == rid1

        failed = client.get("/api/runs/?status=failed").json()
        assert len(failed["runs"]) == 1
        assert failed["runs"][0]["id"] == rid2

    def test_delete_nonexistent_id_returns_404(self, client):
        resp = client.delete("/api/runs/no-such-uuid")
        assert resp.status_code == 404

    def test_queue_state_after_enqueue(self, client):
        client.post("/api/runs/", json={
            "run_type": "stock_scan", "code": "NVDA.US"})
        resp = client.get("/api/runs/queue")
        assert resp.json()["active_run_id"] is not None
        assert resp.json()["pending_count"] == 0
