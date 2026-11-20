"""Exercise the installed wheel from outside the source tree."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.support.project import home_environment


def test_installed_wheel_serves_web_assets(test_project, tmp_path):
    root = Path(__file__).resolve().parents[1]
    build = tmp_path / "build"
    shutil.copytree(
        test_project / "src", build / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    for filename in ("pyproject.toml", "README.md"):
        shutil.copyfile(root / filename, build / filename)

    wheels = tmp_path / "wheels"
    installed = tmp_path / "installed"
    env = dict(os.environ, PIP_DISABLE_PIP_VERSION_CHECK="1")
    _run(
        [
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-index",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheels),
            ".",
        ],
        build,
        env,
    )
    (wheel,) = wheels.glob("quantflow-*.whl")
    _run(
        ["-m", "pip", "install", "--no-deps", "--no-index", "--target", str(installed), str(wheel)],
        tmp_path,
        env,
    )

    # Keep the offline child-process guard, and remove the editable source path.
    env.update(
        PYTHONPATH=os.pathsep.join((str(root / "tests/support"), str(installed))),
        **home_environment(tmp_path / "home"),
    )
    _run(
        [
            "-c",
            """
import sys
from importlib.metadata import distribution
from pathlib import Path

import quantflow
from fastapi.testclient import TestClient
from quantflow.web.server import create_app

assert Path(quantflow.__file__).resolve().is_relative_to(Path(sys.argv[1])), quantflow.__file__
scripts = {entry.name: entry for entry in distribution("quantflow").entry_points
           if entry.group == "console_scripts"}
for name in ("quantflow-scan", "quantflow-monitor", "quantflow-tasks", "quantflow-web"):
    assert callable(scripts[name].load()), name

with TestClient(create_app()) as client:
    page = client.get("/")
    assert page.status_code == 200, page.text
    assert "text/html" in page.headers["content-type"]
    assert "/app.js" in page.text
    for path in ("/app.js", "/utils.js"):
        asset = client.get(path)
        assert asset.status_code == 200, path
        assert "javascript" in asset.headers["content-type"], path
        assert asset.content, path
""",
            str(installed),
        ],
        tmp_path,
        env,
    )


def _run(args, cwd, env):
    result = subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
