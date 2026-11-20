"""Run each Web E2E test against its own project, state directory and loopback server."""

import os
import shutil
import subprocess
import sys
import time

import httpx
import pytest

from tests.support.project import home_environment, prepare_project

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

from quantflow.web.server import create_app

if sys.argv[2] == "replay":
    from replay_market import install_replay

    install_replay(Path.cwd())

app = create_app()
with socket.socket() as sock:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", int(sys.argv[1])))
    Path("server.port").write_text(str(sock.getsockname()[1]))
    uvicorn.Server(uvicorn.Config(app)).run(sockets=[sock])
"""


class TestServer:
    __test__ = False

    def __init__(self, root, *, replay=True):
        self.root = root
        self.home = root / "home"
        self.port = 0
        self.process = None
        self.replay = replay

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        port_file = self.root / "server.port"
        port_file.unlink(missing_ok=True)
        pythonpath = os.pathsep.join((str(self.root / "src"), os.environ["PYTHONPATH"]))
        env = dict(os.environ, PYTHONPATH=pythonpath, **home_environment(self.home))
        log_path = self.root / "server.log"
        with log_path.open("ab") as log:
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _SERVER,
                    str(self.port),
                    "replay" if self.replay else "live",
                ],
                cwd=self.root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
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


@pytest.fixture
def web_server(tmp_path, request, monkeypatch, test_project):
    root = tmp_path / "project"
    shutil.copytree(
        test_project / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    prepare_project(root, test_project)
    server = TestServer(root, replay=request.node.get_closest_marker("integration") is None)
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


@pytest.fixture
def page(page):
    # The application toggles this class for panels and dialogs. Keep browser
    # behavior deterministic when the external Tailwind script is unavailable.
    page.route(
        "https://cdn.tailwindcss.com/**",
        lambda route: route.fulfill(
            content_type="application/javascript",
            body="document.head.append(Object.assign(document.createElement('style'), "
            "{textContent: '.hidden {display:none!important}'}));",
        ),
    )
    return page


@pytest.fixture
def client(e2e_url):
    with httpx.Client(base_url=e2e_url, timeout=4, trust_env=False) as connection:
        yield connection
