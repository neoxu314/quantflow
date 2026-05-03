"""Tests for config API endpoints - full coverage including PUT/write path."""
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ─── Route registration tests ──────────────────────────────────────────

def test_get_strategies_available():
    """Returns strategies from registry."""
    from quantflow.web.api.config import router

    routes = [r.path for r in router.routes]
    assert "/api/strategies" in routes


def test_config_and_strategies_routes_registered():
    """Config router has GET, PUT, and strategies."""
    from quantflow.web.api.config import router

    routes = {r.path: set() for r in router.routes}
    for route in router.routes:
        routes[route.path].update(route.methods)

    assert "/api/config" in routes
    assert "GET" in routes["/api/config"]
    assert "PUT" in routes["/api/config"]
    assert "/api/strategies" in routes


def test_create_app():
    """App includes all routes."""
    from quantflow.web.server import create_app

    app = create_app()
    route_paths = {r.path for r in app.routes}

    for expected in (
        "/api/config",
        "/api/strategies",
        "/api/watchlists",
        "/api/watchlists/{filename:path}",
        "/api/watchlists/search",
        "/api/tasks",
        "/api/tasks/{task_id}",
        "/api/task-files",
        "/api/task-files/{filename}",
        "/api/library/strategies",
        "/api/library/indicators",
        "/api/library/indicators/params",
    ):
        assert expected in route_paths


# ─── GET /api/config tests ────────────────────────────────────────────

def test_get_config_not_found(tmp_path):
    """Returns error when config file not found."""
    from quantflow.web.api import config as config_module

    fake_path = tmp_path / "config" / "nonexistent.yaml"
    with patch.object(config_module, "CONFIG_PATH", fake_path):
        app = FastAPI()
        app.include_router(config_module.router)
        client = TestClient(app)
        resp = client.get("/api/config")
        assert resp.status_code == 200
        assert "error" in resp.json()


def test_get_config_success(config_client):
    """GET returns full config payload with all sections."""
    client, _ = config_client
    resp = client.get("/api/config")
    assert resp.status_code == 200

    data = resp.json()
    assert "raw" in data
    assert "markets" in data
    assert "defaults" in data
    assert "lookback" in data
    assert "yfinance" in data
    assert "web" in data
    assert "tushare" in data
    assert "logging" in data
    assert "filePath" in data


def test_get_config_values_match_file(config_client):
    """GET returns values that match the actual YAML file."""
    client, config_path = config_client
    with open(config_path, "r", encoding="utf-8") as f:
        file_data = yaml.safe_load(f)

    resp = client.get("/api/config").json()
    assert resp["markets"] == file_data["data"]["markets"]
    assert resp["lookback"] == file_data.get("lookback", {})
    assert resp["web"] == file_data.get("web", {})


# ─── PUT /api/config tests ───────────────────────────────────────────

def test_put_config_updates_file(config_client):
    """PUT writes config to file."""
    client, config_path = config_client

    resp = client.get("/api/config").json()
    current = resp["raw"]
    current["logging"]["level"] = "DEBUG"

    resp = client.put("/api/config", json={"raw": current})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # Verify file content
    with open(config_path, "r", encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    assert saved["logging"]["level"] == "DEBUG"


def test_put_config_roundtrip(config_client):
    """PUT → GET round-trip: written values survive read-write cycle."""
    client, _ = config_client

    # Read current
    orig = client.get("/api/config").json()["raw"]

    # Modify multiple fields
    orig["lookback"]["calendar_multiplier"] = 3
    orig["lookback"]["buffer_days"] = 60
    orig["web"]["port"] = 9090
    orig["web"]["host"] = "0.0.0.0"
    orig["yfinance"]["batch"]["chunk_size"] = 100

    # Write
    put_resp = client.put("/api/config", json={"raw": orig})
    assert put_resp.status_code == 200

    # Read back
    read_resp = client.get("/api/config").json()["raw"]

    assert read_resp["lookback"]["calendar_multiplier"] == 3
    assert read_resp["lookback"]["buffer_days"] == 60
    assert read_resp["web"]["port"] == 9090
    assert read_resp["web"]["host"] == "0.0.0.0"
    assert read_resp["yfinance"]["batch"]["chunk_size"] == 100


def test_put_config_preserves_unmodified_fields(config_client):
    """PUT with subset of raw fields preserves untouched sections."""
    client, config_path = config_client

    # Get original data
    orig = client.get("/api/config").json()["raw"]
    original_markets = orig["data"].get("markets", {})
    original_defaults = orig["data"].get("defaults", {})

    # Only modify logging
    payload = dict(orig)
    payload["logging"] = {"level": "WARNING", "format": "%(levelname)s"}

    client.put("/api/config", json={"raw": payload})

    # Verify markets and defaults still present
    with open(config_path, "r", encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    assert saved["data"]["markets"] == original_markets
    assert saved["data"]["defaults"] == original_defaults


def test_put_config_writing_produces_valid_yaml(config_client):
    """PUT produces YAML that yaml.safe_load can parse without error."""
    client, config_path = config_client

    new_config = {
        "data": {"markets": {"cn": {"primary": "baostock"}}, "defaults": {"adjust": "hfq"}},
        "tushare": {"token": "abc123"},
        "logging": {"level": "INFO", "format": "%(asctime)s"},
        "lookback": {"calendar_multiplier": 2.5, "buffer_days": 45},
        "yfinance": {"batch": {"chunk_size": 100, "sleep_min": 3, "sleep_max": 8}},
        "web": {"port": 3000, "host": "0.0.0.0"},
    }

    resp = client.put("/api/config", json={"raw": new_config})
    assert resp.status_code == 200

    # Re-parse the written file
    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()
    parsed = yaml.safe_load(content)
    assert isinstance(parsed, dict)
    assert parsed["web"]["port"] == 3000


def test_put_config_sort_keys_false(config_client):
    """PUT writes YAML with sort_keys=False to preserve field ordering."""
    client, config_path = config_client

    raw = client.get("/api/config").json()["raw"]
    client.put("/api/config", json={"raw": raw})

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # "data" should appear before "tushare", which should appear before "logging"
    assert content.index("data:") < content.index("tushare:") < content.index("logging:")


def test_put_config_not_found(tmp_path):
    """PUT returns 404 when config file does not exist."""
    from quantflow.web.api import config as config_module

    fake_path = tmp_path / "config" / "nonexistent.yaml"
    with patch.object(config_module, "CONFIG_PATH", fake_path):
        app = FastAPI()
        app.include_router(config_module.router)
        client = TestClient(app)
        resp = client.put("/api/config", json={"raw": {}})
        assert resp.status_code == 404


def test_put_config_empty_payload_defaults(config_client):
    """PUT with empty raw payload writes valid default structure."""
    client, config_path = config_client

    resp = client.put("/api/config", json={"raw": {}})
    assert resp.status_code == 200

    with open(config_path, "r", encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    assert isinstance(saved, dict)
    assert "data" in saved
    assert "logging" in saved
    assert saved["logging"]["level"] == "INFO"
