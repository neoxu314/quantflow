"""Offline reproductions at the Yahoo conversion, routing and worker boundaries."""

import multiprocessing
import time
from unittest.mock import Mock

import pandas as pd
import pytest

from quantflow.control import ExecutionCancelled
from quantflow.data import StockCode, yahoo_batch
from quantflow.data.adapters import YahooQueryDataSource, YFinanceDataSource
from quantflow.data.factory import DataSourceFactory
from tests.data.test_quality_contracts import FakeAdapter, sample


def _hung_worker(sender, source, settings, codes, args, probe):
    sender.send(({codes[0].standard: sample()}, {}, 1, codes[0].standard, False))
    time.sleep(30)


@pytest.mark.parametrize("cancel", [True, False])
def test_stalled_sdk_is_reaped_and_completed_quotes_survive(cancel):
    codes = [StockCode("A", "US"), StockCode("B", "US")]
    previous = {p.pid for p in multiprocessing.active_children()}
    start = time.monotonic()

    def progress(*args):
        if cancel:
            raise ExecutionCancelled()

    def request():
        return yahoo_batch.download("test", {}, codes, (), start + 3, progress, worker=_hung_worker)

    if cancel:
        with pytest.raises(ExecutionCancelled):
            request()
    else:
        got = request()
        assert list(got.frames) == ["A.US"]
        assert "deadline" in got.errors["B.US"]
    assert time.monotonic() - start < 7
    assert {p.pid for p in multiprocessing.active_children()} <= previous


def test_empty_response_is_rechecked_even_without_exception(monkeypatch):
    a, b = StockCode("A", "US"), StockCode("B", "US")
    factory = DataSourceFactory()
    primary, backup = FakeAdapter({}), FakeAdapter({})
    fetch = Mock(side_effect=[{a.standard: sample()}, {b.standard: sample()}])
    monkeypatch.setattr(primary, "fetch_batch_ohlcv", fetch)
    monkeypatch.setattr(factory, "_get_adapter", lambda s: primary if s == "yahooquery" else backup)
    got = factory.fetch_batch_ohlcv([a, b], "2026-11-17", "2026-11-18")
    assert set(got) == {a.standard, b.standard}
    assert [call.args[0] for call in fetch.call_args_list] == [[a, b], [b]]
    assert backup.calls == [[b.standard]]


def test_real_yfinance_parser_recovers_only_all_null_symbol(monkeypatch):
    import yfinance

    raw = sample().set_index("date")
    raw.index = pd.DatetimeIndex(raw.index, name="Date")
    raw.columns = raw.columns.str.title()
    empty = raw.copy() * float("nan")
    empty["Volume"] = 0
    calls = []

    def download(**options):
        calls.append(options["tickers"])
        return pd.concat({"A": raw, "B": empty} if len(calls) == 1 else {"B": raw}, axis=1)

    monkeypatch.setattr(yfinance, "download", download)
    feed = YFinanceDataSource(recovery_max_passes=1, cooldown_base=0)
    got = feed.fetch_batch_ohlcv(
        [StockCode("A", "US"), StockCode("B", "US")], "2026-11-17", "2026-11-18"
    )
    assert calls == [["A", "B"], ["B"]]
    assert set(got) == {"A.US", "B.US"}


@pytest.mark.parametrize("reference_available", [False, True])
def test_probe_distinguishes_provider_outage_from_isolated_symbols(
    monkeypatch, reference_available
):
    calls = []

    def fetch(self, code, *args):
        calls.append(code.code)
        if reference_available and code.code in ("SPY", "D"):
            return sample()
        return pd.DataFrame()

    monkeypatch.setattr(YahooQueryDataSource, "fetch_ohlcv", fetch)
    sender = Mock()
    yahoo_batch._download(
        sender,
        "yahooquery",
        {"sleep_min": 0, "sleep_max": 0},
        [StockCode(c, "US") for c in "ABCDE"],
        ("2026-11-17", "2026-11-18", "d", "qfq"),
        False,
    )
    assert calls[:4] == ["A", "B", "C", "SPY"]
    assert ("D" in calls) == reference_available
    assert sender.send.call_args.args[0][-1] != reference_available


def test_common_outage_switches_provider_and_cooldown_preserves_unresolved(monkeypatch):
    factory = DataSourceFactory()
    calls = []

    def offline(source, settings, group, args, deadline, progress=None, *, probe=False):
        calls.append((source, probe, deadline))
        return yahoo_batch.Download(
            errors={c.standard: "simulated network outage" for c in group}, outage=True
        )

    monkeypatch.setattr(yahoo_batch, "download", offline)
    a, b = StockCode("A", "US"), StockCode("B", "US")
    assert not factory.fetch_batch_ohlcv([a], "2026-11-17", "2026-11-18")
    assert [(source, probe) for source, probe, _ in calls] == [
        ("yahooquery", False),
        ("yfinance", True),
    ]
    assert calls[0][2] < calls[1][2]
    assert not factory.fetch_batch_ohlcv([b], "2026-11-17", "2026-11-18")
    assert len(calls) == 2 and factory.pending_network == {"A.US", "B.US"}


def test_macos_proxy_respects_explicit_environment_and_excluded_hosts(monkeypatch):
    from quantflow.data.adapters import yahoo_proxy

    monkeypatch.setattr(yahoo_proxy.sys, "platform", "darwin")
    monkeypatch.setattr(yahoo_proxy, "getproxies_environment", lambda: {})
    monkeypatch.setattr(yahoo_proxy, "getproxies", lambda: {"https": "http://localhost:9876"})
    monkeypatch.setattr(yahoo_proxy, "proxy_bypass", lambda host: host.startswith("query2."))
    routes = yahoo_proxy.session_options()["proxies"]
    assert routes["https://query1.finance.yahoo.com"] == "http://localhost:9876"
    assert "https://query2.finance.yahoo.com" not in routes
    monkeypatch.setattr(yahoo_proxy, "getproxies_environment", lambda: {"https": "http://explicit"})
    assert yahoo_proxy.session_options() == {}
