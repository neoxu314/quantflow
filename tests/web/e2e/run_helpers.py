"""Drive Runs by their API-issued IDs and by visible controls."""

from time import monotonic, sleep

import pytest
from playwright.sync_api import expect

from tests.support.replay_market import SIGNAL_DATE

TERMINAL = {"completed", "partial", "failed", "cancelled", "interrupted"}
SCAN = {
    "run_type": "stock_scan",
    "code": "AAPL.US",
    "indicators": ["kdj"],
    "start_date": "2025-06-03",
    "end_date": SIGNAL_DATE,
}


def result(response):
    response.raise_for_status()
    return response.json()


def start_scan(client, **options):
    body = result(client.post("/api/runs/", json={**SCAN, **options}))
    assert body["ok"], body
    return body["run_id"]


def wait_until(check, message, timeout=10):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if value := check():
            return value
        sleep(0.03)
    pytest.fail(message)


def wait_run(client, run_id, status="completed"):
    def check():
        run = result(client.get(f"/api/runs/{run_id}"))["run"]
        if run["status"] in TERMINAL or run["status"] == status:
            return run
        return None

    run = wait_until(check, f"Run {run_id} did not reach {status}")
    assert run["status"] == status, run
    return run


def open_runs(page, url):
    with page.expect_response(lambda r: r.url == f"{url}/api/runs/" and r.ok):
        page.goto(url)
    page.get_by_role("button", name="Runs", exact=True).click()


def open_new_run(page, kind):
    page.locator("#btn-new-run").click()
    page.locator(f'[data-type="{kind}"]').click()
    expect(page.locator(f"#run-config-{kind}")).to_be_visible()


def submit_run(page, url):
    with page.expect_response(
        lambda r: r.url == f"{url}/api/runs/" and r.request.method == "POST"
    ) as run:
        page.locator("#btn-execute-run").click()
    body = run.value.json()
    assert body["ok"], body
    expect(page.locator("#modal-new-run")).to_be_hidden()
    return body["run_id"]


def select_run(page, run_id, status):
    row = page.locator(f'li[data-run-id="{run_id}"]')
    expect(row).to_contain_text(status, timeout=7000)
    row.click()
    expect(page.locator("#runtab-config")).to_contain_text(status)
    return row


def open_run_tab(page, tab):
    page.locator(f'[data-runtab="{tab}"]').click()
    return page.locator(f"#runtab-{tab}")


def pause_provider(web_server, code="AAPL.US"):
    gate = web_server.root / "provider-gate"
    gate.write_text(code)
    return gate
