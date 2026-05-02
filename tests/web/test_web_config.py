"""Tests for web config loader."""
from quantflow.web.config import WebConfig


def test_default_config():
    """Default config uses 127.0.0.1:8080."""
    cfg = WebConfig.load("/nonexistent/path/quantflow.yaml")
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8080


def test_load_from_yaml(test_quantflow_yaml):
    """Loads config from yaml file."""
    cfg = WebConfig.load(str(test_quantflow_yaml))
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9999
