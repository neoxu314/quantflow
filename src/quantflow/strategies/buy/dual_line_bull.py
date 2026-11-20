"""日K-多头中部区间买入策略。"""

import pandas as pd
from typing import List

from quantflow.strategies.base import BuyStrategy, Condition
from quantflow.indicators.factory import IndicatorFactory
from quantflow.indicators.base import IndicatorBase


class DailyBullishMidRangeBuy(BuyStrategy):
    """在日线多头区间筛选回调候选。

    短期趋势线需高于多空线，收盘价须位于两线之间，等于任一边界
    也算命中。只要条件持续满足，每根日线都可触发。
    """

    @property
    def name(self) -> str:
        return "DailyBullishMidRange"

    def get_conditions(self) -> List[Condition]:
        # The range check is implemented in generate_signals().
        return []

    def get_required_indicators(self) -> List[IndicatorBase]:
        return [IndicatorFactory.create("DualLine")]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # 确保计算过双线指标
        if "short_trend_line" not in df.columns:
            ind = IndicatorFactory.create("DualLine")
            df = ind.calculate(df)

        df = df.copy()

        # 条件1：短期趋势线 > 多空线 (多头排列)
        bull_trend = df["short_trend_line"] > df["long_short_line"]

        # 条件2：收盘价在两条线之间 (包含等于)
        # 多头排列下：low_line = long_short_line, high_line = short_trend_line
        price_in_channel = (df["close"] >= df["long_short_line"]) & (
            df["close"] <= df["short_trend_line"]
        )

        df["bullish_mid_range_buy"] = bull_trend & price_in_channel
        df["buy_signal"] = df["bullish_mid_range_buy"]

        df["signal_reason"] = df.apply(
            lambda row: (
                "Price is within bullish channel"
                if row["bullish_mid_range_buy"]
                else ""
            ),
            axis=1,
        )

        return df
