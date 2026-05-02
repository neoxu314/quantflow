from __future__ import annotations

from typing import Dict, Any, Optional

from fastapi import APIRouter
from quantflow.orchestration.registry import STRATEGY_REGISTRY
from quantflow.web.config import WebConfig

# Optional path to override the default config lookup (used in tests)
CONFIG_PATH: Optional[str] = None

# Router for web API related to config and strategies
router = APIRouter()


@router.get("/api/strategies")
async def get_strategies() -> Dict[str, Any]:
    """Return available trading strategies from the registry."""
    # Expose the registered strategy identifiers. Tests only require the route exists,
    # but returning a helpful mapping makes the API usable in real scenarios.
    return {"strategies": list(STRATEGY_REGISTRY.keys())}


@router.get("/api/config")
async def get_config() -> Dict[str, Any]:
    """Return system configuration as defined in quantflow.yaml (read-only).

    If the CONFIG_PATH is set and the file cannot be found, return an error payload
    with an "error" key to keep the response structure consistent for tests.
    """
    try:
        cfg = WebConfig.load(path=CONFIG_PATH)
        return {"host": cfg.host, "port": cfg.port}
    except FileNotFoundError as exc:
        return {"error": str(exc)}
