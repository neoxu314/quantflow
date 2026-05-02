import pytest
import pandas as pd


def _make_multi_index_df(tickers_data):
    frames = []
    for ticker, rows in tickers_data.items():
        df = pd.DataFrame(rows)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        df.columns = pd.MultiIndex.from_product([[ticker], df.columns])
        frames.append(df)
    return pd.concat(frames, axis=1)


SAMPLE_ROWS = [
    {"date": "2025-01-02", "Open": 100.0, "High": 105.0,
     "Low": 99.0, "Close": 103.0, "Volume": 1000000},
    {"date": "2025-01-03", "Open": 103.0, "High": 108.0,
     "Low": 102.0, "Close": 107.0, "Volume": 1500000},
]


class TestYFinanceBatchFetch:

    def test_empty_input(self, monkeypatch):
        from quantflow.data.adapters.yfinance import YFinanceDataSource
        source = YFinanceDataSource()
        assert source.fetch_batch_ohlcv([], "2025-01-01", "2025-12-31") == {}

    def test_returns_dict_with_correct_keys(self, monkeypatch):
        import yfinance
        monkeypatch.setattr(yfinance, "download", lambda **kw: _make_multi_index_df({
            "AAPL": SAMPLE_ROWS,
            "MSFT": SAMPLE_ROWS,
        }))
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        codes = [
            StockCode(code="AAPL", exchange="US"),
            StockCode(code="MSFT", exchange="US"),
            StockCode(code="GOOG", exchange="US"),
        ]
        result = YFinanceDataSource().fetch_batch_ohlcv(
            codes, "2025-01-01", "2025-12-31"
        )

        assert "AAPL.US" in result
        assert "MSFT.US" in result
        assert "GOOG.US" not in result

    def test_dataframe_columns_match_single_fetch(self, monkeypatch):
        import yfinance
        monkeypatch.setattr(yfinance, "download", lambda **kw: _make_multi_index_df({
            "AAPL": SAMPLE_ROWS,
        }))
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        codes = [StockCode(code="AAPL", exchange="US")]
        result = YFinanceDataSource().fetch_batch_ohlcv(
            codes, "2025-01-01", "2025-12-31"
        )

        expected_cols = ["date", "open", "high", "low", "close", "volume"]
        assert list(result["AAPL.US"].columns) == expected_cols
        assert pd.api.types.is_datetime64_any_dtype(result["AAPL.US"]["date"])

    def test_empty_result_excluded(self, monkeypatch):
        import yfinance
        monkeypatch.setattr(yfinance, "download", lambda **kw: _make_multi_index_df({
            "AAPL": SAMPLE_ROWS,
            "DEL": [],
        }))
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        codes = [
            StockCode(code="AAPL", exchange="US"),
            StockCode(code="DEL", exchange="US"),
        ]
        result = YFinanceDataSource().fetch_batch_ohlcv(
            codes, "2025-01-01", "2025-12-31"
        )

        assert "AAPL.US" in result
        assert "DEL.US" not in result

    def test_download_exception_returns_empty(self, monkeypatch):
        import yfinance
        monkeypatch.setattr(yfinance, "download", lambda **kw: (_ for _ in ()).throw(Exception("Network error")))
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        codes = [StockCode(code="AAPL", exchange="US")]
        result = YFinanceDataSource().fetch_batch_ohlcv(
            codes, "2025-01-01", "2025-12-31"
        )
        assert result == {}


class TestYFinanceVersionCheck:

    def test_old_version(self, monkeypatch):
        import yfinance
        monkeypatch.setattr(yfinance, "__version__", "0.2.10")

        from quantflow.data.adapters.yfinance import YFinanceDataSource
        assert YFinanceDataSource.check_version() is False

    def test_new_version(self, monkeypatch):
        import yfinance
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.adapters.yfinance import YFinanceDataSource
        assert YFinanceDataSource.check_version() is True


class TestYFinanceChunking:
    """Tests for batch chunking behavior."""

    def test_chunk_size_respected(self, monkeypatch):
        """When tickers > chunk_size, download() should be called multiple times."""
        import yfinance

        download_calls = []

        def mock_download(**kw):
            download_calls.append(kw["tickers"][:])
            return _make_multi_index_df({
                t: SAMPLE_ROWS for t in kw["tickers"]
            })

        monkeypatch.setattr(yfinance, "download", mock_download)
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        codes = [StockCode(code=f"TICKER{i:03d}", exchange="US") for i in range(8)]
        # chunk_size=3, 8 tickers => 3 calls: [3, 3, 2]
        source = YFinanceDataSource(chunk_size=3, sleep_between_chunks=0)
        result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")

        assert len(download_calls) == 3
        assert len(download_calls[0]) == 3
        assert len(download_calls[1]) == 3
        assert len(download_calls[2]) == 2
        assert len(result) == 8

    def test_single_chunk_when_below_threshold(self, monkeypatch):
        """When tickers <= chunk_size, download() should be called once."""
        import yfinance

        download_calls = []

        def mock_download(**kw):
            download_calls.append(kw["tickers"][:])
            return _make_multi_index_df({
                t: SAMPLE_ROWS for t in kw["tickers"]
            })

        monkeypatch.setattr(yfinance, "download", mock_download)
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        codes = [
            StockCode(code="AAPL", exchange="US"),
            StockCode(code="MSFT", exchange="US"),
        ]
        source = YFinanceDataSource(chunk_size=10, sleep_between_chunks=0)
        result = source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")

        assert len(download_calls) == 1
        assert len(result) == 2

    def test_default_chunk_size_fallback(self, monkeypatch):
        """Default chunk_size should be 30 when not provided."""
        import yfinance

        monkeypatch.setattr(yfinance, "download", lambda **kw: _make_multi_index_df({
            t: SAMPLE_ROWS for t in kw["tickers"]
        }))
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.adapters.yfinance import YFinanceDataSource

        source = YFinanceDataSource()
        assert source._chunk_size == 30
        assert source._sleep_between_chunks == 15

    def test_timeout_parameter_passed(self, monkeypatch):
        """yf.download() should receive timeout=30."""
        import yfinance

        captured_timeout = None

        def mock_download(**kw):
            nonlocal captured_timeout
            captured_timeout = kw.get("timeout")
            return _make_multi_index_df({
                t: SAMPLE_ROWS for t in kw["tickers"]
            })

        monkeypatch.setattr(yfinance, "download", mock_download)
        monkeypatch.setattr(yfinance, "__version__", "0.2.40")

        from quantflow.data.base import StockCode
        from quantflow.data.adapters.yfinance import YFinanceDataSource

        codes = [StockCode(code="AAPL", exchange="US")]
        source = YFinanceDataSource(chunk_size=10, sleep_between_chunks=0)
        source.fetch_batch_ohlcv(codes, "2025-01-01", "2025-12-31")

        assert captured_timeout == 30
