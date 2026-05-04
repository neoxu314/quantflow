"""Indicator integration tests using real market data.

Compares indicator output against known TongDaXin reference values.
Fetches real OHLCV data via BaoStock (A-share) and YFinance (US),
calculates indicators, and validates output within tolerance.

Run:
    pytest tests/indicators/test_integration.py -m integration -v
"""

import pytest
import numpy as np
import pandas as pd

from quantflow.indicators.standard.kdj import KDJIndicator
from quantflow.indicators.standard.macd import MACDIndicator
from quantflow.indicators.standard.rsi import RSIIndicator
from quantflow.indicators.standard.boll import BOLLIndicator
from quantflow.indicators.custom.dual_line import DualLineIndicator
from quantflow.indicators.custom.brick_chart import BrickChartIndicator
from quantflow.indicators.custom.washout_short_term import WashoutIndicator


@pytest.mark.integration
@pytest.mark.parametrize("code,start_date,end_date,period,expected", [
    (
        "002594.SZ", "2025-01-01", "2026-04-01", "d",
        {
            "KDJ": {"K": 35.80, "D": 48.40, "J": 10.58},
            "MACD": {"DIF": 2.75, "DEA": 2.88, "MACD": -0.27},
            "BOLL": {"BOLL_MID": 101.90, "BOLL_UPPER": 110.11, "BOLL_LOWER": 93.69},
            "RSI": {"RSI6": 43.04, "RSI12": 53.29, "RSI24": 55.40},
            "DualLine": {"short_trend_line": 102.53, "long_short_line": 99.24},
            "BrickChart": {"brick_chart": 75.12},
            "Washout": {"short": 7.61, "long": 65.96},
        },
    ),
    (
        "AAPL", "2022-01-01", "2026-02-06", "w",
        {
            "KDJ": {"K": 47.629, "D": 37.966, "J": 66.957},
            "MACD": {"DIF": 8.133, "DEA": 10.467, "MACD": -4.668},
            "BOLL": {"BOLL_MID": 265.206, "BOLL_UPPER": 286.741, "BOLL_LOWER": 243.670},
            "RSI": {"RSI6": 66.234, "RSI12": 62.828, "RSI24": 60.413},
            "DualLine": {"short_trend_line": 263.038, "long_short_line": 244.419},
            "BrickChart": {"brick_chart": 85.713},
            "Washout": {"short": 100.000, "long": 98.344},
        },
    ),
])
class TestIndicatorValues:
    """Integration test: fetch real data → calculate indicators → compare with TongDaXin."""

    def _fetch_baostock(self, code: str, start: str, end: str) -> pd.DataFrame:
        """Fetch BaoStock OHLCV data."""
        import baostock as bs
        bs.login()
        prefix, ticker = code.split(".")
        target = prefix.lower() + "." + ticker

        rs = bs.query_history_k_data_plus(
            target, "date,open,high,low,close,volume",
            start_date=start, end_date=end,
            frequency="d", adjustflag="2",
        )
        records = []
        while rs.error_code == "0" and rs.next():
            records.append(rs.get_row_data())
        bs.logout()

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records, columns=["date", "open", "high", "low", "close", "volume"])
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        return df

    def _fetch_yfinance(self, ticker: str, start: str, end: str) -> pd.DataFrame:
        """Fetch YFinance OHLCV data."""
        import yfinance as yf
        df = yf.download(ticker, start=start, end=end, progress=False)
        if df.empty:
            return df

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        df.index = pd.to_datetime(df.index)
        return df

    def _resample_weekly(self, df: pd.DataFrame) -> pd.DataFrame:
        res = pd.DataFrame()
        res["open"] = df["open"].resample("W").first()
        res["high"] = df["high"].resample("W").max()
        res["low"] = df["low"].resample("W").min()
        res["close"] = df["close"].resample("W").last()
        res["volume"] = df["volume"].resample("W").sum()
        return res.dropna()

    def test_kdj(self, code, start_date, end_date, period, expected):
        df = self._fetch_for_code(code, start_date, end_date, period)
        if df.empty:
            pytest.skip(f"No data for {code}")

        ind = KDJIndicator()
        result = ind.calculate(df)
        target = pd.to_datetime(end_date)
        row = self._find_row(result, target)

        vals = expected["KDJ"]
        tol = 0.15 if period == "w" else 0.05
        assert row["K"] == pytest.approx(vals["K"], rel=tol)
        assert row["D"] == pytest.approx(vals["D"], rel=tol)
        assert row["J"] == pytest.approx(vals["J"], rel=0.05)

    def _find_row(self, result: pd.DataFrame, target: pd.Timestamp) -> pd.Series:
        target_norm = target.normalize() if hasattr(target, "normalize") else target
        if target in result.index:
            return result.loc[target]
        if target_norm in result.index:
            return result.loc[target_norm]
        nearest_idx = result.index.get_indexer([target_norm], method="nearest")[0]
        return result.iloc[nearest_idx]

    def test_macd(self, code, start_date, end_date, period, expected):
        df = self._fetch_for_code(code, start_date, end_date, period)
        if df.empty:
            pytest.skip(f"No data for {code}")

        ind = MACDIndicator()
        result = ind.calculate(df)
        row = self._find_row(result, pd.to_datetime(end_date))
        vals = expected["MACD"]
        assert row["DIF"] == pytest.approx(vals["DIF"], rel=0.05)
        assert row["DEA"] == pytest.approx(vals["DEA"], rel=0.05)
        assert row["MACD"] == pytest.approx(vals["MACD"], rel=0.15)

    def test_boll(self, code, start_date, end_date, period, expected):
        df = self._fetch_for_code(code, start_date, end_date, period)
        if df.empty:
            pytest.skip(f"No data for {code}")

        ind = BOLLIndicator()
        result = ind.calculate(df)
        row = self._find_row(result, pd.to_datetime(end_date))
        vals = expected["BOLL"]
        assert row["BOLL_MID"] == pytest.approx(vals["BOLL_MID"], rel=0.05)
        assert row["BOLL_UPPER"] == pytest.approx(vals["BOLL_UPPER"], rel=0.05)
        assert row["BOLL_LOWER"] == pytest.approx(vals["BOLL_LOWER"], rel=0.05)

    def test_rsi(self, code, start_date, end_date, period, expected):
        df = self._fetch_for_code(code, start_date, end_date, period)
        if df.empty:
            pytest.skip(f"No data for {code}")

        ind = RSIIndicator(periods=[6, 12, 24])
        result = ind.calculate(df)
        row = self._find_row(result, pd.to_datetime(end_date))
        vals = expected["RSI"]
        tol = 0.15 if period == "w" else 0.05
        for col, exp_val in vals.items():
            assert row[col] == pytest.approx(exp_val, rel=tol)

    def test_dual_line(self, code, start_date, end_date, period, expected):
        df = self._fetch_for_code(code, start_date, end_date, period)
        if df.empty:
            pytest.skip(f"No data for {code}")

        ind = DualLineIndicator()
        result = ind.calculate(df)
        row = self._find_row(result, pd.to_datetime(end_date))
        vals = expected["DualLine"]
        if np.isnan(float(row.get("long_short_line", float("nan")))):
            pytest.skip("Insufficient bars for DualLine long_short_line")
        assert row["short_trend_line"] == pytest.approx(vals["short_trend_line"], rel=0.05)
        assert row["long_short_line"] == pytest.approx(vals["long_short_line"], rel=0.05)

    def test_brick_chart(self, code, start_date, end_date, period, expected):
        df = self._fetch_for_code(code, start_date, end_date, period)
        if df.empty:
            pytest.skip(f"No data for {code}")

        ind = BrickChartIndicator()
        result = ind.calculate(df)
        row = self._find_row(result, pd.to_datetime(end_date))
        vals = expected["BrickChart"]
        assert row["brick_chart"] == pytest.approx(vals["brick_chart"], rel=0.10)

    def test_washout(self, code, start_date, end_date, period, expected):
        df = self._fetch_for_code(code, start_date, end_date, period)
        if df.empty:
            pytest.skip(f"No data for {code}")

        ind = WashoutIndicator()
        result = ind.calculate(df)
        row = self._find_row(result, pd.to_datetime(end_date))
        vals = expected["Washout"]
        assert row["short"] == pytest.approx(vals["short"], rel=0.10)
        assert row["long"] == pytest.approx(vals["long"], rel=0.10)

    def _fetch_for_code(self, code, start, end, period):
        if "." in code:
            df = self._fetch_baostock(code, start, end)
        else:
            df = self._fetch_yfinance(code, start, end)

        if period == "w" and not df.empty:
            df = self._resample_weekly(df)

        return df
