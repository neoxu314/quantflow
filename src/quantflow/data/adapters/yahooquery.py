"""YahooQuery data source adapter for global markets.

Uses yahooquery library with sequential per-ticker fetches for reliability.
Unlike yfinance (which uses Yahoo's batch download API), yahooquery fetches
each ticker individually. The library's asynchronous=True batch mode is
unreliable (HTTP 404 / KeyError for >4 tickers), so this adapter uses
asynchronous=False with retries per ticker.

Why not yahooquery async batch mode:
  YahooQuery's asynchronous=True uses requests-futures for concurrent requests,
  but Yahoo's API returns HTTP 404 when too many concurrent requests hit it.
  The library's _historical_data_to_dataframe() then crashes with KeyError
  because it doesn't handle the error response dict gracefully.

  Our approach: fetch tickers sequentially with retries, which is slower but
  reliable (~90% per attempt, ~99% with 3 retries).

Supported markets:
- US: No suffix (e.g., AAPL)
- HK: .HK suffix (e.g., 0700.HK)
- KR: .KS suffix (e.g., 000660.KS)
- JP: .T suffix (e.g., 8035.T)

Adjust (复权):
  - qfq (前复权): Uses adjclose column with adj_ohlc=True to adjust OHLC.
  - hfq (后复权): Not directly supported; returns unadjusted data.
  - none: Raw unadjusted data with adj_ohlc=False.
"""

import logging
import random
import time
from typing import Dict, List, Optional

import pandas as pd

from quantflow.data.base import DataSourceBase, FundamentalData, StockCode
from quantflow.control import check_cancelled, cancellable_sleep
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_YQ_PATCHED = False


def _patch_yahooquery_error_handling() -> None:
    global _YQ_PATCHED
    if _YQ_PATCHED:
        return

    try:
        from yahooquery import Ticker
        from yahooquery.ticker import history_dataframe

        def patched(self, data, params, adj_timezone):
            if isinstance(data, dict) and "error" in data and len(data) == 1:
                return pd.DataFrame(
                    columns=["high", "low", "volume", "open", "close"]
                )
            d = {}
            for symbol in self._symbols:
                if symbol not in data:
                    continue
                symbol_data = data[symbol]
                if isinstance(symbol_data, str):
                    continue
                if isinstance(symbol_data, dict):
                    if "timestamp" in symbol_data:
                        daily = params["interval"][-1] not in ["m", "h"]
                        d[symbol] = history_dataframe(
                            symbol_data, daily, adj_timezone
                        )
                    else:
                        continue
            if not d:
                return pd.DataFrame(
                    columns=["high", "low", "volume", "open", "close"]
                )
            try:
                df = pd.concat(d, names=["symbol", "date"], sort=False)
            except ValueError:
                return pd.DataFrame(
                    columns=["high", "low", "volume", "open", "close"]
                )
            else:
                if "dividends" in df.columns:
                    df.fillna({"dividends": 0}, inplace=True)
                if "splits" in df.columns:
                    df.fillna({"splits": 0}, inplace=True)
            return df

        Ticker._historical_data_to_dataframe = patched
        _YQ_PATCHED = True
        logger.debug("Patched yahooquery _historical_data_to_dataframe")
    except Exception as e:
        logger.warning(f"Failed to patch yahooquery: {e}")


class YahooQueryDataSource(DataSourceBase):

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
        "date": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    }

    _MAX_RETRIES = 5
    _RETRY_DELAY = 3.0

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        sleep_min: Optional[float] = None,
        sleep_max: Optional[float] = None,
        max_workers: Optional[int] = None,
    ):
        self._chunk_size = chunk_size or 100
        self._sleep_min = sleep_min if sleep_min is not None else 0.5
        self._sleep_max = sleep_max if sleep_max is not None else 2.0
        self._max_workers = max_workers or 20
        _patch_yahooquery_error_handling()

    def get_name(self) -> str:
        return "YahooQuery"

    def get_supported_adjusts(self):
        return ["qfq", "none"]

    def get_supported_periods(self):
        return ["d", "w", "m"]

    def _validate_request(self, period, adjust):
        if period not in self.get_supported_periods() or adjust not in self.get_supported_adjusts():
            raise ValueError(f"Unsupported YahooQuery request: {period}/{adjust}")
        check_cancelled()

    def supports_market(self, market: str) -> bool:
        return market in ["us", "hk", "jp", "kr", "美股", "港股", "日本", "韩国"]

    def _get_yahooquery_symbol(self, code: StockCode) -> str:
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
        adjust: Optional[str] = None,
    ) -> pd.DataFrame:
        from yahooquery import Ticker

        adjust = adjust or "qfq"
        self._validate_request(period, adjust)
        symbol = self._get_yahooquery_symbol(code)
        interval = self.PERIOD_INTERVAL.get(period, "1d")
        adj_ohlc = adjust == "qfq"

        logger.info(f"Fetching {period} data for {symbol} via YahooQuery")

        ticker = Ticker(symbol, asynchronous=False, timeout=30)
        raw = ticker.history(
            start=start_date,
            end=(pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
            interval=interval, adj_ohlc=adj_ohlc
        )

        if raw is None or raw.empty:
            logger.warning(f"No data for {symbol}")
            return pd.DataFrame()

        return self._normalize_single(raw, adj_ohlc)

    def fetch_batch_ohlcv(
        self,
        codes: List[StockCode],
        start_date: str,
        end_date: str,
        period: str = "d",
        adjust: Optional[str] = None,
        progress_cb=None,
    ) -> Dict[str, pd.DataFrame]:
        self._validate_request(period, adjust or "qfq")
        if not codes:
            return {}

        from yahooquery import Ticker

        interval = self.PERIOD_INTERVAL.get(period, "1d")
        adj_ohlc = (adjust or "qfq") == "qfq"

        symbol_to_code: Dict[str, str] = {}
        yq_symbols: List[str] = []
        for code_obj in codes:
            yq_sym = self._get_yahooquery_symbol(code_obj)
            symbol_to_code[yq_sym] = code_obj.standard
            yq_symbols.append(yq_sym)

        total = len(yq_symbols)

        logger.info(
            f"Batch fetching {total} tickers via YahooQuery "
            f"(sequential, retries={self._MAX_RETRIES}, "
            f"sleep=[{self._sleep_min}-{self._sleep_max}]s): "
            f"{', '.join(yq_symbols[:3])}{'...' if total > 3 else ''}"
        )

        all_results: Dict[str, pd.DataFrame] = {}
        failed: List[str] = []

        t0 = time.time()
        for idx, yq_sym in enumerate(yq_symbols, 1):
            # Report progress while fetching (not only after the whole batch
            # returns) so the Web UI progress bar advances in real time.
            if progress_cb is not None:
                try:
                    progress_cb(idx, total, yq_sym)
                except Exception:
                    pass
            df = self._fetch_single_with_retry(
                Ticker, yq_sym, start_date, end_date, interval, adj_ohlc,
            )
            if df is not None and not df.empty:
                code = symbol_to_code[yq_sym]
                all_results[code] = df
                logger.debug(f"  [{idx}/{total}] ✓ {yq_sym}: {len(df)} rows")
            else:
                failed.append(yq_sym)
                logger.debug(f"  [{idx}/{total}] ✗ {yq_sym}: no data after retries")

            if idx < total:
                self._jitter_sleep()

        elapsed = time.time() - t0
        logger.info(
            f"Batch complete: {len(all_results)}/{total} tickers "
            f"({len(failed)} failed | {elapsed:.1f}s)"
        )

        return all_results

    def _fetch_single_with_retry(
        self,
        ticker_cls,
        yq_sym: str,
        start_date: str,
        end_date: str,
        interval: str,
        adj_ohlc: bool,
    ) -> Optional[pd.DataFrame]:
        for attempt in range(1, self._MAX_RETRIES + 1):
            try:
                check_cancelled()
                ticker = ticker_cls(yq_sym, asynchronous=False, timeout=30)
                raw = ticker.history(
                    start=start_date,
                    end=(pd.Timestamp(end_date) + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
                    interval=interval,
                    adj_ohlc=adj_ohlc,
                )
                if raw is not None and not raw.empty:
                    return self._normalize_single(raw, adj_ohlc)
            except KeyError:
                logger.debug(
                    f"  {yq_sym} KeyError on attempt {attempt}/{self._MAX_RETRIES}"
                )
            except Exception as e:
                logger.debug(
                    f"  {yq_sym} {type(e).__name__} on attempt "
                    f"{attempt}/{self._MAX_RETRIES}: {e}"
                )

            if attempt < self._MAX_RETRIES:
                cancellable_sleep(self._RETRY_DELAY)

        return None

    def _normalize_single(self, raw_df: pd.DataFrame, adj_ohlc: bool) -> pd.DataFrame:
        if raw_df.empty:
            return pd.DataFrame()

        df = raw_df.reset_index()
        df = self._resolve_close_column(df, adj_ohlc)
        df = df.rename(
            columns={k: v for k, v in self._COL_MAP.items() if k in df.columns}
        )
        df = df.drop(columns=["symbol"], errors="ignore")

        target_cols = ["date", "open", "high", "low", "close", "volume"]
        df = df[[c for c in target_cols if c in df.columns]]

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)

        return df.reset_index(drop=True)

    @staticmethod
    def _resolve_close_column(df: pd.DataFrame, adj_ohlc: bool) -> pd.DataFrame:
        if "adjclose" in df.columns:
            if adj_ohlc:
                df = df.drop(columns=["close"])
                df = df.rename(columns={"adjclose": "close"})
            else:
                df = df.drop(columns=["adjclose"])
        return df

    def _jitter_sleep(self) -> float:
        duration = random.uniform(self._sleep_min, self._sleep_max)
        cancellable_sleep(duration)
        return duration

    def fetch_fundamental(self, code: StockCode, as_of=None) -> Optional[FundamentalData]:
        from yahooquery import Ticker

        if as_of and pd.Timestamp(as_of).date() < datetime.now(timezone.utc).date():
            raise ValueError("YahooQuery fundamentals do not support point-in-time history")
        check_cancelled()

        symbol = self._get_yahooquery_symbol(code)

        try:
            ticker = Ticker(symbol)

            key_stats = ticker.key_stats
            summary_detail = ticker.summary_detail

            ks = key_stats.get(symbol, {}) if isinstance(key_stats, dict) else {}
            sd = summary_detail.get(symbol, {}) if isinstance(summary_detail, dict) else {}

            pe_ttm = sd.get("trailingPE") or ks.get("trailingPE")

            pb = ks.get("priceToBook") or sd.get("priceToBook")
            total_mv = sd.get("marketCap")

            return FundamentalData(
                pe_ttm=pe_ttm,
                pb=pb,
                total_mv=total_mv,
                forward_pe=ks.get("forwardPE"), enterprise_value=ks.get("enterpriseValue"),
                code=code.standard, source="yahooquery", currency=sd.get("currency"),
                as_of=datetime.now(timezone.utc).isoformat(),
                available_at=datetime.now(timezone.utc).isoformat(),
                source_url=f"https://finance.yahoo.com/quote/{symbol}/",
                quality_flags=["current_snapshot_only", "financial_statements_not_collected"],
            )
        except Exception as e:
            logger.warning(f"Failed to fetch fundamental for {symbol}: {e}")
            return None
