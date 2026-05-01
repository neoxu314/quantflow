# src/quantflow/data/base.py
"""Base types and abstract classes for data layer."""

from dataclasses import dataclass
from typing import Optional, List
from abc import ABC, abstractmethod
import pandas as pd


@dataclass
class StockCode:
    """Unified stock code representation.
    
    Internal format: 600000.SH (standard)
    BaoStock format: sh.600000 (converted internally)
    """
    code: str           # 6-digit code: 600000
    exchange: str       # Exchange: SH/SZ/HK/US
    name: Optional[str] = None
    
    @property
    def standard(self) -> str:
        """Return standard format: 600000.SH"""
        return f"{self.code}.{self.exchange}"
    
    @property
    def baostock(self) -> str:
        """Return BaoStock format: sh.600000"""
        exchange_map = {"SH": "sh", "SZ": "sz"}
        return f"{exchange_map.get(self.exchange, self.exchange.lower())}.{self.code}"
    
    @classmethod
    def from_standard(cls, code_str: str, name: Optional[str] = None) -> "StockCode":
        """Parse from standard format 600000.SH"""
        parts = code_str.split(".")
        code = parts[0]
        exchange = parts[1] if len(parts) > 1 else "SH"
        return cls(code=code, exchange=exchange, name=name)
    
    @classmethod
    def from_baostock(cls, code_str: str, name: Optional[str] = None) -> "StockCode":
        """Parse from BaoStock format sh.600000"""
        parts = code_str.split(".")
        exchange = parts[0]
        code = parts[1] if len(parts) > 1 else ""
        exchange_map = {"sh": "SH", "sz": "SZ"}
        return cls(code=code, exchange=exchange_map.get(exchange, exchange.upper()), name=name)
    
    def __str__(self) -> str:
        return self.standard
    
    def __repr__(self) -> str:
        return f"StockCode({self.code}, {self.exchange}, '{self.name or ''}')"


@dataclass
class FundamentalData:
    """Unified fundamental data schema."""
    pe_ttm: Optional[float] = None      # 市盈率TTM
    pb: Optional[float] = None          # 市净率
    ps_ttm: Optional[float] = None      # 市销率TTM
    roe: Optional[float] = None         # ROE
    debt_ratio: Optional[float] = None  # 资产负债率
    total_mv: Optional[float] = None    # 总市值(万元)
    circ_mv: Optional[float] = None     # 流通市值(万元)


class DataSourceBase(ABC):
    """Abstract base class for all data sources."""
    
    @abstractmethod
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: str = "qfq"
    ) -> pd.DataFrame:
        """Fetch OHLCV (K-line) data.
        
        Args:
            code: StockCode object
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            period: d/w/m/y (daily/weekly/monthly/yearly)
            adjust: qfq/hfq/none (前复权/后复权/不复权)
        
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return data source name for logging."""
        pass
    
    @abstractmethod
    def supports_market(self, market: str) -> bool:
        """Check if this source supports the given market.
        
        Args:
            market: Market identifier (cn, hk, us, jp, kr, sector)
        """
        pass
    
    def fetch_fundamental(self, code: StockCode) -> Optional[FundamentalData]:
        """Fetch fundamental data (optional, default returns None).
        
        Override in adapters that support fundamental data.
        """
        return None
    
    def get_supported_periods(self) -> List[str]:
        """Return list of supported periods."""
        return ["d", "w", "m", "y"]
    
    def get_supported_adjusts(self) -> List[str]:
        """Return list of supported adjustment types."""
        return ["qfq", "hfq", "none"]


class SectorDataSource(ABC):
    """Abstract base for sector/industry data."""
    
    @abstractmethod
    def get_industry_list(self) -> pd.DataFrame:
        """Get all industries with codes and names.
        
        Returns:
            DataFrame with columns: code, name
        """
        pass
    
    @abstractmethod
    def get_industry_constituents(self, industry_code: str) -> List[StockCode]:
        """Get constituent stocks of an industry.
        
        Args:
            industry_code: Industry identifier
        
        Returns:
            List of StockCode objects
        """
        pass
    
    @abstractmethod
    def get_concept_list(self) -> pd.DataFrame:
        """Get all concepts with codes and names.
        
        Returns:
            DataFrame with columns: code, name
        """
        pass
    
    @abstractmethod
    def get_concept_constituents(self, concept_code: str) -> List[StockCode]:
        """Get constituent stocks of a concept.
        
        Args:
            concept_code: Concept identifier
        
        Returns:
            List of StockCode objects
        """
        pass