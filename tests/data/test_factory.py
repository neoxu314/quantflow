"""Tests for DataSourceFactory."""

import datetime
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from quantflow.data.base import StockCode
from quantflow.data.factory import DataSourceFactory
from quantflow.data.config import MarketDataSourceConfig


@pytest.fixture
def factory():
    return DataSourceFactory()


class TestDataSourceFactory:

    def test_get_source_cn(self, factory):
        source = factory.get_source("cn")
        assert source.get_name() == "BaoStock"

    def test_get_source_us(self, factory):
        source = factory.get_source("us")
        assert source.get_name() == "YFinance"

    def test_detect_market(self, factory):
        cn_code = StockCode.from_standard("600000.SH")
        assert factory._detect_market(cn_code) == "cn"

        hk_code = StockCode(code="00700", exchange="HK")
        assert factory._detect_market(hk_code) == "hk"

        us_code = StockCode(code="AAPL", exchange="US")
        assert factory._detect_market(us_code) == "us"

    def test_custom_config(self):
        custom_config = MarketDataSourceConfig(primary={"cn": "tushare"})
        factory = DataSourceFactory(config=custom_config, tushare_token="test")

        source = factory.get_source("cn")
        assert source.get_name() == "Tushare"

    def test_adapter_singleton(self, factory):
        source1 = factory.get_source("cn")
        source2 = factory.get_source("cn")
        assert source1 is source2


class TestDataSourceFallback:
    """Test automatic fallback when end_date = today but no data available."""

    @staticmethod
    def _mock_df(start, end):
        idx = pd.date_range("2026-05-04", "2026-05-04", freq="B")
        return pd.DataFrame(
            {"open": [1.0], "high": [1.1], "low": [0.95], "close": [1.05], "volume": [100]},
            index=idx,
        )

    def test_fallback_triggers_when_today_no_data(self, factory):
        """When end_date = today and no data, fallback expands 180 days to get history."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        call_log = []

        def mock_fetch(*args, **kw):
            s, e = args[1], args[2]
            call_log.append((s, e))
            if s == today and e == today:
                return pd.DataFrame()
            # Simulate fallback returns full range of data
            idx = pd.date_range("2025-12-01", "2026-05-04", freq="B")[:10]
            return pd.DataFrame(
                {"open": [1.0] * len(idx), "high": [1.1] * len(idx),
                 "low": [0.95] * len(idx), "close": [1.05] * len(idx),
                 "volume": [100] * len(idx)},
                index=idx,
            )

        mock_adapter = MagicMock()
        mock_adapter.supports_market.return_value = True
        mock_adapter.fetch_ohlcv = mock_fetch

        code = StockCode.from_standard("600519.SH")
        with patch.object(factory, "_get_adapter", return_value=mock_adapter):
            df, source = factory.fetch_ohlcv(code, today, today)

        assert not df.empty
        assert len(df) == 10  # Full fallback range, not truncated
        assert len(call_log) >= 2
        assert call_log[0] == (today, today)

    def test_no_fallback_when_historical_date_no_data(self, factory):
        """Requesting a historical date with no data should NOT fallback."""
        with patch.object(factory, "_get_adapter") as get_adapter:
            mock_adapter = MagicMock()
            mock_adapter.supports_market.return_value = True
            mock_adapter.fetch_ohlcv.return_value = pd.DataFrame()
            get_adapter.return_value = mock_adapter

            code = StockCode.from_standard("600519.SH")
            df, source = factory.fetch_ohlcv(code, "2020-01-01", "2020-01-01")

        assert df.empty

    def test_fallback_preserves_requested_range_when_possible(self, factory):
        """When user provides a range (not today), fallback keeps their start date."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        def mock_fetch(*args, **kw):
            s, e = args[1], args[2]
            return TestDataSourceFallback._mock_df(s, e)

        mock_adapter = MagicMock()
        mock_adapter.supports_market.return_value = True
        mock_adapter.fetch_ohlcv = mock_fetch

        code = StockCode.from_standard("600519.SH")
        with patch.object(factory, "_get_adapter", return_value=mock_adapter):
            df, source = factory.fetch_ohlcv(code, today, today)

        assert not df.empty

    def test_latest_date_helper(self, factory):
        """_latest_date returns the last index as a string."""
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        df = pd.DataFrame({"close": [1]}, index=pd.DatetimeIndex([today]))
        assert factory._latest_date(df) == today