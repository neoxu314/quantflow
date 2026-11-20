"""E2E tests for watchlist_run preflight validation."""
from __future__ import annotations

import httpx

from .conftest import TEST_WATCHLIST_NAME


class TestWatchlistPreflight:

    def test_watchlist_run_with_empty_watchlist_fails(self, e2e_url: str):
        wl_resp = httpx.put(
            f"{e2e_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={
                "name": TEST_WATCHLIST_NAME,
                "description": "E2E test empty watchlist",
                "items": [],
            },
            timeout=10,
        )
        assert wl_resp.status_code in (200, 201)

        run_resp = httpx.post(
            f"{e2e_url}/api/runs/",
            json={
                "run_type": "watchlist_run",
                "watchlist": f"watchlists/{TEST_WATCHLIST_NAME}.yaml",
                "strategies": ["daily_bull_oversold"],
            },
            timeout=10,
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        assert data["ok"] is False, "Preflight should fail for empty watchlist"
        assert "errors" in data
        assert len(data["errors"]) > 0

    def test_watchlist_run_with_invalid_strategy_fails(self, e2e_url: str):
        wl_resp = httpx.put(
            f"{e2e_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={
                "name": TEST_WATCHLIST_NAME,
                "description": "E2E test watchlist",
                "items": [
                    {"code": "NVDA.US", "name": "Nvidia", "tags": []}
                ],
            },
            timeout=10,
        )
        assert wl_resp.status_code in (200, 201)

        run_resp = httpx.post(
            f"{e2e_url}/api/runs/",
            json={
                "run_type": "watchlist_run",
                "watchlist": f"watchlists/{TEST_WATCHLIST_NAME}.yaml",
                "strategies": ["nonexistent_strategy_xyz"],
            },
            timeout=10,
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        assert data["ok"] is False, "Preflight should fail for invalid strategy"
        assert "errors" in data
        assert len(data["errors"]) > 0

    def test_watchlist_run_with_nonexistent_watchlist_fails(self, e2e_url: str):
        run_resp = httpx.post(
            f"{e2e_url}/api/runs/",
            json={
                "run_type": "watchlist_run",
                "watchlist": "watchlists/nonexistent_wl.yaml",
                "strategies": ["daily_bull_oversold"],
            },
            timeout=10,
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        assert data["ok"] is False
        assert "errors" in data
        assert len(data["errors"]) > 0

    def test_watchlist_run_preflight_validate_only(self, e2e_url: str):
        wl_resp = httpx.put(
            f"{e2e_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={
                "name": TEST_WATCHLIST_NAME,
                "description": "E2E test watchlist for preflight",
                "items": [
                    {"code": "NVDA.US", "name": "Nvidia", "tags": []}
                ],
            },
            timeout=10,
        )
        assert wl_resp.status_code in (200, 201)

        run_resp = httpx.post(
            f"{e2e_url}/api/runs/",
            json={
                "run_type": "watchlist_run",
                "watchlist": f"watchlists/{TEST_WATCHLIST_NAME}.yaml",
                "strategies": ["daily_bull_oversold"],
                "validate_only": True,
            },
            timeout=10,
        )
        assert run_resp.status_code == 200
        data = run_resp.json()
        assert data["ok"] is True

        runs_resp = httpx.get(f"{e2e_url}/api/runs/", timeout=10)
        runs = runs_resp.json().get("runs", [])
        wl_runs = [r for r in runs if r.get("run_type") == "watchlist_run"]
        assert len(wl_runs) == 0, "validate_only should not create a run"
