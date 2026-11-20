import pytest
import pandas as pd
import numpy as np
import warnings
import os
from unittest.mock import MagicMock

warnings.filterwarnings('ignore')

from quantflow.strategies.base import (
    StrategyBase, SignalOutput, BuyStrategy, SellStrategy
)
from quantflow.strategies.buy import DailyBullishMidRangeBuy, DailyBullishOversoldBuy
from quantflow.strategies.sell import KDJDeadCrossSell, DualLineBearZoneSell, StopLossSell
from quantflow.strategies.composite import CompositeStrategy
from quantflow.indicators.base import Condition, IndicatorBase

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


@pytest.mark.integration
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


class TestSignalOutput:
    """Tests for SignalOutput dataclass."""

    def test_default_values(self):
        out = SignalOutput()
        assert out.buy_signal is False
        assert out.sell_signal is False
        assert out.signal_strength == 0.0
        assert out.signal_reason == ""

    def test_buy_signal(self):
        out = SignalOutput(
            buy_signal=True, signal_strength=1.0, signal_reason="bullish cross"
        )
        assert out.buy_signal is True
        assert out.sell_signal is False
        assert out.signal_strength == 1.0
        assert out.signal_reason == "bullish cross"

    def test_sell_signal(self):
        out = SignalOutput(
            sell_signal=True, signal_strength=1.0, signal_reason="dead cross"
        )
        assert out.buy_signal is False
        assert out.sell_signal is True
        assert out.signal_strength == 1.0
        assert out.signal_reason == "dead cross"

    def test_to_dict_complete(self):
        out = SignalOutput(
            buy_signal=True, sell_signal=False, signal_strength=0.8, signal_reason="test"
        )
        assert out.to_dict() == {
            "buy_signal": True,
            "sell_signal": False,
            "signal_strength": 0.8,
            "signal_reason": "test",
        }

    def test_to_dict_matches_output_columns(self):
        """to_dict keys should match generate_signals() output columns."""
        out = SignalOutput(buy_signal=True, sell_signal=True)
        d = out.to_dict()
        assert set(d.keys()) == {"buy_signal", "sell_signal", "signal_strength", "signal_reason"}


# Concrete test subclass for testing StrategyBase abstract contract
class _TestableBuyStrategy(BuyStrategy):
    """Minimal concrete BuyStrategy for testing base class methods."""

    @property
    def name(self) -> str:
        return "TestableBuy"

    def get_conditions(self):
        return [
            Condition(field="RSI", operator=">", value=50),
            Condition(field="close", operator=">", value="open"),
        ]

    def get_required_indicators(self):
        return []

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["buy_signal"] = True
        return df


class _TestableSellStrategy(SellStrategy):
    """Minimal concrete SellStrategy for testing base class methods."""

    @property
    def name(self) -> str:
        return "TestableSell"

    def get_conditions(self):
        return [Condition(field="RSI", operator="<", value=30)]

    def get_required_indicators(self):
        return []

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["sell_signal"] = True
        return df


class _TestableStrategyWithIndicators(BuyStrategy):
    """Strategy that declares indicator requirements."""

    @property
    def name(self) -> str:
        return "TestableWithInd"

    def get_conditions(self):
        return [Condition(field="J", operator="<", value=20)]

    def get_required_indicators(self):
        from quantflow.indicators.factory import IndicatorFactory
        return [IndicatorFactory.create("KDJ")]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["buy_signal"] = False
        return df


class TestStrategyBaseContract:
    """Tests for StrategyBase abstract contract and concrete helper methods."""

    # --- SignalOutput ---

    def test_buy_strategy_signal_type(self):
        assert BuyStrategy.signal_type.fget(_TestableBuyStrategy()) == "buy"
        s = _TestableBuyStrategy()
        assert s.signal_type == "buy"

    def test_sell_strategy_signal_type(self):
        s = _TestableSellStrategy()
        assert s.signal_type == "sell"

    # --- evaluate_row ---

    def test_evaluate_row_all_conditions_met(self):
        df = pd.DataFrame({
            "RSI": [55.0],
            "close": [105.0],
            "open": [100.0],
        })
        strat = _TestableBuyStrategy()
        result = strat.evaluate_row(df, row_idx=0)
        assert result.buy_signal is True
        assert result.sell_signal is False
        assert result.signal_strength == 1.0
        assert "TestableBuy" in result.signal_reason

    def test_evaluate_row_conditions_not_met(self):
        df = pd.DataFrame({
            "RSI": [30.0],  # 30 < 50, condition fails
            "close": [95.0],
            "open": [100.0],
        })
        strat = _TestableBuyStrategy()
        result = strat.evaluate_row(df, row_idx=0)
        assert result.buy_signal is False
        assert result.signal_strength == 0.0
        assert result.signal_reason == ""

    def test_evaluate_row_no_conditions(self):
        """Strategies with empty get_conditions() should return default SignalOutput."""
        strat = DailyBullishOversoldBuy()  # returns []
        df = pd.DataFrame({"close": [100.0], "J": [10.0]})
        result = strat.evaluate_row(df, row_idx=0)
        assert result.buy_signal is False
        assert result.signal_strength == 0.0

    def test_evaluate_row_cross_down_condition(self):
        df = pd.DataFrame({
            "K": [45.0, 50.0, 40.0],  # row 2: K(40) < D(48), and prev K(50) >= prev D(49)
            "D": [42.0, 49.0, 48.0],
        })
        strat = KDJDeadCrossSell()
        result = strat.evaluate_row(df, row_idx=2)
        assert result.sell_signal is True

    def test_evaluate_row_cross_down_not_triggered(self):
        df = pd.DataFrame({
            "K": [40.0, 45.0, 50.0],  # K rising, no cross down
            "D": [42.0, 46.0, 52.0],
        })
        strat = KDJDeadCrossSell()
        result = strat.evaluate_row(df, row_idx=2)
        assert result.sell_signal is False

    # --- validate_input ---

    def test_validate_input_success(self):
        df = pd.DataFrame({
            "RSI": [50.0],
            "close": [100.0],
            "open": [98.0],
        })
        strat = _TestableBuyStrategy()
        assert strat.validate_input(df) is True

    def test_validate_input_missing_column(self):
        df = pd.DataFrame({"close": [100.0]})  # missing RSI, open
        strat = _TestableBuyStrategy()
        assert strat.validate_input(df) is False

    # --- get_required_fields ---

    def test_get_required_fields_from_conditions(self):
        strat = _TestableBuyStrategy()  # RSI > 50, close > open
        fields = strat.get_required_fields()
        assert "RSI" in fields
        assert "close" in fields
        assert "open" in fields
        assert len(fields) == 3  # RSI, close, open

    def test_get_required_fields_value_is_number(self):
        """When condition value is a number, only field name is added."""
        s = KDJDeadCrossSell()
        fields = s.get_required_fields()
        assert "K" in fields
        assert "D" in fields

    # --- get_lookback_bars ---

    def test_get_lookback_bars_no_indicators(self):
        strat = _TestableBuyStrategy()
        assert strat.get_lookback_bars() == 1  # default when no indicators

    def test_get_lookback_bars_with_indicators(self):
        from quantflow.indicators.factory import IndicatorFactory
        kdj = IndicatorFactory.create("KDJ")
        strat = _TestableStrategyWithIndicators()
        assert strat.get_lookback_bars() == kdj.lookback_bars

    # --- get_required_period ---

    def test_get_required_period_default(self):
        strat = _TestableBuyStrategy()
        assert strat.get_required_period() == "d"

    # --- get_conditions ---

    def test_buy_strategy_conditions(self):
        s = KDJDeadCrossSell()
        conds = s.get_conditions()
        assert len(conds) == 1
        assert conds[0].field == "K"
        assert conds[0].operator == "cross_down"
        assert conds[0].value == "D"

    def test_dual_line_bear_conditions(self):
        s = DualLineBearZoneSell()
        conds = s.get_conditions()
        assert len(conds) == 1
        assert conds[0].field == "is_bear_zone"
        assert conds[0].operator == "=="
        assert conds[0].value is True

    def test_buy_strategies_return_empty_conditions(self):
        """Buy strategies use procedural logic, not Condition objects."""
        assert DailyBullishMidRangeBuy().get_conditions() == []
        assert DailyBullishOversoldBuy().get_conditions() == []

    # --- generate_signals output columns ---

    def test_buy_generates_buy_signal_column(self):
        df = pd.DataFrame({
            "close": [100.0], "high": [100.0], "low": [100.0],
            "short_trend_line": [105.0], "long_short_line": [95.0],
            "J": [15.0], "open": [99.0],
        })
        result = DailyBullishOversoldBuy().generate_signals(df)
        assert "buy_signal" in result.columns

    def test_sell_generates_sell_signal_column(self):
        df = pd.DataFrame({
            "K": [50.0, 45.0, 40.0],
            "D": [48.0, 47.0, 48.0],
        })
        result = KDJDeadCrossSell().generate_signals(df)
        assert "sell_signal" in result.columns

    # --- StopLossSell specific ---

    def test_stop_loss_default_generate_signals_all_false(self):
        """Without entry price, StopLossSell should return all False."""
        df = pd.DataFrame({"close": [100.0, 90.0, 80.0]})
        strat = StopLossSell()
        result = strat.generate_signals(df)
        assert (result["sell_signal"] == False).all()
        assert (result["stop_loss_sell"] == False).all()

    def test_stop_loss_with_entry_triggers(self):
        df = pd.DataFrame({"close": [100.0, 97.0, 96.0, 90.0]})
        strat = StopLossSell()
        result = strat.generate_signals_with_entry(df, entry_price=100.0)
        assert result.loc[0, "sell_signal"] == False
        assert result.loc[1, "sell_signal"] == False
        assert result.loc[2, "sell_signal"] == False
        assert result.loc[3, "sell_signal"] == True

    def test_stop_loss_with_custom_percentage(self):
        from quantflow.strategies.sell.stop_loss import StopLossConfig
        df = pd.DataFrame({"close": [100.0, 92.0, 88.0]})
        strat = StopLossSell(config=StopLossConfig(percentage=10.0))
        result = strat.generate_signals_with_entry(df, entry_price=100.0)
        assert result.loc[0, "sell_signal"] == False
        assert result.loc[1, "sell_signal"] == False
        assert result.loc[2, "sell_signal"] == True

    def test_stop_loss_signal_reason(self):
        df = pd.DataFrame({"close": [85.0]})
        strat = StopLossSell()
        result = strat.generate_signals_with_entry(df, entry_price=100.0)
        assert "Stop loss triggered" in result.loc[0, "signal_reason"]
        assert "95.00" in result.loc[0, "signal_reason"]


class TestCompositeStrategy:

    def test_compose_any_mode(self, sample_df_with_indicators):
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

    def test_name_property(self):
        b1 = DailyBullishMidRangeBuy()
        b2 = DailyBullishOversoldBuy()
        comp_any = CompositeStrategy([b1, b2], mode="any")
        comp_all = CompositeStrategy([b1, b2], mode="all")
        assert comp_any.name == "Composite(2,any)"
        assert comp_all.name == "Composite(2,all)"

    def test_signal_type_buy_only(self):
        comp = CompositeStrategy([
            DailyBullishMidRangeBuy(),
            DailyBullishOversoldBuy(),
        ])
        assert comp.signal_type == "buy"

    def test_signal_type_sell_only(self):
        comp = CompositeStrategy([
            KDJDeadCrossSell(),
            DualLineBearZoneSell(),
        ])
        assert comp.signal_type == "sell"

    def test_signal_type_mixed(self):
        comp = CompositeStrategy([
            DailyBullishMidRangeBuy(),
            KDJDeadCrossSell(),
        ])
        assert comp.signal_type == "mixed"

    @pytest.mark.parametrize("mode", ["all", "any"])
    def test_nested_composite_keeps_direction_votes_separate(self, mode):
        from unittest.mock import Mock

        buyer = Mock(signal_type="buy")
        buyer.generate_signals.side_effect = lambda df: df.assign(buy_signal=[True, False])
        seller = Mock(signal_type="sell")
        seller.generate_signals.side_effect = lambda df: df.assign(sell_signal=[False, True])
        mixed = CompositeStrategy([buyer, seller], mode=mode)
        result = CompositeStrategy([buyer, mixed], mode=mode).generate_signals(
            pd.DataFrame({"buy_signal": [True, True], "sell_signal": [True, True]})
        )

        assert result.buy_signal.tolist() == [True, False]
        assert result.sell_signal.tolist() == [False, True]

    def test_all_mode_requires_all_triggers(self):
        length = 100
        df = pd.DataFrame({
            "close": [45.0] * length,
            "high": [46.0] * length,
            "low": [44.0] * length,
            "short_trend_line": [50.0] * length,
            "long_short_line": [40.0] * length,
            "J": [15.0] * length,
        })

        b1 = DailyBullishMidRangeBuy()
        b2 = DailyBullishOversoldBuy()
        comp = CompositeStrategy([b1, b2], mode="all")
        res = comp.generate_signals(df)
        assert res["buy_signal"].iloc[-1] == True

        df["J"] = [30.0] * length
        res2 = comp.generate_signals(df)
        assert res2["buy_signal"].iloc[-1] == False

    def test_any_mode_one_triggers(self):
        length = 100
        df = pd.DataFrame({
            "close": [45.0] * length,
            "high": [46.0] * length,
            "low": [44.0] * length,
            "short_trend_line": [50.0] * length,
            "long_short_line": [40.0] * length,
            "J": [30.0] * length,
        })

        b1 = DailyBullishMidRangeBuy()
        b2 = DailyBullishOversoldBuy()
        comp = CompositeStrategy([b1, b2], mode="any")
        res = comp.generate_signals(df)
        assert res["buy_signal"].iloc[-1] == True

        df["close"] = [55.0] * length
        res2 = comp.generate_signals(df)
        assert res2["buy_signal"].iloc[-1] == False

    def test_empty_strategies_list(self):
        df = pd.DataFrame({"close": [100.0]})
        comp = CompositeStrategy([])
        res = comp.generate_signals(df)
        assert len(res) == 1
        assert "buy_signal" not in res.columns

    def test_add_strategy(self):
        b1 = DailyBullishMidRangeBuy()
        comp = CompositeStrategy([b1])
        assert len(comp.strategies) == 1

        comp.add_strategy(DailyBullishOversoldBuy())
        assert len(comp.strategies) == 2
        assert "DailyBullishOversold" in comp.get_strategy_names()

    def test_remove_strategy_by_name(self):
        b1 = DailyBullishMidRangeBuy()
        b2 = DailyBullishOversoldBuy()
        comp = CompositeStrategy([b1, b2])
        assert len(comp.strategies) == 2

        comp.remove_strategy("DailyBullishMidRange")
        assert len(comp.strategies) == 1
        assert "DailyBullishMidRange" not in comp.get_strategy_names()

    def test_remove_strategy_nonexistent(self):
        b1 = DailyBullishMidRangeBuy()
        comp = CompositeStrategy([b1])
        comp.remove_strategy("NonExistent")
        assert len(comp.strategies) == 1

    def test_get_conditions_aggregates_all(self):
        b1 = DailyBullishMidRangeBuy()  # get_conditions() returns []
        b2 = KDJDeadCrossSell()         # returns [Condition(K, cross_down, D)]
        comp = CompositeStrategy([b1, b2])
        conds = comp.get_conditions()
        assert len(conds) == 1
        assert conds[0].field == "K"
        assert conds[0].operator == "cross_down"


def test_oversold_strict_threshold_and_inclusive_support():
    frame = pd.DataFrame({
        "J": [19.9, 20.0, 19.9, 19.9, np.nan],
        "short_trend_line": [11.0, 11.0, 10.0, 11.0, 11.0],
        "long_short_line": [10.0] * 5,
        "close": [10.0, 10.0, 10.0, 9.99, 10.0],
    })
    result = DailyBullishOversoldBuy().generate_signals(frame)
    assert result.buy_signal.tolist() == [True, False, False, False, False]
    assert result.signal_reason.tolist() == ["Oversold J=19.9 in bull channel", "", "", "", ""]
