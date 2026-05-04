import pandas as pd
import pytest

from quantflow.indicators.standard.kdj import KDJIndicator
from quantflow.indicators.standard.macd import MACDIndicator
from quantflow.indicators.standard.rsi import RSIIndicator
from quantflow.indicators.standard.boll import BOLLIndicator
from quantflow.indicators.standard.vol_ma import VolumeMAIndicator


@pytest.fixture
def sample_df():
    dates = pd.date_range("2026-01-01", periods=50, freq="D")
    close = [100.0 + i for i in range(50)]
    open_ = [c - 1 for c in close]
    high = [c + 1 for c in close]
    low = [c - 2 for c in close]
    volume = [1000 + i for i in range(50)]
    return pd.DataFrame({
        "date": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestKDJIndicator:
    def test_name_and_params(self):
        ind = KDJIndicator()
        assert ind.name == "KDJ"
        assert ind.params == {"n": 9, "m1": 3, "m2": 3}

    def test_lookback_bars(self):
        assert KDJIndicator().lookback_bars == 21

    def test_required_fields(self):
        assert KDJIndicator().get_required_fields() == ["high", "low", "close"]

    def test_output_fields(self):
        assert KDJIndicator().get_output_fields() == ["K", "D", "J"]

    def test_calculate_success(self, sample_df):
        df_out = KDJIndicator().calculate(sample_df)
        assert {"K", "D", "J"}.issubset(set(df_out.columns))
        assert df_out.shape[0] == sample_df.shape[0]

    def test_insufficient_data(self):
        df_short = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=2, freq="D"),
            "high": [2.0, 3.0], "low": [0.5, 1.5], "close": [1.5, 2.5],
            "open": [1.0, 2.0], "volume": [100, 100],
        })
        df_out = KDJIndicator().calculate(df_short)
        assert {"K", "D", "J"}.issubset(set(df_out.columns))

    def test_custom_params(self):
        ind = KDJIndicator(n=5, m1=2, m2=2)
        assert ind.name == "KDJ"
        assert ind.params == {"n": 5, "m1": 2, "m2": 2}


class TestMACDIndicator:
    def test_name_and_params(self):
        ind = MACDIndicator()
        assert ind.name == "MACD"
        assert ind.params == {"fast_period": 12, "slow_period": 26, "signal_period": 9}

    def test_lookback_bars(self):
        assert MACDIndicator().lookback_bars == 45

    def test_required_fields(self):
        assert MACDIndicator().get_required_fields() == ["close"]

    def test_output_fields(self):
        assert MACDIndicator().get_output_fields() == ["DIF", "DEA", "MACD"]

    def test_calculate_success(self, sample_df):
        df_out = MACDIndicator().calculate(sample_df)
        assert {"DIF", "DEA", "MACD"}.issubset(set(df_out.columns))
        assert df_out.shape[0] == sample_df.shape[0]

    def test_insufficient_data(self):
        df_short = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=1, freq="D"),
            "close": [100.5], "open": [100.0], "high": [101.0],
            "low": [99.0], "volume": [1000],
        })
        df_out = MACDIndicator().calculate(df_short)
        assert {"DIF", "DEA", "MACD"}.issubset(set(df_out.columns))

    def test_custom_params(self):
        ind = MACDIndicator(fast_period=5, slow_period=15, signal_period=6)
        assert ind.name == "MACD"
        assert ind.params == {"fast_period": 5, "slow_period": 15, "signal_period": 6}


class TestRSIIndicator:
    def test_name_and_params(self):
        ind = RSIIndicator()
        assert ind.name == "RSI"
        assert ind.params == {"periods": [14]}

    def test_name_and_params_multi(self):
        ind = RSIIndicator(periods=[6, 12, 24])
        assert ind.name == "RSI"
        assert ind.params == {"periods": [6, 12, 24]}

    def test_lookback_bars(self):
        assert RSIIndicator().lookback_bars == 24
        assert RSIIndicator(periods=[6, 12, 24]).lookback_bars == 34

    def test_required_fields(self):
        assert RSIIndicator().get_required_fields() == ["close"]

    def test_output_fields(self):
        assert RSIIndicator().get_output_fields() == ["RSI14"]
        assert RSIIndicator(periods=[6, 12, 24]).get_output_fields() == ["RSI6", "RSI12", "RSI24"]

    def test_calculate_success(self, sample_df):
        df_out = RSIIndicator().calculate(sample_df)
        assert "RSI14" in df_out.columns

    def test_calculate_multi_period(self, sample_df):
        df_out = RSIIndicator(periods=[6, 12, 24]).calculate(sample_df)
        for col in ("RSI6", "RSI12", "RSI24"):
            assert col in df_out.columns
            assert df_out[col].min() >= 0
            assert df_out[col].max() <= 100

    def test_insufficient_data(self):
        df_short = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=2, freq="D"),
            "close": [1.0, 1.6], "open": [1.0, 1.5], "high": [1.2, 1.7],
            "low": [0.8, 1.2], "volume": [100, 100],
        })
        df_out = RSIIndicator(periods=[6, 12, 24]).calculate(df_short)
        for col in ("RSI6", "RSI12", "RSI24"):
            assert col in df_out.columns

    def test_custom_params(self):
        ind = RSIIndicator(periods=[7])
        assert ind.name == "RSI"
        assert ind.params == {"periods": [7]}
        assert ind.get_output_fields() == ["RSI7"]


class TestBOLLIndicator:
    def test_name_and_params(self):
        ind = BOLLIndicator()
        assert ind.name == "BOLL"
        assert ind.params == {"period": 20, "std_dev": 2.0}

    def test_lookback_bars(self):
        assert BOLLIndicator().lookback_bars == 25

    def test_required_fields(self):
        assert BOLLIndicator().get_required_fields() == ["close"]

    def test_output_fields(self):
        assert BOLLIndicator().get_output_fields() == ["BOLL_MID", "BOLL_UPPER", "BOLL_LOWER"]

    def test_calculate_success(self, sample_df):
        df_out = BOLLIndicator().calculate(sample_df)
        for col in ("BOLL_MID", "BOLL_UPPER", "BOLL_LOWER"):
            assert col in df_out.columns

    def test_insufficient_data(self):
        df_short = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=1, freq="D"),
            "close": [1.5], "open": [1.0], "high": [2.0], "low": [0.5],
            "volume": [100],
        })
        df_out = BOLLIndicator().calculate(df_short)
        for col in ("BOLL_MID", "BOLL_UPPER", "BOLL_LOWER"):
            assert col in df_out.columns

    def test_custom_params(self):
        ind = BOLLIndicator(period=25, std_dev=1.5)
        assert ind.name == "BOLL"
        assert ind.params == {"period": 25, "std_dev": 1.5}


class TestVolumeMAIndicator:
    def test_name_and_params(self):
        ind = VolumeMAIndicator()
        assert ind.name == "VOL_MA"
        assert ind.params == {"periods": [5, 10, 20]}

    def test_lookback_bars(self):
        assert VolumeMAIndicator().lookback_bars == 20

    def test_required_fields(self):
        assert VolumeMAIndicator().get_required_fields() == ["volume"]

    def test_output_fields(self):
        assert VolumeMAIndicator().get_output_fields() == ["VOL_MA5", "VOL_MA10", "VOL_MA20"]

    def test_calculate_success(self, sample_df):
        df_out = VolumeMAIndicator().calculate(sample_df)
        for col in ("VOL_MA5", "VOL_MA10", "VOL_MA20"):
            assert col in df_out.columns

    def test_insufficient_data(self):
        df_short = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=3, freq="D"),
            "close": [1.0, 1.2, 1.1], "open": [1.0, 1.1, 1.2],
            "high": [1.2, 1.3, 1.4], "low": [0.9, 1.0, 1.1],
            "volume": [100, 110, 105],
        })
        df_out = VolumeMAIndicator().calculate(df_short)
        for col in ("VOL_MA5", "VOL_MA10", "VOL_MA20"):
            assert col in df_out.columns

    def test_custom_params(self):
        ind = VolumeMAIndicator(periods=[3, 7])
        assert ind.name == "VOL_MA"
        assert ind.params == {"periods": [3, 7]}
