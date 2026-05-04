"""E2E tests for Runs Panel - Stock Scan Workflow."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path

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


class TestRunsStockScanWorkflow:

    def wait_for_run_completion(self, base_url: str, stock_code: str) -> dict | None:
        deadline = time.time() + RUN_TIMEOUT_SEC
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/runs/")
                if resp.status_code == 200:
                    for run in resp.json().get("runs", []):
                        if run.get("config", {}).get("code") == stock_code:
                            if run["status"] == "completed":
                                return run
                            if run["status"] == "failed":
                                return run
            except Exception:
                pass
            time.sleep(3)
        return None

    def test_stock_scan_full_lifecycle(self, page: Page, base_url: str):
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")

        page.click("button[data-type='stock_scan']")
        page.wait_for_selector("#run-config-stock_scan", state="visible")

        code_input = page.locator("#run-stock-code")
        code_input.fill(TEST_STOCK_CODE)
        page.wait_for_timeout(500)

        page.click("#btn-execute-run")
        page.wait_for_selector("#modal-new-run", state="hidden")

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

        run = self.wait_for_run_completion(base_url, TEST_STOCK_CODE)
        assert run is not None, "Run did not complete within timeout"
        assert run["status"] == "completed", f"Run failed: {run.get('error')}"

        page.reload()
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

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
            arg=TEST_STOCK_CODE,
            timeout=10000,
        )

        run_item = page.locator(
            f"li[data-run-id]:has-text('{TEST_STOCK_CODE}')"
        ).first
        run_item.click()
        page.wait_for_selector("#runs-detail", state="visible")
        expect(page.locator("#runtab-config")).to_contain_text("completed")

        page.click('[data-runtab="files"]')
        expect(
            page.locator("#runtab-files table tbody tr td").first
        ).to_contain_text("indicators.json")

        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT status, report_path FROM run_history WHERE config LIKE ? ORDER BY created_at DESC LIMIT 1",
                (f"%{TEST_STOCK_CODE}%",),
            ).fetchall()

        assert len(rows) > 0, "Run should exist in DB"
        status, report_path = rows[0]
        assert status == "completed", f"Expected completed, got {status}"
        assert report_path is not None, "Report path should not be null"

        report_file = Path(report_path)
        assert report_file.exists(), f"Output file should exist: {report_file}"

        with open(report_file) as f:
            data = json.load(f)

        assert isinstance(data, list), "Report should be a JSON list"
        assert len(data) > 0, "Report data should not be empty"

        first_row = data[0]
        has_indicator = any(
            k in ("K", "D", "J", "MACD", "short_trend_line") for k in first_row
        )
        assert has_indicator, "Data row must contain indicator columns (K/D/J/etc)"

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

        assert count == 0, "Run should be deleted from DB"
        assert not report_file.exists(), "Output file should be deleted"
