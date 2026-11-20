"""Cover the complete browser path through batch import and folder selection."""

from playwright.sync_api import expect

from .run_helpers import open_new_run, open_runs, result


def test_batch_import_is_saved_only_after_confirmation(page, client, e2e_url):
    page.goto(e2e_url)
    page.locator('#watchlist-list .watchlist-item[data-filename="djia.yaml"]').click()
    expect(page.locator("#stock-table")).to_contain_text("AAPL.US")
    page.locator("#btn-batch-import").click()
    page.locator("#batch-input").fill("MSFT.US Microsoft\n0700.HK 腾讯")
    page.locator("#btn-confirm-batch").click()
    table = page.locator("#stock-table")
    expect(table).to_contain_text("MSFT.US")
    expect(table).to_contain_text("0700.HK")
    path = "/api/watchlists/djia.yaml"
    assert [item["code"] for item in result(client.get(path))["items"]] == ["AAPL.US"]

    with page.expect_response(
        lambda r: r.url == f"{e2e_url}{path}" and r.request.method == "PUT"
    ) as saved:
        page.locator("#btn-save-watchlist").click()
    assert saved.value.ok
    assert [(item["code"], item["name"]) for item in result(client.get(path))["items"]][1:] == [
        ("MSFT.US", "Microsoft"), ("0700.HK", "腾讯"),
    ]


def test_run_folder_picker_creates_selects_and_cancels(page, e2e_url, tmp_path):
    open_runs(page, e2e_url)
    open_new_run(page, "stock_scan")
    output = page.locator("#run-output-path")
    output.fill(str(tmp_path))
    page.locator("#btn-browse-dir").click()
    expect(page.locator("#browse-current-path")).to_contain_text(tmp_path.name)
    page.locator("#btn-browse-new").click()
    page.locator("#browse-new-folder-name").fill("acceptance")
    page.locator("#btn-browse-new-ok").click()
    page.locator('#browse-list [data-name="acceptance"]').dblclick()
    expect(page.locator("#browse-current-path")).to_contain_text("acceptance")
    page.locator("#btn-browse-select").click()
    assert (tmp_path / "acceptance").is_dir()
    expect(output).to_have_value(str(tmp_path / "acceptance"))

    page.locator("#btn-browse-dir").click()
    page.locator("#btn-browse-up").click()
    expect(page.locator("#browse-current-path")).to_contain_text(tmp_path.name)
    page.locator("#btn-browse-cancel").click()
    expect(output).to_have_value(str(tmp_path / "acceptance"))
