"""Custom Buy Strategy Template."""

import pandas as pd
from typing import List

from quantflow.strategies.base import BuyStrategy, Condition


class KDJGoldenCrossBuy(BuyStrategy):
    
    @property
    def name(self) -> str:
        return "CustomBuy_1"
    
    def get_conditions(self) -> List[Condition]:
        # TODO: Add your buy conditions
        return []
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # TODO: Implement your buy logic here
        df["buy_signal"] = False
        df["signal_reason"] = ""
        return df