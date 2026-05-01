# Quantflow Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement unified data layer with DataSourceBase abstraction, four adapters (BaoStock/AKShare/Tushare/yfinance), factory pattern with fallback, and market routing.

**Architecture:** Abstract base class defines common interface (`fetch_data`, `get_fundamental`). Concrete adapters implement per-source logic. Factory selects adapter based on market config with automatic fallback.

**Tech Stack:** Python 3.10+, pandas, baostock, akshare, tushare, yfinance

---

## Files Structure

| File | Purpose |
|------|---------|
| `src/quantflow/data/__init__.py` | Package exports |
| `src/quantflow/data/base.py` | DataSourceBase, SectorDataSource, FundamentalData, StockCode |
| `src/quantflow/data/config.py` | MarketDataSourceConfig (market → source mapping) |
| `src/quantflow/data/adapters/__init__.py` | Adapter exports |
| `src/quantflow/data/adapters/baostock.py` | BaoStockDataSource |
| `src/quantflow/data/adapters/akshare.py` | AKShareDataSource (sector + HK) |
| `src/quantflow/data/adapters/tushare.py` | TushareDataSource (A股 + fundamental) |
| `src/quantflow/data/adapters/yfinance.py` | YFinanceDataSource (US/HK/JP/KR) |
| `src/quantflow/data/factory.py` | DataSourceFactory with fallback |
| `tests/data/test_base.py` | Base class tests |
| `tests/data/test_baostock.py` | BaoStock adapter tests |
| `tests/data/test_factory.py` | Factory tests |

---

## Market Configuration

```yaml
# Default market → source mapping
markets:
  cn:
    primary: baostock
    fallback: tushare
    fundamental: tushare  # 基本面数据用 tushare
  hk:
    primary: yfinance
    fallback: akshare
  us:
    primary: yfinance
  jp:
    primary: yfinance
  kr:
    primary: yfinance
  sector:
    primary: akshare  # 板块数据
```

---

## Task 1: Define Base Classes and Types

**Files:**
- Create: `src/quantflow/data/__init__.py`
- Create: `src/quantflow/data/base.py`
- Create: `tests/data/test_base.py`

- [ ] **Step 1: Create package directory**

```bash
mkdir -p src/quantflow/data/adapters tests/data
```

- [ ] **Step 2: Write StockCode and FundamentalData types**

```python
# src/quantflow/data/base.py
from dataclasses import dataclass
from typing import Optional
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
    def from_standard(cls, code_str: str) -> "StockCode":
        """Parse from standard format 600000.SH"""
        code, exchange = code_str.split(".")
        return cls(code=code, exchange=exchange)
    
    @classmethod
    def from_baostock(cls, code_str: str) -> "StockCode":
        """Parse from BaoStock format sh.600000"""
        exchange, code = code_str.split(".")
        exchange_map = {"sh": "SH", "sz": "SZ"}
        return cls(code=code, exchange=exchange_map.get(exchange, exchange.upper()))


@dataclass
class FundamentalData:
    """Unified fundamental data schema."""
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    ps_ttm: Optional[float] = None
    roe: Optional[float] = None
    debt_ratio: Optional[float] = None
    total_mv: Optional[float] = None  # 总市值
    circ_mv: Optional[float] = None   # 流通市值


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
            period: d/w/m/y
            adjust: qfq/hfq/none
        
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
        """Check if this source supports the given market."""
        pass
    
    def fetch_fundamental(self, code: StockCode) -> Optional[FundamentalData]:
        """Fetch fundamental data (optional, default returns None)."""
        return None


class SectorDataSource(ABC):
    """Abstract base for sector/industry data."""
    
    @abstractmethod
    def get_industry_list(self) -> pd.DataFrame:
        """Get all industries with codes and names."""
        pass
    
    @abstractmethod
    def get_industry_constituents(self, industry_code: str) -> list[StockCode]:
        """Get constituent stocks of an industry."""
        pass
    
    @abstractmethod
    def get_concept_list(self) -> pd.DataFrame:
        """Get all concepts with codes and names."""
        pass
    
    @abstractmethod
    def get_concept_constituents(self, concept_code: str) -> list[StockCode]:
        """Get constituent stocks of a concept."""
        pass
```

- [ ] **Step 3: Write tests for base classes**

```python
# tests/data/test_base.py
import pytest
from quantflow.data.base import StockCode, FundamentalData


class TestStockCode:
    def test_standard_format(self):
        code = StockCode(code="600000", exchange="SH", name="浦发银行")
        assert code.standard == "600000.SH"
        assert code.baostock == "sh.600000"
    
    def test_from_standard(self):
        code = StockCode.from_standard("000001.SZ")
        assert code.code == "000001"
        assert code.exchange == "SZ"
    
    def test_from_baostock(self):
        code = StockCode.from_baostock("sh.600000")
        assert code.code == "600000"
        assert code.exchange == "SH"


class TestFundamentalData:
    def test_defaults(self):
        data = FundamentalData()
        assert data.pe_ttm is None
        assert data.pb is None
```

- [ ] **Step 4: Create package init**

```python
# src/quantflow/data/__init__.py
from .base import StockCode, FundamentalData, DataSourceBase, SectorDataSource

__all__ = [
    "StockCode",
    "FundamentalData",
    "DataSourceBase",
    "SectorDataSource",
]
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/data/test_base.py -v
```

Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/quantflow/data/base.py src/quantflow/data/__init__.py tests/data/test_base.py
git commit -m "feat(data): add base types and abstract classes"
```

---

## Task 2: Implement BaoStock Adapter

**Files:**
- Create: `src/quantflow/data/adapters/baostock.py`
- Create: `src/quantflow/data/adapters/__init__.py`
- Create: `tests/data/test_baostock.py`

- [ ] **Step 1: Write BaoStock adapter**

```python
# src/quantflow/data/adapters/baostock.py
import pandas as pd
import logging
from typing import Optional
from functools import wraps
import time

from quantflow.data.base import DataSourceBase, StockCode

logger = logging.getLogger(__name__)


def retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Retry decorator for network operations."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            last_exception = None
            
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    retries += 1
                    if retries < max_retries:
                        logger.warning(f"Retry {retries}/{max_retries}: {e}")
                        time.sleep(current_delay)
                        current_delay *= backoff
            
            raise last_exception
        return wrapper
    return decorator


class BaoStockDataSource(DataSourceBase):
    """BaoStock data source for A-share stocks.
    
    Features:
    - Free, no token required
    - Supports qfq/hfq/none adjustment
    - Daily/weekly/monthly/yearly periods
    """
    
    ADJUST_MAP = {"qfq": "2", "hfq": "1", "none": "3"}
    PERIOD_MAP = {"d": "d", "w": "w", "m": "m", "y": "y"}
    
    DEFAULT_FIELDS = ["date", "code", "open", "high", "low", "close", "volume", "amount"]
    
    def __init__(self, adjust: str = "qfq"):
        self.adjust = adjust
        self._bs = None
        self._logged_in = False
    
    def get_name(self) -> str:
        return "BaoStock"
    
    def supports_market(self, market: str) -> bool:
        return market in ["cn", "A股"]
    
    def _login(self):
        if self._logged_in:
            return
        
        import baostock as bs
        self._bs = bs
        
        lg = bs.login()
        if lg.error_code != "0":
            raise ConnectionError(f"BaoStock login failed: {lg.error_msg}")
        
        self._logged_in = True
        logger.info("BaoStock login successful")
    
    def _logout(self):
        if self._logged_in and self._bs:
            self._bs.logout()
            self._logged_in = False
    
    @retry(max_retries=3)
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> pd.DataFrame:
        self._login()
        
        actual_adjust = adjust or self.adjust
        if actual_adjust not in self.ADJUST_MAP:
            raise ValueError(f"Invalid adjust: {actual_adjust}")
        
        adjustflag = self.ADJUST_MAP[actual_adjust]
        frequency = self.PERIOD_MAP.get(period, "d")
        
        bs_code = code.baostock
        # BaoStock requires YYYY-MM-DD format (not YYYYMMDD)
        start = start_date
        end = end_date
        
        fields = ",".join(self.DEFAULT_FIELDS)
        
        logger.info(f"Fetching {period} data for {code.standard} from {start_date} to {end_date}")
        
        rs = self._bs.query_history_k_data_plus(
            bs_code,
            fields,
            start_date=start,
            end_date=end,
            frequency=frequency,
            adjustflag=adjustflag
        )
        
        if rs.error_code != "0":
            raise RuntimeError(f"BaoStock query failed: {rs.error_msg}")
        
        data = []
        while rs.error_code == "0" and rs.next():
            data.append(rs.get_row_data())
        
        if not data:
            logger.warning(f"No data for {code.standard}")
            return pd.DataFrame()
        
        df = pd.DataFrame(data, columns=rs.fields)
        
        # Convert types
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        df = df.sort_values("date").reset_index(drop=True)
        
        return df[["date", "open", "high", "low", "close", "volume"]]
```

- [ ] **Step 2: Create adapters init**

```python
# src/quantflow/data/adapters/__init__.py
from .baostock import BaoStockDataSource

__all__ = ["BaoStockDataSource"]
```

- [ ] **Step 3: Write adapter tests**

```python
# tests/data/test_baostock.py
import pytest
from datetime import datetime, timedelta
from quantflow.data.base import StockCode
from quantflow.data.adapters.baostock import BaoStockDataSource


@pytest.fixture
def baostock_source():
    return BaoStockDataSource(adjust="qfq")


class TestBaoStockDataSource:
    def test_supports_cn_market(self, baostock_source):
        assert baostock_source.supports_market("cn")
        assert baostock_source.supports_market("A股")
        assert not baostock_source.supports_market("us")
    
    def test_get_name(self, baostock_source):
        assert baostock_source.get_name() == "BaoStock"
    
    @pytest.mark.integration
    def test_fetch_daily_data(self, baostock_source):
        """Integration test - requires network."""
        code = StockCode.from_standard("600000.SH")
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        df = baostock_source.fetch_ohlcv(code, start, end, period="d")
        
        assert not df.empty
        assert "date" in df.columns
        assert "close" in df.columns
        assert len(df) > 0
```

- [ ] **Step 4: Run tests (skip integration)**

```bash
pytest tests/data/test_baostock.py -v -m "not integration"
```

Expected: Basic tests pass

- [ ] **Step 5: Commit**

```bash
git add src/quantflow/data/adapters/baostock.py src/quantflow/data/adapters/__init__.py tests/data/test_baostock.py
git commit -m "feat(data): implement BaoStock adapter"
```

---

## Task 3: Implement Tushare Adapter

**Files:**
- Create: `src/quantflow/data/adapters/tushare.py`
- Modify: `src/quantflow/data/adapters/__init__.py`
- Create: `tests/data/test_tushare.py`

- [ ] **Step 1: Write Tushare adapter**

```python
# src/quantflow/data/adapters/tushare.py
import pandas as pd
import logging
import os
from typing import Optional

from quantflow.data.base import DataSourceBase, StockCode, FundamentalData

logger = logging.getLogger(__name__)


class TushareDataSource(DataSourceBase):
    """Tushare data source for A-share stocks.
    
    Features:
    - Requires token (set via TUSHARE_TOKEN env or constructor)
    - Supports qfq/hfq/none adjustment
    - Provides fundamental data (PE/PB/ROE etc.)
    """
    
    PERIOD_MAP = {"d": "D", "w": "W", "m": "M", "y": "Y"}
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("TUSHARE_TOKEN", "")
        self._pro = None
    
    def get_name(self) -> str:
        return "Tushare"
    
    def supports_market(self, market: str) -> bool:
        return market in ["cn", "A股"]
    
    def _init_pro(self):
        if self._pro is not None:
            return
        
        if not self.token:
            raise ValueError("Tushare token required. Set TUSHARE_TOKEN env or pass token.")
        
        import tushare as ts
        ts.set_token(self.token)
        self._pro = ts.pro_api()
        logger.info("Tushare initialized")
    
    def _convert_code(self, code: StockCode) -> str:
        """Convert StockCode to Tushare format: 600000.SH"""
        return code.standard
    
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> pd.DataFrame:
        self._init_pro()
        
        ts_code = self._convert_code(code)
        freq = self.PERIOD_MAP.get(period, "D")
        
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        
        logger.info(f"Fetching {period} data for {code.standard} via Tushare")
        
        # Use daily API with adj factor
        df = self._pro.daily(
            ts_code=ts_code,
            start_date=start,
            end_date=end,
            adj=adjust or "qfq"
        )
        
        if df is None or df.empty:
            logger.warning(f"No data for {code.standard}")
            return pd.DataFrame()
        
        # Rename columns
        df = df.rename(columns={
            "trade_date": "date",
            "vol": "volume"
        })
        
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        df = df.sort_values("date").reset_index(drop=True)
        
        return df[["date", "open", "high", "low", "close", "volume"]]
    
    def fetch_fundamental(self, code: StockCode) -> Optional[FundamentalData]:
        """Fetch fundamental data from Tushare."""
        self._init_pro()
        
        ts_code = self._convert_code(code)
        
        try:
            # Get daily basic data
            df = self._pro.daily_basic(
                ts_code=ts_code,
                fields="pe_ttm,pb,ps_ttm,total_mv,circ_mv"
            )
            
            if df is None or df.empty:
                return None
            
            latest = df.iloc[-1]
            
            return FundamentalData(
                pe_ttm=float(latest.get("pe_ttm", 0) or 0),
                pb=float(latest.get("pb", 0) or 0),
                ps_ttm=float(latest.get("ps_ttm", 0) or 0),
                total_mv=float(latest.get("total_mv", 0) or 0),
                circ_mv=float(latest.get("circ_mv", 0) or 0)
            )
        except Exception as e:
            logger.warning(f"Failed to fetch fundamental for {code.standard}: {e}")
            return None
```

- [ ] **Step 2: Update adapters init**

```python
# src/quantflow/data/adapters/__init__.py
from .baostock import BaoStockDataSource
from .tushare import TushareDataSource

__all__ = ["BaoStockDataSource", "TushareDataSource"]
```

- [ ] **Step 3: Write tests**

```python
# tests/data/test_tushare.py
import pytest
from quantflow.data.base import StockCode
from quantflow.data.adapters.tushare import TushareDataSource


class TestTushareDataSource:
    def test_supports_cn_market(self):
        source = TushareDataSource(token="test")
        assert source.supports_market("cn")
        assert source.supports_market("A股")
        assert not source.supports_market("us")
    
    def test_get_name(self):
        source = TushareDataSource(token="test")
        assert source.get_name() == "Tushare"
    
    def test_requires_token(self):
        source = TushareDataSource(token="")
        code = StockCode.from_standard("600000.SH")
        
        with pytest.raises(ValueError, match="token required"):
            source.fetch_ohlcv(code, "2024-01-01", "2024-01-31")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/data/test_tushare.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/quantflow/data/adapters/tushare.py tests/data/test_tushare.py
git commit -m "feat(data): implement Tushare adapter with fundamental data"
```

---

## Task 4: Implement YFinance Adapter

**Files:**
- Create: `src/quantflow/data/adapters/yfinance.py`
- Modify: `src/quantflow/data/adapters/__init__.py`
- Create: `tests/data/test_yfinance.py`

- [ ] **Step 1: Write YFinance adapter**

```python
# src/quantflow/data/adapters/yfinance.py
import pandas as pd
import logging
from typing import Optional

from quantflow.data.base import DataSourceBase, StockCode, FundamentalData

logger = logging.getLogger(__name__)


class YFinanceDataSource(DataSourceBase):
    """YFinance data source for US/HK/JP/KR stocks.
    
    Features:
    - Free, no token required
    - Supports global markets
    - Provides some fundamental data
    """
    
    MARKET_SUFFIX = {
        "HK": ".HK",      # 港股: 00700.HK
        "JP": ".T",       # 日本: 7203.T
        "KR": ".KS",      # 韩国: 005930.KS
        "US": "",         # 美股: AAPL (no suffix)
    }
    
    PERIOD_INTERVAL = {
        "d": "1d",
        "w": "1wk",
        "m": "1mo",
    }
    
    def get_name(self) -> str:
        return "YFinance"
    
    def supports_market(self, market: str) -> bool:
        return market in ["us", "hk", "jp", "kr", "美股", "港股", "日本", "韩国"]
    
    def _get_yfinance_symbol(self, code: StockCode) -> str:
        """Convert StockCode to YFinance symbol."""
        if code.exchange == "US":
            return code.code  # AAPL
        
        suffix = self.MARKET_SUFFIX.get(code.exchange, "")
        return f"{code.code}{suffix}"
    
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> pd.DataFrame:
        import yfinance as yf
        
        symbol = self._get_yfinance_symbol(code)
        interval = self.PERIOD_INTERVAL.get(period, "1d")
        
        logger.info(f"Fetching {period} data for {symbol} via YFinance")
        
        ticker = yf.Ticker(symbol)
        
        # Calculate appropriate history period
        if period == "d":
            hist_period = "1y"
        elif period == "w":
            hist_period = "3y"
        elif period == "m":
            hist_period = "5y"
        else:
            hist_period = "max"
        
        df = ticker.history(period=hist_period, interval=interval)
        
        if df.empty:
            logger.warning(f"No data for {symbol}")
            return pd.DataFrame()
        
        # Filter by date range
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        df = df.loc[start:end]
        
        # Rename columns
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })
        
        # Keep only needed columns
        cols = ["date", "open", "high", "low", "close", "volume"]
        df = df[[c for c in cols if c in df.columns]]
        
        return df.reset_index(drop=True)
    
    def fetch_fundamental(self, code: StockCode) -> Optional[FundamentalData]:
        """Fetch fundamental data from YFinance."""
        import yfinance as yf
        
        symbol = self._get_yfinance_symbol(code)
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            return FundamentalData(
                pe_ttm=info.get("trailingPE"),
                pb=info.get("priceToBook"),
                total_mv=info.get("marketCap"),
            )
        except Exception as e:
            logger.warning(f"Failed to fetch fundamental for {symbol}: {e}")
            return None
```

- [ ] **Step 2: Update adapters init**

```python
# src/quantflow/data/adapters/__init__.py
from .baostock import BaoStockDataSource
from .tushare import TushareDataSource
from .yfinance import YFinanceDataSource

__all__ = ["BaoStockDataSource", "TushareDataSource", "YFinanceDataSource"]
```

- [ ] **Step 3: Write tests**

```python
# tests/data/test_yfinance.py
import pytest
from quantflow.data.base import StockCode
from quantflow.data.adapters.yfinance import YFinanceDataSource


@pytest.fixture
def yfinance_source():
    return YFinanceDataSource()


class TestYFinanceDataSource:
    def test_supports_global_markets(self, yfinance_source):
        assert yfinance_source.supports_market("us")
        assert yfinance_source.supports_market("hk")
        assert yfinance_source.supports_market("jp")
        assert yfinance_source.supports_market("kr")
        assert not yfinance_source.supports_market("cn")
    
    def test_get_name(self, yfinance_source):
        assert yfinance_source.get_name() == "YFinance"
    
    def test_symbol_conversion(self, yfinance_source):
        # US stock
        us_code = StockCode(code="AAPL", exchange="US")
        assert yfinance_source._get_yfinance_symbol(us_code) == "AAPL"
        
        # HK stock
        hk_code = StockCode(code="00700", exchange="HK")
        assert yfinance_source._get_yfinance_symbol(hk_code) == "00700.HK"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/data/test_yfinance.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/quantflow/data/adapters/yfinance.py tests/data/test_yfinance.py
git commit -m "feat(data): implement YFinance adapter for global markets"
```

---

## Task 5: Implement AKShare Adapter (Sector + HK)

**Files:**
- Create: `src/quantflow/data/adapters/akshare.py`
- Modify: `src/quantflow/data/adapters/__init__.py`
- Create: `tests/data/test_akshare.py`

- [ ] **Step 1: Write AKShare adapter**

```python
# src/quantflow/data/adapters/akshare.py
import pandas as pd
import logging
from typing import Optional

from quantflow.data.base import DataSourceBase, SectorDataSource, StockCode

logger = logging.getLogger(__name__)


class AKShareDataSource(DataSourceBase, SectorDataSource):
    """AKShare data source.
    
    Features:
    - Free, no token required
    - Sector/industry data (primary use)
    - HK stock data (alternative)
    """
    
    def get_name(self) -> str:
        return "AKShare"
    
    def supports_market(self, market: str) -> bool:
        return market in ["hk", "港股", "sector"]
    
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> pd.DataFrame:
        """Fetch HK stock data."""
        import akshare as ak
        
        if code.exchange != "HK":
            raise ValueError(f"AKShare only supports HK stocks, got {code.exchange}")
        
        logger.info(f"Fetching HK data for {code.code} via AKShare")
        
        try:
            df = ak.stock_hk_daily(symbol=code.code, adjust="qfq")
            
            if df.empty:
                return pd.DataFrame()
            
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date")
            
            # Filter by date range
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            df = df.loc[start:end]
            
            df = df.reset_index()
            df = df.rename(columns={
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume"
            })
            
            return df[["date", "open", "high", "low", "close", "volume"]]
        except Exception as e:
            logger.error(f"AKShare fetch failed: {e}")
            return pd.DataFrame()
    
    # SectorDataSource implementation
    def get_industry_list(self) -> pd.DataFrame:
        """Get SW (申万) industry list."""
        import akshare as ak
        
        try:
            df = ak.stock_board_industry_name_em()
            return df.rename(columns={
                "板块名称": "name",
                "板块代码": "code"
            })
        except Exception as e:
            logger.error(f"Failed to get industry list: {e}")
            return pd.DataFrame()
    
    def get_industry_constituents(self, industry_code: str) -> list[StockCode]:
        """Get stocks in an industry."""
        import akshare as ak
        
        try:
            df = ak.stock_board_industry_cons_em(symbol=industry_code)
            
            codes = []
            for row in df.itertuples():
                # Parse code from 申万格式
                code_str = row.code if hasattr(row, 'code') else row.代码
                if "." in str(code_str):
                    code, exchange = str(code_str).split(".")
                    codes.append(StockCode(code=code, exchange=exchange))
            
            return codes
        except Exception as e:
            logger.error(f"Failed to get industry constituents: {e}")
            return []
    
    def get_concept_list(self) -> pd.DataFrame:
        """Get concept list."""
        import akshare as ak
        
        try:
            df = ak.stock_board_concept_name_em()
            return df.rename(columns={
                "板块名称": "name",
                "板块代码": "code"
            })
        except Exception as e:
            logger.error(f"Failed to get concept list: {e}")
            return pd.DataFrame()
    
    def get_concept_constituents(self, concept_code: str) -> list[StockCode]:
        """Get stocks in a concept."""
        import akshare as ak
        
        try:
            df = ak.stock_board_concept_cons_em(symbol=concept_code)
            
            codes = []
            for row in df.itertuples():
                code_str = row.code if hasattr(row, 'code') else row.代码
                if "." in str(code_str):
                    code, exchange = str(code_str).split(".")
                    codes.append(StockCode(code=code, exchange=exchange))
            
            return codes
        except Exception as e:
            logger.error(f"Failed to get concept constituents: {e}")
            return []
```

- [ ] **Step 2: Update adapters init**

```python
# src/quantflow/data/adapters/__init__.py
from .baostock import BaoStockDataSource
from .tushare import TushareDataSource
from .yfinance import YFinanceDataSource
from .akshare import AKShareDataSource

__all__ = [
    "BaoStockDataSource",
    "TushareDataSource",
    "YFinanceDataSource",
    "AKShareDataSource",
]
```

- [ ] **Step 3: Write tests**

```python
# tests/data/test_akshare.py
import pytest
from quantflow.data.base import StockCode
from quantflow.data.adapters.akshare import AKShareDataSource


@pytest.fixture
def akshare_source():
    return AKShareDataSource()


class TestAKShareDataSource:
    def test_supports_hk_and_sector(self, akshare_source):
        assert akshare_source.supports_market("hk")
        assert akshare_source.supports_market("sector")
        assert not akshare_source.supports_market("cn")
    
    def test_get_name(self, akshare_source):
        assert akshare_source.get_name() == "AKShare"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/data/test_akshare.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/quantflow/data/adapters/akshare.py tests/data/test_akshare.py
git commit -m "feat(data): implement AKShare adapter for HK and sector data"
```

---

## Task 6: Implement Factory with Fallback

**Files:**
- Create: `src/quantflow/data/config.py`
- Create: `src/quantflow/data/factory.py`
- Modify: `src/quantflow/data/__init__.py`
- Create: `tests/data/test_factory.py`

- [ ] **Step 1: Write config class**

```python
# src/quantflow/data/config.py
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
        return self.primary.get(market, "yfinance")
    
    def get_fallback(self, market: str) -> Optional[str]:
        return self.fallback.get(market)
    
    def get_fundamental_source(self, market: str) -> Optional[str]:
        return self.fundamental.get(market)


# Default configuration instance
DEFAULT_CONFIG = MarketDataSourceConfig()
```

- [ ] **Step 2: Write factory**

```python
# src/quantflow/data/factory.py
import logging
from typing import Optional, Dict, Any

from quantflow.data.base import DataSourceBase, SectorDataSource, StockCode, FundamentalData
from quantflow.data.config import MarketDataSourceConfig, DEFAULT_CONFIG
from quantflow.data.adapters import (
    BaoStockDataSource,
    TushareDataSource,
    YFinanceDataSource,
    AKShareDataSource,
)

logger = logging.getLogger(__name__)


class DataSourceFactory:
    """Factory for creating and managing data sources with fallback.
    
    Features:
    - Market-based source selection
    - Automatic fallback on failure
    - Singleton adapters (reuse connections)
    """
    
    ADAPTER_MAP = {
        "baostock": BaoStockDataSource,
        "tushare": TushareDataSource,
        "yfinance": YFinanceDataSource,
        "akshare": AKShareDataSource,
    }
    
    def __init__(
        self,
        config: Optional[MarketDataSourceConfig] = None,
        tushare_token: Optional[str] = None
    ):
        self.config = config or DEFAULT_CONFIG
        self.tushare_token = tushare_token
        self._adapters: Dict[str, DataSourceBase] = {}
    
    def _get_adapter(self, source_name: str) -> DataSourceBase:
        """Get or create adapter instance."""
        if source_name in self._adapters:
            return self._adapters[source_name]
        
        adapter_cls = self.ADAPTER_MAP.get(source_name)
        if not adapter_cls:
            raise ValueError(f"Unknown data source: {source_name}")
        
        # Create adapter with appropriate config
        if source_name == "tushare":
            adapter = adapter_cls(token=self.tushare_token)
        else:
            adapter = adapter_cls()
        
        self._adapters[source_name] = adapter
        return adapter
    
    def get_source(self, market: str) -> DataSourceBase:
        """Get primary data source for market."""
        source_name = self.config.get_primary(market)
        return self._get_adapter(source_name)
    
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: str = "qfq",
        market: Optional[str] = None
    ) -> tuple[Any, Any]:
        """Fetch OHLCV data with automatic fallback.
        
        Args:
            code: StockCode
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            period: d/w/m/y
            adjust: qfq/hfq/none
            market: Market identifier (auto-detected from code if None)
        
        Returns:
            (DataFrame, source_name) - data and which source succeeded
        """
        # Auto-detect market from code
        if market is None:
            market = self._detect_market(code)
        
        primary = self.config.get_primary(market)
        fallback = self.config.get_fallback(market)
        
        # Try primary source
        try:
            adapter = self._get_adapter(primary)
            if adapter.supports_market(market):
                df = adapter.fetch_ohlcv(code, start_date, end_date, period, adjust)
                if not df.empty:
                    logger.info(f"Successfully fetched from {primary}")
                    return df, primary
        except Exception as e:
            logger.warning(f"Primary source {primary} failed: {e}")
        
        # Try fallback source
        if fallback:
            try:
                adapter = self._get_adapter(fallback)
                if adapter.supports_market(market):
                    df = adapter.fetch_ohlcv(code, start_date, end_date, period, adjust)
                    if not df.empty:
                        logger.info(f"Fallback to {fallback} succeeded")
                        return df, fallback
            except Exception as e:
                logger.warning(f"Fallback source {fallback} failed: {e}")
        
        # All sources failed
        logger.error(f"All data sources failed for {code.standard}")
        return pd.DataFrame(), None
    
    def fetch_fundamental(self, code: StockCode, market: Optional[str] = None) -> Optional[FundamentalData]:
        """Fetch fundamental data."""
        if market is None:
            market = self._detect_market(code)
        
        source_name = self.config.get_fundamental_source(market)
        if not source_name:
            return None
        
        try:
            adapter = self._get_adapter(source_name)
            return adapter.fetch_fundamental(code)
        except Exception as e:
            logger.warning(f"Failed to fetch fundamental: {e}")
            return None
    
    def get_sector_source(self) -> SectorDataSource:
        """Get sector data source (AKShare)."""
        return self._get_adapter("akshare")
    
    def _detect_market(self, code: StockCode) -> str:
        """Detect market from StockCode."""
        if code.exchange in ["SH", "SZ"]:
            return "cn"
        elif code.exchange == "HK":
            return "hk"
        elif code.exchange == "US":
            return "us"
        elif code.exchange in ["T"]:  # Tokyo
            return "jp"
        elif code.exchange in ["KS"]:  # Korea
            return "kr"
        else:
            return "us"  # Default to US
```

- [ ] **Step 3: Update package init**

```python
# src/quantflow/data/__init__.py
from .base import StockCode, FundamentalData, DataSourceBase, SectorDataSource
from .config import MarketDataSourceConfig, DEFAULT_CONFIG
from .factory import DataSourceFactory

__all__ = [
    "StockCode",
    "FundamentalData",
    "DataSourceBase",
    "SectorDataSource",
    "MarketDataSourceConfig",
    "DEFAULT_CONFIG",
    "DataSourceFactory",
]
```

- [ ] **Step 4: Write factory tests**

```python
# tests/data/test_factory.py
import pytest
import pandas as pd
from quantflow.data.base import StockCode
from quantflow.data.factory import DataSourceFactory
from quantflow.data.config import MarketDataSourceConfig


@pytest.fixture
def factory():
    return DataSourceFactory()


class TestDataSourceFactory:
    def test_get_source_cn(self, factory):
        source = factory.get_source("cn")
        assert source.get_name() == "BaoStock"
    
    def test_get_source_us(self, factory):
        source = factory.get_source("us")
        assert source.get_name() == "YFinance"
    
    def test_detect_market(self, factory):
        cn_code = StockCode.from_standard("600000.SH")
        assert factory._detect_market(cn_code) == "cn"
        
        hk_code = StockCode(code="00700", exchange="HK")
        assert factory._detect_market(hk_code) == "hk"
        
        us_code = StockCode(code="AAPL", exchange="US")
        assert factory._detect_market(us_code) == "us"
    
    def test_custom_config(self):
        custom_config = MarketDataSourceConfig(
            primary={"cn": "tushare"}
        )
        factory = DataSourceFactory(config=custom_config, tushare_token="test")
        
        source = factory.get_source("cn")
        assert source.get_name() == "Tushare"
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/data/test_factory.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/quantflow/data/config.py src/quantflow/data/factory.py src/quantflow/data/__init__.py tests/data/test_factory.py
git commit -m "feat(data): implement DataSourceFactory with fallback mechanism"
```

---

## Task 7: Update Main Package Init

**Files:**
- Create: `src/quantflow/__init__.py`
- Create: `src/quantflow/py.typed` (marker for type hints)

- [ ] **Step 1: Create main package init**

```python
# src/quantflow/__init__.py
"""Quantflow - Stock Quantitative Analysis System.

Layers:
- data: Unified data layer with multi-source support
- indicators: Technical indicator calculations
- strategies: Trading strategy implementation
- monitoring: Stock monitoring and alerts
"""

__version__ = "0.1.0"

from quantflow.data import DataSourceFactory, StockCode

__all__ = ["DataSourceFactory", "StockCode", "__version__"]
```

- [ ] **Step 2: Create type marker**

```bash
touch src/quantflow/py.typed
```

- [ ] **Step 3: Commit**

```bash
git add src/quantflow/__init__.py src/quantflow/py.typed
git commit -m "feat: initialize quantflow package"
```

---

## Task 8: Create Configuration File

**Files:**
- Create: `config/quantflow.yaml`
- Create: `src/quantflow/config/loader.py`

- [ ] **Step 1: Write config file**

```yaml
# config/quantflow.yaml
# Quantflow Configuration

version: "0.1.0"

# Data layer configuration
data:
  markets:
    cn:
      primary: baostock
      fallback: tushare
      fundamental: tushare
    hk:
      primary: yfinance
      fallback: akshare
    us:
      primary: yfinance
    jp:
      primary: yfinance
    kr:
      primary: yfinance
    sector:
      primary: akshare
  
  defaults:
    adjust: qfq       # Default adjustment type
    period: d         # Default period

# Tushare configuration
tushare:
  token: ""           # Set via TUSHARE_TOKEN env var

# Logging configuration
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

- [ ] **Step 2: Write config loader**

```python
# src/quantflow/config/loader.py
import yaml
from pathlib import Path
from typing import Any, Optional

from quantflow.data.config import MarketDataSourceConfig


class ConfigLoader:
    """Load and parse configuration files."""
    
    DEFAULT_CONFIG_PATH = "config/quantflow.yaml"
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Optional[dict] = None
    
    def load(self) -> dict:
        """Load configuration from file."""
        if self._config is not None:
            return self._config
        
        path = Path(self.config_path)
        if not path.exists():
            # Return defaults if file doesn't exist
            self._config = self._get_defaults()
            return self._config
        
        with open(path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f) or {}
        
        return self._config
    
    def get_data_config(self) -> MarketDataSourceConfig:
        """Get data layer configuration."""
        config = self.load()
        data_config = config.get("data", {})
        markets = data_config.get("markets", {})
        
        primary = {}
        fallback = {}
        fundamental = {}
        
        for market, mc in markets.items():
            if mc.get("primary"):
                primary[market] = mc["primary"]
            if mc.get("fallback"):
                fallback[market] = mc["fallback"]
            if mc.get("fundamental"):
                fundamental[market] = mc["fundamental"]
        
        return MarketDataSourceConfig(
            primary=primary,
            fallback=fallback,
            fundamental=fundamental
        )
    
    def get_tushare_token(self) -> Optional[str]:
        """Get Tushare token from config or env."""
        import os
        
        # First check env var
        token = os.environ.get("TUSHARE_TOKEN")
        if token:
            return token
        
        # Then check config file
        config = self.load()
        return config.get("tushare", {}).get("token")
    
    def _get_defaults(self) -> dict:
        """Return default configuration."""
        return {
            "data": {
                "markets": {
                    "cn": {"primary": "baostock", "fallback": "tushare"},
                    "hk": {"primary": "yfinance"},
                    "us": {"primary": "yfinance"},
                    "jp": {"primary": "yfinance"},
                    "kr": {"primary": "yfinance"},
                    "sector": {"primary": "akshare"},
                },
                "defaults": {"adjust": "qfq", "period": "d"},
            },
            "logging": {"level": "INFO"},
        }
```

- [ ] **Step 3: Create config package**

```python
# src/quantflow/config/__init__.py
from .loader import ConfigLoader

__all__ = ["ConfigLoader"]
```

- [ ] **Step 4: Commit**

```bash
mkdir -p config src/quantflow/config
git add config/quantflow.yaml src/quantflow/config/loader.py src/quantflow/config/__init__.py
git commit -m "feat(config): add configuration system"
```

---

## Self-Review Checklist

1. **Spec coverage**: All requirements covered?
   - [ ] DataSourceBase abstraction ✓
   - [ ] Four adapters (BaoStock/Tushare/AKShare/yfinance) ✓
   - [ ] Factory with fallback ✓
   - [ ] Market routing ✓
   - [ ] Fundamental data ✓
   - [ ] Sector data ✓
   - [ ] StockCode unified format ✓

2. **Placeholder scan**: No TBD/TODO/placeholders ✓

3. **Type consistency**: StockCode.standard/baostock methods used consistently ✓

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-04-21-quantflow-data-layer.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**