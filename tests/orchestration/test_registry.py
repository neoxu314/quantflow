"""Tests for the orchestration strategy registry."""
import pytest

from quantflow.orchestration.registry import STRATEGY_REGISTRY, get_strategy_class
from quantflow.strategies.base import StrategyBase
from quantflow.strategies.buy import (
    DailyBullishMidRangeBuy,
    DailyBullishOversoldBuy,
)
from quantflow.strategies.sell import DualLineBearZoneSell, KDJDeadCrossSell


class TestStrategyRegistry:
    """Verify STRATEGY_REGISTRY contents."""

    def test_registry_has_4_strategies(self):
        """All four production strategies are registered."""
        assert len(STRATEGY_REGISTRY) == 4

    def test_registered_ids(self):
        """Expected strategy IDs exist."""
        expected = {
            "daily_bull_mid_range",
            "daily_bull_oversold",
            "kdj_dead_cross",
            "dual_line_bear",
        }
        assert set(STRATEGY_REGISTRY.keys()) == expected

    def test_all_values_are_strategy_subclasses(self):
        """Every registered class inherits from StrategyBase."""
        for name, cls in STRATEGY_REGISTRY.items():
            assert issubclass(cls, StrategyBase), (
                f"{name} is not a StrategyBase subclass"
            )


class TestGetStrategyClass:
    """Verify get_strategy_class() lookup behavior."""

    @pytest.mark.parametrize(
        "strategy_id, expected_cls",
        [
            ("daily_bull_mid_range", DailyBullishMidRangeBuy),
            ("daily_bull_oversold", DailyBullishOversoldBuy),
            ("kdj_dead_cross", KDJDeadCrossSell),
            ("dual_line_bear", DualLineBearZoneSell),
        ],
    )
    def test_known_strategy_returns_class(self, strategy_id, expected_cls):
        """Known IDs return the correct class."""
        assert get_strategy_class(strategy_id) is expected_cls

    @pytest.mark.parametrize("invalid_name", [
        "nonexistent", "", "DAILY_BULL_OVERSOLD",
        "daily_bull", "oversold",
    ])
    def test_unknown_strategy_raises(self, invalid_name):
        """Invalid IDs raise ValueError."""
        with pytest.raises(ValueError, match="Unknown strategy"):
            get_strategy_class(invalid_name)

    def test_error_message_lists_valid_ids(self):
        """ValueError message includes all valid strategy IDs."""
        with pytest.raises(ValueError) as exc_info:
            get_strategy_class("fake")
        error_msg = str(exc_info.value)
        assert "daily_bull_mid_range" in error_msg
        assert "daily_bull_oversold" in error_msg
