"""YFinance data source adapter for global markets."""

import time
import pandas as pd
import logging
from typing import Optional, List, Dict

from quantflow.data.base import DataSourceBase, StockCode, FundamentalData

logger = logging.getLogger(__name__)


def _get_chrome_session():
    try:
        from curl_cffi import Session
        return Session(impersonate="chrome")
    except ImportError:
        logger.warning("curl_cffi not installed, using default session")
        return None


def _unstack_ticker(raw_df: pd.DataFrame, col_map: Dict[str, str]) -> pd.DataFrame:
    if raw_df.empty:
        return raw_df
    df = raw_df.reset_index()
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    cols = ["date", "open", "high", "low", "close", "volume"]
    df = df[[c for c in cols if c in df.columns]]
    return df.reset_index(drop=True)


class YFinanceDataSource(DataSourceBase):

    MARKET_SUFFIX = {
        "HK": ".HK",
        "T": ".T",
        "KS": ".KS",
        "US": "",
    }

    PERIOD_INTERVAL = {"d": "1d", "w": "1wk", "m": "1mo"}
    _COL_MAP = {
        "Date": "date", "Datetime": "date",
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    }

    _session = None

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        sleep_between_chunks: Optional[int] = None,
    ):
        if YFinanceDataSource._session is None:
            YFinanceDataSource._session = _get_chrome_session()
        self._chunk_size = chunk_size or 30
        self._sleep_between_chunks = sleep_between_chunks or 15

    def get_name(self) -> str:
        return "YFinance"

    def supports_market(self, market: str) -> bool:
        return market in ["us", "hk", "jp", "kr", "美股", "港股", "日本", "韩国"]

    def _get_yfinance_symbol(self, code: StockCode) -> str:
        if code.exchange == "US":
            return code.code

        suffix = self.MARKET_SUFFIX.get(code.exchange, "")

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
        df = ticker.history(start=start_date, end=end_date, interval=interval)

        if df.empty:
            logger.warning(f"No data for {symbol}")
            return pd.DataFrame()

        start = pd.to_datetime(start_date).tz_localize(df.index.tz)
        end = pd.to_datetime(end_date).tz_localize(df.index.tz)
        df = df.loc[start:end]

        return _unstack_ticker(df, self._COL_MAP)

    @staticmethod
    def check_version() -> bool:
        try:
            import yfinance as yf
            version = tuple(int(x) for x in yf.__version__.split(".")[:3])
            return version >= (0, 2, 30)
        except Exception:
            return False

    def _download_chunk(
        self, yf_symbols: List[str], start_date: str, end_date: str, interval: str
    ) -> Dict[str, pd.DataFrame]:
        import yfinance as yf

        try:
            df_multi = yf.download(
                tickers=yf_symbols,
                start=start_date,
                end=end_date,
                interval=interval,
                group_by="ticker",
                threads=True,
                session=self._session,
                progress=False,
                timeout=30,
            )
        except Exception as e:
            logger.error(f"Chunk download failed: {e}")
            return {}

        if df_multi is None or df_multi.empty:
            return {}

        chunk_results: Dict[str, pd.DataFrame] = {}
        for yf_sym in yf_symbols:
            try:
                raw = df_multi[yf_sym]
            except KeyError:
                continue
            if raw.empty:
                continue
            single = _unstack_ticker(raw, self._COL_MAP)
            if single.empty:
                continue
            chunk_results[yf_sym] = single
        return chunk_results

    def fetch_batch_ohlcv(
        self,
        codes: List["StockCode"],
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        if not self.check_version():
            raise RuntimeError(
                "Batch OHLCV fetch requires yfinance >= 0.2.30."
            )

        if not codes:
            return {}

        interval = self.PERIOD_INTERVAL.get(period, "1d")

        symbol_to_code: Dict[str, str] = {}
        yf_symbols: List[str] = []
        for code_obj in codes:
            yf_sym = self._get_yfinance_symbol(code_obj)
            symbol_to_code[yf_sym] = code_obj.standard
            yf_symbols.append(yf_sym)

        total = len(yf_symbols)
        chunk_size = min(self._chunk_size, total)

        logger.info(
            f"Batch fetching {total} tickers (chunk_size={chunk_size}, "
            f"sleep={self._sleep_between_chunks}s): "
            f"{', '.join(yf_symbols[:3])}{'...' if total > 3 else ''}"
        )

        all_results: Dict[str, pd.DataFrame] = {}
        num_chunks = (total + chunk_size - 1) // chunk_size

        for i in range(0, total, chunk_size):
            batch = yf_symbols[i:i + chunk_size]
            chunk_num = (i // chunk_size) + 1

            logger.info(f"  Chunk {chunk_num}/{num_chunks} ({len(batch)} tickers)")
            chunk_result = self._download_chunk(batch, start_date, end_date, interval)

            for yf_sym, df in chunk_result.items():
                all_results[symbol_to_code[yf_sym]] = df

            if i + chunk_size < total:
                logger.info(f"  Sleeping {self._sleep_between_chunks}s between chunks...")
                time.sleep(self._sleep_between_chunks)

        logger.info(
            f"Batch complete: {len(all_results)}/{total} tickers with data"
        )
        return all_results

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
