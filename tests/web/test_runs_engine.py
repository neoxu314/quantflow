import pytest


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
