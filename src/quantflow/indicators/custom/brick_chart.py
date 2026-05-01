"""Brick Chart Indicator implementation."""

import pandas as pd
from typing import Dict, Any, List

from quantflow.indicators.base import IndicatorBase


def _tdx_sma(series: pd.Series, n: int, m: int) -> pd.Series:
    """TDX SMA(X, N, M): Y = (M * X + (N - M) * Y_prev) / N"""
    result = pd.Series(0.0, index=series.index)
    result.iloc[0] = series.iloc[0]
    for i in range(1, len(series)):
        result.iloc[i] = result.iloc[i - 1] * (n - m) / n + series.iloc[i] * m / n
    return result


class BrickChartIndicator(IndicatorBase):
    """Brick Chart Kinetic Energy Indicator.

    Replicates the TDX (通达信) formula for momentum analysis.
    Note on TDX Parity and Convergence:
    1. **Warm-up Period**: The indicator uses SMA (recursive smoothing), which relies on
       historical data depth. With short data windows (e.g., < 60 bars), results will
       diverge from TDX due to initialization differences. To match TDX values exactly,
       ensure at least 1 year of historical data is fed into the calculation.
    2. **Data Source Precision**: Even with full history, absolute values may differ slightly
       from TDX if the input OHLCV data (e.g., BaoStock vs TDX commercial feed) has minor
       discrepancies in split-adjustment. However, the trend direction and color signals
       remain consistent and reliable across data sources.
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
        range_n = high_n - low_n

        var1a = (high_n - df["close"]) / range_n * 100 - 90
        var2a = _tdx_sma(var1a, self.smooth1_n, 1) + 100

        var3a = (df["close"] - low_n) / range_n * 100
        var4a = _tdx_sma(var3a, 6, 1)
        var5a = _tdx_sma(var4a, self.smooth2_n, 1) + 100

        var6a = var5a - var2a
        df["brick_chart"] = (var6a > self.shift) * (var6a - self.shift)

        return df

    def get_buy_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["block_height"] = df["brick_chart"] - df["brick_chart"].shift(1).fillna(0)
        df["yesterday_block_height"] = df["brick_chart"].shift(1) - df["brick_chart"].shift(2).fillna(0)

        df["ma20"] = df["close"].rolling(window=self.ma_window, min_periods=1).mean()
        df["v5"] = df["volume"].rolling(window=self.vol_window, min_periods=1).mean()

        turn_point = (df["block_height"] > 0) & (df["yesterday_block_height"] < 0)
        strength = df["block_height"] > (df["yesterday_block_height"].abs() * 0.666)
        df["buy_signal"] = turn_point & strength & (df["close"] > df["ma20"]) & (df["volume"] > df["v5"])
        return df
