"""Use a provider gate to verify deterministic queue hand-off."""

from .run_helpers import (
    open_runs,
    pause_provider,
    result,
    select_run,
    start_scan,
    wait_run,
    wait_until,
)


def test_second_run_starts_after_first_finishes(page, client, e2e_url, web_server):
    gate = pause_provider(web_server)
    first_id = start_scan(client)
    wait_until(gate.with_suffix(".entered").exists, "First run did not reach the provider")
    second_id = start_scan(client, code="MSFT.US")
    queued = wait_run(client, second_id, "queued")
    assert queued["started_at"] is None
    assert result(client.get("/api/runs/queue")) == {
        "active_run_id": first_id,
        "pending_count": 1,
        "total_queued": 2,
    }
    open_runs(page, e2e_url)
    select_run(page, second_id, "queued")

    gate.unlink()
    first = wait_run(client, first_id)
    second = wait_run(client, second_id)
    assert first["finished_at"] <= second["started_at"]
    select_run(page, second_id, "completed")
    select_run(page, first_id, "completed")


def test_queue_empty_when_no_runs(client):
    assert result(client.get("/api/runs/queue")) == {
        "active_run_id": None,
        "pending_count": 0,
        "total_queued": 0,
    }
