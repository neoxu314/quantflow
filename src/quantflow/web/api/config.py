"""System config and strategies API."""
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["Config"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "quantflow.yaml"


@router.get("/config")
def get_system_config():
    """Get system configuration (read-only)."""
    import yaml

    if not CONFIG_PATH.exists():
        return {"error": "Config file not found", "path": str(CONFIG_PATH)}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return {
        "markets": data.get("data", {}).get("markets", {}),
        "defaults": data.get("data", {}).get("defaults", {}),
        "lookback": data.get("lookback", {}),
        "yfinance": data.get("yfinance", {}),
        "web": data.get("web", {}),
        "filePath": str(CONFIG_PATH.relative_to(PROJECT_ROOT)),
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
