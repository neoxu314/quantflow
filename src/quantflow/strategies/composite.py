"""Composite Strategy for combining multiple strategies."""

import pandas as pd
from typing import List, Literal

from quantflow.strategies.base import StrategyBase


class CompositeStrategy(StrategyBase):
    
    def __init__(
        self,
        strategies: List[StrategyBase],
        mode: Literal["all", "any"] = "all"
    ):
        if mode not in ("all", "any"):
            raise ValueError(f"Unsupported composite mode: {mode}")
        self.strategies = strategies
        self.mode = mode
    
    @property
    def name(self) -> str:
        return f"Composite({len(self.strategies)},{self.mode})"
    
    @property
    def signal_type(self) -> str:
        directions = {strategy.signal_type for strategy in self.strategies}
        if len(directions) == 1:
            return next(iter(directions))
        return "mixed"
    
    def get_conditions(self) -> List:
        conditions = []
        for strategy in self.strategies:
            conditions.extend(strategy.get_conditions())
        return conditions

    def get_required_indicators(self):
        indicators = {}
        for strategy in self.strategies:
            for indicator in strategy.get_required_indicators():
                if indicator.name in indicators and indicators[indicator.name].params != indicator.params:
                    raise ValueError(f"Conflicting indicator parameters: {indicator.name}")
                indicators[indicator.name] = indicator
        return list(indicators.values())

    def get_required_period(self) -> str:
        periods = {strategy.get_required_period() for strategy in self.strategies}
        periods.discard("d")
        if len(periods) > 1:
            raise ValueError(f"Incompatible composite periods: {sorted(periods)}")
        return next(iter(periods), "d")
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        base = df.drop(columns=["buy_signal", "sell_signal", "signal_reason"], errors="ignore")
        df = base.copy()
        signal_col = f"{self.name}_signal"
        reason_col = f"{self.name}_reason"
        if not self.strategies:
            return df.assign(**{signal_col: False, reason_col: ""})
        directions = {"buy": [], "sell": []}
        no_signal = pd.Series(False, index=df.index)
        for strategy in self.strategies:
            evaluated = strategy.generate_signals(base.copy())
            for direction, signals in directions.items():
                if strategy.signal_type in (direction, "mixed"):
                    signals.append(evaluated.get(
                        f"{direction}_signal", no_signal
                    ).reindex(df.index).eq(True).fillna(False))

        # A directional all/any only includes children that can emit that direction.
        for direction, signals in directions.items():
            df[f"{direction}_signal"] = False
            if signals:
                voters = pd.concat(signals, axis=1)
                df[f"{direction}_signal"] = getattr(voters, self.mode)(axis=1)
        df[signal_col] = df["buy_signal"] | df["sell_signal"]
        df[reason_col] = df[signal_col].map({True: f"{self.name} ({self.mode} mode)", False: ""})
        df["signal_reason"] = df[reason_col]
        return df
    
    def add_strategy(self, strategy: StrategyBase) -> None:
        self.strategies.append(strategy)
    
    def remove_strategy(self, name: str) -> None:
        self.strategies = [s for s in self.strategies if s.name != name]
    
    def get_strategy_names(self) -> List[str]:
        return [s.name for s in self.strategies]
