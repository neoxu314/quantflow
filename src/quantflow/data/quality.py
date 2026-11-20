"""Daily OHLCV contract and exchange-local completed-session validation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quantflow.data.trading_calendar import CALENDARS, completed_session, session_schedule


def last_completed_session(code, end_date=None, now=None):
    return completed_session(code, end_date, now).date


def normalize_ohlcv(frame, start=None, end=None):
    if frame is None or frame.empty:
        return pd.DataFrame()
    df = frame.copy()
    if "date" not in df:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("OHLCV requires an actual date column or DatetimeIndex")
        df["date"] = df.index
    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.tz_localize(None).dt.normalize()
    if df["date"].isna().any():
        raise ValueError("Missing OHLCV session dates")
    if start:
        df = df.loc[df.date >= pd.Timestamp(start)]
    if end:
        df = df.loc[df.date <= pd.Timestamp(end)]
    if df.empty:
        return pd.DataFrame()
    if df["date"].duplicated().any():
        raise ValueError("Duplicate OHLCV session dates")
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
    df = df.sort_values("date")
    df.attrs.update(frame.attrs)
    return df.reset_index(drop=True)


@dataclass(frozen=True)
class DailyBarQuality:
    status: str
    missing_sessions: tuple[str, ...] = ()
    unexpected_dates: tuple[str, ...] = ()


def inspect_daily_bars(frame, code, expected):
    """Check normalized bars over their observed input window."""
    if frame.empty:
        return DailyBarQuality("no_data")
    dates = pd.DatetimeIndex(frame.date)
    last = dates[-1]
    if last != pd.Timestamp(expected):
        return DailyBarQuality("stale")
    if frame.volume.iloc[-1] <= 0:
        return DailyBarQuality("suspended")

    # Leading absence may be a new listing. Only gaps after the first observed
    # bar are measurable here. The indicator independently checks its lookback.
    first = dates[0]
    calendar = CALENDARS[code.exchange]
    sessions = pd.DatetimeIndex([])
    for year in range(first.year, last.year + 1):
        year_dates = session_schedule(calendar, year).index
        sessions = sessions.union(year_dates[(year_dates >= first) & (year_dates <= last)])
    missing = tuple(sessions.difference(dates).strftime("%Y-%m-%d"))
    unexpected = tuple(dates.difference(sessions).strftime("%Y-%m-%d"))
    return DailyBarQuality("data_gap" if missing or unexpected else "ok", missing, unexpected)


def prepare_daily_frame(frame, code, end_date, now=None):
    expected = last_completed_session(code, end_date, now)
    df = normalize_ohlcv(frame, end=expected)
    return df, expected, inspect_daily_bars(df, code, expected).status
