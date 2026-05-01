# src/quantflow/data/config.py
"""Market data source configuration."""

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class MarketDataSourceConfig:
    """Configuration for market-specific data source selection."""
    
    # Market → primary source mapping
    primary: Dict[str, str] = field(default_factory=lambda: {
        "cn": "baostock",
        "hk": "yfinance",
        "us": "yfinance",
        "jp": "yfinance",
        "kr": "yfinance",
        "sector": "akshare",
    })
    
    # Market → fallback source mapping
    fallback: Dict[str, Optional[str]] = field(default_factory=lambda: {
        "cn": "tushare",
        "hk": "akshare",
        "us": None,
        "jp": None,
        "kr": None,
        "sector": None,
    })
    
    # Market → fundamental source (for PE/PB etc.)
    fundamental: Dict[str, str] = field(default_factory=lambda: {
        "cn": "tushare",
        "us": "yfinance",
        "hk": "yfinance",
    })
    
    def get_primary(self, market: str) -> str:
        """Get primary data source for market."""
        return self.primary.get(market, "yfinance")
    
    def get_fallback(self, market: str) -> Optional[str]:
        """Get fallback data source for market."""
        return self.fallback.get(market)
    
    def get_fundamental_source(self, market: str) -> Optional[str]:
        """Get fundamental data source for market."""
        return self.fundamental.get(market)
    
    def set_primary(self, market: str, source: str) -> None:
        """Set primary data source for market."""
        self.primary[market] = source
    
    def set_fallback(self, market: str, source: Optional[str]) -> None:
        """Set fallback data source for market."""
        self.fallback[market] = source


# Default configuration instance
DEFAULT_CONFIG = MarketDataSourceConfig()