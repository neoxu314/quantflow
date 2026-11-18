"""Configuration loader."""

from pathlib import Path
from typing import Optional

import yaml

from quantflow.data.config import MarketDataSourceConfig


class ConfigLoader:

    DEFAULT_CONFIG_PATH = str(Path(__file__).resolve().parents[3] / "config/quantflow.yaml")

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Optional[dict] = None

    def load(self) -> dict:
        if self._config is not None:
            return self._config

        path = Path(self.config_path)
        if not path.exists():
            self._config = self._get_defaults()
            return self._config

        with open(path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}

        return self._config

    def get_data_config(self) -> MarketDataSourceConfig:
        config = self.load()
        data_config = config.get("data", {})
        markets = data_config.get("markets", {})

        defaults = MarketDataSourceConfig()
        primary = dict(defaults.primary)
        fallback = dict(defaults.fallback)
        fundamental = dict(defaults.fundamental)

        for market, mc in markets.items():
            if mc.get("primary"):
                primary[market] = mc["primary"]
            if "fallback" in mc:
                fallback[market] = mc["fallback"]
            if "fundamental" in mc:
                fundamental[market] = mc["fundamental"]

        return MarketDataSourceConfig(
            primary=primary,
            fallback=fallback,
            fundamental=fundamental
        )

    def get_adjust(self) -> str:
        adjust = self.load().get("data", {}).get("defaults", {}).get("adjust", "qfq")
        if adjust not in ("qfq", "hfq", "none"):
            raise ValueError(f"Invalid default adjustment: {adjust}")
        return adjust

    def create_data_factory(self):
        from quantflow.data.factory import DataSourceFactory
        return DataSourceFactory(config=self.get_data_config(),
                                 tushare_token=self.get_tushare_token(),
                                 yfinance_config=self.get_yfinance_config(),
                                 yahooquery_config=self.get_yahooquery_config())

    def get_tushare_token(self) -> Optional[str]:
        import os

        token = os.environ.get("TUSHARE_TOKEN")
        if token:
            return token

        config = self.load()
        return config.get("tushare", {}).get("token")

    def get_yfinance_config(self) -> dict:
        config = self.load()
        return config.get("yfinance", {}).get("batch", {})

    def get_yahooquery_config(self) -> dict:
        config = self.load()
        return config.get("yahooquery", {}).get("batch", {})

    def get_logging_config(self) -> dict:
        config = self.load()
        return config.get("logging", {})

    def _get_defaults(self) -> dict:
        return {
            "data": {
                "markets": {
                    "cn": {"primary": "baostock", "fallback": "tushare"},
                    "hk": {"primary": "yahooquery", "fallback": "yfinance"},
                    "us": {"primary": "yahooquery", "fallback": "yfinance"},
                    "jp": {"primary": "yahooquery", "fallback": "yfinance"},
                    "kr": {"primary": "yahooquery", "fallback": "yfinance"},
                    "sector": {"primary": "akshare"},
                },
                "defaults": {"adjust": "qfq"},
            },
            "yahooquery": {
                "batch": {
                    "chunk_size": 100,
                    "sleep_min": 0.5,
                    "sleep_max": 2,
                    "max_workers": 20,
                }
            },
            "logging": {
                "console_level": "INFO",
                "file_enabled": True,
                "file_level": "DEBUG",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        }
