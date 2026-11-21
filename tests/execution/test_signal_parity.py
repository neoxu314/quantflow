import pandas as pd
import pytest

from quantflow.backtest.rebound import _signals
from quantflow.data import StockCode
from quantflow.data.quality import normalize_ohlcv, tradable_bars
from quantflow.execution.executor import Executor, InsufficientHistoryError
from quantflow.execution.job import ExecutionJob
from quantflow.execution.watchlist import WatchlistItem
from quantflow.strategies.buy import DailyBullishOversoldBuy
from quantflow.strategies.sell import DualLineBearZoneSell
from tests.support.replay_market import bars


def test_confirmed_suspension_preserves_scan_and_backtest_parity():
    code = StockCode("AAPL", "US")
    frame = normalize_ohlcv(bars(code), end="2025-06-04")
    frame["trade_status"] = "1"
    frame.loc[frame.date.eq("2025-05-01"), ["trade_status", "volume"]] = ["0", 0]
    strategy = DailyBullishOversoldBuy()
    markers = _signals(frame.set_index("date"), strategy)
    executor = Executor()
    job = ExecutionJob("fixture", [], [strategy], ".")
    for date in pd.date_range("2025-05-28", "2025-06-04", freq="B"):
        history = tradable_bars(frame.loc[frame.date <= date])
        result = executor._process_single(WatchlistItem(code), code, history, job)
        assert bool(result) == bool(markers.loc[date, "each_oversold_day"])
    assert markers.iloc[-1].each_oversold_day
    gap = frame.set_index("date").drop(index="2025-05-01").reindex(markers.index)
    assert not _signals(gap, strategy).iloc[-1].any()


def test_trend_change_needs_two_warmed_days():
    code = StockCode("TEST", "US")
    frame = pd.DataFrame({"close": range(228, 0, -1)})
    strategy = DualLineBearZoneSell()
    job = ExecutionJob("fixture", [], [strategy], ".")
    executor = Executor()
    for length in (228, 115):
        assert executor._process_single(WatchlistItem(code), code, frame.tail(length), job) is None
    with pytest.raises(InsufficientHistoryError):
        executor._process_single(WatchlistItem(code), code, frame.tail(114), job)
    calculated = strategy.get_required_indicators()[0].calculate(frame.tail(114))
    assert not strategy.generate_signals(calculated).sell_signal.any()


def test_calculation_identity_ignores_documentation_and_detects_rule_changes(tmp_path):
    from quantflow.execution.identity import calculation_hash

    for name in (
        "execution/executor.py",
        "execution/storage.py",
        "execution/job.py",
        "orchestration/registry.py",
        "strategies/rule.py",
    ):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("def rule():\n    return 1\n")
    before = calculation_hash(tmp_path)
    path.write_text('# comment\ndef rule():\n    """Documentation."""\n    return 1\n')
    assert calculation_hash(tmp_path) == before
    path.write_text("def rule():\n    return 2\n")
    assert calculation_hash(tmp_path) != before
