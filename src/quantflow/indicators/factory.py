"""IndicatorFactory
Dynamically instantiate indicators using configuration overrides.
"""
from __future__ import annotations

import importlib
import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

import yaml

_run_config = ContextVar("quantflow_indicator_config", default=None)


class IndicatorFactory:
    _config: Dict[str, Any] | None = None
    _class_map: Dict[str, Any] = {}
    _config_stamp = None

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        scoped = _run_config.get()
        if scoped is not None:
            return scoped
        config_path = Path(__file__).resolve().parents[3] / "config" / "indicators.yaml"
        stamp = config_path.stat().st_mtime_ns if config_path.exists() else None
        if IndicatorFactory._config_stamp is not None and stamp != IndicatorFactory._config_stamp:
            IndicatorFactory._config = None
        if IndicatorFactory._config is None:
            root = Path(__file__).resolve().parents[3]
            config_path = root / "config" / "indicators.yaml"
            if not config_path.exists():
                IndicatorFactory._config = {}
            else:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                # Support both {indicators: {...}} and direct mapping {name: {...}}
                if isinstance(data, dict) and "indicators" in data:
                    IndicatorFactory._config = data["indicators"] or {}
                else:
                    IndicatorFactory._config = data
            IndicatorFactory._config_stamp = stamp
        return IndicatorFactory._config or {}

    @staticmethod
    @contextmanager
    def snapshot():
        """UI configuration edits apply to the next run, never half of this one."""
        token = _run_config.set(deepcopy(IndicatorFactory._load_config()))
        try:
            yield
        finally:
            _run_config.reset(token)

    @staticmethod
    def _get_class_by_name(name: str):
        if name in IndicatorFactory._class_map:
            return IndicatorFactory._class_map[name]

        candidates = [name]
        # Common alias forms used in indicators
        candidates += [f"{name}Indicator", f"{name}Ind"]

        for module_name in ("quantflow.indicators.standard", "quantflow.indicators.custom"):
            try:
                mod = importlib.import_module(module_name)
            except Exception:
                continue
            for cand in candidates:
                if hasattr(mod, cand):
                    cls = getattr(mod, cand)
                    IndicatorFactory._class_map[name] = cls
                    return cls
        return None

    @staticmethod
    def _get_init_defaults(cls) -> Dict[str, Any]:
        sig = inspect.signature(cls.__init__)
        defaults: Dict[str, Any] = {}
        # skip 'self'
        params = list(sig.parameters.values())[1:]
        for p in params:
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                continue
            if p.default is not inspect._empty:
                defaults[p.name] = p.default
        return defaults

    @staticmethod
    def create(name: str) -> Any:
        cfg = IndicatorFactory._load_config()
        entry = cfg.get(name) if isinstance(cfg, dict) else None
        if entry is None:
            raise ValueError(f"Indicator '{name}' not configured in config/indicators.yaml")
        enabled = True
        if isinstance(entry, dict):
            enabled = entry.get("enabled", True)
        if not enabled:
            raise ValueError(f"Indicator '{name}' is disabled in config.")

        cls = IndicatorFactory._get_class_by_name(name)
        if cls is None:
            raise ValueError(f"Indicator class for '{name}' not found in standard or custom modules.")

        defaults = IndicatorFactory._get_init_defaults(cls)
        overrides: Dict[str, Any] = {}
        if isinstance(entry, dict) and isinstance(entry.get("params"), dict):
            overrides = entry["params"]
        final_kwargs = {**defaults, **overrides}
        return cls(**final_kwargs)
