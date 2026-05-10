"""YFinance data source adapter for global markets.

Supported markets:
- US: No suffix (e.g., AAPL)
- HK: .HK suffix (e.g., 09660.HK)
- KR: .KS suffix (e.g., 000660.KS for SK Hynix)
- JP: .T suffix (e.g., 8035.T for Tokyo Electron)

Market suffix mapping handled via MARKET_SUFFIX dictionary:
- KR → .KS (Korean stocks)
- JP → .T (Japanese stocks)
- HK → .HK (Hong Kong stocks)

SSL Note (macOS):
  System Python 3.9 uses LibreSSL 2.8.3, which is incompatible with urllib3 v2.
  This causes intermittent yfinance errors (TypeError, OperationalError) in batch downloads.
  Fix: use Homebrew Python (linked with OpenSSL) in a venv:
    brew install python@3.12
    /opt/homebrew/bin/python3.12 -m venv .venv
    source .venv/bin/activate
    pip install -e .
"""

import logging
import random
import time
from typing import Dict, List, Optional

import pandas as pd

from quantflow.data.base import DataSourceBase, FundamentalData, StockCode

logger = logging.getLogger(__name__)


def _check_ssl_compatibility() -> Optional[str]:
    """
    Check SSL library compatibility with urllib3 v2.
    
    Returns: Warning message if incompatible, None if OK
    """
    import ssl
    
    ssl_version = ssl.OPENSSL_VERSION
    if 'LibreSSL' in ssl_version:
        return (
            f"SSL compatibility issue detected: {ssl_version}. "
            f"urllib3 v2 requires OpenSSL 1.1.1+. "
            f"This may cause 'NoneType object is not subscriptable' and "
            f"'unable to open database file' errors in yfinance batch downloads. "
            f"Fix: use Homebrew Python (linked with OpenSSL) in a venv: "
            f"brew install python@3.12 && "
            f"/opt/homebrew/bin/python3.12 -m venv .venv && "
            f"source .venv/bin/activate && pip install -e ."
        )
    return None


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
        "JP": ".T",
        "KS": ".KS",
        "KR": ".KS",
        "US": "",
    }

    PERIOD_INTERVAL = {"d": "1d", "w": "1wk", "m": "1mo"}
    _COL_MAP = {
        "Date": "date", "Datetime": "date",
        "Open": "open", "High": "high", "Low": "low",
        "Close": "close", "Volume": "volume",
    }

    _session = None
    _ssl_warning_logged = False

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        sleep_min: Optional[float] = None,
        sleep_max: Optional[float] = None,
        retry_max_attempts: Optional[int] = None,
        retry_base_delay: Optional[float] = None,
    ):
        if YFinanceDataSource._session is None:
            YFinanceDataSource._session = _get_chrome_session()
        
        ssl_warning = _check_ssl_compatibility()
        if ssl_warning and not YFinanceDataSource._ssl_warning_logged:
            logger.warning(ssl_warning)
            YFinanceDataSource._ssl_warning_logged = True
        
        self._chunk_size = chunk_size or 50
        self._sleep_min = sleep_min if sleep_min is not None else 5
        self._sleep_max = sleep_max if sleep_max is not None else 12
        self._retry_max_attempts = retry_max_attempts if retry_max_attempts is not None else 3
        self._retry_base_delay = retry_base_delay if retry_base_delay is not None else 30

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

        max_attempts = self._retry_max_attempts
        base_delay = self._retry_base_delay

        df_multi = None
        for attempt in range(1, max_attempts + 1):
            logger.info(f"  Download attempt {attempt}/{max_attempts}: {len(yf_symbols)} tickers")

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
                logger.warning(f"  Exception during download: {type(e).__name__}: {e}")
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(f"  Retry in {delay:.0f}s...")
                    time.sleep(delay)
                continue

            if df_multi is None or df_multi.empty:
                logger.warning(f"  Empty DataFrame returned")
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(f"  Retry in {delay:.0f}s...")
                    time.sleep(delay)
                continue

            success_count = 0
            for sym in yf_symbols:
                try:
                    if sym in df_multi and not df_multi[sym].empty:
                        success_count += 1
                except (KeyError, AttributeError):
                    pass

            success_rate = success_count / len(yf_symbols)

            if success_rate >= 0.5:
                logger.info(f"  Success rate {success_rate:.0%} >= 50% - accepted")
                break
            elif attempt == max_attempts:
                logger.warning(f"  Success rate {success_rate:.0%} < 50% but max attempts reached")
                break
            else:
                logger.warning(f"  Success rate {success_rate:.0%} < 50% - retrying...")
                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(f"  Retry in {delay:.0f}s...")
                time.sleep(delay)

        if df_multi is None or df_multi.empty:
            logger.warning(
                f"Chunk returned empty data after {max_attempts} attempts "
                f"(symbols: {', '.join(yf_symbols[:5])}...)"
            )
            return {}

        chunk_results: Dict[str, pd.DataFrame] = {}
        failed_symbols: List[str] = []

        for yf_sym in yf_symbols:
            try:
                raw = df_multi[yf_sym]
            except KeyError:
                failed_symbols.append(yf_sym)
                logger.warning(f"  Symbol not in response: {yf_sym}")
                continue

            if raw is None or raw.empty:
                failed_symbols.append(yf_sym)
                logger.warning(f"  Empty data for: {yf_sym}")
                continue

            single = _unstack_ticker(raw, self._COL_MAP)
            if single.empty:
                failed_symbols.append(yf_sym)
                logger.warning(f"  Parse failed for: {yf_sym}")
                continue

            chunk_results[yf_sym] = single
            logger.info(f"  ✓ {yf_sym}: {len(single)} rows")

        if failed_symbols:
            logger.warning(
                f"  Failed symbols in chunk ({len(failed_symbols)}/{len(yf_symbols)}): "
                f"{', '.join(failed_symbols[:10])}"
            )

        return chunk_results

    def _jitter_sleep(self) -> float:
        duration = random.uniform(self._sleep_min, self._sleep_max)
        time.sleep(duration)
        return duration

    def _retry_with_backoff(
        self,
        func,
        max_attempts: int,
        base_delay: float,
        error_types: List[type],
        *args,
        **kwargs
    ) -> tuple:
        """
        Retry function with exponential backoff for specific error types.

        Returns: (result, attempts_used, last_error)
        """
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                result = func(*args, **kwargs)
                return (result, attempt, None)
            except Exception as e:
                last_error = e
                is_retryable = any(
                    isinstance(e, etype) or
                    (etype.__name__ in str(e))
                    for etype in error_types
                )

                if not is_retryable or attempt == max_attempts:
                    break

                delay = base_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"  Retry attempt {attempt}/{max_attempts} after {delay:.0f}s "
                    f"(error: {type(e).__name__}: {e})"
                )
                time.sleep(delay)

        return (None, max_attempts, last_error)

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
            f"sleep=[{self._sleep_min}-{self._sleep_max}]s): "
            f"{', '.join(yf_symbols[:3])}{'...' if total > 3 else ''}"
        )

        all_results: Dict[str, pd.DataFrame] = {}
        num_chunks = (total + chunk_size - 1) // chunk_size

        for i in range(0, total, chunk_size):
            batch = yf_symbols[i:i + chunk_size]
            chunk_num = (i // chunk_size) + 1

            t0 = time.time()
            chunk_result = self._download_chunk(batch, start_date, end_date, interval)
            elapsed = time.time() - t0
            success_count = len(chunk_result)
            fail_count = len(batch) - success_count

            logger.info(
                f"  Chunk {chunk_num}/{num_chunks} "
                f"({len(batch)} tickers, {success_count} ok, {fail_count} fail | {elapsed:.1f}s)"
            )

            for yf_sym, df in chunk_result.items():
                all_results[symbol_to_code[yf_sym]] = df

            if i + chunk_size < total:
                sleep_duration = self._jitter_sleep()
                logger.info(f"  Sleep {sleep_duration:.1f}s...")

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
