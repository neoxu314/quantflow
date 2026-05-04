"""KDJ Indicator implementation."""

import pandas as pd
from typing import Dict, Any, List

from quantflow.indicators.base import IndicatorBase


class KDJIndicator(IndicatorBase):
    
    def __init__(self, n: int = 9, m1: int = 3, m2: int = 3):
        self.n = n
        self.m1 = m1
        self.m2 = m2
    
    @property
    def name(self) -> str:
        return "KDJ"
    
    @property
    def lookback_bars(self) -> int:
        return self.n + self.m1 + self.m2 + 6
    
    @property
    def params(self) -> Dict[str, Any]:
        return {"n": self.n, "m1": self.m1, "m2": self.m2}
    
    def get_required_fields(self) -> List[str]:
        return ["high", "low", "close"]
    
    def get_output_fields(self) -> List[str]:
        return ["K", "D", "J"]
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        low_n = df["low"].rolling(window=self.n, min_periods=1).min()
        high_n = df["high"].rolling(window=self.n, min_periods=1).max()
        
        rsv = (df["close"] - low_n) / (high_n - low_n) * 100
        rsv = rsv.fillna(50)
        
        k = pd.Series(50.0, index=df.index)
        d = pd.Series(50.0, index=df.index)
        
        k_prev = (self.m1 - 1) / self.m1
        k_curr = 1 / self.m1
        d_prev = (self.m2 - 1) / self.m2
        d_curr = 1 / self.m2
        
        for i in range(1, len(df)):
            k.iloc[i] = k.iloc[i - 1] * k_prev + rsv.iloc[i] * k_curr
            d.iloc[i] = d.iloc[i - 1] * d_prev + k.iloc[i] * d_curr
        
        j = 3 * k - 2 * d
        
        df["K"] = k
        df["D"] = d
        df["J"] = j
        
        return df