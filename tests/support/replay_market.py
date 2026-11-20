"""Synthetic daily market fixture. No external quotes or credentials."""

from datetime import datetime
from pathlib import Path
from time import monotonic, sleep

import pandas as pd

from quantflow.control import check_cancelled
from quantflow.data.base import StockCode
from quantflow.data.quality import daily_sessions


AS_OF = "2025-06-04T21:00:00+00:00"
SIGNAL_DATE = "2025-06-04"
PULLBACK = dict(
    zip(
        ("2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06", "2025-06-09"),
        (0.5, 1.4, 2.5, 3.7, 4.1, 4.2),
    )
)


def bars(code: StockCode) -> pd.DataFrame:
    """A steady uptrend with a six-session drawdown only for AAPL.US."""
    dates = daily_sessions(code, "2024-08-01", "2025-07-08")
    discount = PULLBACK if code.standard == "AAPL.US" else {}
    close = [100.0 + i * 0.2 - discount.get(d.strftime("%Y-%m-%d"), 0) for i, d in enumerate(dates)]
    return pd.DataFrame(
        {
            "date": dates,
            "code": code.standard,
            "close": close,
            "open": [v - 0.1 for v in close],
            "low": [v - 0.3 for v in close],
            "high": [v + 0.3 for v in close],
            "volume": 10_000,
        }
    )


class ReplayClock(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = datetime.fromisoformat(AS_OF)
        return instant.replace(tzinfo=None) if tz is None else instant.astimezone(tz)


class ReplayAdapter:
    def __init__(self, source: str, gate: Path | None = None):
        self.source = source
        self.gate = gate

    def get_name(self):
        return self.source

    def supports_market(self, market):
        return True

    def get_supported_periods(self):
        return ["d"]

    def get_supported_adjusts(self):
        return ["none", "qfq", "hfq"]

    def fetch_ohlcv(self, code, start, end, period, adjust):
        if self.gate:
            with (self.gate.parent / "provider-requests.log").open("a", encoding="utf-8") as calls:
                calls.write(f"{code.standard}\n")
            if (
                code.standard == "BROKEN.US"
                and not self.gate.with_name("provider-available").exists()
            ):
                raise TimeoutError("simulated provider connection timeout")
        if self.gate and self.gate.is_file() and self.gate.read_text().strip() == code.standard:
            self.gate.with_suffix(".entered").touch()
            deadline = monotonic() + 20
            while self.gate.exists():
                check_cancelled()
                if monotonic() >= deadline:
                    raise TimeoutError("Test did not release the market fixture")
                sleep(0.02)
        if code.standard == "EMPTY.US" and not (
            self.gate and self.gate.with_name("provider-available").exists()
        ):
            return pd.DataFrame()
        frame = bars(code)
        return frame.loc[frame.date.between(pd.Timestamp(start), pd.Timestamp(end))]

    def fetch_batch_ohlcv(self, codes, start, end, period, adjust, progress_cb=None):
        results, self.batch_errors = {}, {}
        for i, code in enumerate(codes, 1):
            try:
                results[code.standard] = self.fetch_ohlcv(code, start, end, period, adjust)
            except TimeoutError as exc:
                self.batch_errors[code.standard] = str(exc)
            if progress_cb:
                progress_cb(i, len(codes), code)
        return results

    def fetch_fundamental(self, *args, **kwargs):
        return None


def install_replay(project: Path, patch=setattr):
    """Set the provider and market clock in a standalone test server process."""
    from quantflow.data.factory import DataSourceFactory
    from quantflow.execution import executor, scanner
    from quantflow.orchestration import app

    patch(
        DataSourceFactory,
        "_get_adapter",
        lambda self, source: ReplayAdapter(source, project / "provider-gate"),
    )
    for module in (executor, scanner, app):
        patch(module, "datetime", ReplayClock)
