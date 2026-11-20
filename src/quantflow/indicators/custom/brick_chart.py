"""Brick Chart Indicator implementation."""

import pandas as pd
from typing import Dict, Any, List

from quantflow.indicators.base import IndicatorBase


def _tdx_sma(series: pd.Series, n: int, m: int) -> pd.Series:
    """Apply recursive TDX smoothing and carry state across undefined inputs."""
    return series.ewm(alpha=m / n, adjust=False, ignore_na=True).mean().where(series.notna())


class BrickChartIndicator(IndicatorBase):
    """Brick Chart Kinetic Energy Indicator.

    Uses the TDX (通达信) momentum formula. Recursive smoothing depends on the
    historical window and OHLCV source. Use a longer warm-up when comparing
    results against TDX. A zero rolling range leaves momentum undefined.
    """

    def __init__(self, period: int = 4, smooth1_n: int = 4, smooth2_n: int = 6, shift: float = 4.0):
        self.period = period
        self.smooth1_n = smooth1_n
        self.smooth2_n = smooth2_n
        self.shift = shift  # Noise filtering threshold: ignores weak momentum values below 4.0
        self.ma_window = 20
        self.vol_window = 5

    @property
    def name(self) -> str:
        return "BrickChart"
    
    @property
    def lookback_bars(self) -> int:
        return max(self.period, self.smooth1_n, self.smooth2_n, self.ma_window, self.vol_window) + 50

    @property
    def params(self) -> Dict[str, Any]:
        return {"period": self.period, "smooth1_n": self.smooth1_n, "smooth2_n": self.smooth2_n, "shift": self.shift}

    def get_required_fields(self) -> List[str]:
        return ["high", "low", "close", "volume"]

    def get_output_fields(self) -> List[str]:
        return ["brick_chart"]

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        n = self.period
        high_n = df["high"].rolling(window=n, min_periods=1).max()
        low_n = df["low"].rolling(window=n, min_periods=1).min()
        range_n = (high_n - low_n).where(high_n > low_n)

        var1a = (high_n - df["close"]) / range_n * 100 - 90
        var2a = _tdx_sma(var1a, self.smooth1_n, 1) + 100

        var3a = (df["close"] - low_n) / range_n * 100
        var4a = _tdx_sma(var3a, 6, 1)
        var5a = _tdx_sma(var4a, self.smooth2_n, 1) + 100

        var6a = var5a - var2a
        df["brick_chart"] = (var6a - self.shift).clip(lower=0)

        return df

    def get_buy_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["block_height"] = df["brick_chart"].diff()
        df["yesterday_block_height"] = df["block_height"].shift(1)

        df["ma20"] = df["close"].rolling(window=self.ma_window, min_periods=1).mean()
        df["v5"] = df["volume"].rolling(window=self.vol_window, min_periods=1).mean()

        turn_point = (df["block_height"] > 0) & (df["yesterday_block_height"] < 0)
        strength = df["block_height"] > (df["yesterday_block_height"].abs() * 0.666)
        df["buy_signal"] = turn_point & strength & (df["close"] > df["ma20"]) & (df["volume"] > df["v5"])
        return df
