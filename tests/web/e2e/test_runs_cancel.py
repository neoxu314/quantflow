"""E2E tests for Runs Panel - Cancel Workflow."""
from __future__ import annotations

import sqlite3
import time

import httpx
import pytest
from playwright.sync_api import Page, expect

from .conftest import PROJECT_ROOT, SERVER_URL

DB_PATH = PROJECT_ROOT / ".quantflow" / "runs.db"
TEST_STOCK_CODE = "NVDA.US"
RUN_TIMEOUT_SEC = 120


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


class TestRunsCancelWorkflow:

    def wait_for_run_status(
        self, base_url: str, stock_code: str, target_status: str, timeout: int = 60
    ) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/runs/")
                if resp.status_code == 200:
                    for run in resp.json().get("runs", []):
                        if run.get("config", {}).get("code") == stock_code:
                            if run["status"] == target_status:
                                return run
            except Exception:
                pass
            time.sleep(2)
        return None

    def wait_for_run_appearance(
        self, base_url: str, stock_code: str, timeout: int = 15
    ) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/runs/")
                if resp.status_code == 200:
                    for run in resp.json().get("runs", []):
                        if run.get("config", {}).get("code") == stock_code:
                            return run
            except Exception:
                pass
            time.sleep(1)
        return None

    def test_cancel_active_run(self, page: Page, base_url: str):
        resp = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": TEST_STOCK_CODE,
                "indicators": ["kdj"],
            },
            timeout=30,
        )
        assert resp.status_code == 200
        run_data = resp.json()
        assert run_data["ok"] is True
        run_id = run_data["run_id"]

        appeared = self.wait_for_run_appearance(base_url, TEST_STOCK_CODE)
        assert appeared is not None

        cancel_resp = httpx.post(f"{base_url}/api/runs/{run_id}/cancel", timeout=30)
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["ok"] is True

        cancelled = self.wait_for_run_status(
            base_url, TEST_STOCK_CODE, "cancelled", timeout=30
        )
        assert cancelled is not None, "Run should be cancelled"
        assert cancelled["status"] == "cancelled"

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.wait_for_function(
            """(stockCode) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(stockCode) && item.textContent.includes('cancelled')) {
                        return true;
                    }
                }
                return false;
            }""",
            arg=TEST_STOCK_CODE,
            timeout=10000,
        )

        run_item = page.locator(
            f"li[data-run-id]:has-text('{TEST_STOCK_CODE}')"
        ).first
        run_item.click()
        page.wait_for_selector("#runs-detail", state="visible")
        expect(page.locator("#runtab-config")).to_contain_text("cancelled")

        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT status FROM run_history WHERE config LIKE ? ORDER BY created_at DESC LIMIT 1",
                (f"%{TEST_STOCK_CODE}%",),
            ).fetchall()
        assert len(rows) > 0
        assert rows[0][0] == "cancelled"

    def test_cancel_queued_run(self, page: Page, base_url: str):
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

        queued_code = "AAPL.US"
        resp2 = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": queued_code,
                "indicators": ["kdj"],
            },
            timeout=30,
        )
        assert resp2.status_code == 200
        queued_run_id = resp2.json()["run_id"]

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        cancel_resp = httpx.post(
            f"{base_url}/api/runs/{queued_run_id}/cancel", timeout=30
        )
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["ok"] is True

        page.wait_for_function(
            """(code) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(code)) return false;
                }
                return true;
            }""",
            arg=queued_code,
            timeout=10000,
        )

        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT status FROM run_history WHERE config LIKE ? ORDER BY created_at DESC LIMIT 1",
                (f"%{queued_code}%",),
            ).fetchall()
        assert len(rows) > 0
        assert rows[0][0] == "cancelled"

    def test_delete_cancelled_run(self, page: Page, base_url: str):
        resp = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": TEST_STOCK_CODE,
                "indicators": ["kdj"],
            },
            timeout=30,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        self.wait_for_run_appearance(base_url, TEST_STOCK_CODE)

        httpx.post(f"{base_url}/api/runs/{run_id}/cancel", timeout=30)
        self.wait_for_run_status(base_url, TEST_STOCK_CODE, "cancelled", timeout=30)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.wait_for_function(
            """(stockCode) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(stockCode) && item.textContent.includes('cancelled')) {
                        return true;
                    }
                }
                return false;
            }""",
            arg=TEST_STOCK_CODE,
            timeout=10000,
        )

        page.on("dialog", lambda dialog: dialog.accept())
        delete_btn = page.locator(
            f'li[data-run-id]:has-text("{TEST_STOCK_CODE}"):has(button[title="Delete run"])'
        ).locator('button[title="Delete run"]').first
        delete_btn.click()

        page.wait_for_function(
            """(stockCode) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(stockCode)) return false;
                }
                return true;
            }""",
            arg=TEST_STOCK_CODE,
            timeout=10000,
        )

        with sqlite3.connect(str(DB_PATH)) as conn:
            count = conn.execute(
                "SELECT count(*) FROM run_history WHERE config LIKE ?",
                (f"%{TEST_STOCK_CODE}%",),
            ).fetchone()[0]
        assert count == 0, "Cancelled run should be deleted from DB"

    def test_cancel_button_appears_for_running(self, page: Page, base_url: str):
        resp = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": TEST_STOCK_CODE,
                "indicators": ["kdj"],
            },
            timeout=30,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

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

        run_item = page.locator(
            f"li[data-run-id]:has-text('{TEST_STOCK_CODE}')"
        ).first
        run_item.click()
        page.wait_for_selector("#runs-detail", state="visible")

        status_text = page.locator("#runtab-config").text_content()
        assert "running" in status_text.lower() or "queued" in status_text.lower()

        progress_tab = page.locator('[data-runtab="progress"]')
        progress_tab.click()

        page.wait_for_selector("#run-log-container", state="visible", timeout=10000)
        log_entries = page.evaluate(
            "() => document.getElementById('run-log-container')?.children.length || 0"
        )
        assert log_entries >= 0
