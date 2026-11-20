"""Run each Web E2E test against its own project, state directory and loopback server."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
import yaml

from quantflow.config.loader import ConfigLoader

SOURCE_ROOT = Path(__file__).resolve().parents[3]
TEST_WATCHLIST_NAME = "_test_e2e_wl"
TEST_TASK_FILE = "tasks_e2e_test.yaml"

# Legacy test helpers read these names from their module globals. The fixture
# below assigns paths and URLs only after the temporary server is ready.
PROJECT_ROOT = None
SERVER_URL = None

_SERVER = """
import socket
import sys
from pathlib import Path

import uvicorn

home = Path(sys.argv[1])
Path.home = classmethod(lambda cls: home)
from quantflow.web.server import create_app

app = create_app()
with socket.socket() as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", int(sys.argv[2])))
    Path("server.port").write_text(str(sock.getsockname()[1]))
    uvicorn.Server(uvicorn.Config(app)).run(sockets=[sock])
"""


class TestServer:
    __test__ = False

    def __init__(self, root):
        self.root = root
        self.home = root / "home"
        self.port = 0
        self.process = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        port_file = self.root / "server.port"
        port_file.unlink(missing_ok=True)
        env = dict(os.environ, PYTHONPATH=str(self.root / "src"))
        env.pop("TUSHARE_TOKEN", None)
        log_path = self.root / "server.log"
        with log_path.open("ab") as log:
            self.process = subprocess.Popen(
                [sys.executable, "-c", _SERVER, str(self.home), str(self.port)],
                cwd=self.root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            )

        deadline = time.monotonic() + 20
        with httpx.Client(trust_env=False, timeout=0.4) as client:
            while self.process.poll() is None and time.monotonic() < deadline:
                if port_file.exists() and (port := port_file.read_text()):
                    self.port = int(port)
                    try:
                        if client.get(f"{self.url}/api/config").is_success:
                            return
                    except httpx.RequestError:
                        pass
                time.sleep(0.05)
        raise RuntimeError(f"E2E Web server did not start:\n{log_path.read_text()[-4000:]}")

    def stop(self):
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()

    def restart(self):
        self.stop()
        self.start()


def _write_fixture(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")


@pytest.fixture
def web_server(tmp_path, request, monkeypatch):
    root = tmp_path / "project"
    shutil.copytree(
        SOURCE_ROOT / "src" / "quantflow", root / "src" / "quantflow",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    config = ConfigLoader()._get_defaults()
    config.update({
        "web": {"host": "127.0.0.1", "port": 8080},
        "lookback": {"calendar_multiplier": 2, "buffer_days": 30},
        "tushare": {"token": ""},
        "yfinance": {"batch": {"chunk_size": 35, "sleep_min": 0, "sleep_max": 0}},
    })
    _write_fixture(root / "config" / "quantflow.yaml", config)
    shutil.copyfile(SOURCE_ROOT / "config" / "indicators.yaml", root / "config" / "indicators.yaml")
    _write_fixture(root / "watchlists" / "djia.yaml", {
        "name": "DJIA", "items": [{"code": "AAPL.US", "name": "Apple"}],
    })
    _write_fixture(root / "config" / "tasks_test.yaml", {"tasks": [{
        "name": "djia", "watchlist": "watchlists/djia.yaml",
        "strategies": ["daily_bull_mid_range", "daily_bull_oversold"],
    }]})
    server = TestServer(root)
    try:
        server.start()
        state = server.home / ".quantflow"
        bindings = {
            "PROJECT_ROOT": root,
            "SERVER_URL": server.url,
            "DB_PATH": state / "runs.db",
            "CHECKPOINT_DIR": state / "checkpoints",
            "TEST_TMP_DIR": state / "e2e_browse_test",
            "TASK_CONFIG_PATH": root / "config" / TEST_TASK_FILE,
            "WATCHLIST_YAML": root / "watchlists" / f"{TEST_WATCHLIST_NAME}.yaml",
        }
        for name, value in bindings.items():
            if hasattr(request.module, name):
                monkeypatch.setattr(request.module, name, value)
        yield server
    finally:
        server.stop()


@pytest.fixture(autouse=True)
def e2e_url(web_server):
    return web_server.url
