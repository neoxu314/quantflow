"""Tests for BaoStock adapter."""

import pytest
from quantflow.data.base import StockCode
from quantflow.data.adapters.baostock import BaoStockDataSource


@pytest.fixture
def baostock_source():
    return BaoStockDataSource(adjust="qfq")


class TestBaoStockDataSource:
    
    def test_supports_cn_market(self, baostock_source):
        assert baostock_source.supports_market("cn")
        assert baostock_source.supports_market("A股")
        assert not baostock_source.supports_market("us")
    
    def test_get_name(self, baostock_source):
        assert baostock_source.get_name() == "BaoStock"
    
    def test_adjust_map(self, baostock_source):
        assert baostock_source.ADJUST_MAP["qfq"] == "2"
        assert baostock_source.ADJUST_MAP["hfq"] == "1"
        assert baostock_source.ADJUST_MAP["none"] == "3"