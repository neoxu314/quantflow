"""Tests for indicator layer."""

import pytest
import pandas as pd
import numpy as np

from quantflow.indicators.base import IndicatorBase, Condition
from quantflow.indicators.standard import KDJIndicator, MACDIndicator, RSIIndicator, BOLLIndicator, VolumeMAIndicator
from quantflow.indicators.custom import DualLineIndicator
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


class TestKDJIndicator:
    
    def test_name_and_params(self):
        kdj = KDJIndicator(n=9)
        assert kdj.name == "KDJ"
        assert kdj.params["n"] == 9
        assert kdj.params["m1"] == 3
        assert kdj.params["m2"] == 3
    
    def test_custom_m1_m2(self):
        kdj = KDJIndicator(n=14, m1=5, m2=4)
        assert kdj.params == {"n": 14, "m1": 5, "m2": 4}
        result = kdj.calculate(
            pd.DataFrame({
                "high": [10] * 20,
                "low": [5] * 20,
                "close": list(range(10, 30)),
            })
        )
        assert "K" in result.columns
        assert result["K"].iloc[-1] != result["D"].iloc[-1]
    
    def test_required_fields(self):
        kdj = KDJIndicator()
        assert kdj.get_required_fields() == ["high", "low", "close"]
    
    def test_output_fields(self):
        kdj = KDJIndicator()
        assert "K" in kdj.get_output_fields()
        assert "D" in kdj.get_output_fields()
        assert "J" in kdj.get_output_fields()
    
    def test_calculate(self, sample_df):
        kdj = KDJIndicator(n=9)
        result = kdj.calculate(sample_df)
        
        assert "K" in result.columns
        assert "D" in result.columns
        assert "J" in result.columns
        assert len(result) == len(sample_df)


class TestMACDIndicator:
    
    def test_calculate(self, sample_df):
        macd = MACDIndicator()
        result = macd.calculate(sample_df)
        
        assert "MACD" in result.columns
        assert "MACD_SIGNAL" in result.columns
        assert "MACD_HIST" in result.columns


class TestRSIIndicator:
    
    def test_calculate(self, sample_df):
        rsi = RSIIndicator(period=14)
        result = rsi.calculate(sample_df)
        
        assert "RSI" in result.columns
        assert result["RSI"].min() >= 0
        assert result["RSI"].max() <= 100


class TestDualLineIndicator:
    
    def test_calculate(self, sample_df):
        dual = DualLineIndicator(ema_period=10, ma_periods=[14, 28])
        result = dual.calculate(sample_df)
        
        assert "short_trend_line" in result.columns
        assert "long_short_line" in result.columns
        assert "is_bull_zone" in result.columns
        assert "is_bear_zone" in result.columns


class TestIndicatorComposer:
    
    def test_compose_single(self, sample_df):
        kdj = KDJIndicator()
        composer = IndicatorComposer([kdj])
        
        result = composer.compose(sample_df)
        
        assert "K" in result.columns
        assert "D" in result.columns
    
    def test_compose_multiple(self, sample_df):
        kdj = KDJIndicator()
        macd = MACDIndicator()
        composer = IndicatorComposer([kdj, macd])
        
        result = composer.compose(sample_df)
        
        assert "K" in result.columns
        assert "MACD" in result.columns
    
    def test_dependency_validation(self):
        kdj = KDJIndicator()
        composer = IndicatorComposer([kdj])
        
        df_without_required = pd.DataFrame({"close": [1, 2, 3]})
        
        with pytest.raises(ValueError, match="requires fields"):
            composer.compose(df_without_required)


class TestBOLLIndicator:
    
    def test_calculate(self, sample_df):
        boll = BOLLIndicator(period=20, std_dev=2.0)
        result = boll.calculate(sample_df)
        
        assert "BOLL_MID" in result.columns
        assert "BOLL_UPPER" in result.columns
        assert "BOLL_LOWER" in result.columns
        
        valid = result.dropna(subset=["BOLL_UPPER"])
        assert (valid["BOLL_UPPER"] >= valid["BOLL_MID"]).all()
        assert (valid["BOLL_LOWER"] <= valid["BOLL_MID"]).all()


class TestVolumeMAIndicator:
    
    def test_calculate(self, sample_df):
        vol_ma = VolumeMAIndicator(periods=[5, 10])
        result = vol_ma.calculate(sample_df)
        
        assert "VOL_MA5" in result.columns
        assert "VOL_MA10" in result.columns
    
    def test_mutable_default_independent(self):
        v1 = VolumeMAIndicator()
        v2 = VolumeMAIndicator()
        v1.periods.append(60)
        assert 60 not in v2.periods