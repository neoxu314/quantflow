"""Tests for real data fetching from data sources.

Uses real stock data to verify data source adapters work correctly.
These tests require network access and valid API tokens.

Test data reference:
A股:
- BYD (002594.SZ): 2025-07-25, open=112.34, close=111.32, volume=157041 (手)
- Moutai (600519.SH): 2026-03-19, open=1472.96, close=1452.87, volume=30319 (手)

美股:
- INTC: 2025-09-18, open=31.78, close=30.57, volume=5.24亿
- MSFT: 2026-04-21, open=420.24, close=424.16, volume=3204.85万

韩国股票:
- 000660 (SK海力士): 2026-04-21, open=1175000, close=1247000, volume=7.49M

Run integration tests:
    pytest tests/data/test_data_fetch.py -m integration -v
    
Skip integration tests:
    pytest tests/data/test_data_fetch.py -m "not integration" -v
"""

import pytest
import pandas as pd
import os
from datetime import datetime

from quantflow.data.base import StockCode
from quantflow.data.adapters.baostock import BaoStockDataSource
from quantflow.data.adapters.tushare import TushareDataSource
from quantflow.data.adapters.yfinance import YFinanceDataSource
from quantflow.data.adapters.yahooquery import YahooQueryDataSource
from quantflow.data.factory import DataSourceFactory


# =============================================================================
# Test Data Reference (provided by user)
# =============================================================================

TEST_DATA = {
    # A股测试数据
    "byd": {
        "code": "002594.SZ",
        "date": "2025-07-25",
        "expected_open": 112.34,
        "expected_close": 111.32,
        "expected_volume": 157041,
        "baostock_open": 112.33,
        "baostock_close": 111.32,
        "baostock_volume": 15704076,
    },
    "moutai": {
        "code": "600519.SH",
        "date": "2026-03-19",
        "expected_open": 1472.96,
        "expected_close": 1452.87,
        "expected_volume": 30319,
        "baostock_open": 1472.96,
        "baostock_close": 1452.87,
        "baostock_volume": 3031859,
    },
    # 美股测试数据
    "intc": {
        "code": "INTC.US",
        "date": "2025-09-18",
        "expected_open": 31.78,
        "expected_close": 30.57,
        "expected_volume": 524000000,
    },
    "msft": {
        "code": "MSFT.US",
        "date": "2026-04-21",
        "expected_open": 420.24,
        "expected_close": 424.16,
        "expected_volume": 32048500,
    },
    # 韩股测试数据
    "sk_hynix": {
        "code": "000660.KR",
        "date": "2026-04-21",
        "expected_open": 1175000,
        "expected_close": 1247000,
        "expected_volume": 7490000,
    },
    # 港股测试数据
    "nongfu_spring": {
        "code": "09660.HK",
        "date": "2025-10-30",
        "expected_open": 9.29,
        "expected_close": 9.04,
        "expected_volume": 233000000,
    },
    "tencent": {
        "code": "00700.HK",
        "date": "2024-05-21",
        "expected_open": 388.9,
        "expected_close": 379.1,
        "expected_volume": 30679800,
    },
    # 日本股票测试数据
    "tokyo_electron": {
        "code": "8035.JP",
        "date": "2025-08-04",
        "expected_open": 21089.4,
        "expected_close": 22086.4,
        "expected_volume": 7839800,
    },
}

# =============================================================================
# Weekly/Monthly Test Data (周线/月线测试数据)
# =============================================================================

PERIOD_TEST_DATA = {
    # A股周线/月线数据
    "hengrui_weekly": {
        "code": "600276.SH",
        "period": "w",
        "date": "2025-11-07",
        "expected_open": 64.96,
        "expected_close": 61.58,
        "expected_volume": 1833000,
    },
    "hengrui_monthly": {
        "code": "600276.SH",
        "period": "m",
        "date": "2018-12-28",
        "expected_open": 37.66,
        "expected_close": 29.35,
        "expected_volume": 5056000,
    },
    # 港股周线/月线数据
    "alibaba_hk_weekly": {
        "code": "09988.HK",
        "period": "w",
        "date": "2020-11-09",
        "expected_open": 286.852,
        "expected_close": 252.452,
        "expected_volume": 313000000,
    },
    "alibaba_hk_monthly": {
        "code": "09988.HK",
        "period": "m",
        "date": "2025-10-01",
        "expected_open": 179.7,
        "expected_close": 165.1,
        "expected_volume": 2256000000,
    },
    # 美股周线/月线数据
    "goog_weekly": {
        "code": "GOOG.US",
        "period": "w",
        "date": "2025-02-03",
        "expected_open": 201.289,
        "expected_close": 186.283,
        "expected_volume": 139000000,
    },
    "goog_monthly": {
        "code": "GOOG.US",
        "period": "m",
        "date": "2026-02-01",
        "expected_open": 336.313,
        "expected_close": 311.211,
        "expected_volume": 490000000,
    },
    # 日本股票周线/月线数据
    "advantest_weekly": {
        "code": "6857.JP",
        "period": "w",
        "date": "2025-10-27",
        "expected_open": 17685.0,
        "expected_close": 23135.0,
        "expected_volume": 118000000,
    },
    "advantest_monthly": {
        "code": "6857.JP",
        "period": "m",
        "date": "2023-05-01",
        "expected_open": 2635.2,
        "expected_close": 4448.4,
        "expected_volume": 357000000,
    },
}


# =============================================================================
# BaoStock Integration Tests
# =============================================================================

@pytest.mark.integration
class TestBaoStockFetch:
    """Integration tests for BaoStock data fetching."""
    
    @pytest.fixture
    def baostock_source(self):
        return BaoStockDataSource(adjust="qfq")
    
    def test_fetch_byd_data(self, baostock_source):
        """Test fetching BYD (002594.SZ) daily data."""
        code = StockCode.from_standard(TEST_DATA["byd"]["code"])
        start_date = "2025-07-01"
        end_date = "2025-07-31"
        
        df = baostock_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty, "Should return data for BYD"
        
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns
        
        target_date = pd.to_datetime(TEST_DATA["byd"]["date"])
        match = df[df["date"] == target_date]
        
        assert len(match) > 0
        
        row = match.iloc[0]
        expected_open = TEST_DATA["byd"]["baostock_open"]
        expected_close = TEST_DATA["byd"]["baostock_close"]
        
        assert abs(row["open"] - expected_open) < 0.5
        assert abs(row["close"] - expected_close) < 0.5
        
        # BaoStock returns volume in shares (股), user reference is in lots (手)
        expected_volume = TEST_DATA["byd"]["baostock_volume"]
        assert abs(row["volume"] - expected_volume) / expected_volume < 0.05
    
    def test_fetch_moutai_data(self, baostock_source):
        """Test fetching Moutai (600519.SH) daily data."""
        code = StockCode.from_standard(TEST_DATA["moutai"]["code"])
        start_date = "2026-03-01"
        end_date = "2026-03-31"
        
        df = baostock_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty
        
        target_date = pd.to_datetime(TEST_DATA["moutai"]["date"])
        match = df[df["date"] == target_date]
        
        assert len(match) > 0
        
        row = match.iloc[0]
        expected_open = TEST_DATA["moutai"]["baostock_open"]
        expected_close = TEST_DATA["moutai"]["baostock_close"]
        
        assert abs(row["open"] - expected_open) < 1.0
        assert abs(row["close"] - expected_close) < 1.0
    
    def test_date_format_yyyy_mm_dd(self, baostock_source):
        """Verify BaoStock adapter uses YYYY-MM-DD format correctly."""
        code = StockCode.from_standard("002594.SZ")
        
        df = baostock_source.fetch_ohlcv(
            code, 
            start_date="2024-01-01",
            end_date="2024-01-10"
        )
        
        assert not df.empty
    
    def test_stock_code_conversion(self, baostock_source):
        """Test StockCode format conversion."""
        code = StockCode.from_standard("600000.SH")
        assert code.baostock == "sh.600000"
        
        code = StockCode.from_standard("000001.SZ")
        assert code.baostock == "sz.000001"


# =============================================================================
# Tushare Integration Tests (requires token)
# =============================================================================

@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("TUSHARE_TOKEN"),
    reason="TUSHARE_TOKEN not set"
)
class TestTushareFetch:
    """Integration tests for Tushare data fetching."""
    
    @pytest.fixture
    def tushare_source(self):
        token = os.environ.get("TUSHARE_TOKEN")
        return TushareDataSource(token=token)
    
    def test_fetch_byd_data(self, tushare_source):
        """Test fetching BYD data via Tushare."""
        code = StockCode.from_standard(TEST_DATA["byd"]["code"])
        start_date = "2025-07-01"
        end_date = "2025-07-31"
        
        df = tushare_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty
        
        target_date = pd.to_datetime(TEST_DATA["byd"]["date"])
        match = df[df["date"] == target_date]
        
        assert len(match) > 0
        
        row = match.iloc[0]
        
        # Tushare vs BaoStock price difference is expected:
        # - Tushare: 341 (dynamic adjustment)
        # - BaoStock: 112 (static adjustment)
        # This is due to BYD's dividend/split in 2025-07-29
        # Unit difference: Tushare returns lots (手), BaoStock returns shares (股)
        
        expected_volume_lots = TEST_DATA["byd"]["expected_volume"]
        assert abs(row["volume"] - expected_volume_lots) / expected_volume_lots < 0.05
    
    def test_fetch_moutai_data(self, tushare_source):
        """Test fetching Moutai data via Tushare."""
        code = StockCode.from_standard(TEST_DATA["moutai"]["code"])
        start_date = "2026-03-01"
        end_date = "2026-03-31"
        
        df = tushare_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty
        
        target_date = pd.to_datetime(TEST_DATA["moutai"]["date"])
        match = df[df["date"] == target_date]
        
        assert len(match) > 0
        
        row = match.iloc[0]
        expected_open = TEST_DATA["moutai"]["expected_open"]
        expected_close = TEST_DATA["moutai"]["expected_close"]
        
        assert abs(row["open"] - expected_open) < 1.0
        assert abs(row["close"] - expected_close) < 1.0


# =============================================================================
# YFinance Integration Tests (US/KR markets)
# =============================================================================

@pytest.mark.integration
class TestYFinanceFetch:
    """Integration tests for YFinance data fetching."""
    
    @pytest.fixture
    def yfinance_source(self):
        return YFinanceDataSource()
    
    def test_fetch_intc_data(self, yfinance_source):
        """Test fetching INTC (Intel) US stock daily data."""
        code = StockCode(code="INTC", exchange="US")
        start_date = "2025-09-01"
        end_date = "2025-09-30"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty, "Should return data for INTC"
        
        required_cols = ["date", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns
        
        target_date = TEST_DATA["intc"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find data for {TEST_DATA['intc']['date']}"
        
        row = match.iloc[0]
        expected_open = TEST_DATA["intc"]["expected_open"]
        expected_close = TEST_DATA["intc"]["expected_close"]
        
        assert abs(row["open"] - expected_open) < 0.5, f"Open mismatch: {row['open']} vs {expected_open}"
        assert abs(row["close"] - expected_close) < 0.5, f"Close mismatch: {row['close']} vs {expected_close}"
        
        expected_volume = TEST_DATA["intc"]["expected_volume"]
        volume_diff_pct = abs(row["volume"] - expected_volume) / expected_volume
        assert volume_diff_pct < 0.10, f"Volume mismatch: {row['volume']} vs {expected_volume} ({volume_diff_pct:.2%})"
    
    def test_fetch_msft_data(self, yfinance_source):
        """Test fetching MSFT (Microsoft) US stock daily data."""
        code = StockCode(code="MSFT", exchange="US")
        start_date = "2026-04-01"
        end_date = "2026-04-30"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty
        
        target_date = TEST_DATA["msft"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0
        
        row = match.iloc[0]
        expected_open = TEST_DATA["msft"]["expected_open"]
        expected_close = TEST_DATA["msft"]["expected_close"]
        
        assert abs(row["open"] - expected_open) < 1.0
        assert abs(row["close"] - expected_close) < 1.0
    
    def test_fetch_sk_hynix_data(self, yfinance_source):
        """Test fetching SK Hynix (000660.KS) Korea stock daily data."""
        code = StockCode(code="000660", exchange="KR")
        start_date = "2026-04-01"
        end_date = "2026-04-30"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty, "Should return data for SK Hynix"
        
        target_date = TEST_DATA["sk_hynix"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0
        
        row = match.iloc[0]
        expected_open = TEST_DATA["sk_hynix"]["expected_open"]
        expected_close = TEST_DATA["sk_hynix"]["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_fetch_nongfu_spring_data(self, yfinance_source):
        """Test fetching Nongfu Spring (09660.HK) Hong Kong stock daily data."""
        code = StockCode(code="09660", exchange="HK")
        start_date = "2025-10-01"
        end_date = "2025-10-31"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty, "Should return data for Nongfu Spring"
        
        target_date = TEST_DATA["nongfu_spring"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find data for {target_date}"
        
        row = match.iloc[0]
        expected_open = TEST_DATA["nongfu_spring"]["expected_open"]
        expected_close = TEST_DATA["nongfu_spring"]["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_fetch_tencent_data(self, yfinance_source):
        """Test fetching Tencent (00700.HK) Hong Kong stock daily data."""
        code = StockCode(code="00700", exchange="HK")
        start_date = "2024-05-01"
        end_date = "2024-05-31"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty, "Should return data for Tencent"
        
        target_date = TEST_DATA["tencent"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find data for {target_date}"
        
        row = match.iloc[0]
        expected_open = TEST_DATA["tencent"]["expected_open"]
        expected_close = TEST_DATA["tencent"]["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_fetch_tokyo_electron_data(self, yfinance_source):
        """Test fetching Tokyo Electron (8035.T) Japan stock daily data."""
        code = StockCode(code="8035", exchange="JP")
        start_date = "2025-08-01"
        end_date = "2025-08-31"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="d")
        
        assert not df.empty, "Should return data for Tokyo Electron"
        
        target_date = TEST_DATA["tokyo_electron"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find data for {target_date}"
        
        row = match.iloc[0]
        expected_open = TEST_DATA["tokyo_electron"]["expected_open"]
        expected_close = TEST_DATA["tokyo_electron"]["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_yfinance_symbol_conversion(self, yfinance_source):
        """Test YFinance symbol conversion for different markets."""
        us_code = StockCode(code="INTC", exchange="US")
        assert yfinance_source._get_yfinance_symbol(us_code) == "INTC"
        
        kr_code = StockCode(code="000660", exchange="KR")
        assert yfinance_source._get_yfinance_symbol(kr_code) == "000660.KS"
    
    def test_yfinance_supports_markets(self, yfinance_source):
        """Test YFinance supports correct markets."""
        assert yfinance_source.supports_market("us")
        assert yfinance_source.supports_market("kr")
        assert not yfinance_source.supports_market("cn")


# =============================================================================
# YahooQuery Integration Tests (US/HK/JP/KR markets)
# =============================================================================

@pytest.mark.integration
class TestYahooQueryFetch:
    """Integration tests for YahooQuery data fetching."""

    @pytest.fixture
    def yq_source(self):
        return YahooQueryDataSource()

    def test_fetch_intc_data(self, yq_source):
        """Test fetching INTC (Intel) US stock daily data."""
        code = StockCode(code="INTC", exchange="US")
        start_date = "2025-09-01"
        end_date = "2025-09-30"

        df = yq_source.fetch_ohlcv(code, start_date, end_date, period="d")

        assert not df.empty, "Should return data for INTC"

        required_cols = ["date", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            assert col in df.columns

        target_date = TEST_DATA["intc"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]

        assert len(match) > 0, f"Should find data for {target_date}"

        row = match.iloc[0]
        expected_close = TEST_DATA["intc"]["expected_close"]

        assert abs(row["close"] - expected_close) < 1.0, (
            f"Close mismatch: {row['close']} vs {expected_close}"
        )

    def test_fetch_msft_data(self, yq_source):
        """Test fetching MSFT (Microsoft) US stock daily data."""
        code = StockCode(code="MSFT", exchange="US")
        start_date = "2026-04-01"
        end_date = "2026-04-30"

        df = yq_source.fetch_ohlcv(code, start_date, end_date, period="d")

        assert not df.empty

        target_date = TEST_DATA["msft"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]

        assert len(match) > 0

        row = match.iloc[0]
        expected_open = TEST_DATA["msft"]["expected_open"]
        expected_close = TEST_DATA["msft"]["expected_close"]

        assert abs(row["open"] - expected_open) < 1.0
        assert abs(row["close"] - expected_close) < 1.0

    def test_fetch_sk_hynix_data(self, yq_source):
        """Test fetching SK Hynix (000660.KS) Korea stock daily data."""
        code = StockCode(code="000660", exchange="KR")
        start_date = "2026-04-01"
        end_date = "2026-04-30"

        df = yq_source.fetch_ohlcv(code, start_date, end_date, period="d")

        assert not df.empty, "Should return data for SK Hynix"

        target_date = TEST_DATA["sk_hynix"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]

        assert len(match) > 0

        row = match.iloc[0]
        expected_close = TEST_DATA["sk_hynix"]["expected_close"]

        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        assert close_diff_pct < 0.05, (
            f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
        )

    def test_fetch_nongfu_spring_data(self, yq_source):
        """Test fetching Nongfu Spring (09660.HK) Hong Kong stock daily data."""
        code = StockCode(code="09660", exchange="HK")
        start_date = "2025-10-01"
        end_date = "2025-10-31"

        df = yq_source.fetch_ohlcv(code, start_date, end_date, period="d")

        assert not df.empty, "Should return data for Nongfu Spring"

        target_date = TEST_DATA["nongfu_spring"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]

        assert len(match) > 0, f"Should find data for {target_date}"

        row = match.iloc[0]
        expected_open = TEST_DATA["nongfu_spring"]["expected_open"]
        expected_close = TEST_DATA["nongfu_spring"]["expected_close"]

        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close

        assert open_diff_pct < 0.05, (
            f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        )
        assert close_diff_pct < 0.05, (
            f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
        )

    def test_fetch_tencent_data(self, yq_source):
        """Test fetching Tencent (00700.HK) Hong Kong stock daily data."""
        code = StockCode(code="00700", exchange="HK")
        start_date = "2024-05-01"
        end_date = "2024-05-31"

        df = yq_source.fetch_ohlcv(code, start_date, end_date, period="d")

        assert not df.empty, "Should return data for Tencent"

        target_date = TEST_DATA["tencent"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]

        assert len(match) > 0, f"Should find data for {target_date}"

        row = match.iloc[0]
        expected_open = TEST_DATA["tencent"]["expected_open"]
        expected_close = TEST_DATA["tencent"]["expected_close"]

        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close

        assert open_diff_pct < 0.05, (
            f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        )
        assert close_diff_pct < 0.05, (
            f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
        )

    def test_fetch_tokyo_electron_data(self, yq_source):
        """Test fetching Tokyo Electron (8035.T) Japan stock daily data."""
        code = StockCode(code="8035", exchange="JP")
        start_date = "2025-08-01"
        end_date = "2025-08-31"

        df = yq_source.fetch_ohlcv(code, start_date, end_date, period="d")

        assert not df.empty, "Should return data for Tokyo Electron"

        target_date = TEST_DATA["tokyo_electron"]["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]

        assert len(match) > 0, f"Should find data for {target_date}"

        row = match.iloc[0]
        expected_close = TEST_DATA["tokyo_electron"]["expected_close"]

        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        assert close_diff_pct < 0.05, (
            f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
        )

    def test_yahooquery_symbol_conversion(self, yq_source):
        """Test YahooQuery symbol conversion for different markets."""
        us_code = StockCode(code="INTC", exchange="US")
        assert yq_source._get_yahooquery_symbol(us_code) == "INTC"

        kr_code = StockCode(code="000660", exchange="KR")
        assert yq_source._get_yahooquery_symbol(kr_code) == "000660.KS"

        hk_code = StockCode(code="00700", exchange="HK")
        assert yq_source._get_yahooquery_symbol(hk_code) == "0700.HK"

    def test_yahooquery_supports_markets(self, yq_source):
        """Test YahooQuery supports correct markets."""
        assert yq_source.supports_market("us")
        assert yq_source.supports_market("kr")
        assert yq_source.supports_market("hk")
        assert yq_source.supports_market("jp")
        assert not yq_source.supports_market("cn")

    def test_yahooquery_batch_fetch_us(self, yq_source):
        """Test YahooQuery batch fetch for US stocks with asynchronous=True."""
        codes = [
            StockCode(code="AAPL", exchange="US"),
            StockCode(code="MSFT", exchange="US"),
            StockCode(code="GOOGL", exchange="US"),
        ]
        results = yq_source.fetch_batch_ohlcv(codes, "2026-05-01", "2026-05-12")

        assert len(results) == 3
        for code_str in ["AAPL.US", "MSFT.US", "GOOGL.US"]:
            assert code_str in results
            df = results[code_str]
            assert not df.empty
            assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]

    def test_yahooquery_batch_fetch_multi_market(self, yq_source):
        """Test YahooQuery batch fetch across US + HK markets."""
        codes = [
            StockCode(code="AAPL", exchange="US"),
            StockCode(code="0700", exchange="HK"),
        ]
        results = yq_source.fetch_batch_ohlcv(codes, "2026-05-01", "2026-05-12")

        assert len(results) == 2
        assert "AAPL.US" in results
        assert "0700.HK" in results

    def test_yahooquery_fundamental(self, yq_source):
        """Test YahooQuery fundamental data fetch for US stock."""
        code = StockCode(code="AAPL", exchange="US")
        result = yq_source.fetch_fundamental(code)

        assert result is not None
        assert result.pe_ttm is not None or result.pb is not None
        assert result.total_mv is not None


# =============================================================================
# Weekly/Monthly Period Tests (周线/月线数据测试)
# =============================================================================

@pytest.mark.integration
class TestPeriodDataFetch:
    """Integration tests for weekly and monthly data fetching."""
    
    @pytest.fixture
    def baostock_source(self):
        return BaoStockDataSource(adjust="qfq")
    
    @pytest.fixture
    def yfinance_source(self):
        return YFinanceDataSource()
    
    def test_baostock_weekly_hengrui(self, baostock_source):
        """Test BaoStock weekly data for Hengrui (600276.SH)."""
        data = PERIOD_TEST_DATA["hengrui_weekly"]
        code = StockCode.from_standard(data["code"])
        start_date = "2025-11-01"
        end_date = "2025-11-30"
        
        df = baostock_source.fetch_ohlcv(code, start_date, end_date, period="w")
        
        assert not df.empty, "Should return weekly data for Hengrui"
        
        target_date = data["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find weekly data for {target_date}"
        
        row = match.iloc[0]
        expected_open = data["expected_open"]
        expected_close = data["expected_close"]
        
        assert abs(row["open"] - expected_open) / expected_open < 0.05
        assert abs(row["close"] - expected_close) / expected_close < 0.05
    
    def test_baostock_monthly_hengrui(self, baostock_source):
        """Test BaoStock monthly data for Hengrui (600276.SH)."""
        data = PERIOD_TEST_DATA["hengrui_monthly"]
        code = StockCode.from_standard(data["code"])
        start_date = "2018-12-01"
        end_date = "2018-12-31"
        
        df = baostock_source.fetch_ohlcv(code, start_date, end_date, period="m")
        
        assert not df.empty, "Should return monthly data for Hengrui"
        
        target_date = data["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find monthly data for {target_date}"
        
        row = match.iloc[0]
        expected_open = data["expected_open"]
        expected_close = data["expected_close"]
        
        assert abs(row["open"] - expected_open) / expected_open < 0.05
        assert abs(row["close"] - expected_close) / expected_close < 0.05
    
    def test_yfinance_weekly_alibaba_hk(self, yfinance_source):
        """Test YFinance weekly data for Alibaba HK (9988.HK)."""
        data = PERIOD_TEST_DATA["alibaba_hk_weekly"]
        code = StockCode(code="09988", exchange="HK")
        start_date = "2020-11-01"
        end_date = "2020-11-30"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="w")
        
        assert not df.empty, "Should return weekly data for Alibaba HK"
        
        target_date = data["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find weekly data for {target_date}"
        
        row = match.iloc[0]
        expected_open = data["expected_open"]
        expected_close = data["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_yfinance_monthly_alibaba_hk(self, yfinance_source):
        """Test YFinance monthly data for Alibaba HK (9988.HK)."""
        data = PERIOD_TEST_DATA["alibaba_hk_monthly"]
        code = StockCode(code="09988", exchange="HK")
        start_date = "2025-10-01"
        end_date = "2025-10-31"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="m")
        
        assert not df.empty, "Should return monthly data for Alibaba HK"
        
        target_date = data["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find monthly data for {target_date}"
        
        row = match.iloc[0]
        expected_open = data["expected_open"]
        expected_close = data["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_yfinance_weekly_goog(self, yfinance_source):
        """Test YFinance weekly data for Google (GOOG)."""
        data = PERIOD_TEST_DATA["goog_weekly"]
        code = StockCode(code="GOOG", exchange="US")
        start_date = "2025-02-01"
        end_date = "2025-02-28"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="w")
        
        assert not df.empty, "Should return weekly data for GOOG"
        
        target_date = data["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find weekly data for {target_date}"
        
        row = match.iloc[0]
        expected_open = data["expected_open"]
        expected_close = data["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_yfinance_monthly_goog(self, yfinance_source):
        """Test YFinance monthly data for Google (GOOG)."""
        data = PERIOD_TEST_DATA["goog_monthly"]
        code = StockCode(code="GOOG", exchange="US")
        start_date = "2026-02-01"
        end_date = "2026-02-28"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="m")
        
        assert not df.empty, "Should return monthly data for GOOG"
        
        target_date = data["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find monthly data for {target_date}"
        
        row = match.iloc[0]
        expected_open = data["expected_open"]
        expected_close = data["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_yfinance_weekly_advantest(self, yfinance_source):
        """Test YFinance weekly data for Advantest (6857.T)."""
        data = PERIOD_TEST_DATA["advantest_weekly"]
        code = StockCode(code="6857", exchange="JP")
        start_date = "2025-10-01"
        end_date = "2025-10-31"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="w")
        
        assert not df.empty, "Should return weekly data for Advantest"
        
        target_date = data["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find weekly data for {target_date}"
        
        row = match.iloc[0]
        expected_open = data["expected_open"]
        expected_close = data["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"
    
    def test_yfinance_monthly_advantest(self, yfinance_source):
        """Test YFinance monthly data for Advantest (6857.T)."""
        data = PERIOD_TEST_DATA["advantest_monthly"]
        code = StockCode(code="6857", exchange="JP")
        start_date = "2023-05-01"
        end_date = "2023-05-31"
        
        df = yfinance_source.fetch_ohlcv(code, start_date, end_date, period="m")
        
        assert not df.empty, "Should return monthly data for Advantest"
        
        target_date = data["date"]
        match = df[df["date"].dt.strftime("%Y-%m-%d") == target_date]
        
        assert len(match) > 0, f"Should find monthly data for {target_date}"
        
        row = match.iloc[0]
        expected_open = data["expected_open"]
        expected_close = data["expected_close"]
        
        open_diff_pct = abs(row["open"] - expected_open) / expected_open
        close_diff_pct = abs(row["close"] - expected_close) / expected_close
        
        assert open_diff_pct < 0.05, f"Open mismatch: {row['open']} vs {expected_open} ({open_diff_pct:.2%})"
        assert close_diff_pct < 0.05, f"Close mismatch: {row['close']} vs {expected_close} ({close_diff_pct:.2%})"


# =============================================================================
# Factory Integration Tests
# =============================================================================

@pytest.mark.integration
class TestDataSourceFactoryFetch:
    """Integration tests for DataSourceFactory with real data."""
    
    @pytest.fixture
    def factory(self):
        return DataSourceFactory()
    
    def test_fetch_cn_stock(self, factory):
        """Test fetching A-share stock via factory."""
        code = StockCode.from_standard("002594.SZ")
        
        df, source_name = factory.fetch_ohlcv(
            code, 
            "2025-07-01", 
            "2025-07-31",
            period="d"
        )
        
        assert not df.empty
        assert source_name.lower() == "baostock"
    
    def test_fetch_with_fallback(self, factory):
        """Test factory fallback mechanism."""
        code = StockCode.from_standard("600519.SH")
        
        df, source_name = factory.fetch_ohlcv(
            code,
            "2026-03-01",
            "2026-03-31"
        )
        
        assert not df.empty
        assert source_name.lower() in ["baostock", "tushare"]


# =============================================================================
# Edge Case Tests (non-integration, uses mock)
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @pytest.fixture
    def baostock_source(self):
        return BaoStockDataSource()
    
    def test_empty_result_handling(self, baostock_source):
        """An empty provider result is handled offline without contacting BaoStock."""
        from unittest.mock import Mock
        baostock_source._logged_in = True
        baostock_source._bs = Mock()
        response = Mock(error_code="0", fields=["date", "code", "open", "high", "low", "close", "volume", "amount"])
        response.next.return_value = False
        baostock_source._bs.query_history_k_data_plus.return_value = response
        assert baostock_source.fetch_ohlcv(StockCode("600000", "SH"), "2026-01-01", "2026-01-31").empty
    
    def test_invalid_adjust_type(self, baostock_source):
        """Test error handling for invalid adjust type."""
        code = StockCode.from_standard("600000.SH")
        
        with pytest.raises(ValueError, match="Invalid adjust"):
            baostock_source.fetch_ohlcv(
                code,
                "2024-01-01",
                "2024-01-31",
                adjust="invalid"
            )
    
    def test_invalid_stock_code(self):
        """Missing market suffix is rejected instead of defaulting silently."""
        with pytest.raises(ValueError, match="stock code"):
            StockCode.from_standard("invalid")


# =============================================================================
# Run Instructions
# =============================================================================

def test_run_instructions():
    """Print test run instructions."""
    instructions = """
    =====================================================================
    Data Layer Test Run Instructions
    =====================================================================
    
    1. Run all tests (including integration):
       pytest tests/data/test_data_fetch.py -v
    
    2. Run only unit tests (skip integration):
       pytest tests/data/test_data_fetch.py -m "not integration" -v
    
    3. Run only integration tests:
       pytest tests/data/test_data_fetch.py -m integration -v
    
    4. Run with Tushare tests (set token first):
       export TUSHARE_TOKEN="your_token"
       pytest tests/data/test_data_fetch.py -m integration -v
    
    5. Run specific test:
       pytest tests/data/test_data_fetch.py::TestBaoStockFetch::test_fetch_byd_data -v
    
    =====================================================================
    """
    print(instructions)
    # This test always passes, just prints instructions
    assert True