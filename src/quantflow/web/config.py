from __future__ import annotations

import os
from typing import Optional
import yaml
from pathlib import Path


class WebConfig:
    """Lightweight web configuration loader.

    Default values:
    - host: 127.0.0.1
    - port: 8080
    """

    host: str = "127.0.0.1"
    port: int = 8080

    @classmethod
    def load(cls, path: Optional[str] = None) -> "WebConfig":
        """Load web configuration from a YAML file.

        If no path is provided, attempt to locate a bundled quantflow.yaml in the
        repository/package (config/quantflow.yaml). If found, it will be used to
        override defaults. If no file can be found, defaults are returned.
        If a path is provided but does not exist, a FileNotFoundError is raised.
        """
        cfg = cls()

        # Determine YAML path: explicit path takes precedence; otherwise try default
        yaml_path: Optional[str] = None
        if path:
            yaml_path = path
        else:
            # Resolve a sensible default path relative to this module's location:
            # repo_ROOT/config/quantflow.yaml
            default_candidate = Path(__file__).resolve().parents[3] / "config" / "quantflow.yaml"
            if default_candidate.exists():
                yaml_path = str(default_candidate)

        if yaml_path:
            p = Path(yaml_path)
            if not p.exists():
                raise FileNotFoundError(str(p))
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                if "host" in data:
                    cfg.host = str(data["host"])
                if "port" in data:
                    cfg.port = int(data["port"])
        return cfg
