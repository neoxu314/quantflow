"""Watchlist submission and continuation from a genuine partial run."""

import json
from pathlib import Path

from playwright.sync_api import expect

from .run_helpers import (
    open_new_run,
    open_run_tab,
    open_runs,
    pause_provider,
    result,
    select_run,
    submit_run,
    wait_run,
    wait_until,
)


def test_watchlist_reports_the_known_candidate(page, client, e2e_url):
    open_runs(page, e2e_url)
    open_new_run(page, "watchlist_run")
    page.locator("#run-watchlist-select").select_option("watchlists/djia.yaml")
    expect(page.locator("#run-cli-preview")).to_contain_text(
        "monitor --watchlist watchlists/djia.yaml"
    )
    run_id = submit_run(page, e2e_url)
    assert wait_run(client, run_id)["signal_count"] == 1
    select_run(page, run_id, "completed")
    report = open_run_tab(page, "report")
    expect(report).to_contain_text("AAPL.US")
    expect(report).to_contain_text("Oversold J=4.4 in bull channel")
    files = open_run_tab(page, "files")
    expect(files.get_by_role("cell", name="web-DJIA.md", exact=True)).to_be_visible()


def test_back_allows_changing_run_type(page, e2e_url):
    open_runs(page, e2e_url)
    open_new_run(page, "stock_scan")
    page.locator("#btn-back-run").click()
    expect(page.locator("#run-step-type")).to_be_visible()
    expect(page.locator("#run-config-stock_scan")).to_be_hidden()
    page.locator('[data-type="watchlist_run"]').click()
    expect(page.locator("#run-config-watchlist_run")).to_be_visible()
    expect(page.locator("#run-config-stock_scan")).to_be_hidden()


def test_resume_creates_new_completed_run_and_keeps_original(page, client, e2e_url, web_server):
    result(
        client.put(
            "/api/watchlists/resume-fixture.yaml",
            json={
                "name": "resume-fixture",
                "items": [{"code": "AAPL.US"}, {"code": "BROKEN.US"}],
            },
        )
    )
    body = result(
        client.post(
            "/api/runs/",
            json={
                "run_type": "watchlist_run",
                "watchlist": "watchlists/resume-fixture.yaml",
                "strategies": ["daily_bull_oversold"],
            },
        )
    )
    original_id = body["run_id"]
    original = wait_run(client, original_id, "partial")
    assert original["signal_count"] == 1
    (coverage,) = Path(original["output_path"]).glob("*_coverage.json")
    outcome = next(
        row for row in json.loads(coverage.read_text())["outcomes"] if row["code"] == "BROKEN.US"
    )
    assert outcome["status"] == "error"
    assert "connection timeout" in outcome["error"]
    request_log = web_server.root / "provider-requests.log"
    first_requests = request_log.read_text().splitlines()
    (web_server.root / "provider-available").touch()

    open_runs(page, e2e_url)
    select_run(page, original_id, "partial")
    with page.expect_response(
        lambda r: r.url == f"{e2e_url}/api/runs/{original_id}/resume" and r.request.method == "POST"
    ) as resumed:
        page.get_by_role("button", name="⏵ Resume", exact=True).click()
    new_id = resumed.value.json()["run_id"]
    assert new_id != original_id
    finished = wait_run(client, new_id)
    assert finished["config"]["resume_from"] == original_id
    assert finished["output_path"] != original["output_path"]
    assert finished["signal_count"] == 1
    assert request_log.read_text().splitlines()[len(first_requests) :] == ["BROKEN.US"]
    assert result(client.get(f"/api/runs/{original_id}"))["run"]["status"] == "partial"
    select_run(page, new_id, "completed")
    expect(open_run_tab(page, "report")).to_contain_text("Oversold J=4.4 in bull channel")


def test_progress_during_download_and_after_reconnect(page, client, e2e_url, web_server):
    result(
        client.put(
            "/api/watchlists/progress.yaml",
            json={
                "name": "Progress",
                "items": [{"code": "AAPL.US"}, {"code": "MSFT.US"}],
            },
        )
    )
    gate = pause_provider(web_server, "MSFT.US")
    run_id = result(
        client.post(
            "/api/runs/",
            json={
                "run_type": "watchlist_run",
                "watchlist": "watchlists/progress.yaml",
                "strategies": ["daily_bull_oversold"],
            },
        )
    )["run_id"]
    wait_until(gate.with_suffix(".entered").exists, "Second stock was never requested")
    open_runs(page, e2e_url)
    select_run(page, run_id, "running")
    progress = open_run_tab(page, "progress")
    expect(progress.locator("#run-progress-text")).to_have_text("Downloading 50% (1/2)")
    expect(progress.get_by_role("progressbar")).to_have_attribute("aria-valuenow", "50")

    page.route("**/logs:sse", lambda route: route.abort())
    open_runs(page, e2e_url)
    select_run(page, run_id, "running")
    progress = open_run_tab(page, "progress")
    expect(progress.locator("#run-progress-text")).to_have_text("Downloading 50% (1/2)")
    assert not list(Path(wait_run(client, run_id, "running")["output_path"]).glob("snapshots/*/*"))

    gate.unlink()
    assert wait_run(client, run_id)["signal_count"] == 1
    expect(progress).to_contain_text("Complete", timeout=7000)
    expect(progress).to_be_visible()
    expect(open_run_tab(page, "report")).to_contain_text("Oversold J=4.4 in bull channel")
