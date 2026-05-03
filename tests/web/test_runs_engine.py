import pytest
import shutil
import tempfile
from pathlib import Path
from quantflow.web.engine import run_history

# Preserve original DB path for teardown
_ORIG_DB_PATH = run_history.DB_PATH


class TestRunHistory:

    def setup_method(self):
        run_history.DB_PATH = Path(":memory:")
        run_history._MEMORY_CONN = None
        run_history._connect()

    def teardown_method(self):
        run_history.DB_PATH = _ORIG_DB_PATH
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
        rid = h.create_run("From Preset", "stock_scan", {},
                           preset_id="my-preset")
        run = h.get_run(rid)
        assert run.preset_id == "my-preset"


class TestRunQueue:
    def test_first_enqueue_active(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue()
        assert q.enqueue("r1") is True
        assert q.active == "r1"

    def test_second_enqueue_pending(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue()
        q.enqueue("r1")
        assert q.enqueue("r2") is False
        assert q.get_state().pending_count == 1

    def test_dequeue_promotes_next(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue()
        q.enqueue("r1"); q.enqueue("r2"); q.enqueue("r3")
        assert q.dequeue() == "r2"
        assert q.active == "r2"

    def test_dequeue_empty(self):
        from quantflow.web.engine.run_queue import RunQueue
        assert RunQueue().dequeue() is None

    def test_cancel_pending(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue()
        q.enqueue("r1"); q.enqueue("r2")
        assert q.cancel("r2") is True
        assert q.get_state().pending_count == 0

    def test_cancel_active_false(self):
        from quantflow.web.engine.run_queue import RunQueue
        q = RunQueue(); q.enqueue("r1")
        assert q.cancel("r1") is False

    def test_callback_on_available(self):
        from quantflow.web.engine.run_queue import RunQueue
        results = []
        q = RunQueue(on_run_available=lambda rid: results.append(rid))
        q.enqueue("r1")
        assert "r1" in results


class TestSSEManager:
    def test_subscribe_and_publish(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q = m.subscribe("r1")
        m.publish_log("r1", "hello")
        assert q.get(timeout=1)["data"]["message"] == "hello"

    def test_progress_pct(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q = m.subscribe("r1")
        m.publish_progress("r1", 12, 50)
        assert q.get(timeout=1)["data"]["percentage"] == 24

    def test_status(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q = m.subscribe("r1")
        m.publish_status("r1", "completed", signal_count=3)
        d = q.get(timeout=1)["data"]
        assert d["status"] == "completed" and d["signal_count"] == 3

    def test_unsubscribe(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager(); q = m.subscribe("r1")
        m.unsubscribe("r1", q)
        m.publish_log("r1", "gone")
        assert q.empty()

    def test_multiple_subscribers(self):
        from quantflow.web.engine.sse import SSEManager
        m = SSEManager()
        q1 = m.subscribe("r1"); q2 = m.subscribe("r1")
        m.publish_log("r1", "both")
        assert q1.get(timeout=1)["data"]["message"] == "both"
        assert q2.get(timeout=1)["data"]["message"] == "both"


class TestPreflightChecker:
    def test_valid_stock(self):
        from quantflow.web.engine.preflight import PreflightChecker
        assert PreflightChecker.validate("stock_scan", {"code": "NVDA.US"}).ok

    def test_invalid_code_fmt(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("stock_scan", {"code": "NVDA"})
        assert not r.ok and any(
            "Invalid stock code" in e for e in r.errors)

    def test_missing_code(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("stock_scan", {})
        assert not r.ok and any("required" in e for e in r.errors)

    def test_bad_date_order(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("stock_scan", {
            "code": "NVDA.US",
            "start_date": "2026-06-01",
            "end_date": "2026-05-01",
        })
        assert not r.ok and any("after" in e.lower() for e in r.errors)

    def test_unknown_run_type(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("bogus", {})
        assert not r.ok

    def test_unknown_indicator(self):
        from quantflow.web.engine.preflight import PreflightChecker
        r = PreflightChecker.validate("stock_scan",
            {"code": "NVDA.US", "indicators": ["magic"]})
        assert not r.ok and any("Unknown indicator" in e for e in r.errors)


class TestRunEngine:
    def test_cancellation_flag(self):
        from quantflow.web.engine.run_engine import CancellationFlag
        f = CancellationFlag()
        assert f.is_set is False
        f.cancel()
        assert f.is_set is True

    def test_cancel_unknown(self):
        from quantflow.web.engine import RunEngine, RunQueue, SSEManager
        from quantflow.web.engine import run_history
        orig = run_history.DB_PATH
        run_history.DB_PATH = Path(":memory:")
        engine = RunEngine(RunQueue(), run_history.RunHistory(), SSEManager())
        assert engine.cancel("nope") is False
        run_history.DB_PATH = orig


class TestPresetManager:
    def setup_method(self):
        import tempfile
        from quantflow.web.engine import presets
        self._orig = presets.PRESETS_DIR
        self._tmp = tempfile.mkdtemp()
        presets.PRESETS_DIR = Path(self._tmp)

    def teardown_method(self):
        from quantflow.web.engine import presets
        presets.PRESETS_DIR = self._orig
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_create_and_get(self):
        from quantflow.web.engine.presets import PresetManager
        pid = PresetManager.create(
            "My Scan", "stock_scan", {"code": "NVDA.US"})
        p = PresetManager.get(pid)
        assert p.name == "My Scan"
        assert p.config["code"] == "NVDA.US"

    def test_list_presets(self):
        from quantflow.web.engine.presets import PresetManager
        PresetManager.create("A", "stock_scan", {})
        PresetManager.create("B", "watchlist_run", {})
        assert len(PresetManager.list_presets()) == 2

    def test_update(self):
        from quantflow.web.engine.presets import PresetManager
        pid = PresetManager.create("Old", "stock_scan", {})
        PresetManager.update(pid, "New", "task_run", {"task_config": "x"})
        assert PresetManager.get(pid).name == "New"

    def test_delete(self):
        from quantflow.web.engine.presets import PresetManager
        pid = PresetManager.create("T", "stock_scan", {})
        assert PresetManager.delete(pid) is True
        assert PresetManager.get(pid) is None

    def test_delete_nonexistent(self):
        from quantflow.web.engine.presets import PresetManager
        assert PresetManager.delete("no-such-preset") is False
