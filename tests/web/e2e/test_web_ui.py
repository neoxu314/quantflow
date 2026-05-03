"""End-to-end Playwright tests for QuantFlow Web UI.

Requires: pip install pytest-playwright
Usage: playwright install chromium && pytest tests/web/e2e/test_web_ui.py -v

Note: Shared fixtures (web_server, base_url, protect_production_configs) are
      defined in conftest.py and automatically applied to all E2E tests.
"""
import pytest
from pathlib import Path

from playwright.sync_api import Page

from tests.web.e2e.conftest import (
    PROJECT_ROOT,
    SERVER_URL,
    TEST_WATCHLIST_NAME,
    TEST_TASK_FILE,
)

# Page fixture is provided by pytest-playwright
# web_server and base_url fixtures are in conftest.py (session scope)
# protect_production_configs fixture is in conftest.py (autouse=True)


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


def test_new_watchlist_yaml_created(page: Page, base_url):
    """Create watchlist via UI, then verify the underlying YAML file on disk."""
    import yaml

    page.goto(base_url)
    page.wait_for_load_state("networkidle")

    def handle_dialog(dialog):
        dialog.accept(TEST_WATCHLIST_NAME)

    page.once("dialog", handle_dialog)
    page.get_by_role("button", name="+ New").click()

    page.get_by_role("button", name=TEST_WATCHLIST_NAME).wait_for(
        state="visible", timeout=5000
    )

    wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
    assert wl_path.exists()
    data = yaml.safe_load(wl_path.read_text())
    assert data["name"] == TEST_WATCHLIST_NAME
    assert data.get("items") == [] or data.get("items") is None


def test_new_task_file_yaml_created(page: Page, base_url):
    """Create task file via UI, then verify the underlying YAML file on disk."""
    import yaml, httpx

    httpx.post(
        f"{base_url}/api/task-files",
        json={"filename": TEST_TASK_FILE},
    )

    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Tasks").click()
    page.get_by_text(TEST_TASK_FILE).wait_for(state="visible", timeout=5000)

    tf_path = PROJECT_ROOT / "config" / TEST_TASK_FILE
    assert tf_path.exists()
    data = yaml.safe_load(tf_path.read_text())
    assert data == {"tasks": []}


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


def test_library_panel_loads_strategies(page: Page, base_url):
    """Library tab appears, strategies load, and strategy cards display."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Library").click()
    page.locator("#panel-library").wait_for(state="visible", timeout=5000)
    page.locator("#library-strategies-list").wait_for(state="visible", timeout=5000)
    strategy_count = page.locator("#library-strategies-list > div").count()
    assert strategy_count >= 4


def test_library_panel_indicators_tab(page: Page, base_url):
    """Library indicators sub-tab shows indicator table."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Library").click()
    page.locator("#panel-library").wait_for(state="visible", timeout=5000)
    page.get_by_role("button", name="Indicators").click()
    page.locator("#library-indicators-panel").wait_for(state="visible", timeout=5000)
    page.locator("#library-indicators-table").wait_for(state="visible", timeout=5000)
    row_count = page.locator("#library-indicators-table > tr").count()
    assert row_count == 8


def test_tab_navigation_includes_library(page: Page, base_url):
    """Tab navigation round-trip includes Library tab."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Library").click()
    page.locator("#panel-library").wait_for(state="visible", timeout=5000)
    page.get_by_role("button", name="Tasks").click()
    page.locator("#task-file-list").wait_for(state="visible", timeout=5000)
    page.get_by_role("button", name="Library").click()
    page.locator("#panel-library").wait_for(state="visible", timeout=5000)


def test_settings_modify_and_save(page: Page, base_url):
    """Modify a config setting via UI, save, and verify the file is updated."""
    import httpx, yaml

    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Settings").click()
    page.wait_for_selector("#settings-form", timeout=5000)

    cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"

    logging_select = page.locator("#cfg-log-level")
    logging_select.select_option(label="WARNING")

    page.locator("#btn-save-settings").click()
    page.wait_for_timeout(2000)

    verify = httpx.get(f"{base_url}/api/config").json()
    assert verify["logging"]["level"] == "WARNING"

    with open(cfg_path, "r", encoding="utf-8") as f:
        saved = yaml.safe_load(f)
    assert saved["logging"]["level"] == "WARNING"


def test_add_stock_with_market_selector(page: Page, base_url):
    """Add stock via UI using market selector, then verify YAML on disk has correct suffix."""
    import yaml, httpx

    wl_name = "_test_market_selector"

    def handle_dialog(dialog):
        dialog.accept(wl_name)

    page.goto(base_url)
    page.wait_for_load_state("networkidle")

    page.once("dialog", handle_dialog)
    page.get_by_role("button", name="+ New").click()

    page.get_by_role("button", name=wl_name).wait_for(state="visible", timeout=5000)

    page.get_by_role("button", name="+ Add Stock").click()

    page.locator("#modal-add-stock").wait_for(state="visible", timeout=5000)

    page.locator("#add-stock-market").select_option(label="🇺🇸 US (美国)")

    page.locator("#add-stock-code").fill("AAPL")

    page.locator("#add-stock-preview").wait_for(state="visible", timeout=3000)
    preview_text = page.locator("#add-stock-preview-code").text_content()
    assert preview_text.strip() == "AAPL.US"

    page.locator("#add-stock-name").fill("Apple Inc")

    page.get_by_role("button", name="Add").click()

    page.locator("#stock-table").get_by_text("AAPL.US").wait_for(state="visible", timeout=5000)

    wl_path = PROJECT_ROOT / "watchlists" / f"{wl_name}.yaml"
    assert wl_path.exists()
    data = yaml.safe_load(wl_path.read_text())
    assert any(item["code"] == "AAPL.US" for item in data.get("items", []))

    httpx.delete(f"{base_url}/api/watchlists/{wl_name}.yaml")
    if wl_path.exists():
        wl_path.unlink()


def test_add_stock_multiple_markets(page: Page, base_url):
    """Verify adding stocks from different markets produces correct suffixes in YAML."""
    import yaml, httpx

    wl_name = "_test_multi_market"

    def handle_dialog(dialog):
        dialog.accept(wl_name)

    page.goto(base_url)
    page.wait_for_load_state("networkidle")

    page.once("dialog", handle_dialog)
    page.get_by_role("button", name="+ New").click()
    page.get_by_role("button", name=wl_name).wait_for(state="visible", timeout=5000)

    test_cases = [
        ("HK", "00700", "00700.HK"),
        ("JP", "7203", "7203.T"),
        ("KR", "005930", "005930.KS"),
    ]

    for market_opt, raw_code, expected_code in test_cases:
        page.get_by_role("button", name="+ Add Stock").click()
        page.locator("#modal-add-stock").wait_for(state="visible", timeout=5000)

        page.locator("#add-stock-market").select_option(value=market_opt)
        page.locator("#add-stock-code").fill(raw_code)

        page.locator("#add-stock-preview").wait_for(state="visible", timeout=3000)
        preview_text = page.locator("#add-stock-preview-code").text_content().strip()
        assert preview_text == expected_code

        page.locator("#add-stock-name").fill(f"Stock {raw_code}")
        page.get_by_role("button", name="Add").click()

        page.locator("#stock-table").get_by_text(expected_code).wait_for(state="visible", timeout=5000)

    wl_path = PROJECT_ROOT / "watchlists" / f"{wl_name}.yaml"
    assert wl_path.exists()
    data = yaml.safe_load(wl_path.read_text())
    codes = [item["code"] for item in data.get("items", [])]
    assert "00700.HK" in codes
    assert "7203.T" in codes
    assert "005930.KS" in codes

    httpx.delete(f"{base_url}/api/watchlists/{wl_name}.yaml")
    if wl_path.exists():
        wl_path.unlink()


def test_settings_survive_server_restart(page: Page, base_url):
    """Modify a config, restart server, and confirm changes persist."""
    import httpx, subprocess, time, socket, os

    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Settings").click()
    page.wait_for_selector("#settings-form", timeout=5000)

    buffer_field = page.locator("#cfg-lookback-buffer")
    buffer_field.fill("99")

    page.locator("#btn-save-settings").click()
    page.wait_for_timeout(1000)

    resp = httpx.get(f"{base_url}/api/config")
    assert resp.json()["lookback"]["buffer_days"] == 99

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
        assert field.input_value() == "99"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_library_strategy_descriptions_visible(page: Page, base_url):
    """Strategy cards in Library tab show non-empty descriptions."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Library").click()
    page.locator("#panel-library").wait_for(state="visible", timeout=5000)
    page.locator("#library-strategies-list").wait_for(state="visible", timeout=5000)
    desc_paragraphs = page.locator("#library-strategies-list > div p")
    count = desc_paragraphs.count()
    assert count >= 2, f"Expected at least 2 description paragraphs, got {count}"
    for i in range(count):
        text = desc_paragraphs.nth(i).text_content()
        assert text and len(text.strip()) > 10, f"Description {i} is too short or empty: {text}"


def test_library_indicator_param_edit(page: Page, base_url):
    """Indicator params modal opens, edit saves, toast appears."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Library").click()
    page.locator("#panel-library").wait_for(state="visible", timeout=5000)
    page.get_by_role("button", name="Indicators").click()
    page.locator("#library-indicators-panel").wait_for(state="visible", timeout=5000)
    page.locator("#library-indicators-table").wait_for(state="visible", timeout=5000)
    page.locator(".indicator-config-btn").first.click()
    page.locator("#modal-indicator-params").wait_for(state="visible", timeout=5000)
    title = page.locator("#indicator-params-title")
    assert "Configure" in title.text_content()
    first_input = page.locator(".indicator-param-input").first
    first_input.fill("99")
    page.locator("#btn-save-params").click()
    page.locator("#modal-indicator-params").wait_for(state="hidden", timeout=5000)
    toast_el = page.locator("#toast")
    toast_el.wait_for(state="visible", timeout=5000)
    assert "save" in toast_el.text_content().lower()

def test_indicator_params_visible_on_reopen(page: Page, base_url):
    """Edit indicator params, save, reopen modal, verify new value persists."""
    page.goto(base_url)
    page.wait_for_load_state("networkidle")
    page.get_by_role("button", name="Library").click()
    page.locator("#panel-library").wait_for(state="visible", timeout=5000)
    page.get_by_role("button", name="Indicators").click()
    page.locator("#library-indicators-panel").wait_for(state="visible", timeout=5000)
    page.locator("#library-indicators-table").wait_for(state="visible", timeout=5000)
    page.locator(".indicator-config-btn").first.click()
    page.locator("#modal-indicator-params").wait_for(state="visible", timeout=5000)
    
    # Get the initial value of the first input
    first_input = page.locator(".indicator-param-input").first
    initial_val = first_input.input_value()
    
    # Change it
    first_input.fill(str(int(initial_val) + 1))
    
    # Save
    page.locator("#btn-save-params").click()
    page.locator("#modal-indicator-params").wait_for(state="hidden", timeout=5000)
    page.wait_for_timeout(1000)
    
    # Reopen modal for the same indicator
    page.locator(".indicator-config-btn").first.click()
    page.locator("#modal-indicator-params").wait_for(state="visible", timeout=5000)
    
    # Verify the value changed
    new_val = first_input.input_value()
    assert new_val == str(int(initial_val) + 1), f"Expected {int(initial_val)+1}, got {new_val}"
    
    # Close
    page.locator("#btn-cancel-params").click()
    page.locator("#modal-indicator-params").wait_for(state="hidden", timeout=5000)
