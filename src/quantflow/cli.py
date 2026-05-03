"""CLI entry points."""

import argparse
import logging
from datetime import datetime, timedelta

from quantflow.data import DataSourceFactory, StockCode
from quantflow.indicators.standard import KDJIndicator, MACDIndicator
from quantflow.indicators.custom import DualLineIndicator
from quantflow.indicators.composer import IndicatorComposer
from quantflow.strategies.composite import CompositeStrategy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def scan():
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
        if ind_name == "kdj": indicators.append(KDJIndicator())
        elif ind_name == "macd": indicators.append(MACDIndicator())
        elif ind_name == "dual_line": indicators.append(DualLineIndicator())
    
    if indicators:
        df = IndicatorComposer(indicators).compose(df)
    
    print(f"\n=== Scan Result for {args.code} ===")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Data source: {source}")


def monitor():
    parser = argparse.ArgumentParser(description="Run single watchlist via Execution Layer")
    parser.add_argument("--watchlist", required=True, help="Watchlist YAML path")
    parser.add_argument("--output", default="./output", help="Output dir")
    
    args = parser.parse_args()
    
    from quantflow.execution.watchlist import Watchlist
    from quantflow.execution.job import ExecutionJob
    from quantflow.execution.executor import Executor
    from quantflow.execution.storage import ExecutionResultItem
from quantflow.strategies.buy import DailyBullishMidRangeBuy, DailyBullishOversoldBuy

    watchlist = Watchlist.load(args.watchlist)
    
    job = ExecutionJob(
        name=f"Manual-{watchlist.name}",
        items=watchlist.items,
        strategies=[DailyBullishMidRangeBuy(), DailyBullishOversoldBuy()],
        output_dir=args.output
    )
    
    executor = Executor()
    results = executor.execute(job)
    print(f"Execution complete. {len(results)} items with signals saved.")


def tasks():
    parser = argparse.ArgumentParser(description="Run scheduled tasks via Orchestration")
    parser.add_argument("--config", required=True, help="Path to tasks config (e.g., config/tasks_us_mac.yaml)")
    parser.add_argument("--output", default=None, help="Base output directory override")
    parser.add_argument("--daily", action="store_true", help="Auto-append date to output path")
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
    # Late import to avoid circular deps
    from quantflow.web.server import start_server
    from quantflow.web.config import WebConfig

    config = WebConfig.load()
    print(f"Starting QuantFlow Web UI on {config.host}:{config.port}...")
    start_server(config)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        command = sys.argv[1]
        sys.argv = sys.argv[1:]
        if command == "scan": scan()
        elif command == "monitor": monitor()
        elif command == "tasks": tasks()
        elif command == "web": web()
        else: print(f"Unknown command: {command}")
    else:
        print("Usage: python -m quantflow.cli <command>")
        print("Commands: scan, monitor, tasks, web")
