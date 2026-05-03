"""End-to-end Playwright tests for QuantFlow Web UI.

Requires: pip install pytest-playwright
Usage: playwright install chromium && pytest tests/web/e2e/test_web_ui.py -v
"""
import os
import subprocess
import time
import socket
import pytest
from pathlib import Path

from playwright.sync_api import Page

TEST_WATCHLIST_NAME = "_test_e2e_wl"
TEST_TASK_FILE = "tasks_e2e_test.yaml"
WEB_PORT = 8080

PROJECT_ROOT = Path(__file__).parents[3]
SERVER_URL = f"http://127.0.0.1:{WEB_PORT}"


def _wait_for_server(host, port, timeout=30):
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
    return SERVER_URL


@pytest.fixture(autouse=True)
def cleanup_test_data(base_url):
    yield
    _remove_test_watchlist(base_url)
    _remove_test_task_file(base_url)


def _remove_test_watchlist(base_url):
    import httpx
    try:
        httpx.delete(f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml")
    except Exception:
        pass


def _remove_test_task_file(base_url):
    import httpx
    try:
        resp = httpx.delete(f"{base_url}/api/task-files/{TEST_TASK_FILE}")
        if resp.status_code == 404:
            path = PROJECT_ROOT / "config" / TEST_TASK_FILE
            if path.exists():
                path.unlink()
    except Exception:
        pass


def test_watchlist_page_loads(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    assert page.title() == "QuantFlow Web"
    page.get_by_role("button", name="Watchlists").wait_for(state="visible")
    page.get_by_role("button", name="Tasks").wait_for(state="visible")
    page.get_by_role("button", name="Settings").wait_for(state="visible")
    page.locator("#watchlist-list").wait_for(state="visible")
    page.locator("#search-input").wait_for(state="visible")


def test_watchlist_select_shows_table(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    djia = page.locator("#watchlist-list").get_by_text("DJIA")
    djia.click()
    page.wait_for_function("document.querySelector('#stock-table') !== null")
    page.wait_for_selector("#stock-table", timeout=5000)
    header = page.locator("#watchlist-title")
    header.wait_for(state="visible", timeout=5000)
    assert "DJIA" in header.text_content()


def test_search_stock(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    search_box = page.get_by_role("textbox", name="Enter stock code")
    search_box.fill("AAPL")
    search_box.press("Enter")
    status = page.locator("#search-status")
    status.wait_for(state="visible", timeout=5000)
    text = status.text_content().lower()
    assert "found" in text


def test_new_watchlist(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")

    def handle_dialog(dialog):
        dialog.accept(TEST_WATCHLIST_NAME)

    page.once("dialog", handle_dialog)
    page.get_by_role("button", name="+ New").click()
    page.get_by_role("button", name=TEST_WATCHLIST_NAME).wait_for(
        state="visible", timeout=5000
    )


def test_delete_watchlist_via_api(page: Page, base_url):
    import httpx
    httpx.put(
        f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
        json={"name": TEST_WATCHLIST_NAME, "items": []},
    )
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name=TEST_WATCHLIST_NAME).wait_for(
        state="visible", timeout=5000
    )
    delete_resp = httpx.delete(
        f"{base_url}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml"
    )
    assert delete_resp.status_code == 200
    page.reload()
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name=TEST_WATCHLIST_NAME).wait_for(
        state="hidden", timeout=5000
    )


def test_tasks_page_loads(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Tasks").click()
    page.get_by_role("heading", name="Task Files", level=3).wait_for(
        state="visible"
    )
    page.wait_for_selector("#task-file-list", timeout=5000)
    assert page.locator("#task-file-list button").count() >= 1


def test_select_task_file_shows_tasks_table(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Tasks").click()
    first_tf = page.locator("#task-file-list button").first
    first_tf.click()
    page.wait_for_selector("#task-table", timeout=5000)


def test_new_task_file_creation(page: Page, base_url):
    import httpx
    httpx.post(
        f"{base_url}/api/task-files",
        json={"filename": TEST_TASK_FILE},
    )
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Tasks").click()
    page.get_by_text(TEST_TASK_FILE).wait_for(state="visible", timeout=5000)


def test_settings_page_loads_all_sections(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Settings").click()
    page.wait_for_selector("#settings-form", timeout=5000)
    for section in ("Data Sources", "Lookback Period", "YFinance Batch",
                    "Web Server", "Tushare Token", "Logging Level"):
        page.get_by_text(section).wait_for(state="visible")


def test_settings_values_populated(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Settings").click()
    cn_primary = page.locator("#cfg-cn-primary")
    cn_primary.wait_for(state="visible", timeout=5000)
    assert cn_primary.input_value() in ("baostock", "tushare")
    port_field = page.locator("#cfg-web-port")
    port_field.wait_for(state="visible", timeout=5000)
    assert port_field.input_value() == "8080"


def test_tab_navigation_roundtrip(page: Page, base_url):
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Tasks").click()
    page.wait_for_selector("#task-file-list", timeout=5000)
    page.get_by_role("button", name="Settings").click()
    page.wait_for_selector("#settings-form", timeout=5000)
    page.get_by_role("button", name="Watchlists").click()
    page.wait_for_selector("#watchlist-list", timeout=5000)


def test_settings_modify_and_save(page: Page, base_url):
    """Modify a config setting via UI, save, and verify the file is updated."""
    import httpx, yaml

    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Settings").click()
    page.wait_for_selector("#settings-form", timeout=5000)

    logging_select = page.locator("#cfg-log-level")
    original = logging_select.input_value()

    logging_select.select_option(label="WARNING")

    page.locator("#btn-save-settings").click()
    page.wait_for_timeout(2000)

    verify = httpx.get(f"{base_url}/api/config").json()
    assert verify["logging"]["level"] == "WARNING"

    cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    assert saved["logging"]["level"] == "WARNING"

    logging_select.select_option(label=original)
    page.locator("#btn-save-settings").click()
    page.wait_for_timeout(1000)


def test_settings_survive_server_restart(page: Page, base_url):
    """Modify a config, restart server, and confirm changes persist."""
    import httpx, yaml, subprocess, time, socket, os

    cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        original = yaml.safe_load(f)
    orig_buffer = original.get("lookback", {}).get("buffer_days", 30)
    new_buffer = 99

    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Settings").click()
    page.wait_for_selector("#settings-form", timeout=5000)

    buffer_field = page.locator("#cfg-lookback-buffer")
    buffer_field.fill(str(new_buffer))

    page.locator("#btn-save-settings").click()
    page.wait_for_timeout(1000)

    resp = httpx.get(f"{base_url}/api/config")
    assert resp.json()["lookback"]["buffer_days"] == new_buffer

    lsof = subprocess.run(["lsof", "-ti:8080"], capture_output=True, text=True)
    for pid in lsof.stdout.strip().splitlines():
        os.kill(int(pid), 9)
    time.sleep(2)

    env = os.environ.copy()
    proc = subprocess.Popen(
        ["python3", "-m", "quantflow.cli", "web"],
        cwd=str(PROJECT_ROOT), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", WEB_PORT)) == 0:
                s.close()
                break
            s.close()
        except OSError:
            pass
        time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Server did not restart in time")

    try:
        page.reload()
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        field = page.locator("#cfg-lookback-buffer")
        field.wait_for(state="visible", timeout=5000)
        assert field.input_value() == str(new_buffer)
    finally:
        original["lookback"]["buffer_days"] = orig_buffer
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(original, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
