"""Dual Line Strategy Indicator implementation."""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional

from quantflow.indicators.base import IndicatorBase


class DualLineIndicator(IndicatorBase):
    
    def __init__(
        self,
        ema_period: int = 10,
        ma_periods: Optional[List[int]] = None
    ):
        self.ema_period = ema_period
        self.ma_periods = ma_periods or [14, 28, 57, 114]
    
    @property
    def name(self) -> str:
        return "DualLine"
    
    @property
    def lookback_bars(self) -> int:
        return max(self.ema_period, *self.ma_periods)
    
    @property
    def params(self) -> Dict[str, Any]:
        return {
            "ema_period": self.ema_period,
            "ma_periods": self.ma_periods,
        }
    
    def get_required_fields(self) -> List[str]:
        return ["close"]
    
    def get_output_fields(self) -> List[str]:
        return [
            "short_trend_line",
            "long_short_line",
            "is_bull_zone",
            "is_bear_zone",
        ]
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        ema1 = df["close"].ewm(span=self.ema_period, adjust=False).mean()
        df["short_trend_line"] = ema1.ewm(span=self.ema_period, adjust=False).mean()
        
        ma_sum = pd.Series(0.0, index=df.index)
        valid_count = pd.Series(0, index=df.index)
        
        for period in self.ma_periods:
            ma = df["close"].rolling(window=period, min_periods=period).mean()
            valid = ~ma.isna()
            ma_sum = ma_sum.add(ma.fillna(0), fill_value=0)
            valid_count = valid_count.add(valid.astype(int), fill_value=0)
        
        # Strict mode: Invalidate lines if not all periods are complete
        # For new stocks, insufficient history prevents false signals
        required_count = len(self.ma_periods)
        is_complete = valid_count >= required_count
        
        avg = ma_sum / valid_count.replace(0, np.nan)
        df["long_short_line"] = avg.where(is_complete)
        
        df["is_bull_zone"] = (df["long_short_line"] < df["short_trend_line"]).astype("boolean").where(is_complete)
        df["is_bear_zone"] = (df["long_short_line"] > df["short_trend_line"]).astype("boolean").where(is_complete)
        
        return df