"""A browser test server owns only its temporary project and run history."""

import shutil
import sqlite3

import httpx

from .conftest import TestServer


def test_servers_have_distinct_run_history_and_lifecycles(web_server, tmp_path):
    db = web_server.home / ".quantflow" / "runs.db"
    assert db.is_file()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO run_history (id, name, run_type, config, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("owned", "Owned run", "stock_scan", "{}", "running", "2026-11-20T00:00:00Z"),
        )

    second_root = tmp_path / "second"
    second_root.mkdir()
    shutil.copytree(web_server.root / "src", second_root / "src")
    shutil.copytree(web_server.root / "config", second_root / "config")
    second = TestServer(second_root)
    try:
        second.start()
        assert second.url != web_server.url
        assert httpx.get(f"{second.url}/api/runs/", timeout=3).json()["runs"] == []
        second.restart()
        assert httpx.get(f"{second.url}/api/runs/", timeout=3).json()["runs"] == []
    finally:
        second.stop()

    first_run = httpx.get(f"{web_server.url}/api/runs/owned", timeout=3).json()["run"]
    assert first_run["status"] == "running"
