"""日K-多头中部区间买入策略。"""

import pandas as pd
from typing import List

from quantflow.strategies.base import BuyStrategy, Condition
from quantflow.indicators.factory import IndicatorFactory
from quantflow.indicators.base import IndicatorBase


class DailyBullishMidRangeBuy(BuyStrategy):
    """
    策略定义：日K-多头中部区间买入策略 (Daily Bullish Mid-Range Buy)
    作者：[你的中文名]

    买入逻辑（需同时满足）：
    1) 趋势判定：处于多头区间。
       即：双线战法中，短期趋势线 > 多空线。
    
    2) 位置判定：收盘价处于双线通道内（含触碰）。
       即：[多空线 ≤ 收盘价 ≤ 短期趋势线]。
       意义：确认股价在多头通道内运行，既没破位，也未过度加速，是稳健的回调上车点。
    """

    @property
    def name(self) -> str:
        return "DailyBullishMidRange"

    def get_conditions(self) -> List[Condition]:
        # Logic implemented in generate_signals due to complexity involving range check
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
