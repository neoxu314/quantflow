"""End-to-end browser automation tests for QuantFlow Web UI.

Uses Playwright (pytest-playwright) to simulate real user interactions:
- Clicking buttons, filling forms, switching tabs
- Verifying UI state changes and backend YAML file updates
- Testing data boundaries (cancel without save, unsaved changes)

Total: 48 E2E tests across 4 test files:
- test_web_ui.py: Basic UI navigation and operations (22 tests)
- test_data_boundary.py: Cancel/unsaved change scenarios (8 tests)
- test_yaml_sync.py: YAML file synchronization verification (11 tests)
- test_error_handling.py: Error and validation handling (7 tests)

Run with: pytest tests/web/e2e/ -v
"""