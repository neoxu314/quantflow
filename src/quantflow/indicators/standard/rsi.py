"""RSI Indicator implementation."""

import pandas as pd
import numpy as np
from typing import Dict, Any, List

from quantflow.indicators.base import IndicatorBase


class RSIIndicator(IndicatorBase):
    
    def __init__(self, period: int = 14):
        self.period = period
    
    @property
    def name(self) -> str:
        return "RSI"
    
    @property
    def lookback_bars(self) -> int:
        return self.period + 10
    
    @property
    def params(self) -> Dict[str, Any]:
        return {"period": self.period}
    
    def get_required_fields(self) -> List[str]:
        return ["close"]
    
    def get_output_fields(self) -> List[str]:
        return ["RSI"]
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        delta = df["close"].diff()
        
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Wilder's RSI uses EMA smoothing, not SMA
        avg_gain = gain.ewm(alpha=1 / self.period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / self.period, adjust=False).mean()
        
        rs = avg_gain / avg_loss.replace(0, np.inf)
        df["RSI"] = 100 - (100 / (1 + rs))
        
        df["RSI"] = df["RSI"].fillna(50)
        
        return df