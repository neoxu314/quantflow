"""YFinance data source adapter for global markets.

Data Differences Notes:
- 韩股数据可能与本地数据源有约1-2%差异, 建议放宽容差至5%
- 美股数据通常与本地数据源一致
- 基本面数据（pb/total_mv）港股可能存在差异

Comparison Notes (vs 富途牛牛, 2026-04-24):
- pe_ttm: 正常值差异合理（0.2%-1.7%），亏损返回None
- pb: 港股差异较大（-10.8%~-4.5%），美股准确（-1.3%）
- total_mv: 美股完全一致，港股差异较大（-22.7%）

Rate Limit Notes:
- Yahoo Finance 有严格的反爬虫机制 (60 req/min, 360 req/hour, 8000 req/day)
- 中国地区访问可能被额外限制, 建议使用VPN
- 本adapter使用curl_cffi模拟Chrome TLS指纹以绕过反爬虫检测
"""

import pandas as pd
import logging
from typing import Optional

from quantflow.data.base import DataSourceBase, StockCode, FundamentalData

logger = logging.getLogger(__name__)


def _get_chrome_session():
    """Create a session that impersonates Chrome browser to avoid rate limits.
    
    Yahoo Finance rejects standard requests library calls.
    Using curl_cffi with Chrome impersonation bypasses this restriction.
    """
    try:
        from curl_cffi import Session
        session = Session(impersonate="chrome")
        return session
    except ImportError:
        logger.warning("curl_cffi not installed, using default session (may hit rate limits)")
        return None


class YFinanceDataSource(DataSourceBase):
    
    MARKET_SUFFIX = {
        "HK": ".HK",
        "T": ".T",
        "KS": ".KS",
        "US": "",
    }
    
    PERIOD_INTERVAL = {"d": "1d", "w": "1wk", "m": "1mo"}
    
    _session = None
    
    def __init__(self):
        if YFinanceDataSource._session is None:
            YFinanceDataSource._session = _get_chrome_session()
    
    def get_name(self) -> str:
        return "YFinance"
    
    def supports_market(self, market: str) -> bool:
        return market in ["us", "hk", "jp", "kr", "美股", "港股", "日本", "韩国"]
    
    def _get_yfinance_symbol(self, code: StockCode) -> str:
        if code.exchange == "US":
            return code.code
        
        suffix = self.MARKET_SUFFIX.get(code.exchange, "")
        
        # 港股代码: 去掉前导零后保留4位数字
        # 09660 -> 9660.HK, 00700 -> 0700.HK
        if code.exchange == "HK":
            stripped_code = code.code.lstrip("0")
            if len(stripped_code) < 4:
                stripped_code = "0" + stripped_code
            return f"{stripped_code}{suffix}"
        
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
        
        ticker = yf.Ticker(symbol, session=self._session)
        
        interval = self.PERIOD_INTERVAL.get(period, "1d")
        
        df = ticker.history(start=start_date, end=end_date, interval=interval)
        
        if df.empty:
            logger.warning(f"No data for {symbol}")
            return pd.DataFrame()
        
        start = pd.to_datetime(start_date).tz_localize(df.index.tz)
        end = pd.to_datetime(end_date).tz_localize(df.index.tz)
        df = df.loc[start:end]
        
        df = df.reset_index()
        df = df.rename(columns={
            "Date": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })
        
        cols = ["date", "open", "high", "low", "close", "volume"]
        df = df[[c for c in cols if c in df.columns]]
        
        return df.reset_index(drop=True)
    
    def fetch_fundamental(self, code: StockCode) -> Optional[FundamentalData]:
        import yfinance as yf
        
        symbol = self._get_yfinance_symbol(code)
        
        try:
            ticker = yf.Ticker(symbol, session=self._session)
            info = ticker.info
            
            return FundamentalData(
                pe_ttm=info.get("trailingPE"),
                pb=info.get("priceToBook"),
                total_mv=info.get("marketCap"),
            )
        except Exception as e:
            logger.warning(f"Failed to fetch fundamental for {symbol}: {e}")
            return None