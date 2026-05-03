"""pytest configuration for web E2E tests."""
import pytest
from playwright.sync_api import Browser


@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Use the installed Chrome for Testing browser."""
    return {"headless": True, "channel": "chrome"}
