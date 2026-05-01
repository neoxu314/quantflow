"""Tests for execution layer."""

import pytest
import tempfile
from pathlib import Path

from quantflow.data.base import StockCode
from quantflow.execution.watchlist import Watchlist, WatchlistItem


@pytest.fixture
def sample_watchlist():
    items = [
        WatchlistItem(code=StockCode.from_standard("600000.SH"), weight=1.0),
    ]
    return Watchlist(name="test", items=items)


class TestWatchlistItem:
    def test_creation(self):
        code = StockCode.from_standard("600000.SH")
        item = WatchlistItem(code=code, weight=1.5)
        assert item.code.standard == "600000.SH"
        assert item.weight == 1.5


class TestWatchlist:
    def test_creation(self, sample_watchlist):
        assert sample_watchlist.name == "test"
        assert len(sample_watchlist.items) == 1

    def test_add_remove(self, sample_watchlist):
        new_item = WatchlistItem(code=StockCode.from_standard("600519.SH"))
        sample_watchlist.add_item(new_item)
        assert len(sample_watchlist.items) == 2
        
        sample_watchlist.remove_item(new_item.code)
        assert len(sample_watchlist.items) == 1

    def test_save_and_load(self, sample_watchlist):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name
        
        sample_watchlist.save(path)
        loaded = Watchlist.load(path)
        assert loaded.name == sample_watchlist.name
        Path(path).unlink()