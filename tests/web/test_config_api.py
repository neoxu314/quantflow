"""Tests for config API."""
import pytest
from pathlib import Path
from unittest.mock import patch


def test_get_strategies_available():
    """Returns strategies from registry."""
    from quantflow.web.api.config import router

    # Check that the /strategies endpoint handler exists
    routes = [r.path for r in router.routes]
    assert "/api/strategies" in routes


def test_get_config_not_found(tmp_path, monkeypatch):
    """Returns error when config file not found."""
    from quantflow.web.api import config as config_module

    fake_path = tmp_path / "config" / "nonexistent.yaml"
    with patch.object(config_module, "CONFIG_PATH", fake_path):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(config_module.router)
        client = TestClient(app)
        resp = client.get("/api/config")

        assert resp.status_code == 200
        assert "error" in resp.json()


def test_create_app():
    """App includes all routes."""
    from quantflow.web.server import create_app

    app = create_app()
    routes = [r.path for r in app.routes]

    assert "/api/config" in routes
    assert "/api/strategies" in routes
    assert "/api/watchlists" in routes
    assert "/api/watchlists/{filename:path}" in routes
    assert "/api/watchlists/search" in routes
    assert "/api/tasks" in routes
    assert "/api/tasks/{task_id}" in routes
