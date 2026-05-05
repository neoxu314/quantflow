"""E2E tests for watchlist_run preflight validation."""
from __future__ import annotations

import httpx
import pytest

from .conftest import PROJECT_ROOT, SERVER_URL, TEST_WATCHLIST_NAME


@pytest.fixture(autouse=True)
def cleanup_after_test(base_url):
    """Clean up runs and test watchlists."""
    yield
    try:
        resp = httpx.get(f"{base_url}/api/runs/")
        if resp.status_code == 200:
            for run in resp.json().get("runs", []):
                httpx.delete(f"{base_url}/api/runs/{run['id']}")
    except Exception:
        pass
    try:
        httpx.delete(f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml")
    except Exception:
        pass


class TestWatchlistPreflight:

    def test_watchlist_run_with_empty_watchlist_fails(self, base_url: str):
        wl_resp = httpx.put(
            f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={
                "name": TEST_WATCHLIST_NAME,
                "description": "E2E test empty watchlist",
                "items": [],
            },
            timeout=10,
        )
        assert wl_resp.status_code in (200, 201)

        run_resp = httpx.post(
            f"{base_url}/api/runs/",
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

    def test_watchlist_run_with_invalid_strategy_fails(self, base_url: str):
        wl_resp = httpx.put(
            f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
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
            f"{base_url}/api/runs/",
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

    def test_watchlist_run_with_nonexistent_watchlist_fails(self, base_url: str):
        run_resp = httpx.post(
            f"{base_url}/api/runs/",
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

    def test_watchlist_run_preflight_validate_only(self, base_url: str):
        wl_resp = httpx.put(
            f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
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
            f"{base_url}/api/runs/",
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

        runs_resp = httpx.get(f"{base_url}/api/runs/", timeout=10)
        runs = runs_resp.json().get("runs", [])
        wl_runs = [r for r in runs if r.get("run_type") == "watchlist_run"]
        assert len(wl_runs) == 0, "validate_only should not create a run"
