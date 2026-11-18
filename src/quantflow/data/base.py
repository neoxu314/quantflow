# src/quantflow/data/base.py
"""Base types and abstract classes for data layer."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
import re
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
        if not isinstance(code_str, str) or not re.fullmatch(r"[A-Za-z0-9-]{1,15}\.(SH|SZ|HK|US|T|KS|JP|KR)", code_str):
            raise ValueError(f"Invalid standard stock code: {code_str!r}")
        code, exchange = code_str.rsplit(".", 1)
        exchange = {"JP": "T", "KR": "KS"}.get(exchange, exchange)
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
    total_mv: Optional[float] = None    # Base currency units, never 10,000-units
    circ_mv: Optional[float] = None
    forward_pe: Optional[float] = None
    enterprise_value: Optional[float] = None
    code: Optional[str] = None
    currency: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    as_of: Optional[str] = None
    period_end: Optional[str] = None
    published_at: Optional[str] = None
    available_at: Optional[str] = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "partial"
    quality_flags: list = field(default_factory=list)
    units: dict = field(default_factory=lambda: {"total_mv": "currency", "circ_mv": "currency",
                                                "enterprise_value": "currency", "roe": "ratio",
                                                "debt_ratio": "ratio"})

    def __post_init__(self):
        for name in ("pe_ttm", "pb", "ps_ttm", "roe", "debt_ratio", "total_mv", "circ_mv",
                     "forward_pe", "enterprise_value"):
            value = getattr(self, name)
            try:
                value = float(value) if value is not None else None
                if value is not None and not math.isfinite(value):
                    value = None
            except (TypeError, ValueError):
                value = None
            setattr(self, name, value)

    @property
    def missing_fields(self):
        return [n for n in ("pe_ttm", "pb", "ps_ttm", "roe", "debt_ratio", "currency",
                             "period_end", "published_at") if getattr(self, n) is None]

    def to_dict(self):
        return dict(asdict(self), schema_version=1, missing_fields=self.missing_fields)


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
