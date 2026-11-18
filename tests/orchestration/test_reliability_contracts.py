"""Task-level failures and mandatory artifact writes must reach the run status."""
import json
from pathlib import Path

import pytest

from quantflow.artifacts import ArtifactWriteError
from quantflow.execution.storage import ScanResults, StockOutcome
from quantflow.orchestration.app import Orchestrator
from quantflow.orchestration.loader import TaskConfig


def test_failed_task_is_visible_alongside_successful_task(tmp_path,monkeypatch):
    wl=tmp_path/'wl.yaml';wl.write_text('name: watch\nitems:\n- code: AAPL.US\n')
    tasks=[TaskConfig('good',str(wl),['daily_bull_oversold']),
           TaskConfig('broken',str(tmp_path/'missing.yaml'),['daily_bull_oversold'])]
    monkeypatch.setattr('quantflow.execution.executor.Executor.execute',
        lambda *a,**k:ScanResults([], [StockOutcome('AAPL.US','no_signal')]))
    app=Orchestrator(tasks,output_override=str(tmp_path))
    app.run()
    assert app.last_summary['status']=='partial'
    assert app.last_summary['tasks_requested']==2
    assert app.last_summary['tasks_completed']==1
    assert app.last_summary['task_errors'][0]['task']=='broken'
    assert 'broken' in Path(app.report_path).read_text()


def test_all_failed_tasks_never_become_completed_or_full_coverage(tmp_path):
    app=Orchestrator([TaskConfig('missing',str(tmp_path/'missing.yaml'),['daily_bull_oversold'])],
                     output_override=str(tmp_path))
    assert app.run()==0
    assert app.last_summary['status']=='failed'
    assert app.last_summary['coverage']==0
    assert json.loads((app.output_dir/'manifest.json').read_text())['status']=='failed'


def test_required_report_write_failure_is_fatal(tmp_path,monkeypatch):
    wl=tmp_path/'wl.yaml';wl.write_text('name: watch\nitems:\n- code: AAPL.US\n')
    monkeypatch.setattr('quantflow.execution.executor.Executor.execute',
        lambda *a,**k:ScanResults([], [StockOutcome('AAPL.US','no_signal')]))
    def fail(*a,**k):raise ArtifactWriteError('required report failed')
    monkeypatch.setattr('quantflow.reports.markdown.MarkdownReporter.generate',fail)
    app=Orchestrator([TaskConfig('task',str(wl),['daily_bull_oversold'])],output_override=str(tmp_path))
    with pytest.raises(ArtifactWriteError):app.run()
    assert json.loads((app.output_dir/'manifest.json').read_text())['status']=='failed'
