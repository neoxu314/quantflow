"""日K-多头区间超卖策略。"""

import pandas as pd
from typing import List

from quantflow.strategies.base import BuyStrategy, Condition
from quantflow.indicators.custom import DualLineIndicator
from quantflow.indicators.standard import KDJIndicator
from quantflow.indicators.base import IndicatorBase


class DailyBullishOversoldBuy(BuyStrategy):
    """
    策略定义：日K-多头区间超卖策略 (Daily Bullish Oversold Buy)
    作者：[你的中文名]

    买入逻辑（需同时满足）：
    1) 趋势判定：处于多头区间。
       即：双线战法中，短期趋势线 > 多空线。
    
    2) 超卖判定：极度恐慌。
       即：KDJ 的 J 值小于 20。说明短线回调幅度够深，有反弹需求。
    
    3) 防守判定：未破位。
       即：收盘价 ≥ 多空线。
       意义：虽然超卖，但不能跌破主力控盘线（多空线），这是抄底的底线。
       排除了那种虽然超卖但已经转成空头趋势的下跌中继。
    """

    @property
    def name(self) -> str:
        return "DailyBullishOversold"

    def get_conditions(self) -> List[Condition]:
        return []

    def get_required_indicators(self) -> List[IndicatorBase]:
        return [DualLineIndicator(), KDJIndicator()]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # 确保计算过双线指标
        if "short_trend_line" not in df.columns:
            ind = DualLineIndicator()
            df = ind.calculate(df)
        
        # 确保计算过 KDJ 指标
        if "J" not in df.columns:
            ind = KDJIndicator()
            df = ind.calculate(df)

        df = df.copy()

        # 条件1：短期趋势线 > 多空线 (多头排列)
        bull_trend = df["short_trend_line"] > df["long_short_line"]

        # 条件2：KDJ 的 J 值 < 20 (超卖)
        oversold = df["J"] < 20

        # 条件3：收盘价 ≥ 多空线 (未破位)
        support_held = df["close"] >= df["long_short_line"]

        # 综合判定
        df["bullish_oversold_buy"] = bull_trend & oversold & support_held
        df["buy_signal"] = df["bullish_oversold_buy"]

        df["signal_reason"] = df.apply(
            lambda row: (
                f"Oversold J={row['J']:.1f} in bull channel"
                if row["bullish_oversold_buy"]
                else ""
            ),
            axis=1,
        )

        return df