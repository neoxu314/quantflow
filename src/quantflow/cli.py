"""CLI entry points."""

import argparse
import logging
from datetime import datetime, timedelta

from quantflow.data import DataSourceFactory, StockCode
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.standard import KDJIndicator, MACDIndicator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def stock_scan():
    parser = argparse.ArgumentParser(description="Scan single stock")
    parser.add_argument("--code", required=True, help="Stock code (e.g., 600000.SH)")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--indicator", default="kdj,dual_line", help="Indicators to use")

    args = parser.parse_args()
    code = StockCode.from_standard(args.code)

    end_date = args.end or datetime.now().strftime("%Y-%m-%d")
    start_date = args.start or (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    factory = DataSourceFactory()
    df, source = factory.fetch_ohlcv(code, start_date, end_date)

    if df.empty:
        logger.error(f"No data for {args.code}")
        return

    indicators = []
    for ind_name in args.indicator.split(","):
        if ind_name == "kdj":
            indicators.append(KDJIndicator())
        elif ind_name == "macd":
            indicators.append(MACDIndicator())
        elif ind_name == "dual_line":
            from quantflow.indicators.custom import DualLineIndicator
            indicators.append(DualLineIndicator())

    if indicators:
        df = IndicatorComposer(indicators).compose(df)

    print(f"\n=== Scan Result for {args.code} ===")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Data source: {source}")


def watchlist_run():
    """Run single watchlist via Execution Layer (same as Web watchlist_run)."""
    parser = argparse.ArgumentParser(
        description="Run stock watchlist with strategies")
    parser.add_argument("--watchlist", required=True,
        help="Watchlist YAML path")
    parser.add_argument("--output", default="./output",
        help="Output directory")
    parser.add_argument("--strategies",
        default="daily_bull_oversold,daily_bull_mid_range",
        help="Comma-separated strategy IDs (default: daily_bull_oversold,daily_bull_mid_range)")
    parser.add_argument("--days-back", type=int, default=None,
        help="Override auto-calculated lookback days")

    args = parser.parse_args()

    from quantflow.config.lookback import compute_days_back
    from quantflow.execution.executor import Executor
    from quantflow.execution.job import ExecutionJob
    from quantflow.execution.storage import Storage
    from quantflow.execution.watchlist import Watchlist
    from quantflow.orchestration.registry import STRATEGY_REGISTRY
    from quantflow.reports.markdown import MarkdownReporter

    watchlist = Watchlist.load(args.watchlist)

    strategy_ids = [s.strip() for s in args.strategies.split(",")]
    strategies = [STRATEGY_REGISTRY[s]() for s in strategy_ids]

    days_back = compute_days_back(
        strategies=strategies, override=args.days_back)

    job = ExecutionJob(
        name=f"cli:{watchlist.name}",
        items=watchlist.items,
        strategies=strategies,
        output_dir=args.output,
        days_back=days_back
    )

    executor = Executor()
    results = executor.execute(job)

    date_str = datetime.now().strftime("%Y-%m-%d")
    rpath = MarkdownReporter().generate(
        f"cli:{watchlist.name}", strategies, results, watchlist,
        args.output, date_str)

    Storage().save_results(f"{args.output}/{watchlist.name}_results.json", results)
    print(f"Execution complete. {len(results)} signals saved.")
    print(f"Report: {rpath}")


def task_run():
    parser = argparse.ArgumentParser(
        description="Run scheduled tasks via Orchestration")
    parser.add_argument("--config", required=True,
        help="Path to tasks config (e.g., config/tasks_us_mac.yaml)")
    parser.add_argument("--output", default=None,
        help="Base output directory override")
    parser.add_argument("--daily", action="store_true",
        help="Auto-append date to output path")
    args = parser.parse_args()

    from quantflow.orchestration.app import Orchestrator
    from quantflow.orchestration.loader import TaskConfig

    try:
        configs = TaskConfig.load(args.config)
        app = Orchestrator(configs, output_override=args.output, daily_mode=args.daily)
        app.run()
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")


def web():
    """Launch QuantFlow Web UI."""
    from quantflow.web.config import WebConfig
    from quantflow.web.server import start_server

    config = WebConfig.load()
    print(f"Starting QuantFlow Web UI on {config.host}:{config.port}...")
    start_server(config)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        sys.argv = sys.argv[1:]
        if command in ("scan", "stock_scan"):
            stock_scan()
        elif command in ("monitor", "watchlist_run"):
            watchlist_run()
        elif command in ("tasks", "task_run"):
            task_run()
        elif command == "web":
            web()
        else:
            print(f"Unknown command: {command}")
    else:
        print("Usage: python -m quantflow.cli <command>")
        print("Commands: stock_scan, watchlist_run, task_run, web")
        print("Aliases: scan, monitor, tasks (deprecated)")
