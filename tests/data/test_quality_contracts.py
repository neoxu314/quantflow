"""Offline adapter, calendar and fundamental provenance contracts."""
from unittest.mock import Mock

import pandas as pd
import pytest

from quantflow.config.loader import ConfigLoader
from quantflow.data import StockCode, DataSourceBase, FundamentalData
from quantflow.data.adapters.tushare import TushareDataSource
from quantflow.data.adapters.yfinance import YFinanceDataSource
from quantflow.data.adapters.yahooquery import YahooQueryDataSource
from quantflow.data.config import MarketDataSourceConfig
from quantflow.data.factory import DataSourceFactory
from quantflow.data.quality import last_completed_session, normalize_ohlcv, prepare_daily_frame


def sample():
    return pd.DataFrame({"date": ["2026-11-17", "2026-11-18"],
                         "open": [10., 11.], "high": [11., 12.], "low": [9., 10.],
                         "close": [10., 11.], "volume": [100., 200.]})


class FakeAdapter(DataSourceBase):
    def __init__(self, data):
        self.data = data
        self.calls = []
    def get_name(self):
        return "fake"
    def supports_market(self, market):
        return True
    def fetch_ohlcv(self, code, *args):
        self.calls.append(code.standard)
        return self.data.get(code.standard, pd.DataFrame())
    def fetch_batch_ohlcv(self, codes, *args):
        self.calls.append([c.standard for c in codes])
        return self.data


@pytest.mark.parametrize("missing", [None, pd.DataFrame()])
def test_partial_batch_fallback_only_fetches_missing_symbols(monkeypatch, missing):
    primary = FakeAdapter({"A.US": sample(), "B.US": missing})
    fallback = FakeAdapter({"B.US": sample()})
    factory = DataSourceFactory()
    monkeypatch.setattr(factory, "_get_adapter", lambda source: primary if source == "yahooquery" else fallback)
    got = factory.fetch_batch_ohlcv([StockCode("A","US"),StockCode("B","US")],
                                   "2026-11-17","2026-11-18")
    assert set(got) == {"A.US", "B.US"}
    assert got["B.US"][1] == "yfinance"
    assert fallback.calls == [["B.US"]]


@pytest.mark.parametrize("batch", [False, True])
def test_stale_history_uses_only_newer_fallback_and_keeps_its_source(monkeypatch, batch):
    complete = sample()
    stale = complete.iloc[:1]
    code = StockCode("A", "US")
    primary = FakeAdapter({code.standard: stale})
    fallback = FakeAdapter({code.standard: complete})
    factory = DataSourceFactory()
    monkeypatch.setattr(
        factory, "_get_adapter", lambda source: primary if source == "yahooquery" else fallback
    )

    def fetch():
        args = ("2026-11-17", "2026-11-18")
        if batch:
            return factory.fetch_batch_ohlcv([code], *args, require_end_session=True)[code.standard]
        return factory.fetch_ohlcv(code, *args, require_end_session=True)

    assert fetch()[1] == "yfinance"
    fallback.data[code.standard] = stale
    result, source = fetch()
    assert source == result.attrs["source"] == "yahooquery"
    assert result.date.iloc[-1] == pd.Timestamp("2026-11-17")


def test_primary_initialization_error_does_not_prevent_batch_fallback(monkeypatch):
    code = StockCode("A", "US")
    fallback = FakeAdapter({code.standard: sample()})
    factory = DataSourceFactory()

    def adapter(source):
        if source == "yahooquery":
            raise RuntimeError("primary initialization failed")
        return fallback

    monkeypatch.setattr(factory, "_get_adapter", adapter)
    result = factory.fetch_batch_ohlcv([code], "2026-11-17", "2026-11-18")
    assert result[code.standard][1] == "yfinance"
    assert factory.failures[code.standard] == ["yahooquery: primary initialization failed"]


@pytest.mark.parametrize("column,value", [("date",None), ("close",float('nan')), ("volume",-1), ("high",1)])
def test_invalid_frames_are_rejected(column, value):
    df = sample()
    df.loc[1,column] = value
    with pytest.raises(ValueError):
        normalize_ohlcv(df)


def test_latest_date_uses_column_and_order_is_normalized():
    df = sample().iloc[::-1]
    assert DataSourceFactory._latest_date(df) == "2026-11-18"
    assert normalize_ohlcv(df).date.is_monotonic_increasing
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_ohlcv(pd.concat([df,df]))


def test_invalid_price_outside_requested_window_cannot_poison_valid_bars():
    data = sample()
    data.loc[0, "high"] = 1.0
    assert len(normalize_ohlcv(data, "2026-11-18", "2026-11-18")) == 1
    with pytest.raises(ValueError, match="Inconsistent"):
        normalize_ohlcv(data, "2026-11-17", "2026-11-18")


@pytest.mark.parametrize("code,end,now,expected", [
    ("600000.SH","2026-11-18","2026-11-18T06:00:00Z","2026-11-17"),
    ("600000.SH","2026-11-18","2026-11-18T08:00:00Z","2026-11-18"),
    ("600000.SH","2026-10-01","2026-10-01T12:00:00Z","2026-09-30"),
    ("AAPL.US","2026-11-18","2026-11-18T14:00:00Z","2026-11-17"),
    ("AAPL.US","2026-11-18","2026-11-18T22:00:00Z","2026-11-18"),
    ("AAPL.US","2026-07-03","2026-07-03T22:00:00Z","2026-07-02"),
    ("00700.HK","2026-11-18","2026-11-18T09:00:00Z","2026-11-18"),
    ("8035.T","2026-11-18","2026-11-18T09:00:00Z","2026-11-18"),
    ("000660.KS","2026-11-18","2026-11-18T09:00:00Z","2026-11-18"),
])
def test_completed_sessions_holidays_and_timezones(code, end, now, expected):
    assert last_completed_session(StockCode.from_standard(code),end,now) == expected


def test_incomplete_bar_is_trimmed_and_zero_volume_is_suspended():
    code = StockCode("600000","SH")
    df, expected, quality = prepare_daily_frame(sample(),code,"2026-11-18","2026-11-18T06:00:00Z")
    assert len(df) == 1 and expected == "2026-11-17" and quality == "ok"
    bad = sample(); bad.loc[1,"volume"] = 0
    assert prepare_daily_frame(bad,code,"2026-11-18","2026-11-18T08:00:00Z")[2] == "suspended"


@pytest.mark.parametrize("adjust,closes", [("qfq",[5.,5.]), ("hfq",[10.,10.]), ("none",[10.,5.])])
def test_tushare_split_adjustment_and_share_volume(adjust, closes):
    source = TushareDataSource()
    source._pro = Mock()
    source._pro.daily.return_value = pd.DataFrame({"trade_date":["20261118","20261117"],
        "open":[5.,10.],"high":[5.5,11.],"low":[4.5,9.],"close":[5.,10.],"vol":[10.,20.]})
    source._pro.adj_factor.return_value = pd.DataFrame({"trade_date":["20261118","20261117"],"adj_factor":[2.,1.]})
    df=source.fetch_ohlcv(StockCode("600000","SH"),"2026-11-17","2026-11-18",adjust=adjust)
    assert df.close.tolist() == closes
    assert df.volume.tolist() == [2000.,1000.]
    assert "adj" not in source._pro.daily.call_args.kwargs


def test_tushare_missing_factors_cannot_silently_return_raw_prices():
    source = TushareDataSource(); source._pro = Mock()
    source._pro.daily.return_value = sample().rename(columns={"date":"trade_date","volume":"vol"})
    source._pro.daily.return_value["trade_date"] = ["20261117","20261118"]
    source._pro.adj_factor.return_value = pd.DataFrame()
    with pytest.raises(ValueError, match="factors"):
        source.fetch_ohlcv(StockCode("600000","SH"),"2026-11-17","2026-11-18")
    with pytest.raises(ValueError, match="daily"):
        source.fetch_ohlcv(StockCode("600000","SH"),"2026-11-17","2026-11-18",period="w")


def test_yfinance_adjustment_and_inclusive_end_are_explicit(monkeypatch):
    df = sample().set_index(pd.DatetimeIndex(["2026-11-17","2026-11-18"],name="Date"))
    df=df.drop(columns="date").rename(columns={c:c.capitalize() for c in ['open','high','low','close','volume']})
    ticker=Mock(); ticker.history.return_value=df
    monkeypatch.setattr('yfinance.Ticker',Mock(return_value=ticker))
    result=YFinanceDataSource().fetch_ohlcv(StockCode("A","US"),"2026-11-17","2026-11-18",adjust="none")
    assert ticker.history.call_args.kwargs['end'] == '2026-11-19'
    assert ticker.history.call_args.kwargs['auto_adjust'] is False
    assert len(result)==2


@pytest.mark.parametrize("cls", [YFinanceDataSource,YahooQueryDataSource])
def test_unsupported_adjustment_never_mislabels_raw_data(cls):
    source=cls()
    with pytest.raises(ValueError):
        source.fetch_ohlcv(StockCode("A","US"),"2026-11-17","2026-11-18",adjust="hfq")


def test_tushare_fundamental_date_currency_units_and_missing_values():
    source=TushareDataSource(); source._pro=Mock()
    source._pro.daily_basic.return_value=pd.DataFrame({
        'trade_date':['20261118','20261117','20261119'], 'pe_ttm':[18.,99.,123.],
        'total_mv':[12.,10.,15.], 'pb':[float('nan'),2.,3.]})
    data=source.fetch_fundamental(StockCode('600000','SH'),as_of='2026-11-18')
    assert data.pe_ttm==18 and data.total_mv==120000 and data.pb is None
    assert data.currency=='CNY' and data.as_of=='2026-11-18'
    assert 'trade_date' in source._pro.daily_basic.call_args.kwargs['fields']
    assert data.published_at is None and data.available_at
    assert data.to_dict()['schema_version']==1


def test_yahoo_fundamental_preserves_forward_and_enterprise_value(monkeypatch):
    ticker=Mock(key_stats={'A':{'forwardPE':28.,'enterpriseValue':1000.}},summary_detail={'A':{}})
    monkeypatch.setattr('yahooquery.Ticker',Mock(return_value=ticker))
    data=YahooQueryDataSource().fetch_fundamental(StockCode('A','US'))
    assert data.pe_ttm is None and data.total_mv is None
    assert data.forward_pe==28 and data.enterprise_value==1000
    assert 'current_snapshot_only' in data.quality_flags
    with pytest.raises(ValueError,match='point-in-time'):
        YahooQueryDataSource().fetch_fundamental(StockCode('A','US'),as_of='2025-01-01')


def test_partial_configuration_merges_defaults_and_explicit_none(tmp_path):
    path=tmp_path/'config.yaml';path.write_text('data:\n  markets:\n    us:\n      primary: yfinance\n      fallback: null\n')
    cfg=ConfigLoader(str(path)).get_data_config()
    assert cfg.get_primary('cn')=='baostock'
    assert cfg.get_primary('us')=='yfinance' and cfg.get_fallback('us') is None


def test_baostock_qfq_rebases_to_requested_end_not_future_action():
    from quantflow.data.adapters.baostock import BaoStockDataSource
    class Response:
        error_code='0'
        def __init__(self,fields,rows):
            self.fields=fields; self.rows=iter(rows)
        def next(self):
            self.row=next(self.rows,None)
            return self.row is not None
        def get_row_data(self):return self.row
    source=BaoStockDataSource();source._logged_in=True;source._bs=Mock()
    source._bs.query_history_k_data_plus.side_effect=[
        Response(['date','code','open','high','low','close','volume','amount'],[
            ['2026-11-17','sh.600000','5','5.5','4.5','5','100','1000'],
            ['2026-11-18','sh.600000','5','5.5','4.5','5','100','1000']]),
        Response(['date','close'],[['2026-11-18','10']])]
    result=source.fetch_ohlcv(StockCode('600000','SH'),'2026-11-17','2026-11-18')
    assert result.close.tolist()==[10.,10.]
    assert result.volume.tolist()==[100.,100.]
    assert result.attrs['adjustment_anchor']=='2026-11-18'
    assert source._bs.query_history_k_data_plus.call_args.kwargs['adjustflag']==source.ADJUST_MAP['none']


@pytest.mark.parametrize('end,now,expected',[
    ('2026-03-13','2026-03-13T20:15:00Z','2026-03-13'),
    ('2026-11-18','2026-11-18T20:15:00Z','2026-11-17'),
    ('2026-11-27','2026-11-27T19:00:00Z','2026-11-27'),
    ('2026-11-26','2026-11-26T19:00:00Z','2026-11-25'),
])
def test_us_dst_early_close_and_thanksgiving(end,now,expected):
    assert last_completed_session(StockCode('AAPL','US'),end,now)==expected


@pytest.mark.parametrize("batch", [False, True])
def test_current_but_gapped_primary_replaced_by_complete_fallback(monkeypatch, batch):
    code = StockCode("A", "US")
    complete = pd.concat([sample(), sample().iloc[[-1]].assign(date="2026-11-19")])
    gapped = complete.iloc[[0, 2]]
    primary = FakeAdapter({code.standard: gapped})
    fallback = FakeAdapter({code.standard: complete})
    factory = DataSourceFactory()
    monkeypatch.setattr(
        factory, "_get_adapter", lambda source: primary if source == "yahooquery" else fallback
    )
    args = ("2026-11-17", "2026-11-19")
    kwargs = {"require_end_session": True, "min_history_bars": 3}

    def fetch():
        if batch:
            return factory.fetch_batch_ohlcv([code], *args, **kwargs)[code.standard]
        return factory.fetch_ohlcv(code, *args, **kwargs)

    bars, source = fetch()
    assert source == bars.attrs["source"] == "yfinance"
    assert len(bars) == 3
    fallback.data[code.standard] = gapped.iloc[[-1]]
    bars, source = fetch()
    assert source == "yahooquery"
    assert len(bars) == 2


def test_completed_session_check_distinguishes_gaps_from_holidays_and_short_history():
    from quantflow.data.quality import inspect_daily_bars

    code = StockCode("AAPL", "US")
    before_holiday = sample().iloc[[0]].assign(date="2026-11-25")
    after_holiday = sample().iloc[[1]].assign(date="2026-11-27")
    closed_date = sample().iloc[[0]].assign(date="2026-11-26")
    clean = normalize_ohlcv(pd.concat([before_holiday, after_holiday]))
    assert inspect_daily_bars(clean, code, "2026-11-27").status == "ok"
    assert inspect_daily_bars(clean.iloc[[-1]], code, "2026-11-27").status == "ok"
    invalid = normalize_ohlcv(pd.concat([clean, closed_date]))
    quality = inspect_daily_bars(invalid, code, "2026-11-27")
    assert quality.status == "data_gap"
    assert quality.missing_sessions == ()
    assert quality.unexpected_dates == ("2026-11-26",)


def test_signed_off_listing_date_and_halted_placeholder_are_distinct_from_data_gap():
    from quantflow.data.quality import inspect_daily_bars, tradable_bars

    code = StockCode("001309", "SZ")
    frame = normalize_ohlcv(pd.concat([
        sample().iloc[[0]].assign(date="2026-11-16", trade_status="1"),
        sample().iloc[[0]].assign(date="2026-11-17", trade_status="0", volume=0),
        sample().iloc[[1]].assign(date="2026-11-18", trade_status="1"),
    ]))
    frame.attrs.update(listing_date="2026-11-16", query_start="2026-11-10")
    quality = inspect_daily_bars(frame, code, "2026-11-18")
    assert quality.status == "ok"
    assert quality.confirmed_suspensions == ("2026-11-17",)
    assert len(tradable_bars(frame)) == 2
    assert inspect_daily_bars(frame.iloc[:2], code, "2026-11-17").status == "suspended"

    frame.attrs["listing_date"] = "2026-11-13"
    quality = inspect_daily_bars(frame, code, "2026-11-18")
    assert quality.status == "data_gap"
    assert quality.missing_sessions == ("2026-11-13",)


def test_ohlc_allows_float_roundoff_but_rejects_a_material_price_violation():
    import numpy as np

    quotes = sample()
    quotes.loc[0, "high"] = np.nextafter(quotes.loc[0, "close"], 0)
    clean = normalize_ohlcv(quotes)
    assert clean.loc[0, "high"] == clean.loc[0, "close"]
    quotes.loc[0, "high"] = quotes.loc[0, "close"] - 0.01
    with pytest.raises(ValueError, match="Inconsistent"):
        normalize_ohlcv(quotes)


def test_batch_rechecks_only_symbols_with_unresolved_transport_errors(monkeypatch):
    a, b = StockCode("A", "US"), StockCode("B", "US")
    primary = FakeAdapter({"A.US": sample()})
    fallback = FakeAdapter({})
    factory = DataSourceFactory()

    def fetch(codes, *args):
        names = [code.standard for code in codes]
        primary.calls.append(names)
        if len(primary.calls) == 1:
            primary.batch_errors = {"B.US": "TimeoutError: simulated network interruption"}
            return {"A.US": sample()}
        primary.batch_errors = {}
        return {"B.US": sample()}

    monkeypatch.setattr(primary, "fetch_batch_ohlcv", fetch)
    monkeypatch.setattr(
        factory, "_get_adapter", lambda name: primary if name == "yahooquery" else fallback,
    )
    result = factory.fetch_batch_ohlcv([a, b], "2026-11-17", "2026-11-18")
    assert {code: source for code, (_, source) in result.items()} == {
        "A.US": "yahooquery", "B.US": "yahooquery",
    }
    assert primary.calls == [["A.US", "B.US"], ["B.US"]]
    assert fallback.calls == [["B.US"]]
