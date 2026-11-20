"""Web API routes for config and strategies."""
from __future__ import annotations

import inspect
from pathlib import Path
from threading import Lock
from typing import Any, Dict

import yaml
from fastapi import APIRouter, HTTPException

from quantflow.artifacts import atomic_text

# Router for API endpoints under /api
router = APIRouter(prefix="/api", tags=["Config"])

# Compute project root robustly (repo root). This file lives at:
# quantflow/src/quantflow/web/api/config.py
# Parents sequence from this file upwards leads to the repo root.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
CONFIG_PATH: Path = PROJECT_ROOT / "config" / "quantflow.yaml"
_config_write_lock = Lock()


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
    except (OSError, yaml.YAMLError):
        return {"error": "Invalid config file", "path": str(CONFIG_PATH)}

    if not isinstance(data, dict) or not isinstance(data.get("tushare", {}), dict):
        return {"error": "Invalid config file", "path": str(CONFIG_PATH)}
    tushare = data.get("tushare", {})
    token_configured = bool(tushare.pop("token", None))
    # The token is write-only through the Web settings.
    return {
        "raw": data,
        "markets": data.get("data", {}).get("markets", {}),
        "defaults": data.get("data", {}).get("defaults", {}),
        "lookback": data.get("lookback", {}),
        "yfinance": data.get("yfinance", {}),
        "yahooquery": data.get("yahooquery", {}),
        "web": data.get("web", {}),
        "tushare": {**tushare, "tokenConfigured": token_configured},
        "logging": data.get("logging", {"console_level": "INFO", "file_enabled": True, "file_level": "DEBUG", "format": ""}),
        "filePath": _display_config_path(CONFIG_PATH, PROJECT_ROOT),
    }


@router.put("/config")
def update_system_config(payload: Dict[str, Any]):
    """Update system configuration - writes to quantflow.yaml."""
    if not CONFIG_PATH.exists():
        raise HTTPException(status_code=404, detail="Config file not found")

    raw = payload.get("raw", {})
    if not isinstance(raw, dict) or not isinstance(raw.get("tushare", {}), dict):
        raise HTTPException(status_code=422, detail="Invalid config payload")
    tushare = dict(raw.get("tushare", {}))
    if "token" in tushare and tushare["token"] is not None and not isinstance(tushare["token"], str):
        raise HTTPException(status_code=422, detail="Invalid Tushare token")
    config = {
        "version": raw.get("version", "0.1.0"),
        "data": raw.get("data", {}),
        "tushare": tushare,
        "logging": raw.get("logging", {
            "console_level": "INFO",
            "file_enabled": True,
            "file_level": "DEBUG",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        }),
        "lookback": raw.get("lookback", {}),
        "yfinance": raw.get("yfinance", {}),
        "yahooquery": raw.get("yahooquery", {}),
        "web": raw.get("web", {}),
    }

    try:
        with _config_write_lock:
            if "token" not in tushare or tushare["token"] == "":
                current = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
                tushare["token"] = current.get("tushare", {}).get("token", "")
            elif tushare["token"] is None:
                tushare["token"] = ""
            atomic_text(
                CONFIG_PATH, yaml.safe_dump(config, allow_unicode=True, sort_keys=False),
                register=False,
            )
        return {"success": True, "message": "Config saved"}
    except (OSError, yaml.YAMLError) as exc:
        raise HTTPException(status_code=500, detail="Failed to save config") from exc


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
