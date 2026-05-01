"""Tushare data source adapter for A-share stocks.

Data Differences Notes:
- 复权方式差异: Tushare使用动态复权, BaoStock使用静态复权, 价格可能有较大差异
- 单位差异: Tushare成交量单位为"手"(100股), BaoStock单位为"股"
- 除权除息日附近差异更明显, 如比亚迪2025-07-29除权后价格差异约3倍
"""

import pandas as pd
import logging
import os
from typing import Optional

from quantflow.data.base import DataSourceBase, StockCode, FundamentalData

logger = logging.getLogger(__name__)


class TushareDataSource(DataSourceBase):
    
    PERIOD_MAP = {"d": "D", "w": "W", "m": "M", "y": "Y"}
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("TUSHARE_TOKEN", "")
        self._pro = None
    
    def get_name(self) -> str:
        return "Tushare"
    
    def supports_market(self, market: str) -> bool:
        return market in ["cn", "A股", "a"]
    
    def _init_pro(self):
        if self._pro is not None:
            return
        
        if not self.token:
            raise ValueError(
                "Tushare token required.\n"
                "Options:\n"
                "  1. Set environment variable: export TUSHARE_TOKEN='your_token'\n"
                "  2. Use .env file: cp .env.example .env (then edit)\n"
                "  3. Pass token directly: TushareDataSource(token='...')\n"
                "Get token from: https://tushare.pro/user/token"
            )
        
        import tushare as ts
        ts.set_token(self.token)
        self._pro = ts.pro_api()
        logger.info("Tushare initialized")
    
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> pd.DataFrame:
        self._init_pro()
        
        ts_code = code.standard
        freq = self.PERIOD_MAP.get(period, "D")
        
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        
        logger.info(f"Fetching {period} data for {code.standard} via Tushare")
        
        df = self._pro.daily(
            ts_code=ts_code,
            start_date=start,
            end_date=end,
            adj=adjust or "qfq"
        )
        
        if df is None or df.empty:
            logger.warning(f"No data for {code.standard}")
            return pd.DataFrame()
        
        df = df.rename(columns={"trade_date": "date", "vol": "volume"})
        
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        df = df.sort_values("date").reset_index(drop=True)
        
        return df[["date", "open", "high", "low", "close", "volume"]]
    
    def fetch_fundamental(self, code: StockCode) -> Optional[FundamentalData]:
        self._init_pro()
        
        ts_code = code.standard
        
        try:
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