"""Task-level failures and mandatory artifact writes must reach the run status."""
import json
from pathlib import Path

import pytest

from quantflow.artifacts import ArtifactWriteError
from quantflow.execution.checkpoint import Checkpoint
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
    assert app.last_summary['coverage'] is None
    assert app.last_summary['unreadable_watchlists'] == 1
    assert app.last_summary['enumerated_coverage'] == 1.0
    summary = json.loads((app.output_dir / "Run_Summary.json").read_text())
    assert summary["coverage"] is None
    report = Path(app.report_path).read_text()
    assert "broken" in report
    assert "**Coverage**: unknown" in report
    assert "**Coverage of enumerated stocks**: 100.0%" in report


def test_all_failed_tasks_never_become_completed_or_full_coverage(tmp_path):
    app=Orchestrator([TaskConfig('missing',str(tmp_path/'missing.yaml'),['daily_bull_oversold'])],
                     output_override=str(tmp_path))
    assert app.run()==0
    assert app.last_summary['status']=='failed'
    assert app.last_summary['coverage'] is None
    assert app.last_summary['enumerated_coverage'] is None
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


def test_resumed_task_run_reuses_original_cutoff_for_all_tasks(tmp_path, monkeypatch):
    watchlist = tmp_path / "watchlist.yaml"
    watchlist.write_text("name: watch\nitems:\n- code: AAPL.US\n")
    tasks = [
        TaskConfig(name, str(watchlist), ["daily_bull_oversold"])
        for name in ("first", "second")
    ]
    checkpoint = Checkpoint("original", path=tmp_path / "checkpoint.json")
    cutoffs = []

    def execute(_executor, job, **_kwargs):
        cutoffs.append(job.as_of)
        if job.name == "second" and len(cutoffs) == 2:
            raise RuntimeError("second task never downloaded its data")
        return ScanResults([], [StockOutcome("AAPL.US", "no_signal")])

    monkeypatch.setattr("quantflow.execution.executor.Executor.execute", execute)
    initial = "2026-11-18T14:00:00Z"
    Orchestrator(tasks, output_override=tmp_path, checkpoint=checkpoint, as_of=initial).run()
    reloaded = Checkpoint.load("original", path=checkpoint.path)
    resumed = Orchestrator(
        tasks, output_override=tmp_path, checkpoint=reloaded, as_of="2026-11-19T23:00:00Z"
    )
    resumed.run()

    assert cutoffs == [initial] * 4
    assert resumed.last_summary["as_of"] == initial


@pytest.mark.parametrize("change", ["watchlist", "reorder", "strategy", "add", "remove"])
def test_runs_reject_changes_to_unstarted_tasks_before_processing(tmp_path, monkeypatch, change):
    from quantflow.execution.checkpoint import ResumePlanError

    first, second = tmp_path / "one.yaml", tmp_path / "two.yaml"
    first.write_text("name: one\nitems: [{code: AAPL.US}]\n")
    second.write_text("name: two\nitems: [{code: MSFT.US}]\n")
    tasks = [
        TaskConfig("one", str(first), ["daily_bull_oversold"]),
        TaskConfig("two", str(second), ["daily_bull_oversold"]),
    ]
    checkpoint = Checkpoint("original", path=tmp_path / "checkpoint.json")
    original = Orchestrator(tasks, output_override=tmp_path, checkpoint=checkpoint)
    checkpoint.freeze_run_plan(original.run_plan(original.prepare_tasks(tmp_path)))
    checkpoint.mark_done("one", "AAPL.US")
    reloaded = Checkpoint.load("original", path=checkpoint.path)

    ran = []
    monkeypatch.setattr(original.executor, "execute", lambda *args, **kwargs: ran.append(args))
    if change == "watchlist":
        second.write_text("name: two\nitems: [{code: NVDA.US}]\n")
    elif change == "reorder":
        tasks.reverse()
    elif change == "strategy":
        tasks[1].strategy_names = ["daily_bull_mid_range"]
    elif change == "add":
        tasks.append(TaskConfig("three", str(first), ["daily_bull_oversold"]))
    elif change == "remove":
        tasks.pop()
    original.checkpoint = reloaded
    with pytest.raises(ResumePlanError, match="inputs changed"):
        original.run()
    assert ran == []


def test_conflicting_task_names_have_independent_artifacts_and_resume(tmp_path, monkeypatch):
    import hashlib

    from quantflow.artifacts import delete_owned_artifacts
    from tests.support.replay_market import install_replay

    install_replay(tmp_path, monkeypatch.setattr)
    watchlist = tmp_path / "quotes.yaml"
    watchlist.write_text("name: quotes\nitems: [{code: AAPL.US}]\n")
    names = ["manifest", "Run_Summary", "Combined_Results", "Daily_Report",
             "scan", "Scan", "scan_context", "scan_coverage"]
    tasks = [TaskConfig(name, str(watchlist), ["daily_bull_oversold"]) for name in names]
    cp = Checkpoint("first", path=tmp_path / "first.json")
    app = Orchestrator(tasks, output_override=tmp_path, checkpoint=cp)
    assert app.run() == len(names)
    root = app.output_dir
    summary = json.loads((root / "Run_Summary.json").read_text())
    assert summary["status"] == "completed" and summary["analyzed"] == len(names)
    assert len(json.loads((root / "Combined_Results.json").read_text())) == len(names)
    manifest = json.loads((root / "manifest.json").read_text())
    assert (manifest["run_id"], manifest["status"]) == (root.name, "completed")
    assert len(set(summary["task_directories"].values())) == len(names)
    for n, name in enumerate(names, 1):
        folder = root / summary["task_directories"][name]
        assert folder == root / "tasks" / f"{n:04d}"
        assert json.loads((folder / "results.json").read_text())[0]["code"] == "AAPL.US"
        assert json.loads((folder / "context.json").read_text())["task"] == name
        assert (folder / "report.md").read_text().startswith(f"# {name} Scan Report")
        outcome, = json.loads((folder / "coverage.json").read_text())["outcomes"]
        snapshot = root / "snapshots" / f"{n:04d}" / "AAPL.US.json"
        assert Path(outcome["snapshot_path"]) == snapshot
        for path in [*folder.iterdir(), snapshot]:
            record = manifest["artifacts"][path.relative_to(root).as_posix()]
            assert record["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(list(cp.verified_snapshots(root))) == len(names)

    request_log = tmp_path / "provider-requests.log"
    request_log.write_text("")
    resumed = Orchestrator(tasks, output_override=tmp_path, checkpoint=cp)
    assert resumed.run() == len(names) and request_log.read_text() == ""
    delete_owned_artifacts(root, root.name)
    assert not root.exists()
    assert len(list(cp.verified_snapshots(resumed.output_dir))) == len(names)
