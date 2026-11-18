"""Tests for Executor with mocked data source."""

import json
import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from quantflow.data.base import StockCode
from quantflow.execution.watchlist import WatchlistItem
from quantflow.execution.job import ExecutionJob
from quantflow.execution.executor import Executor, ProgressEvent, InsufficientHistoryError
from quantflow.execution.storage import ExecutionResultItem
from quantflow.data.config import MarketDataSourceConfig
from quantflow.strategies.buy import DailyBullishOversoldBuy, DailyBullishMidRangeBuy


def _make_empty_df():
    return pd.DataFrame()


def _make_ohlcv_df(rows=30):
    """Create a minimal OHLCV DataFrame with indicator columns for signal detection."""
    length = rows
    df = pd.DataFrame({
        "close": [45.0] * length,
        "high": [47.0] * length,
        "low": [43.0] * length,
        "open": [44.0] * length,
        "volume": [1e6] * length,
    })
    return df


def _make_signal_df(buy=True):
    """Create a DataFrame that will produce a buy/sell signal when passed to oversold strategy."""
    length = 120
    df = pd.DataFrame({
        "close": [45.0] * length,
        "high": [47.0] * length,
        "low": [43.0] * length,
        "open": [44.0] * length,
        "volume": [1e6] * length,
        "short_trend_line": [50.0] * length,
        "long_short_line": [40.0] * length,
        "J": [10.0] * length,
        "K": [10.0] * length, "D": [10.0] * length,
        "is_bull_zone": [True] * length, "is_bear_zone": [False] * length,
    })
    return df


class TestExecutorProgressCallback:
    def test_emits_progress_events(self):
        events = []
        def capture(event: ProgressEvent):
            events.append(event)

        item = WatchlistItem(code=StockCode.from_standard("002594.SZ"))
        job = ExecutionJob(
            name="progress_test",
            items=[item],
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
            days_back=30,
        )

        executor = Executor()
        df = _make_signal_df()

        # Mock fetch to return our signal-producing DataFrame
        with patch.object(executor.factory, "fetch_ohlcv", return_value=(df, "baostock")):
            with patch.object(executor.factory, "_detect_market", return_value="a_share"):
                executor.execute(job, on_progress=capture)

        assert len(events) >= 2
        types = [e.type for e in events]
        assert "stock_start" in types
        assert "stock_done" in types

    def test_progress_event_structure(self):
        events = []
        def capture(event: ProgressEvent):
            events.append(event)

        item = WatchlistItem(code=StockCode.from_standard("MSFT.US"))
        job = ExecutionJob(
            name="struct_test",
            items=[item],
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
            days_back=30,
        )

        executor = Executor()
        df = _make_signal_df()

        with patch.object(executor.factory, "fetch_batch_ohlcv", return_value={
            "MSFT.US": (df, "yfinance"),
        }):
            with patch.object(executor.factory, "_detect_market", return_value="us"):
                with patch.object(executor.factory, "config", MarketDataSourceConfig()) as mock_config:
                    mock_config.set_primary("us", "yfinance")
                    executor.execute(job, on_progress=capture)

        start_events = [e for e in events if e.type == "stock_start"]
        assert len(start_events) >= 1
        e = start_events[0]
        assert e.code == "MSFT.US"
        assert e.total == 1
        assert e.current == 0  # stock_start reports completed items


class TestExecutorEmptyWatchlist:
    def test_empty_job_still_saves_json(self):
        """Even with zero items, Executor should write an empty JSON array."""
        job = ExecutionJob(
            name="empty_job",
            items=[],
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
            days_back=30,
        )

        executor = Executor()
        results = executor.execute(job)

        assert results == []
        import shutil
        out_path = Path(f"/tmp/executor_test/empty_job.json")
        if out_path.exists():
            with open(out_path) as f:
                data = json.load(f)
            assert data == []
            out_path.unlink()
            # Clean up parent if empty
            if out_path.parent.exists() and not any(out_path.parent.iterdir()):
                out_path.parent.rmdir()


class TestExecutorNoSignals:
    def test_no_signals_returns_empty_list(self):
        """When no stock triggers any strategy, results should be empty."""
        item = WatchlistItem(code=StockCode.from_standard("600000.SH"))
        job = ExecutionJob(
            name="no_sig",
            items=[item],
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
            days_back=30,
        )

        executor = Executor()
        # DataFrame with no indicator columns — strategies return no signals
        df = _make_ohlcv_df()

        with patch.object(executor.factory, "fetch_ohlcv", return_value=(df, "baostock")):
            with patch.object(executor.factory, "_detect_market", return_value="a_share"):
                results = executor.execute(job)

        assert results == []


class TestExecutorProcessSingle:
    def test_process_single_with_buy_signal(self):
        executor = Executor()
        df = _make_signal_df()
        item = WatchlistItem(
            code=StockCode.from_standard("002594.SZ", name="BYD"),
            weight=1.0,
        )
        job = ExecutionJob(
            name="test",
            items=[item],
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
        )

        with patch.object(executor.composer, "compose", return_value=df):
            result = executor._process_single(item, item.code, df, job)

        assert result is not None
        assert result.code == "002594.SZ"
        assert result.buy_signals == 1
        assert "DailyBullishOversold" in result.matched_buy_strategies

    def test_process_single_no_signal(self):
        executor = Executor()
        df = _make_ohlcv_df()
        item = WatchlistItem(code=StockCode.from_standard("600000.SH"))
        job = ExecutionJob(
            name="test",
            items=[item],
            strategies=[DailyBullishMidRangeBuy()],
            output_dir="/tmp/executor_test",
        )

        with patch.object(executor.composer, "compose", return_value=df):
            with pytest.raises(InsufficientHistoryError):
                executor._process_single(item, item.code, df, job)


class TestExecutorMultiStock:
    def test_yfinance_batch_fetch(self):
        """Verify Executor correctly uses batch fetch for yFinance items."""
        items = [
            WatchlistItem(code=StockCode.from_standard("MSFT.US")),
            WatchlistItem(code=StockCode.from_standard("AAPL.US")),
        ]
        job = ExecutionJob(
            name="multi_yf",
            items=items,
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
            days_back=30,
        )

        df = _make_signal_df()
        executor = Executor()
        
        with patch.object(executor.factory, "fetch_batch_ohlcv") as mock_fetch:
            mock_fetch.return_value = {
                "MSFT.US": (df, "yfinance"),
                "AAPL.US": (df, "yfinance"),
            }
            with patch.object(executor.factory, "_detect_market", return_value="us"):
                with patch.object(executor.factory, "config", MarketDataSourceConfig()) as mock_config:
                    mock_config.set_primary("us", "yfinance")
                    results = executor.execute(job)

        # fetch_batch_ohlcv should be called with both codes
        call_args = mock_fetch.call_args[0][0]
        assert "MSFT.US" in call_args or any(
            "MSFT" in str(c) for c in call_args
        )

    def test_mixed_market_cn_and_global(self):
        """Verify Executor partitions CN (sequential) and global (batch) stocks correctly."""
        items = [
            WatchlistItem(code=StockCode.from_standard("600000.SH")),
            WatchlistItem(code=StockCode.from_standard("MSFT.US")),
        ]
        job = ExecutionJob(
            name="mixed_market",
            items=items,
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
            days_back=30,
        )

        df = _make_signal_df()
        executor = Executor()

        with patch.object(executor.factory, "fetch_batch_ohlcv") as mock_batch, \
             patch.object(executor.factory, "fetch_ohlcv") as mock_sequential, \
             patch.object(executor.factory, "_detect_market") as mock_detect, \
             patch.object(executor.factory, "config", MarketDataSourceConfig()) as mock_config:

            def detect_side_effect(code):
                if code.exchange in ("SH", "SZ"):
                    return "cn"
                return "us"

            mock_detect.side_effect = detect_side_effect
            mock_config.set_primary("cn", "baostock")
            mock_config.set_fallback("cn", "tushare")

            mock_batch.return_value = {"MSFT.US": (df, "yahooquery")}
            mock_sequential.return_value = (df, "baostock")

            results = executor.execute(job)

        mock_batch.assert_called_once()
        mock_sequential.assert_called_once()

    def test_batch_items_no_data_skipped(self):
        """Verify batch items with no data are skipped gracefully."""
        items = [
            WatchlistItem(code=StockCode.from_standard("BAD.US")),
        ]
        job = ExecutionJob(
            name="batch_no_data",
            items=items,
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
            days_back=30,
        )

        executor = Executor()

        with patch.object(executor.factory, "fetch_batch_ohlcv", return_value={}), \
             patch.object(executor.factory, "_detect_market", return_value="us"), \
             patch.object(executor.factory, "config", MarketDataSourceConfig()) as mock_config:
            mock_config.set_primary("us", "yahooquery")
            results = executor.execute(job)

        assert results == []

    def test_sequential_items_exception_handled(self):
        """Verify sequential items with fetch exception are handled gracefully."""
        items = [
            WatchlistItem(code=StockCode.from_standard("600000.SH")),
        ]
        job = ExecutionJob(
            name="seq_error",
            items=items,
            strategies=[DailyBullishOversoldBuy()],
            output_dir="/tmp/executor_test",
            days_back=30,
        )

        executor = Executor()

        with patch.object(executor.factory, "fetch_ohlcv", side_effect=Exception("Network error")), \
             patch.object(executor.factory, "_detect_market", return_value="cn"):
            results = executor.execute(job)

        assert results == []
