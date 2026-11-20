"""Exchange session schedules, including explicit provisional China coverage."""

from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

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
CALENDAR_TIME_ZONES = {
    "XSHG": "Asia/Shanghai",
    "XHKG": "Asia/Hong_Kong",
    "XNYS": "America/New_York",
    "XTKS": "Asia/Tokyo",
    "XKRX": "Asia/Seoul",
}

# State Council holiday announcement, 2026-11-05 (国办发明电〔2026〕10号).
# SSE/SZSE trade Mon–Fri. Compensatory working weekends remain non-trading.
# https://www.gov.cn/zhengce/content/202611/content_7085101.htm
_CN_CLOSURES_2027 = (
    ("2027-01-01", "2027-01-03"),
    ("2027-02-05", "2027-02-13"),
    ("2027-04-03", "2027-04-05"),
    ("2027-05-01", "2027-05-05"),
    ("2027-06-09", "2027-06-09"),
    ("2027-09-15", "2027-09-15"),
    ("2027-10-01", "2027-10-07"),
)


@dataclass(frozen=True)
class CompletedSession:
    date: str
    calendar_warning: str | None = None


@lru_cache(maxsize=64)
def session_schedule(name, year):
    """Return session labels and UTC close times for a single calendar year."""
    import exchange_calendars as xcals

    start, end = f"{year}-01-01", f"{year}-12-31"
    try:
        schedule = xcals.get_calendar(name, start=start, end=end).schedule[["close"]].copy()
    except ValueError as exc:
        if name != "XSHG" or year != 2027 or "holidays are only recorded" not in str(exc):
            raise ValueError(f"{name} calendar unavailable for {year}: {exc}") from exc
        sessions = pd.date_range(start, end, freq="B")
        for first, last in _CN_CLOSURES_2027:
            sessions = sessions[(sessions < pd.Timestamp(first)) | (sessions > pd.Timestamp(last))]
        closes = (sessions + pd.Timedelta(hours=15)).tz_localize("Asia/Shanghai").tz_convert("UTC")
        schedule = pd.DataFrame({"close": closes}, index=sessions)
        schedule.attrs["provisional"] = True
    schedule.index = schedule.index.tz_localize(None)
    return schedule


def completed_session(code, end_date=None, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    calendar = CALENDARS.get(code.exchange)
    if calendar is None:
        raise ValueError(f"No trading calendar for {code.exchange}")
    local_date = now.tz_convert(ZoneInfo(CALENDAR_TIME_ZONES[calendar])).date()
    limit = min(local_date, pd.Timestamp(end_date).date()) if end_date else local_date
    schedule = session_schedule(calendar, limit.year)
    warning = None
    if schedule.attrs.get("provisional"):
        warning = (
            "XSHG 2027 calendar is provisional based on published public holidays. "
            "Confirm SSE/SZSE holiday notices before relying on those dates."
        )
    elif calendar == "XSHG" and limit == local_date and limit.month >= 11:
        try:
            next_schedule = session_schedule(calendar, limit.year + 1)
        except ValueError:
            warning = f"XSHG calendar coverage for {limit.year + 1} is unavailable."
        else:
            if next_schedule.attrs.get("provisional"):
                warning = f"XSHG calendar coverage for {limit.year + 1} is provisional."

    def eligible_dates(schedule):
        return schedule.index[
            (schedule.index <= pd.Timestamp(limit))
            & (pd.to_datetime(schedule.close, utc=True) <= now)
        ]

    eligible = eligible_dates(schedule)
    if eligible.empty:
        eligible = eligible_dates(session_schedule(calendar, limit.year - 1))
    if eligible.empty:
        raise ValueError("No completed session in calendar range")
    return CompletedSession(eligible[-1].strftime("%Y-%m-%d"), warning)
