"""Web API routes for config and strategies."""
from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter
from typing import Any, Dict

# Router for API endpoints under /api
router = APIRouter(prefix="/api", tags=["Config"])

# Compute project root robustly (repo root). This file lives at:
# quantflow/src/quantflow/web/api/config.py
# Parents sequence from this file upwards leads to the repo root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[3]
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "quantflow.yaml"


@router.get("/config")
def get_system_config() -> Dict[str, Any]:
    """Get system configuration (read-only).

    Returns a dictionary payload. On error, returns an object with an "error" field
    and may include additional diagnostics.
    """
    import yaml

    if not CONFIG_PATH.exists():
        return {"error": "Config file not found", "path": str(CONFIG_PATH)}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:  # pragma: no cover - defensive error handling
        return {"error": "Invalid config file", "detail": str(exc), "path": str(CONFIG_PATH)}

    # Build a stable, documented subset of the config payload
    return {
        "markets": data.get("data", {}).get("markets", {}),
        "defaults": data.get("data", {}).get("defaults", {}),
        "lookback": data.get("lookback", {}),
        "yfinance": data.get("yfinance", {}),
        "web": data.get("web", {}),
        # Display a user-friendly path; prefer a path relative to PROJECT_ROOT when possible
        "filePath": _display_config_path(CONFIG_PATH, PROJECT_ROOT),
    }


@router.get("/strategies")
def get_strategies():
    """Get available strategy list."""
    try:
        from quantflow.orchestration.registry import STRATEGY_REGISTRY

        strategy_info = []
        for sid, cls in STRATEGY_REGISTRY.items():
            name = cls.__name__
            is_buy = "Buy" in name
            strategy_info.append({
                "id": sid,
                "name": name,
                "type": "buy" if is_buy else "sell",
            })

        return {"strategies": strategy_info}
    except ImportError:
        return {"strategies": [], "error": "Strategy registry not available"}


def _display_config_path(config_path: Path, project_root: Path) -> str:
    """Return a string path for display that is relative to project_root when possible."""
    try:
        return str(config_path.resolve().relative_to(project_root.resolve()))
    except Exception:
        return str(config_path.resolve())
