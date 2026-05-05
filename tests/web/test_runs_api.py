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

    from quantflow.web.api import presets as presets_api
    from quantflow.web.api import runs as runs_api
    from quantflow.web.engine import RunEngine, RunHistory, RunQueue, SSEManager

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


class TestDeleteRunApi:
    def test_delete_run(self, client):
        """Delete a completed run removes DB record."""
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        r2 = client.delete(f"/api/runs/{rid}")
        assert r2.json()["ok"] is True
        r3 = client.get(f"/api/runs/{rid}")
        assert r3.status_code == 404

    def test_delete_nonexistent(self, client):
        """Delete a run that doesn't exist returns 404."""
        r = client.delete("/api/runs/no-such-id")
        assert r.status_code == 404

    def test_delete_removes_from_list(self, client):
        """After delete, runner should not appear in list."""
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan", "code": "NVDA.US"})
        rid = r.json()["run_id"]
        client.delete(f"/api/runs/{rid}")
        runs = client.get("/api/runs/").json()
        assert all(run["id"] != rid for run in runs["runs"])

    def test_delete_report_file(self, client, tmp_path):
        """Delete removes the report file if it exists."""
        report_file = tmp_path / "test_report.json"
        report_file.write_text("{}")
        h = run_history.RunHistory()
        rid = h.create_run("T", "stock_scan", {})
        h.update_status(rid, "completed",
            report_path=str(report_file))

        from quantflow.web.api import runs as runs_api
        from quantflow.web.engine.run_engine import RunEngine
        from quantflow.web.engine.run_queue import RunQueue
        from quantflow.web.engine.sse import SSEManager

        engine = RunEngine(
            RunQueue(), h, SSEManager())
        runs_api._set_engine(engine)

        client.delete(f"/api/runs/{rid}")
        assert not report_file.exists()

    def test_delete_task_run_preserves_user_files(self, client, tmp_path):
        """task_run delete should only remove task outputs, not user files.
        
        Safety check: if user sets Output Directory = /Downloads,
        and Downloads contains user photos/documents, delete_run
        should only remove task output files (Daily_Report.md, etc),
        not the entire Downloads directory.
        """
        import yaml
        
        # Setup: create output directory with user files
        output_dir = tmp_path / "user_downloads"
        output_dir.mkdir()
        
        # User's other files (should be preserved)
        user_photo = output_dir / "vacation.jpg"
        user_doc = output_dir / "work.pdf"
        user_photo.write_text("fake photo data")
        user_doc.write_text("fake document")
        
        # Task output files (should be deleted)
        task_report = output_dir / "Daily_Report.md"
        combined_json = output_dir / "Combined_Results.json"
        task_md = output_dir / "test_task.md"
        task_json = output_dir / "test_task.json"  # Executor output
        task_report.write_text("# Report")
        combined_json.write_text("{\"signals\": []}")
        task_md.write_text("# Task Report")
        task_json.write_text("{\"results\": []}")
        
        # Create task config file
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        task_config_file = config_dir / "tasks_test.yaml"
        
        # Create watchlist
        watchlists_dir = tmp_path / "watchlists"
        watchlists_dir.mkdir()
        watchlist_file = watchlists_dir / "test.yaml"
        watchlist_file.write_text(yaml.dump({
            "name": "test",
            "description": "test",
            "items": [{"code": "AAPL.US", "name": "Apple", "tags": []}]
        }))
        
        # Create task config (no output field)
        task_config_file.write_text(yaml.dump({
            "tasks": [{
                "name": "test_task",
                "watchlist": str(watchlist_file),
                "strategies": ["daily_bull_oversold"]
            }]
        }))
        
        # Create task_run record
        h = run_history.RunHistory()
        rid = h.create_run("Test Task", "task_run", {
            "task_config": str(task_config_file),
            "output_path": str(output_dir),
            "daily": False
        })
        h.update_status(rid, "completed", 
            output_path=str(output_dir),
            report_path=str(task_report))
        
        from quantflow.web.api import runs as runs_api
        from quantflow.web.engine.run_engine import RunEngine
        from quantflow.web.engine.run_queue import RunQueue
        from quantflow.web.engine.sse import SSEManager
        
        engine = RunEngine(RunQueue(), h, SSEManager())
        runs_api._set_engine(engine)
        
        # Delete the run
        resp = client.delete(f"/api/runs/{rid}")
        assert resp.json()["ok"] is True
        
        # Verify: task output files deleted
        assert not task_report.exists()
        assert not combined_json.exists()
        assert not task_md.exists()
        assert not task_json.exists()  # Executor output also deleted
        
        # Verify: user files preserved
        assert user_photo.exists()
        assert user_doc.exists()
        
        # Verify: output directory still exists
        assert output_dir.exists()

    def test_delete_task_run_daily_mode_removes_date_dir(self, client, tmp_path):
        """daily mode: delete should remove date subdirectory."""
        import yaml
        
        # Setup: output directory with date subdirectory
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        date_dir = output_dir / "2026-05-05"
        date_dir.mkdir()
        
        # User files in base output_dir (should be preserved)
        user_file = output_dir / "config.yaml"
        user_file.write_text("config: test")
        
        # Task outputs in date subdirectory (should be deleted)
        task_report = date_dir / "Daily_Report.md"
        combined_json = date_dir / "Combined_Results.json"
        task_json = date_dir / "test_task.json"  # Executor output
        task_report.write_text("# Report")
        combined_json.write_text("{\"signals\": []}")
        task_json.write_text("{\"results\": []}")
        
        # Create task config
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        task_config_file = config_dir / "tasks_test.yaml"
        watchlists_dir = tmp_path / "watchlists"
        watchlists_dir.mkdir()
        watchlist_file = watchlists_dir / "test.yaml"
        watchlist_file.write_text(yaml.dump({
            "name": "test",
            "description": "test",
            "items": [{"code": "AAPL.US", "name": "Apple", "tags": []}]
        }))
        task_config_file.write_text(yaml.dump({
            "tasks": [{
                "name": "test_task",
                "watchlist": str(watchlist_file),
                "strategies": ["daily_bull_oversold"]
            }]
        }))
        
        # Create task_run with daily=True
        h = run_history.RunHistory()
        rid = h.create_run("Daily Task", "task_run", {
            "task_config": str(task_config_file),
            "output_path": str(output_dir),
            "daily": True
        })
        h.update_status(rid, "completed",
            output_path=str(output_dir),
            report_path=str(task_report),
            finished_at="2026-05-05T10:00:00Z")
        
        from quantflow.web.api import runs as runs_api
        from quantflow.web.engine.run_engine import RunEngine
        from quantflow.web.engine.run_queue import RunQueue
        from quantflow.web.engine.sse import SSEManager
        
        engine = RunEngine(RunQueue(), h, SSEManager())
        runs_api._set_engine(engine)
        
        # Delete the run
        resp = client.delete(f"/api/runs/{rid}")
        assert resp.json()["ok"] is True
        
        # Verify: date subdirectory and task outputs deleted
        assert not date_dir.exists()
        assert not task_report.exists()
        assert not combined_json.exists()
        assert not task_json.exists()  # Executor output also deleted
        
        # Verify: user files in base output_dir preserved
        assert user_file.exists()
        assert output_dir.exists()


class TestTaskRunPreflight:
    def test_preflight_missing_task_config(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "task_run",
        })
        data = r.json()
        assert data["ok"] is False
        assert any("required" in e.lower() for e in data["errors"])

    def test_preflight_nonexistent_task_file(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "task_run",
            "task_config": "config/does_not_exist.yaml",
        })
        data = r.json()
        assert data["ok"] is False
        assert any("not found" in e.lower() for e in data["errors"])

    def test_preflight_valid_task_config(self, client, tmp_path):
        from quantflow.web.engine import preflight
        orig = preflight.PROJECT_ROOT
        preflight.PROJECT_ROOT = tmp_path

        tp = tmp_path / "config" / "tasks_valid.yaml"
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(
            "tasks:\n"
            "  - name: valid_task\n"
            "    watchlist: watchlists/djia.yaml\n"
            "    strategies: [daily_bull_oversold]\n"
            "    output: ./output/valid\n"
        )
        try:
            r = client.post("/api/runs/", json={
                "run_type": "task_run",
                "task_config": str(tp),
            })
            assert r.json()["ok"] is True
            assert r.json()["run_id"] is not None
        finally:
            preflight.PROJECT_ROOT = orig


class TestFilesEndpoint:
    def test_files_endpoint_no_output_path(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        files_resp = client.get(f"/api/runs/{rid}/files")
        assert files_resp.status_code == 200
        assert files_resp.json()["files"] == []

    def test_files_endpoint_nonexistent_run(self, client):
        r = client.get("/api/runs/nonexistent-id/files")
        assert r.status_code == 404

    def test_files_endpoint_finds_files_in_subdirectory(self, client, tmp_path):
        """Files in nested directories (daily mode) should be discovered."""
        import yaml
        
        # Create valid task config file
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        task_file = config_dir / "tasks_test.yaml"
        
        # Create watchlist file
        watchlists_dir = tmp_path / "watchlists"
        watchlists_dir.mkdir()
        watchlist_file = watchlists_dir / "test.yaml"
        watchlist_file.write_text(yaml.dump({
            "name": "test",
            "description": "test",
            "items": [{"code": "NVDA.US", "name": "Nvidia", "tags": []}]
        }))
        
        # Create task config
        task_file.write_text(yaml.dump({
            "tasks": [{
                "name": "test_task",
                "watchlist": str(watchlist_file),
                "strategies": ["daily_bull_oversold"]
            }]
        }))
        
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        daily_dir = output_dir / "2026-05-05"
        daily_dir.mkdir()
        
        json_file = daily_dir / "Combined_Results.json"
        json_file.write_text("{\"signals\": []}")
        md_file = daily_dir / "Daily_Report.md"
        md_file.write_text("# Report")
        
        r = client.post("/api/runs/", json={
            "run_type": "task_run",
            "task_config": str(task_file),
        })
        rid = r.json()["run_id"]
        h = run_history.RunHistory()
        h.update_status(rid, "completed", output_path=str(output_dir))
        
        files_resp = client.get(f"/api/runs/{rid}/files")
        assert files_resp.status_code == 200
        files = files_resp.json()["files"]
        assert len(files) == 2
        file_names = {f["name"] for f in files}
        assert "Combined_Results.json" in file_names
        assert "Daily_Report.md" in file_names


class TestOpenFolderEndpoint:
    def test_open_folder_success(self, client, tmp_path):
        folder = tmp_path / "output_test"
        folder.mkdir()
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        h = run_history.RunHistory()
        h.update_status(rid, "completed", output_path=str(folder))
        r2 = client.post(f"/api/runs/{rid}/open-folder")
        assert r2.status_code == 200
        data = r2.json()
        assert data["ok"] is True
        assert data["path"] == str(folder)

    def test_open_folder_no_output_path(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        r2 = client.post(f"/api/runs/{rid}/open-folder")
        assert r2.status_code == 200
        data = r2.json()
        assert data["ok"] is False
        assert "No output path" in data["message"]

    def test_open_folder_nonexistent_path(self, client, tmp_path):
        fake_path = str(tmp_path / "does_not_exist")
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        h = run_history.RunHistory()
        h.update_status(rid, "completed", output_path=fake_path)
        r2 = client.post(f"/api/runs/{rid}/open-folder")
        assert r2.status_code == 200
        data = r2.json()
        assert data["ok"] is False
        assert "does not exist" in data["message"]

    def test_open_folder_nonexistent_run(self, client):
        r = client.post("/api/runs/nonexistent-id/open-folder")
        assert r.status_code == 404


class TestTaskRunNaming:
    def test_task_run_auto_name(self, client, tmp_path):
        from quantflow.web.engine import preflight
        orig = preflight.PROJECT_ROOT
        preflight.PROJECT_ROOT = tmp_path

        tp = tmp_path / "config" / "tasks_named.yaml"
        tp.parent.mkdir(parents=True, exist_ok=True)
        tp.write_text(
            "tasks:\n"
            "  - name: named_task\n"
            "    watchlist: watchlists/djia.yaml\n"
            "    strategies: [daily_bull_oversold]\n"
            "    output: ./output/named\n"
        )
        try:
            r = client.post("/api/runs/", json={
                "run_type": "task_run",
                "task_config": str(tp),
            })
            assert r.json()["ok"] is True
            rid = r.json()["run_id"]
            detail = client.get(f"/api/runs/{rid}").json()
            assert "tasks_named" in detail["run"]["name"]
        finally:
            preflight.PROJECT_ROOT = orig


class TestMdToHtmlFrontend:
    """Verify mdToHtml handles markdown lists."""

    def test_md_list_star_syntax(self):
        """List syntax should produce <li> elements."""
        from pathlib import Path
        ts = Path(__file__).resolve().parents[2]
        app_ts = (
            ts / "src" / "quantflow" / "web" / "static" / "app.ts"
        )
        content = app_ts.read_text()
        lines = content.split("\n")
        md_start = None
        md_end = None
        for i, line in enumerate(lines):
            if "function mdToHtml" in line:
                md_start = i
            if md_start is not None and "return html;" in line:
                md_end = i
                break
        assert md_start is not None
        md_body = "\n".join(lines[md_start:md_end + 1])
        assert "<li" in md_body
        assert "list-disc" in md_body


class TestGetReportEndpoint:
    def test_get_report_no_run(self, client):
        r = client.get("/api/runs/nonexistent-id/report")
        assert r.status_code == 404

    def test_get_report_no_report_path(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        h = run_history.RunHistory()
        h.update_status(rid, "completed")
        r2 = client.get(f"/api/runs/{rid}/report")
        assert r2.status_code == 200
        data = r2.json()
        assert data["report"] is None
        assert data["message"] == "No report available"

    def test_get_report_file_not_found(self, client, tmp_path):
        fake_path = str(tmp_path / "missing.md")
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        h = run_history.RunHistory()
        h.update_status(rid, "completed", report_path=fake_path)
        r2 = client.get(f"/api/runs/{rid}/report")
        assert r2.status_code == 200
        data = r2.json()
        assert data["report"] is None
        assert data["message"] == "Report file not found"

    def test_get_report_success(self, client, tmp_path):
        report_file = tmp_path / "report.md"
        report_file.write_text("# Test Report\nHello world.")
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        h = run_history.RunHistory()
        h.update_status(rid, "completed", report_path=str(report_file))
        r2 = client.get(f"/api/runs/{rid}/report")
        assert r2.status_code == 200
        data = r2.json()
        assert data["report"] == "# Test Report\nHello world."
        assert data["path"] == str(report_file)


class TestGetIndicatorDataEndpoint:
    def test_indicator_data_not_stock_scan(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "watchlist_run",
            "watchlist": "watchlists/djia.yaml",
            "strategies": ["daily_bull_oversold"],
        })
        rid = r.json()["run_id"]
        r2 = client.get(f"/api/runs/{rid}/indicator-data")
        assert r2.status_code == 200
        data = r2.json()
        assert data["data"] is None
        assert data["message"] == "Not a stock scan run"

    def test_indicator_data_no_data_path(self, client):
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        r2 = client.get(f"/api/runs/{rid}/indicator-data")
        assert r2.status_code == 200
        data = r2.json()
        assert data["data"] is None
        assert data["message"] == "No data available"

    def test_indicator_data_file_not_found(self, client, tmp_path):
        fake_path = str(tmp_path / "missing.json")
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        h = run_history.RunHistory()
        h.update_status(rid, "completed", report_path=fake_path)
        r2 = client.get(f"/api/runs/{rid}/indicator-data")
        assert r2.status_code == 200
        data = r2.json()
        assert data["data"] is None
        assert data["message"] == "Data file not found"

    def test_indicator_data_success(self, client, tmp_path):
        data_file = tmp_path / "indicator_data.json"
        import json
        sample_data = [
            {"date": "2025-01-01", "kdj_k": 50.0, "kdj_d": 45.0},
            {"date": "2025-01-02", "kdj_k": 55.0, "kdj_d": 48.0},
        ]
        data_file.write_text(json.dumps(sample_data))
        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        h = run_history.RunHistory()
        h.update_status(rid, "completed", report_path=str(data_file))
        r2 = client.get(f"/api/runs/{rid}/indicator-data")
        assert r2.status_code == 200
        data = r2.json()
        assert data["data"] == sample_data
        assert data["code"] == "NVDA.US"
        assert data["bar_count"] == 2


class TestCancelRunEndpoint:
    def test_cancel_pending_run(self, client):
        from quantflow.web.api import runs as runs_api
        from quantflow.web.engine import RunEngine, RunHistory, RunQueue, SSEManager

        h = run_history.RunHistory()
        sse = SSEManager()
        queue = RunQueue(on_run_available=lambda rid: None)
        engine = RunEngine(queue=queue, history=h, sse=sse)
        runs_api._set_engine(engine)

        r1 = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid1 = r1.json()["run_id"]
        assert r1.json()["status"] == "active"

        r2 = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "AAPL.US",
        })
        rid2 = r2.json()["run_id"]
        assert r2.json()["status"] == "queued"

        r3 = client.post(f"/api/runs/{rid2}/cancel")
        assert r3.json()["ok"] is True
        run2 = h.get_run(rid2)
        assert run2.status == "cancelled"

    def test_cancel_active_run(self, client):
        from quantflow.web.api import runs as runs_api
        from quantflow.web.engine import RunEngine, RunHistory, RunQueue, SSEManager

        h = run_history.RunHistory()
        sse = SSEManager()
        queue = RunQueue(on_run_available=lambda rid: None)
        engine = RunEngine(queue=queue, history=h, sse=sse)
        runs_api._set_engine(engine)

        r = client.post("/api/runs/", json={
            "run_type": "stock_scan",
            "code": "NVDA.US",
        })
        rid = r.json()["run_id"]
        assert r.json()["status"] == "active"

        r2 = client.post(f"/api/runs/{rid}/cancel")
        assert r2.json()["ok"] is True
        run = h.get_run(rid)
        assert run.status == "cancelled"

    def test_cancel_nonexistent_run(self, client):
        """Cancel for a run not in queue returns 200 (queue.active != run_id).
        
        NOTE: The cancel endpoint creates a cancelled status record even for
        nonexistent run IDs because queue.active (None) != the fake run_id.
        This is a known API issue — cancel should first verify the run exists.
        """
        r = client.post("/api/runs/fake-id/cancel")
        assert r.status_code == 200
        assert r.json()["ok"] is True


class TestBuildConfigFunction:
    def test_build_config_stock_scan_all_fields(self):
        from quantflow.web.api.runs import _build_config
        body = {
            "code": "NVDA.US",
            "start_date": "2025-01-01",
            "end_date": "2025-03-01",
            "indicators": ["macd", "rsi"],
            "output_path": "/tmp/output",
        }
        result = _build_config("stock_scan", body)
        assert result == {
            "code": "NVDA.US",
            "start_date": "2025-01-01",
            "end_date": "2025-03-01",
            "indicators": ["macd", "rsi"],
            "output_path": "/tmp/output",
        }

    def test_build_config_stock_scan_defaults(self):
        from quantflow.web.api.runs import _build_config
        result = _build_config("stock_scan", {"code": "NVDA.US"})
        assert result["code"] == "NVDA.US"
        assert result["start_date"] is None
        assert result["end_date"] is None
        assert result["indicators"] == ["kdj", "dual_line"]
        assert result["output_path"] is None

    def test_build_config_watchlist_run(self):
        from quantflow.web.api.runs import _build_config
        body = {
            "watchlist": "watchlists/djia.yaml",
            "strategies": ["daily_bull_oversold"],
            "output_path": "/tmp/output",
        }
        result = _build_config("watchlist_run", body)
        assert result == {
            "watchlist": "watchlists/djia.yaml",
            "strategies": ["daily_bull_oversold"],
            "output_path": "/tmp/output",
        }

    def test_build_config_task_run(self):
        from quantflow.web.api.runs import _build_config
        body = {
            "task_config": "config/tasks_us_mac.yaml",
            "output_path": "/tmp/output",
        }
        result = _build_config("task_run", body)
        assert result["task_config"] == "config/tasks_us_mac.yaml"
        assert result["output_path"] == "/tmp/output"
        assert result["daily"] is False

    def test_build_config_unknown_type(self):
        from quantflow.web.api.runs import _build_config
        result = _build_config("unknown_type", {"foo": "bar"})
        assert result == {}

    def test_build_config_presets_fields(self):
        from quantflow.web.api.runs import _build_config
        body = {
            "code": "NVDA.US",
            "validate_only": True,
            "name": "Custom Name",
            "preset_id": "preset-123",
        }
        result = _build_config("stock_scan", body)
        assert "validate_only" not in result
        assert "name" not in result
        assert "preset_id" not in result
        assert result["code"] == "NVDA.US"


class TestToDictFunction:
    def test_to_dict_all_fields(self):
        from quantflow.web.api.runs import _to_dict

        class FakeRun:
            id = "run-1"
            name = "Test Run"
            run_type = "stock_scan"
            config = {"code": "NVDA.US"}
            status = "completed"
            created_at = "2025-01-01T00:00:00+00:00"
            started_at = "2025-01-01T00:01:00+00:00"
            finished_at = "2025-01-01T00:02:00+00:00"
            duration_ms = 60000
            error = None
            output_path = "/tmp/output"
            report_path = "/tmp/report.md"
            signal_count = 3
            preset_id = "preset-123"

        result = _to_dict(FakeRun())
        assert result == {
            "id": "run-1",
            "name": "Test Run",
            "run_type": "stock_scan",
            "config": {"code": "NVDA.US"},
            "status": "completed",
            "created_at": "2025-01-01T00:00:00+00:00",
            "started_at": "2025-01-01T00:01:00+00:00",
            "finished_at": "2025-01-01T00:02:00+00:00",
            "duration_ms": 60000,
            "error": None,
            "output_path": "/tmp/output",
            "report_path": "/tmp/report.md",
            "signal_count": 3,
            "preset_id": "preset-123",
        }


class TestAutoNameFunction:
    def test_auto_name_stock_scan(self):
        from quantflow.web.api.runs import _auto_name
        result = _auto_name("stock_scan", {"code": "NVDA.US"})
        assert result == "NVDA.US Scan"

    def test_auto_name_watchlist_run(self):
        from quantflow.web.api.runs import _auto_name
        result = _auto_name("watchlist_run", {"watchlist": "watchlists/my_watchlist.yaml"})
        assert result == "my_watchlist Monitor"

    def test_auto_name_task_run(self):
        from quantflow.web.api.runs import _auto_name
        result = _auto_name("task_run", {"task_config": "config/tasks_us_mac.yaml"})
        assert result == "tasks_us_mac Task"
