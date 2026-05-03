import pytest
import pandas as pd
import numpy as np
import warnings
import os
from unittest.mock import MagicMock

warnings.filterwarnings('ignore')

from quantflow.strategies.base import StrategyBase, BuyStrategy
from quantflow.strategies.buy import DailyBullishMidRangeBuy, DailyBullishOversoldBuy
from quantflow.strategies.composite import CompositeStrategy

@pytest.fixture
def fixture_dir():
    return "fixtures"

@pytest.fixture
def sample_df_with_indicators():
    dates = pd.date_range("2024-01-01", periods=50, freq="D")
    np.random.seed(42)
    close = 100 + np.random.randn(50).cumsum()
    high = close + np.random.rand(50) * 2
    low = close - np.random.rand(50) * 2
    
    from quantflow.indicators.standard import KDJIndicator
    from quantflow.indicators.custom import DualLineIndicator
    
    df = pd.DataFrame({"date": dates, "high": high, "low": low, "close": close, "volume": np.ones(50)*1000})
    
    kdj = KDJIndicator()
    dual = DualLineIndicator()
    
    df = kdj.calculate(df)
    df = dual.calculate(df)
    
    return df


# KDJGoldenCrossBuy tests removed: strategy deleted from codebase


class TestStrategyIntegration:
    """
    Integration tests for strategies using real market data.
    Supports testing specific strategies against expected outcomes.
    """

    def _fetch_cn(self, code, start, end):
        import baostock as bs
        bs.login()
        prefix, ticker = code.split(".")
        target = prefix.lower() + "." + ticker
        
        rs = bs.query_history_k_data_plus(
            target, "date,open,high,low,close,volume",
            start_date=start, end_date=end,
            frequency="d", adjustflag="2"
        )
        records = []
        while rs.error_code == '0' and rs.next():
            records.append(rs.get_row_data())
        bs.logout()
        
        if not records:
            return pd.DataFrame()
        
        cols = ["date", "open", "high", "low", "close", "volume"]
        df = pd.DataFrame(records, columns=cols)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)
        return df

    def _fetch_us(self, ticker, start, end):
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, progress=False)
        if df.empty:
            return df
            
        # Flatten multi-columns if needed
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
            
        df.index = pd.to_datetime(df.index)
        return df

    def _run_strategy(self, strategy_cls, code, date_str, expected, is_cn=True, start_date="2023-01-01"):
        
        # Fetch enough history (depends on strategy requirements, 1-3 years)
        end_date = "2027-01-01" 
        
        if is_cn:
            df = self._fetch_cn(code, start_date, end_date)
        else:
            df = self._fetch_us(code, start_date, end_date)
            
        if df.empty:
            pytest.skip(f"No data for {code} in target range")
        
        # Convert target_date to index format
        target_dt = pd.to_datetime(date_str)
        
        strategy = strategy_cls()
        res = strategy.generate_signals(df)
        
        # Locate date
        row_found = False
        actual = False
        if target_dt in res.index:
            actual = res.loc[target_dt, "buy_signal"]
            row_found = True
        elif hasattr(res.index, 'normalize'):
            try:
                actual = res.loc[target_dt.normalize(), "buy_signal"]
                row_found = True
            except KeyError:
                pass
                
        if not row_found:
            pytest.skip(f"Date {date_str} not found in fetched data.")
            
        assert actual == expected, f"For {code} on {date_str}, expected {expected}, got {actual}"

    def test_mid_range_cn_hit(self):
        self._run_strategy(DailyBullishMidRangeBuy, "sz.002594", "2026-04-10", expected=True, is_cn=True)

    def test_mid_range_cn_miss(self):
        self._run_strategy(DailyBullishMidRangeBuy, "sz.002594", "2026-04-07", expected=False, is_cn=True)

    def test_mid_range_us_miss(self):
        self._run_strategy(DailyBullishMidRangeBuy, "MSFT", "2026-04-15", expected=False, is_cn=False)
        self._run_strategy(DailyBullishMidRangeBuy, "GOOG", "2025-12-10", expected=False, is_cn=False)

    def test_oversold_cn_hit(self):
        self._run_strategy(DailyBullishOversoldBuy, "sz.002594", "2026-04-02", expected=True, is_cn=True)

    def test_oversold_cn_miss(self):
        self._run_strategy(DailyBullishOversoldBuy, "sz.002594", "2026-04-07", expected=False, is_cn=True)
        
    def test_oversold_us_msft_miss(self):
        self._run_strategy(DailyBullishOversoldBuy, "MSFT", "2026-04-15", expected=False, is_cn=False)
        self._run_strategy(DailyBullishOversoldBuy, "MSFT", "2025-10-30", expected=False, is_cn=False)
        
    def test_oversold_tsla_hit(self):
        # TSLA 2024.07.25
        self._run_strategy(DailyBullishOversoldBuy, "TSLA", "2024-07-25", expected=True, is_cn=False, start_date="2023-01-01")


class TestDualLineStrategyNaNHandling:
    """
    Tests verifying strategies safely handle missing DualLine indicators (NaN)
    for new/insufficient stocks.
    """

    def _make_insufficient_df(self):
        dates = pd.date_range("2024-01-01", periods=50, freq="D")
        close = [100.0] * 50 
        
        df = pd.DataFrame({
            "date": dates, "high": close, "low": close, "close": close, "volume": [0]*50
        })
        df.set_index("date", inplace=True)
        
        from quantflow.indicators.custom import DualLineIndicator
        from quantflow.indicators.standard import KDJIndicator
        
        df = KDJIndicator().calculate(df)
        df = DualLineIndicator().calculate(df)
        
        return df

    def test_mid_range_returns_no_signals_on_nan(self):
        """MidRange strategy should NOT trigger signals when lines are NaN."""
        df = self._make_insufficient_df()
        
        assert pd.isna(df["long_short_line"].iloc[-1]) == True
        
        strategy = DailyBullishMidRangeBuy()
        result = strategy.generate_signals(df)
        
        assert result["buy_signal"].iloc[-1] == False

    def test_oversold_returns_no_signals_on_nan(self):
        """Oversold strategy should NOT trigger signals when lines are NaN."""
        df = self._make_insufficient_df()
        
        strategy = DailyBullishOversoldBuy()
        result = strategy.generate_signals(df)
        
        assert result["buy_signal"].iloc[-1] == False

    def test_strategies_with_valid_data(self):
        """Verify strategies still work when we manually mock Valid Lines."""
        length = 100
        base_values = [10.0] * length
        
        df = pd.DataFrame({
            "close": range(100, 100 + length),
            "high": range(100, 100 + length),
            "low": range(100, 100 + length),
            "short_trend_line": [50.0] * length,
            "long_short_line": [40.0] * length,
            "J": base_values
        })
        
        res_mid = DailyBullishMidRangeBuy().generate_signals(df)
        assert res_mid["buy_signal"].iloc[-1] == False

        df["close"] = [45.0] * length
        res_mid = DailyBullishMidRangeBuy().generate_signals(df)
        assert res_mid["buy_signal"].iloc[-1] == True

        res_over = DailyBullishOversoldBuy().generate_signals(df)
        assert res_over["buy_signal"].iloc[-1] == True


class TestCompositeStrategy:
    
    def test_compose(self, sample_df_with_indicators):
        b1 = DailyBullishMidRangeBuy()
        b2 = DailyBullishMidRangeBuy()
        comp = CompositeStrategy([b1, b2], mode="any")
        res = comp.generate_signals(sample_df_with_indicators)
        assert "buy_signal" in res.columns
    
    def test_get_names(self):
        b1 = DailyBullishMidRangeBuy()
        b2 = DailyBullishOversoldBuy()
        comp = CompositeStrategy([b1, b2])
        names = comp.get_strategy_names()
        assert "DailyBullishMidRange" in names
        assert "DailyBullishOversold" in names
