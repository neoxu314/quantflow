"""Pre-flight validation for run configurations."""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class ValidationResult:
    def __init__(self):
        self.errors: list[str] = []

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def validate_code_fmt(value: str) -> ValidationResult:
    r = ValidationResult()
    if not re.fullmatch(r'[A-Za-z0-9-]{1,15}\.(SH|SZ|HK|US|T|KS|JP|KR)', value):
        r.fail(f"Invalid stock code format: '{value}'. Expected: NVDA.US, 600519.SH")
        return r
    try:
        from quantflow.data.base import StockCode
        StockCode.from_standard(value)
    except Exception as e:
        r.fail(f"Invalid stock code '{value}': {e}")
    return r


def validate_watchlist_file(path: str) -> ValidationResult:
    r = ValidationResult()
    p = Path(path) if os.path.isabs(path) else PROJECT_ROOT / path
    if not p.exists():
        r.fail(f"Watchlist not found: '{path}'")
        return r
    try:
        from quantflow.execution.watchlist import Watchlist
        wl = Watchlist.load(str(p))
        if not wl.items:
            r.fail(f"Watchlist '{path}' is empty")
    except Exception as e:
        r.fail(f"Invalid watchlist: {e}")
    return r


def validate_task_file(path: str) -> ValidationResult:
    r = ValidationResult()
    p = Path(path) if os.path.isabs(path) else PROJECT_ROOT / path
    if not p.exists():
        r.fail(f"Task config not found: '{path}'")
        return r
    try:
        from quantflow.orchestration.loader import TaskConfig
        tasks = TaskConfig.load(str(p))
        if not tasks:
            r.fail(f"Task config '{path}' has no valid tasks")
    except Exception as e:
        r.fail(f"Invalid task config: {e}")
    return r


def validate_output_path(path: Optional[str]) -> ValidationResult:
    r = ValidationResult()
    if path:
        p = Path(path) if os.path.isabs(path) else PROJECT_ROOT / path
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            r.fail(f"Cannot create output path: {e}")
    return r


def validate_strategy_id(sid: str) -> ValidationResult:
    r = ValidationResult()
    try:
        from quantflow.orchestration.registry import get_strategy_class
        get_strategy_class(sid)
    except (ValueError, ImportError):
        r.fail(f"Unknown strategy '{sid}'")
    return r


def validate_dates(start: Optional[str], end: Optional[str]) -> ValidationResult:
    r = ValidationResult()
    date_re = r"^\d{4}-\d{2}-\d{2}$"
    if start and not re.match(date_re, start):
        r.fail("Invalid start_date format")
        return r
    if end and not re.match(date_re, end):
        r.fail("Invalid end_date format")
        return r
    try:
        s = datetime.strptime(start, "%Y-%m-%d") if start else None
        e = datetime.strptime(end, "%Y-%m-%d") if end else None
        if s and e and s > e:
            r.fail("start_date after end_date")
    except ValueError:
        r.fail("Invalid calendar date")
    return r


class PreflightChecker:
    @staticmethod
    def validate(run_type: str, config: dict) -> ValidationResult:
        r = ValidationResult()
        if run_type == "stock_scan":
            code = config.get("code")
            if not code:
                r.fail("Stock code is required")
            else:
                r.errors.extend(validate_code_fmt(code).errors)
            r.errors.extend(
                validate_dates(
                    config.get("start_date"), config.get("end_date")
                ).errors
            )
            for ind in config.get("indicators", []):
                if ind not in ("kdj", "macd", "dual_line", "rsi", "boll",
                               "vol_ma", "brick_chart", "washout"):
                    r.fail(f"Unknown indicator: '{ind}'")
        elif run_type == "watchlist_run":
            if config.get("days_back") is not None and (not isinstance(config["days_back"], int) or config["days_back"] <= 0):
                r.fail("days_back must be a positive integer")
            wl = config.get("watchlist")
            if not wl:
                r.fail("Watchlist path required")
            else:
                r.errors.extend(validate_watchlist_file(wl).errors)
            for sid in config.get("strategies") or []:
                r.errors.extend(validate_strategy_id(sid).errors)
        elif run_type == "task_run":
            tp = config.get("task_config")
            if not tp:
                r.fail("Task config path required")
            else:
                r.errors.extend(validate_task_file(tp).errors)
        else:
            r.fail(f"Unknown run_type: '{run_type}'")
        r.errors.extend(validate_output_path(config.get("output_path")).errors)
        return r
