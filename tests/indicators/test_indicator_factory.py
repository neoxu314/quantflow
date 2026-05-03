import pytest
from unittest.mock import patch

from quantflow.indicators.factory import IndicatorFactory


class TestIndicatorFactory:
    """Tests for IndicatorFactory - config reading, creation, merging, errors."""

    def test_create_returns_indicator_instance(self):
        """Factory creates a valid indicator instance."""
        # Use real config load (KDJ is enabled by default in config/indicators.yaml)
        IndicatorFactory._config = None
        IndicatorFactory._class_map.clear()
        ind = IndicatorFactory.create("KDJ")
        assert ind is not None
        assert ind.__class__.__name__ == "KDJIndicator"
        # Validate basic contract from the public API
        assert getattr(ind, "name") == "KDJ"

    def test_create_merges_config_with_defaults(self):
        """Config params override class defaults while keeping others intact."""
        custom_cfg = {"KDJ": {"enabled": True, "params": {"m1": 4}}}
        with patch.object(IndicatorFactory, "_load_config", return_value=custom_cfg):
            IndicatorFactory._config = None
            IndicatorFactory._class_map.clear()
            ind = IndicatorFactory.create("KDJ")
        # m1 should be overridden; other params should stay at defaults
        assert ind.m1 == 4
        assert ind.n == 9  # default
        assert ind.m2 == 3  # default

    def test_create_raises_on_unknown_name(self):
        """ValueError for indicator not in config."""
        with patch.object(IndicatorFactory, "_load_config", return_value={}):
            IndicatorFactory._config = None
            IndicatorFactory._class_map.clear()
            with pytest.raises(ValueError) as exc:
                IndicatorFactory.create("UNKNOWN_INDICATOR")
        assert "not configured" in str(exc.value)

    def test_create_raises_on_disabled_indicator(self):
        """ValueError when enabled=false in config."""
        cfg = {"KDJ": {"enabled": False}}
        with patch.object(IndicatorFactory, "_load_config", return_value=cfg):
            IndicatorFactory._config = None
            IndicatorFactory._class_map.clear()
            with pytest.raises(ValueError) as exc:
                IndicatorFactory.create("KDJ")
        assert "disabled" in str(exc.value)

    def test_create_caches_class_lookup(self):
        """Repeated calls for same name return same class reference."""
        IndicatorFactory._config = None
        IndicatorFactory._class_map.clear()
        cls1 = IndicatorFactory._get_class_by_name("KDJ")
        cls2 = IndicatorFactory._get_class_by_name("KDJ")
        assert cls1 is not None
        assert cls1 is cls2
        assert cls1.__name__ == "KDJIndicator"

    def test_create_all_configured_indicators(self):
        """All 8 indicators in config/indicators.yaml can be created."""
        names_expected = [
            ("KDJ", "KDJIndicator"),
            ("MACD", "MACDIndicator"),
            ("RSI", "RSIIndicator"),
            ("BOLL", "BOLLIndicator"),
            ("VolumeMA", "VolumeMAIndicator"),
            ("DualLine", "DualLineIndicator"),
            ("BrickChart", "BrickChartIndicator"),
            ("Washout", "WashoutIndicator"),
        ]

        IndicatorFactory._config = None
        IndicatorFactory._class_map.clear()
        for name, clsname in names_expected:
            ind = IndicatorFactory.create(name)
            assert ind.__class__.__name__ == clsname

    def test_create_with_custom_config_params(self, tmp_path):
        """Config file overrides are applied to created instances."""
        custom = {"KDJ": {"enabled": True, "params": {"m1": 5, "n": 8}}}
        with patch.object(IndicatorFactory, "_load_config", return_value=custom):
            IndicatorFactory._config = None
            IndicatorFactory._class_map.clear()
            ind = IndicatorFactory.create("KDJ")
        assert ind.m1 == 5
        assert ind.n == 8

    def test_create_indicators_from_real_config(self):
        # Integration test: create all indicators from real config/indicators.yaml.
        # This does NOT patch _load_config - it loads the real file.
        from pathlib import Path
        root = Path(__file__).resolve().parents[2]
        real_config = root / "config" / "indicators.yaml"
        assert real_config.exists(), f"Config file not found: {real_config}"

        # Reset factory cache so it reads the real file
        IndicatorFactory._config = None
        IndicatorFactory._class_map.clear()

        # Create KDJ - this will use the real config path
        ind = IndicatorFactory.create("KDJ")
        assert ind is not None
        assert ind.__class__.__name__ == "KDJIndicator"
