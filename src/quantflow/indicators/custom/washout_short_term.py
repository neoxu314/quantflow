"""Washout Short Term Indicator implementation."""

import pandas as pd
from typing import Dict, Any, List

from quantflow.indicators.base import IndicatorBase


class WashoutIndicator(IndicatorBase):
    """Washout Short Term Indicator.
    
    Captures multi-cycle dip buying opportunities by tracking the relative
    position of the close within recent price ranges. Identifies four types
    of robust entry signals:
    1. 'Four Zero': Panic selling climax (short/mid/mid_long/long <= 6).
    2. 'Dip': Bull market pullback (short <= 20 but long >= 60).
    3. 'Golden Cross': Bottom reversal confirmation (short crosses up long < 20).
    4. 'Crossover': Weakness to strength (short crosses up mid < 30).
    """

    def __init__(self, n1: int = 3, n2: int = 21):
        self.n1 = n1
        self.n2 = n2

    @property
    def name(self) -> str:
        return "Washout"
    
    @property
    def lookback_bars(self) -> int:
        return max(self.n1, 10, 20, self.n2) + 5

    @property
    def params(self) -> Dict[str, Any]:
        return {"n1": self.n1, "n2": self.n2}

    def get_required_fields(self) -> List[str]:
        return ["high", "low", "close", "volume"]

    def get_output_fields(self) -> List[str]:
        return ["short", "mid", "mid_long", "long", "washout_signal"]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        short_low = df["low"].rolling(window=self.n1, min_periods=1).min()
        short_high_close = df["close"].rolling(window=self.n1, min_periods=1).max()
        df["short"] = 100 * (df["close"] - short_low) / (short_high_close - short_low)

        mid_low = df["low"].rolling(window=10, min_periods=1).min()
        mid_high_close = df["close"].rolling(window=10, min_periods=1).max()
        df["mid"] = 100 * (df["close"] - mid_low) / (mid_high_close - mid_low)

        mid_long_low = df["low"].rolling(window=20, min_periods=1).min()
        mid_long_high_close = df["close"].rolling(window=20, min_periods=1).max()
        df["mid_long"] = 100 * (df["close"] - mid_long_low) / (mid_long_high_close - mid_long_low)

        long_low = df["low"].rolling(window=self.n2, min_periods=1).min()
        long_high_close = df["close"].rolling(window=self.n2, min_periods=1).max()
        df["long"] = 100 * (df["close"] - long_low) / (long_high_close - long_low)

        df["buy_four_zero"] = (df["short"] <= 6) & (df["mid"] <= 6) & (df["mid_long"] <= 6) & (df["long"] <= 6)
        df["buy_white_below_20"] = (df["short"] <= 20) & (df["long"] >= 60)
        df["buy_white_cross_red"] = (df["short"] > df["long"]) & (df["short"].shift(1) <= df["long"].shift(1)) & (df["long"] < 20)
        df["buy_white_cross_yellow"] = (df["short"] > df["mid"]) & (df["short"].shift(1) <= df["mid"].shift(1)) & (df["mid"] < 30)

        df["washout_signal"] = df["buy_four_zero"] | df["buy_white_below_20"] | df["buy_white_cross_red"] | df["buy_white_cross_yellow"]

        return df
