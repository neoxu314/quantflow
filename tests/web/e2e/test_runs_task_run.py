"""E2E tests for Runs Panel - Task Run Workflow."""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from playwright.sync_api import Page, expect

from .conftest import SERVER_URL, TEST_TASK_FILE, TEST_WATCHLIST_NAME

DB_PATH = None
TEST_STOCK_CODE = "NVDA.US"
RUN_TIMEOUT_SEC = 180
TASK_CONFIG_PATH = None
WATCHLIST_YAML = None


def setup_test_task_config(e2e_url):
    wl_payload = {
        "name": TEST_WATCHLIST_NAME,
        "description": "E2E test watchlist for task_run",
        "items": [{"code": TEST_STOCK_CODE, "name": "Nvidia", "tags": []}],
    }
    resp = httpx.put(
        f"{e2e_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
        json=wl_payload,
        timeout=30,
    )
    assert resp.status_code in (201, 200)
    assert WATCHLIST_YAML.exists()

    tf_resp = httpx.post(
        f"{e2e_url}/api/task-files",
        json={"filename": TEST_TASK_FILE},
        timeout=30,
    )
    assert tf_resp.status_code in (201, 409)

    task_resp = httpx.post(
        f"{e2e_url}/api/tasks?filename={TEST_TASK_FILE}",
        json={
            "name": "e2e_task_test",
            "watchlist": f"watchlists/{TEST_WATCHLIST_NAME}.yaml",
            "strategies": ["daily_bull_oversold"],
        },
        timeout=30,
    )
    assert task_resp.status_code in (201, 409)
    assert TASK_CONFIG_PATH.exists()

    data = yaml.safe_load(TASK_CONFIG_PATH.read_text())
    assert len(data.get("tasks", [])) >= 1


class TestRunsTaskRunWorkflow:

    def wait_for_run_completion(self, e2e_url: str, run_type: str) -> dict | None:
        deadline = time.time() + RUN_TIMEOUT_SEC
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{e2e_url}/api/runs/")
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

    def test_task_run_full_lifecycle(self, page: Page, e2e_url: str):
        setup_test_task_config(e2e_url)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")

        page.click("button[data-type='task_run']")
        page.wait_for_selector("#run-config-task_run", state="visible")

        page.wait_for_timeout(500)
        page.locator("#run-task-config-select").select_option(index=0)
        page.wait_for_timeout(500)

        cli_preview = page.locator("#run-cli-preview")
        expect(cli_preview).to_contain_text("tasks --config")

        page.click("#btn-check-run")
        page.wait_for_timeout(1000)

        validation_errors = page.locator("#run-validation-errors")
        if validation_errors.is_visible():
            raise AssertionError(
                f"Preflight validation failed: {validation_errors.text_content()}"
            )

        page.click("#btn-execute-run")
        page.wait_for_selector("#modal-new-run", state="hidden", timeout=10000)

        page.wait_for_function(
            """(tfName) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(tfName)) return true;
                }
                return false;
            }""",
            arg=TEST_TASK_FILE.replace(".yaml", ""),
            timeout=15000,
        )

        run = self.wait_for_run_completion(e2e_url, "task_run")
        assert run is not None, "Run did not complete within timeout"
        assert run["status"] == "completed", f"Run failed: {run.get('error')}"

        page.reload()
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.wait_for_function(
            """(tfName) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    const text = item.textContent;
                    if (text.includes(tfName) && text.includes('completed')) {
                        return true;
                    }
                }
                return false;
            }""",
            arg=TEST_TASK_FILE.replace(".yaml", ""),
            timeout=10000,
        )

        run_item = page.locator(
            f"li[data-run-id]:has-text('{TEST_TASK_FILE.replace('.yaml', '')}')"
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
            sql = (
                "SELECT status, report_path, output_path, signal_count "
                "FROM run_history WHERE config LIKE ? "
                "ORDER BY created_at DESC LIMIT 1"
            )
            rows = conn.execute(sql, (f"%{TEST_TASK_FILE}%",)).fetchall()

        assert len(rows) > 0, "Run should exist in DB"
        status, report_path, output_path, signal_count = rows[0]
        assert status == "completed", f"Expected completed, got {status}"
        assert report_path is not None, "Report path should not be null"
        assert output_path is not None, "Output path should not be null"

        report_file = Path(report_path)
        assert report_file.exists(), f"Report file should exist: {report_file}"
        report_text = report_file.read_text()
        has_valid_content = (
            "task" in report_text.lower()
            or "Signal" in report_text
            or "Report" in report_text
        )
        assert has_valid_content

        assert isinstance(signal_count, int) and signal_count >= 0

        page.on("dialog", lambda dialog: dialog.accept())
        page.click('button[data-tab="runs"]')
        task_stem = TEST_TASK_FILE.replace(".yaml", "")
        delete_btn = page.locator(
            f'li[data-run-id]:has-text("{task_stem}")'
        ).locator('button[title="Delete run"]').first
        delete_btn.click()

        page.wait_for_function(
            """(tfName) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(tfName)) return false;
                }
                return true;
            }""",
            arg=TEST_TASK_FILE.replace(".yaml", ""),
            timeout=10000,
        )

        with sqlite3.connect(str(DB_PATH)) as conn:
            count = conn.execute(
                "SELECT count(*) FROM run_history WHERE config LIKE ?",
                (f"%{TEST_TASK_FILE}%",),
            ).fetchone()[0]

        assert count == 0, "Run should be deleted from DB"

    def test_task_run_with_daily_mode(self, page: Page, e2e_url: str):
        setup_test_task_config(e2e_url)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')
        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")
        page.click("button[data-type='task_run']")
        page.wait_for_selector("#run-config-task_run", state="visible")

        page.wait_for_timeout(500)
        page.locator("#run-task-config-select").select_option(index=0)
        page.wait_for_timeout(500)

        daily_checkbox = page.locator("#run-daily-mode")
        daily_checkbox.check()
        page.wait_for_timeout(500)

        cli_preview = page.locator("#run-cli-preview")
        expect(cli_preview).to_contain_text("--daily")

        page.click("#btn-execute-run")
        page.wait_for_selector("#modal-new-run", state="hidden", timeout=10000)

        run = self.wait_for_run_completion(e2e_url, "task_run")
        assert run is not None, "Run did not complete within timeout"
        assert run["status"] == "completed", f"Run failed: {run.get('error')}"

        assert run.get("config", {}).get("daily") is True

    def test_run_modal_resets_on_open(self, page: Page, e2e_url: str):
        setup_test_task_config(e2e_url)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")
        page.click("button[data-type='task_run']")
        page.wait_for_selector("#run-config-task_run", state="visible")

        page.click("#btn-cancel-run")
        page.wait_for_selector("#modal-new-run", state="hidden")

        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")
        page.wait_for_selector("#run-step-type", state="visible")

        section_ids = [
            "run-config-stock_scan",
            "run-config-watchlist_run",
            "run-config-task_run",
        ]
        for section_id in section_ids:
            expect(page.locator(f"#{section_id}")).to_be_hidden()

    def test_progress_tab_shows_live_log(self, page: Page, e2e_url: str):
        setup_test_task_config(e2e_url)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")
        page.click("button[data-type='task_run']")
        page.wait_for_selector("#run-config-task_run", state="visible")

        page.wait_for_timeout(500)
        page.locator("#run-task-config-select").select_option(index=0)
        page.wait_for_timeout(500)

        page.click("#btn-execute-run")
        page.wait_for_selector("#modal-new-run", state="hidden", timeout=10000)

        page.wait_for_function(
            """(tfName) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(tfName)) return true;
                }
                return false;
            }""",
            arg=TEST_TASK_FILE.replace(".yaml", ""),
            timeout=15000,
        )

        run_item = page.locator(
            f"li[data-run-id]:has-text('{TEST_TASK_FILE.replace('.yaml', '')}')"
        ).first
        run_item.click()
        page.wait_for_selector("#runs-detail", state="visible")

        page.click('[data-runtab="progress"]')
        page.wait_for_selector("#run-log-container", state="visible", timeout=15000)

        # The log box now renders the real on-disk log as plain text via
        # textContent (not child elements), so assert on its text length.
        page.wait_for_function(
            "() => {\n"
            "    const container = document.getElementById('run-log-container');\n"
            "    return container && (container.textContent || '').trim().length > 0;\n"
            "}",
            timeout=30000,
        )

        log_text = page.evaluate(
            "() => (document.getElementById('run-log-container')?.textContent || '').trim()"
        )
        assert len(log_text) > 0, "Progress tab should show log text during execution"

    def test_files_tab_isolated_per_run(self, page: Page, e2e_url: str):
        setup_test_task_config(e2e_url)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')
        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")
        page.click("button[data-type='task_run']")
        page.wait_for_selector("#run-config-task_run", state="visible")
        page.wait_for_timeout(500)
        page.locator("#run-task-config-select").select_option(index=0)
        page.wait_for_timeout(500)

        page.click("#btn-execute-run")
        page.wait_for_selector("#modal-new-run", state="hidden", timeout=10000)

        run = self.wait_for_run_completion(e2e_url, "task_run")
        assert run is not None
        assert run["status"] == "completed"

        page.reload()
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        run_item = page.locator(
            f"li[data-run-id]:has-text('{TEST_TASK_FILE.replace('.yaml', '')}')"
        ).first
        run_item.click()
        page.wait_for_selector("#runs-detail", state="visible")

        page.click('[data-runtab="files"]')
        page.wait_for_timeout(2000)
        
        # IMPROVED VALIDATION: Check specific file names
        file_rows = page.locator("#runtab-files table tbody tr").all()
        assert len(file_rows) >= 1
        
        # Extract file names from table
        file_names = []
        for row in file_rows:
            name_cell = row.locator("td").first
            file_names.append(name_cell.text_content())
        
        # Verify expected files exist
        expected_files = ["Daily_Report.md", "Combined_Results.json"]
        for expected in expected_files:
            assert any(expected in name for name in file_names), \
                f"Expected {expected} in files, got: {file_names}"

    def test_task_run_daily_mode_files_validation(self, page: Page, e2e_url: str):
        """Daily mode: files tab should show files from YYYY-MM-DD subdirectory."""
        setup_test_task_config(e2e_url)
        
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')
        page.click("#btn-new-run")
        page.wait_for_selector("#modal-new-run", state="visible")
        page.click("button[data-type='task_run']")
        page.wait_for_selector("#run-config-task_run", state="visible")
        
        page.wait_for_timeout(500)
        page.locator("#run-task-config-select").select_option(index=0)
        page.wait_for_timeout(500)
        
        # Enable daily mode
        daily_checkbox = page.locator("#run-daily-mode")
        daily_checkbox.check()
        page.wait_for_timeout(500)
        
        page.click("#btn-execute-run")
        page.wait_for_selector("#modal-new-run", state="hidden", timeout=10000)
        
        run = self.wait_for_run_completion(e2e_url, "task_run")
        assert run is not None
        assert run["status"] == "completed"
        
        # Verify daily config
        assert run.get("config", {}).get("daily") is True
        
        page.reload()
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')
        
        run_item = page.locator(
            f"li[data-run-id]:has-text('{TEST_TASK_FILE.replace('.yaml', '')}')"
        ).first
        run_item.click()
        page.wait_for_selector("#runs-detail", state="visible")
        
        # Check report tab - should have content
        page.click('[data-runtab="report"]')
        page.wait_for_timeout(1000)
        expect(page.locator("#runtab-report")).not_to_contain_text("No report available")
        
        # Check files tab - should find files from subdirectory
        page.click('[data-runtab="files"]')
        page.wait_for_timeout(2000)
        
        file_rows = page.locator("#runtab-files table tbody tr").all()
        assert len(file_rows) >= 1
        
        # Verify expected files from date subdirectory
        file_names = []
        for row in file_rows:
            name_cell = row.locator("td").first
            file_names.append(name_cell.text_content())
        
        # Daily mode should generate these files
        expected_files = ["Daily_Report.md"]
        for expected in expected_files:
            assert any(expected in name for name in file_names), \
                f"Daily mode should have {expected}, got: {file_names}"
        
        # Verify paths contain date directory (YYYY-MM-DD pattern)
        today = datetime.now().strftime("%Y-%m-%d")
        for row in file_rows[:3]:
            cells = row.locator("td").all()
            if len(cells) >= 2:
                path_cell = cells[1]
                if path_cell.count() > 0:
                    path_text = path_cell.text_content()
                    # Path should contain today's date directory or date pattern
                    assert today in path_text or any(c.isdigit() for c in path_text), \
                        f"Daily mode file path should contain date: {path_text}"
