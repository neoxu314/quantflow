"""Task creation, daily archiving, log output and per-run artifacts."""

from datetime import date
from pathlib import Path

import pytest
from playwright.sync_api import expect

from .run_helpers import (
    open_new_run,
    open_run_tab,
    open_runs,
    result,
    select_run,
    start_scan,
    submit_run,
    wait_run,
)


@pytest.mark.parametrize("daily", [False, True])
def test_task_run_reports_expected_signal_and_owned_files(page, client, e2e_url, tmp_path, daily):
    base = tmp_path / "runs-output"
    open_runs(page, e2e_url)
    open_new_run(page, "task_run")
    page.locator("#run-task-config-select").select_option("config/tasks_test.yaml")
    page.locator("#run-daily-mode").set_checked(daily)
    page.locator("#run-output-path").fill(str(base))
    preview = page.locator("#run-cli-preview")
    expect(preview).to_contain_text("tasks --config config/tasks_test.yaml")
    if daily:
        expect(preview).to_contain_text("--daily")
    run_id = submit_run(page, e2e_url)
    run = wait_run(client, run_id)
    assert run["signal_count"] == 1
    output = Path(run["output_path"])
    assert output.name == run_id and output.parent.name == "runs"
    prefix = output.parent.parent
    if daily:
        assert str(date.fromisoformat(prefix.name)) == prefix.name
        assert prefix.parent == base
    else:
        assert prefix == base

    select_run(page, run_id, "completed")
    report = open_run_tab(page, "report")
    expect(report).to_contain_text("Oversold J=4.4 in bull channel")
    files = open_run_tab(page, "files")
    for filename in ("Daily_Report.md", "Combined_Results.json", "tasks/0001/report.md"):
        expect(files.get_by_role("cell", name=filename, exact=True)).to_be_visible()
    progress = open_run_tab(page, "progress")
    expect(progress.locator("#run-log-container")).to_contain_text("Task djia:")


def test_same_scan_output_base_keeps_run_files_separate(client, tmp_path):
    first_id = start_scan(client, output_path=str(tmp_path))
    first = wait_run(client, first_id)
    first_file = Path(first["report_path"])
    first_data = first_file.read_bytes()
    second_id = start_scan(client, output_path=str(tmp_path), start_date="2025-06-04")
    second = wait_run(client, second_id)
    assert first_id != second_id
    assert (first["signal_count"], second["signal_count"]) == (2, 1)
    assert Path(second["report_path"]) != first_file
    assert result(client.delete(f"/api/runs/{second_id}"))["ok"]
    assert first_file.read_bytes() == first_data
    assert not Path(second["report_path"]).exists()
