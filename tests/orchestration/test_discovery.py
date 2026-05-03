"""Tests for the orchestration discovery module."""
import pytest
from quantflow.orchestration.discovery import discover_indicators


class TestDiscoverIndicators:
    """Tests for discover_indicators() function."""

    def test_returns_list_of_dicts(self):
        """Returns a list where each item is a dict."""
        result = discover_indicators()
        assert isinstance(result, list)
        assert len(result) > 0
        for item in result:
            assert isinstance(item, dict)

    def test_all_items_have_required_keys(self):
        """Each discovered indicator has all required metadata fields."""
        result = discover_indicators()
        required_keys = {"name", "category", "params", "required_fields", "output_fields", "lookback_bars"}
        for item in result:
            missing = required_keys - set(item.keys())
            assert not missing, f"Missing keys: {missing} in {item.get('name')}"

    def test_discovers_standard_indicators(self):
        """Includes standard indicators (KDJ, MACD, RSI, BOLL, VolumeMA)."""
        result = discover_indicators()
        names = [i["name"] for i in result]
        standard_names = {"KDJ", "MACD", "RSI", "BOLL", "VOL_MA"}
        for sn in standard_names:
            assert sn in names, f"Expected standard indicator {sn}"

    def test_discovers_custom_indicators(self):
        """Includes custom indicators (DualLine, BrickChart, Washout)."""
        result = discover_indicators()
        names = [i["name"] for i in result]
        custom_names = {"DualLine", "BrickChart", "Washout"}
        for cn in custom_names:
            assert cn in names, f"Expected custom indicator {cn}"

    def test_category_field_is_correct(self):
        """Standard and custom indicators are tagged correctly."""
        result = discover_indicators()
        standard = [i for i in result if i["category"] == "standard"]
        custom = [i for i in result if i["category"] == "custom"]
        assert len(standard) >= 5, f"Expected at least 5 standard, got {len(standard)}"
        assert len(custom) >= 3, f"Expected at least 3 custom, got {len(custom)}"

    def test_lookback_bars_is_number(self):
        """All discovered indicators have a numeric lookback_bars."""
        result = discover_indicators()
        for item in result:
            assert isinstance(item["lookback_bars"], int), f"lookback_bars not int for {item['name']}"

    def test_total_count(self):
        """Total indicators: 5 standard + 3 custom = 8."""
        result = discover_indicators()
        assert len(result) == 8
