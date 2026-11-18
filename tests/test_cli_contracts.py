"""Current CLI output, exit status and CLI/Web shared-service regression contracts."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from quantflow import cli
from quantflow.execution.storage import ScanResults, StockOutcome


@pytest.mark.parametrize('status,exit_code', [('completed',0),('partial',2),('failed',1)])
def test_watchlist_exit_status_and_run_owned_report(tmp_path,monkeypatch,status,exit_code):
    wl=tmp_path/'wl.yaml';wl.write_text('name: watch\nitems:\n- code: AAPL.US\n')
    outcomes={'completed':[StockOutcome('AAPL.US','no_signal')],
              'partial':[StockOutcome('AAPL.US','no_signal'),StockOutcome('B.US','error')],
              'failed':[StockOutcome('AAPL.US','no_data')]}
    execute=Mock(return_value=ScanResults([],outcomes[status]))
    monkeypatch.setattr('quantflow.execution.executor.Executor.execute',execute)
    monkeypatch.setattr('sys.argv',['cli','--watchlist',str(wl),'--output',str(tmp_path),
                                  '--strategies','daily_bull_oversold','--days-back','500'])
    assert cli.watchlist_run()==exit_code
    root=next((tmp_path/'runs').iterdir())
    assert json.loads((root/'manifest.json').read_text())['status']==status
    assert json.loads((root/'Run_Summary.json').read_text())['status']==status
    assert execute.call_args.args[0].days_back==500
    assert (root/'cli-watch.md').exists()
    assert not (tmp_path/'cli-watch.md').exists()


@pytest.mark.parametrize('function,args',[(cli.watchlist_run,['--watchlist','/missing/watch.yaml']),
                                         (cli.task_run,['--config','/missing/tasks.yaml'])])
def test_missing_input_is_nonzero(tmp_path,monkeypatch,function,args):
    monkeypatch.setattr('sys.argv',['cli',*args,'--output',str(tmp_path)])
    assert function()==1


def test_single_stock_cli_and_web_delegate_to_same_service(tmp_path,monkeypatch):
    from quantflow.execution import scanner
    from quantflow.web.engine.run_engine import RunEngine, CancellationFlag
    from quantflow.web.engine import RunHistory, RunQueue, SSEManager
    from types import SimpleNamespace
    scan=Mock(return_value=(str(tmp_path/'result.json'),3,{'source':'fake'}))
    monkeypatch.setattr(scanner,'scan_stock',scan)
    monkeypatch.setattr('quantflow.web.engine.run_engine.scan_stock',scan)
    monkeypatch.setattr('sys.argv',['cli','--code','AAPL.US','--start','2026-01-01',
                                  '--end','2026-04-30','--indicator','kdj,macd','--output',str(tmp_path)])
    assert cli.stock_scan()==0
    assert scan.call_args.args[0]['indicators']==['kdj','macd']
    engine=RunEngine(RunQueue(),Mock(),SSEManager())
    engine._exec_stock_scan('id',SimpleNamespace(output_path=str(tmp_path),config={
        'code':'AAPL.US','indicators':['kdj','macd']}),CancellationFlag())
    assert scan.call_count==2


def test_single_stock_scan_never_substitutes_unrequested_dates(tmp_path,monkeypatch):
    from quantflow.execution.scanner import scan_stock
    from tests.execution.test_correctness_contracts import frame
    factory=Mock();factory.fetch_ohlcv.return_value=(frame(end='2026-11-20'),'mock')
    monkeypatch.setattr('quantflow.config.loader.ConfigLoader.create_data_factory',lambda self:factory)
    with pytest.raises(ValueError,match='requested output interval'):
        scan_stock({'code':'600000.SH','start_date':'2026-11-21','end_date':'2026-11-21'},
                   tmp_path,now='2026-11-22T14:00:00Z')


def test_single_scan_records_config_source_dates_and_strict_json(tmp_path,monkeypatch):
    from quantflow.execution.scanner import scan_stock
    from tests.execution.test_correctness_contracts import frame
    factory=Mock();factory.fetch_ohlcv.return_value=(frame(),'mock')
    monkeypatch.setattr('quantflow.config.loader.ConfigLoader.create_data_factory',lambda self:factory)
    path,count,metadata=scan_stock({'code':'600000.SH','start_date':'2026-11-18','end_date':'2026-11-18'},
                                   tmp_path,now='2026-11-18T14:00:00Z')
    assert count==1
    assert json.loads(Path(path).read_text())[0]['date'].startswith('2026-11-18')
    assert metadata['bar_date']=='2026-11-18' and metadata['source']=='mock'
    assert metadata['indicator_params']['DualLine']['ema_period']==10
    assert factory.fetch_ohlcv.call_args.kwargs['adjust']=='qfq'
    assert (tmp_path/'600000.SH_snapshot.json').exists()
