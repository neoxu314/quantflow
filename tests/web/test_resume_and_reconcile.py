"""Tests for startup reconciliation, file logs, and checkpoint resume."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


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

    def test_load_rejects_an_invalid_nested_structure(self, tmp_path):
        from quantflow.execution.checkpoint import Checkpoint

        path = tmp_path / "checkpoint.json"
        path.write_text('{"work": {"task": {"done": []}}}')
        assert Checkpoint.load("bad", path=path) is None

    def test_copy_to_new_run(self, app_and_engine):
        from quantflow.execution.checkpoint import Checkpoint
        _, _, _, tmp_path = app_and_engine
        cp = Checkpoint("old")
        cp.freeze_run_plan({"tasks": []})
        cp.fork("new", None, tmp_path)
        new_cp = Checkpoint.load("new")
        assert new_cp.get_context("run:plan") == {"tasks": []}
        assert new_cp._data["resumed_from"] == "old"


class TestResumeApi:
    def test_resume_creates_new_run_and_copies_checkpoint(self, app_and_engine, monkeypatch):
        from quantflow.execution.checkpoint import Checkpoint
        from tests.support.replay_market import install_replay

        app, engine, history, root = app_and_engine
        install_replay(root, monkeypatch.setattr)
        monkeypatch.setattr(engine, "start_processing", lambda rid: None)
        watchlist = root / "watch.yaml"
        watchlist.write_text("name: watch\nitems: [{code: AAPL.US}, {code: BROKEN.US}]\n")
        rid = history.create_run("wl", "watchlist_run", {
            "watchlist": str(watchlist), "output_path": str(root),
            "strategies": ["daily_bull_oversold"]})
        engine._execute_run(rid)
        original = history.get_run(rid)
        assert original.status == "partial"
        assert Checkpoint.load(rid).get_done("watchlist") == {"AAPL.US"}

        client = TestClient(app)
        engine._queue.enqueue("occupied")
        snapshot = Path(Checkpoint.load(rid).get_stats("watchlist", "AAPL.US")["outcome"]["snapshot_path"])
        saved = snapshot.read_bytes()
        snapshot.write_text("changed")
        assert not client.get(f"/api/runs/{rid}/checkpoint").json()["can_resume"]
        assert client.post(f"/api/runs/{rid}/resume").status_code == 400
        assert {p.name for p in (root / "runs").iterdir()} == {rid}
        assert {run.id for run in history.list_runs()} == {rid}
        snapshot.write_bytes(saved)
        assert client.get(f"/api/runs/{rid}/checkpoint").json()["can_resume"]
        res = client.post(f"/api/runs/{rid}/resume")
        assert res.status_code == 200, res.text
        assert res.json()["status"] == "queued"
        new_id = res.json()["run_id"]
        assert client.delete(f"/api/runs/{rid}").status_code == 200
        assert not (Path(original.output_path) / "snapshots").exists()
        cloned = Checkpoint.load(new_id)
        assert len(list(cloned.verified_snapshots(history.get_run(new_id).output_path))) == 1

        (root / "provider-available").touch()
        (root / "provider-requests.log").write_text("")
        assert engine._queue.finish("occupied") == new_id
        engine._execute_run(new_id)
        assert history.get_run(new_id).status == "completed"
        assert (root / "provider-requests.log").read_text().splitlines() == ["BROKEN.US"]
        assert "AAPL.US" in client.get(f"/api/runs/{new_id}/report").json()["report"]

    def test_changed_watchlist_is_rejected_before_enqueue(self, app_and_engine):
        from quantflow.execution.checkpoint import Checkpoint
        from quantflow.execution.executor import Executor

        app, engine, history, tmp_path = app_and_engine
        file = tmp_path / "watch.yaml"
        file.write_text("name: watch\nitems: [{code: AAPL.US}]\n")
        rid = history.create_run("wl", "watchlist_run", {"watchlist": str(file)})
        cp = Checkpoint(rid)
        watchlist, job = engine._watchlist_job(history.get_run(rid), tmp_path)
        cp.freeze_run_plan({
            "watchlist": watchlist.to_dict(), "execution": Executor().execution_identity(job),
        })
        client = TestClient(app)
        history.update_status(rid, "running")
        assert not client.get(f"/api/runs/{rid}/checkpoint").json()["can_resume"]
        history.update_status(rid, "interrupted")
        file.write_text("name: watch\nitems: [{code: MSFT.US}]\n")
        result = client.get(f"/api/runs/{rid}/checkpoint").json()
        assert not result["can_resume"] and "changed" in result["reason"]
        assert client.post(f"/api/runs/{rid}/resume").status_code == 400
        assert len(history.list_runs()) == 1

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


def test_legacy_run_exports_only_verified_finished_work(app_and_engine):
    import hashlib
    from quantflow.artifacts import create_run_directory, atomic_json
    from quantflow.execution.checkpoint import Checkpoint

    app, _, history, base = app_and_engine
    rid = history.create_run("legacy", "watchlist_run", {"watchlist": "old-list.yaml"})
    root = create_run_directory(base, rid)
    history.update_status(rid, "cancelled", output_path=str(root))
    cp = Checkpoint(rid)
    cp.freeze_run_plan({"watchlist": {"items": [{"code":"A.US"}, {"code":"B.US"}]},
                        "execution": {"code_hash": "older-source-hash"}})
    path = root / "snapshots/old/A.US.json"
    atomic_json(path, {"code": "A.US"})
    cp.mark_done("watchlist", "A.US", stats={"outcome": {
        "code":"A.US", "status":"signal", "bar_date":"2025-06-04", "source":"fixture",
        "snapshot_path":str(path), "snapshot_sha256":hashlib.sha256(path.read_bytes()).hexdigest()
    }}, result={"code":"A.US", "matched_buy_strategies":["DailyBullishOversold"], "price":100})
    client = TestClient(app)
    assert not client.get(f"/api/runs/{rid}/checkpoint").json()["can_resume"]
    view = client.get(f"/api/runs/{rid}/report").json()
    assert view["partial"] and "Verified coverage: 1/2" in view["report"]
    assert "A.US" in view["report"] and "DailyBullishOversold" in view["report"]
    exported = client.get(f"/api/runs/{rid}/report?download=true")
    assert exported.text == view["report"] and "attachment" in exported.headers["content-disposition"]
    assert history.get_run(rid).report_path is None
    path.write_text("changed")
    assert client.get(f"/api/runs/{rid}/report?download=true").status_code == 409
