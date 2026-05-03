"""Web module tests for QuantFlow.

Three test layers:
1. API tests (test_*_api.py): Unit tests using FastAPI TestClient + tmp_path
2. Integration tests (test_integration.py): API→filesystem→API round-trip
3. E2E browser tests (e2e/): Playwright browser automation

Production safety:
- API/Integration tests: Use tmp_path, never touch production files
- E2E tests: Backup/restore mechanism for quantflow.yaml and indicators.yaml

See AGENTS.md for detailed structure and running instructions.
"""