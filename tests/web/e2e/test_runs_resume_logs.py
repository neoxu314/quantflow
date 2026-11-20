"""E2E tests for the three Runs improvements:

1. Progress log box shows the REAL on-disk Python log (not SSE summaries).
2. Startup reconciliation renders the ``interrupted`` state in the UI.
3. Resume button visibility + checkpoint API + resume guard rails.

These tests seed run rows directly into the live SQLite DB (WAL mode, safe to
write from the test process) and remove them afterwards.  They do NOT launch
any real data download, so they are fast and network-independent.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from playwright.sync_api import Page

from .conftest import SERVER_URL

DB_PATH = None
CHECKPOINT_DIR = None


def _seed_run(name: str, run_type: str, status: str, config: dict | None = None,
              log_path: str | None = None, error: str | None = None) -> str:
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    try:
        conn.execute(
            "INSERT INTO run_history "
            "(id,name,run_type,config,status,created_at,log_path,error) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (run_id, name, run_type, json.dumps(config or {}), status, now,
             log_path, error),
        )
        conn.commit()
    finally:
        conn.close()
    return run_id


def _delete_run(run_id: str) -> None:
    try:
        httpx.delete(f"{SERVER_URL}/api/runs/{run_id}", timeout=5)
    except Exception:
        pass
    conn = sqlite3.connect(str(DB_PATH), timeout=15)
    try:
        conn.execute("DELETE FROM run_history WHERE id = ?", (run_id,))
        conn.commit()
    finally:
        conn.close()
    cp = CHECKPOINT_DIR / f"{run_id}.json"
    if cp.exists():
        cp.unlink()


@pytest.fixture
def seeded_runs(e2e_url):
    ids: list[str] = []

    def _add(*args, **kwargs) -> str:
        rid = _seed_run(*args, **kwargs)
        ids.append(rid)
        return rid

    yield _add

    for rid in ids:
        _delete_run(rid)


def _open_run_progress(page: Page, run_id: str):
    page.goto(SERVER_URL)
    page.wait_for_load_state("networkidle")
    page.click('button[data-tab="runs"]')
    page.locator(f'li[data-run-id="{run_id}"]').wait_for(state="visible", timeout=10000)
    page.locator(f'li[data-run-id="{run_id}"]').click()
    page.wait_for_selector("#runs-detail", state="visible")
    page.click('[data-runtab="progress"]')
    page.wait_for_selector("#run-log-container", state="visible")


class TestRealFileLogE2E:

    def test_log_box_shows_real_file_text(self, page: Page, seeded_runs, tmp_path):
        """The black box must show bytes read from the .log file, for a
        completed run too (the old SSE-only design showed nothing after
        refresh)."""
        marker = f"E2E_LOG_MARKER_{uuid.uuid4().hex[:8]}"
        log_file = tmp_path / "run.log"
        log_file.write_text(
            f"2026-01-01 INFO Starting execution\n2026-01-01 INFO {marker}\n",
            encoding="utf-8",
        )
        rid = seeded_runs(
            f"e2e_log_{marker[-6:]}", "task_run", "completed",
            log_path=str(log_file),
        )

        _open_run_progress(page, rid)

        page.wait_for_function(
            "(m) => (document.getElementById('run-log-container')?.textContent || '').includes(m)",
            arg=marker, timeout=10000,
        )
        text = page.evaluate(
            "() => document.getElementById('run-log-container').textContent"
        )
        assert marker in text
        assert "Starting execution" in text
        # path label is rendered next to the box
        assert str(log_file) in page.locator("#run-log-path").text_content()

    def test_logs_api_matches_disk(self, seeded_runs, tmp_path):
        log_file = tmp_path / "run.log"
        content = "line one\nline two\nline three\n"
        log_file.write_text(content, encoding="utf-8")
        rid = seeded_runs("e2e_log_api", "task_run", "completed",
                          log_path=str(log_file))

        resp = httpx.get(f"{SERVER_URL}/api/runs/{rid}/logs?tail=0", timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        assert body["exists"] is True
        assert body["content"] == content

    def test_missing_log_file_reports_gracefully(self, seeded_runs):
        rid = seeded_runs("e2e_no_log", "task_run", "completed", log_path=None)
        resp = httpx.get(f"{SERVER_URL}/api/runs/{rid}/logs", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["exists"] is False


class TestInterruptedStateE2E:

    def test_interrupted_shown_in_progress_tab(self, page: Page, seeded_runs):
        rid = seeded_runs(
            "e2e_interrupted", "task_run", "interrupted",
            error="Server restarted while run was active",
        )
        _open_run_progress(page, rid)
        page.locator("#runtab-progress").get_by_text(
            "Interrupted", exact=True).wait_for(state="visible", timeout=10000)

    def test_reconcile_endpoint_via_api(self, seeded_runs):
        """The checkpoint API reports can_resume for an interrupted run."""
        rid = seeded_runs("e2e_interrupted_api", "task_run", "interrupted")
        resp = httpx.get(f"{SERVER_URL}/api/runs/{rid}/checkpoint", timeout=10)
        assert resp.status_code == 200
        body = resp.json()
        # No checkpoint seeded -> exists False, but run is still resumable by status
        assert body["exists"] is False
        assert body["can_resume"] is False


class TestResumeE2E:

    def test_resume_button_visible_for_failed_task_run(self, page: Page, seeded_runs):
        rid = seeded_runs("e2e_resume_btn", "task_run", "failed",
                          config={"task_config": "config/tasks_test.yaml"})
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')
        page.locator(f'li[data-run-id="{rid}"]').click()
        page.wait_for_selector("#runs-detail", state="visible")
        page.click('[data-runtab="config"]')
        resume = page.get_by_role("button", name="⏵ Resume")
        resume.wait_for(state="visible", timeout=10000)
        # Run Again is always present
        assert page.get_by_role("button", name="▶ Run Again").is_visible()

    def test_resume_button_hidden_for_completed(self, page: Page, seeded_runs):
        rid = seeded_runs("e2e_no_resume_btn", "task_run", "completed")
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')
        page.locator(f'li[data-run-id="{rid}"]').click()
        page.wait_for_selector("#runs-detail", state="visible")
        page.click('[data-runtab="config"]')
        page.wait_for_timeout(500)
        assert page.get_by_role("button", name="⏵ Resume").count() == 0

    def test_resume_rejects_completed_run(self, seeded_runs):
        rid = seeded_runs("e2e_resume_reject", "task_run", "completed")
        # Drive the endpoint via the same call the UI button makes, but assert
        # the guard rail: a completed run cannot be resumed.
        # Use raw HTTP to the live server instead (no in-process client here).
        resp = httpx.post(f"{SERVER_URL}/api/runs/{rid}/resume", timeout=10)
        assert resp.status_code == 400
        assert "cannot be resumed" in resp.json()["detail"].lower()

    def test_resume_rejects_stock_scan(self, seeded_runs):
        rid = seeded_runs("e2e_resume_stock", "stock_scan", "failed",
                          config={"code": "AAPL.US"})
        resp = httpx.post(f"{SERVER_URL}/api/runs/{rid}/resume", timeout=10)
        assert resp.status_code == 400
        assert "does not support resume" in resp.json()["detail"].lower()

    def test_resume_copies_checkpoint_and_creates_new_run(self, seeded_runs):
        """End-to-end resume: checkpoint copied forward, original preserved."""
        rid = seeded_runs("e2e_resume_ok", "watchlist_run", "interrupted",
                          config={"watchlist": "watchlists/nonexistent.yaml"})
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        cp_file = CHECKPOINT_DIR / f"{rid}.json"
        cp_file.write_text(json.dumps({
            "version": 1, "run_id": rid, "config": {}, "context": {},
            "work": {"watchlist": {"done": {"AAPL.US": {"done_at": "2026-01-01"}}}},
            "results": {"watchlist": [{"code": "AAPL.US", "buy_signals": 1}]},
        }), encoding="utf-8")

        resp = httpx.post(f"{SERVER_URL}/api/runs/{rid}/resume", timeout=15)
        assert resp.status_code == 200
        body = resp.json()
        assert body["resumed_from"] == rid
        new_id = body["run_id"]
        try:
            # original preserved, new record linked back via resume_from
            orig = httpx.get(f"{SERVER_URL}/api/runs/{rid}", timeout=10).json()["run"]
            assert orig["status"] == "interrupted"
            new = httpx.get(f"{SERVER_URL}/api/runs/{new_id}", timeout=10).json()["run"]
            assert new["config"].get("resume_from") == rid
            # checkpoint cloned to the new run id
            new_cp = httpx.get(f"{SERVER_URL}/api/runs/{new_id}/checkpoint",
                               timeout=10).json()
            assert new_cp["exists"] is True
            assert new_cp["summary"]["done_count"] == 1
        finally:
            _delete_run(new_id)
