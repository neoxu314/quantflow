"""日K-多头区间超卖策略。"""

import pandas as pd
from typing import List

from quantflow.strategies.base import BuyStrategy, Condition
from quantflow.indicators.factory import IndicatorFactory
from quantflow.indicators.base import IndicatorBase


class DailyBullishOversoldBuy(BuyStrategy):
    """在日线多头区间筛选超卖候选。

    同一根日线需满足：短期趋势线高于多空线，KDJ J 小于 20，
    且收盘价不低于多空线。只要条件持续满足，每根日线都可触发。
    入场确认与持有期限由后续研究或回测单独定义。
    """

    @property
    def name(self) -> str:
        return "DailyBullishOversold"

    def get_conditions(self) -> List[Condition]:
        return []

    def get_required_indicators(self) -> List[IndicatorBase]:
        return [IndicatorFactory.create("DualLine"), IndicatorFactory.create("KDJ")]

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # 确保计算过双线指标
        if "short_trend_line" not in df.columns:
            ind = IndicatorFactory.create("DualLine")
            df = ind.calculate(df)
        
        # 确保计算过 KDJ 指标
        if "J" not in df.columns:
            ind = IndicatorFactory.create("KDJ")
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
