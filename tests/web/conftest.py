"""Shared fixtures for web module tests."""
import shutil
import pathlib
import pytest


@pytest.fixture
def web_config_yaml_path(tmp_path: pathlib.Path) -> str:
    # Provide a fresh path for tests to write to
    path = tmp_path / "config" / "web.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@pytest.fixture
def config_client(tmp_path):
    """
    Isolated config API client with a temporary CONFIG_PATH.

    Creates a valid quantflow.yaml in tmp_path, patches the module's
    CONFIG_PATH and PROJECT_ROOT, and yields a TestClient. On teardown,
    the temporary files are cleaned up — production config is never touched.
    """
    import yaml
    from quantflow.web.api import config as config_module
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Create a fresh config dir + valid quantflow.yaml copy
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    project_root = pathlib.Path(__file__).resolve().parents[2]
    real_config = project_root / "config" / "quantflow.yaml"

    if real_config.exists():
        shutil.copy2(real_config, config_dir / "quantflow.yaml")
    else:
        # Minimal valid config for tests
        (config_dir / "quantflow.yaml").write_text(
            yaml.dump({
                "data": {"markets": {}, "defaults": {"adjust": "qfq"}},
                "logging": {"console_level": "INFO", "file_enabled": True, "file_level": "DEBUG"},
                "lookback": {"calendar_multiplier": 2, "buffer_days": 30},
                "yfinance": {"batch": {"chunk_size": 50}},
                "web": {"port": 8080, "host": "127.0.0.1"},
            }, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )

    test_config_path = config_dir / "quantflow.yaml"

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
