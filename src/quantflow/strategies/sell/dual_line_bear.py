"""Dual Line Bear Zone sell strategy."""

import pandas as pd
from typing import List

from quantflow.strategies.base import SellStrategy, Condition
from quantflow.indicators.base import IndicatorBase
from quantflow.indicators.factory import IndicatorFactory


class DualLineBearZoneSell(SellStrategy):
    """
    策略定义：双线空头区间卖出策略 (Dual Line Bear Zone Sell)

    卖出逻辑（需同时满足）：
    1) 空头区间：双线战法中，进入空头状态（is_bear_zone == True）。
       即：短期趋势线 < 多空线，且状态刚转为空头。
       意义：趋势由多转空，应及时卖出离场。
    """

    @property
    def name(self) -> str:
        return "DualLine_BearZone"
    
    def get_conditions(self) -> List[Condition]:
        return [
            Condition(field="is_bear_zone", operator="==", value=True),
        ]
    
    def get_required_indicators(self) -> List[IndicatorBase]:
        return [IndicatorFactory.create("DualLine")]
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        df["zone_change_to_bear"] = df["is_bear_zone"] & (~df["is_bear_zone"].shift(1).fillna(False))
        
        df["dual_line_bear_sell"] = df["zone_change_to_bear"]
        df["sell_signal"] = df["dual_line_bear_sell"]
        df["signal_reason"] = df.apply(
            lambda row: "Dual line zone change to bear" if row["dual_line_bear_sell"] else "",
            axis=1
        )
        
        return df
