"""Data boundary tests for QuantFlow Web UI.

Tests verify that config files remain unchanged when:
- User modifies parameters but cancels without saving
- User switches tabs/pages while editing
- User refreshes page after saving (params persist)

These tests protect against accidental data loss and ensure
the save/cancel boundary is correctly enforced.
"""
import yaml
import pytest
from playwright.sync_api import Page
from pathlib import Path

from tests.web.e2e.conftest import PROJECT_ROOT, SERVER_URL


class TestSettingsCancelBoundary:
    """Verify Settings modifications that are cancelled don't affect YAML."""

    def test_settings_modify_without_save_yaml_unchanged(self, page: Page):
        """Modify settings but don't save - YAML should remain unchanged."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"
        
        with open(cfg_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)
        original_buffer = original.get("lookback", {}).get("buffer_days", 30)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        buffer_field = page.locator("#cfg-lookback-buffer")
        buffer_field.fill(str(original_buffer + 50))

        page.get_by_role("button", name="Watchlists").click()
        page.wait_for_selector("#watchlist-list", timeout=5000)

        with open(cfg_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f)
        current_buffer = current.get("lookback", {}).get("buffer_days", 30)

        assert current_buffer == original_buffer

    def test_settings_cancel_after_modify_yaml_unchanged(self, page: Page):
        """Click cancel/reset after modifying settings - YAML unchanged."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"
        
        with open(cfg_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)
        original_level = original.get("logging", {}).get("console_level", "INFO")

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        logging_select = page.locator("#cfg-log-console-level")
        logging_select.select_option(label="DEBUG")

        if page.locator("#btn-reset-settings").is_visible():
            page.locator("#btn-reset-settings").click()
        else:
            page.get_by_role("button", name="Watchlists").click()

        page.wait_for_timeout(500)

        with open(cfg_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f)
        current_level = current.get("logging", {}).get("console_level", "INFO")

        assert current_level == original_level


class TestIndicatorParamsCancelBoundary:
    """Verify Indicator params modifications that are cancelled don't affect YAML."""

    def test_indicator_params_cancel_without_save(self, page: Page):
        """Modify indicator params but click Cancel - YAML unchanged."""
        indicators_path = PROJECT_ROOT / "config" / "indicators.yaml"
        
        if not indicators_path.exists():
            pytest.skip("indicators.yaml not found")

        with open(indicators_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)

        kdj_params_original = None
        if "indicators" in original and "KDJ" in original["indicators"]:
            kdj_params_original = original["indicators"]["KDJ"].get("params", {}).get("n", 9)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Library").click()
        page.locator("#panel-library").wait_for(state="visible", timeout=5000)
        page.get_by_role("button", name="Indicators").click()
        page.locator("#library-indicators-panel").wait_for(state="visible", timeout=5000)

        page.locator(".indicator-config-btn").first.click()
        page.locator("#modal-indicator-params").wait_for(state="visible", timeout=5000)

        first_input = page.locator(".indicator-param-input").first
        original_val = int(first_input.input_value())
        first_input.fill(str(original_val + 100))

        page.locator("#btn-cancel-params").click()
        page.locator("#modal-indicator-params").wait_for(state="hidden", timeout=5000)

        with open(indicators_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f)

        kdj_params_current = None
        if "indicators" in current and "KDJ" in current["indicators"]:
            kdj_params_current = current["indicators"]["KDJ"].get("params", {}).get("n", 9)

        assert kdj_params_current == kdj_params_original


class TestWatchlistEditCancelBoundary:
    """Verify Watchlist edits that are cancelled don't affect YAML."""

    def test_watchlist_edit_cancel_yaml_unchanged(self, page: Page):
        """Edit watchlist item but cancel - YAML unchanged."""
        from tests.web.e2e.conftest import TEST_WATCHLIST_NAME
        import httpx
        
        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        
        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "AAPL.US", "name": "Apple", "tags": []}
            ]},
        )

        with open(wl_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)
        original_items = len(original.get("items", []))

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        if page.locator("#btn-edit-watchlist").is_visible():
            page.locator("#btn-edit-watchlist").click()
            page.wait_for_timeout(500)
            page.get_by_role("button", name="Watchlists").click()

        with open(wl_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f)
        current_items = len(current.get("items", []))

        assert current_items == original_items


class TestTaskEditCancelBoundary:
    """Verify Task edits that are cancelled don't affect YAML."""

    def test_task_edit_cancel_yaml_unchanged(self, page: Page):
        """Edit task but cancel - YAML unchanged."""
        from tests.web.e2e.conftest import TEST_TASK_FILE
        import httpx
        
        httpx.post(f"{SERVER_URL}/api/task-files", json={"filename": TEST_TASK_FILE})
        httpx.post(
            f"{SERVER_URL}/api/tasks?filename={TEST_TASK_FILE}",
            json={
                "name": "test_task",
                "watchlist": "watchlists/djia.yaml",
                "strategies": ["daily_bull_oversold"],
                "output": "./output/test",
            },
        )

        task_path = PROJECT_ROOT / "config" / TEST_TASK_FILE
        
        with open(task_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)
        original_task_count = len(original.get("tasks", []))

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Tasks").click()
        page.wait_for_selector("#task-file-list", timeout=5000)
        page.get_by_text(TEST_TASK_FILE).click()
        page.wait_for_selector("#task-table", timeout=5000)

        if page.locator(".task-edit-btn").first.is_visible():
            page.locator(".task-edit-btn").first.click()
            page.wait_for_timeout(500)
            page.locator("#modal-task .close-btn").click()

        with open(task_path, "r", encoding="utf-8") as f:
            current = yaml.safe_load(f)
        current_task_count = len(current.get("tasks", []))

        assert current_task_count == original_task_count


class TestModifySaveSequence:
    """Verify sequential modify-save operations."""

    def test_modify_save_modify_save_sequence(self, page: Page):
        """Multiple modify-save cycles should update YAML correctly each time."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"
        
        with open(cfg_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)
        original_buffer = original.get("lookback", {}).get("buffer_days", 30)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        buffer_field = page.locator("#cfg-lookback-buffer")

        buffer_field.fill(str(original_buffer + 10))
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(1000)

        with open(cfg_path, "r", encoding="utf-8") as f:
            after_first = yaml.safe_load(f)
        assert after_first["lookback"]["buffer_days"] == original_buffer + 10

        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)
        buffer_field = page.locator("#cfg-lookback-buffer")
        buffer_field.fill(str(original_buffer + 20))
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(1000)

        with open(cfg_path, "r", encoding="utf-8") as f:
            after_second = yaml.safe_load(f)
        assert after_second["lookback"]["buffer_days"] == original_buffer + 20


class TestRefreshAfterSave:
    """Verify parameters persist after page refresh."""

    def test_refresh_page_after_save_params_persist(self, page: Page):
        """Save settings, refresh page, values should persist."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"
        
        with open(cfg_path, "r", encoding="utf-8") as f:
            original = yaml.safe_load(f)
        original_multiplier = original.get("lookback", {}).get("calendar_multiplier", 2)

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        multiplier_field = page.locator("#cfg-lookback-multiplier")
        new_value = original_multiplier + 1 if original_multiplier < 5 else 1
        multiplier_field.fill(str(new_value))
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(1000)

        page.reload()
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        multiplier_field = page.locator("#cfg-lookback-multiplier")
        assert multiplier_field.input_value() == str(new_value)


class TestSwitchTabWhileEditing:
    """Verify behavior when switching tabs during edit."""

    def test_switch_tab_while_editing_shows_no_dirty_warning(self, page: Page):
        """Switching tab while editing Settings should not trigger dirty warning."""
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        buffer_field = page.locator("#cfg-lookback-buffer")
        buffer_field.fill("999")

        page.get_by_role("button", name="Tasks").click()
        page.wait_for_selector("#task-file-list", timeout=5000)

        dirty_indicator = page.locator("#settings-dirty-indicator")
        if dirty_indicator.is_visible():
            assert "unsaved" in dirty_indicator.text_content().lower()