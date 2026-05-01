"""Indicator Composer for combining multiple indicators."""

import pandas as pd
from typing import List

from quantflow.indicators.base import IndicatorBase


class IndicatorComposer:
    
    def __init__(self, indicators: List[IndicatorBase]):
        self.indicators = indicators
    
    def compose(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply indicators sequentially. 
        
        Note: Execution follows the exact order of the indicator list. If any 
        indicator relies on the output of a previous one, ensure correct ordering.
        """
        df = df.copy()
        
        available_fields = set(df.columns)
        
        for indicator in self.indicators:
            required = indicator.get_required_fields()
            
            missing = set(required) - available_fields
            if missing:
                raise ValueError(
                    f"Indicator {indicator.name} requires fields {missing} "
                    f"but they are not available. Available: {available_fields}"
                )
            
            df = indicator.calculate(df)
            
            output_fields = indicator.get_output_fields()
            available_fields.update(output_fields)
        
        return df
    
    def get_all_signal_columns(self) -> List[str]:
        columns = []
        for indicator in self.indicators:
            signal_col = f"{indicator.name}_signal"
            columns.append(signal_col)
        return columns
    
    def add_indicator(self, indicator: IndicatorBase) -> None:
        self.indicators.append(indicator)
    
    def remove_indicator(self, name: str) -> None:
        self.indicators = [i for i in self.indicators if i.name != name]
    
    def get_indicator_names(self) -> List[str]:
        return [i.name for i in self.indicators]