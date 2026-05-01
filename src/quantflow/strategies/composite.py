"""Composite Strategy for combining multiple strategies."""

import pandas as pd
from typing import List, Literal

from quantflow.strategies.base import StrategyBase, SignalOutput


class CompositeStrategy(StrategyBase):
    
    def __init__(
        self,
        strategies: List[StrategyBase],
        mode: Literal["all", "any"] = "all"
    ):
        self.strategies = strategies
        self.mode = mode
    
    @property
    def name(self) -> str:
        return f"Composite({len(self.strategies)},{self.mode})"
    
    @property
    def signal_type(self) -> str:
        buy_strategies = [s for s in self.strategies if s.signal_type == "buy"]
        sell_strategies = [s for s in self.strategies if s.signal_type == "sell"]
        
        if buy_strategies and not sell_strategies:
            return "buy"
        elif sell_strategies and not buy_strategies:
            return "sell"
        return "mixed"
    
    def get_conditions(self) -> List:
        conditions = []
        for strategy in self.strategies:
            conditions.extend(strategy.get_conditions())
        return conditions
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        signal_col = f"{self.name}_signal"
        reason_col = f"{self.name}_reason"
        
        df[signal_col] = False
        df[reason_col] = ""
        
        strategy_results = []
        for strategy in self.strategies:
            result_df = strategy.generate_signals(df)
            
            if strategy.signal_type == "buy":
                signal_name = "buy_signal"
            else:
                signal_name = "sell_signal"
            
            if signal_name in result_df.columns:
                strategy_results.append(result_df[signal_name])
        
        if not strategy_results:
            return df
        
        if self.mode == "all":
            df[signal_col] = pd.concat(strategy_results, axis=1).all(axis=1)
        else:
            df[signal_col] = pd.concat(strategy_results, axis=1).any(axis=1)
        
        df["buy_signal"] = df[signal_col] if self.signal_type in ["buy", "mixed"] else False
        df["sell_signal"] = df[signal_col] if self.signal_type in ["sell", "mixed"] else False
        
        df["signal_reason"] = df.apply(
            lambda row: f"{self.name} ({self.mode} mode)" if row[signal_col] else "",
            axis=1
        )
        
        return df
    
    def add_strategy(self, strategy: StrategyBase) -> None:
        self.strategies.append(strategy)
    
    def remove_strategy(self, name: str) -> None:
        self.strategies = [s for s in self.strategies if s.name != name]
    
    def get_strategy_names(self) -> List[str]:
        return [s.name for s in self.strategies]