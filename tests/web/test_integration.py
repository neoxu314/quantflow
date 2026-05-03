"""Round-trip integration tests: API → filesystem → API verification."""
import yaml
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ─── Watchlist round-trip tests ────────────────────────────────────────

def test_watchlist_create_then_file_exists(watchlist_dir):
    """PUT watchlist creates file on disk."""
    client, wl_dir = watchlist_dir

    resp = client.put("/api/watchlists/roundtrip.yaml", json={
        "name": "Roundtrip_Test",
        "description": "Integration validation",
        "items": [
            {"code": "NVDA.US", "name": "Nvidia", "tags": ["test"]},
            {"code": "600519.SH", "name": "贵州茅台", "tags": ["cn"]},
        ],
    })
    assert resp.status_code == 201

    saved_path = wl_dir / "roundtrip.yaml"
    assert saved_path.exists()

    with open(saved_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["name"] == "Roundtrip_Test"
    assert len(data["items"]) == 2
    assert data["items"][1]["name"] == "贵州茅台"


def test_watchlist_read_back_matches_api(watchlist_dir):
    """API GET returns data consistent with disk file."""
    client, wl_dir = watchlist_dir

    # Write via API
    client.put("/api/watchlists/readback.yaml", json={
        "name": "Readback_Test",
        "items": [{"code": "TSLA.US", "name": "Tesla", "tags": []}],
    })

    # Read disk directly
    saved = yaml.safe_load((wl_dir / "readback.yaml").read_text())

    # Read via API
    api_resp = client.get("/api/watchlists/readback.yaml").json()
    assert api_resp["name"] == saved["name"]
    assert len(api_resp["items"]) == len(saved["items"])
    assert api_resp["items"][0]["code"] == saved["items"][0]["code"]


def test_watchlist_delete_then_file_gone(watchlist_dir):
    """DELETE watchlist removes file from disk."""
    client, wl_dir = watchlist_dir

    client.put("/api/watchlists/gone.yaml", json={
        "name": "Gone",
        "items": [],
    })
    assert (wl_dir / "gone.yaml").exists()

    resp = client.delete("/api/watchlists/gone.yaml")
    assert resp.status_code == 200
    assert not (wl_dir / "gone.yaml").exists()


def test_watchlist_edit_persists_to_disk(watchlist_dir):
    """Re-PUT updates existing file, preserves structure."""
    client, wl_dir = watchlist_dir

    # Create initial
    client.put("/api/watchlists/edit.yaml", json={
        "name": "Editable",
        "items": [{"code": "AAPL.US", "name": "Apple"}],
    })

    # Overwrite
    client.put("/api/watchlists/edit.yaml", json={
        "name": "Editable_Updated",
        "items": [
            {"code": "AAPL.US", "name": "Apple"},
            {"code": "GOOG.US", "name": "Google"},
        ],
    })

    saved = yaml.safe_load((wl_dir / "edit.yaml").read_text())
    assert saved["name"] == "Editable_Updated"
    assert len(saved["items"]) == 2


# ─── Task round-trip tests ─────────────────────────────────────────────

def test_task_create_then_file_on_disk(task_client):
    """POST task creates entry in task file on disk."""
    client, config_dir = task_client
    task_file = config_dir / "tasks_rt.yaml"

    resp = client.post("/api/task-files", json={"filename": "tasks_rt.yaml"})
    assert resp.status_code == 201

    assert task_file.exists()
    data = yaml.safe_load(task_file.read_text())
    assert data == {"tasks": []}


def test_task_add_then_file_updated(task_client):
    """POST task updates YAML file, readable via disk."""
    client, config_dir = task_client

    # Create empty task file
    client.post("/api/task-files", json={"filename": "tasks_rt2.yaml"})
    task_file = config_dir / "tasks_rt2.yaml"

    # Add task
    resp = client.post("/api/tasks", json={
        "name": "rt_task",
        "watchlist": "watchlists/test.yaml",
        "strategies": ["daily_bull_oversold"],
        "output": "./output/rt",
    }, params={"filename": "tasks_rt2.yaml"})
    assert resp.status_code == 201

    disk_data = yaml.safe_load(task_file.read_text())
    assert len(disk_data["tasks"]) == 1
    assert disk_data["tasks"][0]["name"] == "rt_task"
    assert disk_data["tasks"][0]["strategies"] == ["daily_bull_oversold"]


def test_task_update_then_disk_matches(task_client):
    """PUT task updates file, disk matches API response."""
    client, config_dir = task_client
    task_file = config_dir / "tasks_update.yaml"

    client.post("/api/task-files", json={"filename": "tasks_update.yaml"})
    client.post("/api/tasks", json={
        "name": "upd_task",
        "watchlist": "watchlists/orig.yaml",
        "strategies": ["kdj_golden_cross"],
        "output": "./output/orig",
    }, params={"filename": "tasks_update.yaml"})

    # Update
    resp = client.put("/api/tasks/tasks_update.yaml:upd_task", json={
        "name": "upd_task",
        "watchlist": "watchlists/new.yaml",
        "strategies": ["daily_bull_oversold", "kdj_golden_cross"],
        "output": "./output/new",
    })
    assert resp.status_code == 200

    disk_data = yaml.safe_load(task_file.read_text())
    assert disk_data["tasks"][0]["watchlist"] == "watchlists/new.yaml"
    assert len(disk_data["tasks"][0]["strategies"]) == 2


def test_task_delete_then_removed_from_disk(task_client):
    """DELETE task removes entry from YAML file."""
    client, config_dir = task_client
    task_file = config_dir / "tasks_del.yaml"

    client.post("/api/task-files", json={"filename": "tasks_del.yaml"})
    client.post("/api/tasks", json={
        "name": "del_task",
        "watchlist": "watchlists/x.yaml",
        "strategies": [],
    }, params={"filename": "tasks_del.yaml"})

    disk_before = yaml.safe_load(task_file.read_text())
    assert len(disk_before["tasks"]) == 1

    client.delete("/api/tasks/tasks_del.yaml:del_task")

    disk_after = yaml.safe_load(task_file.read_text())
    assert len(disk_after["tasks"]) == 0


def test_task_file_list_api_matches_disk(task_client):
    """GET /task-files returns info matching actual disk files."""
    client, config_dir = task_client

    # Create two task files
    client.post("/api/task-files", json={"filename": "tasks_a.yaml"})
    client.post("/api/task-files", json={"filename": "tasks_b.yaml"})

    # Add a task to one
    client.post("/api/tasks", json={
        "name": "task_in_b",
        "watchlist": "watchlists/x.yaml",
        "strategies": [],
    }, params={"filename": "tasks_b.yaml"})

    resp = client.get("/api/task-files").json()
    names = {f["filename"] for f in resp}
    assert "tasks_a.yaml" in names
    assert "tasks_b.yaml" in names

    b_info = next(f for f in resp if f["filename"] == "tasks_b.yaml")
    assert b_info["taskCount"] == 1


def test_task_file_delete_then_gone_from_disk(task_client):
    """DELETE task file removes it from disk."""
    client, config_dir = task_client

    resp = client.post("/api/task-files", json={"filename": "tasks_vanish.yaml"})
    assert resp.status_code == 201
    assert (config_dir / "tasks_vanish.yaml").exists()

    resp = client.delete("/api/task-files/tasks_vanish.yaml")
    assert resp.status_code == 200
    assert not (config_dir / "tasks_vanish.yaml").exists()


def test_task_file_create_invalid_name_blocked(task_client):
    """Rejects invalid task file names."""
    client, _ = task_client

    # Path traversal
    resp = client.post("/api/task-files", json={"filename": "../../../../etc/passwd"})
    assert resp.status_code == 400

    # Duplicate
    client.post("/api/task-files", json={"filename": "tasks_dup.yaml"})
    resp = client.post("/api/task-files", json={"filename": "tasks_dup.yaml"})
    assert resp.status_code == 409


def test_task_file_create_without_extension(task_client):
    """Auto-appends .yaml if missing."""
    client, config_dir = task_client

    resp = client.post("/api/task-files", json={"filename": "tasks_noext"})
    assert resp.status_code == 201
    assert (config_dir / "tasks_noext.yaml").exists()
