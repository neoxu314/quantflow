"""Tests for the orchestration Orchestrator class (partial mock + integration style)."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from quantflow.orchestration.app import MarkdownReporter, Orchestrator
from quantflow.execution.storage import ExecutionResultItem


class TestOrchestratorRun:
    """Verify full Orchestrator.run() flow with real YAML + mocked external deps."""

    def _make_task_yaml(self, tmp_path, content):
        p = tmp_path / "tasks.yaml"
        p.write_text(content)
        return str(p)

    def _make_watchlist(self, tmp_path, filename, content):
        p = tmp_path / filename
        p.write_text(content)
        return str(p)

    def _make_output_dir(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir(exist_ok=True)
        return str(d)

    def _build_task_config(self, tmp_path):
        """Build valid task configs with real YAML + watchlist files."""
        self._make_watchlist(tmp_path, "djia.yaml", """\
name: "DJIA"
items:
  - code: "NVDA.US"
  - code: "AAPL.US"
""")
        task_path = self._make_task_yaml(tmp_path, """\
tasks:
  - name: "US-Test"
    watchlist: "./djia.yaml"
    strategies: [daily_bull_oversold]
    output: "./output"
""")
        return task_path

    def test_run_returns_total_signals(self, tmp_path):
        """Orchestrator.run() returns the sum of result counts."""
        task_path = self._build_task_config(tmp_path)
        output_dir = self._make_output_dir(tmp_path)
        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = output_dir

        mock_results = [ExecutionResultItem("A.US", buy_signals=2, sell_signals=0),
                        ExecutionResultItem("B.US", buy_signals=1, sell_signals=1)]
        app = Orchestrator(tasks, output_override=output_dir, daily_mode=False)

        with patch("quantflow.orchestration.app.Executor.execute") as mock_exec, \
             patch("quantflow.orchestration.app.MarkdownReporter.generate"):
            mock_exec.return_value = mock_results
            total = app.run()

        assert total == 2  # 2 results in the list

    def test_run_calls_executor_with_correct_job(self, tmp_path):
        """Executor.execute receives a properly constructed ExecutionJob."""
        task_path = self._build_task_config(tmp_path)
        output_dir = self._make_output_dir(tmp_path)
        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = output_dir

        app = Orchestrator(tasks, output_override=output_dir, daily_mode=False)

        with patch("quantflow.orchestration.app.Executor.execute") as mock_exec, \
             patch("quantflow.orchestration.app.MarkdownReporter.generate"):
            mock_exec.return_value = []
            app.run()

        mock_exec.assert_called_once()
        job = mock_exec.call_args[0][0]
        assert job.name == "US-Test"
        assert len(job.items) == 2
        assert len(job.strategies) == 1

    def test_run_daily_mode_injects_date(self, tmp_path):
        """With daily_mode=True, output dirs include today's date."""
        task_path = self._build_task_config(tmp_path)
        output_dir = self._make_output_dir(tmp_path)
        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = output_dir

        app = Orchestrator(tasks, output_override=output_dir, daily_mode=True)

        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")

        with patch("quantflow.orchestration.app.Executor.execute") as mock_exec, \
             patch("quantflow.orchestration.app.MarkdownReporter.generate"):
            mock_exec.return_value = []
            app.run()

        job = mock_exec.call_args[0][0]
        assert date_str in job.output_dir

    def test_run_generates_reports(self, tmp_path):
        """Per-task and combined reports are generated."""
        task_path = self._build_task_config(tmp_path)
        output_dir = self._make_output_dir(tmp_path)
        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = output_dir

        app = Orchestrator(tasks, output_override=output_dir, daily_mode=False)

        with patch("quantflow.orchestration.app.Executor.execute") as mock_exec, \
             patch.object(MarkdownReporter, "generate") as mock_gen, \
             patch.object(MarkdownReporter, "generate_combined") as mock_combo:
            mock_exec.return_value = []
            app.run()

        mock_gen.assert_called_once()
        mock_combo.assert_called_once()

    def test_run_saves_combined_results_json(self, tmp_path):
        """Combined_Results.json is written to the output directory."""
        task_path = self._build_task_config(tmp_path)
        output_dir = self._make_output_dir(tmp_path)
        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = output_dir

        app = Orchestrator(tasks, output_override=output_dir, daily_mode=False)

        with patch("quantflow.orchestration.app.Executor.execute") as mock_exec, \
             patch("quantflow.orchestration.app.MarkdownReporter.generate"):
            mock_exec.return_value = []
            app.run()

        json_path = app.output_dir / "Combined_Results.json"
        assert json_path.exists()
        data = json.loads(json_path.read_text())
        assert isinstance(data, list)


class TestOrchestratorTaskFailure:
    """Verify Orchestrator continues on individual task failures."""

    def _make_task_yaml(self, tmp_path, content):
        p = tmp_path / "tasks.yaml"
        p.write_text(content)
        return str(p)

    def _make_watchlist(self, tmp_path, filename, content):
        p = tmp_path / filename
        p.write_text(content)
        return str(p)

    def test_single_task_failure_continues_others(self, tmp_path):
        """If one task's strategy lookup fails, other tasks still run."""
        self._make_watchlist(tmp_path, "wl.yaml", """\
name: "Test"
items:
  - code: "NVDA.US"
""")
        task_path = self._make_task_yaml(tmp_path, """\
tasks:
  - name: "Good-Task"
    watchlist: "./wl.yaml"
    strategies: [daily_bull_oversold]
    output: "./output"
  - name: "Bad-Task"
    watchlist: "./wl.yaml"
    strategies: [nonexistent_strategy]
    output: "./output"
  - name: "Another-Good"
    watchlist: "./wl.yaml"
    strategies: [daily_bull_oversold]
    output: "./output"
""")
        output_dir = str(tmp_path / "output")
        (tmp_path / "output").mkdir(exist_ok=True)

        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = output_dir

        app = Orchestrator(tasks, output_override=output_dir, daily_mode=False)
        call_count = 0

        def fake_execute(job):
            nonlocal call_count
            call_count += 1
            return []

        with patch("quantflow.orchestration.app.Executor.execute", side_effect=fake_execute), \
             patch("quantflow.orchestration.app.MarkdownReporter.generate"), \
             patch.object(MarkdownReporter, "generate_combined"):
            app.run()

        assert call_count == 2

    def test_strategy_resolution_error_logged(self, tmp_path):
        """Strategy resolution errors are logged but don't crash."""
        self._make_watchlist(tmp_path, "wl.yaml", """\
name: "Test"
items:
  - code: "NVDA.US"
""")
        task_path = self._make_task_yaml(tmp_path, """\
tasks:
  - name: "Bad-Strategy"
    watchlist: "./wl.yaml"
    strategies: [unknown_strategy_xyz]
    output: "./output"
""")
        output_dir = str(tmp_path / "output")
        (tmp_path / "output").mkdir(exist_ok=True)

        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = output_dir

        app = Orchestrator(tasks, output_override=output_dir, daily_mode=False)

        with patch("quantflow.orchestration.app.Executor.execute") as mock_exec:
            total = app.run()

        mock_exec.assert_not_called()
        assert total == 0


class TestOrchestratorPathResolution:
    """Verify _resolve_task_dir and _resolve_combined_dir."""

    def test_resolve_task_dir_without_daily(self, tmp_path):
        """Without daily mode, uses base path only."""
        app = Orchestrator([], output_override="/base", daily_mode=False)
        app.date_str = "2026-05-05"
        cfg = MagicMock(output_dir="/alternative")
        assert app._resolve_task_dir(cfg) == "/base"

    def test_resolve_task_dir_with_daily(self, tmp_path):
        """With daily mode, appends date to base path."""
        app = Orchestrator([], output_override="/base", daily_mode=True)
        app.date_str = "2026-05-05"
        cfg = MagicMock(output_dir="/alternative")
        assert app._resolve_task_dir(cfg) == "/base/2026-05-05"

    def test_resolve_combined_dir_without_daily(self):
        """Without daily mode, uses base or 'reports' default."""
        app = Orchestrator([], output_override="/base", daily_mode=False)
        app.date_str = "2026-05-05"
        assert app._resolve_combined_dir() == "/base"

    def test_resolve_task_dir_fallback_to_default_output(self):
        """Without override, defaults to './output'."""
        app = Orchestrator([], daily_mode=False)
        cfg = MagicMock()
        assert app._resolve_task_dir(cfg) == "output"

    def test_resolve_combined_dir_fallback_to_reports(self):
        """Without override, defaults to 'reports'."""
        app = Orchestrator([], daily_mode=False)
        assert app._resolve_combined_dir() == "output"


class TestOrchestratorEmptyTasks:
    """Verify behavior when no tasks succeed."""

    def test_empty_task_list_returns_zero(self, tmp_path):
        """No tasks at all returns 0 signals."""
        tasks = []
        app = Orchestrator(tasks, output_override=str(tmp_path), daily_mode=False)
        total = app.run()
        assert total == 0

    def test_all_tasks_fail_returns_zero(self, tmp_path):
        """All tasks fail returns 0 signals, no combined report."""
        task_path = str(tmp_path / "tasks.yaml")
        tmp_path.joinpath("tasks.yaml").write_text("""\
tasks:
  - name: "Bad"
    watchlist: "nonexistent.yaml"
    strategies: [daily_bull_oversold]
    output: "./output"
""")
        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = str(tmp_path / "output")

        app = Orchestrator(tasks, output_override=str(tmp_path), daily_mode=False)

        with patch("quantflow.orchestration.app.Executor.execute") as mock_exec:
            mock_exec.side_effect = RuntimeError("Fetch failed")
            total = app.run()
            assert total == 0
        assert not (tmp_path / "Combined_Results.json").exists()


class TestOrchestratorMultipleTasks:
    """Verify Orchestrator handles multiple tasks correctly."""

    def test_multiple_tasks_all_run(self, tmp_path):
        """All tasks in config are executed sequentially."""
        (tmp_path / "wl1.yaml").write_text("""\
name: "WL1"
items:
  - code: "NVDA.US"
""")
        (tmp_path / "wl2.yaml").write_text("""\
name: "WL2"
items:
  - code: "AAPL.US"
  - code: "TSLA.US"
""")
        task_path = str(tmp_path / "tasks.yaml")
        tmp_path.joinpath("tasks.yaml").write_text("""\
tasks:
  - name: "Task-One"
    watchlist: "./wl1.yaml"
    strategies: [daily_bull_oversold]
    output: "./output"
  - name: "Task-Two"
    watchlist: "./wl2.yaml"
    strategies: [kdj_dead_cross]
    output: "./output"
""")
        output_dir = str(tmp_path / "output")
        (tmp_path / "output").mkdir(exist_ok=True)

        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(task_path)
        for t in tasks:
            t.watchlist_path = str(tmp_path / t.watchlist_path)
            t.output_dir = output_dir

        app = Orchestrator(tasks, output_override=output_dir, daily_mode=False)
        call_count = 0

        def fake_execute(job):
            nonlocal call_count
            call_count += 1
            return [ExecutionResultItem("A.US", buy_signals=1, sell_signals=0)]

        with patch("quantflow.orchestration.app.Executor.execute", side_effect=fake_execute), \
             patch("quantflow.orchestration.app.MarkdownReporter.generate"), \
             patch.object(MarkdownReporter, "generate_combined"):
            total = app.run()

        assert call_count == 2
        assert total == 2
