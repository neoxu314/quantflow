"""Base classes for technical indicators."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import pandas as pd


@dataclass
class Condition:
    field: str
    operator: str
    value: Any
    
    def evaluate(self, df: pd.DataFrame, row_idx: int) -> bool:
        if self.field not in df.columns:
            return False
        
        current_val = df[self.field].iloc[row_idx]
        
        if self.operator == ">":
            if isinstance(self.value, str) and self.value in df.columns:
                return current_val > df[self.value].iloc[row_idx]
            return current_val > self.value
        elif self.operator == "<":
            if isinstance(self.value, str) and self.value in df.columns:
                return current_val < df[self.value].iloc[row_idx]
            return current_val < self.value
        elif self.operator == ">=":
            if isinstance(self.value, str) and self.value in df.columns:
                return current_val >= df[self.value].iloc[row_idx]
            return current_val >= self.value
        elif self.operator == "<=":
            if isinstance(self.value, str) and self.value in df.columns:
                return current_val <= df[self.value].iloc[row_idx]
            return current_val <= self.value
        elif self.operator == "==":
            return current_val == self.value
        elif self.operator == "cross_up":
            if row_idx == 0:
                return False
            if isinstance(self.value, str) and self.value in df.columns:
                prev_current = df[self.field].iloc[row_idx - 1]
                prev_target = df[self.value].iloc[row_idx - 1]
                return prev_current <= prev_target and current_val > df[self.value].iloc[row_idx]
            return False
        elif self.operator == "cross_down":
            if row_idx == 0:
                return False
            if isinstance(self.value, str) and self.value in df.columns:
                prev_current = df[self.field].iloc[row_idx - 1]
                prev_target = df[self.value].iloc[row_idx - 1]
                return prev_current >= prev_target and current_val < df[self.value].iloc[row_idx]
            return False
        
        return False


class IndicatorBase(ABC):
    
    @property
    @abstractmethod
    def name(self) -> str:
        pass
    
    @property
    @abstractmethod
    def params(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_required_fields(self) -> List[str]:
        pass
    
    @abstractmethod
    def get_output_fields(self) -> List[str]:
        pass
    
    @property
    @abstractmethod
    def lookback_bars(self) -> int:
        """所需最小K线条数（根）"""
        pass
    
    @property
    def required_period(self) -> str:
        """所需周期: 'd' 或 'w'"""
        return "d"
    
    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        pass
    
    def get_signal_conditions(self) -> List[Condition]:
        return []
    
    def validate_input(self, df: pd.DataFrame) -> bool:
        required = self.get_required_fields()
        return all(field in df.columns for field in required)
    
    def get_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        conditions = self.get_signal_conditions()
        signal_name = f"{self.name}_signal"
        df[signal_name] = False
        
        if conditions:
            for i in range(len(df)):
                if all(cond.evaluate(df, i) for cond in conditions):
                    df.loc[df.index[i], signal_name] = True
        
        return df