"""E2E tests for Runs Panel - Watchlist Run Workflow."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import httpx
import pytest
import yaml
from playwright.sync_api import Page, expect

from .conftest import PROJECT_ROOT, SERVER_URL, TEST_WATCHLIST_NAME

DB_PATH = PROJECT_ROOT / ".quantflow" / "runs.db"
TEST_STOCK_CODE = "NVDA.US"
RUN_TIMEOUT_SEC = 120
WATCHLIST_YAML = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"


@pytest.fixture(autouse=True)
def cleanup_runs_after_test(base_url):
    yield
    try:
        resp = httpx.get(f"{base_url}/api/runs/")
        if resp.status_code == 200:
            for run in resp.json().get("runs", []):
                if run.get("run_type") == "watchlist_run":
                    httpx.delete(f"{base_url}/api/runs/{run['id']}")
    except Exception:
        pass


def setup_test_watchlist(base_url):
    payload = {
        "name": TEST_WATCHLIST_NAME,
        "description": "E2E test watchlist",
        "items": [{"code": TEST_STOCK_CODE, "name": "Nvidia", "tags": []}],
    }
    resp = httpx.put(
        f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
        json=payload,
        timeout=30,
    )
    assert resp.status_code in (201, 200)
    assert WATCHLIST_YAML.exists()
    data = yaml.safe_load(WATCHLIST_YAML.read_text())
    assert len(data.get("items", [])) == 1


class TestRunsWatchlistRunWorkflow:

    def wait_for_run_completion(self, base_url: str, run_type: str) -> dict | None:
        deadline = time.time() + RUN_TIMEOUT_SEC
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/runs/")
                if resp.status_code == 200:
                    for run in resp.json().get("runs", []):
                        if run.get("run_type") == run_type:
                            if run["status"] == "completed":
                                return run
                            if run["status"] == "failed":
                                return run
            except Exception:
                pass
            time.sleep(3)
        return None

    def test_watchlist_run_full_lifecycle(self, page: Page, base_url: str):
        setup_test_watchlist(base_url)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")

        page.click("button[data-type='watchlist_run']")
        page.wait_for_selector("#run-config-watchlist_run", state="visible")

        page.locator("#run-watchlist-select").select_option(index=0)
        page.wait_for_timeout(500)

        page.click("#btn-execute-run")
        page.wait_for_timeout(2000)

        validation_errors = page.locator("#run-validation-errors")
        if validation_errors.is_visible():
            raise AssertionError(
                f"Preflight validation failed: {validation_errors.text_content()}"
            )

        page.wait_for_selector("#modal-new-run", state="hidden", timeout=10000)

        page.wait_for_function(
            f"""(wlName) => {{
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {{
                    if (item.textContent.includes(wlName)) return true;
                }}
                return false;
            }}""",
            arg=TEST_WATCHLIST_NAME,
            timeout=15000,
        )

        run = self.wait_for_run_completion(base_url, "watchlist_run")
        assert run is not None, "Run did not complete within timeout"
        assert run["status"] == "completed", f"Run failed: {run.get('error')}"

        page.reload()
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.wait_for_function(
            f"""(wlName) => {{
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {{
                    if (item.textContent.includes(wlName) && item.textContent.includes('completed')) {{
                        return true;
                    }}
                }}
                return false;
            }}""",
            arg=TEST_WATCHLIST_NAME,
            timeout=10000,
        )

        run_item = page.locator(
            f"li[data-run-id]:has-text('{TEST_WATCHLIST_NAME}')"
        ).first
        run_item.click()
        page.wait_for_selector("#runs-detail", state="visible")
        expect(page.locator("#runtab-config")).to_contain_text("completed")

        page.click('[data-runtab="report"]')
        expect(page.locator("#runtab-report")).not_to_contain_text(
            "No report available"
        )
        expect(page.locator("#runtab-report")).not_to_contain_text("Failed to load")

        page.click('[data-runtab="files"]')
        expect(
            page.locator("#runtab-files table tbody tr td").first
        ).to_contain_text(".md")

        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT status, report_path, output_path, signal_count FROM run_history WHERE config LIKE ? ORDER BY created_at DESC LIMIT 1",
                (f"%{TEST_WATCHLIST_NAME}%",),
            ).fetchall()

        assert len(rows) > 0, "Run should exist in DB"
        status, report_path, output_path, signal_count = rows[0]
        assert status == "completed", f"Expected completed, got {status}"
        assert report_path is not None, "Report path should not be null"
        assert output_path is not None, "Output path should not be null"

        report_file = Path(report_path)
        assert report_file.exists(), f"Report file should exist: {report_file}"
        report_text = report_file.read_text()
        assert "daily_bull_oversold" in report_text or "Buy" in report_text

        page.on("dialog", lambda dialog: dialog.accept())
        delete_btn = page.locator(
            f'li[data-run-id]:has-text("{TEST_WATCHLIST_NAME}"):has(button[title="Delete run"])'
        ).locator("button[title=\"Delete run\"]").first
        delete_btn.click()

        page.wait_for_function(
            f"""(wlName) => {{
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {{
                    if (item.textContent.includes(wlName)) return false;
                }}
                return true;
            }}""",
            arg=TEST_WATCHLIST_NAME,
            timeout=10000,
        )

        with sqlite3.connect(str(DB_PATH)) as conn:
            count = conn.execute(
                "SELECT count(*) FROM run_history WHERE config LIKE ?",
                (f"%{TEST_WATCHLIST_NAME}%",),
            ).fetchone()[0]

        assert count == 0, "Run should be deleted from DB"

    def test_run_type_cannot_modify_after_select(self, page: Page, base_url: str):
        setup_test_watchlist(base_url)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")

        page.click("button[data-type='stock_scan']")
        page.wait_for_selector("#run-config-stock_scan", state="visible")

        page.click("#btn-back-run")
        page.wait_for_selector("#run-step-type", state="visible")

        step_type = page.locator("#run-step-type")
        expect(step_type).to_be_visible()
        config_stock = page.locator("#run-config-stock_scan")
        expect(config_stock).to_be_hidden()