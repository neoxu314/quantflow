"""CLI entry points."""

import argparse
import json
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from quantflow.config.lookback import load_lookback_config
from quantflow.data import DataSourceFactory, StockCode
from quantflow.indicators.composer import IndicatorComposer
from quantflow.indicators.standard import KDJIndicator, MACDIndicator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def stock_scan():
    parser = argparse.ArgumentParser(description="Scan single stock")
    parser.add_argument("--code", required=True, help="Stock code (e.g., 600000.SH)")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--indicator", default="kdj,dual_line", help="Indicators to use")
    parser.add_argument("--output", default=None, help="Output directory for indicator results")

    args = parser.parse_args()
    code = StockCode.from_standard(args.code)

    end_date = args.end or datetime.now().strftime("%Y-%m-%d")
    start_date = args.start or (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

    ind_objs = []
    for ind_name in args.indicator.split(","):
        if ind_name == "kdj":
            ind_objs.append(KDJIndicator())
        elif ind_name == "macd":
            ind_objs.append(MACDIndicator())
        elif ind_name == "dual_line":
            from quantflow.indicators.custom import DualLineIndicator
            ind_objs.append(DualLineIndicator())

    if ind_objs:
        lookback_cfg = load_lookback_config()
        multiplier = lookback_cfg.get("calendar_multiplier", 2)
        buffer = lookback_cfg.get("buffer_days", 30)
        max_lookback = max(ind.lookback_bars for ind in ind_objs)
        extra_days = math.ceil(max_lookback * multiplier) + buffer

        fetch_start_date = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=extra_days)
        fetch_start = fetch_start_date.strftime("%Y-%m-%d")
    else:
        fetch_start = start_date

    factory = DataSourceFactory()
    df, source = factory.fetch_ohlcv(code, fetch_start, end_date)

    if df.empty:
        logger.error(f"No data for {args.code}")
        return

    actual_end = factory._latest_date(df)
    if actual_end < end_date:
        print(f"⚠️ No data on {end_date}. Using latest available: {actual_end}")
    if df.empty:
        logger.error(f"No data for {args.code}")
        return

    actual_end = factory._latest_date(df)
    if actual_end < end_date:
        print(f"⚠️ No data on {end_date}. Using latest available: {actual_end}")

    if ind_objs:
        df = IndicatorComposer(ind_objs).compose(df)

        if "date" in df.columns:
            df = df[pd.to_datetime(df["date"]) >= start_date]

        if start_date == end_date:
            df = df.tail(1)

    print(f"\n=== Scan Result for {args.code} ===")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Data source: {source}")

    output_dir = Path(args.output) if args.output else PROJECT_ROOT / "output" / "cli_scans"
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_code = args.code.replace("/", "_").replace("\\", "_")
    indicator_file = output_dir / f"{safe_code}_indicators.json"

    def _serialize_df(df_to_save):
        out = []
        for row in df_to_save.to_dict(orient="records"):
            clean = {}
            for k, v in row.items():
                if hasattr(v, "isoformat"):
                    clean[k] = v.isoformat()
                elif hasattr(v, "item"):
                    try:
                        val = v.item()
                        if isinstance(val, float) and math.isnan(val):
                            clean[k] = None
                        else:
                            clean[k] = val
                    except Exception:
                        clean[k] = str(v)
                elif isinstance(v, float):
                    clean[k] = None if math.isnan(v) else v
                else:
                    clean[k] = v
            out.append(clean)
        return out

    indicator_data = _serialize_df(df)
    indicator_file.write_text(json.dumps(indicator_data, indent=2))

    print(f"Indicator data saved: {indicator_file}")


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
