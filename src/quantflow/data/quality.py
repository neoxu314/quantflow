"""Daily OHLCV contract and exchange-local completed-session validation."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

CALENDARS = {
    "SH": "XSHG",
    "SZ": "XSHG",
    "HK": "XHKG",
    "US": "XNYS",
    "T": "XTKS",
    "JP": "XTKS",
    "KS": "XKRX",
    "KR": "XKRX",
}


@lru_cache(maxsize=32)
def _calendar(name, year):
    import exchange_calendars as xcals

    return xcals.get_calendar(name, start=f"{year - 2}-01-01", end=f"{year}-12-31")


def last_completed_session(code, end_date=None, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    name = CALENDARS.get(code.exchange)
    if name is None:
        raise ValueError(f"No trading calendar for {code.exchange}")
    year = pd.Timestamp(end_date or now).year
    cal = _calendar(name, year)
    schedule = cal.schedule
    # Date labels represent exchange-local sessions; market close is UTC.
    sessions = schedule.index
    limit = pd.Timestamp(end_date or now.tz_convert(cal.tz).date()).tz_localize(None)
    labels = sessions.tz_localize(None)
    closes = pd.to_datetime(schedule["close"], utc=True)
    eligible = schedule.loc[(labels <= limit) & (closes <= now)]
    if eligible.empty:
        raise ValueError("No completed session in calendar range")
    return eligible.index[-1].strftime("%Y-%m-%d")


def normalize_ohlcv(frame, start=None, end=None):
    if frame is None or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    if "date" not in df:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("OHLCV requires an actual date column or DatetimeIndex")
        df["date"] = df.index
    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.tz_localize(None).dt.normalize()
    if df["date"].isna().any() or df["date"].duplicated().any():
        raise ValueError("Missing or duplicate OHLCV session dates")
    columns = ["open", "high", "low", "close", "volume"]
    if set(columns) - set(df.columns):
        raise ValueError("OHLCV columns are incomplete")
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors="raise")
    if not np.isfinite(df[columns].to_numpy(dtype=float)).all():
        raise ValueError("Non-finite OHLCV values")
    if (df[["open", "high", "low", "close"]] <= 0).any().any() or (df.volume < 0).any():
        raise ValueError("Non-positive prices or negative volume")
    if (
        (df.high < df[["open", "close", "low"]].max(axis=1))
        | (df.low > df[["open", "close", "high"]].min(axis=1))
    ).any():
        raise ValueError("Inconsistent OHLC price range")
    df = df.sort_values("date").reset_index(drop=True)
    if start:
        df = df[df.date >= pd.Timestamp(start)]
    if end:
        df = df[df.date <= pd.Timestamp(end)]
    df.attrs.update(frame.attrs)
    return df.reset_index(drop=True)


def prepare_daily_frame(frame, code, end_date, now=None):
    df = normalize_ohlcv(frame)
    expected = last_completed_session(code, end_date, now)
    df = df[df.date <= pd.Timestamp(expected)].reset_index(drop=True)
    if df.empty:
        return df, expected, "no_data"
    actual = df.date.iloc[-1].strftime("%Y-%m-%d")
    if actual != expected:
        return df, expected, "stale"
    if df.volume.iloc[-1] <= 0:
        return df, expected, "suspended"
    return df, expected, "ok"
