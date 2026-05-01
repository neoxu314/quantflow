"""Volume MA Indicator implementation."""

import pandas as pd
from typing import Dict, Any, List, Optional

from quantflow.indicators.base import IndicatorBase


class VolumeMAIndicator(IndicatorBase):
    
    def __init__(self, periods: Optional[List[int]] = None):
        self.periods = periods if periods is not None else [5, 10, 20]
    
    @property
    def name(self) -> str:
        return "VOL_MA"
    
    @property
    def lookback_bars(self) -> int:
        return max(self.periods) if self.periods else 1
    
    @property
    def params(self) -> Dict[str, Any]:
        return {"periods": self.periods}
    
    def get_required_fields(self) -> List[str]:
        return ["volume"]
    
    def get_output_fields(self) -> List[str]:
        return [f"VOL_MA{p}" for p in self.periods]
    
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        for period in self.periods:
            df[f"VOL_MA{period}"] = df["volume"].rolling(window=period, min_periods=1).mean()
        
        return df