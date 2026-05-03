"""Library API endpoints for QuantFlow web UI (Phase 1).

Provides endpoints to expose registered strategies and available indicators.
"""
from __future__ import annotations

import inspect
import yaml
from pathlib import Path
from fastapi import APIRouter, HTTPException
from typing import Any, Dict, List

# Router for API endpoints under /api/library
router = APIRouter(prefix="/api/library", tags=["Library"])

PROJECT_ROOT: Path = Path(__file__).resolve().parents[4]
INDICATORS_YAML: Path = PROJECT_ROOT / "config" / "indicators.yaml"


@router.get("/strategies")
def get_library_strategies():
    """Return detailed info about all registered strategies.

    Each entry contains:
- id: registry key
- name: class name
- type: buy or sell
- description: class docstring (cleandoc)
- min_lookback_days: lookback required by the strategy
- required_indicators: list of indicator names used by the strategy
    """
    try:
        from quantflow.orchestration.registry import STRATEGY_REGISTRY

        result: List[Dict[str, Any]] = []
        for sid, cls in STRATEGY_REGISTRY.items():
            name = cls.__name__
            is_buy = "Buy" in name
            # Use class docstring for description if provided
            description = inspect.cleandoc(cls.__doc__ or "")
            # Instantiate with defaults where possible
            try:
                instance = cls()
            except Exception:
                instance = None

            min_lookback = instance.get_lookback_bars() if instance else 1
            # Gather required indicators (names)
            req_inds: List[str] = []
            if instance:
                for ind in instance.get_required_indicators():
                    try:
                        req_inds.append(ind.name)
                    except Exception:
                        pass

            result.append({
                "id": sid,
                "name": name,
                "type": "buy" if is_buy else "sell",
                "description": description,
                "min_lookback_days": min_lookback,
                "required_indicators": req_inds,
            })

        return {"strategies": result}
    except ImportError:
        return {"strategies": [], "error": "Strategy registry not available"}


@router.get("/indicators")
def get_library_indicators():
    """List all indicators discovered from indicators.__all__ in standard and custom packages."""
    indicators: List[Dict[str, Any]] = []
    seen = set()

    # Load YAML config once per request (if present) for overrides
    config: Dict[str, Any] = {}
    if INDICATORS_YAML.exists():
        with open(INDICATORS_YAML, "r", encoding="utf-8") as f:
            ydata = yaml.safe_load(f) or {}
        if isinstance(ydata, dict) and "indicators" in ydata:
            config = ydata.get("indicators", {})

    # Helper to process a module's indicators
    def process_module(module, category: str):
        nonlocal indicators, seen
        for name in getattr(module, "__all__", []):
            if name in seen:
                continue
            seen.add(name)
            cls = getattr(module, name)
            try:
                inst = cls()
            except Exception:
                # If cannot instantiate with defaults, skip metadata collection
                continue

            # Start with class defaults, then apply YAML overrides if present
            params = getattr(inst, "params", {})
            ind_key = getattr(inst, "name", name)
            ind_config = config.get(ind_key, {})
            if isinstance(ind_config, dict) and isinstance(ind_config.get("params"), dict):
                params = {**params, **ind_config["params"]}

            indicators.append({
                "name": inst.name,
                "category": category,
                "params": params,
                "required_fields": inst.get_required_fields(),
                "output_fields": inst.get_output_fields(),
                "lookback_bars": getattr(inst, "lookback_bars", 0),
            })

    # Import modules lazily to avoid import side-effects on startup
    try:
        from quantflow.indicators import standard as standard_indicators
        from quantflow.indicators import custom as custom_indicators
        process_module(standard_indicators, "standard")
        process_module(custom_indicators, "custom")
    except Exception:
        # If anything goes wrong, return what we have
        pass

    return {"indicators": indicators}


@router.put("/indicators/params")
def update_indicator_params(payload: Dict[str, Any]):
    """Update parameters for a given indicator and persist to YAML.

    Payload: { name: "KDJ", params: { ... } }
    """
    name = payload.get("name")
    params = payload.get("params", {})
    if not name:
        raise HTTPException(status_code=400, detail="Indicator name is required")

    try:
        if INDICATORS_YAML.exists():
            with open(INDICATORS_YAML, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {"indicators": {}}

        # Ensure nested structure exists
        if "indicators" not in data:
            data = {"indicators": data}
        existing = data["indicators"].get(name, {})
        if isinstance(existing, dict):
            existing["params"] = params
            data["indicators"][name] = existing
        else:
            data["indicators"][name] = {"enabled": True, "params": params}
        with open(INDICATORS_YAML, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        # Invalidate IndicatorFactory cache lazily to reflect new overrides
        from quantflow.indicators.factory import IndicatorFactory
        IndicatorFactory._config = None
        IndicatorFactory._class_map.clear()
        return {"success": True, "message": "指标参数已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update indicator params: {str(e)}")
