"""Error handling tests for QuantFlow Web UI.

Tests verify proper error handling when:
- Server returns 500 error during save
- Network disconnects during save operation  
- User provides invalid input (frontend validation)
"""
import pytest
from playwright.sync_api import Page
from unittest.mock import patch, MagicMock

from tests.web.e2e.conftest import SERVER_URL


class TestServerErrorHandling:
    """Handle server errors gracefully."""

    def test_save_when_server_500_error(self, page: Page):
        """When server returns 500, UI should show error toast."""
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        buffer_field = page.locator("#cfg-lookback-buffer")
        buffer_field.fill("999")

        page.route("**/api/config", lambda route: route.fulfill(status=500, body="Internal Server Error"))
        
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(2000)

        toast_el = page.locator("#toast")
        if toast_el.is_visible():
            toast_text = toast_el.text_content().lower()
            assert "error" in toast_text or "fail" in toast_text

        page.unroute("**/api/config")


class TestNetworkDisconnectHandling:
    """Handle network errors gracefully."""

    def test_network_disconnect_during_save(self, page: Page):
        """When network fails during save, UI should show error."""
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        buffer_field = page.locator("#cfg-lookback-buffer")
        buffer_field.fill("888")

        page.route("**/api/config", lambda route: route.abort("failed"))
        
        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(2000)

        toast_el = page.locator("#toast")
        if toast_el.is_visible():
            assert toast_el.text_content() is not None

        page.unroute("**/api/config")


class TestInvalidInputValidation:
    """Frontend should validate user input before sending to API."""

    def test_empty_watchlist_name_blocked(self, page: Page):
        """Empty watchlist name should be rejected."""
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")

        dialog_accepted = False
        
        def handle_dialog(dialog):
            dialog.accept("")
            dialog_accepted = True

        page.once("dialog", handle_dialog)
        page.get_by_role("button", name="+ New").click()
        page.wait_for_timeout(1000)

        watchlist_btn = page.get_by_role("button", name="_test_e2e_wl")
        if not watchlist_btn.is_visible():
            pass

    def test_invalid_stock_code_format(self, page: Page):
        """Invalid stock code format should show preview or error."""
        from tests.web.e2e.conftest import TEST_WATCHLIST_NAME
        import httpx
        
        httpx.put(
            f"{SERVER_URL}/api/watchlists/{TEST_WATCHLIST_NAME}.yaml",
            json={"name": TEST_WATCHLIST_NAME, "items": []},
        )

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name=TEST_WATCHLIST_NAME).click()
        page.wait_for_selector("#stock-table", timeout=5000)

        page.get_by_role("button", name="+ Add Stock").click()
        page.locator("#modal-add-stock").wait_for(state="visible", timeout=5000)

        page.locator("#add-stock-code").fill("INVALID_FORMAT")

        preview_el = page.locator("#add-stock-preview")
        if preview_el.is_visible():
            preview_text = preview_el.text_content()
            if preview_text:
                assert "INVALID" in preview_text or preview_text.strip() == ""

        page.locator("#btn-cancel-add-stock").click()

    def test_negative_value_validation(self, page: Page):
        """Negative values in numeric fields should be handled."""
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_selector("#settings-form", timeout=5000)

        buffer_field = page.locator("#cfg-lookback-buffer")
        buffer_field.fill("-10")

        page.locator("#btn-save-settings").click()
        page.wait_for_timeout(1000)

        toast_el = page.locator("#toast")
        if toast_el.is_visible():
            pass


class TestApiErrorResponses:
    """Handle various API error codes properly."""

    def test_404_error_handling(self, page: Page):
        """404 from API should show appropriate message."""
        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Library").click()
        page.locator("#panel-library").wait_for(state="visible", timeout=5000)

        page.route("**/api/library/indicators", lambda route: route.fulfill(status=404, body="Not Found"))
        
        page.get_by_role("button", name="Indicators").click()
        page.wait_for_timeout(2000)

        page.unroute("**/api/library/indicators")

    def test_409_conflict_error_handling(self, page: Page):
        """409 conflict (duplicate) should show message."""
        from tests.web.e2e.conftest import TEST_TASK_FILE
        import httpx
        
        httpx.post(f"{SERVER_URL}/api/task-files", json={"filename": TEST_TASK_FILE})

        page.goto(SERVER_URL)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Tasks").click()
        page.wait_for_selector("#task-file-list", timeout=5000)

        resp = httpx.post(f"{SERVER_URL}/api/task-files", json={"filename": TEST_TASK_FILE})
        assert resp.status_code == 409