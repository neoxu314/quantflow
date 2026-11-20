"""Cancellation and deletion while the real worker is parked at the data boundary."""

from playwright.sync_api import expect

from .run_helpers import (
    open_run_tab,
    open_runs,
    pause_provider,
    result,
    select_run,
    start_scan,
    wait_run,
    wait_until,
)


def test_cancel_active_run_and_delete_it(page, client, e2e_url, web_server):
    gate = pause_provider(web_server)
    run_id = start_scan(client)
    wait_until(gate.with_suffix(".entered").exists, "Worker did not reach the provider")
    open_runs(page, e2e_url)
    select_run(page, run_id, "running")
    expect(open_run_tab(page, "progress").locator("#run-log-container")).to_contain_text(
        "Log file:"
    )

    response = result(client.post(f"/api/runs/{run_id}/cancel"))
    assert response == {"ok": True, "status": "cancelling"}
    cancelled = wait_run(client, run_id, "cancelled")
    assert cancelled["report_path"] is None
    row = select_run(page, run_id, "cancelled")
    page.once("dialog", lambda dialog: dialog.accept())
    with page.expect_response(
        lambda r: r.url == f"{e2e_url}/api/runs/{run_id}" and r.request.method == "DELETE"
    ) as deleted:
        row.get_by_title("Delete run").click()
    assert deleted.value.json()["ok"]
    expect(row).to_have_count(0)
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_cancelling_queued_run_does_not_stop_the_active_one(client, web_server):
    gate = pause_provider(web_server)
    running = start_scan(client)
    wait_until(gate.with_suffix(".entered").exists, "Worker did not reach the provider")
    queued = start_scan(client, code="MSFT.US")
    wait_run(client, queued, "queued")
    assert result(client.post(f"/api/runs/{queued}/cancel")) == {"ok": True, "status": "cancelled"}
    wait_run(client, queued, "cancelled")
    assert result(client.get("/api/runs/queue"))["active_run_id"] == running
    gate.unlink()
    wait_run(client, running)
