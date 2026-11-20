import pandas as pd
import pytest

from quantflow.backtest.rebound import _eligible, _summarize, _trades
from quantflow.data import StockCode


def _fixture():
    days = pd.bdate_range("2025-06-02", periods=18)
    bars = pd.DataFrame({"open": 100.0, "close": 104.0, "low": 97.0, "volume": 100}, index=days)
    flags = pd.Series(False, index=days)
    flags.iloc[[0, 2]] = True
    return days, bars, flags


def test_rebound_uses_next_eligible_open_and_market_sessions():
    dates, bars, flags = _fixture()
    bars.loc[dates[1], "volume"] = 0
    code = StockCode("AAPL", "US")
    first, overlapped = _trades(code, bars, flags, dates[0], dates[-1], 5, .001)
    assert first["entry"] == dates[2].date().isoformat()
    assert first["exit_target"] == dates[6].date().isoformat()
    assert first["net_return"] == pytest.approx(104 * .999 / (100 * 1.001) - 1)
    assert first["max_adverse"] == pytest.approx(97 / (100 * 1.001) - 1)
    assert overlapped["status"] == "overlap_skipped"


def test_unknown_first_day_does_not_silently_become_a_fill():
    dates, bars, flags = _fixture()
    flags.iloc[2] = False
    bars.loc[dates[1], "open"] = float("nan")
    events = _trades(StockCode("AAPL", "US"), bars, flags, dates[0], dates[-1], 5, 0)
    assert events[0]["status"] == "entry_unknown"
    assert _summarize(events)["entry_fill_rate"] == 0
    assert _eligible(bars.iloc[3], "SZ", "buy") is None
    blocked = pd.Series({"open": 100, "volume": 100, "buy_allowed": False})
    assert _eligible(blocked, "SZ", "buy") is False
