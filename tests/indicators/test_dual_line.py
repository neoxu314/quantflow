"""Dual Line Indicator tests."""

import json
import pytest
import pandas as pd
from pathlib import Path

from quantflow.indicators.custom import DualLineIndicator


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "msft_close_prices.json"


@pytest.fixture(scope="module")
def msft_data():
    """Load MSFT close price fixtures, or fetch from network and save."""
    if FIXTURE_PATH.exists():
        with open(FIXTURE_PATH, "r") as f:
            data = json.load(f)
        if data.get("daily", {}).get("close_prices"):
            return data

    import yfinance as yf
    import warnings
    warnings.filterwarnings("ignore")

    data = {"metadata": {"stock_code": "MSFT", "market": "US", "indicator": "DualLine"}}

    daily_raw = yf.download("MSFT", start="2020-01-01", end="2026-04-16")
    data["daily"] = {
        "end_date": "2026-04-15",
        "expected_short_trend": 377.515,
        "expected_long_short": 400.081,
        "close_prices": daily_raw[("Close", "MSFT")].tolist(),
    }

    weekly_raw = yf.download("MSFT", start="2020-01-01", end="2026-04-30", interval="1wk")
    data["weekly"] = {
        "end_date": "2025-05-02",
        "expected_short_trend": 395.479,
        "expected_long_short": 396.800,
        "close_prices": weekly_raw[("Close", "MSFT")].tolist(),
    }

    monthly_raw = yf.download("MSFT", start="2015-01-01", end="2026-04-30", interval="1mo")
    data["monthly"] = {
        "end_date": "2022-10-31",
        "expected_short_trend": 264.050,
        "expected_long_short": 201.731,
        "close_prices": monthly_raw[("Close", "MSFT")].tolist(),
    }

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXTURE_PATH, "w") as f:
        json.dump(data, f, indent=2)

    return data


def run_dual_line(close_list):
    df = pd.DataFrame({"close": close_list})
    indicator = DualLineIndicator()
    return indicator.calculate(df)


class TestDualLineIndicator:

    def _assert_values(self, actual_short, actual_long, expected_short, expected_long):
        assert actual_short == pytest.approx(expected_short, abs=0.5), \
            f"Short trend: {actual_short:.3f} != {expected_short:.3f}"
        assert actual_long == pytest.approx(expected_long, abs=0.5), \
            f"Long/Short line: {actual_long:.3f} != {expected_long:.3f}"

    def test_daily(self, msft_data):
        data = msft_data["daily"]
        closes = data["close_prices"]
        if not closes:
            pytest.skip("No close prices for daily test")

        result_df = run_dual_line(closes)
        self._assert_values(
            result_df["short_trend_line"].iloc[-1],
            result_df["long_short_line"].iloc[-1],
            data["expected_short_trend"],
            data["expected_long_short"],
        )

    def test_weekly(self, msft_data):
        data = msft_data["weekly"]
        closes = data["close_prices"]
        if not closes:
            pytest.skip("No close prices for weekly test")

        result_df = run_dual_line(closes)
        self._assert_values(
            result_df["short_trend_line"].iloc[-1],
            result_df["long_short_line"].iloc[-1],
            data["expected_short_trend"],
            data["expected_long_short"],
        )

    def test_monthly(self, msft_data):
        data = msft_data["monthly"]
        closes = data["close_prices"]
        if not closes:
            pytest.skip("No close prices for monthly test")
        
        if len(closes) < 114:
            pytest.skip("Insufficient monthly data for full DualLine convergence")

        result_df = run_dual_line(closes)
        self._assert_values(
            result_df["short_trend_line"].iloc[-1],
            result_df["long_short_line"].iloc[-1],
            data["expected_short_trend"],
            data["expected_long_short"],
        )

    def test_params_override(self):
        indicator = DualLineIndicator(ema_period=5, ma_periods=[10, 20])
        assert indicator.ema_period == 5
        assert indicator.ma_periods == [10, 20]
        assert "short_trend_line" in indicator.get_output_fields()
        assert "long_short_line" in indicator.get_output_fields()

    def test_insufficient_data_returns_nan(self):
        """Test strict mode: new stocks (<114 days) shouldn't output partial lines."""
        # Create only 50 days of data
        closes = [10.0] * 50
        df = pd.DataFrame({"close": closes + [15.0, 16.0, 17.0]}) # Total ~53 days

        indicator = DualLineIndicator() # default periods: [14, 28, 57, 114]
        result = indicator.calculate(df)

        assert pd.isna(result["long_short_line"].iloc[-1]), \
            "long_short_line should be NaN for data < 114 days"
        
        # Short trend line (EMA based) should still calculate
        assert not pd.isna(result["short_trend_line"].iloc[-1])
