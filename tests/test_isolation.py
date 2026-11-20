"""Keep test isolation from regressing when fixtures or entry points change."""

import os
import subprocess
import sys

from tests.support.network_guard import NETWORK_LOG


def test_offline_child_uses_test_project_and_blocks_socket_and_curl(test_project, tmp_path):
    event_log = tmp_path / "blocked.log"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os
import socket
import sys
from pathlib import Path

import quantflow
from curl_cffi import requests
from quantflow.web.engine.run_history import DB_PATH

project = Path(sys.argv[1])
assert Path(quantflow.__file__).is_relative_to(project)
assert Path.cwd() == project
assert DB_PATH == Path(os.environ["HOME"]) / ".quantflow" / "runs.db"
assert DB_PATH.is_relative_to(project.parent)

with socket.socket() as mock_provider:
    mock_provider.bind(("127.0.0.1", 0))
    mock_provider.listen()
    with socket.create_connection(mock_provider.getsockname(), timeout=1):
        pass

for request in (
    lambda: socket.create_connection(("192.0.2.1", 80), timeout=1),
    lambda: requests.get("https://provider.invalid/data?token=test-only", timeout=1),
):
    try:
        request()
    except OSError as error:
        assert "Offline QuantFlow test blocked" in str(error), error
    else:
        raise AssertionError("Offline request was not blocked")
""",
            str(test_project),
        ],
        env=dict(os.environ, **{NETWORK_LOG: str(event_log)}),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert event_log.read_text().splitlines() == ["'192.0.2.1'", "'provider.invalid'"]
