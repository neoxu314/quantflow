"""BOLL Indicator implementation."""

import pandas as pd
import numpy as np
from typing import Dict, Any, List

from quantflow.indicators.base import IndicatorBase


class BOLLIndicator(IndicatorBase):
    
    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev
    
    @property
    def name(self) -> str:
        return "BOLL"
    
    @property
    def lookback_bars(self) -> int:
        return self.period + 5
    
    @property
    def params(self) -> Dict[str, Any]:
        return {"period": self.period, "std_dev": self.std_dev}
    
    def get_required_fields(self) -> List[str]:
        return ["close"]
    
    def get_output_fields(self) -> List[str]:
        return ["BOLL_MID", "BOLL_UPPER", "BOLL_LOWER"]
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        df["BOLL_MID"] = df["close"].rolling(window=self.period, min_periods=1).mean()
        std = df["close"].rolling(window=self.period, min_periods=1).std()
        
        df["BOLL_UPPER"] = df["BOLL_MID"] + self.std_dev * std
        df["BOLL_LOWER"] = df["BOLL_MID"] - self.std_dev * std
        
        return df