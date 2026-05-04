import pytest
import pandas as pd
import numpy as np

from quantflow.indicators.standard import KDJIndicator, MACDIndicator
from quantflow.indicators.composer import IndicatorComposer


@pytest.fixture
def sample_df():
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    np.random.seed(42)
    close = 100 + np.random.randn(50).cumsum()
    high = close + np.random.rand(50) * 2
    low = close - np.random.rand(50) * 2
    volume = np.random.randint(1000, 10000, 50)

    return pd.DataFrame({
        "date": dates,
        "open": close - np.random.rand(50) * 1,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestIndicatorComposerAddRemove:

    def test_add_indicator(self, sample_df):
        kdj = KDJIndicator()
        macd = MACDIndicator()
        composer = IndicatorComposer([kdj])

        composer.add_indicator(macd)
        result = composer.compose(sample_df)

        assert "K" in result.columns
        assert "DIF" in result.columns

    def test_remove_indicator(self, sample_df):
        kdj = KDJIndicator()
        macd = MACDIndicator()
        composer = IndicatorComposer([kdj, macd])

        composer.remove_indicator("KDJ")
        result = composer.compose(sample_df)

        # KDJ outputs should be removed
        assert "K" not in result.columns
        # MACD outputs remain
        assert "DIF" in result.columns

    def test_get_indicator_names(self, sample_df):
        kdj = KDJIndicator()
        macd = MACDIndicator()
        composer = IndicatorComposer([kdj, macd])

        names = composer.get_indicator_names()
        assert names == ["KDJ", "MACD"]

    def test_compose_preserves_input_data(self, sample_df):
        kdj = KDJIndicator()
        composer = IndicatorComposer([kdj])
        result = composer.compose(sample_df)

        for col in ["date", "open", "high", "low", "close", "volume"]:
            assert col in result.columns

    def test_compose_order_independent(self, sample_df):
        kdj = KDJIndicator()
        macd = MACDIndicator()
        comp1 = IndicatorComposer([kdj, macd])
        comp2 = IndicatorComposer([macd, kdj])

        df1 = comp1.compose(sample_df)
        df2 = comp2.compose(sample_df)

        # Different order, same set of columns added
        assert set(df1.columns) == set(df2.columns)
