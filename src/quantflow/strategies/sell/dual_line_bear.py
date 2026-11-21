"""Dual Line Bear Zone sell strategy."""

import pandas as pd
from typing import List

from quantflow.strategies.base import SellStrategy, Condition
from quantflow.indicators.base import IndicatorBase
from quantflow.indicators.factory import IndicatorFactory


class DualLineBearZoneSell(SellStrategy):
    """在日线进入双线空头区间时发出卖出信号。

    短期趋势线低于多空线，且前一根日线尚未处于空头区间。
    持续处于空头区间时只在进入的那根日线触发。
    """

    previous_bars = 1

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
        
        df["zone_change_to_bear"] = (
            df["is_bear_zone"].eq(True) & df["is_bear_zone"].shift(1).eq(False)
        ).fillna(False)
        
        df["dual_line_bear_sell"] = df["zone_change_to_bear"]
        df["sell_signal"] = df["dual_line_bear_sell"]
        df["signal_reason"] = df.apply(
            lambda row: "Dual line zone change to bear" if row["dual_line_bear_sell"] else "",
            axis=1
        )
        
        return df
