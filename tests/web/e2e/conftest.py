"""pytest configuration for web E2E tests.

Provides:
1. Browser launch configuration (Chrome for Testing)
2. Production config protection via backup/restore mechanism
3. Test data cleanup (watchlists, task files)

All E2E tests use backup strategy to protect production YAML files:
- config/quantflow.yaml → quantflow.yaml.bak
- config/indicators.yaml → indicators.yaml.bak
"""
import os
import shutil
import subprocess
import time
import socket
import pytest
from pathlib import Path

# ─── Constants ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WEB_PORT = 8080
SERVER_URL = f"http://127.0.0.1:{WEB_PORT}"

# Test data names
TEST_WATCHLIST_NAME = "_test_e2e_wl"
TEST_TASK_FILE = "tasks_e2e_test.yaml"

# Backup file paths
CFG_BACKUP = PROJECT_ROOT / "config" / "quantflow.yaml.bak"
INDICATORS_BACKUP = PROJECT_ROOT / "config" / "indicators.yaml.bak"


# ─── Browser Configuration ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Use the installed Chrome for Testing browser."""
    return {"headless": True, "channel": "chrome"}


# ─── Web Server Fixture ─────────────────────────────────────────────────────

def _wait_for_server(host, port, timeout=30):
    """Wait for server to be ready on given port."""
    for _ in range(timeout * 2):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            if s.connect_ex((host, port)) == 0:
                s.close()
                return True
            s.close()
        except OSError:
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def web_server():
    """Start QuantFlow web server for E2E tests."""
    env = os.environ.copy()
    proc = subprocess.Popen(
        ["python3", "-m", "quantflow.cli", "web"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if not _wait_for_server("127.0.0.1", WEB_PORT):
        proc.kill()
        raise RuntimeError(f"Web server did not start on port {WEB_PORT}")

    yield proc

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="session")
def base_url(web_server):
    """Return base URL for the running web server."""
    return SERVER_URL


# ─── Production Config Protection ───────────────────────────────────────────

@pytest.fixture(autouse=True)
def protect_production_configs(base_url):
    """
    Protect production config files via backup/restore.
    
    This fixture runs before/after every E2E test:
    - Before: Backup quantflow.yaml and indicators.yaml
    - After: Restore backups, delete test watchlists/task files
    
    This ensures E2E tests can safely modify config files without
    affecting production data.
    """
    _backup_all_configs()
    yield
    _restore_all_configs()
    _cleanup_test_data_via_api(base_url)


def _backup_all_configs():
    """Backup all production config files before test."""
    cfg = PROJECT_ROOT / "config" / "quantflow.yaml"
    if cfg.exists():
        shutil.copy2(cfg, CFG_BACKUP)
    
    indicators = PROJECT_ROOT / "config" / "indicators.yaml"
    if indicators.exists():
        shutil.copy2(indicators, INDICATORS_BACKUP)


def _restore_all_configs():
    """Restore all production config files after test."""
    cfg = PROJECT_ROOT / "config" / "quantflow.yaml"
    if CFG_BACKUP.exists():
        shutil.move(str(CFG_BACKUP), str(cfg))
    elif cfg.exists():
        cfg.unlink()
    
    indicators = PROJECT_ROOT / "config" / "indicators.yaml"
    if INDICATORS_BACKUP.exists():
        shutil.move(str(INDICATORS_BACKUP), str(indicators))
    elif indicators.exists():
        indicators.unlink()


def _cleanup_test_data_via_api(base_url):
    """Delete test watchlists and task files via API."""
    import httpx
    
    for endpoint in [
        f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
        f"{base_url}/api/task-files/{TEST_TASK_FILE}",
    ]:
        try:
            httpx.delete(endpoint)
        except Exception:
            pass


# ─── Test Constants Export ──────────────────────────────────────────────────

# Export for use in test files
__all__ = [
    "PROJECT_ROOT",
    "WEB_PORT", 
    "SERVER_URL",
    "TEST_WATCHLIST_NAME",
    "TEST_TASK_FILE",
    "CFG_BACKUP",
    "INDICATORS_BACKUP",
]
