"""Brick Chart Indicator tests."""

import pytest
import pandas as pd

from quantflow.indicators.custom import BrickChartIndicator


class TestBrickChartIndicator:

    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            'high': [10, 11, 12, 13, 12, 11, 10, 11, 12, 13, 14, 15, 12, 10, 10, 11, 12],
            'low': [9, 9, 10, 11, 10, 9, 8, 9, 10, 11, 12, 13, 10, 8, 8, 9, 10],
            'close': [9.5, 10.5, 11.5, 12.5, 11.0, 10.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 11.0, 9.0, 9.0, 10.0, 11.0],
            'volume': [1000, 1200, 1100, 1300, 900, 800, 700, 1100, 1200, 1500, 1600, 1400, 900, 800, 800, 1100, 1300]
        })

    def test_name_and_params(self):
        ind = BrickChartIndicator()
        assert ind.name == "BrickChart"
        assert ind.params["period"] == 4
        assert ind.params["smooth1_n"] == 4
        assert ind.params["smooth2_n"] == 6
        assert ind.params["shift"] == 4.0

    def test_required_fields(self):
        ind = BrickChartIndicator()
        assert ind.get_required_fields() == ["high", "low", "close", "volume"]

    def test_output_fields(self):
        ind = BrickChartIndicator()
        assert ind.get_output_fields() == ["brick_chart"]

    def test_calculate(self, sample_df):
        ind = BrickChartIndicator()
        result = ind.calculate(sample_df)
        assert "brick_chart" in result.columns
        assert len(result) == len(sample_df)

    def test_buy_signals(self, sample_df):
        ind = BrickChartIndicator()
        result = ind.calculate(sample_df)
        result = ind.get_buy_signals(result)
        assert "block_height" in result.columns
        assert "buy_signal" in result.columns

    def test_custom_params(self):
        ind = BrickChartIndicator(period=5, smooth1_n=5, smooth2_n=8, shift=5.0)
        assert ind.period == 5
        assert ind.smooth1_n == 5
        assert ind.smooth2_n == 8
        assert ind.shift == 5.0
