from __future__ import annotations

import os
from typing import Optional
import yaml


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
        """Load web configuration from a YAML file if provided.

        If no path is provided, returns a WebConfig with default values.
        If a path is provided but does not exist, a FileNotFoundError is raised.
        """
        cfg = cls()
        if path:
            if not os.path.exists(path):
                raise FileNotFoundError(path)
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                if "host" in data:
                    cfg.host = str(data["host"])
                if "port" in data:
                    cfg.port = int(data["port"])
        return cfg
