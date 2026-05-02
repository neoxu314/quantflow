from quantflow.web.config import WebConfig


def test_default_config():
    cfg = WebConfig.load()
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
