"""Dual Line Indicator tests."""

import json
import pytest
import pandas as pd
from pathlib import Path

from quantflow.indicators.custom import DualLineIndicator


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "msft_close_prices.json"


@pytest.fixture(scope="module")
def msft_data():
    """Read the committed daily and weekly reference prices."""
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


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
        assert len(closes) >= 114

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
        assert len(closes) >= 114

        result_df = run_dual_line(closes)
        self._assert_values(
            result_df["short_trend_line"].iloc[-1],
            result_df["long_short_line"].iloc[-1],
            data["expected_short_trend"],
            data["expected_long_short"],
        )

    def test_monthly_requires_114_bars_and_uses_all_four_moving_averages(self):
        dates = pd.date_range("2010-01-01", periods=114, freq="MS")
        prices = pd.DataFrame({"close": [100.0] * 113 + [111.0]}, index=dates)
        lines = DualLineIndicator().calculate(prices)
        assert lines["long_short_line"].iloc[:-1].isna().all()
        # A single 11-point price step passes through two EMA layers, both with alpha=2/11.
        assert lines["short_trend_line"].iloc[-1] == pytest.approx(100 + 11 * (2 / 11) ** 2)
        expected_support = 100 + sum(11 / width for width in (14, 28, 57, 114)) / 4
        assert lines["long_short_line"].iloc[-1] == pytest.approx(expected_support)

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
