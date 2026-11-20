import exchange_calendars as xcals
import pytest

from quantflow.data import StockCode
from quantflow.data.trading_calendar import completed_session, session_schedule


@pytest.fixture
def unsupported_next_year(monkeypatch):
    original = xcals.get_calendar

    def get_calendar(name, *, start, end):
        if name == "XSHG" and start >= "2027-01-01":
            raise ValueError("The XSHG holidays are only recorded to the year 2026")
        return original(name, start=start, end=end)

    session_schedule.cache_clear()
    monkeypatch.setattr(xcals, "get_calendar", get_calendar)
    yield
    session_schedule.cache_clear()


@pytest.mark.parametrize(
    ("code", "cutoff", "expected"),
    [
        ("600519.SH", "2027-01-01T07:10:00Z", "2026-12-31"),
        ("000001.SZ", "2027-01-04T06:59:00Z", "2026-12-31"),
        ("600519.SH", "2027-01-04T07:00:00Z", "2027-01-04"),
        ("000001.SZ", "2027-02-14T09:00:00Z", "2027-02-04"),
        ("600519.SH", "2027-02-15T07:05:00Z", "2027-02-15"),
        ("000001.SZ", "2027-10-09T07:05:00Z", "2027-10-08"),
    ],
)
def test_provisional_schedule_respects_holidays_and_close(
    unsupported_next_year, code, cutoff, expected
):
    session = completed_session(StockCode.from_standard(code), now=cutoff)
    assert session.date == expected
    assert "provisional" in session.calendar_warning


def test_provisional_schedule_surfaces_expiry_and_does_not_guess_future_years(
    unsupported_next_year,
):
    code = StockCode.from_standard("000001.SZ")
    session = completed_session(code, now="2026-11-20T08:00:00Z")
    assert session.date == "2026-11-20"
    assert "2027 is provisional" in session.calendar_warning
    with pytest.raises(ValueError, match="calendar unavailable for 2028"):
        completed_session(code, now="2028-01-03T08:00:00Z")


def test_upstream_coverage_takes_precedence_over_fallback(monkeypatch):
    from types import SimpleNamespace

    import pandas as pd

    dates = pd.DatetimeIndex(["2027-01-04"])
    schedule = pd.DataFrame({"close": pd.to_datetime(["2027-01-04T07:00:00Z"])}, index=dates)
    session_schedule.cache_clear()
    monkeypatch.setattr(
        xcals, "get_calendar", lambda *args, **kwargs: SimpleNamespace(schedule=schedule)
    )
    try:
        result = completed_session(StockCode("600519", "SH"), now="2027-01-04T08:00:00Z")
        assert result.date == "2027-01-04"
        assert result.calendar_warning is None
    finally:
        session_schedule.cache_clear()
