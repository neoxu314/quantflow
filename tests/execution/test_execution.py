"""Tests for execution layer."""

import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

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

    def test_defaults(self):
        code = StockCode.from_standard("NVDA.US")
        item = WatchlistItem(code=code)
        assert item.weight == 1.0
        assert item.tags == []
        assert item.notes == ""

    def test_to_dict(self):
        code = StockCode.from_standard("002594.SZ", name="BYD")
        item = WatchlistItem(code=code, weight=1.5, tags=["ai", "ev"], notes="strong momentum")
        d = item.to_dict()
        assert d["code"] == "002594.SZ"
        assert d["name"] == "BYD"
        assert d["weight"] == 1.5
        assert d["tags"] == ["ai", "ev"]
        assert d["notes"] == "strong momentum"

    def test_from_dict(self):
        data = {
            "code": "600519.SH",
            "name": "Moutai",
            "weight": 2.0,
            "tags": ["blue_chip"],
            "notes": "premium",
        }
        item = WatchlistItem.from_dict(data)
        assert item.code.standard == "600519.SH"
        assert item.code.name == "Moutai"
        assert item.weight == 2.0
        assert item.tags == ["blue_chip"]
        assert item.notes == "premium"

    def test_from_dict_minimal(self):
        data = {"code": "AAPL.US"}
        item = WatchlistItem.from_dict(data)
        assert item.code.standard == "AAPL.US"
        assert item.weight == 1.0
        assert item.tags == []
        assert item.notes == ""


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

    def test_description(self):
        wl = Watchlist(name="portfolio", description="A-share value stocks")
        assert wl.description == "A-share value stocks"

    def test_empty_items_defaults(self):
        wl = Watchlist(name="empty")
        assert wl.items == []

    # --- get_codes ---

    def test_get_codes(self, sample_watchlist):
        extra = WatchlistItem(code=StockCode.from_standard("600519.SH"))
        sample_watchlist.add_item(extra)
        codes = sample_watchlist.get_codes()
        assert len(codes) == 2
        assert codes[0].standard == "600000.SH"
        assert codes[1].standard == "600519.SH"

    def test_get_codes_empty(self):
        wl = Watchlist(name="empty")
        assert wl.get_codes() == []

    # --- filter_by_tags ---

    def test_filter_by_tags_single(self):
        items = [
            WatchlistItem(code=StockCode.from_standard("600000.SH"), tags=["bank"]),
            WatchlistItem(code=StockCode.from_standard("600519.SH"), tags=["liquor"]),
            WatchlistItem(code=StockCode.from_standard("002594.SZ"), tags=["ev", "tech"]),
        ]
        wl = Watchlist(name="tagged", items=items)
        result = wl.filter_by_tags(["bank"])
        assert len(result) == 1
        assert result[0].code.standard == "600000.SH"

    def test_filter_by_tags_multiple(self):
        items = [
            WatchlistItem(code=StockCode.from_standard("600000.SH"), tags=["bank"]),
            WatchlistItem(code=StockCode.from_standard("002594.SZ"), tags=["ev", "tech"]),
        ]
        wl = Watchlist(name="tagged", items=items)
        result = wl.filter_by_tags(["tech", "bank"])
        assert len(result) == 2

    def test_filter_by_tags_no_match(self):
        items = [WatchlistItem(code=StockCode.from_standard("600000.SH"), tags=["bank"])]
        wl = Watchlist(name="tagged", items=items)
        result = wl.filter_by_tags(["nonexistent"])
        assert result == []

    # --- YAML save/load ---

    def test_save_load_yaml_full(self, sample_watchlist):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name

        sample_watchlist.description = "YAML test list"
        sample_watchlist.save(path)
        loaded = Watchlist.load(path)
        assert loaded.name == "test"
        assert loaded.description == "YAML test list"
        assert len(loaded.items) == 1
        assert loaded.items[0].code.standard == "600000.SH"
        Path(path).unlink()

    # --- JSON save/load ---

    def test_save_load_json(self):
        items = [WatchlistItem(code=StockCode.from_standard("NVDA.US", name="Nvidia"), tags=["ai"])]
        wl = Watchlist(name="json_test", items=items, description="JSON format test")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        wl.save(path)
        loaded = Watchlist.load(path)
        assert loaded.name == "json_test"
        assert loaded.description == "JSON format test"
        assert len(loaded.items) == 1
        assert loaded.items[0].code.standard == "NVDA.US"
        assert loaded.items[0].tags == ["ai"]
        Path(path).unlink()

    def test_to_dict_full(self, sample_watchlist):
        sample_watchlist.description = "Full dict test"
        d = sample_watchlist.to_dict()
        assert d["name"] == "test"
        assert d["description"] == "Full dict test"
        assert len(d["items"]) == 1
        assert d["items"][0]["code"] == "600000.SH"

    def test_from_dict_full(self):
        data = {
            "name": "import_test",
            "description": "Imported list",
            "items": [
                {
                    "code": "TSLA.US",
                    "name": "Tesla",
                    "weight": 1.0,
                    "tags": ["ev"],
                    "notes": "",
                }
            ],
        }
        wl = Watchlist.from_dict(data)
        assert wl.name == "import_test"
        assert wl.description == "Imported list"
        assert len(wl.items) == 1
        assert wl.items[0].code.standard == "TSLA.US"

    def test_from_dict_empty_items(self):
        data = {"name": "empty", "description": ""}
        wl = Watchlist.from_dict(data)
        assert wl.items == []

    def test_load_missing_file(self):
        with pytest.raises(FileNotFoundError):
            Watchlist.load("/nonexistent/path.yaml")

    # --- add_item duplicates ---

    def test_add_item_replaces_duplicate(self):
        item1 = WatchlistItem(code=StockCode.from_standard("600000.SH"), weight=1.0, tags=["old"])
        wl = Watchlist(name="dup_test", items=[item1])

        item2 = WatchlistItem(code=StockCode.from_standard("600000.SH"), weight=2.0, tags=["new"])
        wl.add_item(item2)

        assert len(wl.items) == 1
        assert wl.items[0].weight == 2.0
        assert wl.items[0].tags == ["new"]
