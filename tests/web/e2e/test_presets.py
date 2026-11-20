"""E2E tests for Presets CRUD and run-from-preset."""
from __future__ import annotations

import httpx
from playwright.sync_api import Page, expect

from .conftest import SERVER_URL

TEST_STOCK_CODE = "NVDA.US"


class TestPresets:

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

    def test_run_from_updated_preset(self, page, client, e2e_url):
        from .run_helpers import SCAN, open_runs, result, select_run, wait_run

        preset = result(client.post("/api/presets/", json={
            "name": "Replay scan", "run_type": "stock_scan", "config": SCAN,
        }))
        preset_id = preset["preset_id"]
        result(client.put(f"/api/presets/{preset_id}", json={
            "name": "Replay scan", "config": {**SCAN, "code": "MSFT.US"},
        }))
        submitted = result(client.post(f"/api/presets/{preset_id}/run"))
        assert submitted["ok"], submitted
        run_id = submitted["run_id"]
        run = wait_run(client, run_id)
        assert run["config"]["code"] == "MSFT.US"
        assert run["preset_id"] == preset_id
        assert run["signal_count"] == 2
        open_runs(page, e2e_url)
        select_run(page, run_id, "completed")

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
