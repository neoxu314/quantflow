"""Tushare: inclusive daily sessions, explicit factor adjustment, volume in shares."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd

from quantflow.control import check_cancelled
from quantflow.data.base import DataSourceBase, FundamentalData
from quantflow.data.quality import last_completed_session, normalize_ohlcv


class TushareDataSource(DataSourceBase):
    def __init__(self, token=None):
        self.token = token or os.environ.get("TUSHARE_TOKEN", "")
        self._pro = None

    def get_name(self):
        return "Tushare"

    def supports_market(self, market):
        return market in ("cn", "A股", "a")

    def get_supported_periods(self):
        return ["d"]

    def _init_pro(self):
        if self._pro is not None:
            return
        if not self.token:
            raise ValueError("Tushare token required")
        import tushare as ts

        self._pro = ts.pro_api(self.token, timeout=30)

    def fetch_ohlcv(self, code, start_date, end_date, period="d", adjust=None):
        if period != "d":
            raise ValueError("Tushare adapter currently supports daily bars only")
        adjust = adjust or "qfq"
        if adjust not in self.get_supported_adjusts():
            raise ValueError(f"Invalid adjustment: {adjust}")
        check_cancelled()
        self._init_pro()
        kwargs = dict(
            ts_code=code.standard,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )
        df = self._pro.daily(**kwargs)
        check_cancelled()
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={"trade_date": "date", "vol": "volume"}).copy()
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df["volume"] = pd.to_numeric(df["volume"]) * 100
        if adjust != "none":
            factors = self._pro.adj_factor(**kwargs)
            check_cancelled()
            if factors is None or factors.empty:
                raise ValueError("Adjustment factors unavailable; refusing unadjusted fallback")
            factors = factors.rename(columns={"trade_date": "date"}).copy()
            factors["date"] = pd.to_datetime(factors["date"], format="%Y%m%d")
            if factors.date.duplicated().any():
                raise ValueError("Duplicate adjustment-factor dates")
            df = df.merge(
                factors[["date", "adj_factor"]], on="date", how="left", validate="one_to_one"
            )
            factor = pd.to_numeric(df["adj_factor"], errors="raise")
            if factor.isna().any() or (factor <= 0).any():
                raise ValueError("Missing or invalid adjustment factors")
            # qfq is anchored to the last requested trading session. hfq uses the
            # provider's cumulative factor (not a first-in-window rebase).
            anchor = factor.loc[df.date.idxmax()] if adjust == "qfq" else 1.0
            for col in ("open", "high", "low", "close"):
                df[col] = pd.to_numeric(df[col]) * factor / anchor
        result = normalize_ohlcv(
            df[["date", "open", "high", "low", "close", "volume"]], start_date, end_date
        )
        result.attrs.update(adjust=adjust, volume_unit="shares", source="tushare")
        return result

    def fetch_fundamental(self, code, as_of=None):
        self._init_pro()
        now = datetime.now(timezone.utc)
        # Explicit historical dates are valuation dates, not reconstructed
        # point-in-time annual financial statements.
        day = last_completed_session(code, as_of, now)
        check_cancelled()
        df = self._pro.daily_basic(
            ts_code=code.standard,
            trade_date=day.replace("-", ""),
            fields="ts_code,trade_date,pe_ttm,pb,ps_ttm,total_mv,circ_mv",
        )
        check_cancelled()
        if df is None or df.empty:
            return None
        df = df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df[df.trade_date <= pd.Timestamp(day)].sort_values("trade_date")
        if df.empty:
            return None
        row = df.iloc[-1]

        def amount(field):
            value = row.get(field)
            return float(value) * 10000 if pd.notna(value) else None

        return FundamentalData(
            pe_ttm=row.get("pe_ttm"),
            pb=row.get("pb"),
            ps_ttm=row.get("ps_ttm"),
            total_mv=amount("total_mv"),
            circ_mv=amount("circ_mv"),
            code=code.standard,
            source="tushare",
            currency="CNY",
            source_url="https://tushare.pro/document/2?doc_id=32",
            as_of=row.trade_date.strftime("%Y-%m-%d"),
            available_at=now.isoformat(),
            quality_flags=["valuation_snapshot_only", "financial_statements_not_collected"],
        )
