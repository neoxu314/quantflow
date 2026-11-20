"""HTTP contracts for the real scan artifacts."""

import json
from pathlib import Path

import pytest

from .run_helpers import result, start_scan, wait_run


def test_indicator_data_matches_the_strict_on_disk_report(client):
    run_id = start_scan(client)
    run = wait_run(client, run_id)
    response = client.get(f"/api/runs/{run_id}/indicator-data")
    response.raise_for_status()

    def invalid_constant(value):
        pytest.fail(f"Invalid JSON constant: {value}")

    data = json.loads(response.content, parse_constant=invalid_constant)
    assert data["code"] == "AAPL.US"
    assert data["bar_count"] == 2
    assert [row["date"][:10] for row in data["data"]] == ["2025-06-03", "2025-06-04"]
    assert data["data"][-1]["close"] == pytest.approx(139.5)
    assert data["data"][-1]["J"] == pytest.approx(4.40254, abs=0.001)
    raw = Path(run["report_path"]).read_text()
    assert data["data"] == json.loads(raw, parse_constant=invalid_constant)
    files = result(client.get(f"/api/runs/{run_id}/files"))["files"]
    assert {Path(file["path"]).name for file in files} >= {
        "AAPL.US_snapshot.json",
        "AAPL.US_indicators.json",
        "AAPL.US_context.json",
    }


def test_indicator_data_for_non_scan_returns_null(client):
    run_id = result(
        client.post(
            "/api/runs/",
            json={
                "run_type": "watchlist_run",
                "watchlist": "watchlists/djia.yaml",
                "strategies": ["daily_bull_oversold"],
            },
        )
    )["run_id"]
    wait_run(client, run_id)
    assert result(client.get(f"/api/runs/{run_id}/indicator-data")) == {
        "data": None,
        "message": "Not a stock scan run",
    }


def test_indicator_data_for_nonexistent_run_returns_404(client):
    assert client.get("/api/runs/missing/indicator-data").status_code == 404
