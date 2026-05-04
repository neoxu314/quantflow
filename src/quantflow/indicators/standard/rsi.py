"""RSI Indicator implementation with multi-period support."""

import pandas as pd
import numpy as np
from typing import Dict, Any, List

from quantflow.indicators.base import IndicatorBase


class RSIIndicator(IndicatorBase):

    def __init__(self, periods: List[int] = None):
        self.periods = periods if periods is not None else [14]

    @property
    def name(self) -> str:
        return "RSI"

    @property
    def lookback_bars(self) -> int:
        return max(self.periods) + 10

    @property
    def params(self) -> Dict[str, Any]:
        return {"periods": self.periods}

    def get_required_fields(self) -> List[str]:
        return ["close"]

    def get_output_fields(self) -> List[str]:
        return [f"RSI{p}" for p in self.periods]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        delta = df["close"].diff()

        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        for period in self.periods:
            avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
            avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

            rs = avg_gain / avg_loss.replace(0, np.inf)
            col = f"RSI{period}"
            df[col] = 100 - (100 / (1 + rs))
            df[col] = df[col].fillna(50)

        return df
