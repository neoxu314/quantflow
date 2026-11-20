"""E2E tests for Presets CRUD and run-from-preset."""
from __future__ import annotations

import sqlite3
import time

import httpx
from playwright.sync_api import Page, expect

from .conftest import SERVER_URL

DB_PATH = None
TEST_STOCK_CODE = "NVDA.US"
RUN_TIMEOUT_SEC = 120


class TestPresets:

    def wait_for_run_completion(
        self, e2e_url: str, preset_name: str, timeout: int = RUN_TIMEOUT_SEC
    ) -> dict | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = httpx.get(f"{e2e_url}/api/runs/")
                if resp.status_code == 200:
                    for run in resp.json().get("runs", []):
                        if run.get("name") == preset_name:
                            if run["status"] in ("completed", "failed"):
                                return run
            except Exception:
                pass
            time.sleep(3)
        return None

    def test_create_preset_via_api(self, e2e_url: str):
        preset_name = "_e2e_test_preset_stock_scan"
        resp = httpx.post(
            f"{e2e_url}/api/presets/",
            json={
                "name": preset_name,
                "run_type": "stock_scan",
                "config": {
                    "code": TEST_STOCK_CODE,
                    "indicators": ["kdj", "dual_line"],
                },
            },
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "preset_id" in data

        resp = httpx.get(f"{e2e_url}/api/presets/", timeout=10)
        assert resp.status_code == 200
        presets = resp.json().get("presets", [])
        names = [p["name"] for p in presets]
        assert preset_name in names

        httpx.delete(f"{e2e_url}/api/presets/{data['preset_id']}")

    def test_create_preset_watchlist(self, e2e_url: str):
        preset_name = "_e2e_test_preset_watchlist"
        resp = httpx.post(
            f"{e2e_url}/api/presets/",
            json={
                "name": preset_name,
                "run_type": "watchlist_run",
                "config": {
                    "watchlist": "watchlists/DJIA.yaml",
                    "strategies": ["daily_bull_oversold"],
                },
            },
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

        resp = httpx.get(f"{e2e_url}/api/presets/", timeout=10)
        presets = resp.json().get("presets", [])
        found = [p for p in presets if p["name"] == preset_name]
        assert len(found) == 1
        assert found[0]["run_type"] == "watchlist_run"

        httpx.delete(f"{e2e_url}/api/presets/{data['preset_id']}")

    def test_delete_preset(self, e2e_url: str):
        preset_name = "_e2e_test_preset_delete"
        resp = httpx.post(
            f"{e2e_url}/api/presets/",
            json={
                "name": preset_name,
                "run_type": "stock_scan",
                "config": {"code": "AAPL.US", "indicators": ["kdj"]},
            },
            timeout=10,
        )
        assert resp.status_code == 200
        preset_id = resp.json()["preset_id"]

        resp = httpx.delete(f"{e2e_url}/api/presets/{preset_id}", timeout=10)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        resp = httpx.get(f"{e2e_url}/api/presets/", timeout=10)
        presets = resp.json().get("presets", [])
        ids = [p["id"] for p in presets]
        assert preset_id not in ids

    def test_delete_nonexistent_preset_returns_404(self, e2e_url: str):
        resp = httpx.delete(
            f"{e2e_url}/api/presets/nonexistent-id-12345", timeout=10
        )
        assert resp.status_code == 404

    def test_run_from_preset(self, page: Page, e2e_url: str):
        preset_name = "_e2e_preset_run_test"
        resp = httpx.post(
            f"{e2e_url}/api/presets/",
            json={
                "name": preset_name,
                "run_type": "stock_scan",
                "config": {
                    "code": TEST_STOCK_CODE,
                    "indicators": ["kdj"],
                },
            },
            timeout=10,
        )
        assert resp.status_code == 200
        preset_id = resp.json()["preset_id"]

        run_resp = httpx.post(
            f"{e2e_url}/api/presets/{preset_id}/run", timeout=30
        )
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["ok"] is True
        assert "run_id" in run_data

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.wait_for_function(
            """(name) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(name)) return true;
                }
                return false;
            }""",
            arg=preset_name,
            timeout=15000,
        )

        completed = self.wait_for_run_completion(e2e_url, preset_name)
        assert completed is not None, "Run from preset did not complete"
        assert completed["status"] == "completed"

        page.reload()
        page.wait_for_load_state("networkidle")
        page.click('button[data-tab="runs"]')

        page.wait_for_function(
            """(name) => {
                const items = document.querySelectorAll('li[data-run-id]');
                for (const item of items) {
                    if (item.textContent.includes(name) && item.textContent.includes('completed')) {
                        return true;
                    }
                }
                return false;
            }""",
            arg=preset_name,
            timeout=10000,
        )

        run_item = page.locator(
            f"li[data-run-id]:has-text('{preset_name}')"
        ).first
        run_item.click()
        page.wait_for_selector("#runs-detail", state="visible")
        expect(page.locator("#runtab-config")).to_contain_text("completed")

        with sqlite3.connect(str(DB_PATH)) as conn:
            rows = conn.execute(
                "SELECT status, preset_id FROM run_history WHERE name LIKE ? ORDER BY created_at DESC LIMIT 1",
                (f"%{preset_name}%",),
            ).fetchall()
        assert len(rows) > 0
        assert rows[0][0] == "completed"
        assert rows[0][1] == preset_id

        httpx.delete(f"{e2e_url}/api/presets/{preset_id}")

    def test_preset_persists_across_reload(self, page: Page, e2e_url: str):
        preset_name = "_e2e_persist_test"
        resp = httpx.post(
            f"{e2e_url}/api/presets/",
            json={
                "name": preset_name,
                "run_type": "stock_scan",
                "config": {"code": "AAPL.US", "indicators": ["kdj"]},
            },
            timeout=10,
        )
        assert resp.status_code == 200
        preset_id = resp.json()["preset_id"]

        page.reload()
        page.wait_for_load_state("networkidle")

        resp = httpx.get(f"{e2e_url}/api/presets/", timeout=10)
        presets = resp.json().get("presets", [])
        found = [p for p in presets if p["name"] == preset_name]
        assert len(found) == 1
        assert found[0]["id"] == preset_id

        httpx.delete(f"{e2e_url}/api/presets/{preset_id}")

    def test_create_preset_invalid_run_type_returns_400(self, e2e_url: str):
        resp = httpx.post(
            f"{e2e_url}/api/presets/",
            json={
                "name": "_e2e_invalid_type",
                "run_type": "invalid_type",
                "config": {},
            },
            timeout=10,
        )
        assert resp.status_code == 400

    def test_create_preset_missing_name_returns_400(self, e2e_url: str):
        resp = httpx.post(
            f"{e2e_url}/api/presets/",
            json={"run_type": "stock_scan", "config": {}},
            timeout=10,
        )
        assert resp.status_code == 400
