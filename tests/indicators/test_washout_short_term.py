# Washout Indicator tests.

import pytest
import pandas as pd

from quantflow.indicators.custom import WashoutIndicator


class TestWashoutIndicator:

    @pytest.fixture
    def sample_df(self):
        return pd.DataFrame({
            'high': [10, 11, 12, 13, 12, 11, 10, 11, 12, 13, 14, 15, 12, 10, 10, 11, 12, 13],
            'low': [9, 9, 10, 11, 10, 9, 8, 9, 10, 11, 12, 13, 10, 8, 8, 9, 10, 11],
            'close': [9.5, 10.5, 11.5, 12.5, 11.0, 10.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 11.0, 9.0, 9.0, 10.0, 11.0, 12.0],
            'volume': [1000, 1200, 1100, 1300, 900, 800, 700, 1100, 1200, 1500, 1600, 1400, 900, 800, 800, 1100, 1300, 1500]
        })

    def test_name_and_params(self):
        ind = WashoutIndicator()
        assert ind.name == "Washout"
        assert ind.params["n1"] == 3
        assert ind.params["n2"] == 21

    def test_required_fields(self):
        ind = WashoutIndicator()
        assert ind.get_required_fields() == ["high", "low", "close", "volume"]

    def test_output_fields(self):
        ind = WashoutIndicator()
        assert set(ind.get_output_fields()) == {"short", "mid", "mid_long", "long", "washout_signal"}

    def test_calculate(self, sample_df):
        ind = WashoutIndicator()
        result = ind.calculate(sample_df)
        assert "short" in result.columns
        assert "washout_signal" in result.columns

    def test_custom_params(self):
        ind = WashoutIndicator(n1=5, n2=30)
        assert ind.n1 == 5
        assert ind.n2 == 30
