"""Tests for web/engine modules."""
import os
import shutil
import tempfile
import pytest
from pathlib import Path

TESTS_PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("PYTHONPATH", str(TESTS_PROJECT_ROOT / "src"))


class TestRunHistory:
    """Test SQLite RunHistory CRUD (uses in-memory DB)."""

    def setup_method(self):
        from quantflow.web.engine import run_history
        self._orig_db = run_history.DB_PATH
        run_history.DB_PATH = Path(":memory:")
        run_history._MEMORY_CONN = None  # Reset for fresh DB per test
        run_history._connect()  # Init schema

    def teardown_method(self):
        from quantflow.web.engine import run_history
        run_history.DB_PATH = self._orig_db
        run_history._MEMORY_CONN = None

    def test_create_and_get_run(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("Test", "stock_scan", {"code": "NVDA.US"})
        run = h.get_run(rid)
        assert run.name == "Test"
        assert run.status == "queued"
        assert run.config == {"code": "NVDA.US"}

    def test_update_status_completed(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("T", "stock_scan", {})
        h.update_status(rid, "completed", signal_count=3, duration_ms=5000)
        run = h.get_run(rid)
        assert run.status == "completed"
        assert run.signal_count == 3

    def test_update_status_failed(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("T", "task_run", {})
        h.update_status(rid, "failed", error="oops")
        assert h.get_run(rid).error == "oops"

    def test_invalid_run_type_raises(self):
        from quantflow.web.engine.run_history import RunHistory
        with pytest.raises(ValueError):
            RunHistory().create_run("T", "bad_type", {})

    def test_list_runs_ordered(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        h.create_run("A", "stock_scan", {})
        h.create_run("B", "watchlist_run", {})
        h.create_run("C", "stock_scan", {})
        runs = h.list_runs()
        assert runs[0].name == "C"

    def test_list_by_status(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("Failed", "stock_scan", {})
        h.update_status(rid, "failed", error="x")
        h.create_run("Running", "task_run", {})
        failed = h.list_runs(status="failed")
        assert len(failed) == 1
        assert failed[0].name == "Failed"

    def test_get_nonexistent_returns_none(self):
        from quantflow.web.engine.run_history import RunHistory
        assert RunHistory().get_run("no-such-id") is None

    def test_create_with_preset_id(self):
        from quantflow.web.engine.run_history import RunHistory
        h = RunHistory()
        rid = h.create_run("From Preset", "stock_scan", {}, preset_id="my-preset")
        run = h.get_run(rid)
        assert run.preset_id == "my-preset"
