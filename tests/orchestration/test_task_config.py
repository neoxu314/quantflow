"""Tests for the orchestration task configuration loader."""
import pytest

from quantflow.orchestration.loader import TaskConfig


class TestTaskConfigLoad:
    """Verify TaskConfig.load() YAML parsing behavior."""

    def _write_yaml(self, tmp_path, content):
        p = tmp_path / "tasks.yaml"
        p.write_text(content)
        return str(p)

    def test_load_single_task(self, tmp_path):
        """Parse a single task from YAML."""
        path = self._write_yaml(tmp_path, """\
tasks:
  - name: "US-Tech"
    watchlist: "watchlists/us_tech.yaml"
    strategies: [daily_bull_oversold]
    output: "output/us"
""")
        tasks = TaskConfig.load(path)
        assert len(tasks) == 1
        t = tasks[0]
        assert t.name == "US-Tech"
        assert t.watchlist_path == "watchlists/us_tech.yaml"
        assert t.strategy_names == ["daily_bull_oversold"]
        assert t.output_dir == "output/us"

    def test_load_multiple_tasks(self, tmp_path):
        """Parse multiple tasks in a single YAML."""
        path = self._write_yaml(tmp_path, """\
tasks:
  - name: "A-Shares"
    watchlist: "watchlists/a_value.yaml"
    strategies: [kdj_dead_cross]
    output: "output/a"
  - name: "HK-Tech"
    watchlist: "watchlists/hk_tech.yaml"
    strategies: [daily_bull_oversold, dual_line_bear]
    output: "output/hk"
""")
        tasks = TaskConfig.load(path)
        assert len(tasks) == 2
        assert tasks[0].name == "A-Shares"
        assert tasks[1].name == "HK-Tech"

    def test_default_strategies_is_empty_list(self, tmp_path):
        """Missing 'strategies' field defaults to []."""
        path = self._write_yaml(tmp_path, """\
tasks:
  - name: "No-Strategy"
    watchlist: "watchlists/djia.yaml"
    output: "output/default"
""")
        tasks = TaskConfig.load(path)
        assert tasks[0].strategy_names == []

    def test_default_output_is_dot_slash_output(self, tmp_path):
        """Missing 'output' field defaults to './output'."""
        path = self._write_yaml(tmp_path, """\
tasks:
  - name: "No-Output"
    watchlist: "watchlists/djia.yaml"
    strategies: [daily_bull_oversold]
""")
        tasks = TaskConfig.load(path)
        assert tasks[0].output_dir == "./output"

    def test_days_back_overridden(self, tmp_path):
        """Explicit 'days_back' is parsed."""
        path = self._write_yaml(tmp_path, """\
tasks:
  - name: "Custom-Lookback"
    watchlist: "watchlists/djia.yaml"
    strategies: [daily_bull_oversold]
    output: "output/x"
    days_back: 180
""")
        tasks = TaskConfig.load(path)
        assert tasks[0].days_back == 180

    def test_days_back_is_none_when_absent(self, tmp_path):
        """Missing 'days_back' field defaults to None."""
        path = self._write_yaml(tmp_path, """\
tasks:
  - name: "Auto-Lookback"
    watchlist: "watchlists/djia.yaml"
    strategies: [daily_bull_oversold]
    output: "output/x"
""")
        tasks = TaskConfig.load(path)
        assert tasks[0].days_back is None

    def test_missing_file_raises_file_not_found_error(self):
        """Non-existent YAML path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            TaskConfig.load("/nonexistent/tasks.yaml")

    def test_empty_tasks_list(self, tmp_path):
        """YAML with 'tasks: []' returns empty list."""
        path = self._write_yaml(tmp_path, "tasks: []\n")
        tasks = TaskConfig.load(path)
        assert tasks == []

    def test_missing_tasks_key(self, tmp_path):
        """YAML without 'tasks' key returns empty list."""
        path = self._write_yaml(tmp_path, "watchlist: x\n")
        tasks = TaskConfig.load(path)
        assert tasks == []

    def test_task_config_attributes(self):
        """TaskConfig stores all fields correctly."""
        cfg = TaskConfig(
            name="Test",
            watchlist_path="wl.yaml",
            strategy_names=["s1", "s2"],
            output_dir="out",
            days_back=100
        )
        assert cfg.name == "Test"
        assert cfg.watchlist_path == "wl.yaml"
        assert cfg.strategy_names == ["s1", "s2"]
        assert cfg.output_dir == "out"
        assert cfg.days_back == 100
