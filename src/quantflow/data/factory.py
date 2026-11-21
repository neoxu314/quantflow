"""Configured data-source routing with per-symbol fallback and explicit contracts."""

from __future__ import annotations

import inspect
import logging
import time
from copy import deepcopy

import pandas as pd

from quantflow.control import ExecutionCancelled, check_cancelled
from quantflow.data.adapters import (
    AKShareDataSource,
    BaoStockDataSource,
    TushareDataSource,
    YahooQueryDataSource,
    YFinanceDataSource,
)
from quantflow.data import yahoo_batch
from quantflow.data.config import DEFAULT_CONFIG
from quantflow.data.quality import inspect_daily_bars, normalize_ohlcv, tradable_bars

logger = logging.getLogger(__name__)


class DataSourceFactory:
    ADAPTER_MAP = {
        "baostock": BaoStockDataSource,
        "tushare": TushareDataSource,
        "yfinance": YFinanceDataSource,
        "akshare": AKShareDataSource,
        "yahooquery": YahooQueryDataSource,
    }

    def __init__(
        self, config=None, tushare_token=None, yfinance_config=None, yahooquery_config=None
    ):
        self.config = deepcopy(config or DEFAULT_CONFIG)
        self.tushare_token = tushare_token
        self._yfinance = yfinance_config or {}
        self._yahooquery = yahooquery_config or {}
        self._adapters = {}
        self.failures = {}
        self._provider_cooldowns = {}
        self.pending_network = set()

    def _get_adapter(self, source_name):
        if source_name in self._adapters:
            return self._adapters[source_name]
        cls = self.ADAPTER_MAP.get(source_name)
        if cls is None:
            raise ValueError(f"Unknown data source: {source_name}")
        if source_name == "tushare":
            obj = cls(token=self.tushare_token)
        elif source_name == "yfinance":
            keys = (
                "chunk_size",
                "sleep_min",
                "sleep_max",
                "retry_max_attempts",
                "retry_base_delay",
                "cooldown_base",
                "recovery_max_passes",
                "recovery_chunk_size",
            )
            obj = cls(**{k: self._yfinance.get(k) for k in keys})
        elif source_name == "yahooquery":
            obj = cls(
                **{
                    k: self._yahooquery.get(k)
                    for k in ("chunk_size", "sleep_min", "sleep_max", "max_workers")
                }
            )
        else:
            obj = cls()
        self._adapters[source_name] = obj
        return obj

    def get_source(self, market):
        return self._get_adapter(self.config.get_primary(market))

    @staticmethod
    def _contract(adapter, market, period, adjust):
        if not adapter.supports_market(market):
            raise ValueError(f"{adapter.get_name()} does not support {market}")
        if period not in adapter.get_supported_periods():
            raise ValueError(f"Unsupported period: {period}")
        if adjust not in adapter.get_supported_adjusts():
            raise ValueError(f"Unsupported adjustment: {adjust}")

    @staticmethod
    def _frame(df, source, period, adjust, start, end):
        clean = normalize_ohlcv(df, start, end)
        clean.attrs.update(
            source=source, period=period, adjust=adjust, volume_unit="shares", end_inclusive=True
        )
        if source in ("yfinance", "yahooquery"):
            clean.attrs["price_adjustment_basis"] = (
                "yahoo_split_adjusted" if adjust == "none" else "yahoo_dividend_and_split_adjusted"
            )
        return clean

    def fetch_ohlcv(
        self, code, start_date, end_date, period="d", adjust="qfq", market=None,
        *, require_end_session=False, min_history_bars=1,
    ):
        market = market or self._detect_market(code)
        self.failures.pop(code.standard, None)
        return self._fetch_from_sources(
            code,
            start_date,
            end_date,
            period,
            adjust,
            market,
            self.config.get_primary(market),
            self.config.get_fallback(market),
            require_end_session,
            min_history_bars,
        )

    def _fetch_from_sources(
        self, code, start_date, end_date, period, adjust, market, primary, fallback,
        require_end_session, min_history_bars,
    ):
        best = (pd.DataFrame(), None)
        for source in dict.fromkeys(s for s in (primary, fallback) if s):
            check_cancelled()
            try:
                adapter = self._get_adapter(source)
                self._contract(adapter, market, period, adjust)
                df = adapter.fetch_ohlcv(code, start_date, end_date, period, adjust)
                check_cancelled()
                df = self._frame(df, source, period, adjust, start_date, end_date)
                if not df.empty:
                    if self._prefer_history(
                        df, best[0], code, period, end_date, require_end_session, min_history_bars
                    ):
                        best = (df, source)
                    if not self._needs_fallback(
                        df, code, period, end_date, require_end_session, min_history_bars
                    ):
                        break
            except ExecutionCancelled:
                raise
            except Exception as exc:
                self.failures.setdefault(code.standard, []).append(f"{source}: {exc}")
                logger.warning("Source %s failed for %s: %s", source, code, exc)
        return best

    @staticmethod
    def _latest_date(df):
        if "date" in df:
            return pd.to_datetime(df["date"]).max().strftime("%Y-%m-%d")
        if isinstance(df.index, pd.DatetimeIndex):
            return df.index.max().strftime("%Y-%m-%d")
        raise ValueError("Data has no session dates")

    def _needs_fallback(self, frame, code, period, end_date, require_end_session, min_bars):
        if frame.empty:
            return True
        if not require_end_session:
            return False
        if period == "d":
            status = inspect_daily_bars(frame, code, end_date).status
            return status != "suspended" and (status != "ok" or len(tradable_bars(frame)) < min_bars)
        return self._latest_date(frame) != end_date

    def _prefer_history(self, candidate, previous, code, period, end_date, require_end_session,
                        min_bars):
        if candidate.empty:
            return False
        if previous.empty:
            return True
        candidate_date, previous_date = self._latest_date(candidate), self._latest_date(previous)
        if candidate_date != previous_date:
            return candidate_date > previous_date
        return (
            require_end_session and period == "d" and candidate_date == end_date
            and len(tradable_bars(candidate)) >= min_bars
            and inspect_daily_bars(candidate, code, end_date).status == "ok"
            and (
                len(tradable_bars(previous)) < min_bars
                or inspect_daily_bars(previous, code, end_date).status == "data_gap"
            )
        )

    def has_batch_support(self, source_name, market):
        try:
            adapter = self._get_adapter(source_name)
            return adapter.supports_market(market) and callable(
                getattr(adapter, "fetch_batch_ohlcv", None)
            )
        except Exception:
            # The single-symbol path records primary errors and can still use its fallback.
            return False

    def _request_batch(self, source, adapter, group, args, deadline, *, progress=None, probe=False):
        if type(adapter) in (YahooQueryDataSource, YFinanceDataSource):
            if self._provider_cooldowns.get(source, 0) > time.monotonic():
                self.pending_network.update(code.standard for code in group)
                raise ConnectionError("Network unavailable; retry pending stocks with Resume")
            settings = self._yahooquery if source == "yahooquery" else self._yfinance
            allowed = inspect.signature(type(adapter)).parameters
            settings = {k: v for k, v in settings.items() if k in allowed}
            received = yahoo_batch.download(source, settings, group, args, deadline, progress,
                                           probe=probe)
            adapter.batch_errors = received.errors
            self.pending_network.update(received.errors)
            if received.outage:
                self._provider_cooldowns[source] = time.monotonic() + yahoo_batch.COOLDOWN_SECONDS
                logger.warning("%s unavailable or timed out; deferring unresolved quotes", source)
            return received.frames
        kwargs = {}
        if progress and "progress_cb" in inspect.signature(adapter.fetch_batch_ohlcv).parameters:
            kwargs["progress_cb"] = progress
        return adapter.fetch_batch_ohlcv(group, *args, **kwargs)

    def fetch_batch_ohlcv(
        self, codes, start_date, end_date, period="d", adjust="qfq", progress_cb=None,
        *, require_end_session=False, min_history_bars=1,
    ):
        started = time.monotonic()
        deadline = started + yahoo_batch.BATCH_SECONDS
        groups, results, missing = {}, {}, []
        for code in codes:
            self.pending_network.discard(code.standard)
            self.failures.pop(code.standard, None)
            market = self._detect_market(code)
            source = self.config.get_primary(market)
            try:
                if self.has_batch_support(source, market):
                    groups.setdefault(source, []).append(code)
                else:
                    df, src = self.fetch_ohlcv(
                        code, start_date, end_date, period, adjust,
                        require_end_session=require_end_session, min_history_bars=min_history_bars,
                    )
                    if not df.empty:
                        results[code.standard] = (df, src)
            except ExecutionCancelled:
                raise
            except Exception as exc:
                self.failures.setdefault(code.standard, []).append(str(exc))
                missing.append(code)
        offset = 0
        for source, group in groups.items():
            check_cancelled()
            adapter = self._get_adapter(source)
            try:
                for code in group:
                    self._contract(adapter, self._detect_market(code), period, adjust)
                def notify(index, total, code, base=offset):
                    check_cancelled()
                    progress_cb(base + index, len(codes), code)

                batch = self._request_batch(
                    source, adapter, group, (start_date, end_date, period, adjust),
                    started + yahoo_batch.PRIMARY_SECONDS, progress=notify if progress_cb else None,
                )
                check_cancelled()
                self._record_batch_errors(adapter, source, group)
                for code in group:
                    try:
                        df = self._frame(
                            batch.get(code.standard), source, period, adjust, start_date, end_date
                        )
                        needs_fallback = self._needs_fallback(
                            df, code, period, end_date, require_end_session, min_history_bars
                        )
                        if not df.empty:
                            results[code.standard] = (df, source)
                        if needs_fallback:
                            missing.append(code)
                    except Exception as exc:
                        missing.append(code)
                        self.failures.setdefault(code.standard, []).append(f"{source}: {exc}")
            except ExecutionCancelled:
                raise
            except Exception as exc:
                logger.warning("Batch from %s failed: %s", source, exc)
                for code in group:
                    self.failures.setdefault(code.standard, []).append(f"{source}: {exc}")
                missing.extend(c for c in group if c.standard not in results)
            offset += len(group)
        self._batch_fallback(
            missing, start_date, end_date, period, adjust, results, require_end_session,
            min_history_bars, deadline=deadline,
        )
        retry = [
            code for code in missing
            if self._needs_fallback(
                results.get(code.standard, (pd.DataFrame(), None))[0],
                code, period, end_date, require_end_session, min_history_bars,
            )
        ]
        if retry:
            logger.info("Rechecking %d unresolved provider failures: %s",
                        len(retry), ", ".join(code.standard for code in retry))
            self._batch_fallback(
                retry, start_date, end_date, period, adjust, results, require_end_session,
                min_history_bars, deadline=deadline, use_primary=True,
            )
        return results

    def _record_batch_errors(self, adapter, source, codes):
        errors = getattr(adapter, "batch_errors", None)
        if isinstance(errors, dict):
            for code in codes:
                if error := errors.get(code.standard):
                    self.failures.setdefault(code.standard, []).append(f"{source}: {error}")

    def _batch_fallback(
        self, failed_codes, start_date, end_date, period, adjust, all_results, require_end_session,
        min_history_bars, *, deadline, use_primary=False,
    ):
        groups = {}
        source_for = self.config.get_primary if use_primary else self.config.get_fallback
        for code in failed_codes:
            source = source_for(self._detect_market(code))
            if source:
                groups.setdefault(source, []).append(code)
        for source, group in groups.items():
            check_cancelled()
            try:
                adapter = self._get_adapter(source)
                for code in group:
                    self._contract(adapter, self._detect_market(code), period, adjust)
                if callable(getattr(adapter, "fetch_batch_ohlcv", None)):
                    probe = not use_primary and any(
                        until > time.monotonic() for until in self._provider_cooldowns.values()
                    )
                    batch = self._request_batch(source, adapter, group,
                                                (start_date, end_date, period, adjust),
                                                deadline, probe=probe)
                else:
                    batch = {}
                    for code in group:
                        check_cancelled()
                        try:
                            batch[code.standard] = adapter.fetch_ohlcv(
                                code, start_date, end_date, period, adjust
                            )
                        except ExecutionCancelled:
                            raise
                        except Exception as exc:
                            self.failures.setdefault(code.standard, []).append(f"{source}: {exc}")
                check_cancelled()
                self._record_batch_errors(adapter, source, group)
                for code in group:
                    try:
                        df = self._frame(
                            batch.get(code.standard), source, period, adjust, start_date, end_date
                        )
                        previous = all_results.get(code.standard)
                        if not df.empty and (
                            previous is None or self._prefer_history(
                                df, previous[0], code, period, end_date, require_end_session,
                                min_history_bars,
                            )
                        ):
                            all_results[code.standard] = (df, source)
                    except Exception as exc:
                        self.failures.setdefault(code.standard, []).append(f"{source}: {exc}")
            except ExecutionCancelled:
                raise
            except Exception as exc:
                logger.warning("Fallback %s failed: %s", source, exc)
                for code in group:
                    self.failures.setdefault(code.standard, []).append(f"{source}: {exc}")

    def fetch_fundamental(self, code, market=None, as_of=None):
        source = self.config.get_fundamental_source(market or self._detect_market(code))
        if not source:
            return None
        check_cancelled()
        try:
            adapter = self._get_adapter(source)
            return (
                adapter.fetch_fundamental(code, as_of=as_of)
                if as_of
                else adapter.fetch_fundamental(code)
            )
        except Exception as exc:
            logger.warning("Fundamental data unavailable for %s: %s", code, exc)
            return None

    def get_sector_source(self):
        return self._get_adapter("akshare")

    def _detect_market(self, code):
        markets = {
            "SH": "cn",
            "SZ": "cn",
            "HK": "hk",
            "US": "us",
            "T": "jp",
            "JP": "jp",
            "KS": "kr",
            "KR": "kr",
        }
        if code.exchange not in markets:
            raise ValueError(f"Unknown exchange: {code.exchange}")
        return markets[code.exchange]
