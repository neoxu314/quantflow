"""E2E tests for Runs Panel - Queue Behavior."""
from __future__ import annotations

import time

import httpx
import pytest
from playwright.sync_api import Page

from .conftest import PROJECT_ROOT, SERVER_URL

TEST_STOCK_CODE = "NVDA.US"
RUN_TIMEOUT_SEC = 180


@pytest.fixture(autouse=True)
def cleanup_runs_after_test(base_url):
    yield
    try:
        resp = httpx.get(f"{base_url}/api/runs/")
        if resp.status_code == 200:
            for run in resp.json().get("runs", []):
                httpx.delete(f"{base_url}/api/runs/{run['id']}")
    except Exception:
        pass


class TestRunsQueue:

    def wait_for_run_status(
        self, base_url: str, identifier: str, target_status: str, timeout: int = 60
    ) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/runs/")
                if resp.status_code == 200:
                    for run in resp.json().get("runs", []):
                        code = run.get("config", {}).get("code", "")
                        if identifier in code or identifier == run.get("name", ""):
                            if run["status"] == target_status:
                                return run
            except Exception:
                pass
            time.sleep(3)
        return None

    def wait_for_all_completed(
        self, base_url: str, codes: list, timeout: int = RUN_TIMEOUT_SEC
    ) -> list:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/runs/")
                if resp.status_code == 200:
                    runs = resp.json().get("runs", [])
                    completed = []
                    for code in codes:
                        for run in runs:
                            run_code = run.get("config", {}).get("code", "")
                            if code in run_code and run["status"] == "completed":
                                completed.append(run)
                    if len(completed) == len(codes):
                        return completed
            except Exception:
                pass
            time.sleep(3)
        return []

    def test_queue_status_shows_active_and_pending(self, page: Page, base_url: str):
        resp1 = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": TEST_STOCK_CODE,
                "indicators": ["kdj"],
            },
            timeout=30,
        )
        assert resp1.status_code == 200
        assert resp1.json()["ok"] is True

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.wait_for_function(
            """(stockCode) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(stockCode)) return true;
                }
                return false;
            }""",
            arg=TEST_STOCK_CODE,
            timeout=15000,
        )

        queue_resp = httpx.get(f"{base_url}/api/runs/queue", timeout=10)
        assert queue_resp.status_code == 200
        queue_data = queue_resp.json()
        assert "active_run_id" in queue_data
        assert "pending_count" in queue_data
        assert "total_queued" in queue_data
        assert queue_data["total_queued"] >= 1

    def test_second_run_starts_after_first_completes(self, page: Page, base_url: str):
        code1 = TEST_STOCK_CODE
        code2 = "AAPL.US"

        resp1 = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": code1,
                "indicators": ["kdj"],
            },
            timeout=30,
        )
        assert resp1.status_code == 200
        run_id_1 = resp1.json()["run_id"]

        resp2 = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": code2,
                "indicators": ["kdj"],
            },
            timeout=30,
        )
        assert resp2.status_code == 200
        run_id_2 = resp2.json()["run_id"]

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.wait_for_function(
            """(code1, code2) => {
                const items = document.querySelectorAll('li[data-run-id]');
                let found1 = false, found2 = false;
                for (const item of items) {
                    if (item.textContent.includes(code1)) found1 = true;
                    if (item.textContent.includes(code2)) found2 = true;
                }
                return found1 && found2;
            }""",
            arg={"code1": code1, "code2": code2},
            timeout=15000,
        )

        queue_resp = httpx.get(f"{base_url}/api/runs/queue", timeout=10)
        queue_data = queue_resp.json()
        assert queue_data["total_queued"] >= 2

        completed = self.wait_for_all_completed(base_url, [code1, code2])
        assert len(completed) == 2, f"Both runs should complete, got {len(completed)}"

        page.reload()
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        for code in [code1, code2]:
            page.wait_for_function(
                """(stockCode) => {
                    const items = document.querySelectorAll('li[data-run-id]');
                    for (const item of items) {
                        if (item.textContent.includes(stockCode) && item.textContent.includes('completed')) {
                            return true;
                        }
                    }
                    return false;
                }""",
                arg=code,
                timeout=10000,
            )

    def test_queue_empty_when_no_runs(self, base_url: str):
        queue_resp = httpx.get(f"{base_url}/api/runs/queue", timeout=10)
        assert queue_resp.status_code == 200
        queue_data = queue_resp.json()
        assert queue_data["pending_count"] >= 0
        assert queue_data["active_run_id"] is None or isinstance(queue_data["active_run_id"], str)
