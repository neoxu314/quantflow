"""Tests for watchlist API endpoints."""
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from quantflow.web.api.watchlists import router, WATCHLISTS_DIR


@pytest.fixture
def app():
    """Create test FastAPI app with watchlist router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(tmp_path, app):
    """Create TestClient with mocked watchlist dir."""
    (tmp_path / "watchlists").mkdir()

    # Mock the WATCHLISTS_DIR
    import quantflow.web.api.watchlists as wl_module
    original = wl_module.WATCHLISTS_DIR
    wl_module.WATCHLISTS_DIR = tmp_path / "watchlists"

    c = TestClient(app)
    yield c

    # Restore original
    wl_module.WATCHLISTS_DIR = original


def test_list_empty_watchlists(client):
    """Returns empty list when no watchlists exist."""
    resp = client.get("/api/watchlists")
    assert resp.status_code == 200
    assert resp.json() == []


def test_save_new_watchlist(client):
    """Can create a new watchlist."""
    resp = client.put("/api/watchlists/test.yaml", json={
        "name": "Test_List",
        "description": "Test watchlist",
        "items": [
            {"code": "002594.SZ", "name": "比亚迪", "tags": ["Personal"]},
        ],
    })
    assert resp.status_code == 201
    assert resp.json()["itemCount"] == 1


def test_get_watchlist(client):
    """Can retrieve a watchlist."""
    # First create one
    client.put("/api/watchlists/fetch_test.yaml", json={
        "name": "Fetch_Test",
        "items": [{"code": "NVDA.US", "name": "Nvidia"}],
    })

    resp = client.get("/api/watchlists/fetch_test.yaml")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Fetch_Test" if isinstance(data, dict) else data
    assert isinstance(data, dict)
    assert data["name"] == "Fetch_Test"
    assert len(data["items"]) == 1


def test_get_nonexistent_watchlist(client):
    """Returns 404 for missing watchlist."""
    resp = client.get("/api/watchlists/nonexistent.yaml")
    assert resp.status_code == 404


def test_delete_watchlist(client):
    """Can delete a watchlist."""
    # Create
    client.put("/api/watchlists/del_test.yaml", json={
        "name": "Delete_Test",
        "items": [],
    })

    # Delete
    resp = client.delete("/api/watchlists/del_test.yaml")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify gone
    resp = client.get("/api/watchlists/del_test.yaml")
    assert resp.status_code == 404


def test_search_stock_found(client, tmp_path):
    """Search finds stock in watchlists."""
    # Create watchlist with known stock
    wpath = tmp_path / "watchlists"
    wpath.mkdir(exist_ok=True)
    (wpath / "test.yaml").write_text(
        yaml.dump({
            "name": "Test",
            "items": [{"code": "NVDA.US", "name": "Nvidia"}],
        }),
        encoding="utf-8",
    )

    resp = client.post("/api/watchlists/search", json={"code": "NVDA.US"})
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    assert "test.yaml" in resp.json()["inLists"]


def test_search_stock_not_found(client):
    """Search returns found=False for unknown stock."""
    resp = client.post("/api/watchlists/search", json={"code": "FAKE.XX"})
    assert resp.status_code == 200
    assert resp.json()["found"] is False
    assert resp.json()["inLists"] == []


def test_search_fuzzy_match(client, tmp_path):
    """Fuzzy search finds partial matches with watchlist field."""
    wpath = tmp_path / "watchlists"
    wpath.mkdir(exist_ok=True)
    (wpath / "fuzzy.yaml").write_text(
        yaml.dump({
            "name": "Fuzzy_Test",
            "items": [
                {"code": "NVDA.US", "name": "Nvidia"},
                {"code": "TSLA.US", "name": "Tesla"},
            ],
        }),
        encoding="utf-8",
    )

    resp = client.post("/api/watchlists/search", json={"code": "NV"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert isinstance(data["fuzzyMatches"], list)
    match = next((m for m in data["fuzzyMatches"] if m["code"] == "NVDA.US"), None)
    assert match is not None
    assert match["watchlist"] == "fuzzy.yaml"


def test_path_traversal_blocked(client):
    """Blocks path traversal attempts."""
    # Encoded path to bypass Starlette URL normalization
    resp = client.put("/api/watchlists/%2E%2E/%2E%2E/etc/passwd.yaml", json={
        "name": "hack",
        "items": [],
    })
    assert resp.status_code == 400
