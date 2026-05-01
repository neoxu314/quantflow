"""Tests for data layer base classes."""

import pytest
from quantflow.data.base import StockCode, FundamentalData


class TestStockCode:
    
    def test_standard_format(self):
        code = StockCode(code="600000", exchange="SH", name="浦发银行")
        assert code.standard == "600000.SH"
        assert code.baostock == "sh.600000"
    
    def test_from_standard(self):
        code = StockCode.from_standard("000001.SZ")
        assert code.code == "000001"
        assert code.exchange == "SZ"
    
    def test_from_baostock(self):
        code = StockCode.from_baostock("sh.600000")
        assert code.code == "600000"
        assert code.exchange == "SH"
    
    def test_str_repr(self):
        code = StockCode(code="AAPL", exchange="US")
        assert str(code) == "AAPL.US"


class TestFundamentalData:
    
    def test_defaults(self):
        data = FundamentalData()
        assert data.pe_ttm is None
        assert data.pb is None
    
    def test_with_values(self):
        data = FundamentalData(pe_ttm=15.5, pb=2.3, total_mv=1000000)
        assert data.pe_ttm == 15.5
        assert data.pb == 2.3
        assert data.total_mv == 1000000