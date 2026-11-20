from quantflow.web.config import WebConfig
import yaml


def test_default_config_without_web_settings(web_config_yaml_path):
    with open(web_config_yaml_path, "w", encoding="utf-8") as config:
        config.write("{}")
    cfg = WebConfig.load(web_config_yaml_path)
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8080


def test_load_from_yaml(web_config_yaml_path):
    yaml_path = web_config_yaml_path
    # Write a small YAML config
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write("host: 0.0.0.0\nport: 8081\n")
    cfg = WebConfig.load(yaml_path)
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 8081


def test_load_from_yaml_nested_keys(web_config_yaml_path):
    """Verify WebConfig correctly reads nested web settings written by the UI.

    The Settings UI writes to config/quantflow.yaml with a nested structure
    (e.g., web: { port: ... }). WebConfig.load() must handle this structure
    to ensure that configuration changes made via the UI take effect on restart.
    """
    yaml_path = web_config_yaml_path
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump({
            "web": {"host": "0.0.0.0", "port": 9090},
            "data": {"markets": {}},
        }, f)

    cfg = WebConfig.load(yaml_path)
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 9090
