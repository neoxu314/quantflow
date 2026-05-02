"""Web UI configuration loader."""
from pathlib import Path
from typing import Optional


class WebConfig:
    """Web UI configuration from quantflow.yaml."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "WebConfig":
        """Load web config from quantflow.yaml."""
        import yaml

        defaults = cls()

        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "quantflow.yaml"

        path = Path(config_path)
        if not path.exists():
            return defaults

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        web_cfg = data.get("web", {})
        return cls(
            host=web_cfg.get("host", defaults.host),
            port=int(web_cfg.get("port", defaults.port)),
        )
