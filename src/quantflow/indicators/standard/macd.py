"""MACD Indicator implementation."""

import pandas as pd
from typing import Dict, Any, List

from quantflow.indicators.base import IndicatorBase


class MACDIndicator(IndicatorBase):
    
    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
    
    @property
    def name(self) -> str:
        return "MACD"
    
    @property
    def lookback_bars(self) -> int:
        return self.slow_period + self.signal_period + 10
    
    @property
    def params(self) -> Dict[str, Any]:
        return {
            "fast_period": self.fast_period,
            "slow_period": self.slow_period,
            "signal_period": self.signal_period,
        }
    
    def get_required_fields(self) -> List[str]:
        return ["close"]
    
    def get_output_fields(self) -> List[str]:
        return ["DIF", "DEA", "MACD"]
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        ema_fast = df["close"].ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = df["close"].ewm(span=self.slow_period, adjust=False).mean()
        
        # DIF = EMA(12) - EMA(26)
        df["DIF"] = ema_fast - ema_slow
        # DEA = EMA(DIF, 9)
        df["DEA"] = df["DIF"].ewm(span=self.signal_period, adjust=False).mean()
        # MACD = (DIF - DEA) * 2 (Matches TongDaXin logic)
        df["MACD"] = 2 * (df["DIF"] - df["DEA"])
        
        return df