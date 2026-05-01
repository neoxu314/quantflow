"""Base classes for trading strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
import pandas as pd

from quantflow.indicators.base import IndicatorBase, Condition


@dataclass
class SignalOutput:
    buy_signal: bool = False
    sell_signal: bool = False
    signal_strength: float = 0.0
    signal_reason: str = ""
    
    def to_dict(self) -> dict:
        return {
            "buy_signal": self.buy_signal,
            "sell_signal": self.sell_signal,
            "signal_strength": self.signal_strength,
            "signal_reason": self.signal_reason,
        }


class StrategyBase(ABC):
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def signal_type(self) -> str:
        pass
    
    @abstractmethod
    def get_conditions(self) -> List[Condition]:
        pass
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        pass
    
    def get_required_indicators(self) -> List[IndicatorBase]:
        return []
    
    def get_lookback_bars(self) -> int:
        indicators = self.get_required_indicators()
        if not indicators:
            return 1
        return max(ind.lookback_bars for ind in indicators)
    
    def get_required_period(self) -> str:
        indicators = self.get_required_indicators()
        if not indicators:
            return "d"
        periods = [ind.required_period for ind in indicators]
        return "w" if "w" in periods else "d"
    
    def get_required_fields(self) -> List[str]:
        conditions = self.get_conditions()
        fields = set()
        for cond in conditions:
            fields.add(cond.field)
            if isinstance(cond.value, str):
                fields.add(cond.value)
        return list(fields)
    
    def validate_input(self, df: pd.DataFrame) -> bool:
        required = self.get_required_fields()
        return all(field in df.columns for field in required)
    
    def evaluate_row(self, df: pd.DataFrame, row_idx: int) -> SignalOutput:
        conditions = self.get_conditions()
        
        if not conditions:
            return SignalOutput()
        
        all_met = all(cond.evaluate(df, row_idx) for cond in conditions)
        
        if all_met:
            reason = f"{self.name}: {len(conditions)} conditions met"
            return SignalOutput(
                buy_signal=self.signal_type == "buy",
                sell_signal=self.signal_type == "sell",
                signal_strength=1.0,
                signal_reason=reason,
            )
        
        return SignalOutput()


class BuyStrategy(StrategyBase):
    
    @property
    def signal_type(self) -> str:
        return "buy"


class SellStrategy(StrategyBase):
    
    @property
    def signal_type(self) -> str:
        return "sell"