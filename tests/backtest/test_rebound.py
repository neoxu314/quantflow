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


def test_evaluate_uses_exact_entries_and_exit_prices_from_frozen_bars():
    from quantflow.backtest.rebound import evaluate
    from tests.support.replay_market import bars as market_bars

    data = market_bars(StockCode("AAPL", "US"))
    periods = {"complete": ("2025-06-03", "2025-07-01"), "short": ("2025-06-03", "2025-06-10")}
    periods["five_day_boundary"] = ("2025-06-03", "2025-06-11")
    periods["ten_day_boundary"] = ("2025-06-03", "2025-06-18")
    result = evaluate(data, periods, fee_bps=2, slippage_bps=5)
    studies = {(row["period"], row["scenario"], row["horizon"]): row for row in result["results"]}
    first = studies["complete", "first_oversold", 5]
    five, = first["events"]
    ten, = studies["complete", "first_oversold", 10]["events"]
    assert five["signal"] == ten["signal"] == "2025-06-04"
    assert five["entry"] == ten["entry"] == "2025-06-05"
    assert five["exit_target"] == "2025-06-11"
    assert ten["exit_target"] == "2025-06-18"
    assert five["net_return"] == pytest.approx(143.0 * .9993 / (138.4 * 1.0007) - 1)
    assert ten["net_return"] == pytest.approx(144.0 * .9993 / (138.4 * 1.0007) - 1)
    for horizon, period in ((5, "five_day_boundary"), (10, "ten_day_boundary")):
        boundary = studies[period, "first_oversold", horizon]
        assert boundary["complete"] == boundary["entries"] == 1
        assert boundary["events"] == studies["complete", "first_oversold", horizon]["events"]
    recovery, = studies["complete", "recovery_confirmed", 10]["events"]
    assert (recovery["signal"], recovery["entry"], recovery["exit_target"]) == (
        "2025-06-10", "2025-06-11", "2025-06-25",
    )
    assert studies["short", "first_oversold", 5]["status_counts"] == {"right_censored": 1}
    for window in (5, 10):
        daily = studies["complete", "each_oversold_day", window]["events"]
        assert [e["signal"] for e in daily] == [
            "2025-06-04", "2025-06-05", "2025-06-06", "2025-06-09",
        ]
        assert [e["status"] for e in daily] == ["complete", *(["overlap_skipped"] * 3)]
    assert evaluate(data.loc[data.date <= "2025-07-01"], periods)["results"] == result["results"]


def test_backtest_cli_records_snapshot_provenance_and_periods(tmp_path):
    import hashlib
    import json
    import subprocess
    import sys

    from tests.support.replay_market import bars as market_bars

    source = tmp_path / "history.csv"
    target = tmp_path / "results.json"
    market_bars(StockCode("AAPL", "US")).to_csv(source, index=False)
    subprocess.run(
        [sys.executable, "-m", "quantflow.backtest.rebound", "--input", str(source),
         "--output", str(target), "--start", "2025-05-01", "--holdout-start", "2025-06-01",
         "--end", "2025-07-01"], check=True, capture_output=True, timeout=15,
    )
    result = json.loads(target.read_text())
    assert result["input_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["symbols"] == ["AAPL.US"]
    first = next(r for r in result["results"] if
                 (r["period"], r["scenario"], r["horizon"]) == ("holdout", "first_oversold", 10))
    assert first["signals"] == first["complete"] == 1
    assert first["events"][0]["signal"] == "2025-06-04"


@pytest.mark.parametrize("horizon", [5, 10])
@pytest.mark.parametrize("delay", [1, 2])
def test_exit_on_cutoff_counts_and_open_position_stays_unrealized(horizon, delay):
    from quantflow.data.quality import daily_sessions

    code = StockCode("AAPL", "US")
    days = daily_sessions(code, "2025-06-26", "2025-07-31")
    bars = pd.DataFrame({"open": 100., "close": 102., "low": 99., "volume": 100}, index=days)
    flags = pd.Series(False, index=days)
    flags.iloc[[0, 2]] = True
    if delay == 2:
        bars.loc[days[1], "volume"] = 0
    exit_day = days[delay + horizon - 1]
    if horizon == 5 and delay == 1:
        assert str(exit_day.date()) == "2025-07-03"
    first, overlap = _trades(code, bars, flags, days[0], exit_day, horizon, 0)
    assert (first["status"], first["entry"], first["exit_target"]) == (
        "complete", str(days[delay].date()), str(exit_day.date()))
    assert first["net_return"] == pytest.approx(.02)
    assert overlap["status"] == "overlap_skipped"

    cutoff = days[delay + horizon - 2]
    events = _trades(code, bars, flags, days[0], cutoff, horizon, 0)
    truncated = _trades(code, bars.loc[:cutoff], flags.loc[:cutoff], days[0], cutoff, horizon, 0)
    assert events == truncated
    assert events[0] == {"code": "AAPL.US", "signal": "2025-06-26",
                         "entry": str(days[delay].date()), "status": "right_censored"}
    assert events[1]["status"] == "overlap_skipped"
    summary = _summarize(events)
    assert summary["entries"] == 1 and summary["entry_fill_rate"] == 1
    assert summary["complete"] == 0 and summary["win_rate"] is None


@pytest.mark.parametrize(("last_day", "status"), [(0, "right_censored"), (1, "right_censored"),
                                                   (2, "entry_blocked")])
def test_blocked_entry_at_sample_end_only_uses_observed_openings(last_day, status):
    days, bars, flags = _fixture()
    flags.iloc[2] = False
    bars.loc[days[1:3], "volume"] = 0
    event, = _trades(StockCode("AAPL", "US"), bars, flags, days[0], days[last_day], 5, 0)
    assert event["status"] == status and "entry" not in event
    summary = _summarize([event])
    assert summary["entries"] == 0
    assert summary["entry_fill_rate"] == (0 if last_day == 2 else None)
