"""Evaluate rebound entries from a frozen daily OHLCV snapshot."""

import argparse
import hashlib
import math
from collections import Counter
from pathlib import Path

import pandas as pd

from quantflow.artifacts import atomic_json
from quantflow.data import StockCode
from quantflow.data.quality import daily_sessions, normalize_ohlcv, tradable_bars
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.factory import IndicatorFactory
from quantflow.strategies.buy import DailyBullishOversoldBuy

SCENARIOS = ("first_oversold", "each_oversold_day", "recovery_confirmed")
HORIZONS = (5, 10)


def _eligible(row, market, side):
    """An absent bar has unknown tradability, even if a later bar exists."""
    if pd.isna(row.open) or pd.isna(row.volume):
        return None
    if row.volume <= 0 or str(row.get("trade_status")) == "0":
        return False
    value = row.get(f"{side}_allowed")
    if pd.isna(value):
        return True if market == "US" else None
    value = str(value).lower()
    if value in ("true", "1"):
        return True
    if value in ("false", "0"):
        return False
    raise ValueError(f"Invalid {side}_allowed value: {value}")


def _signals(bars, strategy):
    indicators = strategy.get_required_indicators()
    warmup = max(indicator.lookback_bars for indicator in indicators)
    markers = pd.DataFrame(False, index=bars.index, columns=SCENARIOS)
    # A missing session breaks the observed history. A recorded suspension
    # consumes a calendar session but contributes no bar to either calculator.
    segment = bars.open.isna().cumsum()
    observed = tradable_bars(bars.loc[bars.open.notna()])
    for _, part in observed.groupby(segment):
        if len(part) < warmup:
            continue
        calculated = IndicatorComposer(indicators).compose(part)
        signaled = strategy.generate_signals(calculated)
        active = signaled.buy_signal.astype(bool)
        previous = active.shift(fill_value=False)
        supported = (signaled.short_trend_line > signaled.long_short_line) & (
            signaled.close >= signaled.long_short_line
        )
        flags = pd.DataFrame({
            "first_oversold": active & ~previous,
            "each_oversold_day": active,
            "recovery_confirmed": previous & signaled.J.ge(20) & supported,
        }, index=part.index)
        # Also require a fully warmed previous observation for transitions.
        markers.loc[part.index[warmup:]] = flags.iloc[warmup:]
        first_ready = part.index[warmup - 1]
        markers.loc[first_ready, "each_oversold_day"] = active.loc[first_ready]
    return markers


def _trades(code, bars, candidates, first, last, horizon, side_cost):
    dates = bars.index
    cutoff = dates.searchsorted(pd.Timestamp(last), side="right") - 1
    busy_until = -1
    results = []
    for pos in dates.get_indexer(candidates.loc[first:last].index[candidates.loc[first:last]]):
        event = {"code": code.standard, "signal": dates[pos].date().isoformat()}
        results.append(event)
        if pos + 2 + horizon - 1 > cutoff:
            event["status"] = "right_censored"
            continue
        if pos < busy_until:
            event["status"] = "overlap_skipped"
            continue
        entry = None
        for index in range(pos + 1, pos + 3):
            allowed = _eligible(bars.iloc[index], code.exchange, "buy")
            if allowed is None:
                event["status"] = "entry_unknown"
                break
            if allowed:
                entry = index
                break
        if entry is None:
            event.setdefault("status", "entry_blocked")
            continue
        exit_index = entry + horizon - 1
        event["entry"] = dates[entry].date().isoformat()
        event["exit_target"] = dates[exit_index].date().isoformat()
        allowed = _eligible(bars.iloc[exit_index], code.exchange, "sell")
        if allowed is not True:
            event["status"] = "exit_unknown" if allowed is None else "exit_blocked"
            busy_until = cutoff
            continue
        entry_price = bars.open.iloc[entry] * (1 + side_cost)
        exit_price = bars.close.iloc[exit_index] * (1 - side_cost)
        lows = bars.low.iloc[entry:exit_index + 1]
        event.update(
            status="complete",
            net_return=float(exit_price / entry_price - 1),
            max_adverse=(
                min(0.0, float(lows.min() / entry_price - 1)) if lows.notna().all() else None
            ),
        )
        busy_until = exit_index
    return results


def _summarize(events):
    counts = Counter(event["status"] for event in events)
    considered = len(events) - counts["right_censored"] - counts["overlap_skipped"]
    entered = counts["complete"] + counts["exit_unknown"] + counts["exit_blocked"]
    realized = pd.Series(
        [event["net_return"] for event in events if event["status"] == "complete"], dtype=float
    )
    adverse = pd.Series(
        [event["max_adverse"] for event in events if event.get("max_adverse") is not None],
        dtype=float,
    )
    return {
        "signals": len(events),
        "status_counts": dict(counts),
        "entries": entered,
        "entry_fill_rate": entered / considered if considered else None,
        "complete": len(realized),
        "net_mean": float(realized.mean()) if len(realized) else None,
        "net_median": float(realized.median()) if len(realized) else None,
        "win_rate": float(realized.gt(0).mean()) if len(realized) else None,
        "adverse_median": float(adverse.median()) if len(adverse) else None,
        "adverse_p10": float(adverse.quantile(.10)) if len(adverse) else None,
        "adverse_observed": len(adverse),
    }


@IndicatorFactory.snapshot()
def evaluate(frame, periods, fee_bps=2, slippage_bps=5):
    """Compare fixed entries, with at most one live position per symbol and scenario."""
    cost = (fee_bps + slippage_bps) / 10_000
    if not all(math.isfinite(v) and v >= 0 for v in (fee_bps, slippage_bps)) or cost >= 1:
        raise ValueError("Fee and slippage must be finite, nonnegative and total less than 100%")
    strategy = DailyBullishOversoldBuy()
    studies = {
        (period, scenario, horizon): []
        for period in periods for scenario in SCENARIOS for horizon in HORIZONS
    }
    for symbol, quotes in frame.groupby("code", sort=True):
        code = StockCode.from_standard(symbol)
        bars = normalize_ohlcv(quotes).set_index("date")
        if bars.empty:
            continue
        sessions = daily_sessions(code, bars.index[0], bars.index[-1])
        if not bars.index.difference(sessions).empty:
            raise ValueError(f"{code.standard} has bars on non-trading dates")
        bars = bars.reindex(sessions)
        signals = _signals(bars, strategy)
        for (period, scenario, horizon), events in studies.items():
            events.extend(_trades(code, bars, signals[scenario], *periods[period], horizon, cost))

    return {
        "fee_bps_per_side": fee_bps,
        "slippage_bps_per_side": slippage_bps,
        "max_entry_delay_sessions": 2,
        "horizons": HORIZONS,
        "periods": periods,
        "indicator_params": {
            indicator.name: indicator.params for indicator in strategy.get_required_indicators()
        },
        "results": [
            {"period": period, "scenario": scenario, "horizon": horizon,
             **_summarize(events), "events": events}
            for (period, scenario, horizon), events in studies.items()
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", required=True, help="First in-sample signal date")
    parser.add_argument("--holdout-start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--fee-bps", type=float, default=2)
    parser.add_argument("--slippage-bps", type=float, default=5)
    args = parser.parse_args()
    start, holdout, end = [pd.Timestamp(d) for d in (args.start, args.holdout_start, args.end)]
    if not start < holdout < end:
        parser.error("Expected start < holdout-start < end")
    frame = pd.read_csv(args.input, dtype={"code": str, "trade_status": str})
    periods = {
        "development": (
            start.date().isoformat(), (holdout - pd.Timedelta(days=1)).date().isoformat()
        ),
        "holdout": (holdout.date().isoformat(), end.date().isoformat()),
    }
    results = evaluate(frame, periods, args.fee_bps, args.slippage_bps)
    results["input_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    results["symbols"] = sorted(frame.code.unique())
    atomic_json(args.output, results, register=False)
    print(args.output)


if __name__ == "__main__":
    main()
