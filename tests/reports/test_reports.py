from pathlib import Path
from unittest.mock import MagicMock

import pytest

from quantflow.execution.storage import ExecutionResultItem
from quantflow.execution.watchlist import Watchlist
from quantflow.reports.markdown import MarkdownReporter


class TestMarkdownReporterGrouping:
    """Verify signal grouping logic in MarkdownReporter."""

    @pytest.fixture
    def reporter(self):
        return MarkdownReporter()

    @pytest.fixture
    def temp_watchlist(self, tmp_path):
        wl_path = tmp_path / "test_wl.yaml"
        wl_path.write_text(
            "name: TestWatchlist\n"
            "items:\n"
            "  - code: AAPL.US\n"
            "    name: Apple Inc.\n"
            "    tags: [tech, large-cap]\n"
            "  - code: TSLA.US\n"
            "    name: Tesla Inc.\n"
            "    tags: [ev]\n"
            "  - code: 600519.SH\n"
            "    name: Kweichow Moutai\n"
            "    tags: [cn, liquor]\n"
        )
        return Watchlist.load(str(wl_path))

    @pytest.fixture
    def mock_strategies(self):
        s1 = MagicMock()
        s1.name = "daily_bull_oversold"
        s2 = MagicMock()
        s2.name = "daily_bull_mid_range"
        return [s1, s2]

    def test_complete_report_structure(self, reporter, temp_watchlist, mock_strategies):
        """Full report: resonance grouping, single strategy, sell signal, name display."""
        item_resonance = ExecutionResultItem(
            code="AAPL.US",
            name="Apple",
            buy_signals=2,
            sell_signals=0,
            reasons=["Oversold J < 20", "Price within Double Line Channel"],
            matched_buy_strategies=["daily_bull_oversold", "daily_bull_mid_range"],
        )

        item_single = ExecutionResultItem(
            code="TSLA.US",
            name="Tesla",
            buy_signals=1,
            sell_signals=0,
            reasons=["Oversold J < 20"],
            matched_buy_strategies=["daily_bull_oversold"],
        )

        item_sell = ExecutionResultItem(
            code="600519.SH",
            name="Moutai",
            buy_signals=0,
            sell_signals=1,
            reasons=["Short term trend crossed below long/short line"],
            matched_sell_strategies=["dual_line_bear"],
        )

        output_dir = str(Path(temp_watchlist.name) / "full")
        report_path = reporter.generate(
            task_name="UnitTest_Full",
            strategies=mock_strategies,
            results=[item_resonance, item_single, item_sell],
            watchlist=temp_watchlist,
            output_dir=output_dir,
            date_str="2026-05-01",
        )

        content = Path(report_path).read_text()

        assert "### 🔵 Buy - daily_bull_oversold & daily_bull_mid_range" in content
        assert "Apple" in content
        assert "### 🔵 Buy - daily_bull_oversold" in content
        assert "Tesla" in content
        assert "### 🔴 Sell - dual_line_bear" in content
        assert "Moutai" in content

    def test_single_strategy_only(self, reporter, temp_watchlist, mock_strategies):
        """Only a single strategy triggers, no resonance group."""
        item = ExecutionResultItem(
            code="AAPL.US",
            name="Apple",
            buy_signals=1,
            sell_signals=0,
            reasons=["Reason"],
            matched_buy_strategies=["daily_bull_mid_range"],
        )

        output_dir = str(Path(temp_watchlist.name) / "single")
        report_path = reporter.generate(
            task_name="Test_Single",
            strategies=mock_strategies,
            results=[item],
            watchlist=temp_watchlist,
            output_dir=output_dir,
            date_str="2026-05-01",
        )

        content = Path(report_path).read_text()

        assert "daily_bull_oversold & daily_bull_mid_range" not in content
        assert "Apple" in content

    def test_name_fallback_from_watchlist(self, reporter, temp_watchlist, mock_strategies):
        """Item with empty name falls back to watchlist name."""
        item_no_name = ExecutionResultItem(
            code="AAPL.US",
            name="",
            buy_signals=1,
            sell_signals=0,
            reasons=["Test reason"],
            matched_buy_strategies=["daily_bull_oversold"],
        )

        output_dir = str(Path(temp_watchlist.name) / "fallback")
        report_path = reporter.generate(
            task_name="Test_Fallback",
            strategies=mock_strategies,
            results=[item_no_name],
            watchlist=temp_watchlist,
            output_dir=output_dir,
            date_str="2026-05-01",
        )

        content = Path(report_path).read_text()
        assert "Apple Inc." in content


class TestMarkdownReporterGenerateCombined:
    """Verify generate_combined() for multi-task aggregation."""

    @pytest.fixture
    def reporter(self):
        return MarkdownReporter()

    @pytest.fixture
    def temp_watchlist(self, tmp_path):
        wl_path = tmp_path / "wl.yaml"
        wl_path.write_text(
            "name: TestWL\n"
            "items:\n"
            "  - code: AAPL.US\n"
            "    name: Apple\n"
        )
        return Watchlist.load(str(wl_path))

    def _make_task_run(self, name, watchlist, strategies, results):
        return (name, results, watchlist, strategies)

    def test_combined_basic(self, reporter, temp_watchlist):
        """Multiple tasks with mixed signals produce correct combined report."""
        strat = MagicMock()
        strat.name = "daily_bull_oversold"

        item1 = ExecutionResultItem(
            code="AAPL.US", name="Apple",
            buy_signals=1, sell_signals=0,
            matched_buy_strategies=["daily_bull_oversold"],
        )

        task_runs = [
            self._make_task_run("Task-A", temp_watchlist, [strat], [item1]),
            self._make_task_run("Task-B", temp_watchlist, [strat], []),
        ]

        output_dir = str(Path(temp_watchlist.name) / "combined_basic")
        report_path = reporter.generate_combined(
            date_str="2026-05-01",
            task_runs=task_runs,
            output_dir=output_dir,
        )

        content = Path(report_path).read_text()
        assert "# Daily Scan Summary" in content
        assert "**Tasks Executed**: 2" in content
        assert "- **Buy Signals**: 1" in content
        assert "- **Sell Signals**: 0" in content
        assert "## Task-A" in content
        assert "## Task-B" in content

    def test_combined_empty_task_runs(self, reporter, tmp_path):
        """Empty task_runs produces a report with zero statistics."""
        output_dir = str(tmp_path / "combined_empty")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        report_path = reporter.generate_combined(
            date_str="2026-05-01",
            task_runs=[],
            output_dir=output_dir,
        )

        content = Path(report_path).read_text()
        assert "**Tasks Executed**: 0" in content
        assert "- **Total Watched**: 0" in content
        assert "- **Buy Signals**: 0" in content
        assert "- **Sell Signals**: 0" in content

    def test_combined_single_task(self, reporter, temp_watchlist):
        """Single task produces correct combined report."""
        strat = MagicMock()
        strat.name = "kdj_dead_cross"

        item = ExecutionResultItem(
            code="AAPL.US", name="Apple",
            buy_signals=0, sell_signals=1,
            matched_sell_strategies=["kdj_dead_cross"],
        )

        task_runs = [
            self._make_task_run("Solo", temp_watchlist, [strat], [item]),
        ]

        output_dir = str(Path(temp_watchlist.name) / "combined_single")
        report_path = reporter.generate_combined(
            date_str="2026-05-01",
            task_runs=task_runs,
            output_dir=output_dir,
        )

        content = Path(report_path).read_text()
        assert "**Tasks Executed**: 1" in content
        assert "- **Sell Signals**: 1" in content
        assert "## Solo" in content

    def test_combined_aggregates_statistics(self, reporter, tmp_path):
        """Statistics are correctly summed across tasks."""
        wl1_path = tmp_path / "wl1.yaml"
        wl1_path.write_text(
            "name: WL1\n"
            "items:\n"
            "  - code: AAPL.US\n"
            "    name: Apple\n"
            "  - code: GOOG.US\n"
            "    name: Google\n"
        )
        wl2_path = tmp_path / "wl2.yaml"
        wl2_path.write_text(
            "name: WL2\n"
            "items:\n"
            "  - code: TSLA.US\n"
            "    name: Tesla\n"
        )
        wl1 = Watchlist.load(str(wl1_path))
        wl2 = Watchlist.load(str(wl2_path))

        strat = MagicMock()
        strat.name = "daily_bull_oversold"

        buy_item = ExecutionResultItem(
            code="AAPL.US", name="Apple",
            buy_signals=1, sell_signals=0,
            matched_buy_strategies=["daily_bull_oversold"],
        )
        sell_item = ExecutionResultItem(
            code="TSLA.US", name="Tesla",
            buy_signals=0, sell_signals=1,
            matched_sell_strategies=["daily_bull_oversold"],
        )

        task_runs = [
            self._make_task_run("T1", wl1, [strat], [buy_item]),
            self._make_task_run("T2", wl2, [strat], [sell_item]),
        ]

        output_dir = str(tmp_path / "combined_stats")
        reporter.generate_combined(
            date_str="2026-05-01",
            task_runs=task_runs,
            output_dir=output_dir,
        )

        content = Path(output_dir + "/Daily_Report.md").read_text()
        assert "- **Total Watched**: 3" in content
        assert "- **Buy Signals**: 1" in content
        assert "- **Sell Signals**: 1" in content
        assert "- **No Signals**: 1" in content


class TestMarkdownReporterEdgeCases:
    """Verify edge cases in generate()."""

    @pytest.fixture
    def reporter(self):
        return MarkdownReporter()

    @pytest.fixture
    def temp_watchlist(self, tmp_path):
        wl_path = tmp_path / "wl.yaml"
        wl_path.write_text(
            "name: EdgeWL\n"
            "items:\n"
            "  - code: AAPL.US\n"
            "    name: Apple\n"
        )
        return Watchlist.load(str(wl_path))

    def test_generate_empty_results(self, reporter, temp_watchlist):
        """Empty results produces a report with zero statistics and no signal groups."""
        output_dir = str(Path(temp_watchlist.name) / "empty_results")
        report_path = reporter.generate(
            task_name="Test_Empty",
            strategies=[],
            results=[],
            watchlist=temp_watchlist,
            output_dir=output_dir,
            date_str="2026-05-01",
        )

        content = Path(report_path).read_text()
        assert "# Test_Empty Scan Report" in content
        assert "- **Buy Signals**: 0" in content
        assert "- **Sell Signals**: 0" in content
        assert "### 🔵 Buy" not in content
        assert "### 🔴 Sell" not in content

    def test_generate_sell_only(self, reporter, temp_watchlist):
        """Only sell signals, no buy signals."""
        item = ExecutionResultItem(
            code="AAPL.US",
            name="Apple",
            buy_signals=0,
            sell_signals=1,
            reasons=["Bear zone exit"],
            matched_sell_strategies=["dual_line_bear"],
        )

        output_dir = str(Path(temp_watchlist.name) / "sell_only")
        report_path = reporter.generate(
            task_name="Test_Sell",
            strategies=[],
            results=[item],
            watchlist=temp_watchlist,
            output_dir=output_dir,
            date_str="2026-05-01",
        )

        content = Path(report_path).read_text()
        assert "### 🔴 Sell - dual_line_bear" in content
        assert "### 🔵 Buy" not in content

    def test_generate_creates_output_dir(self, reporter, temp_watchlist, tmp_path):
        """Output directory is auto-created if it doesn't exist."""
        output_dir = str(tmp_path / "new_dir" / "nested" / "path")
        assert not Path(output_dir).exists()

        report_path = reporter.generate(
            task_name="Test_Mkdir",
            strategies=[],
            results=[],
            watchlist=temp_watchlist,
            output_dir=output_dir,
            date_str="2026-05-01",
        )

        assert Path(output_dir).exists()
        assert Path(report_path).exists()


class TestGroupByStrategy:
    """Verify _group_by_strategy() directly."""

    @pytest.fixture
    def reporter(self):
        return MarkdownReporter()

    def test_empty_list(self, reporter):
        """Empty items list returns empty list."""
        result = reporter._group_by_strategy([], "buy")
        assert result == []

    def test_sorting_by_resonance_count(self, reporter):
        """Groups with more matched strategies appear first."""
        item_single = ExecutionResultItem(
            code="X", name="X",
            buy_signals=1,
            matched_buy_strategies=["daily_bull_oversold"],
        )
        item_double = ExecutionResultItem(
            code="Y", name="Y",
            buy_signals=2,
            matched_buy_strategies=["daily_bull_oversold", "daily_bull_mid_range"],
        )

        result = reporter._group_by_strategy(
            [item_single, item_double], "buy"
        )

        assert len(result) == 2
        assert len(result[0][0]) == 2
        assert len(result[1][0]) == 1

    def test_sell_signal_grouping(self, reporter):
        """Sell signals are grouped by matched_sell_strategies."""
        item1 = ExecutionResultItem(
            code="X", name="X",
            sell_signals=1,
            matched_sell_strategies=["dual_line_bear"],
        )
        item2 = ExecutionResultItem(
            code="Y", name="Y",
            sell_signals=1,
            matched_sell_strategies=["dual_line_bear"],
        )
        item3 = ExecutionResultItem(
            code="Z", name="Z",
            sell_signals=1,
            matched_sell_strategies=["kdj_dead_cross"],
        )

        result = reporter._group_by_strategy(
            [item1, item2, item3], "sell"
        )

        assert len(result) == 2
        assert len(result[0][1]) == 2
        assert result[0][0] == ("dual_line_bear",)


class TestFormatStrategyName:
    """Verify _format_strategy_name()."""

    @pytest.fixture
    def reporter(self):
        return MarkdownReporter()

    def test_single_strategy(self, reporter):
        """Single strategy returns its name directly."""
        result = reporter._format_strategy_name(("daily_bull_oversold",))
        assert result == "daily_bull_oversold"

    def test_multiple_strategies(self, reporter):
        """Multiple strategies joined with ' & '."""
        result = reporter._format_strategy_name(
            ("daily_bull_oversold", "daily_bull_mid_range")
        )
        assert result == "daily_bull_oversold & daily_bull_mid_range"

    def test_three_strategies(self, reporter):
        """Three strategies joined with ' & '."""
        result = reporter._format_strategy_name(
            ("s1", "s2", "s3")
        )
        assert result == "s1 & s2 & s3"


class TestCountWatched:
    """Verify _count_watched()."""

    @pytest.fixture
    def reporter(self):
        return MarkdownReporter()

    def test_with_length_attribute(self, reporter, tmp_path):
        """Uses watchlist.length when available."""
        wl_path = tmp_path / "wl.yaml"
        wl_path.write_text(
            "name: WL\n"
            "items:\n"
            "  - code: AAPL.US\n"
            "    name: Apple\n"
        )
        wl = Watchlist.load(str(wl_path))
        wl.length = 99

        assert reporter._count_watched(wl) == 99

    def test_fallback_to_len_items(self, reporter, tmp_path):
        """Falls back to len(items) when no length attribute."""
        wl_path = tmp_path / "wl.yaml"
        wl_path.write_text(
            "name: WL\n"
            "items:\n"
            "  - code: AAPL.US\n"
            "    name: Apple\n"
            "  - code: TSLA.US\n"
            "    name: Tesla\n"
            "  - code: GOOG.US\n"
            "    name: Google\n"
        )
        wl = Watchlist.load(str(wl_path))

        assert reporter._count_watched(wl) == 3
