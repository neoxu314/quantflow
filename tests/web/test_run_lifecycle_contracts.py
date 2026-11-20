"""API-to-worker contracts for cancellation, output ownership and failure states."""
import json
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quantflow.artifacts import atomic_json, create_run_directory, finish_manifest
from quantflow.execution.storage import ScanResults, StockOutcome
from quantflow.web.api import runs
from quantflow.web.engine import RunHistory, RunQueue, SSEManager
from quantflow.web.engine.run_engine import RunEngine
from quantflow.web.engine.run_queue import QueueFullError


@pytest.fixture
def env(tmp_path,monkeypatch):
    history,queue,sse=RunHistory(),RunQueue(),SSEManager()
    engine=RunEngine(queue,history,sse)
    monkeypatch.setattr(runs._get_engine,'_instance',engine,raising=False)
    app=FastAPI(); app.include_router(runs.router)
    wl=tmp_path/'watch.yaml';wl.write_text('name: watch\nitems:\n- code: AAPL.US\n')
    return engine,TestClient(app),tmp_path,wl


def create(engine,root,wl,kind='watchlist_run'):
    cfg={'watchlist':str(wl),'output_path':str(root),'strategies':['daily_bull_oversold']}
    rid=engine._history.create_run('test',kind,cfg)
    engine._queue.enqueue(rid)
    return rid


def test_cancel_waits_for_worker_before_queue_handoff(env,monkeypatch):
    engine,client,root,wl=env
    a=create(engine,root,wl);b=create(engine,root,wl);c=create(engine,root,wl)
    entered,release=threading.Event(),threading.Event()
    def execute(*args,**kwargs):
        entered.set()
        assert release.wait(5)
        return ScanResults([], [StockOutcome('AAPL.US','no_signal')])
    monkeypatch.setattr('quantflow.execution.executor.Executor.execute',execute)
    reporter=Mock();monkeypatch.setattr('quantflow.reports.markdown.MarkdownReporter.generate',reporter)
    worker=threading.Thread(target=engine._execute_run,args=(a,));worker.start()
    assert entered.wait(5)
    response=client.post(f'/api/runs/{a}/cancel')
    assert response.json()['status']=='cancelling'
    assert engine._queue.active==a
    assert client.delete(f'/api/runs/{a}').status_code==409
    engine.start_processing.assert_not_called()
    release.set();worker.join(5);assert not worker.is_alive()
    assert engine._history.get_run(a).status=='cancelled'
    reporter.assert_not_called()
    engine.start_processing.assert_called_once_with(b)
    assert engine._queue.active==b
    assert engine._queue.finish(a) is None
    assert engine._queue.active==b
    manifest=Path(engine._history.get_run(a).output_path)/'manifest.json'
    assert json.loads(manifest.read_text())['status']=='cancelled'


def test_initialization_failure_releases_queue_and_persists_failed(env,monkeypatch):
    engine,client,root,wl=env
    a=create(engine,root,wl); b=create(engine,root,wl)
    def fail(*a):raise OSError('logging setup failed')
    monkeypatch.setattr('quantflow.web.engine.run_engine.setup_logging',fail)
    engine._execute_run(a)
    assert engine._history.get_run(a).status=='failed'
    engine.start_processing.assert_called_once_with(b)
    assert engine._queue.active==b
    assert not engine._workers


@pytest.mark.parametrize('status', ['partial','failed','completed'])
def test_worker_persists_actual_coverage_state(env,monkeypatch,status):
    engine,client,root,wl=env
    rid=create(engine,root,wl)
    outcomes={'completed':[StockOutcome('AAPL.US','no_signal')],
              'failed':[StockOutcome('AAPL.US','no_data')],
              'partial':[StockOutcome('AAPL.US','no_signal'),StockOutcome('B.US','error')]}
    monkeypatch.setattr('quantflow.execution.executor.Executor.execute',
                        lambda *a,**k: ScanResults([],outcomes[status]))
    engine._execute_run(rid)
    record=engine._history.get_run(rid)
    assert record.status==status
    summary=json.loads((Path(record.output_path)/'Run_Summary.json').read_text())
    assert summary['status']==status
    assert engine._queue.active is None
    assert Path(record.report_path).is_file()


def test_old_run_deletion_does_not_touch_newer_run(env):
    engine,client,root,wl=env
    ids=[]
    for name in ['old','new']:
        rid=engine._history.create_run(name,'stock_scan',{})
        output=create_run_directory(root,rid)
        atomic_json(output/'AAPL.US_indicators.json',{'run':name})
        finish_manifest(output,'completed')
        engine._history.update_status(rid,'completed',output_path=str(output),
                                      report_path=str(output/'AAPL.US_indicators.json'))
        ids.append(rid)
    assert client.delete(f'/api/runs/{ids[0]}').json()['ok']
    new=engine._history.get_run(ids[1])
    assert json.loads(Path(new.report_path).read_text())=={'run':'new'}
    assert client.get(f'/api/runs/{ids[1]}/files').json()['files'][0]['name']=='AAPL.US_indicators.json'


def test_legacy_delete_preserves_shared_report(env):
    engine,client,root,wl=env
    p=root/'Daily_Report.md';p.write_text('newest report')
    rid=engine._history.create_run('legacy','task_run',{})
    engine._history.update_status(rid,'completed',output_path=str(root),report_path=str(p))
    assert client.delete(f'/api/runs/{rid}').json()['ok']
    assert p.read_text()=='newest report'


def test_cancel_unknown_or_completed_run_is_rejected(env):
    engine,client,root,wl=env
    assert client.post('/api/runs/unknown/cancel').status_code==404
    rid=engine._history.create_run('finished','stock_scan',{})
    engine._history.update_status(rid,'completed')
    assert client.post(f'/api/runs/{rid}/cancel').status_code==400
    assert engine._history.get_run(rid).status=='completed'


def test_cancel_pending_never_advances_active_slot(env):
    engine,client,root,wl=env
    a=create(engine,root,wl);b=create(engine,root,wl)
    assert client.post(f'/api/runs/{b}/cancel').json()['status']=='cancelled'
    assert engine._queue.active==a
    engine.start_processing.assert_not_called()


def test_queue_full_rejects_without_orphan_record(env):
    engine,client,root,wl=env
    engine._queue=RunQueue(max_pending=0)
    create(engine,root,wl)
    before=len(engine._history.list_runs())
    response=client.post('/api/runs/',json={'run_type':'watchlist_run','watchlist':str(wl)})
    assert response.status_code==429
    assert len(engine._history.list_runs())==before


def test_terminal_cancellation_cannot_be_overwritten(env):
    engine,client,root,wl=env
    rid=engine._history.create_run('cancelled','watchlist_run',{})
    engine._history.update_status(rid,'cancelled')
    engine._history.update_status(rid,'completed')
    assert engine._history.get_run(rid).status=='cancelled'


def test_legacy_report_is_explicitly_unverified(env):
    engine,client,root,wl=env
    p=root/'shared.md';p.write_text('possibly newer report')
    rid=engine._history.create_run('legacy','watchlist_run',{})
    engine._history.update_status(rid,'completed',report_path=str(p),output_path=str(root))
    data=client.get(f'/api/runs/{rid}/report').json()
    assert data['report']=='possibly newer report'
    assert 'cannot be verified' in data['legacy_warning']


def test_owned_report_has_no_legacy_warning(env):
    from quantflow.artifacts import atomic_text
    engine,client,root,wl=env
    rid=engine._history.create_run('owned','watchlist_run',{})
    output=create_run_directory(root,rid)
    p=output/'report.md';atomic_text(p,'owned report')
    finish_manifest(output,'completed')
    engine._history.update_status(rid,'completed',report_path=str(p),output_path=str(output))
    assert client.get(f'/api/runs/{rid}/report').json()['legacy_warning'] is None


@pytest.mark.parametrize("fail", [False, True])
def test_worker_publishes_terminal_status_after_manifest(env, monkeypatch, fail):
    engine, client, root, wl = env
    run_id = create(engine, root, wl)
    next_id = create(engine, root, wl)
    monkeypatch.setattr(
        "quantflow.execution.executor.Executor.execute",
        lambda *args, **kwargs: ScanResults([], [StockOutcome("AAPL.US", "no_signal")]),
    )
    statuses = []
    monkeypatch.setattr(engine._sse, "publish_status", lambda _, status: statuses.append(status))

    def finalize(output, status, **metadata):
        assert engine._history.get_run(run_id).status == "running"
        assert statuses == ["running"]
        assert engine._queue.active == run_id
        if fail:
            raise OSError("disk full")
        finish_manifest(output, status, **metadata)

    finalize_manifest = Mock(side_effect=finalize)
    monkeypatch.setattr("quantflow.web.engine.run_engine.finish_manifest", finalize_manifest)
    engine._execute_run(run_id)

    finalize_manifest.assert_called_once()
    run = engine._history.get_run(run_id)
    assert run.status == ("failed" if fail else "completed")
    assert statuses == ["running", run.status]
    if fail:
        assert "Manifest finalization failed: disk full" in run.error
    else:
        manifest = json.loads((Path(run.output_path) / "manifest.json").read_text())
        assert manifest["status"] == "completed"
    engine.start_processing.assert_called_once_with(next_id)


@pytest.mark.parametrize("mode", ["timeout", "rate_limit"])
def test_cancel_during_provider_io_or_backoff(env, monkeypatch, mode):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import requests
    from yfinance import exceptions

    from quantflow.data.adapters import yfinance as adapter

    engine, client, root, wl = env
    active = create(engine, root, wl)
    next_id = create(engine, root, wl)
    waiting, release = threading.Event(), threading.Event()
    actual_sleep = adapter.cancellable_sleep

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if mode == "timeout":
                waiting.set()
                release.wait(5)
                return
            self.send_response(429)
            self.end_headers()

        def log_message(self, *_args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as provider:
        http_thread = threading.Thread(target=provider.serve_forever)
        http_thread.start()
        worker = threading.Thread(target=engine._execute_run, args=(active,))
        try:
            def download(**_kwargs):
                response = requests.get(
                    f"http://127.0.0.1:{provider.server_port}/", timeout=1
                )
                if response.status_code == 429:
                    raise exceptions.YFRateLimitError()
                response.raise_for_status()

            def backoff(seconds):
                waiting.set()
                actual_sleep(seconds)

            feed = adapter.YFinanceDataSource(retry_base_delay=30)

            def execute(*_args, **_kwargs):
                feed._download_chunk(["AAPL"], "2026-11-16", "2026-11-20", "1d")
                pytest.fail("Cancellation should exit the download")

            monkeypatch.setattr("yfinance.download", download)
            monkeypatch.setattr(adapter, "cancellable_sleep", backoff)
            monkeypatch.setattr("quantflow.execution.executor.Executor.execute", execute)
            worker.start()
            assert waiting.wait(3)
            assert client.post(f"/api/runs/{active}/cancel").json()["status"] == "cancelling"
            worker.join(3)
            assert not worker.is_alive()
            assert engine._history.get_run(active).status == "cancelled"
            engine.start_processing.assert_called_once_with(next_id)
        finally:
            release.set()
            provider.shutdown()
            http_thread.join()
            if worker.ident is not None:
                worker.join(3)


@pytest.mark.parametrize("batch", [False, True])
def test_cancel_during_yahooquery_session_setup_skips_history(env, monkeypatch, batch):
    from quantflow.data import StockCode
    from quantflow.data.adapters.yahooquery import YahooQueryDataSource

    engine, client, root, wl = env
    active = create(engine, root, wl)
    next_id = create(engine, root, wl)
    setting_up, release = threading.Event(), threading.Event()
    ticker = Mock()

    def connect(*_args, **_kwargs):
        setting_up.set()
        assert release.wait(5)
        return ticker

    def execute(*_args, **_kwargs):
        provider = YahooQueryDataSource()
        code = StockCode("AAPL", "US")
        args = ("2026-11-16", "2026-11-20")
        if batch:
            provider.fetch_batch_ohlcv([code], *args)
        else:
            provider.fetch_ohlcv(code, *args)
        pytest.fail("Cancellation should stop before asking for history")

    monkeypatch.setattr("yahooquery.Ticker", connect)
    monkeypatch.setattr("quantflow.execution.executor.Executor.execute", execute)
    worker = threading.Thread(target=engine._execute_run, args=(active,))
    worker.start()
    try:
        assert setting_up.wait(3)
        assert client.post(f"/api/runs/{active}/cancel").json()["status"] == "cancelling"
        assert engine._queue.active == active
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    ticker.history.assert_not_called()
    assert engine._history.get_run(active).status == "cancelled"
    engine.start_processing.assert_called_once_with(next_id)


@pytest.mark.parametrize("corrupt", [False, True])
def test_restart_reconciles_crash_between_manifest_and_database(env, monkeypatch, corrupt):
    from quantflow.web.engine.run_history import RunHistory

    engine, client, root, wl = env
    run_id = create(engine, root, wl)
    monkeypatch.setattr(
        "quantflow.execution.executor.Executor.execute",
        lambda *args, **kwargs: ScanResults([], [StockOutcome("AAPL.US", "no_signal")]),
    )
    update_status = engine._history.update_status

    def fail_after_manifest(rid, status, **fields):
        if status == "completed":
            raise OSError("SQLite went away at final commit")
        return update_status(rid, status, **fields)

    monkeypatch.setattr(engine._history, "update_status", fail_after_manifest)
    with pytest.raises(OSError, match="final commit"):
        engine._execute_run(run_id)
    before = engine._history.get_run(run_id)
    assert before.status == "running" and before.report_path is None
    manifest = json.loads((Path(before.output_path) / "manifest.json").read_text())
    report = Path(before.output_path) / manifest["run_result"]["report"]
    if corrupt:
        report.write_text("changed")

    restarted = RunHistory()
    assert restarted.reconcile_stale_runs() == 1
    after = restarted.get_run(run_id)
    assert after.status == ("interrupted" if corrupt else "completed")
    if not corrupt:
        assert after.report_path == str(report)
        assert after.finished_at == manifest["finished_at"]
    assert restarted.reconcile_stale_runs() == 0
