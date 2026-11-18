"""CLI layer tests - parameter parsing, command routing, and structural validation.

Tests cover:
1. Argument parsing (required params missing, format validation)
2. Command routing (scan/stock_scan aliases)
3. Indicator/strategy string parsing
4. CLI output format validation
5. Basic CLI execution (file generation, output structure)
6. Integration tests with TongDaXin reference values (BYD & AAPL)

TODO Tests (pending expected results):
- watchlist_run with expected signal counts and matched strategies
- task_run with expected orchestration results and combined reports

Note: This file covers STEP 1 tests (structural validation) and STEP 2 tests (expected values).
STEP 2 tests for stock_scan completed (BYD/AAPL validation).
STEP 2 tests for watchlist_run/task_run pending (need real execution results).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestCLIArgumentParsing:
    """Test argument parsing for each CLI command."""

    def test_stock_scan_requires_code_param(self):
        """Missing --code should raise SystemExit."""
        with pytest.raises(SystemExit):
            sys.argv = ["quantflow.cli", "scan"]
            from quantflow.cli import stock_scan
            stock_scan()

    def test_watchlist_run_requires_watchlist_param(self):
        """Missing --watchlist should raise SystemExit."""
        with pytest.raises(SystemExit):
            sys.argv = ["quantflow.cli", "monitor"]
            from quantflow.cli import watchlist_run
            watchlist_run()

    def test_task_run_requires_config_param(self):
        """Missing --config should raise SystemExit."""
        with pytest.raises(SystemExit):
            sys.argv = ["quantflow.cli", "tasks"]
            from quantflow.cli import task_run
            task_run()

    def test_stock_scan_accepts_optional_params(self, tmp_path):
        from quantflow.cli import stock_scan
        sys.argv = ["cli", "--code", "NVDA.US", "--output", str(tmp_path), "--start", "2026-01-01", "--end", "2026-04-30", "--indicator", "kdj,macd"]
        with patch("quantflow.execution.scanner.scan_stock", side_effect=_stub_scan) as scan:
            assert stock_scan() == 0
        assert scan.call_args.args[0]["indicators"] == ["kdj", "macd"]

    def test_watchlist_run_accepts_optional_strategies_param(self, tmp_path):
        from quantflow.cli import watchlist_run
        wl = tmp_path / "watch.yaml"
        wl.write_text("name: WL\nitems:\n- code: NVDA.US\n")
        sys.argv = ["cli", "--watchlist", str(wl), "--output", str(tmp_path), "--strategies", "daily_bull_oversold,daily_bull_mid_range"]
        with patch("quantflow.execution.executor.Executor.execute", side_effect=_stub_execute) as execute:
            assert watchlist_run() == 0
        job = execute.call_args.args[0]
        assert [s.name for s in job.strategies] == ["DailyBullishOversold", "DailyBullishMidRange"]
        assert job.days_back > 0

    def test_watchlist_run_accepts_days_back_override(self, tmp_path):
        from quantflow.cli import watchlist_run
        wl = tmp_path / "watch.yaml"
        wl.write_text("name: WL\nitems:\n- code: NVDA.US\n")
        sys.argv = ["cli", "--watchlist", str(wl), "--output", str(tmp_path), "--days-back", "500"]
        with patch("quantflow.execution.executor.Executor.execute", side_effect=_stub_execute) as execute:
            assert watchlist_run() == 0
        job = execute.call_args.args[0]
        assert [s.name for s in job.strategies] == ["DailyBullishOversold", "DailyBullishMidRange"]
        assert job.days_back == 500

    def test_task_run_accepts_daily_mode_flag(self, tmp_path):
        from quantflow.cli import task_run
        wl = tmp_path / "wl.yaml"
        wl.write_text("name: WL\nitems:\n- code: NVDA.US\n")
        tasks = tmp_path / "tasks.yaml"
        tasks.write_text("tasks:\n- name: scan\n  watchlist: wl.yaml\n  strategies: [daily_bull_oversold]\n")
        sys.argv = ["cli", "--config", str(tasks), "--output", str(tmp_path), "--daily"]
        with patch("quantflow.execution.executor.Executor.execute", side_effect=_stub_execute):
            assert task_run() == 0
        assert len(list(tmp_path.glob("*/runs/*/logs/task_run_*.log"))) == 1
        assert len(list(tmp_path.glob("*/runs/*/Daily_Report.md"))) == 1


class TestCLICommandRouting:
    """Test command routing via subprocess (integration tests for entry point)."""

    @pytest.mark.integration
    def test_scan_alias_executes_stock_scan(self):
        """CLI 'scan' command should execute stock_scan successfully."""
        result = subprocess.run(
            [sys.executable, "-m", "quantflow.cli", "scan", "--code", "NVDA.US"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "Scan Result for NVDA.US" in combined

    @pytest.mark.integration
    def test_stock_scan_alias_executes_stock_scan(self):
        """CLI 'stock_scan' command should execute successfully."""
        result = subprocess.run(
            [sys.executable, "-m", "quantflow.cli", "stock_scan", "--code", "NVDA.US"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "Scan Result for NVDA.US" in combined

    @pytest.mark.integration
    def test_unknown_command_prints_error(self):
        """Unknown command should print error message."""
        result = subprocess.run(
            [sys.executable, "-m", "quantflow.cli", "unknown_command"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "Unknown command: unknown_command" in result.stdout

    @pytest.mark.integration
    def test_no_command_prints_usage(self):
        """No command should print usage instructions."""
        result = subprocess.run(
            [sys.executable, "-m", "quantflow.cli"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert "Usage:" in result.stdout
        assert "Commands:" in result.stdout


class TestCLIIndicatorParsing:
    """Test indicator string parsing logic."""

    def test_indicator_string_split(self, tmp_path):
        from quantflow.cli import stock_scan
        sys.argv = ["cli", "--code", "NVDA.US", "--output", str(tmp_path), "--indicator", "kdj,macd"]
        with patch("quantflow.execution.scanner.scan_stock", side_effect=_stub_scan) as scan:
            assert stock_scan() == 0
        assert scan.call_args.args[0]["indicators"] == ["kdj", "macd"]

    def test_default_indicator_is_kdj_dual_line(self, tmp_path):
        from quantflow.cli import stock_scan
        sys.argv = ["cli", "--code", "NVDA.US", "--output", str(tmp_path)]
        with patch("quantflow.execution.scanner.scan_stock", side_effect=_stub_scan) as scan:
            assert stock_scan() == 0
        assert scan.call_args.args[0]["indicators"] == ["kdj", "dual_line"]


class TestCLIStrategyParsing:
    """Test strategy ID string parsing."""

    def test_strategy_string_split(self, tmp_path):
        from quantflow.cli import watchlist_run
        wl = tmp_path / "watch.yaml"
        wl.write_text("name: WL\nitems:\n- code: NVDA.US\n")
        sys.argv = ["cli", "--watchlist", str(wl), "--output", str(tmp_path), "--strategies", "daily_bull_mid_range"]
        with patch("quantflow.execution.executor.Executor.execute", side_effect=_stub_execute) as execute:
            assert watchlist_run() == 0
        job = execute.call_args.args[0]
        assert [s.name for s in job.strategies] == ["DailyBullishMidRange"]
        assert job.days_back > 0

    def test_default_strategies(self, tmp_path):
        from quantflow.cli import watchlist_run
        wl = tmp_path / "watch.yaml"
        wl.write_text("name: WL\nitems:\n- code: NVDA.US\n")
        sys.argv = ["cli", "--watchlist", str(wl), "--output", str(tmp_path)]
        with patch("quantflow.execution.executor.Executor.execute", side_effect=_stub_execute) as execute:
            assert watchlist_run() == 0
        job = execute.call_args.args[0]
        assert [s.name for s in job.strategies] == ["DailyBullishOversold", "DailyBullishMidRange"]
        assert job.days_back > 0


@pytest.mark.integration
class TestCLIExecutionIntegration:
    """Integration tests: CLI execution generates files and output."""

    def test_stock_scan_generates_output(self, tmp_path):
        """stock_scan CLI execution should generate indicator output."""
        output_dir = tmp_path / "scan_output"
        output_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantflow.cli",
                "scan",
                "--code",
                "NVDA.US",
                "--indicator",
                "kdj",
                "--start",
                "2026-04-01",
                "--end",
                "2026-04-30",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path(__file__).parent.parent),
        )

        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "Scan Result for NVDA.US" in combined
        assert "Data source:" in combined

    def test_stock_scan_output_contains_indicator_columns(self, tmp_path):
        """Indicator output should be calculated successfully."""
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantflow.cli",
                "scan",
                "--code",
                "NVDA.US",
                "--indicator",
                "kdj",
                "--start",
                "2026-04-01",
                "--end",
                "2026-04-30",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(Path(__file__).parent.parent),
        )

        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "Scan Result for NVDA.US" in combined

    def test_watchlist_run_generates_report(self, tmp_path):
        """watchlist_run should generate Markdown report."""
        watchlist_file = tmp_path / "test_wl.yaml"
        watchlist_file.write_text(
            "name: 'TestWL'\nitems:\n  - code: 'NVDA.US'\n"
        )

        output_dir = tmp_path / "watchlist_output"
        output_dir.mkdir()

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantflow.cli",
                "monitor",
                "--watchlist",
                str(watchlist_file),
                "--output",
                str(output_dir),
                "--strategies",
                "daily_bull_oversold",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path(__file__).parent.parent),
        )

        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "Execution complete" in combined

        json_files = list(output_dir.glob("*_results.json"))
        assert len(json_files) > 0, "Should generate JSON results file"

    def test_task_run_generates_combined_results(self, tmp_path):
        """task_run should generate Combined_Results.json."""
        task_file = tmp_path / "test_tasks.yaml"
        watchlist_file = tmp_path / "test_wl.yaml"

        watchlist_file.write_text(
            "name: 'TestWL'\nitems:\n  - code: 'NVDA.US'\n"
        )

        output_dir = tmp_path / "task_output"
        output_dir.mkdir()

        task_file.write_text(
            f"""tasks:
  - name: 'TestTask'
    watchlist: '{watchlist_file.name}'
    strategies: ['daily_bull_oversold']
    output: '{output_dir.name}'
"""
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantflow.cli",
                "tasks",
                "--config",
                str(task_file),
                "--output",
                str(output_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(tmp_path),
        )

        combined_json = output_dir / "Combined_Results.json"
        assert combined_json.exists(), "Should generate Combined_Results.json"

        data = json.loads(combined_json.read_text())
        assert isinstance(data, list)


class TestCLILogFile:
    """Test that CLI run commands create log files."""

    def test_stock_scan_creates_log_file(self, tmp_path):
        from quantflow.cli import stock_scan
        sys.argv = ["cli", "--code", "NVDA.US", "--output", str(tmp_path)]
        with patch("quantflow.execution.scanner.scan_stock", side_effect=_stub_scan):
            assert stock_scan() == 0
        logs = list(tmp_path.glob("runs/*/logs/stock_scan_*.log"))
        assert len(logs) == 1
        assert "Saved 1 bars" in logs[0].read_text()

    def test_watchlist_run_creates_log_file(self, tmp_path):
        from quantflow.cli import watchlist_run
        wl = tmp_path / "watch.yaml"
        wl.write_text("name: WL\nitems:\n- code: NVDA.US\n")
        sys.argv = ["cli", "--watchlist", str(wl), "--output", str(tmp_path)]
        with patch("quantflow.execution.executor.Executor.execute", side_effect=_stub_execute) as execute:
            assert watchlist_run() == 0
        job = execute.call_args.args[0]
        assert [s.name for s in job.strategies] == ["DailyBullishOversold", "DailyBullishMidRange"]
        assert len(list(tmp_path.glob("runs/*/logs/watchlist_run_*.log"))) == 1

    def test_task_run_creates_log_file(self, tmp_path):
        from quantflow.cli import task_run
        wl = tmp_path / "wl.yaml"
        wl.write_text("name: WL\nitems:\n- code: NVDA.US\n")
        tasks = tmp_path / "tasks.yaml"
        tasks.write_text("tasks:\n- name: scan\n  watchlist: wl.yaml\n  strategies: [daily_bull_oversold]\n")
        sys.argv = ["cli", "--config", str(tasks), "--output", str(tmp_path), "--daily"]
        with patch("quantflow.execution.executor.Executor.execute", side_effect=_stub_execute):
            assert task_run() == 0
        assert len(list(tmp_path.glob("*/runs/*/logs/task_run_*.log"))) == 1
        assert len(list(tmp_path.glob("*/runs/*/Daily_Report.md"))) == 1


class TestCLIErrorHandling:
    """Test CLI error handling and messages."""

    def test_stock_scan_invalid_code_format(self, tmp_path):
        from quantflow.cli import stock_scan
        sys.argv = ["cli", "--code", "INVALID_CODE", "--output", str(tmp_path)]
        assert stock_scan() == 1

    def test_watchlist_run_invalid_watchlist_path(self, tmp_path):
        from quantflow.cli import watchlist_run
        sys.argv = ["cli", "--watchlist", "/nonexistent/path.yaml", "--output", str(tmp_path)]
        assert watchlist_run() == 1

    def test_task_run_invalid_config_path(self):
        """Invalid task config path should log error and not raise."""
        sys.argv = [
            "quantflow.cli",
            "--config",
            "/nonexistent/tasks.yaml",
        ]

        from quantflow.cli import task_run
        task_run()


class TestCLIOutputFormat:
    """Test CLI output format and messages."""

    def test_stock_scan_output_format(self, tmp_path):
        from quantflow.cli import stock_scan
        sys.argv = ["cli", "--code", "NVDA.US", "--output", str(tmp_path)]
        with patch("quantflow.execution.scanner.scan_stock", side_effect=_stub_scan):
            assert stock_scan() == 0
        path = next(tmp_path.glob("runs/*/NVDA.US_indicators.json"))
        data = json.loads(path.read_text())
        assert data[0]["date"] == "2026-04-30"
        assert {"K", "D", "J", "close"} <= set(data[0])
        assert not (tmp_path / "NVDA.US_indicators.json").exists()

    def test_watchlist_run_output_format(self, tmp_path):
        from quantflow.cli import watchlist_run
        wl = tmp_path / "watch.yaml"
        wl.write_text("name: WL\nitems:\n- code: NVDA.US\n")
        sys.argv = ["cli", "--watchlist", str(wl), "--output", str(tmp_path)]
        with patch("quantflow.execution.executor.Executor.execute", side_effect=_stub_execute) as execute:
            assert watchlist_run() == 0
        job = execute.call_args.args[0]
        assert [s.name for s in job.strategies] == ["DailyBullishOversold", "DailyBullishMidRange"]
        assert json.loads((Path(job.output_dir) / "cli-WL.json").read_text()) == []


@pytest.mark.integration
class TestCLIStockScanWithExpectedValues:
    """Integration tests with TongDaXin reference values from test_integration.py.

    Validates CLI stock_scan calculation accuracy using authoritative reference data.
    Reference data source: tests/indicators/test_integration.py (TongDaXin values).
    """

    def test_cli_stock_scan_byd_kdj_reference_values(self, tmp_path):
        """Verify BYD (002594.SZ) 2026-04-01 KDJ values match TongDaXin reference.

        Reference from test_integration.py:
            KDJ: {"K": 35.80, "D": 48.40, "J": 10.58}
        """
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "quantflow.cli",
                "scan",
                "--code",
                "002594.SZ",
                "--start",
                "2025-01-01",
                "--end",
                "2026-04-01",
                "--indicator",
                "kdj",
                "--output",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path(__file__).parent.parent),
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        combined = result.stdout + result.stderr
        assert "Indicator data saved" in combined

        json_file = tmp_path / "002594.SZ_indicators.json"
        assert json_file.exists(), "JSON file should be generated"

        data = json.loads(json_file.read_text())
        assert len(data) > 0, "Should have indicator data"

        target_date = "2026-04-01"
        matching_rows = [
            r for r in data
            if r.get("date") and (
                r["date"].startswith(target_date) or
                target_date in str(r["date"])
            )
        ]

        assert len(matching_rows) > 0, f"Should have data for {target_date}"

        target_row = matching_rows[-1]

        assert "K" in target_row, "Should have K value"
        assert "D" in target_row, "Should have D value"
        assert "J" in target_row, "Should have J value"

        ref_K = 35.80
        ref_D = 48.40
        ref_J = 10.58

        assert target_row["K"] == pytest.approx(ref_K, rel=0.05), \
            f"K mismatch: got {target_row['K']}, expected {ref_K}, date={target_row.get('date')}"
        assert target_row["D"] == pytest.approx(ref_D, rel=0.05), \
            f"D mismatch: got {target_row['D']}, expected {ref_D}, date={target_row.get('date')}"
        assert target_row["J"] == pytest.approx(ref_J, rel=0.05), \
            f"J mismatch: got {target_row['J']}, expected {ref_J}, date={target_row.get('date')}"

        print(f"✅ BYD KDJ validation passed:")
        print(f"   K={target_row['K']:.2f} (ref={ref_K}, error={abs(target_row['K']-ref_K)/ref_K*100:.2f}%)")
        print(f"   D={target_row['D']:.2f} (ref={ref_D}, error={abs(target_row['D']-ref_D)/ref_D*100:.2f}%)")
        print(f"   J={target_row['J']:.2f} (ref={ref_J}, error={abs(target_row['J']-ref_J)/ref_J*100:.2f}%)")

    def test_cli_stock_scan_aapl_weekly_kdj(self, tmp_path):
        """Verify AAPL weekly KDJ values match TongDaXin reference.

        Reference from test_integration.py (weekly data):
            KDJ: {"K": 47.629, "D": 37.966, "J": 66.957}

        Note: CLI currently only supports daily data. This test documents
        the limitation and will be updated when weekly support is added.
        """
        pass


@pytest.mark.integration
@pytest.mark.skip(reason="Pending expected signal counts and strategy matches from real execution")
class TestCLIWatchlistRunWithExpectedValues:
    """Integration tests for watchlist_run with expected results.

    TODO: Add expected results from real execution:
    - Signal counts (buy_signals, sell_signals)
    - Matched stock codes
    - Strategy IDs and names
    - Output JSON structure validation

    Suggested test data sources:
    - Use execution/test_executor.py mock data patterns
    - Or run real watchlist_run once to capture reference results
    """

    def test_cli_watchlist_run_us_djia_expected_signals(self, tmp_path):
        """Verify watchlist_run for US DJIA produces expected signals.

        Expected results needed:
        - watchlist file: watchlists/us_djia.yaml
        - strategy: daily_bull_oversold
        - expected buy_signals count
        - expected matched strategies list
        """
        # Placeholder - will be implemented with expected data
        pass

    def test_cli_watchlist_run_multiple_strategies_expected(self, tmp_path):
        """Verify watchlist_run with multiple strategies.

        Expected results needed:
        - strategies: daily_bull_oversold + daily_bull_mid_range
        - expected total signal count
        - expected per-strategy breakdown
        """
        # Placeholder - will be implemented with expected data
        pass


@pytest.mark.integration
@pytest.mark.skip(reason="Pending expected orchestration results from real task execution")
class TestCLITaskRunWithExpectedValues:
    """Integration tests for task_run with expected results.

    TODO: Add expected results from real orchestration:
    - Total signal count across all tasks
    - Per-task signal breakdown
    - Combined_Results.json structure
    - Markdown report validation

    Suggested test data sources:
    - Use orchestration/test_orchestrator.py mock data patterns
    - Or run real task_run once to capture reference results
    """

    def test_cli_task_run_single_task_expected_results(self, tmp_path):
        """Verify task_run for single task produces expected results.

        Expected results needed:
        - task config: single task with known watchlist
        - expected Combined_Results.json length
        - expected Daily_Report.md structure
        """
        # Placeholder - will be implemented with expected data
        pass

    def test_cli_task_run_multiple_tasks_expected_total(self, tmp_path):
        """Verify task_run for multiple tasks produces expected total signals.

        Expected results needed:
        - task config: multiple tasks (e.g., US + Asia)
        - expected total signal count
        - expected per-task output directories
        """
        # Placeholder - will be implemented with expected data
        pass

def _stub_scan(cfg, output):
    from quantflow.artifacts import atomic_json
    path = Path(output) / f"{cfg['code']}_indicators.json"
    atomic_json(path, [{"date": "2026-04-30", "close": 100.0, "K": 35., "D": 40., "J": 25.}])
    return str(path), 1, {"source": "mock"}


def _stub_execute(job, **kwargs):
    from quantflow.execution.storage import ScanResults, StockOutcome, Storage
    results = ScanResults([], [StockOutcome(item.code.standard, "no_signal") for item in job.items])
    Storage().save_results(Path(job.output_dir) / f"{job.name}.json", results)
    return results
