"""Regression contracts for D01/D02/D03/D05/D06/D08/D09 and checkpoint provenance."""
import json
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from quantflow.artifacts import atomic_json, create_run_directory, delete_owned_artifacts, finish_manifest
from quantflow.config.loader import ConfigLoader
from quantflow.control import ExecutionCancelled, cancellation_scope, cancellable_sleep
from quantflow.data import StockCode
from quantflow.data.trading_calendar import CALENDARS, session_schedule
from quantflow.execution.checkpoint import Checkpoint
from quantflow.execution.executor import Executor, InsufficientHistoryError
from quantflow.execution.job import ExecutionJob
from quantflow.execution.storage import ScanResults, StockOutcome, Storage
from quantflow.execution.watchlist import WatchlistItem
from quantflow.indicators.factory import IndicatorFactory
from quantflow.indicators.standard import RSIIndicator
from quantflow.strategies.buy import DailyBullishMidRangeBuy, DailyBullishOversoldBuy
from quantflow.strategies.sell import KDJDeadCrossSell
from quantflow.web.engine.run_engine import CancellationFlag

AS_OF = "2026-11-18T14:00:00+00:00"


def frame(rows=140, end="2026-11-18", exchange="SH"):
    year = pd.Timestamp(end).year
    calendar = CALENDARS[exchange]
    dates = session_schedule(calendar, year - 1).index.union(session_schedule(calendar, year).index)
    dates = dates[dates <= pd.Timestamp(end)][-rows:]
    prices = [100 + i * .1 for i in range(rows)]
    return pd.DataFrame({"date": dates,
                         "open": prices, "high": [p+1 for p in prices],
                         "low": [p-1 for p in prices], "close": prices, "volume": [1000]*rows})


def setup_executor(monkeypatch, tmp_path, df=None, codes=("600000.SH",)):
    executor = Executor()
    monkeypatch.setattr(executor.factory, "has_batch_support", lambda *a: False)
    mock = Mock(return_value=(frame() if df is None else df, "test-source"))
    monkeypatch.setattr(executor.factory, "fetch_ohlcv", mock)
    job = ExecutionJob("task", [WatchlistItem(StockCode.from_standard(c)) for c in codes],
                       [DailyBullishMidRangeBuy()], str(tmp_path), as_of=AS_OF)
    return executor, job, mock


@pytest.mark.parametrize("prices,expected", [(range(1,40),100), (range(40,1,-1),0), ([10]*40,50)])
def test_rsi_one_direction_and_flat(prices, expected):
    actual = RSIIndicator().calculate(pd.DataFrame({"close": list(prices)}))
    assert actual.RSI14.iloc[-1] == pytest.approx(expected)


def test_configured_indicators_reach_actual_execution(monkeypatch, tmp_path):
    monkeypatch.setattr(IndicatorFactory, "_config", {
        "DualLine": {"params": {"ema_period": 2, "ma_periods": [2,3,4,5]}}})
    executor, job, _ = setup_executor(monkeypatch, tmp_path, frame(20))
    results = executor.execute(job)
    assert results.summary["analyzed"] == 1
    context = json.loads((tmp_path / "task_context.json").read_text())
    assert context["execution"]["indicators"]["DualLine"]["ma_periods"] == [2,3,4,5]


def test_batch_requests_are_grouped_by_exchange_completed_session(monkeypatch, tmp_path):
    executor, job, _ = setup_executor(
        monkeypatch, tmp_path, codes=("600000.SH", "00700.HK", "AAPL.US")
    )
    request = Mock(side_effect=lambda codes, start, end, **kwargs: {
        code.standard: (frame(end=end, exchange=code.exchange), "fixture") for code in codes
    })
    monkeypatch.setattr(executor.factory, "has_batch_support", lambda *args: True)
    monkeypatch.setattr(executor.factory, "fetch_batch_ohlcv", request)
    results = executor.execute(job)

    assert results.summary["analyzed"] == 3
    assert {
        call.args[2]: [code.standard for code in call.args[0]] for call in request.call_args_list
    } == {"2026-11-18": ["600000.SH", "00700.HK"], "2026-11-17": ["AAPL.US"]}
    assert all(call.kwargs["require_end_session"] for call in request.call_args_list)


@pytest.mark.parametrize("reverse", [False, True])
def test_strategy_order_cannot_change_direction_counts(monkeypatch, tmp_path, reverse):
    executor = Executor()
    df = frame()
    df["short_trend_line"], df["long_short_line"] = 120., 100.
    df["is_bull_zone"], df["is_bear_zone"] = True, False
    df["K"], df["D"], df["J"] = 60., 50., 80.
    monkeypatch.setattr(executor.composer, "compose", lambda data: df.copy())
    item = WatchlistItem(StockCode("TEST", "US", "test company"))
    strategies = [DailyBullishMidRangeBuy(), KDJDeadCrossSell()]
    if reverse:
        strategies.reverse()
    job = ExecutionJob("test", [item], strategies, str(tmp_path))
    result = executor._process_single(item, item.code, df, job)
    assert result.buy_signals == 1
    assert result.sell_signals == 0
    assert result.matched_buy_strategies == ["DailyBullishMidRange"]
    assert result.name == "test company"


def test_outcomes_and_report_do_not_count_missing_as_no_signal(monkeypatch, tmp_path):
    executor, job, fetch = setup_executor(monkeypatch, tmp_path, codes=("600000.SH","600001.SH","600002.SH"))
    fetch.side_effect = [(frame(), "mock"), (pd.DataFrame(), None), RuntimeError("failure")]
    results = executor.execute(job)
    assert results.summary["analyzed"] == 1
    assert results.summary["no_data"] == 1
    assert results.summary["error"] == 1
    assert results.summary["no_signal"] == 1
    assert results.summary["status"] == "partial"
    assert results.summary["coverage"] == pytest.approx(1/3)
    assert results.summary["as_of"] == AS_OF
    from quantflow.reports.markdown import MarkdownReporter
    from quantflow.execution.watchlist import Watchlist
    path = MarkdownReporter().generate("task", job.strategies, results,
             Watchlist("watch", job.items), str(tmp_path), "2026-11-18")
    assert "**No Signals**: 1" in Path(path).read_text()
    assert "**no_data**: 1" in Path(path).read_text()
    assert f"**Market data cutoff**: {AS_OF}" in Path(path).read_text()


@pytest.mark.parametrize("end,status", [("2026-11-17","stale"), ("2026-11-18","insufficient")])
def test_stale_and_short_history_are_not_success(monkeypatch, tmp_path, end, status):
    executor, job, _ = setup_executor(monkeypatch, tmp_path, frame(5, end))
    result = executor.execute(job)
    assert result.summary[status] == 1
    assert result.summary["status"] == "failed"
    assert result.summary["no_signal"] == 0


def test_storage_failure_propagates_and_preserves_existing_file(monkeypatch, tmp_path):
    target = tmp_path / "results.json"
    target.write_text('["previous"]')
    def fail(*args):
        raise OSError("disk unavailable")
    monkeypatch.setattr("quantflow.artifacts.os.replace", fail)
    with pytest.raises(OSError):
        Storage().save_results(target, [])
    assert target.read_text() == '["previous"]'
    assert not list(tmp_path.glob('.quantflow-*'))


def test_run_ownership_and_modified_user_files(tmp_path):
    a, b = create_run_directory(tmp_path, "a"), create_run_directory(tmp_path, "b")
    atomic_json(a / "report.json", {"run":"a"})
    atomic_json(b / "report.json", {"run":"b"})
    atomic_json(a / "changed.json", {"original":True})
    finish_manifest(a, "completed")
    (a / "notes.txt").write_text("user notes")
    (a / "changed.json").write_text("user replacement")
    delete_owned_artifacts(a, "a")
    assert (b / "report.json").is_file()
    assert not (a / "report.json").exists()
    assert (a / "notes.txt").read_text() == "user notes"
    assert (a / "changed.json").read_text() == "user replacement"


def test_legacy_shared_directory_is_never_guessed_on_delete(tmp_path):
    (tmp_path / "Daily_Report.md").write_text("possibly newer report")
    delete_owned_artifacts(tmp_path, "old")
    assert (tmp_path / "Daily_Report.md").exists()


def test_resume_uses_frozen_data_and_retries_missing(monkeypatch, tmp_path):
    executor, job, fetch = setup_executor(monkeypatch, tmp_path, codes=("600000.SH", "600001.SH"))
    fetch.side_effect = [(frame(), "mock"), (pd.DataFrame(), None)]
    cp = Checkpoint("resume", tmp_path / "checkpoint.json")
    result = executor.execute(job, checkpoint=cp, task_key="t")
    assert cp.get_done("t") == {"600000.SH"}
    resumed_dir = tmp_path / "resumed"
    job.output_dir = str(resumed_dir)
    job.as_of = "2026-11-25T14:00:00+00:00"
    fetch.reset_mock(side_effect=True)
    fetch.return_value = (frame(), "mock")
    result = executor.execute(job, checkpoint=cp, task_key="t")
    assert fetch.call_count == 1
    assert result.summary["analyzed"] == 2
    assert fetch.call_args.args[2] == "2026-11-18"
    assert (resumed_dir / "snapshots/task/600000.SH.json").is_file()


def test_resume_rejects_changed_parameters(monkeypatch, tmp_path):
    executor, job, fetch = setup_executor(monkeypatch, tmp_path)
    cp = Checkpoint("c", tmp_path / "checkpoint.json")
    executor.execute(job, checkpoint=cp, task_key="t")
    monkeypatch.setattr(IndicatorFactory, "_config", {
        "DualLine": {"params": {"ema_period": 4, "ma_periods": [2,3,4,5]}}})
    with pytest.raises(ValueError, match="changed"):
        executor.execute(job, checkpoint=cp, task_key="t")


def test_cancellation_is_not_swallowed_as_stock_error(monkeypatch, tmp_path):
    executor, job, fetch = setup_executor(monkeypatch, tmp_path)
    flag = CancellationFlag()
    def download(*args, **kwargs):
        flag.cancel()
        return frame(), "mock"
    fetch.side_effect = download
    with pytest.raises(ExecutionCancelled), cancellation_scope(flag):
        executor.execute(job)
    assert not (tmp_path / "task.json").exists()


def test_cancelled_retry_sleep_returns_immediately():
    flag = CancellationFlag()
    with cancellation_scope(flag):
        flag.cancel()
        with pytest.raises(ExecutionCancelled):
            cancellable_sleep(30)


@pytest.mark.parametrize('batch', [False, True])
def test_per_stock_errors_are_isolated_for_both_fetch_modes(monkeypatch,tmp_path,batch):
    executor,job,fetch=setup_executor(monkeypatch,tmp_path,codes=('600000.SH','600001.SH','600002.SH'))
    bad=frame().drop(columns='date')
    if batch:
        monkeypatch.setattr(executor.factory,'has_batch_support',lambda *a:True)
        monkeypatch.setattr(executor.factory,'fetch_batch_ohlcv',lambda *a,**k:{
            '600000.SH':(frame(),'mock'), '600001.SH':(bad,'mock'), '600002.SH':(frame(),'mock')})
    else:
        fetch.side_effect=[(frame(),'mock'),(bad,'mock'),(frame(),'mock')]
    result=executor.execute(job)
    assert result.summary['analyzed']==2 and result.summary['error']==1
    assert result.summary['status']=='partial'


def test_snapshot_write_failure_is_fatal(monkeypatch,tmp_path):
    from quantflow.artifacts import atomic_json as real_write, ArtifactWriteError
    executor,job,fetch=setup_executor(monkeypatch,tmp_path)
    def write(path,payload):
        if 'snapshots' in Path(path).parts:
            raise ArtifactWriteError('snapshot disk unavailable')
        return real_write(path,payload)
    monkeypatch.setattr('quantflow.execution.executor.atomic_json',write)
    with pytest.raises(ArtifactWriteError,match='snapshot'):
        executor.execute(job)
    assert not (tmp_path/'task.json').exists()


def test_indicator_changes_mid_run_apply_only_to_next_run(monkeypatch,tmp_path):
    first={'DualLine':{'params':{'ema_period':2,'ma_periods':[2,3,4,5]}}}
    monkeypatch.setattr(IndicatorFactory,'_config',first)
    executor,job,fetch=setup_executor(monkeypatch,tmp_path,frame(20),codes=('600000.SH','600001.SH'))
    def download(*args,**kwargs):
        IndicatorFactory._config={'DualLine':{'params':{'ema_period':10,'ma_periods':[14,28,57,114]}}}
        return frame(20),'mock'
    fetch.side_effect=download
    result=executor.execute(job)
    assert result.summary['analyzed']==2
    assert result.summary['insufficient']==0
    next_run=executor.execute(job)
    assert next_run.summary['insufficient']==2


def test_resume_rejects_modified_snapshot(monkeypatch,tmp_path):
    executor,job,fetch=setup_executor(monkeypatch,tmp_path)
    cp=Checkpoint('c',tmp_path/'checkpoint.json')
    executor.execute(job,checkpoint=cp,task_key='t')
    snapshot=Path(cp.get_stats('t','600000.SH')['outcome']['snapshot_path'])
    snapshot.write_text('{}')
    with pytest.raises(ValueError,match='modified'):
        executor.execute(job,checkpoint=cp,task_key='t')


def test_repeated_resume_is_independent_of_original_run_artifacts(monkeypatch,tmp_path):
    executor,job,fetch=setup_executor(monkeypatch,tmp_path)
    cp=Checkpoint('c',tmp_path/'checkpoint.json')
    executor.execute(job,checkpoint=cp,task_key='t')
    original=Path(cp.get_stats('t','600000.SH')['outcome']['snapshot_path'])
    job.output_dir=str(tmp_path/'second')
    executor.execute(job,checkpoint=cp,task_key='t')
    original.unlink()
    job.output_dir=str(tmp_path/'third')
    fetch.side_effect=AssertionError('Must not refetch a completed unit')
    result=executor.execute(job,checkpoint=cp,task_key='t')
    assert result.summary['analyzed']==1
    current=Path(cp.get_stats('t','600000.SH')['outcome']['snapshot_path'])
    assert current.is_file() and 'third' in current.parts


def test_internal_data_gap_blocks_strategy_and_is_reported(monkeypatch, tmp_path):
    data = frame()
    missing = data.date.iloc[-5].strftime("%Y-%m-%d")
    executor, job, _ = setup_executor(monkeypatch, tmp_path, data.drop(data.index[-5]))
    unexpected_execution = Mock(side_effect=AssertionError("strategy should not run"))
    monkeypatch.setattr(executor, "_process_single", unexpected_execution)

    results = executor.execute(job)
    unexpected_execution.assert_not_called()
    assert results == []
    assert results.summary["data_gap"] == 1
    assert results.summary["status"] == "failed"
    assert results.summary["no_signal"] == 0
    assert results.outcomes[0].missing_sessions == (missing,)
    coverage = json.loads((tmp_path / "task_coverage.json").read_text())
    assert coverage["outcomes"][0]["missing_sessions"] == [missing]
