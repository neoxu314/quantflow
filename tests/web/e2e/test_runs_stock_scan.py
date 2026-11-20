"""A stock scan through the browser, the real worker and the saved report."""

from playwright.sync_api import expect

from .run_helpers import (
    SCAN,
    open_new_run,
    open_run_tab,
    open_runs,
    select_run,
    submit_run,
    wait_run,
)


def test_stock_scan_full_lifecycle(page, client, e2e_url):
    open_runs(page, e2e_url)
    open_new_run(page, "stock_scan")
    for field, key in (
        ("stock-code", "code"),
        ("start-date", "start_date"),
        ("end-date", "end_date"),
    ):
        page.locator(f"#run-{field}").fill(SCAN[key])
    expect(page.locator("#run-cli-preview")).to_contain_text("--start 2025-06-03 --end 2025-06-04")
    run_id = submit_run(page, e2e_url)
    assert wait_run(client, run_id)["signal_count"] == 2

    open_runs(page, e2e_url)
    select_run(page, run_id, "completed")
    report = open_run_tab(page, "report")
    expect(report).to_contain_text("Total bars: 2")
    expect(report.get_by_role("row").nth(1)).to_contain_text("2025-06-04")
    expect(report.get_by_role("row").nth(1)).to_contain_text("139.5000")
    files = open_run_tab(page, "files")
    for name in ("AAPL.US_indicators.json", "AAPL.US_context.json", "AAPL.US_snapshot.json"):
        expect(files.get_by_role("cell", name=name, exact=True)).to_be_visible()


def test_new_run_reopens_at_type_selection(page, e2e_url):
    open_runs(page, e2e_url)
    open_new_run(page, "stock_scan")
    page.locator("#run-stock-code").fill("AAPL.US")
    page.locator("#btn-cancel-run").click()
    page.locator("#btn-new-run").click()
    expect(page.locator("#run-step-type")).to_be_visible()
    expect(page.locator("#run-config-stock_scan")).to_be_hidden()
