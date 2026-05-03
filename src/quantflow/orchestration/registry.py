"""Strategy Registry."""
from typing import Dict, Type
from quantflow.strategies.base import StrategyBase
from quantflow.strategies.buy import (
    DailyBullishMidRangeBuy,
    DailyBullishOversoldBuy,
)
from quantflow.strategies.sell import (
    KDJDeadCrossSell,
    DualLineBearZoneSell
)

STRATEGY_REGISTRY: Dict[str, Type[StrategyBase]] = {
    "daily_bull_mid_range": DailyBullishMidRangeBuy,
    "daily_bull_oversold": DailyBullishOversoldBuy,
    "kdj_dead_cross": KDJDeadCrossSell,
    "dual_line_bear": DualLineBearZoneSell,
}

def get_strategy_class(name: str) -> Type[StrategyBase]:
    if name not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown strategy '{name}'. Valid: {list(STRATEGY_REGISTRY.keys())}")
    return STRATEGY_REGISTRY[name]
