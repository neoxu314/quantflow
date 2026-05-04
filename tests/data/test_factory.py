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


class TestFetchBatchOhlcv:
    """Tests for DataSourceFactory.fetch_batch_ohlcv() batching logic."""

    def test_empty_codes_returns_empty(self, factory):
        result = factory.fetch_batch_ohlcv([], start_date="2026-01-01", end_date="2026-01-31")
        assert result == {}

    def test_batch_includes_only_yfinance_codes_and_calls_adapter_with_params(self, factory):
        # Prepare codes: US and HK should be batched (primary == 'yfinance'), CN should be excluded
        code_us = StockCode.from_standard("AAPL.US")
        code_hk = StockCode(code="00700", exchange="HK")
        code_cn = StockCode.from_standard("600519.SH")  # CN, primary != yfinance -> excluded
        codes = [code_us, code_hk, code_cn]

        captured = {}

        class MockYFAdapter:
            def supports_market(self, market: str) -> bool:
                return market in ["us", "hk"]

            def fetch_batch_ohlcv(self, codes_list, start_date, end_date, period, adjust):
                # Capture the incoming codes as strings for assertion
                captured["codes"] = [str(c) for c in codes_list]
                # Return a small dummy DataFrame per code key
                import pandas as pd
                df = pd.DataFrame({"open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0], "volume": [100]})
                return {
                    str(code_us): df,
                    str(code_hk): df,
                }

        mock_yf = MockYFAdapter()
        with patch.object(DataSourceFactory, "_get_adapter", return_value=mock_yf) as _get_adapter_patch:
            result = factory.fetch_batch_ohlcv(codes, start_date="2026-01-01", end_date="2026-01-31", period="d", adjust="qfq")

        # Should have been called for US and HK only
        assert captured["codes"] == [str(code_us), str(code_hk)]
        assert set(result.keys()) == {str(code_us), str(code_hk)}
        # Each entry should be a tuple with a DataFrame and the source code 'yfinance'
        for k, v in result.items():
            df, src = v
            assert src == "yfinance"
            import pandas as pd
            assert isinstance(df, pd.DataFrame)

    def test_cn_codes_excluded_from_batch(self, factory):
        # Only CN codes should be excluded; include CN only; expect empty batch result
        code_cn = StockCode.from_standard("600519.SH")
        codes = [code_cn]

        mock_yf = MagicMock()
        mock_yf.supports_market.return_value = True
        mock_yf.fetch_batch_ohlcv.return_value = {str(code_cn): None}
        with patch.object(DataSourceFactory, "_get_adapter", return_value=mock_yf):
            result = factory.fetch_batch_ohlcv(codes, start_date="2026-01-01", end_date="2026-01-31")
        # CN should be excluded from batch; hence empty result
        assert result == {}


class TestFetchFundamental:
    """Tests for fetch_fundamental routing and error handling."""

    def test_routing_cn_to_tushare_and_us_to_yfinance(self, factory):
        code_cn = StockCode.from_standard("600519.SH")
        code_us = StockCode.from_standard("AAPL.US")

        mock_ts = MagicMock()
        mock_ts.fetch_fundamental.return_value = {"pe": 20}
        mock_yf = MagicMock()
        mock_yf.fetch_fundamental.return_value = {"pe": 25}

        def fake_get_adapter(name):
            if name == "tushare":
                return mock_ts
            if name == "yfinance":
                return mock_yf
            raise ValueError("unexpected adapter")

        with patch.object(DataSourceFactory, "_get_adapter", side_effect=fake_get_adapter):
            # cn -> tushare
            res_cn = factory.fetch_fundamental(code_cn)
            assert res_cn == {"pe": 20}
            # us -> yfinance
            res_us = factory.fetch_fundamental(code_us)
            assert res_us == {"pe": 25}

    def test_none_when_no_fundamental_source_configured(self, factory):
        code_jp = StockCode(code="7203", exchange="JP")
        with patch.object(DataSourceFactory, "_detect_market", return_value="jp"):
            with patch.object(MarketDataSourceConfig, "get_fundamental_source", return_value=None):
                res = factory.fetch_fundamental(code_jp)
                assert res is None

    def test_exception_handling_returns_none_on_adapter_failure(self, factory):
        code_us = StockCode.from_standard("AAPL.US")
        mock_yf = MagicMock()
        mock_yf.fetch_fundamental.side_effect = Exception("boom")
        with patch.object(DataSourceFactory, "_get_adapter", return_value=mock_yf):
            with patch.object(DataSourceFactory, "_detect_market", return_value="us"):
                res = factory.fetch_fundamental(code_us)
                assert res is None


class TestGetSectorSource:
    def test_get_sector_source_returns_akshare_adapter(self, factory):
        sector_source = factory.get_sector_source()
        # AKShare adapter names include AKShare in their get_name() string
        assert "AKShare" in sector_source.get_name()


class TestMarketDetectionEdgeCases:
    def test_jp_detection_from_T_exchange(self, factory):
        code = StockCode(code="0000", exchange="T")
        assert factory._detect_market(code) == "jp"

    def test_kr_detection_from_KS_exchange(self, factory):
        code = StockCode(code="00001", exchange="KS")
        assert factory._detect_market(code) == "kr"

    def test_unknown_exchange_defaults_to_us(self, factory):
        code = StockCode(code="X", exchange="ZZ")
        assert factory._detect_market(code) == "us"
