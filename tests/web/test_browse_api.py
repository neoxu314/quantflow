"""Tests for Browse API endpoints."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

from quantflow.web.api.browse import router, PROJECT_ROOT


class TestBrowseDirListing:
    def test_default_root_listing(self, tmp_path):
        """GET /api/browse/ with no path returns PROJECT_ROOT subdirs."""
        (tmp_path / "dir_a").mkdir()
        (tmp_path / "dir_b").mkdir()
        (tmp_path / "file.txt").touch()

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_path"] == str(tmp_path)
            assert data["directories"] == ["dir_a", "dir_b"]
            assert data["has_parent"] is True
            assert data["name"] == tmp_path.name

    def test_custom_path_listing(self, tmp_path):
        """GET /api/browse/?path=/tmp creates dirs and lists them."""
        target = tmp_path / "custom"
        target.mkdir()
        (target / "sub1").mkdir()
        (target / "sub2").mkdir()

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/", params={"path": str(target)})
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_path"] == str(target)
            assert data["directories"] == ["sub1", "sub2"]

    def test_nonexistent_path_returns_empty_list(self, tmp_path):
        """Non-existent path returns empty directories list, not 404."""
        nonexistent = tmp_path / "does_not_exist"

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/", params={"path": str(nonexistent)})
            assert resp.status_code == 200
            data = resp.json()
            assert data["directories"] == []

    def test_permission_denied_returns_empty_list(self, tmp_path):
        """Returns empty list for unreadable dirs."""
        restricted = tmp_path / "restricted"
        restricted.mkdir()
        (restricted / "secret").mkdir()
        os.chmod(str(restricted), 0o000)

        app = FastAPI()
        app.include_router(router)

        try:
            with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
                client = TestClient(app)
                resp = client.get("/api/browse/", params={"path": str(restricted)})
                assert resp.status_code == 200
                data = resp.json()
                assert data["directories"] == []
        finally:
            os.chmod(str(restricted), 0o755)

    def test_relative_path_under_project_root(self, tmp_path):
        """relative_path is correct for paths under PROJECT_ROOT."""
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/", params={"path": str(nested)})
            assert resp.status_code == 200
            data = resp.json()
            assert data["relative_path"] == "a/b"

    def test_relative_path_outside_project_root(self, tmp_path):
        """relative_path returns full path when outside PROJECT_ROOT."""
        outside = Path("/tmp")

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/", params={"path": str(outside)})
            assert resp.status_code == 200
            data = resp.json()
            assert data["relative_path"] == str(outside)

    def test_parent_path_navigation(self, tmp_path):
        """parent_path and has_parent are correct."""
        child = tmp_path / "child"
        child.mkdir()

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)

            # Root has no parent
            resp = client.get("/api/browse/")
            data = resp.json()
            assert data["has_parent"] is True
            assert data["parent_path"] == str(tmp_path.parent)

            # Child path
            resp = client.get("/api/browse/", params={"path": str(child)})
            data = resp.json()
            assert data["has_parent"] is True
            assert data["parent_path"] == str(tmp_path)

    def test_directory_filters_out_files(self, tmp_path):
        """Only dirs returned, not files."""
        (tmp_path / "adir").mkdir()
        (tmp_path / "bfile.txt").touch()
        (tmp_path / "cfile.py").touch()
        (tmp_path / "bdir").mkdir()

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["directories"] == ["adir", "bdir"]

    def test_sorted_output_case_insensitive(self, tmp_path):
        """Directories are sorted case-insensitively."""
        (tmp_path / "Zebra").mkdir()
        (tmp_path / "alpha").mkdir()
        (tmp_path / "Beta").mkdir()

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["directories"] == ["alpha", "Beta", "Zebra"]

    def test_empty_path_defaults_to_project_root(self, tmp_path):
        """Empty path parameter defaults to PROJECT_ROOT."""
        (tmp_path / "subdir").mkdir()

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/", params={"path": ""})
            assert resp.status_code == 200
            data = resp.json()
            assert data["current_path"] == str(tmp_path)
            assert "subdir" in data["directories"]

    def test_root_name_is_directory_name(self, tmp_path):
        """name field contains the directory name."""
        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.get("/api/browse/")
            assert resp.status_code == 200
            data = resp.json()
            assert data["name"] == tmp_path.name


class TestBrowseMkdir:
    def test_mkdir_basic(self, tmp_path):
        """Creates dir under PROJECT_ROOT."""
        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.post("/api/browse/mkdir", json={"path": "", "name": "newdir"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["path"] == str(tmp_path / "newdir")
            assert (tmp_path / "newdir").is_dir()

    def test_mkdir_with_parent_path(self, tmp_path):
        """Creates dir under specified parent path."""
        parent = tmp_path / "parent"
        parent.mkdir()

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.post("/api/browse/mkdir", json={"path": str(parent), "name": "child"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert (parent / "child").is_dir()

    def test_mkdir_with_parents(self, tmp_path):
        """Creates nested dirs."""
        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.post(
                "/api/browse/mkdir",
                json={"path": "", "name": "a/b/c"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert (tmp_path / "a" / "b" / "c").is_dir()

    def test_mkdir_empty_name_returns_400(self, tmp_path):
        """mkdir with empty name returns 400."""
        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.post("/api/browse/mkdir", json={"path": "", "name": ""})
            assert resp.status_code == 400

            resp = client.post("/api/browse/mkdir", json={"path": "", "name": "   "})
            assert resp.status_code == 400

    def test_mkdir_nonexistent_parent_creates_with_parents(self, tmp_path):
        """mkdir with nonexistent parent creates with parents=True."""
        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.post(
                "/api/browse/mkdir",
                json={"path": str(tmp_path / "missing"), "name": "child"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert (tmp_path / "missing" / "child").is_dir()

    def test_mkdir_existing_dir_succeeds(self, tmp_path):
        """mkdir existing dir succeeds with exist_ok=True."""
        existing = tmp_path / "existing"
        existing.mkdir()

        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.post("/api/browse/mkdir", json={"path": "", "name": "existing"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True

    def test_mkdir_relative_path_in_response(self, tmp_path):
        """mkdir response includes correct relative_path."""
        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.post("/api/browse/mkdir", json={"path": "", "name": "testdir"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["relative_path"] == "testdir"

    def test_mkdir_nested_relative_path(self, tmp_path):
        """mkdir with nested name has correct relative_path."""
        app = FastAPI()
        app.include_router(router)

        with patch("quantflow.web.api.browse.PROJECT_ROOT", tmp_path):
            client = TestClient(app)
            resp = client.post("/api/browse/mkdir", json={"path": "", "name": "a/b"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["relative_path"] == "a/b"
