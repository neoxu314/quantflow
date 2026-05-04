"""Data source factory with automatic fallback."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import pandas as pd

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

    ADAPTER_MAP = {
        "baostock": BaoStockDataSource,
        "tushare": TushareDataSource,
        "yfinance": YFinanceDataSource,
        "akshare": AKShareDataSource,
    }

    def __init__(
        self,
        config: Optional[MarketDataSourceConfig] = None,
        tushare_token: Optional[str] = None,
        yfinance_config: Optional[dict] = None,
    ):
        self.config = config or DEFAULT_CONFIG
        self.tushare_token = tushare_token
        self._yfinance = yfinance_config or {}
        self._adapters: Dict[str, DataSourceBase] = {}

    def _get_adapter(self, source_name: str) -> DataSourceBase:
        if source_name in self._adapters:
            return self._adapters[source_name]

        adapter_cls = self.ADAPTER_MAP.get(source_name)
        if not adapter_cls:
            raise ValueError(f"Unknown data source: {source_name}")

        if source_name == "tushare":
            adapter = adapter_cls(token=self.tushare_token)
        elif source_name == "yfinance":
            adapter = adapter_cls(
                chunk_size=self._yfinance.get("chunk_size"),
                sleep_min=self._yfinance.get("sleep_min"),
                sleep_max=self._yfinance.get("sleep_max"),
            )
        else:
            adapter = adapter_cls()

        self._adapters[source_name] = adapter
        return adapter

    def get_source(self, market: str) -> DataSourceBase:
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
    ) -> tuple[pd.DataFrame, Optional[str]]:
        if market is None:
            market = self._detect_market(code)

        primary = self.config.get_primary(market)
        fallback = self.config.get_fallback(market)

        df, source = self._fetch_from_sources(
            code, start_date, end_date, period, adjust, market, primary, fallback)

        today = datetime.now().strftime("%Y-%m-%d")
        if df.empty and end_date == today:
            # Expand range to catch last trading day (180 days covers ~128 trading days,
            # enough for LONG_SHORT_LINE which requires ~114 bars).
            fallback_start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
            if fallback_start < start_date and start_date != today:
                fallback_start = start_date
            df, source = self._fetch_from_sources(
                code, fallback_start, end_date, period, adjust, market, primary, fallback)
            if not df.empty:
                latest_date = self._latest_date(df)
                logger.info(
                    f"Fallback: no data on {end_date}, using latest {latest_date} "
                    f"(range {fallback_start} to {end_date})")

        return df, source

    def _fetch_from_sources(
        self, code, start_date, end_date, period, adjust, market, primary, fallback
    ) -> tuple[pd.DataFrame, Optional[str]]:
        try:
            adapter = self._get_adapter(primary)
            if adapter.supports_market(market):
                df = adapter.fetch_ohlcv(code, start_date, end_date, period, adjust)
                if not df.empty:
                    logger.info(f"Successfully fetched from {primary}")
                    return df, primary
        except Exception as e:
            logger.warning(f"Primary source {primary} failed: {e}")

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

        logger.error(f"All data sources failed for {code.standard}")
        return pd.DataFrame(), None

    @staticmethod
    def _latest_date(df: pd.DataFrame) -> str:
        idx = df.index[-1]
        if hasattr(idx, "strftime"):
            return idx.strftime("%Y-%m-%d")
        return str(idx)

    def fetch_batch_ohlcv(
        self,
        codes: List[StockCode],
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: str = "qfq",
    ) -> Dict[str, tuple[pd.DataFrame, Optional[str]]]:
        if not codes:
            return {}

        yf_codes: List[StockCode] = []
        yf_adapter = self._get_adapter("yfinance")

        for code_obj in codes:
            market = self._detect_market(code_obj)
            primary = self.config.get_primary(market)
            if primary == "yfinance" and yf_adapter.supports_market(market):
                yf_codes.append(code_obj)

        if not yf_codes:
            return {}

        batch_result = yf_adapter.fetch_batch_ohlcv(
            yf_codes, start_date, end_date, period, adjust
        )

        return {code_str: (df, "yfinance") for code_str, df in batch_result.items()}

    def fetch_fundamental(self, code: StockCode, market: Optional[str] = None) -> Optional[FundamentalData]:
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
        return self._get_adapter("akshare")
    
    def _detect_market(self, code: StockCode) -> str:
        if code.exchange in ["SH", "SZ"]:
            return "cn"
        elif code.exchange == "HK":
            return "hk"
        elif code.exchange == "US":
            return "us"
        elif code.exchange == "T":
            return "jp"
        elif code.exchange == "KS":
            return "kr"
        else:
            return "us"