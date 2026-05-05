"""pytest configuration for web E2E tests.

Provides:
1. Browser launch configuration (Chrome for Testing)
2. Production config protection via backup/restore mechanism
3. Test data cleanup (watchlists, task files)
4. SAFETY: Prevents tests from writing to production paths

All E2E tests use backup strategy to protect production YAML files:
- config/quantflow.yaml → quantflow.yaml.bak
- config/indicators.yaml → indicators.yaml.bak
- ALL watchlists/*.yaml → backed up individually
- ALL config/tasks*.yaml → backed up individually
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

def _load_web_port():
    try:
        from quantflow.web.config import WebConfig
        return WebConfig.load().port
    except Exception:
        return 8080

WEB_PORT = _load_web_port()
SERVER_URL = f"http://127.0.0.1:{WEB_PORT}"

# Test data names (use _test_ prefix to distinguish from production)
TEST_WATCHLIST_NAME = "_test_e2e_wl"
TEST_TASK_FILE = "tasks_e2e_test.yaml"

# Backup file paths
CFG_BACKUP = PROJECT_ROOT / "config" / "quantflow.yaml.bak"
INDICATORS_BACKUP = PROJECT_ROOT / "config" / "indicators.yaml.bak"
WATCHLISTS_BACKUP_DIR = PROJECT_ROOT / "watchlists" / ".bak"
TASKS_BACKUP_DIR = PROJECT_ROOT / "config" / ".tasks_bak"


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
    Protect ALL production config and data files via backup/restore.
    
    CRITICAL SAFETY: This fixture runs before/after EVERY E2E test:
    - Before: Backup ALL production files (quantflow.yaml, indicators.yaml, 
              ALL watchlists/*.yaml, ALL config/tasks*.yaml)
    - After: Restore ALL backups, delete test data files
    
    This ensures E2E tests NEVER modify production data.
    
    Protected files:
    - config/quantflow.yaml
    - config/indicators.yaml
    - watchlists/*.yaml (ALL watchlists, not just test ones)
    - config/tasks*.yaml (ALL task configs)
    """
    _backup_all_production_files()
    yield
    _restore_all_production_files()
    _cleanup_test_data_via_api(base_url)


def _backup_all_production_files():
    """Backup ALL production files before test (CRITICAL SAFETY)."""
    # Backup quantflow.yaml
    cfg = PROJECT_ROOT / "config" / "quantflow.yaml"
    if cfg.exists():
        shutil.copy2(cfg, CFG_BACKUP)
    
    # Backup indicators.yaml
    indicators = PROJECT_ROOT / "config" / "indicators.yaml"
    if indicators.exists():
        shutil.copy2(indicators, INDICATORS_BACKUP)
    
    # Backup ALL watchlists (not just test ones!)
    watchlists_dir = PROJECT_ROOT / "watchlists"
    if watchlists_dir.exists():
        WATCHLISTS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for wl_file in watchlists_dir.glob("*.yaml"):
            # Skip test watchlists (they will be deleted anyway)
            if not wl_file.name.startswith("_test_"):
                shutil.copy2(wl_file, WATCHLISTS_BACKUP_DIR / wl_file.name)
    
    # Backup ALL task configs (not just test ones!)
    config_dir = PROJECT_ROOT / "config"
    if config_dir.exists():
        TASKS_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        for task_file in config_dir.glob("tasks*.yaml"):
            # Skip test task files
            if not task_file.name.startswith("tasks_e2e_"):
                shutil.copy2(task_file, TASKS_BACKUP_DIR / task_file.name)


def _restore_all_production_files():
    """Restore ALL production files after test (CRITICAL SAFETY)."""
    # Restore quantflow.yaml
    cfg = PROJECT_ROOT / "config" / "quantflow.yaml"
    if CFG_BACKUP.exists():
        shutil.move(str(CFG_BACKUP), str(cfg))
    elif cfg.exists():
        cfg.unlink()
    
    # Restore indicators.yaml
    indicators = PROJECT_ROOT / "config" / "indicators.yaml"
    if INDICATORS_BACKUP.exists():
        shutil.move(str(INDICATORS_BACKUP), str(indicators))
    elif indicators.exists():
        indicators.unlink()
    
    # Restore ALL watchlists
    watchlists_dir = PROJECT_ROOT / "watchlists"
    if WATCHLISTS_BACKUP_DIR.exists():
        for backup_file in WATCHLISTS_BACKUP_DIR.glob("*.yaml"):
            original = watchlists_dir / backup_file.name
            shutil.move(str(backup_file), str(original))
        # Clean up backup dir
        shutil.rmtree(WATCHLISTS_BACKUP_DIR, ignore_errors=True)
    
    # Restore ALL task configs
    config_dir = PROJECT_ROOT / "config"
    if TASKS_BACKUP_DIR.exists():
        for backup_file in TASKS_BACKUP_DIR.glob("*.yaml"):
            original = config_dir / backup_file.name
            shutil.move(str(backup_file), str(original))
        # Clean up backup dir
        shutil.rmtree(TASKS_BACKUP_DIR, ignore_errors=True)


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
    "WATCHLISTS_BACKUP_DIR",
    "TASKS_BACKUP_DIR",
]
