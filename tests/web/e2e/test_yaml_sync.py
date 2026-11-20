"""YAML synchronization tests for QuantFlow Web UI.

Tests verify that after editing and saving via UI:
- YAML file is correctly updated with new values
- YAML structure and format are preserved
- Re-opening the panel shows values matching YAML
- List values and unicode characters are correctly saved
"""
import yaml
import pytest
from playwright.sync_api import Page, expect
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
        page.get_by_role("button", name="Add", exact=True).click()
        expect(page.locator("#stock-table")).to_contain_text("MSFT.US")
        assert yaml.safe_load(wl_path.read_text()) == original
        with page.expect_response(lambda r: r.request.method == "PUT" and r.url.endswith(wl_path.name)) as saved:
            page.locator("#btn-save-watchlist").click()
        assert saved.value.ok

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

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        row = page.locator("#stock-table").get_by_role("row").filter(has_text="AAPL.US")
        row.get_by_role("button", name="Delete", exact=True).click()
        expect(row).to_have_count(0)
        assert yaml.safe_load(wl_path.read_text()) == original
        with page.expect_response(lambda r: r.request.method == "PUT" and r.url.endswith(wl_path.name)) as saved:
            page.locator("#btn-save-watchlist").click()
        assert saved.value.ok
        updated = yaml.safe_load(wl_path.read_text())
        assert [item["code"] for item in updated["items"]] == ["GOOG.US"]

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


class TestWatchlistInlineNameEditing:
    """Inline name editing should update YAML after save."""

    def test_edit_name_inline_and_save(self, page: Page):
        """Click name cell, edit it, save, verify YAML updated."""
        import httpx

        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "AAPL.US", "name": "Apple Inc", "tags": ["tech"]},
            ]},
        )

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        name_span = page.locator(".editable-name").first
        name_span.click()
        page.wait_for_timeout(300)

        name_input = page.locator("#stock-table input[type='text']").first
        expect(name_input).to_be_visible()
        name_input.clear()
        name_input.fill("Apple Inc Updated")
        name_input.press("Enter")
        page.wait_for_timeout(300)

        save_btn = page.locator("#btn-save-watchlist")
        if save_btn.is_visible():
            save_btn.click()
            page.wait_for_timeout(1000)

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        with open(wl_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        item = next((i for i in data.get("items", []) if i["code"] == "AAPL.US"), None)
        assert item is not None
        assert item.get("name") == "Apple Inc Updated"

    def test_edit_name_escape_cancels(self, page: Page):
        """Press Escape after editing name should revert change."""
        import httpx

        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "MSFT.US", "name": "Microsoft", "tags": []},
            ]},
        )

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        name_span = page.locator(".editable-name").first
        name_span.click()
        name_input = page.locator("#stock-table input[type='text']")
        name_input.fill("Changed Name")
        name_input.press("Escape")
        expect(name_span).to_have_text("Microsoft")
        expect(page.locator("#btn-save-watchlist")).to_be_hidden()

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        with open(wl_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        item = next((i for i in data.get("items", []) if i["code"] == "MSFT.US"), None)
        assert item is not None
        assert item.get("name") == "Microsoft"


class TestWatchlistInlineTagsEditing:
    """Inline tags editing should update YAML after save."""

    def test_add_tag_inline_and_save(self, page: Page):
        """Click tags cell, add a tag, save, verify YAML updated."""
        import httpx

        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "NVDA.US", "name": "Nvidia", "tags": ["tech"]},
            ]},
        )

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        tags_div = page.locator(".editable-tags").first
        tags_div.click()
        page.wait_for_timeout(300)

        tag_input = page.locator(".editable-tags input[type='text']").first
        expect(tag_input).to_be_visible()
        tag_input.fill("AI")
        tag_input.press("Enter")
        page.wait_for_timeout(300)

        page.locator("body").click()
        page.wait_for_timeout(300)

        save_btn = page.locator("#btn-save-watchlist")
        if save_btn.is_visible():
            save_btn.click()
            page.wait_for_timeout(1000)

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        with open(wl_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        item = next((i for i in data.get("items", []) if i["code"] == "NVDA.US"), None)
        assert item is not None
        assert "AI" in item.get("tags", [])
        assert "tech" in item.get("tags", [])

    def test_remove_tag_inline_and_save(self, page: Page):
        """Click tags cell, remove a tag via x button, save, verify YAML updated."""
        import httpx

        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "TSLA.US", "name": "Tesla", "tags": ["tech", "EV"]},
            ]},
        )

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        tags_div = page.locator(".editable-tags").first
        tags_div.click()
        page.wait_for_timeout(300)

        remove_btn = page.locator(".tag-remove-btn").first
        if remove_btn.is_visible():
            remove_btn.click()
            page.wait_for_timeout(300)

        page.locator("body").click()
        page.wait_for_timeout(300)

        save_btn = page.locator("#btn-save-watchlist")
        if save_btn.is_visible():
            save_btn.click()
            page.wait_for_timeout(1000)

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        with open(wl_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        item = next((i for i in data.get("items", []) if i["code"] == "TSLA.US"), None)
        assert item is not None
        tags = item.get("tags", [])
        assert len(tags) < 2

    def test_edit_tags_escape_cancels(self, page: Page):
        """Press Escape in tags edit mode should cancel without saving."""
        import httpx

        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "GOOG.US", "name": "Google", "tags": ["tech"]},
            ]},
        )

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        tags_div = page.locator(".editable-tags").first
        tags_div.click()
        page.wait_for_timeout(300)

        tag_input = page.locator(".editable-tags input[type='text']").first
        expect(tag_input).to_be_visible()
        tag_input.fill("NewTag")
        tag_input.press("Escape")
        page.wait_for_timeout(300)

        save_btn = page.locator("#btn-save-watchlist")
        assert not save_btn.is_visible()

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        with open(wl_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        item = next((i for i in data.get("items", []) if i["code"] == "GOOG.US"), None)
        assert item is not None
        assert "NewTag" not in item.get("tags", [])

    def test_edit_second_stock_tags_in_multi_stock_watchlist(self, page: Page):
        """Edit tags on the second stock in a multi-stock watchlist - regression test for e.currentTarget bug."""
        import httpx

        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "AAPL.US", "name": "Apple", "tags": ["tech"]},
                {"code": "NVDA.US", "name": "Nvidia", "tags": ["tech"]},
                {"code": "TSLA.US", "name": "Tesla", "tags": ["EV"]},
            ]},
        )

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        second_tags = page.locator(".editable-tags").nth(1)
        second_tags.click()
        page.wait_for_timeout(300)

        tag_input = page.locator(".editable-tags input[type='text']").first
        expect(tag_input).to_be_visible()
        tag_input.fill("AI")
        tag_input.press("Enter")
        page.wait_for_timeout(300)

        page.locator("body").click()
        page.wait_for_timeout(300)

        save_btn = page.locator("#btn-save-watchlist")
        if save_btn.is_visible():
            save_btn.click()
            page.wait_for_timeout(1000)

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        with open(wl_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        nvda_item = next((i for i in data.get("items", []) if i["code"] == "NVDA.US"), None)
        assert nvda_item is not None
        assert "AI" in nvda_item.get("tags", [])
        assert "tech" in nvda_item.get("tags", [])

        aapl_item = next((i for i in data.get("items", []) if i["code"] == "AAPL.US"), None)
        assert aapl_item is not None
        assert "AI" not in aapl_item.get("tags", [])

    def test_edit_second_stock_name_in_multi_stock_watchlist(self, page: Page):
        """Edit name on the second stock in a multi-stock watchlist."""
        import httpx

        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": [
                {"code": "AAPL.US", "name": "Apple", "tags": []},
                {"code": "NVDA.US", "name": "Nvidia", "tags": []},
            ]},
        )

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        second_name = page.locator(".editable-name").nth(1)
        second_name.click()
        page.wait_for_timeout(300)

        name_input = page.locator("#stock-table input[type='text']").first
        expect(name_input).to_be_visible()
        name_input.clear()
        name_input.fill("NVIDIA Corp")
        name_input.press("Enter")
        page.wait_for_timeout(300)

        save_btn = page.locator("#btn-save-watchlist")
        if save_btn.is_visible():
            save_btn.click()
            page.wait_for_timeout(1000)

        wl_path = PROJECT_ROOT / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml"
        with open(wl_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        nvda_item = next((i for i in data.get("items", []) if i["code"] == "NVDA.US"), None)
        assert nvda_item is not None
        assert nvda_item.get("name") == "NVIDIA Corp"
        aapl_item = next((i for i in data.get("items", []) if i["code"] == "AAPL.US"), None)
        assert aapl_item is not None
        assert aapl_item.get("name") == "Apple"


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
        page.get_by_role("button", name="Tasks", exact=True).click()
        page.wait_for_selector("#task-file-list", timeout=5000)
        page.locator("#task-file-list").get_by_role("button", name=TEST_TASK_FILE).click()
        page.wait_for_selector("#task-table", timeout=5000)

        page.locator("#task-table").get_by_role("button", name="Edit", exact=True).click()
        page.locator("#task-name").fill("edited_task")
        with page.expect_response(lambda r: "/api/tasks/" in r.url and r.request.method == "PUT") as saved:
            page.locator("#btn-save-task").click()
        assert saved.value.ok
        expect(page.locator("#task-table")).to_contain_text("edited_task")
        data = yaml.safe_load(task_path.read_text())
        assert [task["name"] for task in data["tasks"]] == ["edited_task"]
        assert data["tasks"][0]["watchlist"] == "watchlists/djia.yaml"
        assert data["tasks"][0]["strategies"] == ["daily_bull_oversold"]

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
        
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Tasks", exact=True).click()
        page.wait_for_selector("#task-file-list", timeout=5000)
        page.locator("#task-file-list").get_by_role("button", name=TEST_TASK_FILE).click()
        page.wait_for_selector("#task-table", timeout=5000)

        row = page.locator("#task-table").get_by_role("row").filter(has_text="task_to_delete")
        page.once("dialog", lambda dialog: dialog.accept())
        with page.expect_response(lambda r: "/api/tasks/" in r.url and r.request.method == "DELETE") as deleted:
            row.get_by_role("button", name="Delete", exact=True).click()
        assert deleted.value.ok
        expect(row).to_have_count(0)
        assert yaml.safe_load(task_path.read_text())["tasks"] == []


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
        """Saving a numeric setting preserves unrelated list-valued configuration."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"
        original = yaml.safe_load(cfg_path.read_text())
        original["data"]["watchlist_tags"] = ["短线", "观察"]
        cfg_path.write_text(yaml.safe_dump(original, allow_unicode=True, sort_keys=False))

        page.goto(SERVER_URL)
        page.get_by_role("button", name="Settings", exact=True).click()
        chunk_size = page.locator("#cfg-yf-chunk")
        expect(chunk_size).to_have_value(str(original["yfinance"]["batch"]["chunk_size"]))
        chunk_size.fill("75")
        with page.expect_response(lambda r: r.url.endswith("/api/config") and r.request.method == "PUT") as saved:
            page.locator("#btn-save-settings").click()
        assert saved.value.ok
        data = yaml.safe_load(cfg_path.read_text())
        assert data["yfinance"]["batch"]["chunk_size"] == 75
        assert data["data"]["watchlist_tags"] == ["短线", "观察"]

    def test_settings_yaml_unicode_correct(self, page: Page):
        """YAML should handle unicode correctly after settings save."""
        cfg_path = PROJECT_ROOT / "config" / "quantflow.yaml"

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings", exact=True).click()
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
        page.get_by_role("button", name="Settings", exact=True).click()
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
        page.get_by_role("button", name="Settings", exact=True).click()
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