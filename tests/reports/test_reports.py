import pytest
from pathlib import Path
from unittest.mock import MagicMock

from quantflow.execution.storage import ExecutionResultItem
from quantflow.execution.watchlist import Watchlist
from quantflow.reports.markdown import MarkdownReporter


REPORT_TEST_OUTPUT_DIR = Path("./tests/reports/output")


class TestMarkdownReporterGrouping:
    @pytest.fixture
    def reporter(self):
        return MarkdownReporter()

    @pytest.fixture
    def personal_watchlist(self):
        return Watchlist.load("./watchlists/personal_focus.yaml")

    @pytest.fixture
    def mock_strategies(self):
        s1 = MagicMock()
        s1.name = "daily_bull_oversold"
        s2 = MagicMock()
        s2.name = "daily_bull_mid_range"
        return [s1, s2]

    def test_complete_report_structure(self, reporter, personal_watchlist, mock_strategies):
        """
        Test full report flow: resonance grouping, single strategy, sell signal, and name display.
        """
        item_resonance = ExecutionResultItem(
            code="00700.HK", 
            name="腾讯控股",
            buy_signals=2, 
            sell_signals=0,
            reasons=["Oversold J < 20", "Price within Double Line Channel"],
            matched_buy_strategies=["daily_bull_oversold", "daily_bull_mid_range"]
        )

        item_single_oversold = ExecutionResultItem(
            code="09988.HK",
            name="阿里巴巴-W",
            buy_signals=1,
            sell_signals=0,
            reasons=["Oversold J < 20"],
            matched_buy_strategies=["daily_bull_oversold"]
        )

        item_single_mid = ExecutionResultItem(
            code="002594.SZ",
            name="比亚迪",
            buy_signals=1,
            sell_signals=0,
            reasons=["Price within Double Line Channel"],
            matched_buy_strategies=["daily_bull_mid_range"]
        )

        item_sell = ExecutionResultItem(
            code="BHP.US",
            name="必和必拓",
            buy_signals=0,
            sell_signals=1,
            reasons=["Short term trend crossed below long/short line"],
            matched_sell_strategies=["dual_line_bear"]
        )

        output_dir = REPORT_TEST_OUTPUT_DIR / "full"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_path = reporter.generate(
            task_name="UnitTest_Personal",
            strategies=mock_strategies,
            results=[item_resonance, item_single_oversold, item_single_mid, item_sell],
            watchlist=personal_watchlist,
            output_dir=str(output_dir),
            date_str="2026-05-01"
        )

        assert Path(report_path).exists()
        content = Path(report_path).read_text()
        
        assert "### 🔵 Buy - daily_bull_oversold & daily_bull_mid_range" in content
        assert "腾讯控股" in content
        assert "### 🔵 Buy - daily_bull_oversold" in content
        assert "阿里巴巴-W" in content
        assert "比亚迪" in content
        assert "### 🔴 Sell - dual_line_bear" in content
        assert "必和必拓" in content

    def test_empty_resonance(self, reporter, personal_watchlist, mock_strategies):
        """Test when only a single strategy triggers."""
        item = ExecutionResultItem(
            code="TSM.US", name="台积电",
            buy_signals=1, sell_signals=0,
            reasons=["Reason"],
            matched_buy_strategies=["daily_bull_mid_range"]
        )

        output_dir = REPORT_TEST_OUTPUT_DIR / "single"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_path = reporter.generate(
            task_name="Test_Single",
            strategies=mock_strategies,
            results=[item],
            watchlist=personal_watchlist,
            output_dir=str(output_dir),
            date_str="2026-05-01"
        )
        
        content = Path(report_path).read_text()
        
        assert "daily_bull_oversold & daily_bull_mid_range" not in content
        assert "台积电" in content

    def test_no_stock_name_fallback(self, reporter, personal_watchlist, mock_strategies):
        """Verify that if a strategy result lacks a name, it falls back to the watchlist name."""
        item_no_name = ExecutionResultItem(
            code="00700.HK",
            name="",
            buy_signals=1,
            sell_signals=0,
            reasons=["Test reason"],
            matched_buy_strategies=["daily_bull_oversold"]
        )

        output_dir = REPORT_TEST_OUTPUT_DIR / "fallback"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        report_path = reporter.generate(
            task_name="Test_Fallback",
            strategies=mock_strategies,
            results=[item_no_name],
            watchlist=personal_watchlist,
            output_dir=str(output_dir),
            date_str="2026-05-01"
        )
        
        content = Path(report_path).read_text()
        assert "腾讯控股" in content
