import math
import pytest
from unittest.mock import patch

from quantflow.indicators.custom.dual_line import DualLineIndicator
from quantflow.indicators.standard.kdj import KDJIndicator
from quantflow.config.lookback import compute_days_back


class TestComputeDaysBack:

    def _make_strategy(self, indicators):
        class _S:
            @staticmethod
            def get_lookback_bars():
                inds = indicators
                if not inds:
                    return 1
                return max(i.lookback_bars for i in inds)
        return _S()

    def test_single_strategy_dual_line(self):
        strategy = self._make_strategy([DualLineIndicator()])
        result = _compute_days_back([strategy], None)
        assert result == math.ceil(114 * 2.0) + 30

    def test_multiple_strategies_takes_max(self):
        s_kdj = self._make_strategy([KDJIndicator()])
        s_dual = self._make_strategy([DualLineIndicator()])
        result = _compute_days_back([s_kdj, s_dual], None)
        assert result == math.ceil(114 * 2.0) + 30

    def test_override_takes_precedence(self):
        strategy = self._make_strategy([DualLineIndicator()])
        result = _compute_days_back([strategy], override=500)
        assert result == 500

    def test_empty_strategies_fallback(self):
        result = _compute_days_back([], None)
        assert result == 365
