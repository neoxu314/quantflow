"""CLI and Web run the same fixed market through the real executor and report writer."""

import json
from pathlib import Path
from time import monotonic, sleep

import pytest
from fastapi.testclient import TestClient

from quantflow import cli
from quantflow.web.engine import run_history
from quantflow.web.server import create_app
from tests.support.replay_market import AS_OF, SIGNAL_DATE, install_replay


@pytest.fixture
def market(tmp_path, monkeypatch):
    install_replay(tmp_path, monkeypatch.setattr)
    state = tmp_path / "web-state"
    run_history._ConnectionManager.reset()
    monkeypatch.setattr(run_history, "QUANTFLOW_DIR", state)
    monkeypatch.setattr(run_history, "DB_PATH", state / "runs.db")
    monkeypatch.setattr("quantflow.execution.checkpoint.CHECKPOINT_DIR", state / "checkpoints")
    yield
    run_history._ConnectionManager.reset()


def _watchlist(root, symbols):
    path = root / "fixture.yaml"
    path.write_text("name: fixture\nitems:\n" + "".join(f"- code: {code}\n" for code in symbols))
    return path


def _results(root, kind, label):
    filename = "Combined_Results.json" if kind == "task_run" else f"{label}-fixture.json"
    return json.loads((root / filename).read_text())


def _run_web(client, request):
    response = client.post("/api/runs/", json=request)
    assert response.status_code == 200
    body = response.json()
    assert body["ok"], body
    started = body["run_id"]
    deadline = monotonic() + 8
    while monotonic() < deadline:
        response = client.get(f"/api/runs/{started}")
        response.raise_for_status()
        run = response.json()["run"]
        if run["status"] not in {"queued", "running", "cancelling"}:
            return run
        sleep(0.02)
    pytest.fail(f"Run {started} did not finish: {run}")


@pytest.mark.parametrize("kind", ["watchlist_run", "task_run"])
def test_cli_and_web_report_the_same_expected_rebound(kind, market, monkeypatch, tmp_path):
    watchlist = _watchlist(tmp_path, ["AAPL.US", "MSFT.US"])
    task = tmp_path / "tasks.yaml"
    task.write_text(
        f"tasks:\n- name: fixture\n  watchlist: {watchlist}\n  strategies: [daily_bull_oversold]\n"
    )
    output = tmp_path / "cli"
    strategy = "daily_bull_oversold"
    if kind == "task_run":
        args = ["--config", str(task)]
        config = {"task_config": str(task)}
    else:
        args = ["--watchlist", str(watchlist), "--strategies", strategy]
        config = {"watchlist": str(watchlist), "strategies": [strategy]}
    monkeypatch.setattr("sys.argv", [kind, "--output", str(output), *args])
    assert getattr(cli, kind)() == 0
    (cli_root,) = (output / "runs").iterdir()

    with TestClient(create_app()) as client:
        run = _run_web(client, {"run_type": kind, "output_path": str(tmp_path / "web"), **config})
        assert run["status"] == "completed", run
        assert run["signal_count"] == 1
        report = client.get(f"/api/runs/{run['id']}/report").json()["report"]
        assert "AAPL.US" in report
        assert "Oversold J=4.4 in bull channel" in report
        web_root = Path(run["output_path"])
        assert web_root != cli_root
        web_results = _results(web_root, kind, "web")
        cli_results = _results(cli_root, kind, "cli")
        for rows in (web_results, cli_results):
            (row,) = rows
            assert {
                key: row[key]
                for key in (
                    "code",
                    "bar_date",
                    "source",
                    "matched_buy_strategies",
                    "buy_signals",
                    "reasons",
                )
            } == {
                "code": "AAPL.US",
                "bar_date": SIGNAL_DATE,
                "source": "yahooquery",
                "matched_buy_strategies": ["DailyBullishOversold"],
                "buy_signals": 1,
                "reasons": ["Oversold J=4.4 in bull channel"],
            }
            assert row["price"] == pytest.approx(139.5)
        for folder in (web_root, cli_root):
            summary = json.loads((folder / "Run_Summary.json").read_text())
            assert (summary["signal"], summary["no_signal"], summary["analyzed"]) == (1, 1, 2)
            assert summary["as_of"] == AS_OF


@pytest.mark.parametrize(
    ("symbols", "status", "code", "counts"),
    [
        (["MSFT.US"], "completed", 0, (1, 0)),
        (["MSFT.US", "EMPTY.US"], "partial", 2, (1, 1)),
        (["EMPTY.US"], "failed", 1, (0, 1)),
    ],
)
def test_watchlist_distinguishes_zero_signals_from_missing_bars(
    symbols,
    status,
    code,
    counts,
    market,
    monkeypatch,
    tmp_path,
):
    watchlist = _watchlist(tmp_path, symbols)
    output = tmp_path / "results"
    monkeypatch.setattr(
        "sys.argv",
        [
            "watchlist_run",
            "--watchlist",
            str(watchlist),
            "--output",
            str(output),
            "--strategies",
            "daily_bull_oversold",
        ],
    )
    assert cli.watchlist_run() == code
    (root,) = (output / "runs").iterdir()
    assert _results(root, "watchlist_run", "cli") == []
    summary = json.loads((root / "Run_Summary.json").read_text())
    assert summary["status"] == status
    assert (summary["no_signal"], summary["no_data"]) == counts


def test_web_checkpoints_analyzed_work_before_downloading_the_next_batch(
    market,
    monkeypatch,
    tmp_path,
):
    from quantflow.execution.executor import Executor
    from tests.support.replay_market import ReplayAdapter

    watchlist = _watchlist(tmp_path, ["AAPL.US", "MSFT.US"])
    checkpoint_dir = tmp_path / "web-state" / "checkpoints"
    fetch = ReplayAdapter.fetch_ohlcv
    done_when_next_request_begins = []

    def observe(adapter, symbol, *args):
        if symbol.standard == "MSFT.US":
            (path,) = checkpoint_dir.glob("*.json")
            work = json.loads(path.read_text())["work"]
            done_when_next_request_begins.append(set(work.get("watchlist", {}).get("done", {})))
        return fetch(adapter, symbol, *args)

    monkeypatch.setattr(Executor, "BATCH_SIZE", 1)
    monkeypatch.setattr(ReplayAdapter, "fetch_ohlcv", observe)
    with TestClient(create_app()) as client:
        run = _run_web(
            client,
            {
                "run_type": "watchlist_run",
                "watchlist": str(watchlist),
                "strategies": ["daily_bull_oversold"],
                "output_path": str(tmp_path / "results"),
            },
        )
    assert run["status"] == "completed", run
    assert run["signal_count"] == 1
    assert done_when_next_request_begins == [{"AAPL.US"}]
