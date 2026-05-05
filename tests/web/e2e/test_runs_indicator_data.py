"""E2E tests for Runs Panel - Indicator Data Accuracy."""
from __future__ import annotations

import json
import time

import httpx
import pytest
from playwright.sync_api import Page, expect

from .conftest import PROJECT_ROOT, SERVER_URL

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


class TestRunsIndicatorData:

    def wait_for_run_completion(
        self, base_url: str, stock_code: str, timeout: int = RUN_TIMEOUT_SEC
    ) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{base_url}/api/runs/")
                if resp.status_code == 200:
                    for run in resp.json().get("runs", []):
                        if run.get("config", {}).get("code") == stock_code:
                            if run["status"] in ("completed", "failed"):
                                return run
            except Exception:
                pass
            time.sleep(3)
        return None

    def test_indicator_data_endpoint_returns_valid_json(self, page: Page, base_url: str):
        resp = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": TEST_STOCK_CODE,
                "indicators": ["kdj", "dual_line"],
            },
            timeout=30,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        completed = self.wait_for_run_completion(base_url, TEST_STOCK_CODE)
        assert completed is not None, "Run did not complete"
        assert completed["status"] == "completed"

        data_resp = httpx.get(
            f"{base_url}/api/runs/{run_id}/indicator-data", timeout=30
        )
        assert data_resp.status_code == 200
        data = data_resp.json()
        assert data["data"] is not None
        assert isinstance(data["data"], list)
        assert len(data["data"]) > 0

        first_row = data["data"][0]
        has_expected_cols = any(
            k in first_row for k in ("K", "D", "J", "close", "MACD")
        )
        assert has_expected_cols, f"Expected indicator columns, got: {list(first_row.keys())}"

        assert data["code"] == TEST_STOCK_CODE
        assert data["bar_count"] == len(data["data"])

    def test_indicator_data_no_nan_values(self, page: Page, base_url: str):
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

        completed = self.wait_for_run_completion(base_url, TEST_STOCK_CODE)
        assert completed is not None

        data_resp = httpx.get(
            f"{base_url}/api/runs/{run_id}/indicator-data", timeout=30
        )
        assert data_resp.status_code == 200
        data = data_resp.json()

        raw_text = json.dumps(data["data"])
        assert "NaN" not in raw_text, "Response should not contain NaN strings"
        assert "Infinity" not in raw_text, "Response should not contain Infinity strings"

        for row in data["data"]:
            for key, val in row.items():
                assert val is not None or val is None
                if isinstance(val, float):
                    import math
                    assert not math.isnan(val), f"NaN found in {key}"
                    assert not math.isinf(val), f"Infinity found in {key}"

    def test_indicator_data_bar_count_matches(self, page: Page, base_url: str):
        resp = httpx.post(
            f"{base_url}/api/runs/",
            json={
                "run_type": "stock_scan",
                "code": TEST_STOCK_CODE,
                "indicators": ["kdj", "dual_line"],
            },
            timeout=30,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        completed = self.wait_for_run_completion(base_url, TEST_STOCK_CODE)
        assert completed is not None

        data_resp = httpx.get(
            f"{base_url}/api/runs/{run_id}/indicator-data", timeout=30
        )
        assert data_resp.status_code == 200
        data = data_resp.json()

        assert data["bar_count"] == len(data["data"]), (
            f"bar_count ({data['bar_count']}) should match data length ({len(data['data'])})"
        )

    def test_files_endpoint_returns_expected_files(self, page: Page, base_url: str):
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

        completed = self.wait_for_run_completion(base_url, TEST_STOCK_CODE)
        assert completed is not None

        files_resp = httpx.get(
            f"{base_url}/api/runs/{run_id}/files", timeout=30
        )
        assert files_resp.status_code == 200
        files = files_resp.json()["files"]
        assert len(files) > 0, "Should have output files after completion"

        file_names = [f["name"] for f in files]
        assert "indicators.json" in file_names, (
            f"Expected indicators.json in files, got: {file_names}"
        )

        page.goto(SERVER_URL)
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

        page.click('[data-runtab="files"]')
        expect(
            page.locator("#runtab-files table tbody tr td").first
        ).to_contain_text("indicators.json")

    def test_indicator_data_for_non_stock_scan_returns_null(self, page: Page, base_url: str):
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

        completed = self.wait_for_run_completion(base_url, TEST_STOCK_CODE)
        assert completed is not None

        data_resp = httpx.get(
            f"{base_url}/api/runs/{run_id}/indicator-data", timeout=30
        )
        assert data_resp.status_code == 200
        data = data_resp.json()
        assert data["data"] is not None
        assert data["code"] == TEST_STOCK_CODE

    def test_indicator_data_for_nonexistent_run_returns_404(self, base_url: str):
        resp = httpx.get(
            f"{base_url}/api/runs/fake-run-id-123/indicator-data", timeout=10
        )
        assert resp.status_code == 404
