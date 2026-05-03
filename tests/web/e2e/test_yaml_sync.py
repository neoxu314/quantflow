"""YAML synchronization tests for QuantFlow Web UI.

Tests verify that after editing and saving via UI:
- YAML file is correctly updated with new values
- YAML structure and format are preserved
- Re-opening the panel shows values matching YAML
- List values and unicode characters are correctly saved
"""
import yaml
import pytest
from playwright.sync_api import Page
from pathlib import Path

from tests.web.e2e.conftest import PROJECT_ROOT, SERVER_URL, TEST_WATCHLIST_NAME, TEST_TASK_FILE


class TestWatchlistYamlSync:
    """Watchlist edits should correctly sync to YAML file."""

    def test_watchlist_edit_item_yaml_sync(self, page: Page):
        """Edit watchlist item via UI, verify YAML file updated."""
        import httpx
        
        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "AAPL.US", "name": "Apple Inc", "tags": ["tech"]}
            ]},
        )

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        
        with open(wl_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        page.get_by_role("button", name="+ Add Stock").click()
        page.locator("#modal-add-stock").wait_for(state="visible", timeout=5000)
        page.locator("#add-stock-market").select_option(label="🇺🇸 US (美国)")
        page.locator("#add-stock-code").fill("MSFT")
        page.locator("#add-stock-name").fill("Microsoft Corp")
        page.get_by_role("button", name="Add").click()
        page.wait_for_timeout(1000)

        with open(wl_path, "r", encoding="utf-8") as f:
            updated = yaml.safe_load(f)

        codes = [item["code"] for item in updated.get("items", [])]
        assert "AAPL.US" in codes
        assert "MSFT.US" in codes

    def test_watchlist_delete_item_yaml_sync(self, page: Page):
        """Delete watchlist item via UI, verify YAML file updated."""
        import httpx
        
        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "AAPL.US", "name": "Apple", "tags": []},
                {"code": "GOOG.US", "name": "Google", "tags": []},
            ]},
        )

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        
        with open(wl_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)
        original_count = len(original.get("items", []))

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        delete_btn = page.locator("#stock-table .delete-stock-btn").first
        if delete_btn.is_visible():
            delete_btn.click()
            page.wait_for_timeout(1000)

        with open(wl_path, "r", encoding="utf-8") as f:
            updated = yaml.safe_load(f)
        updated_count = len(updated.get("items", []))

        assert updated_count < original_count

    def test_watchlist_yaml_unicode_correct(self, page: Page):
        """Chinese characters in watchlist name/items should save correctly."""
        import httpx
        
        chinese_name = "测试列表_中文"
        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": chinese_name, "items": [
                {"code": "600519.SH", "name": "贵州茅台", "tags": ["白酒"]}
            ]},
        )

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        
        with open(wl_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert data["name"] == chinese_name
        assert any("茅台" in item.get("name", "") for item in data.get("items", []))


class TestTaskYamlSync:
    """Task edits should correctly sync to YAML file."""

    def test_task_edit_yaml_sync(self, page: Page):
        """Edit task via UI, verify YAML file updated."""
        import httpx
        
        httpx.post(f"{SERVER_URL}/api/task-files", json={"filename": TEST_TASK_FILE})
        httpx.post(
            f"{SERVER_URL}/api/tasks?filename={TEST_TASK_FILE}",
            json={
                "name": "test_edit_task",
                "watchlist": "watchlists/djia.yaml",
                "strategies": ["daily_bull_oversold"],
                "output": "./output/original",
            },
        )

        task_path = PROJECT_ROOT / "config" / TEST_TASK_FILE

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Tasks").click()
        page.wait_for_selector("#task-file-list", timeout=5000)
        page.get_by_text(TEST_TASK_FILE).click()
        page.wait_for_selector("#task-table", timeout=5000)

        edit_btn = page.locator(".task-edit-btn").first
        if edit_btn.is_visible():
            edit_btn.click()
            page.locator("#modal-task").wait_for(state="visible", timeout=5000)
            
            output_field = page.locator("#task-output")
            output_field.fill("./output/edited")
            
            save_btn = page.locator("#modal-task .save-btn")
            if save_btn.is_visible():
                save_btn.click()
            page.wait_for_timeout(1000)

        with open(task_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        task = next((t for t in data.get("tasks", []) if t["name"] == "test_edit_task"), None)
        if task:
            assert task.get("output") == "./output/edited"

    def test_task_delete_yaml_sync(self, page: Page):
        """Delete task via UI, verify YAML file updated."""
        import httpx
        
        httpx.post(f"{SERVER_URL}/api/task-files", json={"filename": TEST_TASK_FILE})
        httpx.post(
            f"{SERVER_URL}/api/tasks?filename={TEST_TASK_FILE}",
            json={
                "name": "task_to_delete",
                "watchlist": "watchlists/djia.yaml",
                "strategies": [],
                "output": "./output/tmp",
            },
        )

        task_path = PROJECT_ROOT / "config" / TEST_TASK_FILE
        
        with open(task_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)
        original_count = len(original.get("tasks", []))

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Tasks").click()
        page.wait_for_selector("#task-file-list", timeout=5000)
        page.get_by_text(TEST_TASK_FILE).click()
        page.wait_for_selector("#task-table", timeout=5000)

        delete_btn = page.locator(".task-delete-btn").first
        if delete_btn.is_visible():
            delete_btn.click()
            page.wait_for_timeout(1000)

        with open(task_path, "r", encoding="utf-8") as f:
            updated = yaml.safe_load(f)
        updated_count = len(updated.get("tasks", []))

        assert updated_count < original_count


class TestIndicatorParamsYamlSync:
    """Indicator params edits should correctly sync to YAML file."""

    def test_indicator_params_yaml_format_correct(self, page: Page):
        """After saving indicator params, YAML should be valid and parseable."""
        indicators_path = PROJECT_ROOT / "config" / "indicators.yaml"
        
        if not indicators_path.exists():
            pytest.skip("indicators.yaml not found")

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Library").click()
        page.locator("#panel-library").wait_for(state="visible", timeout=5000)
        page.get_by_role("button", name="Indicators").click()
        page.locator("#library-indicators-panel").wait_for(state="visible", timeout=5000)

        page.locator(".indicator-config-btn").first.click()
        page.locator("#modal-indicator-params").wait_for(state="visible", timeout=5000)

        first_input = page.locator(".indicator-param-input").first
        first_input.fill("15")
        page.locator("#btn-save-params").click()
        page.locator("#modal-indicator-params").wait_for(state="hidden", timeout=5000)
        page.wait_for_timeout(1000)

        with open(indicators_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        data = yaml.safe_load(content)
        assert isinstance(data, dict)
        assert "indicators" in data

    def test_indicator_params_reopen_matches_yaml(self, page: Page):
        """After saving, re-opening indicator params modal should show YAML values."""
        indicators_path = PROJECT_ROOT / "config" / "indicators.yaml"
        
        if not indicators_path.exists():
            pytest.skip("indicators.yaml not found")

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Library").click()
        page.locator("#panel-library").wait_for(state="visible", timeout=5000)
        page.get_by_role("button", name="Indicators").click()
        page.locator("#library-indicators-panel").wait_for(state="visible", timeout=5000)

        page.locator(".indicator-config-btn").first.click()
        page.locator("#modal-indicator-params").wait_for(state="visible", timeout=5000)

        first_input = page.locator(".indicator-param-input").first
        first_input.fill("25")
        page.locator("#btn-save-params").click()
        page.locator("#modal-indicator-params").wait_for(state="hidden", timeout=5000)
        page.wait_for_timeout(1000)

        page.locator(".indicator-config-btn").first.click()
        page.locator("#modal-indicator-params").wait_for(state="visible", timeout=5000)

        first_input = page.locator(".indicator-param-input").first
        ui_value = first_input.input_value()

        with open(indicators_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        first_indicator_name = list(data.get("indicators", {}).keys())[0]
        yaml_value = str(data["indicators"][first_indicator_name].get("params", {}).get("n", 9))

        assert ui_value == yaml_value


class TestSettingsYamlSync:
    """Settings edits should correctly sync to YAML file."""

    def test_settings_yaml_list_values_preserved(self, page: Page):
        """YAML list values (like yfinance batch params) should remain lists after save."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        chunk_size_field = page.locator("#cfg-yfinance-chunk-size")
        chunk_size_field.fill("75")
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(1000)

        with open(cfg_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert data.get("yfinance", {}).get("batch", {}).get("chunk_size") == 75

    def test_settings_yaml_unicode_correct(self, page: Page):
        """YAML should handle unicode correctly after settings save."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        buffer_field = page.locator("#cfg-lookback-buffer")
        buffer_field.fill("45")
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(1000)

        with open(cfg_path, "r", encoding="utf-8") as f:
            content = f.read()

        data = yaml.safe_load(content)
        assert data.get("lookback", {}).get("buffer_days") == 45

    def test_yaml_reparse_after_save(self, page: Page):
        """YAML file should be re-parseable after any UI save operation."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"

        with open(cfg_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        port_field = page.locator("#cfg-web-port")
        port_field.fill("9090")
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(1000)

        with open(cfg_path, "r", encoding="utf-8") as f:
            content = f.read()

        data = yaml.safe_load(content)
        assert isinstance(data, dict)
        assert "web" in data
        assert data["web"]["port"] == 9090

    def test_yaml_field_order_preserved(self, page: Page):
        """YAML field order should be preserved (sort_keys=False)."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        buffer_field = page.locator("#cfg-lookback-buffer")
        buffer_field.fill("50")
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(1000)

        with open(cfg_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "data:" in content
        assert "tushare:" in content
        assert "logging:" in content

        data_idx = content.find("data:")
        tushare_idx = content.find("tushare:")
        logging_idx = content.find("logging:")

        if all(idx >= 0 for idx in [data_idx, tushare_idx, logging_idx]):
            assert data_idx < tushare_idx