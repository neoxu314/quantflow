"""Shared CLI/Web single-stock scan; output boundaries never silently expand."""

import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from quantflow.artifacts import atomic_json, safe_name
from quantflow.config.loader import ConfigLoader
from quantflow.config.lookback import load_lookback_config
from quantflow.control import check_cancelled
from quantflow.data import StockCode
from quantflow.data.quality import inspect_daily_bars, normalize_ohlcv, tradable_bars
from quantflow.data.trading_calendar import completed_session
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.factory import IndicatorFactory

logger = logging.getLogger(__name__)

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
    calendar = completed_session(code, cfg.get("end_date"), now)
    session = calendar.date
    if calendar.calendar_warning:
        logger.warning("%s", calendar.calendar_warning)
    end = cfg.get("end_date") or session
    start = (
        cfg.get("start_date")
        or (datetime.fromisoformat(end) - timedelta(days=365)).date().isoformat()
    )
    if start > end:
        raise ValueError("start_date after end_date")
    if start > session:
        raise ValueError("No completed trading sessions in the requested output interval")
    names = cfg.get("indicators") or ["kdj", "dual_line"]
    indicators = build_indicators(names)
    min_history_bars = max(i.lookback_bars for i in indicators)
    lookback = load_lookback_config()
    warmup = (
        math.ceil(min_history_bars * lookback["calendar_multiplier"])
        + lookback["buffer_days"]
    )
    fetch_start = (datetime.fromisoformat(start) - timedelta(days=warmup)).date().isoformat()
    factory = config.create_data_factory()
    adjust = config.get_adjust()
    raw, source = factory.fetch_ohlcv(
        code, fetch_start, session, adjust=adjust, require_end_session=True,
        min_history_bars=min_history_bars,
    )
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
            "query_start": fetch_start,
            "expected_session": session,
            "calendar_warning": calendar.calendar_warning,
            "trading_status_source": raw.attrs.get("trading_status_source"),
            "listing_date": raw.attrs.get("listing_date"),
            "listing_date_source": raw.attrs.get("listing_date_source"),
            "price_adjustment_basis": raw.attrs.get("price_adjustment_basis"),
            "rows": raw.to_dict("records"),
        },
    )
    df = normalize_ohlcv(raw, fetch_start, session)
    quality = inspect_daily_bars(df, code, session)
    if quality.status != "ok":
        message = f"Unusable data: {quality.status}; expected {session}"
        if quality.missing_sessions:
            message += f"; missing sessions: {', '.join(quality.missing_sessions)}"
        if quality.unexpected_dates:
            message += f"; non-trading bars: {', '.join(quality.unexpected_dates)}"
        raise ValueError(message)
    df = tradable_bars(df)
    if len(df) < min_history_bars:
        raise ValueError(f"Insufficient indicator history: {len(df)}/{min_history_bars} bars")
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
        "price_adjustment_basis": raw.attrs.get("price_adjustment_basis"),
        "bar_date": df.date.iloc[-1].strftime("%Y-%m-%d"),
        "expected_session": session,
        "calendar_warning": calendar.calendar_warning,
        "start_date": start,
        "end_date": end,
        "indicator_params": {i.name: i.params for i in indicators},
        "bars": len(rows),
    }
    atomic_json(out / f"{safe}_context.json", metadata)
    check_cancelled()
    return str(path), len(rows), metadata
