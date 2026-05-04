"""Shared lookback configuration and days_back computation."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "quantflow.yaml"


def load_lookback_config() -> Dict[str, Any]:
    """Load lookback settings from config/quantflow.yaml."""
    defaults = {"calendar_multiplier": 2, "buffer_days": 30}
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            data = yaml.safe_load(f) or {}
        if "lookback" in data:
            defaults.update(data["lookback"])
    return defaults


def compute_days_back(
    strategies: Optional[List[Any]] = None,
    override: Optional[int] = None,
) -> int:
    """Compute required calendar days for lookback.

    Formula: ceil(max(lookback_bars) * calendar_multiplier) + buffer_days

    If override is provided, returns it directly.
    If strategies is empty/None, defaults to 365.
    """
    if override is not None:
        return override
    if not strategies:
        return 365
    cfg = load_lookback_config()
    multiplier = cfg.get("calendar_multiplier", 2)
    buffer = cfg.get("buffer_days", 30)
    max_bars = max(s.get_lookback_bars() for s in strategies)
    return math.ceil(max_bars * multiplier) + buffer
