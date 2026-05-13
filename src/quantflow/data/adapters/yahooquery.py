"""YahooQuery data source adapter for global markets.

Uses yahooquery library with asynchronous=True for efficient batch fetching.
Unlike yfinance (which uses Yahoo's batch download API and hits 429 rate limits),
yahooquery uses concurrent individual requests via requests-futures, avoiding
the rate-limit issues that plague yfinance for 700+ ticker batches.

Supported markets:
- US: No suffix (e.g., AAPL)
- HK: .HK suffix (e.g., 0700.HK)
- KR: .KS suffix (e.g., 000660.KS)
- JP: .T suffix (e.g., 8035.T)

MultiIndex handling:
  yahooquery.history() with multiple tickers returns a DataFrame with
  MultiIndex (symbol, date). This adapter normalizes it via reset_index()
  and groupby('symbol') to produce per-stock DataFrames matching the
  standard format: date, open, high, low, close, volume.

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

logger = logging.getLogger(__name__)


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

    _SUB_CHUNK_SIZE = 10

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

    def get_name(self) -> str:
        return "YahooQuery"

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

        symbol = self._get_yahooquery_symbol(code)
        interval = self.PERIOD_INTERVAL.get(period, "1d")
        adj_ohlc = adjust == "qfq"

        logger.info(f"Fetching {period} data for {symbol} via YahooQuery")

        ticker = Ticker(symbol, asynchronous=False)
        raw = ticker.history(start=start_date, end=end_date, interval=interval, adj_ohlc=adj_ohlc)

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
    ) -> Dict[str, pd.DataFrame]:
        if not codes:
            return {}


        interval = self.PERIOD_INTERVAL.get(period, "1d")
        adj_ohlc = adjust == "qfq"

        symbol_to_code: Dict[str, str] = {}
        yq_symbols: List[str] = []
        for code_obj in codes:
            yq_sym = self._get_yahooquery_symbol(code_obj)
            symbol_to_code[yq_sym] = code_obj.standard
            yq_symbols.append(yq_sym)

        total = len(yq_symbols)
        chunk_size = min(self._chunk_size, total)

        logger.info(
            f"Batch fetching {total} tickers via YahooQuery "
            f"(chunk_size={chunk_size}, async=True, "
            f"sleep=[{self._sleep_min}-{self._sleep_max}]s): "
            f"{', '.join(yq_symbols[:3])}{'...' if total > 3 else ''}"
        )

        all_results: Dict[str, pd.DataFrame] = {}
        num_chunks = (total + chunk_size - 1) // chunk_size

        for i in range(0, total, chunk_size):
            batch = yq_symbols[i:i + chunk_size]
            chunk_num = (i // chunk_size) + 1

            t0 = time.time()
            chunk_result = self._fetch_chunk(
                batch, start_date, end_date, interval, adj_ohlc, symbol_to_code,
            )
            elapsed = time.time() - t0
            success_count = len(chunk_result)
            fail_count = len(batch) - success_count

            logger.info(
                f"  Chunk {chunk_num}/{num_chunks} "
                f"({len(batch)} tickers, {success_count} ok, {fail_count} fail | {elapsed:.1f}s)"
            )

            all_results.update(chunk_result)

            if i + chunk_size < total:
                sleep_duration = self._jitter_sleep()
                logger.info(f"  Sleep {sleep_duration:.1f}s...")

        missed = [s for s in yq_symbols if symbol_to_code[s] not in all_results]
        if missed:
            logger.info(f"Recovery: retrying {len(missed)} missed tickers")
            time.sleep(self._sleep_max)
            recovery_result = self._fetch_chunk(
                missed, start_date, end_date, interval, adj_ohlc, symbol_to_code,
            )
            all_results.update(recovery_result)

        logger.info(f"Batch complete: {len(all_results)}/{total} tickers with data")
        return all_results

    _SUB_CHUNK_SIZE = 10

    def _fetch_chunk(
        self,
        yq_symbols: List[str],
        start_date: str,
        end_date: str,
        interval: str,
        adj_ohlc: bool,
        symbol_to_code: Dict[str, str],
        _depth: int = 0,
    ) -> Dict[str, pd.DataFrame]:
        if not yq_symbols:
            return {}

        from yahooquery import Ticker

        symbols_str = " ".join(yq_symbols)
        ticker = Ticker(symbols_str, asynchronous=True, max_workers=self._max_workers)

        try:
            raw = ticker.history(
                start=start_date, end=end_date, interval=interval, adj_ohlc=adj_ohlc,
            )
        except Exception as e:
            if _depth >= 2 or len(yq_symbols) <= 1:
                logger.warning(
                    f"  Can't fetch {yq_symbols[0] if len(yq_symbols)==1 else len(yq_symbols)} "
                    f"tickers: {type(e).__name__}: {e}"
                )
                return {}
            logger.info(
                f"  Splitting chunk ({len(yq_symbols)} tickers) after "
                f"{type(e).__name__}: {e}"
            )
            mid = len(yq_symbols) // 2
            left = self._fetch_chunk(
                yq_symbols[:mid], start_date, end_date, interval,
                adj_ohlc, symbol_to_code, _depth + 1,
            )
            right = self._fetch_chunk(
                yq_symbols[mid:], start_date, end_date, interval,
                adj_ohlc, symbol_to_code, _depth + 1,
            )
            return {**left, **right}

        if raw is None or raw.empty:
            logger.warning(f"  Empty response for chunk ({len(yq_symbols)} tickers)")
            return {}

        return self._normalize_multiindex(raw, yq_symbols, adj_ohlc, symbol_to_code)

    def _normalize_multiindex(
        self,
        raw_df: pd.DataFrame,
        requested_symbols: List[str],
        adj_ohlc: bool,
        symbol_to_code: Dict[str, str],
    ) -> Dict[str, pd.DataFrame]:
        if raw_df.empty:
            return {}

        df = raw_df.reset_index()

        if "symbol" not in df.columns:
            logger.warning("  Missing 'symbol' column after reset_index")
            return {}

        df = self._resolve_close_column(df, adj_ohlc)

        results: Dict[str, pd.DataFrame] = {}
        for yq_sym in requested_symbols:
            group = df[df["symbol"] == yq_sym]
            if group.empty:
                logger.debug(f"  No data for symbol: {yq_sym}")
                continue

            group = group.drop(columns=["symbol"]).reset_index(drop=True)
            rename_map = {k: v for k, v in self._COL_MAP.items() if k in group.columns}
            group = group.rename(columns=rename_map)

            target_cols = ["date", "open", "high", "low", "close", "volume"]
            group = group[[c for c in target_cols if c in group.columns]]

            if "date" in group.columns:
                group["date"] = pd.to_datetime(group["date"]).dt.tz_localize(None)

            if group.empty:
                logger.debug(f"  Empty after normalization: {yq_sym}")
                continue

            code = symbol_to_code.get(yq_sym, yq_sym)
            results[code] = group
            logger.debug(f"  ✓ {yq_sym}: {len(group)} rows")

        return results

    def _normalize_single(self, raw_df: pd.DataFrame, adj_ohlc: bool) -> pd.DataFrame:
        if raw_df.empty:
            return pd.DataFrame()

        df = raw_df.reset_index()
        df = self._resolve_close_column(df, adj_ohlc)
        df = df.rename(columns={k: v for k, v in self._COL_MAP.items() if k in df.columns})
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
        time.sleep(duration)
        return duration

    def fetch_fundamental(self, code: StockCode) -> Optional[FundamentalData]:
        from yahooquery import Ticker

        symbol = self._get_yahooquery_symbol(code)

        try:
            ticker = Ticker(symbol)

            key_stats = ticker.key_stats
            summary_detail = ticker.summary_detail

            ks = key_stats.get(symbol, {}) if isinstance(key_stats, dict) else {}
            sd = summary_detail.get(symbol, {}) if isinstance(summary_detail, dict) else {}

            pe_ttm = sd.get("trailingPE") or ks.get("trailingPE")
            if pe_ttm is None:
                pe_ttm = ks.get("forwardPE")

            pb = ks.get("priceToBook") or sd.get("priceToBook")
            total_mv = sd.get("marketCap") or ks.get("enterpriseValue")

            return FundamentalData(
                pe_ttm=pe_ttm,
                pb=pb,
                total_mv=total_mv,
            )
        except Exception as e:
            logger.warning(f"Failed to fetch fundamental for {symbol}: {e}")
            return None
