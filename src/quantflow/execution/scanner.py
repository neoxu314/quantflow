"""Shared CLI/Web single-stock scan; output boundaries never silently expand."""

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantflow.artifacts import atomic_json, safe_name
from quantflow.config.loader import ConfigLoader
from quantflow.config.lookback import load_lookback_config
from quantflow.control import check_cancelled
from quantflow.data import StockCode
from quantflow.data.quality import prepare_daily_frame
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.factory import IndicatorFactory

INDICATOR_NAMES = {
    "kdj": "KDJ",
    "macd": "MACD",
    "rsi": "RSI",
    "boll": "BOLL",
    "vol_ma": "VolumeMA",
    "dual_line": "DualLine",
    "brick_chart": "BrickChart",
    "washout": "Washout",
}


def build_indicators(names):
    return [IndicatorFactory.create(INDICATOR_NAMES.get(n, n)) for n in names]


@IndicatorFactory.snapshot()
def scan_stock(cfg, output, now=None):
    check_cancelled()
    now = now or datetime.now(timezone.utc).isoformat()
    config = ConfigLoader()
    code = StockCode.from_standard(cfg["code"])
    end = cfg.get("end_date") or now[:10]
    start = (
        cfg.get("start_date")
        or (datetime.fromisoformat(end) - timedelta(days=365)).date().isoformat()
    )
    if start > end:
        raise ValueError("start_date after end_date")
    names = cfg.get("indicators") or ["kdj", "dual_line"]
    indicators = build_indicators(names)
    lookback = load_lookback_config()
    warmup = (
        math.ceil(max(i.lookback_bars for i in indicators) * lookback["calendar_multiplier"])
        + lookback["buffer_days"]
    )
    fetch_start = (datetime.fromisoformat(start) - timedelta(days=warmup)).date().isoformat()
    factory = config.create_data_factory()
    adjust = config.get_adjust()
    raw, source = factory.fetch_ohlcv(code, fetch_start, end, adjust=adjust)
    check_cancelled()
    if raw.empty:
        raise ValueError(f"No data for {code.standard}")
    safe = safe_name(code.standard)
    out = Path(output)
    atomic_json(
        out / f"{safe}_snapshot.json",
        {
            "code": code.standard,
            "source": source,
            "adjust": adjust,
            "volume_unit": "shares",
            "as_of": now,
            "rows": raw.to_dict("records"),
        },
    )
    df, expected, quality = prepare_daily_frame(raw, code, end, now)
    if quality != "ok":
        raise ValueError(f"Unusable data: {quality}; expected {expected}")
    df = IndicatorComposer(indicators).compose(df)
    if df[[f for i in indicators for f in i.get_output_fields()]].iloc[-1].isna().any():
        raise ValueError("Insufficient indicator history")
    rows = df[(df.date >= start) & (df.date <= end)]
    if rows.empty:
        raise ValueError("No completed trading sessions in the requested output interval")
    path = out / f"{safe}_indicators.json"
    atomic_json(path, rows.to_dict("records"))
    metadata = {
        "schema_version": 1,
        "code": code.standard,
        "source": source,
        "adjust": adjust,
        "period": "d",
        "volume_unit": "shares",
        "as_of": now,
        "bar_date": df.date.iloc[-1].strftime("%Y-%m-%d"),
        "expected_session": expected,
        "start_date": start,
        "end_date": end,
        "indicator_params": {i.name: i.params for i in indicators},
        "bars": len(rows),
    }
    atomic_json(out / f"{safe}_context.json", metadata)
    check_cancelled()
    return str(path), len(rows), metadata
