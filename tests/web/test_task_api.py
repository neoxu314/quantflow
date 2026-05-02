"""Tests for task API endpoints."""
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from quantflow.web.api.tasks import router, CONFIG_DIR


@pytest.fixture
def app():
    """Create test FastAPI app with task router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def app_with_config(tmp_path, app):
    """Create app with mocked config dir populated with test task files."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "tasks_test.yaml").write_text(
        yaml.dump({
            "tasks": [
                {
                    "name": "test_task_1",
                    "watchlist": "watchlists/personal_focus_us.yaml",
                    "strategies": ["daily_bull_oversold"],
                    "output": "./output/test1",
                }
            ]
        }),
        encoding="utf-8",
    )

    import quantflow.web.api.tasks as task_module
    original = task_module.CONFIG_DIR
    task_module.CONFIG_DIR = tmp_path / "config"

    c = TestClient(app)
    yield c

    task_module.CONFIG_DIR = original


def test_list_all_tasks(app_with_config):
    """Lists tasks from all task config files."""
    resp = app_with_config.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_list_empty_tasks(app_with_config, tmp_path):
    """Returns empty list when no tasks exist."""
    test_file = tmp_path / "config" / "tasks_test.yaml"
    if test_file.exists():
        test_file.unlink()

    resp = app_with_config.get("/api/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_task(app_with_config):
    """Adds a new task to config file."""
    resp = app_with_config.post("/api/tasks", json={
        "name": "new_task",
        "watchlist": "watchlists/test.yaml",
        "strategies": ["kdj_golden_cross"],
        "output": "./output/new",
    }, params={"filename": "tasks_test.yaml"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "new_task"

    resp = app_with_config.get("/api/tasks")
    names = [t["name"] for t in resp.json()]
    assert "new_task" in names


def test_add_duplicate_task(app_with_config):
    """Rejects duplicate task names in same file."""
    resp = app_with_config.post("/api/tasks", json={
        "name": "test_task_1",
        "watchlist": "watchlists/test.yaml",
        "strategies": [],
    }, params={"filename": "tasks_test.yaml"})

    assert resp.status_code == 409


def test_update_task(app_with_config):
    """Updates existing task."""
    task_id = "tasks_test.yaml:test_task_1"
    resp = app_with_config.put(f"/api/tasks/{task_id}", json={
        "name": "test_task_1",
        "watchlist": "watchlists/updated.yaml",
        "strategies": ["daily_bull_oversold", "kdj_golden_cross"],
        "output": "./output/updated",
    })

    assert resp.status_code == 200
    assert resp.json()["updated"] is True


def test_update_nonexistent_task(app_with_config):
    """Returns 404 for missing task."""
    resp = app_with_config.put("/api/tasks/tasks_test.yaml:nonexistent", json={
        "name": "nonexistent",
        "watchlist": "watchlists/x.yaml",
        "strategies": [],
    })
    assert resp.status_code == 404


def test_delete_task(app_with_config):
    """Deletes a task from config file."""
    app_with_config.post("/api/tasks", json={
        "name": "to_delete",
        "watchlist": "watchlists/x.yaml",
        "strategies": [],
    }, params={"filename": "tasks_test.yaml"})

    resp = app_with_config.delete("/api/tasks/tasks_test.yaml:to_delete")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    resp = app_with_config.get("/api/tasks")
    names = [t["name"] for t in resp.json()]
    assert "to_delete" not in names


def test_path_traversal_blocked(app_with_config):
    """Blocks path traversal in task operations."""
    resp = app_with_config.post("/api/tasks", json={
        "name": "hack",
        "watchlist": "x",
    }, params={"filename": "../../etc/passwd.yaml"})
    assert resp.status_code == 400


def test_delete_invalid_task_id(app_with_config):
    """Rejects invalid task ID format."""
    resp = app_with_config.delete("/api/tasks/invalid_id_without_colon")
    assert resp.status_code == 400


def test_delete_non_tasks_file(app_with_config):
    """Rejects deleting from non-task config files."""
    resp = app_with_config.delete("/api/tasks/quantflow.yaml:test")
    assert resp.status_code == 400
