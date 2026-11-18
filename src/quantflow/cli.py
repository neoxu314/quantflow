"""CLI entry points sharing the same scan and execution services as the Web UI."""

import argparse
import logging
from datetime import datetime
from pathlib import Path

from quantflow.artifacts import (
    atomic_json,
    create_run_directory,
    finish_manifest,
    register_artifact,
)
from quantflow.config.logging import setup_logging
from quantflow.control import ExecutionCancelled

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _log_run(output, label):
    path = setup_logging(output, label)
    if path:
        register_artifact(path)


def stock_scan():
    from quantflow.execution.scanner import scan_stock

    parser = argparse.ArgumentParser(description="Scan a stock; each run has its own directory")
    parser.add_argument("--code", required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--indicator", default="kdj,dual_line")
    parser.add_argument("--output")
    args = parser.parse_args()
    cfg = {
        "code": args.code,
        "start_date": args.start,
        "end_date": args.end,
        "indicators": [n.strip() for n in args.indicator.split(",")],
    }
    output = None
    try:
        output = create_run_directory(args.output or PROJECT_ROOT / "output/cli_scans", config=cfg)
        _log_run(output, "stock_scan")
        report, bars, metadata = scan_stock(cfg, output)
        finish_manifest(output, "completed", summary=metadata)
        logger.info("Saved %d bars: %s", bars, report)
        return 0
    except (KeyboardInterrupt, ExecutionCancelled):
        if output:
            finish_manifest(output, "cancelled")
        return 130
    except Exception as exc:
        if output:
            finish_manifest(output, "failed", error=str(exc))
        logger.error("Stock scan failed: %s", exc)
        return 1


def watchlist_run():
    from quantflow.config.lookback import compute_days_back
    from quantflow.execution.executor import Executor
    from quantflow.execution.job import ExecutionJob
    from quantflow.execution.watchlist import Watchlist
    from quantflow.orchestration.registry import get_strategy_class
    from quantflow.reports.markdown import MarkdownReporter

    parser = argparse.ArgumentParser(description="Run watchlist with explicit coverage")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--output", default="./output")
    parser.add_argument("--strategies", default="daily_bull_oversold,daily_bull_mid_range")
    parser.add_argument("--days-back", type=int)
    args = parser.parse_args()
    output = None
    try:
        output = create_run_directory(args.output, config=vars(args))
        _log_run(output, "watchlist_run")
        wl = Watchlist.load(args.watchlist)
        strategies = [get_strategy_class(s.strip())() for s in args.strategies.split(",")]
        days = compute_days_back(strategies, args.days_back)
        if days <= 0:
            raise ValueError("days-back must be positive")
        job = ExecutionJob(f"cli-{wl.name}", wl.items, strategies, str(output), days)
        results = Executor().execute(job)
        report = MarkdownReporter().generate(
            job.name, strategies, results, wl, str(output), datetime.now().strftime("%Y-%m-%d")
        )
        atomic_json(output / "Run_Summary.json", results.summary)
        finish_manifest(output, results.summary["status"], summary=results.summary)
        logger.info("%s; report: %s", results.summary, report)
        return {"completed": 0, "partial": 2, "failed": 1}[results.summary["status"]]
    except (KeyboardInterrupt, ExecutionCancelled):
        if output:
            finish_manifest(output, "cancelled")
        return 130
    except Exception as exc:
        if output:
            finish_manifest(output, "failed", error=str(exc))
        logger.error("Watchlist run failed: %s", exc)
        return 1


def task_run():
    from quantflow.orchestration.app import Orchestrator
    from quantflow.orchestration.loader import TaskConfig

    parser = argparse.ArgumentParser(description="Run task configuration")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output")
    parser.add_argument("--daily", action="store_true")
    args = parser.parse_args()
    try:
        app = Orchestrator(TaskConfig.load(args.config), args.output, args.daily)
        app.run()
        logger.info("%s; report: %s", app.last_summary, app.report_path)
        return {"completed": 0, "partial": 2, "failed": 1}[app.last_summary["status"]]
    except (KeyboardInterrupt, ExecutionCancelled):
        return 130
    except Exception as exc:
        logger.error("Task run failed: %s", exc)
        return 1


def web():
    from quantflow.web.config import WebConfig
    from quantflow.web.server import start_server

    start_server(WebConfig.load())


# Keep installed command entry points functional.
scan = stock_scan
monitor = watchlist_run


if __name__ == "__main__":
    import sys

    commands = {
        "stock_scan": stock_scan,
        "scan": stock_scan,
        "watchlist_run": watchlist_run,
        "monitor": watchlist_run,
        "task_run": task_run,
        "tasks": task_run,
        "web": web,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print("Usage: python -m quantflow.cli <stock_scan|watchlist_run|task_run|web>")
        raise SystemExit(2)
    command = sys.argv[1]
    sys.argv = sys.argv[1:]
    raise SystemExit(commands[command]())
