"""Test fixtures for web module."""
import pytest
from pathlib import Path
import tempfile


@pytest.fixture
def config_dir():
    """Create a temporary config directory with test files."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "config").mkdir()
        (tmp_path / "watchlists").mkdir()
        yield tmp_path


@pytest.fixture
def test_quantflow_yaml(config_dir):
    """Create a test quantflow.yaml in temp config dir."""
    yaml_path = config_dir / "config" / "quantflow.yaml"
    yaml_path.write_text(
        "version: '0.1.0'\n"
        "web:\n"
        "  port: 9999\n"
        "  host: '0.0.0.0'\n",
        encoding="utf-8",
    )
    return yaml_path
