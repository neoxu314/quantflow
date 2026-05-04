"""Tests for Storage and ExecutionResultItem."""

import json
import pytest
import tempfile
from pathlib import Path

from quantflow.execution.storage import Storage, ExecutionResultItem


class TestExecutionResultItem:
    def test_defaults(self):
        item = ExecutionResultItem(code="600000.SH")
        assert item.code == "600000.SH"
        assert item.name == ""
        assert item.buy_signals == 0
        assert item.sell_signals == 0
        assert item.reasons == []
        assert item.matched_buy_strategies == []
        assert item.matched_sell_strategies == []

    def test_full(self):
        item = ExecutionResultItem(
            code="002594.SZ",
            name="BYD",
            buy_signals=2,
            sell_signals=1,
            reasons=["Oversold J=14.2 in bull channel", "Price within channel"],
            matched_buy_strategies=["DailyBullishOversold", "DailyBullishMidRange"],
            matched_sell_strategies=["KDJ_DeadCross"],
        )
        assert item.code == "002594.SZ"
        assert item.buy_signals == 2
        assert item.sell_signals == 1

    def test_to_dict(self):
        item = ExecutionResultItem(
            code="NVDA.US",
            name="Nvidia",
            buy_signals=1,
            sell_signals=0,
            reasons=["Signal reason"],
            matched_buy_strategies=["DailyBullishOversold"],
        )
        d = item.to_dict()

        assert d["code"] == "NVDA.US"
        assert d["name"] == "Nvidia"
        assert d["buy_signals"] == 1
        assert d["sell_signals"] == 0
        assert d["reasons"] == ["Signal reason"]
        assert d["matched_buy_strategies"] == ["DailyBullishOversold"]
        assert d["matched_sell_strategies"] == []
        assert "timestamp" in d
        # timestamp should be ISO 8601
        assert isinstance(d["timestamp"], str)
        assert "T" in d["timestamp"]


class TestStorage:
    def test_save_results_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(base_path=tmpdir)
            path = f"{tmpdir}/empty.json"
            storage.save_results(path, [])

            with open(path) as f:
                data = json.load(f)
            assert data == []

    def test_save_results_single_item(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(base_path=tmpdir)
            items = [
                ExecutionResultItem(
                    code="600000.SH",
                    name="Pudong Bank",
                    buy_signals=1,
                    reasons=["test reason"],
                    matched_buy_strategies=["TestStrategy"],
                )
            ]
            path = f"{tmpdir}/single.json"
            storage.save_results(path, items)

            with open(path) as f:
                data = json.load(f)
            assert len(data) == 1
            assert data[0]["code"] == "600000.SH"
            assert data[0]["name"] == "Pudong Bank"
            assert data[0]["buy_signals"] == 1

    def test_save_results_multiple_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(base_path=tmpdir)
            items = [
                ExecutionResultItem(code="600000.SH", buy_signals=1),
                ExecutionResultItem(code="NVDA.US", buy_signals=2, sell_signals=1),
                ExecutionResultItem(code="00700.HK", sell_signals=1),
            ]
            path = f"{tmpdir}/multi.json"
            storage.save_results(path, items)

            with open(path) as f:
                data = json.load(f)
            assert len(data) == 3
            codes = [d["code"] for d in data]
            assert "600000.SH" in codes
            assert "NVDA.US" in codes
            assert "00700.HK" in codes

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(base_path=tmpdir)
            deep_path = f"{tmpdir}/deep/nested/dir/result.json"
            storage.save_results(deep_path, [])

            assert Path(deep_path).exists()

    def test_save_results_empty_list_is_valid_json(self):
        """Even when no signals, should write valid JSON array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Storage(base_path=tmpdir)
            path = f"{tmpdir}/no_signals.json"
            storage.save_results(path, [])

            with open(path) as f:
                raw = f.read()
            assert raw.strip() == "[]"
