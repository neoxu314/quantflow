"""Stop Loss sell strategy."""

import pandas as pd
from typing import List, Optional
from dataclasses import dataclass

from quantflow.strategies.base import SellStrategy, Condition


@dataclass
class StopLossConfig:
    percentage: float = 5.0
    from_entry: bool = True


class StopLossSell(SellStrategy):
    
    def __init__(self, config: Optional[StopLossConfig] = None):
        self.config = config or StopLossConfig()
    
    @property
    def name(self) -> str:
        return "StopLoss"
    
    def get_conditions(self) -> List[Condition]:
        return []
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        df["stop_loss_sell"] = False
        df["sell_signal"] = False
        df["signal_reason"] = ""
        
        return df
    
    def generate_signals_with_entry(self, df: pd.DataFrame, entry_price: float) -> pd.DataFrame:
        df = df.copy()
        
        stop_price = entry_price * (1 - self.config.percentage / 100)
        
        df["stop_loss_sell"] = df["close"] < stop_price
        df["sell_signal"] = df["stop_loss_sell"]
        df["signal_reason"] = df.apply(
            lambda row: f"Stop loss triggered: {row['close']:.2f} < {stop_price:.2f}" if row["stop_loss_sell"] else "",
            axis=1
        )
        
        return df