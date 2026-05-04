import pytest
import pandas as pd
from unittest.mock import patch
from quantflow.data.adapters.akshare import AKShareDataSource, SectorClassification
from quantflow.data.base import StockCode


def test_sector_classification_values():
    # Ensure all 6 enumeration values exist and match expected strings
    values = [e.value for e in SectorClassification]
    assert len(values) == 6
    assert values == ["em", "ths", "sw", "sw_l1", "sw_l2", "sw_l3"]


def test_init_and_get_name():
    ds = AKShareDataSource("em")
    assert ds.get_name() == "AKShare-EM"
    ds2 = AKShareDataSource("sw_l3")
    assert ds2.get_name() == "AKShare-SW_L3"


def test_supports_market():
    ds = AKShareDataSource()
    # HK market supported
    assert ds.supports_market("hk")
    assert ds.supports_market("港股")
    # sector/class boards also considered market-like
    assert ds.supports_market("sector")
    assert ds.supports_market("板块")
    # unknown market should be unsupported
    assert not ds.supports_market("cn")


def test_normalize_classification_sw_to_sw_l3():
    ds = AKShareDataSource("sw")
    assert ds._normalize_classification() == "sw_l3"


def test_is_shenwan():
    ds_sw = AKShareDataSource("sw_l2")
    assert ds_sw._is_shenwan()
    ds_em = AKShareDataSource("em")
    assert not ds_em._is_shenwan()


def test_get_sw_level():
    ds1 = AKShareDataSource("sw_l1")
    assert ds1._get_sw_level() == "l1"
    ds3 = AKShareDataSource("sw_l3")
    assert ds3._get_sw_level() == "l3"


@patch("akshare.stock_hk_daily")
def test_fetch_ohlcv_hk_success(mock_stock_hk_daily):
    ds = AKShareDataSource("em")
    rows = {
        "date": ["2026-01-01", "2026-01-02"],
        "开盘": [1.0, 1.2],
        "最高": [1.5, 1.8],
        "最低": [0.9, 1.1],
        "收盘": [1.4, 1.7],
        "成交量": [100, 200],
    }
    mock_stock_hk_daily.return_value = pd.DataFrame(rows)

    code = StockCode(code="0005", exchange="HK")
    df = ds.fetch_ohlcv(code, "2026-01-01", "2026-01-02")
    assert list(df.columns) == ["date", "open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert isinstance(df.loc[0, "date"], pd.Timestamp)


def test_fetch_ohlcv_non_hk_raises():
    ds = AKShareDataSource("em")
    code = StockCode(code="0005", exchange="SZ")
    with pytest.raises(ValueError):
        ds.fetch_ohlcv(code, "2026-01-01", "2026-01-02")


@patch("akshare.stock_board_industry_name_em")
def test_get_industry_list_em(mock_em):
    mock_em.return_value = pd.DataFrame({"板块名称": ["行业A"], "板块代码": ["857371"]})
    ds = AKShareDataSource("em")
    df = ds.get_industry_list()
    assert list(df.columns) == ["name", "code"]
    assert df.iloc[0]["name"] == "行业A"


@patch("akshare.stock_board_industry_name_ths")
def test_get_industry_list_ths(mock_ths):
    mock_ths.return_value = pd.DataFrame({"行业名称": ["行业THS"], "行业代码": ["881121"]})
    ds = AKShareDataSource("ths")
    df = ds.get_industry_list()
    assert list(df.columns) == ["name", "code"]


@pytest.mark.parametrize("clf,fn_name", [
    ("sw_l1", "sw_index_first_info"),
    ("sw_l2", "sw_index_second_info"),
    ("sw_l3", "sw_index_third_info"),
])
def test_get_industry_list_sw_levels(monkeypatch, clf, fn_name):
    import akshare as ak
    fake_df = pd.DataFrame({"行业名称": ["SW"], "行业代码": ["857371"]})
    # Patch the target function to return our fake dataframe
    monkeypatch.setattr(ak, fn_name, lambda: fake_df)
    ds = AKShareDataSource(clf)
    df = ds.get_industry_list()
    assert list(df.columns) == ["name", "code"]


@patch("akshare.sw_index_third_cons")
def test_get_industry_constituents_sw_l3(mock_cons):
    df = pd.DataFrame({"代码": ["600000", "000001"]})
    mock_cons.return_value = df
    ds = AKShareDataSource("sw_l3")
    codes = ds.get_industry_constituents("857371.SI")
    assert [c.standard for c in codes] == ["600000.SH", "000001.SZ"]


@patch("akshare.stock_board_industry_cons_em")
def test_get_industry_constituents_em(mock_cons_em):
    df = pd.DataFrame({"代码": ["600000"]})
    mock_cons_em.return_value = df
    ds = AKShareDataSource("em")
    codes = ds.get_industry_constituents("857371")
    assert codes == [StockCode("600000", "SH")]


@patch("akshare.stock_board_concept_name_em")
def test_get_concept_list_em(mock_concept_em):
    df = pd.DataFrame({"板块名称": ["ConceptX"], "板块代码": ["857400"]})
    mock_concept_em.return_value = df
    ds = AKShareDataSource("em")
    res = ds.get_concept_list()
    assert set(res.columns) == {"code", "name"}
    assert res.iloc[0]["code"] == "857400"


def test_get_concept_list_sw_empty():
    ds = AKShareDataSource("sw_l3")
    res = ds.get_concept_list()
    assert set(res.columns) == {"code", "name"}
    assert res.empty


@patch("akshare.stock_board_concept_cons_em")
def test_get_concept_constituents_em(mock_cons_concept):
    df = pd.DataFrame({"代码": ["600000"]})
    mock_cons_concept.return_value = df
    ds = AKShareDataSource("em")
    codes = ds.get_concept_constituents("857400")
    assert codes == [StockCode("600000", "SH")]


@pytest.mark.parametrize("cls,expected_source", [
    ("em", "东方财富"),
    ("ths", "同花顺"),
    ("sw_l1", "申万一级"),
    ("sw_l2", "申万二级"),
    ("sw_l3", "申万三级"),
])
def test_classification_info_content(cls, expected_source):
    ds = AKShareDataSource(cls)
    info = ds.get_classification_info()
    assert info["classification"] == ds._normalize_classification()
    assert info["source"] == expected_source
    assert info["has_industry"] is True
    assert info["has_concept"] == (not ds._is_shenwan())


@patch("akshare.stock_board_industry_name_em")
def test_exception_handling_get_industry_list(mock_em):
    mock_em.side_effect = Exception("boom")
    ds = AKShareDataSource("em")
    df = ds.get_industry_list()
    assert df.empty


@patch("akshare.sw_index_third_cons")
def test_exception_handling_industry_constituents_sw(mock_cons):
    mock_cons.side_effect = Exception("boom")
    ds = AKShareDataSource("sw_l3")
    codes = ds.get_industry_constituents("857371.SI")
    assert codes == []


@patch("akshare.stock_board_concept_name_em")
def test_exception_handling_concept_list(mock_concept_em):
    mock_concept_em.side_effect = Exception("boom")
    ds = AKShareDataSource("em")
    df = ds.get_concept_list()
    assert df.empty


@patch("akshare.stock_board_concept_cons_em")
def test_exception_handling_concept_constituents(mock_concept_cons_em):
    mock_concept_cons_em.side_effect = Exception("boom")
    ds = AKShareDataSource("em")
    codes = ds.get_concept_constituents("857400")
    assert codes == []
