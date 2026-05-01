"""KDJ Dead Cross sell strategy."""

import pandas as pd
from typing import List

from quantflow.strategies.base import SellStrategy, Condition
from quantflow.indicators.base import IndicatorBase
from quantflow.indicators.standard import KDJIndicator


class KDJDeadCrossSell(SellStrategy):
    
    @property
    def name(self) -> str:
        return "KDJ_DeadCross"
    
    def get_conditions(self) -> List[Condition]:
        return [
            Condition(field="K", operator="cross_down", value="D"),
        ]
    
    def get_required_indicators(self) -> List[IndicatorBase]:
        return [KDJIndicator()]
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        df["kdj_dead_cross_sell"] = (df["K"] < df["D"]) & (df["K"].shift(1) >= df["D"].shift(1))
        
        df["sell_signal"] = df["kdj_dead_cross_sell"]
        df["signal_reason"] = df.apply(
            lambda row: "KDJ dead cross" if row["kdj_dead_cross_sell"] else "",
            axis=1
        )
        
        return df