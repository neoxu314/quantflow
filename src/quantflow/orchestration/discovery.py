"""Discovery utilities for indicators.

This module introspects available indicator classes from standard and custom
packages and returns metadata suitable for a library panel UI or tooling.
"""
from __future__ import annotations

import inspect
from importlib import import_module
from typing import Any, Dict, List


def _collect_from_module(module, category: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    __all__ = getattr(module, "__all__", []) or []
    for name in __all__:
        # Resolve class; support aliases like 'KDJ' -> KDJIndicator
        cls = None
        if hasattr(module, name):
            cls = getattr(module, name)
        else:
            for cand in (f"{name}Indicator", f"{name}Ind", name):
                if hasattr(module, cand):
                    cls = getattr(module, cand)
                    break
        if cls is None:
            continue
        # Try default constructor to extract metadata
        try:
            inst = cls()
        except Exception:
            inst = None
        # Params: derive from __init__ defaults
        params: Dict[str, Any] = {}
        try:
            sig = inspect.signature(cls.__init__)
            for pname, p in list(sig.parameters.items())[1:]:
                if p.default is not inspect._empty:
                    params[pname] = p.default
        except Exception:
            pass
        required_fields = inst.get_required_fields() if inst is not None else []
        output_fields = inst.get_output_fields() if inst is not None else []
        lookback_bars = getattr(inst, "lookback_bars", None) if inst is not None else None

        name = getattr(inst, "name", name) if inst is not None else name
        results.append(
            {
                "name": name,
                "category": category,
                "params": params,
                "required_fields": list(required_fields) if required_fields is not None else [],
                "output_fields": list(output_fields) if output_fields is not None else [],
                "lookback_bars": lookback_bars,
            }
        )
    return results


def discover_indicators() -> List[Dict[str, Any]]:
    """Return metadata for all discovered indicators.

    Scans both standard and custom indicator exports and returns a uniform list
    of dictionaries containing: name, category, params, required_fields,
    output_fields, lookback_bars.
    """
    meta: List[Dict[str, Any]] = []
    for module_name, category in (("quantflow.indicators.standard", "standard"),
                                  ("quantflow.indicators.custom", "custom")):
        mod = import_module(module_name)
        meta.extend(_collect_from_module(mod, category))
    return meta
