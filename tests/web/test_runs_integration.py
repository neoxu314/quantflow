"""Runs integration: API → DB → API verification."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from quantflow.web.engine import run_history


@pytest.fixture
def app():
    """Create test app with clean in-memory DB per test."""
    import sqlite3

    from fastapi import FastAPI

    from quantflow.web.api import presets as presets_api
    from quantflow.web.api import runs as runs_api
    from quantflow.web.engine import RunEngine, RunHistory, RunQueue, SSEManager

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

    def test_create_task_run_writes_db_record(self, client, tmp_path):
        tp = tmp_path / "tasks_test.yaml"
        tp.write_text(
            "tasks:\n"
            "  - name: t1\n"
            "    watchlist: watchlists/djia.yaml\n"
            "    strategies: [daily_bull_oversold]\n"
            "    output: ./output/t1\n"
        )

        from quantflow.web.engine import preflight
        orig = preflight.PROJECT_ROOT
        preflight.PROJECT_ROOT = tmp_path
        try:
            resp = client.post("/api/runs/", json={
                "run_type": "task_run",
                "task_config": str(tp),
            })
            assert resp.json()["ok"] is True
            rid = resp.json()["run_id"]

            h = run_history.RunHistory()
            record = h.get_run(rid)
            assert record is not None
            assert record.run_type == "task_run"
            assert record.config["task_config"] == str(tp)
        finally:
            preflight.PROJECT_ROOT = orig

    def test_task_run_list_reflects_db_state(self, client, tmp_path):
        from quantflow.web.engine import preflight
        orig = preflight.PROJECT_ROOT
        preflight.PROJECT_ROOT = tmp_path

        tp1 = tmp_path / "tasks_a.yaml"
        tp1.write_text(
            "tasks:\n"
            "  - name: t1\n"
            "    watchlist: watchlists/djia.yaml\n"
            "    strategies: [daily_bull_oversold]\n"
            "    output: ./output/t1\n"
        )
        tp2 = tmp_path / "tasks_b.yaml"
        tp2.write_text(
            "tasks:\n"
            "  - name: t2\n"
            "    watchlist: watchlists/djia.yaml\n"
            "    strategies: [daily_bull_oversold]\n"
            "    output: ./output/t2\n"
        )
        try:
            client.post("/api/runs/", json={
                "run_type": "task_run", "task_config": str(tp1)})
            client.post("/api/runs/", json={
                "run_type": "task_run", "task_config": str(tp2)})

            resp = client.get("/api/runs/")
            data = resp.json()
            assert data["total"] == 2
            names = [r["name"] for r in data["runs"]]
            assert any("tasks_a" in n for n in names)
            assert any("tasks_b" in n for n in names)
        finally:
            preflight.PROJECT_ROOT = orig

    def test_task_run_preflight_failure_creates_no_db_record(self, client):
        resp = client.post("/api/runs/", json={
            "run_type": "task_run",
            "task_config": "nonexistent_file.yaml",
        })
        assert resp.json()["ok"] is False

        runs_resp = client.get("/api/runs/")
        assert runs_resp.json()["total"] == 0

    def test_task_run_delete_removes_db_record(self, client, tmp_path):
        from quantflow.web.engine import preflight
        orig = preflight.PROJECT_ROOT
        preflight.PROJECT_ROOT = tmp_path

        tp = tmp_path / "tasks_del.yaml"
        tp.write_text(
            "tasks:\n"
            "  - name: t1\n"
            "    watchlist: watchlists/djia.yaml\n"
            "    strategies: [daily_bull_oversold]\n"
            "    output: ./output/t1\n"
        )
        try:
            resp = client.post("/api/runs/", json={
                "run_type": "task_run", "task_config": str(tp)})
            rid = resp.json()["run_id"]

            h = run_history.RunHistory()
            assert h.get_run(rid) is not None

            del_resp = client.delete(f"/api/runs/{rid}")
            assert del_resp.json()["ok"] is True
            assert h.get_run(rid) is None
            assert client.get(f"/api/runs/{rid}").status_code == 404
        finally:
            preflight.PROJECT_ROOT = orig

    def test_per_run_output_isolation(self, tmp_path):
        """Files endpoint should only return files from that run's output dir."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from quantflow.web.api import runs as runs_api
        from quantflow.web.engine.run_engine import RunEngine
        from quantflow.web.engine.run_history import RunHistory
        from quantflow.web.engine.run_queue import RunQueue
        from quantflow.web.engine.sse import SSEManager

        run_history._MEMORY_CONN = None
        run_history.DB_PATH = Path(":memory:")

        import sqlite3
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.executescript(run_history._INIT_SQL)
        run_history._MEMORY_CONN = conn

        h = RunHistory()
        rid1 = h.create_run("Run 1", "stock_scan", {
            "code": "NVDA.US"})
        rid2 = h.create_run("Run 2", "stock_scan", {
            "code": "AAPL.US"})
        d1 = tmp_path / "run1_output"
        d2 = tmp_path / "run2_output"
        d1.mkdir()
        d2.mkdir()
        h.update_status(rid1, "completed", signal_count=1,
                        output_path=str(d1), report_path=str(d1 / "a.json"))
        h.update_status(rid2, "completed", signal_count=1,
                        output_path=str(d2), report_path=str(d2 / "b.json"))
        (d1 / "a.json").write_text("[]")
        (d2 / "b.json").write_text("[]")

        engine = RunEngine(RunQueue(), h, SSEManager())
        runs_api._set_engine(engine)

        api_app = FastAPI()
        api_app.include_router(runs_api.router)
        client = TestClient(api_app)

        files1 = client.get(f"/api/runs/{rid1}/files").json()
        files2 = client.get(f"/api/runs/{rid2}/files").json()
        names1 = {f["name"] for f in files1["files"]}
        names2 = {f["name"] for f in files2["files"]}
        assert names1 == {"a.json"}
        assert names2 == {"b.json"}

class TestCrossRunTypeFileCleanup:
    """Verify delete_run removes ALL output files for every run type."""

    def _setup_engine(self):
        import sqlite3

        from quantflow.web.api import runs as runs_api
        from quantflow.web.engine.run_engine import RunEngine
        from quantflow.web.engine.run_history import RunHistory
        from quantflow.web.engine.run_queue import RunQueue
        from quantflow.web.engine.sse import SSEManager

        run_history._MEMORY_CONN = None
        run_history.DB_PATH = Path(":memory:")
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.executescript(run_history._INIT_SQL)
        run_history._MEMORY_CONN = conn
        h = RunHistory()
        engine = RunEngine(RunQueue(on_run_available=lambda rid: None), h, SSEManager())
        runs_api._set_engine(engine)
        return h, runs_api, engine

    def test_stock_scan_cleanup_on_delete(self):
        h, runs_api, engine = self._setup_engine()

        rid = h.create_run("SS Cleanup", "stock_scan", {"code": "600000.SH"})
        d = Path(tempfile.mkdtemp())
        h.update_status(rid, "completed",
            output_path=str(d),
            report_path=str(d / "data.json"))
        (d / "data.json").write_text("[]")
        (d / "600000.SH_indicators.json").write_text("{}")
        (d / "other_file.txt").write_text("user data")

        client = TestClient(_make_app(runs_api))
        client.delete(f"/api/runs/{rid}")

        # Stock scan: only deletes indicator file, not entire directory
        assert d.exists(), "Directory should remain (shared output)"
        assert not (d / "data.json").exists(), "report_path should be deleted"
        assert not (d / "600000.SH_indicators.json").exists(), "indicator file should be deleted"
        assert (d / "other_file.txt").exists(), "user files should be preserved"

    def test_watchlist_run_cleanup_on_delete(self):
        h, runs_api, engine = self._setup_engine()

        rid = h.create_run("WL Cleanup", "watchlist_run", {"watchlist": "x.yaml"})
        d = Path(tempfile.mkdtemp())
        h.update_status(rid, "completed",
            output_path=str(d),
            report_path=str(d / "report.md"))
        # The Executor saves results as {output_dir}/{job.name}.json
        # where job.name = "web:{wl.name}"
        # For this test, run.name is "WL Cleanup" (not "web:..." because we're mocking)
        # But we should test the actual pattern: {run.name}.json
        json_file = d / "WL Cleanup.json"
        json_file.write_text("[]")
        (d / "report.md").write_text("# Report")
        # User file - should be preserved
        user_file = d / "user_data.txt"
        user_file.write_text("important data")

        client = TestClient(_make_app(runs_api))
        client.delete(f"/api/runs/{rid}")

        # Directory should still exist (no longer deleting entire directory)
        assert d.exists(), "Output directory should be preserved"
        # JSON file should be deleted
        assert not json_file.exists(), "JSON file should be deleted"
        # Report file should be deleted
        assert not (d / "report.md").exists(), "Report file should be deleted"
        # User file should be preserved
        assert user_file.exists(), "User file should be preserved"

    def test_task_run_cleanup_on_delete(self):
        """task_run delete should remove task outputs but preserve directory.
        
        Safety: task_run output_path may contain user files (e.g., /Downloads).
        Delete should only remove task output files, not entire directory.
        """
        h, runs_api, engine = self._setup_engine()

        rid = h.create_run("TR Cleanup", "task_run", {"task_config": "tasks.yaml"})
        d = Path(tempfile.mkdtemp())

        # User files (should be preserved)
        user_file = d / "user_document.pdf"
        user_file.write_text("important data")

        # Task output files (should be deleted)
        h.update_status(rid, "completed",
            output_path=str(d),
            report_path=str(d / "Daily_Report.md"))
        (d / "Combined_Results.json").write_text("[]")
        (d / "Daily_Report.md").write_text("# Report")
        (d / "TR Cleanup.json").write_text("{\"results\": []}")  # Executor output

        client = TestClient(_make_app(runs_api))
        client.delete(f"/api/runs/{rid}")

        # Task outputs deleted
        assert not (d / "Daily_Report.md").exists()
        assert not (d / "Combined_Results.json").exists()
        assert not (d / "TR Cleanup.json").exists()  # Executor output also deleted

        # User file preserved
        assert user_file.exists()

        # Directory preserved
        assert d.exists(), "Task run output directory should be preserved (safety)"

    def test_output_files_actually_exist_on_disk(self):
        """Verify /files endpoint returns paths that exist."""
        h, runs_api, engine = self._setup_engine()

        rid = h.create_run("Exists Check", "task_run", {})
        d = Path(tempfile.mkdtemp())
        (d / "data.json").write_text("[]")
        h.update_status(rid, "completed",
            output_path=str(d))

        client = TestClient(_make_app(runs_api))
        files_resp = client.get(f"/api/runs/{rid}/files")
        for f in files_resp.json()["files"]:
            assert Path(f["path"]).exists(), f"File {f['path']} should exist"

    def test_db_record_deleted_after_cleanup(self):
        """Verify DB record is removed after successful file cleanup."""
        h, runs_api, engine = self._setup_engine()

        rid = h.create_run("DB Delete", "stock_scan", {"code": "X"})
        d = Path(tempfile.mkdtemp())
        h.update_status(rid, "completed",
            output_path=str(d))
        (d / "data.json").write_text("[]")

        client = TestClient(_make_app(runs_api))
        client.delete(f"/api/runs/{rid}")

        assert h.get_run(rid) is None, "DB record should be deleted"

    def test_task_run_daily_mode_cleanup_removes_subdirectory(self):
        """daily mode: delete_run should remove date subdirectory but preserve base dir.
        
        Safety: base output_path may contain user files. Delete only removes
        date subdirectory (created by task), not base directory.
        """
        h, runs_api, engine = self._setup_engine()

        rid = h.create_run("Daily Cleanup", "task_run", {"daily": True})
        d = Path(tempfile.mkdtemp())

        # User files in base directory (should be preserved)
        user_config = d / "user_config.yaml"
        user_config.write_text("important settings")

        # Create date subdirectory (created by task, should be deleted)
        date_dir = d / "2026-05-05"
        date_dir.mkdir()

        (date_dir / "Daily_Report.md").write_text("# Report")
        (date_dir / "Combined_Results.json").write_text("[]")
        (date_dir / "Daily Cleanup.json").write_text("{\"results\": []}")  # Executor output

        # Simulate daily mode paths
        h.update_status(rid, "completed",
            output_path=str(d),
            report_path=str(date_dir / "Daily_Report.md"),
            finished_at="2026-05-05T10:00:00Z")

        client = TestClient(_make_app(runs_api))
        client.delete(f"/api/runs/{rid}")

        # Date subdirectory deleted (task-created)
        assert not date_dir.exists(), "Date subdirectory should be deleted"
        assert not (date_dir / "Daily_Report.md").exists()
        assert not (date_dir / "Combined_Results.json").exists()
        assert not (date_dir / "Daily Cleanup.json").exists()  # Executor output also deleted

        # User file in base directory preserved
        assert user_config.exists()

        # Base directory preserved (may contain user files)
        assert d.exists(), "Base output directory should be preserved (safety)"

    def test_delete_run_removes_report_path_file_first(self):
        """Verify report_path file and indicator file are deleted, directory preserved.
        
        After Phase 1.1: stock_scan no longer creates run_id subdirectory.
        Output directory may contain files from other runs, so we only delete
        specific files, not the entire directory.
        """
        h, runs_api, engine = self._setup_engine()

        rid = h.create_run("Report Delete", "stock_scan", {"code": "X"})
        d = Path(tempfile.mkdtemp())

        # Indicator file (should be deleted)
        indicator_file = d / "X_indicators.json"
        indicator_file.write_text("[]")
        # Report file (should be deleted)
        report_file = d / "data.json"
        report_file.write_text("[]")
        # Other file from different run (should be preserved)
        other_file = d / "other.json"
        other_file.write_text("{}")

        h.update_status(rid, "completed",
            output_path=str(d),
            report_path=str(report_file))

        client = TestClient(_make_app(runs_api))
        client.delete(f"/api/runs/{rid}")

        # Verify specific files are deleted
        assert not report_file.exists(), "report_path file should be deleted"
        assert not indicator_file.exists(), "indicator file should be deleted"
        # Verify directory is preserved (may contain files from other runs)
        assert d.exists(), "output_path directory should be preserved"
        # Verify other file is preserved
        assert other_file.exists(), "other file should be preserved"


def _make_app(runs_api_module):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(runs_api_module.router)
    return app


class TestExecutorAlwaysWritesJson:
    def test_executor_always_writes_json(self, tmp_path):
        """Executor.save_results should write JSON even with empty results."""
        from quantflow.execution.storage import Storage

        output_dir = tmp_path / "test_output"
        output_dir.mkdir()
        json_path = output_dir / "test_run.json"

        storage = Storage._instance if hasattr(Storage, '_instance') else Storage()
        storage.save_results(str(json_path), [])
        assert json_path.exists()
        assert json_path.read_text() == "[]"
