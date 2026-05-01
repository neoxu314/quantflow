"""Tests for DataSourceFactory."""

import pytest
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