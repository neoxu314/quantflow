"""E2E tests for Browse API (directory picker)."""
from __future__ import annotations

import shutil
import tempfile

import httpx
import pytest

from .conftest import PROJECT_ROOT, SERVER_URL

TEST_TMP_DIR = PROJECT_ROOT / ".quantflow" / "e2e_browse_test"


@pytest.fixture(autouse=True)
def cleanup_browse_test():
    yield
    if TEST_TMP_DIR.exists():
        shutil.rmtree(TEST_TMP_DIR, ignore_errors=True)


class TestBrowseApi:

    def test_browse_root_returns_dirs(self, base_url: str):
        resp = httpx.get(f"{base_url}/api/browse/", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert "directories" in data
        assert isinstance(data["directories"], list)
        assert "current_path" in data
        assert data["current_path"] == str(PROJECT_ROOT)

    def test_browse_custom_path(self, base_url: str):
        resp = httpx.get(f"{base_url}/api/browse/?path=/tmp", timeout=10)
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_path"] == "/tmp"
        assert "directories" in data
        assert isinstance(data["directories"], list)

    def test_browse_nonexistent_path(self, base_url: str):
        resp = httpx.get(
            f"{base_url}/api/browse/?path=/nonexistent_path_xyz",
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["directories"] == []
        assert "current_path" in data

    def test_browse_mkdir_and_list(self, base_url: str):
        TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)

        resp = httpx.post(
            f"{base_url}/api/browse/mkdir",
            json={"path": str(TEST_TMP_DIR), "name": "test_dir_a"},
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "test_dir_a" in data["path"]

        resp = httpx.get(
            f"{base_url}/api/browse/?path={TEST_TMP_DIR}",
            timeout=10,
        )
        assert resp.status_code == 200
        dirs = resp.json()["directories"]
        assert "test_dir_a" in dirs

    def test_browse_mkdir_empty_name_fails(self, base_url: str):
        resp = httpx.post(
            f"{base_url}/api/browse/mkdir",
            json={"path": str(TEST_TMP_DIR), "name": ""},
            timeout=10,
        )
        assert resp.status_code == 400

        resp = httpx.post(
            f"{base_url}/api/browse/mkdir",
            json={"path": str(TEST_TMP_DIR), "name": "   "},
            timeout=10,
        )
        assert resp.status_code == 400

    def test_browse_nested_mkdir(self, base_url: str):
        TEST_TMP_DIR.mkdir(parents=True, exist_ok=True)
        nested = TEST_TMP_DIR / "parent" / "child" / "grandchild"

        resp = httpx.post(
            f"{base_url}/api/browse/mkdir",
            json={
                "path": str(TEST_TMP_DIR),
                "name": "parent/child/grandchild",
            },
            timeout=10,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert nested.exists()

        resp = httpx.get(
            f"{base_url}/api/browse/?path={TEST_TMP_DIR}/parent/child",
            timeout=10,
        )
        assert resp.status_code == 200
        dirs = resp.json()["directories"]
        assert "grandchild" in dirs

    def test_browse_parent_path(self, base_url: str):
        resp = httpx.get(
            f"{base_url}/api/browse/?path={PROJECT_ROOT}/src",
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_parent"] is True
        assert data["parent_path"] != ""

    def test_browse_root_has_no_parent(self, base_url: str):
        resp = httpx.get(
            f"{base_url}/api/browse/?path=/",
            timeout=10,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_parent"] is False
