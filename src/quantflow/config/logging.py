"""Logging setup for QuantFlow runs."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from quantflow.config.loader import ConfigLoader


def setup_logging(output_dir: Path, run_label: str) -> Optional[Path]:
    log_cfg = ConfigLoader().get_logging_config()

    console_level = getattr(
        logging, log_cfg.get("console_level", "INFO").upper(), logging.INFO
    )
    file_enabled = log_cfg.get("file_enabled", True)
    file_level = getattr(
        logging, log_cfg.get("file_level", "DEBUG").upper(), logging.DEBUG
    )
    fmt = log_cfg.get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    if not file_enabled:
        return None

    log_dir = output_dir / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        logging.warning(
            "Cannot create log directory %s, file logging disabled", log_dir
        )
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"{run_label}_{timestamp}.log"

    try:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        logging.warning(
            "Cannot create log file %s, file logging disabled", log_path
        )
        return None

    logging.info("Log file: %s", log_path)
    return log_path
