import pandas as pd
from unittest.mock import MagicMock, patch


def _make_multiindex_df(tickers_data, adj_ohlc=False):
    frames = []
    for ticker, rows in tickers_data.items():
        for row in rows:
            row_copy = dict(row)
            row_copy["symbol"] = ticker
            if adj_ohlc and "adjclose" not in row_copy:
                row_copy["adjclose"] = row_copy["close"]
            frames.append(row_copy)
    df = pd.DataFrame(frames)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index(["symbol", "date"])
    return df


SAMPLE_ROWS = [
    {"date": "2025-01-02", "open": 100.0, "high": 105.0,
     "low": 99.0, "close": 103.0, "volume": 1000000},
    {"date": "2025-01-03", "open": 103.0, "high": 108.0,
     "low": 102.0, "close": 107.0, "volume": 1500000},
]

SAMPLE_ROWS_ADJ = [
    {"date": "2025-01-02", "open": 99.5, "high": 104.5,
     "low": 98.5, "close": 102.5, "adjclose": 102.5, "volume": 1000000},
    {"date": "2025-01-03", "open": 102.5, "high": 107.5,
     "low": 101.5, "close": 106.5, "adjclose": 106.5, "volume": 1500000},
]


class TestYahooQueryAdapterBasic:

    def test_get_name(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        assert YahooQueryDataSource().get_name() == "YahooQuery"

    def test_supports_market(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource()
        assert source.supports_market("us") is True
        assert source.supports_market("hk") is True
        assert source.supports_market("jp") is True
        assert source.supports_market("kr") is True
        assert source.supports_market("cn") is False
        assert source.supports_market("sector") is False

    def test_default_params(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource()
        assert source._chunk_size == 100
        assert source._sleep_min == 0.5
        assert source._sleep_max == 2.0
        assert source._max_workers == 20
        assert source._MAX_RETRIES == 5
        assert source._RETRY_DELAY == 3.0

    def test_custom_params(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource(
            chunk_size=100, sleep_min=0.5, sleep_max=2.0, max_workers=10,
        )
        assert source._chunk_size == 100
        assert source._sleep_min == 0.5
        assert source._sleep_max == 2.0
        assert source._max_workers == 10


class TestYahooQuerySymbolMapping:

    def test_us_stock_no_suffix(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        from quantflow.data.base import StockCode
        source = YahooQueryDataSource()
        code = StockCode(code="AAPL", exchange="US")
        assert source._get_yahooquery_symbol(code) == "AAPL"

    def test_hk_stock_suffix(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        from quantflow.data.base import StockCode
        source = YahooQueryDataSource()
        code = StockCode(code="00700", exchange="HK")
        assert source._get_yahooquery_symbol(code) == "0700.HK"

    def test_hk_stock_short_code(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        from quantflow.data.base import StockCode
        source = YahooQueryDataSource()
        code = StockCode(code="09660", exchange="HK")
        assert source._get_yahooquery_symbol(code) == "9660.HK"

    def test_hk_stock_4digit(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        from quantflow.data.base import StockCode
        source = YahooQueryDataSource()
        code = StockCode(code="01234", exchange="HK")
        assert source._get_yahooquery_symbol(code) == "1234.HK"

    def test_kr_stock_suffix(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        from quantflow.data.base import StockCode
        source = YahooQueryDataSource()
        code = StockCode(code="000660", exchange="KR")
        assert source._get_yahooquery_symbol(code) == "000660.KS"

    def test_jp_stock_suffix(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        from quantflow.data.base import StockCode
        source = YahooQueryDataSource()
        code = StockCode(code="8035", exchange="JP")
        assert source._get_yahooquery_symbol(code) == "8035.T"


class TestYahooQueryNormalizeSingle:

    def test_basic_normalization(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource()
        raw = _make_multiindex_df({"AAPL": SAMPLE_ROWS})
        result = source._normalize_single(raw, adj_ohlc=False)
        assert list(result.columns) == ["date", "open", "high", "low", "close", "volume"]
        assert len(result) == 2

    def test_empty_input(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource()
        result = source._normalize_single(pd.DataFrame(), adj_ohlc=False)
        assert result.empty

    def test_adj_ohlc_replaces_close(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource()
        raw = _make_multiindex_df({"AAPL": SAMPLE_ROWS_ADJ}, adj_ohlc=True)
        result = source._normalize_single(raw, adj_ohlc=True)
        assert "adjclose" not in result.columns
        assert "close" in result.columns

    def test_no_adj_ohlc_drops_adjclose(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource()
        raw = _make_multiindex_df({"AAPL": SAMPLE_ROWS_ADJ}, adj_ohlc=True)
        result = source._normalize_single(raw, adj_ohlc=False)
        assert "adjclose" not in result.columns
        assert "close" in result.columns


class TestYahooQueryBatchFetch:

    def test_empty_input(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource()
        assert source.fetch_batch_ohlcv([], "2025-01-01", "2025-12-31") == {}

    def test_returns_dict_with_correct_keys(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.history.return_value = _make_multiindex_df({
            "AAPL": SAMPLE_ROWS,
        })
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("time.sleep", lambda d: None)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        codes = [
            StockCode(code="AAPL", exchange="US"),
            StockCode(code="MSFT", exchange="US"),
        ]
        source = YahooQueryDataSource()
        with patch("yahooquery.Ticker", mock_ticker_cls):
            result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")

        assert "AAPL.US" in result
        assert "MSFT.US" in result

    def test_dataframe_columns_format(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.history.return_value = _make_multiindex_df({
            "AAPL": SAMPLE_ROWS,
        })
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("time.sleep", lambda d: None)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        codes = [StockCode(code="AAPL", exchange="US")]
        source = YahooQueryDataSource()
        with patch("yahooquery.Ticker", mock_ticker_cls):
            result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")

        expected_cols = ["date", "open", "high", "low", "close", "volume"]
        assert list(result["AAPL.US"].columns) == expected_cols

    def test_exception_returns_empty(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.history.side_effect = Exception("Network error")
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("time.sleep", lambda d: None)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        codes = [StockCode(code="AAPL", exchange="US")]
        source = YahooQueryDataSource()
        with patch("yahooquery.Ticker", mock_ticker_cls):
            result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")
        assert result == {}

    def test_empty_response_returns_empty(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("time.sleep", lambda d: None)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        codes = [StockCode(code="AAPL", exchange="US")]
        source = YahooQueryDataSource()
        with patch("yahooquery.Ticker", mock_ticker_cls):
            result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")
        assert result == {}

    def test_sequential_per_ticker_fetch(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        instance = MagicMock()
        instance.history.return_value = _make_multiindex_df({
            "TICK": SAMPLE_ROWS,
        })
        mock_ticker_cls.return_value = instance
        monkeypatch.setattr("time.sleep", lambda d: None)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        codes = [StockCode(code=f"TICK{i:03d}", exchange="US") for i in range(5)]
        source = YahooQueryDataSource(sleep_min=0, sleep_max=0)
        with patch("yahooquery.Ticker", mock_ticker_cls):
            result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")

        assert mock_ticker_cls.call_count == 5
        assert len(result) == 5


class TestYahooQuerySingleFetch:

    def test_fetch_ohlcv_success(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.history.return_value = _make_multiindex_df({
            "AAPL": SAMPLE_ROWS,
        })
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("yahooquery.Ticker", mock_ticker_cls)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        source = YahooQueryDataSource()
        code = StockCode(code="AAPL", exchange="US")
        result = source.fetch_ohlcv(code, "2025-01-01", "2025-12-31")

        assert not result.empty
        assert list(result.columns) == ["date", "open", "high", "low", "close", "volume"]
        assert len(result) == 2

    def test_fetch_ohlcv_empty(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("yahooquery.Ticker", mock_ticker_cls)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        source = YahooQueryDataSource()
        code = StockCode(code="INVALID", exchange="US")
        result = source.fetch_ohlcv(code, "2025-01-01", "2025-12-31")
        assert result.empty

    def test_fetch_ohlcv_adj_ohlc_true(self, monkeypatch):
        captured_kwargs = {}

        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()

        def mock_history(**kwargs):
            captured_kwargs.update(kwargs)
            return _make_multiindex_df({"AAPL": SAMPLE_ROWS_ADJ}, adj_ohlc=True)

        mock_instance.history = mock_history
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("yahooquery.Ticker", mock_ticker_cls)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        source = YahooQueryDataSource()
        code = StockCode(code="AAPL", exchange="US")
        result = source.fetch_ohlcv(code, "2025-01-01", "2025-12-31", adjust="qfq")

        assert captured_kwargs.get("adj_ohlc") is True
        assert "adjclose" not in result.columns


class TestYahooQueryFundamental:

    def test_fetch_fundamental_success(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.key_stats = {
            "AAPL": {"forwardPE": 28.5, "priceToBook": 45.0},
        }
        mock_instance.summary_detail = {
            "AAPL": {"marketCap": 3000000000000, "trailingPE": 32.0},
        }
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("yahooquery.Ticker", mock_ticker_cls)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        source = YahooQueryDataSource()
        code = StockCode(code="AAPL", exchange="US")
        result = source.fetch_fundamental(code)

        assert result is not None
        assert result.total_mv == 3000000000000
        assert result.pe_ttm == 32.0
        assert result.pb == 45.0

    def test_fetch_fundamental_fallback_pe(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.key_stats = {
            "AAPL": {"forwardPE": 28.5},
        }
        mock_instance.summary_detail = {
            "AAPL": {"marketCap": 3000000000000},
        }
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("yahooquery.Ticker", mock_ticker_cls)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        source = YahooQueryDataSource()
        code = StockCode(code="AAPL", exchange="US")
        result = source.fetch_fundamental(code)

        assert result is not None
        assert result.pe_ttm == 28.5

    def test_fetch_fundamental_exception(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        type(mock_instance).key_stats = property(
            lambda self: (_ for _ in ()).throw(Exception("API error"))
        )
        mock_instance.summary_detail = {}
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("yahooquery.Ticker", mock_ticker_cls)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        source = YahooQueryDataSource()
        code = StockCode(code="AAPL", exchange="US")
        result = source.fetch_fundamental(code)
        assert result is None


class TestYahooQueryJitterSleep:

    def test_jitter_sleep_range(self):
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource
        source = YahooQueryDataSource(sleep_min=0.5, sleep_max=2.0)
        dur = source._jitter_sleep()
        assert 0.4 <= dur <= 2.1


class TestYahooQueryRetry:

    def test_retry_on_keyerror(self, monkeypatch):
        call_count = 0
        mock_ticker_cls = MagicMock()

        def make_instance(*args, **kwargs):
            nonlocal call_count
            mock = MagicMock()

            def mock_history(**kw):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise KeyError("AAPL")
                return _make_multiindex_df({"AAPL": SAMPLE_ROWS})

            mock.history = mock_history
            return mock

        mock_ticker_cls.side_effect = make_instance
        monkeypatch.setattr("time.sleep", lambda d: None)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        codes = [StockCode(code="AAPL", exchange="US")]
        source = YahooQueryDataSource()
        with patch("yahooquery.Ticker", mock_ticker_cls):
            result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")

        assert "AAPL.US" in result
        assert call_count == 3

    def test_retry_exhausted(self, monkeypatch):
        mock_ticker_cls = MagicMock()
        mock_instance = MagicMock()
        mock_instance.history.side_effect = KeyError("AAPL")
        mock_ticker_cls.return_value = mock_instance
        monkeypatch.setattr("time.sleep", lambda d: None)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        codes = [StockCode(code="AAPL", exchange="US")]
        source = YahooQueryDataSource()
        with patch("yahooquery.Ticker", mock_ticker_cls):
            result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")
        assert result == {}

    def test_mixed_success_and_failure(self, monkeypatch):
        call_map = {"AAPL": 0, "MSFT": 0}
        mock_ticker_cls = MagicMock()

        def make_instance(sym, **kwargs):
            mock = MagicMock()

            def mock_history(**kw):
                call_map[sym] += 1
                if sym == "MSFT" and call_map[sym] <= 2:
                    raise KeyError("MSFT")
                return _make_multiindex_df({sym: SAMPLE_ROWS})

            mock.history = mock_history
            return mock

        mock_ticker_cls.side_effect = make_instance
        monkeypatch.setattr("time.sleep", lambda d: None)

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yahooquery import YahooQueryDataSource

        codes = [
            StockCode(code="AAPL", exchange="US"),
            StockCode(code="MSFT", exchange="US"),
        ]
        source = YahooQueryDataSource()
        with patch("yahooquery.Ticker", mock_ticker_cls):
            result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")

        assert "AAPL.US" in result
        assert "MSFT.US" in result
        assert call_map["AAPL"] == 1
        assert call_map["MSFT"] == 3
