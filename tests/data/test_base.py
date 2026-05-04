"""Tests for data layer base classes."""

import pytest
import pandas as pd
from quantflow.data.base import StockCode, FundamentalData, DataSourceBase, SectorDataSource


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


class TestDataSourceBaseContract:
    """Concrete tests for the abstract DataSourceBase contract."""

    class _ConcreteDataSource(DataSourceBase):
        def fetch_ohlcv(self, code: StockCode, start_date: str, end_date: str, period: str = "d", adjust: str = "qfq") -> pd.DataFrame:
            # Minimal DataFrame with required columns
            df = pd.DataFrame({
                "date": [start_date],
                "open": [1.0],
                "high": [1.1],
                "low": [0.9],
                "close": [1.0],
                "volume": [1000],
            })
            return df

        def get_name(self) -> str:
            return "ConcreteDataSource"

        def supports_market(self, market: str) -> bool:
            return market in {"cn", "hk", "us", "jp", "kr", "sector"}

    def test_abstract_class_instantiation(self):
        # DataSourceBase should be abstract and cannot be instantiated
        with pytest.raises(TypeError):
            DataSourceBase()

    def test_fetch_ohlcv_signature_and_data(self):
        ds = self._ConcreteDataSource()
        code = StockCode(code="000001", exchange="SZ")
        df = ds.fetch_ohlcv(code, "2020-01-01", "2020-01-31", period="d", adjust="qfq")
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]

    def test_get_name(self):
        ds = self._ConcreteDataSource()
        assert isinstance(ds.get_name(), str)

    def test_supports_market_variants(self):
        ds = self._ConcreteDataSource()
        for m in ["cn", "hk", "us", "jp", "kr", "sector"]:
            assert ds.supports_market(m) is True
        assert ds.supports_market("eu") is False

    def test_fetch_fundamental_default_none(self):
        ds = self._ConcreteDataSource()
        code = StockCode(code="000001", exchange="SZ")
        assert ds.fetch_fundamental(code) is None

    def test_supported_periods_and_adjusts(self):
        ds = self._ConcreteDataSource()
        assert ds.get_supported_periods() == ["d", "w", "m", "y"]
        assert ds.get_supported_adjusts() == ["qfq", "hfq", "none"]

    def test_subclass_instantiation(self):
        # Ensure the concrete subclass can be instantiated cleanly
        ds = self._ConcreteDataSource()
        assert isinstance(ds, DataSourceBase)


class TestSectorDataSourceContract:
    """Concrete tests for the abstract SectorDataSource contract."""

    class _ConcreteSectorDataSource(SectorDataSource):
        def get_industry_list(self) -> pd.DataFrame:
            return pd.DataFrame({"code": ["01", "02"], "name": ["Industry1", "Industry2"]})

        def get_industry_constituents(self, industry_code: str) -> list:
            if industry_code == "01":
                return [StockCode("000001", "SZ"), StockCode("600000", "SH")]
            return [StockCode("000002", "SZ")]

        def get_concept_list(self) -> pd.DataFrame:
            return pd.DataFrame({"code": ["C01", "C02"], "name": ["Concept1", "Concept2"]})

        def get_concept_constituents(self, concept_code: str) -> list:
            if concept_code == "C01":
                return [StockCode("000001", "SZ")]
            return [StockCode("000005", "SH")]

    def test_abstract_sector_instantiate(self):
        with pytest.raises(TypeError):
            SectorDataSource()

    def test_concrete_sector_functions(self):
        ds = self._ConcreteSectorDataSource()
        ind_list = ds.get_industry_list()
        assert isinstance(ind_list, pd.DataFrame)
        constituents = ds.get_industry_constituents("01")
        assert isinstance(constituents, list)
        assert all(isinstance(c, StockCode) for c in constituents)
        conc_list = ds.get_concept_list()
        assert isinstance(conc_list, pd.DataFrame)
        conc_constituents = ds.get_concept_constituents("C01")
        assert isinstance(conc_constituents, list)
        assert all(isinstance(c, StockCode) for c in conc_constituents)
