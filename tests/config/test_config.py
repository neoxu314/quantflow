"""Tests for quantflow.config package - ConfigLoader and lookback functions.

Covers:
- config/loader.py: ConfigLoader (load, get_data_config, get_tushare_token, get_yfinance_config)
- config/lookback.py: load_lookback_config(), compute_days_back()
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from quantflow.config.loader import ConfigLoader
from quantflow.config.lookback import load_lookback_config, compute_days_back
from quantflow.data.config import MarketDataSourceConfig

# ─── ConfigLoader Fixtures ─────────────────────────────────────────────

@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    """Create a temporary directory, return path for a new YAML file."""
    return tmp_path / "test_config.yaml"


def _write_yaml(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, sort_keys=False, default_flow_style=False)
    return path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ─── Sanity: production config is parseable ────────────────────────────

class TestProductionConfigSanity:
    def test_quantflow_yaml_parsable(self):
        path = PROJECT_ROOT / "config" / "quantflow.yaml"
        assert path.exists(), f"config/quantflow.yaml not found at {path}"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "data" in data
        assert "markets" in data["data"]
        assert "lookback" in data
        assert "yfinance" in data


# ─── ConfigLoader.__init__ ─────────────────────────────────────────────

class TestConfigLoaderInit:
    def test_default_config_path(self):
        loader = ConfigLoader()
        assert loader.config_path == ConfigLoader.DEFAULT_CONFIG_PATH

    def test_custom_config_path(self):
        custom = "/custom/path/to/config.yaml"
        loader = ConfigLoader(config_path=custom)
        assert loader.config_path == custom


# ─── ConfigLoader.load() ───────────────────────────────────────────────

class TestConfigLoaderLoad:
    def test_missing_file_returns_defaults(self, config_file: Path):
        """When config file does not exist, load() returns hardcoded defaults."""
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.load()
        assert "data" in result
        assert result["data"]["markets"]["cn"]["primary"] == "baostock"
        assert result["data"]["defaults"]["adjust"] == "qfq"
        assert result["logging"]["level"] == "INFO"

    def test_existing_file_loads_yaml(self, config_file: Path):
        _write_yaml(config_file, {
            "tushare": {"token": "abc123"},
            "yfinance": {"batch": {"chunk_size": 30}},
        })
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.load()
        assert result["tushare"]["token"] == "abc123"
        assert result["yfinance"]["batch"]["chunk_size"] == 30

    def test_empty_yaml_file_returns_empty_dict(self, config_file: Path):
        """A YAML file with no content returns {} from safe_load, which load() returns as {}."""
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("")
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.load()
        assert result == {}

    def test_caching_second_call_returns_same_object(self, config_file: Path):
        """load() caches the result; subsequent calls return the same dict."""
        _write_yaml(config_file, {"tushare": {"token": "initial"}})
        loader = ConfigLoader(config_path=str(config_file))
        first = loader.load()
        # Mutate the cached result to verify caching
        first["tushare"]["token"] = "mutated"
        second = loader.load()
        assert second is first
        assert second["tushare"]["token"] == "mutated"


# ─── ConfigLoader.get_data_config() ────────────────────────────────────

class TestConfigLoaderGetDataConfig:
    def _make_market_config(self) -> dict:
        return {
            "data": {
                "markets": {
                    "cn": {"primary": "baostock", "fallback": "tushare", "fundamental": "tushare"},
                    "us": {"primary": "yfinance", "fundamental": "yfinance"},
                    "hk": {"primary": "yfinance"},
                },
                "defaults": {"adjust": "qfq"},
            }
        }

    def test_full_market_config(self, config_file: Path):
        _write_yaml(config_file, self._make_market_config())
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_data_config()

        assert isinstance(result, MarketDataSourceConfig)
        assert result.get_primary("cn") == "baostock"
        assert result.get_primary("us") == "yfinance"
        assert result.get_fallback("cn") == "tushare"
        assert result.get_fundamental_source("cn") == "tushare"
        assert result.get_fundamental_source("us") == "yfinance"
        # hk has no fallback set
        assert result.get_fallback("hk") is None

    def test_defaults_fallback(self, config_file: Path):
        """Missing file uses ConfigLoader._get_defaults(), which includes market config."""
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_data_config()

        assert isinstance(result, MarketDataSourceConfig)
        assert result.get_primary("cn") == "baostock"
        assert result.get_primary("us") == "yahooquery"
        assert result.get_fallback("cn") == "tushare"

    def test_empty_data_section(self, config_file: Path):
        _write_yaml(config_file, {"data": {}})
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_data_config()

        assert isinstance(result, MarketDataSourceConfig)
        # Empty data section → empty dicts passed to MarketDataSourceConfig
        # get_primary defaults to "yfinance" for unknown markets (not dataclass default_factory)
        assert result.get_primary("cn") == "yfinance"


# ─── ConfigLoader.get_tushare_token() ──────────────────────────────────

class TestConfigLoaderGetTushareToken:
    def test_env_var_takes_priority(self, config_file: Path):
        """Environment variable TUSHARE_TOKEN overrides config file."""
        _write_yaml(config_file, {"tushare": {"token": "yaml-token"}})
        loader = ConfigLoader(config_path=str(config_file))
        with patch.dict(os.environ, {"TUSHARE_TOKEN": "env-token"}):
            result = loader.get_tushare_token()
            assert result == "env-token"

    def test_yaml_fallback_when_no_env(self, config_file: Path, monkeypatch: pytest.MonkeyPatch):
        """When env var is not set, token comes from config file."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        _write_yaml(config_file, {"tushare": {"token": "yaml-token"}})
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_tushare_token()
        assert result == "yaml-token"

    def test_returns_none_when_no_env_no_config(self, config_file: Path, monkeypatch: pytest.MonkeyPatch):
        """No env var and no token in config → None."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        _write_yaml(config_file, {"logging": {"level": "DEBUG"}})
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_tushare_token()
        assert result is None

    def test_returns_none_when_missing_file_no_env(self, config_file: Path, monkeypatch: pytest.MonkeyPatch):
        """No env var and file doesn't exist → None."""
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
        # Don't create the file
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_tushare_token()
        assert result is None


# ─── ConfigLoader.get_yfinance_config() ────────────────────────────────

class TestConfigLoaderGetYfinanceConfig:
    def test_returns_batch_config(self, config_file: Path):
        _write_yaml(config_file, {
            "yfinance": {"batch": {"chunk_size": 30, "sleep_min": 3, "sleep_max": 8}},
        })
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_yfinance_config()
        assert result == {"chunk_size": 30, "sleep_min": 3, "sleep_max": 8}

    def test_returns_empty_dict_when_no_yfinance_section(self, config_file: Path):
        _write_yaml(config_file, {"logging": {"level": "INFO"}})
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_yfinance_config()
        assert result == {}

    def test_returns_empty_dict_when_missing_file(self, config_file: Path):
        loader = ConfigLoader(config_path=str(config_file))
        result = loader.get_yfinance_config()
        assert result == {}


# ─── ConfigLoader._get_defaults() ──────────────────────────────────────

class TestConfigLoaderGetDefaults:
    def test_defaults_structure(self):
        loader = ConfigLoader()
        defaults = loader._get_defaults()

        assert "data" in defaults
        assert "markets" in defaults["data"]
        assert "cn" in defaults["data"]["markets"]
        assert "us" in defaults["data"]["markets"]
        assert "hk" in defaults["data"]["markets"]
        assert defaults["data"]["defaults"]["adjust"] == "qfq"
        assert defaults["logging"]["level"] == "INFO"

    def test_defaults_primary_sources(self):
        loader = ConfigLoader()
        defaults = loader._get_defaults()
        markets = defaults["data"]["markets"]

        assert markets["cn"]["primary"] == "baostock"
        assert markets["us"]["primary"] == "yahooquery"
        assert markets["hk"]["primary"] == "yahooquery"
        assert markets["jp"]["primary"] == "yahooquery"
        assert markets["kr"]["primary"] == "yahooquery"
        assert markets["sector"]["primary"] == "akshare"

    def test_defaults_cn_fallback(self):
        loader = ConfigLoader()
        defaults = loader._get_defaults()
        markets = defaults["data"]["markets"]
        assert markets["cn"]["fallback"] == "tushare"
        assert markets["us"]["fallback"] == "yfinance"
        assert markets["hk"]["fallback"] == "yfinance"
        assert markets["jp"]["fallback"] == "yfinance"
        assert markets["kr"]["fallback"] == "yfinance"
        assert "fallback" not in markets["sector"]  # sector has no fallback
        loader = ConfigLoader()
        defaults = loader._get_defaults()
        assert defaults["data"]["markets"]["cn"]["fallback"] == "tushare"


# ─── load_lookback_config() ───────────────────────────────────────────

class TestLoadLookbackConfig:
    def test_defaults_when_file_missing(self, tmp_path: Path):
        """When config file doesn't exist, returns default values."""
        fake_path = tmp_path / "nonexistent" / "quantflow.yaml"
        with patch("quantflow.config.lookback.CONFIG_PATH", fake_path):
            result = load_lookback_config()
            assert result == {"calendar_multiplier": 2, "buffer_days": 30}

    def test_loads_lookback_section(self, tmp_path: Path):
        """When config file has lookback section, values are merged."""
        fake_path = tmp_path / "config" / "quantflow.yaml"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fake_path, "w") as f:
            yaml.dump({
                "lookback": {"calendar_multiplier": 3, "buffer_days": 50},
                "other": {"key": "value"},
            }, f)
        with patch("quantflow.config.lookback.CONFIG_PATH", fake_path):
            result = load_lookback_config()
            assert result["calendar_multiplier"] == 3
            assert result["buffer_days"] == 50

    def test_missing_lookback_uses_defaults(self, tmp_path: Path):
        """Config file exists but has no lookback key → defaults."""
        fake_path = tmp_path / "config" / "quantflow.yaml"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fake_path, "w") as f:
            yaml.dump({"data": {"markets": {}}}, f)
        with patch("quantflow.config.lookback.CONFIG_PATH", fake_path):
            result = load_lookback_config()
            assert result["calendar_multiplier"] == 2
            assert result["buffer_days"] == 30

    def test_partial_override(self, tmp_path: Path):
        """Only one lookback field overridden, the other keeps default."""
        fake_path = tmp_path / "config" / "quantflow.yaml"
        fake_path.parent.mkdir(parents=True, exist_ok=True)
        with open(fake_path, "w") as f:
            yaml.dump({"lookback": {"buffer_days": 60}}, f)
        with patch("quantflow.config.lookback.CONFIG_PATH", fake_path):
            result = load_lookback_config()
            assert result["calendar_multiplier"] == 2  # default
            assert result["buffer_days"] == 60         # overridden


# ─── compute_days_back() ──────────────────────────────────────────────

class TestComputeDaysBack:
    """Independent tests for compute_days_back(), using mocked config.

    Note: test_orchestration.py also tests this function with real indicator instances.
    These tests use mocks to avoid filesystem dependency on the real config file.
    """

    def _make_strategy(self, lookback_bars: int):
        """Create a mock strategy with a given get_lookback_bars() return."""
        class _Strategy:
            @staticmethod
            def get_lookback_bars():
                return lookback_bars
        return _Strategy()

    def test_override_takes_precedence(self):
        """override parameter bypasses all calculation."""
        result = compute_days_back(
            strategies=[self._make_strategy(100)],
            override=999,
        )
        assert result == 999

    def test_empty_strategies_returns_365(self):
        """Empty list → default 365 days."""
        result = compute_days_back(strategies=[], override=None)
        assert result == 365

    def test_none_strategies_returns_365(self):
        """None → default 365 days."""
        result = compute_days_back(strategies=None, override=None)
        assert result == 365

    def test_single_strategy_formula(self):
        """Formula: ceil(max_bars * multiplier) + buffer"""
        strategy = self._make_strategy(50)
        with patch("quantflow.config.lookback.load_lookback_config") as mock_cfg:
            mock_cfg.return_value = {"calendar_multiplier": 2, "buffer_days": 30}
            result = compute_days_back(strategies=[strategy], override=None)
            assert result == math.ceil(50 * 2) + 30  # = 130

    def test_multiple_strategies_takes_max(self):
        """When multiple strategies, uses max(lookback_bars)."""
        s1 = self._make_strategy(30)
        s2 = self._make_strategy(80)
        s3 = self._make_strategy(50)
        with patch("quantflow.config.lookback.load_lookback_config") as mock_cfg:
            mock_cfg.return_value = {"calendar_multiplier": 2, "buffer_days": 30}
            result = compute_days_back(strategies=[s1, s2, s3], override=None)
            assert result == math.ceil(80 * 2) + 30  # = 190

    def test_custom_multiplier_and_buffer(self):
        """Non-default config values are respected."""
        strategy = self._make_strategy(100)
        with patch("quantflow.config.lookback.load_lookback_config") as mock_cfg:
            mock_cfg.return_value = {"calendar_multiplier": 3, "buffer_days": 45}
            result = compute_days_back(strategies=[strategy], override=None)
            assert result == math.ceil(100 * 3) + 45  # = 345

    def test_formula_with_fractional_result(self):
        """ceil() applies when max_bars * multiplier is not a whole number."""
        strategy = self._make_strategy(25)
        with patch("quantflow.config.lookback.load_lookback_config") as mock_cfg:
            mock_cfg.return_value = {"calendar_multiplier": 2.5, "buffer_days": 10}
            result = compute_days_back(strategies=[strategy], override=None)
            assert result == math.ceil(25 * 2.5) + 10  # = 62.5 → ceil=63 + 10 = 73
