"""KDJ Dead Cross sell strategy."""

import pandas as pd
from typing import List

from quantflow.strategies.base import SellStrategy, Condition
from quantflow.indicators.base import IndicatorBase
from quantflow.indicators.factory import IndicatorFactory


class KDJDeadCrossSell(SellStrategy):
    """
    策略定义：KDJ 死叉卖出策略 (KDJ Dead Cross Sell)

    卖出逻辑（需同时满足）：
    1) KDJ 死叉：K 线从上方向下穿越 D 线。
       即：当前 K < D 且上一根 K >= 上一根 D。
       意义：短期动量转弱，KDJ 指标发出卖出信号。
    """

    @property
    def name(self) -> str:
        return "KDJ_DeadCross"
    
    def get_conditions(self) -> List[Condition]:
        return [
            Condition(field="K", operator="cross_down", value="D"),
        ]
    
    def get_required_indicators(self) -> List[IndicatorBase]:
        return [IndicatorFactory.create("KDJ")]
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        df["kdj_dead_cross_sell"] = (df["K"] < df["D"]) & (df["K"].shift(1) >= df["D"].shift(1))
        
        df["sell_signal"] = df["kdj_dead_cross_sell"]
        df["signal_reason"] = df.apply(
            lambda row: "KDJ dead cross" if row["kdj_dead_cross_sell"] else "",
            axis=1
        )
        
        return df
