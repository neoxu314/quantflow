"""Web API routes for config and strategies."""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict

import yaml
from fastapi import APIRouter, HTTPException

# Router for API endpoints under /api
router = APIRouter(prefix="/api", tags=["Config"])

# Compute project root robustly (repo root). This file lives at:
# quantflow/src/quantflow/web/api/config.py
# Parents sequence from this file upwards leads to the repo root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "quantflow.yaml"


@router.get("/config")
def get_system_config() -> Dict[str, Any]:
    """Get system configuration (read-only).

    Returns a dictionary payload. On error, returns an object with an "error" field
    and may include additional diagnostics.
    """
    if not CONFIG_PATH.exists():
        return {"error": "Config file not found", "path": str(CONFIG_PATH)}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        return {"error": "Invalid config file", "detail": str(exc), "path": str(CONFIG_PATH)}

    # Build a stable, documented subset of the config payload
    return {
        "raw": data,
        "markets": data.get("data", {}).get("markets", {}),
        "defaults": data.get("data", {}).get("defaults", {}),
        "lookback": data.get("lookback", {}),
        "yfinance": data.get("yfinance", {}),
        "yahooquery": data.get("yahooquery", {}),
        "web": data.get("web", {}),
        "tushare": data.get("tushare", {"token": ""}),
        "logging": data.get("logging", {"level": "INFO", "format": ""}),
        "filePath": _display_config_path(CONFIG_PATH, PROJECT_ROOT),
    }


@router.put("/config")
def update_system_config(payload: Dict[str, Any]):
    """Update system configuration - writes to quantflow.yaml."""
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="Config file not found")

    raw = payload.get("raw", {})
    config = {
        "version": raw.get("version", "0.1.0"),
        "data": raw.get("data", {}),
        "tushare": raw.get("tushare", {"token": ""}),
        "logging": raw.get("logging", {
            "level": "INFO",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        }),
        "lookback": raw.get("lookback", {}),
        "yfinance": raw.get("yfinance", {}),
        "yahooquery": raw.get("yahooquery", {}),
        "web": raw.get("web", {}),
    }

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return {"success": True, "message": "Config saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save config: {str(e)}")


@router.get("/strategies")
def get_strategies():
    """Get available strategy list."""
    try:
        from quantflow.orchestration.registry import STRATEGY_REGISTRY

        strategy_info = []
        for sid, cls in STRATEGY_REGISTRY.items():
            name = cls.__name__
            is_buy = "Buy" in name
            # Extract docstring description for the frontend/help
            description = inspect.cleandoc(cls.__doc__ or "")
            strategy_info.append({
                "id": sid,
                "name": name,
                "type": "buy" if is_buy else "sell",
                "description": description,
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
