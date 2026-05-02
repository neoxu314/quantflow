import pathlib
import pytest


@pytest.fixture
def web_config_yaml_path(tmp_path: pathlib.Path) -> str:
    # Provide a fresh path for tests to write to
    path = tmp_path / "config" / "web.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)
