"""Tests for startup reconciliation, file logs, and checkpoint resume."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pytest
from fastapi.testclient import TestClient

from quantflow.web.engine import run_history


@pytest.fixture
def app_and_engine(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from quantflow.web.api import runs as runs_api
    from quantflow.web.engine import RunEngine, RunHistory, RunQueue, SSEManager

    db_path = tmp_path / "runs.db"
    monkeypatch.setattr(run_history, "DB_PATH", db_path)
    run_history._ConnectionManager.reset()

    from quantflow.execution import checkpoint as cp_mod
    monkeypatch.setattr(cp_mod, "CHECKPOINT_DIR", tmp_path / "checkpoints")

    app = FastAPI()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.executescript(run_history._INIT_SQL)
    run_history._ConnectionManager._conn = conn

    history = RunHistory()
    sse = SSEManager()
    queue = RunQueue(on_run_available=lambda rid: None)
    engine = RunEngine(queue=queue, history=history, sse=sse)
    runs_api._set_engine(engine)
    app.include_router(runs_api.router)
    return app, engine, history, tmp_path


class TestReconciliation:
    def test_stale_running_and_queued_become_interrupted(self, app_and_engine):
        _, _, history, _ = app_and_engine
        rid_run = history.create_run("running", "task_run", {})
        rid_q = history.create_run("queued", "task_run", {})
        rid_done = history.create_run("done", "task_run", {})
        history.update_status(rid_run, "running")
        history.update_status(rid_done, "completed")

        changed = history.reconcile_stale_runs()
        assert changed == 2
        assert history.get_run(rid_run).status == "interrupted"
        assert history.get_run(rid_q).status == "interrupted"
        assert history.get_run(rid_done).status == "completed"
        assert history.get_run(rid_run).finished_at is not None

    def test_reconcile_is_idempotent(self, app_and_engine):
        _, _, history, _ = app_and_engine
        rid = history.create_run("r", "task_run", {})
        history.update_status(rid, "running")
        assert history.reconcile_stale_runs() == 1
        assert history.reconcile_stale_runs() == 0


class TestFileLogApi:
    def test_returns_real_file_content(self, app_and_engine):
        app, engine, history, tmp_path = app_and_engine
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        log_file = log_dir / "run.log"
        log_file.write_text("line1\nline2\nline3\n")
        rid = history.create_run("logrun", "task_run", {})
        history.update_status(rid, "running", log_path=str(log_file))

        client = TestClient(app)
        r = client.get(f"/api/runs/{rid}/logs")
        assert r.status_code == 200
        data = r.json()
        assert data["exists"] is True
        assert data["path"] == str(log_file)
        assert "line3" in data["content"]

        r2 = client.get(f"/api/runs/{rid}/logs?tail=2")
        assert r2.json()["content"] == "line2\nline3"

    def test_missing_log_returns_empty(self, app_and_engine):
        app, _, history, _ = app_and_engine
        rid = history.create_run("nolog", "task_run", {})
        client = TestClient(app)
        data = client.get(f"/api/runs/{rid}/logs").json()
        assert data["exists"] is False
        assert data["content"] == ""


class TestCheckpoint:
    def test_roundtrip_and_atomic_marks(self, app_and_engine):
        from quantflow.execution.checkpoint import Checkpoint
        _, _, _, tmp_path = app_and_engine
        cp = Checkpoint("r1")
        cp.set_config({"code": "AAPL.US"})
        cp.set_context("dates:watchlist", {"start_date": "2025-01-01",
                                           "end_date": "2025-02-01"})
        cp.mark_done("watchlist", "AAPL.US", result={"code": "AAPL.US",
                                                     "buy_signals": 1})
        cp.mark_done("watchlist", "MSFT.US", result=None)
        assert cp.path.exists()

        loaded = Checkpoint.load("r1")
        assert loaded is not None
        assert loaded.get_done("watchlist") == {"AAPL.US", "MSFT.US"}
        assert loaded.get_results("watchlist")[0]["code"] == "AAPL.US"
        assert loaded.get_context("dates:watchlist")["end_date"] == "2025-02-01"
        assert loaded.done_count() == 2

    def test_copy_to_new_run(self, app_and_engine):
        from quantflow.execution.checkpoint import Checkpoint
        _, _, _, _ = app_and_engine
        cp = Checkpoint("old")
        cp.mark_done("t", "X", result=None)
        assert Checkpoint.copy_to("old", "new") is True
        new_cp = Checkpoint.load("new")
        assert new_cp.get_done("t") == {"X"}
        assert new_cp._data["resumed_from"] == "old"


class TestResumeApi:
    def test_resume_creates_new_run_and_copies_checkpoint(self, app_and_engine, monkeypatch):
        from quantflow.execution.checkpoint import Checkpoint
        app, engine, history, _ = app_and_engine
        # Don't actually spin up the executor thread with a fake watchlist.
        monkeypatch.setattr(engine, "start_processing", lambda rid: None)
        rid = history.create_run("wl", "watchlist_run", {"watchlist": "x.yaml"})
        history.update_status(rid, "interrupted")
        cp = Checkpoint(rid)
        cp.mark_done("watchlist", "AAPL.US", result={"code": "AAPL.US"})

        client = TestClient(app)
        r = client.post(f"/api/runs/{rid}/resume")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        new_id = data["run_id"]
        new_run = history.get_run(new_id)
        assert new_run.config["resume_from"] == rid
        assert Checkpoint.load(new_id).get_done("watchlist") == {"AAPL.US"}

    def test_resume_rejects_completed_run(self, app_and_engine, monkeypatch):
        app, engine, history, _ = app_and_engine
        monkeypatch.setattr(engine, "start_processing", lambda rid: None)
        rid = history.create_run("wl", "watchlist_run", {})
        history.update_status(rid, "completed")
        client = TestClient(app)
        r = client.post(f"/api/runs/{rid}/resume")
        assert r.status_code == 400


class TestLoggingIsolation:
    def test_repeated_setup_does_not_leak_handlers(self, tmp_path):
        import logging
        from quantflow.config.logging import setup_logging
        root = logging.getLogger()
        original = root.handlers[:]
        try:
            p1 = setup_logging(tmp_path, "run_one")
            h1 = logging.getLogger("quantflow.t1")
            h1.info("message from run one")
            for h in root.handlers:
                h.flush()

            p2 = setup_logging(tmp_path, "run_two")
            h2 = logging.getLogger("quantflow.t2")
            h2.info("message from run two")
            for h in root.handlers:
                h.flush()

            # Old run's file must NOT contain the new run's message.
            c1 = Path(p1).read_text()
            c2 = Path(p2).read_text()
            assert "message from run one" in c1
            assert "message from run two" not in c1, "log files leaked across runs"
            assert "message from run two" in c2
            qf = [h for h in root.handlers
                  if getattr(h, "_quantflow_handler", False)]
            assert len(qf) == 2  # one console + one file, not accumulating
        finally:
            root.handlers = original
