"""Shared fixtures for web module tests."""
import shutil
import pathlib
import pytest


@pytest.fixture(autouse=True)
def isolated_run_state(tmp_path, monkeypatch, request):
    """API tests never launch unmanaged downloads or reconcile the user's DB.

    Worker lifecycle tests drive _execute_run explicitly and join their threads.
    Browser E2E owns its server and has a separate fixture hierarchy.
    """
    if "e2e" in request.node.path.parts:
        yield
        return
    from quantflow.web.engine import run_history, presets
    from quantflow.execution import checkpoint
    from quantflow.web.engine.run_engine import RunEngine
    from unittest.mock import Mock
    run_history._ConnectionManager.reset()
    monkeypatch.setattr(run_history, "DB_PATH", tmp_path / "runs.db")
    monkeypatch.setattr(run_history, "QUANTFLOW_DIR", tmp_path)
    monkeypatch.setattr(presets, "PRESETS_DIR", tmp_path / "presets")
    monkeypatch.setattr(checkpoint, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    monkeypatch.setattr(RunEngine, "start_processing", Mock())
    yield
    run_history._ConnectionManager.reset()


@pytest.fixture
def web_config_yaml_path(tmp_path: pathlib.Path) -> str:
    # Provide a fresh path for tests to write to
    path = tmp_path / "config" / "web.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@pytest.fixture
def config_client(tmp_path, test_project):
    """Give configuration API tests their own writable fixture."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from quantflow.web.api import config as config_module

    config_dir = tmp_path / "config"
    config_dir.mkdir()
    test_config_path = config_dir / "quantflow.yaml"
    shutil.copyfile(test_project / "config" / "quantflow.yaml", test_config_path)

    # Patch module-level constants
    original_config_path = config_module.CONFIG_PATH
    original_project_root = config_module.PROJECT_ROOT
    config_module.CONFIG_PATH = test_config_path
    config_module.PROJECT_ROOT = tmp_path

    app = FastAPI()
    app.include_router(config_module.router)

    client = TestClient(app)
    yield client, test_config_path

    # Restore originals
    config_module.CONFIG_PATH = original_config_path
    config_module.PROJECT_ROOT = original_project_root


@pytest.fixture
def task_client(tmp_path):
    """
    Isolated task API client with a temporary CONFIG_DIR.
    Does NOT modify production task files.
    """
    import yaml
    from quantflow.web.api import tasks as tasks_module
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    original_dir = tasks_module.CONFIG_DIR
    tasks_module.CONFIG_DIR = config_dir

    app = FastAPI()
    app.include_router(tasks_module.router)

    yield TestClient(app), config_dir

    tasks_module.CONFIG_DIR = original_dir


@pytest.fixture
def watchlist_dir(tmp_path):
    """
    Create a temporary watchlists directory and patch the module constant.
    """
    import yaml
    from quantflow.web.api import watchlists as wl_module
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    wl_dir = tmp_path / "watchlists"
    wl_dir.mkdir(parents=True, exist_ok=True)

    original_dir = wl_module.WATCHLISTS_DIR
    wl_module.WATCHLISTS_DIR = wl_dir

    app = FastAPI()
    app.include_router(wl_module.router)

    yield TestClient(app), wl_dir

    wl_module.WATCHLISTS_DIR = original_dir
