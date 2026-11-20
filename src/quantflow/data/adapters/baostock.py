"""BaoStock data source adapter for A-share stocks."""

import pandas as pd
import logging
from typing import Optional
from functools import wraps
import time

from quantflow.data.base import DataSourceBase, StockCode
from quantflow.data.quality import daily_sessions
from quantflow.control import check_cancelled, cancellable_sleep

logger = logging.getLogger(__name__)


def _bound_socket_io():
    """Bound only BaoStock's socket factory, not the process-wide socket defaults."""
    import baostock.util.socketutil as transport
    if getattr(transport, "_quantflow_bounded", False):
        return
    original = transport.socket

    class CheckedSocket:
        def __init__(self, *args, **kwargs):
            self.socket = original.socket(*args, **kwargs)
            self.socket.settimeout(30)
            self.connected = False

        def __getattr__(self, name):
            return getattr(self.socket, name)

        def connect(self, *args):
            check_cancelled()
            result = self.socket.connect(*args)
            self.connected = True
            return result

        def send(self, *args):
            check_cancelled()
            if not self.connected:
                raise ConnectionError("BaoStock connection was not established")
            return self.socket.send(*args)

        def recv(self, *args):
            check_cancelled()
            data = self.socket.recv(*args)
            if not data:
                raise ConnectionError("BaoStock socket closed before a complete response")
            return data

    class SocketProxy:
        socket = CheckedSocket

        def __getattr__(self, name):
            return getattr(original, name)

    transport.socket = SocketProxy()
    transport._quantflow_bounded = True


def retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            current_delay = delay
            last_exception = None
            
            while retries < max_retries:
                check_cancelled()
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    retries += 1
                    if retries < max_retries:
                        logger.warning(f"Retry {retries}/{max_retries}: {e}")
                        cancellable_sleep(current_delay)
                        current_delay *= backoff
            
            raise last_exception
        return wrapper
    return decorator


class BaoStockDataSource(DataSourceBase):
    
    ADJUST_MAP = {"qfq": "2", "hfq": "1", "none": "3"}
    PERIOD_MAP = {"d": "d", "w": "w", "m": "m", "y": "y"}
    DEFAULT_FIELDS = ["date", "code", "open", "high", "low", "close", "volume", "amount"]
    
    def __init__(self, adjust: str = "qfq"):
        self.adjust = adjust
        self._bs = None
        self._logged_in = False
        self._listing_dates = {}
    
    def get_name(self) -> str:
        return "BaoStock"
    
    def supports_market(self, market: str) -> bool:
        return market in ["cn", "A股", "a"]

    def get_supported_periods(self):
        return ["d", "w", "m"]
    
    def _login(self):
        if self._logged_in:
            return
        
        import baostock as bs
        _bound_socket_io()
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
    
    def _listing_date(self, code):
        if code in self._listing_dates:
            return self._listing_dates[code]
        check_cancelled()
        reply = self._bs.query_stock_basic(code=code)
        check_cancelled()
        if reply.error_code != "0" or not reply.next():
            return None
        raw = dict(zip(reply.fields, reply.get_row_data())).get("ipoDate")
        date = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
        if pd.isna(date):
            return None
        listing = date.strftime("%Y-%m-%d")
        self._listing_dates[code] = listing
        return listing

    @retry(max_retries=3)
    def fetch_ohlcv(
        self,
        code: StockCode,
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> pd.DataFrame:
        if period not in self.get_supported_periods():
            raise ValueError(f"Unsupported BaoStock period: {period}")
        
        actual_adjust = adjust or self.adjust
        if actual_adjust not in self.ADJUST_MAP:
            raise ValueError(f"Invalid adjust: {actual_adjust}")
        check_cancelled()
        self._login()
        
        adjustflag = self.ADJUST_MAP[actual_adjust]
        frequency = self.PERIOD_MAP.get(period, "d")
        
        bs_code = code.baostock
        # BaoStock requires YYYY-MM-DD format (not YYYYMMDD)
        start = start_date
        end = end_date
        
        fields = ",".join(self.DEFAULT_FIELDS + (["tradestatus"] if period == "d" else []))
        
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
            check_cancelled()
            data.append(rs.get_row_data())
        if rs.error_code != "0":
            raise RuntimeError(f"BaoStock page fetch failed: {rs.error_msg}")
        
        if not data:
            logger.warning(f"No data for {code.standard}")
            return pd.DataFrame()
        
        df = pd.DataFrame(data, columns=rs.fields)
        
        df["date"] = pd.to_datetime(df["date"])
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        
        df = df.sort_values("date").reset_index(drop=True)

        if actual_adjust == "qfq":
            check_cancelled()
            last_date = df["date"].iloc[-1].strftime("%Y-%m-%d")
            raw = self._bs.query_history_k_data_plus(
                bs_code, "date,close", start_date=last_date, end_date=last_date,
                frequency=frequency, adjustflag=self.ADJUST_MAP["none"])
            if raw.error_code != "0" or not raw.next():
                raise ValueError("Cannot anchor BaoStock qfq to the requested last session")
            raw_close = float(raw.get_row_data()[1])
            ratio = raw_close / df["close"].iloc[-1]
            if not pd.notna(ratio) or ratio <= 0:
                raise ValueError("Invalid BaoStock adjustment anchor")
            df[["open", "high", "low", "close"]] *= ratio

        df.attrs.update(source="baostock", adjust=actual_adjust, volume_unit="shares",
                        adjustment_anchor=df["date"].iloc[-1].strftime("%Y-%m-%d"))
        
        columns = ["date", "open", "high", "low", "close", "volume"]
        if "tradestatus" in df.columns:
            df = df.rename(columns={"tradestatus": "trade_status"})
            columns.append("trade_status")
            df.attrs["trading_status_source"] = "baostock:tradestatus"
            planned = daily_sessions(code, start, df.date.iloc[0])
            if len(planned) and planned[0] < df.date.iloc[0]:
                try:
                    listing = self._listing_date(bs_code)
                except (OSError, RuntimeError, ValueError) as exc:
                    logger.warning("Could not verify listing date for %s: %s", code.standard, exc)
                else:
                    if listing:
                        df.attrs.update(
                            listing_date=listing,
                            listing_date_source="baostock:query_stock_basic",
                            query_start=start,
                        )
        return df[columns]
