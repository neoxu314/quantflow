"""Run tests against detached code and disposable configuration and state."""

import os
import sys
from pathlib import Path
from shutil import copytree, ignore_patterns
from tempfile import TemporaryDirectory

import pytest
from platformdirs import user_cache_dir

from tests.support.network_guard import NETWORK_LOG, install
from tests.support.project import home_environment, prepare_project

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / "tests" / "support"
NETWORK_EVENTS = pytest.StashKey[Path]()
NETWORK_OFFSET = pytest.StashKey[int]()
TEST_PROJECT = pytest.StashKey[Path]()


def pytest_addoption(parser):
    group = parser.getgroup("QuantFlow")
    group.addoption("--live-market", action="store_true", help="Enable live provider tests.")
    group.addoption("--run-browser", action="store_true", help="Enable Web E2E tests.")


def pytest_configure(config):
    temp = TemporaryDirectory(prefix="quantflow-tests-")
    env = pytest.MonkeyPatch()
    config.add_cleanup(temp.cleanup)
    config.add_cleanup(env.undo)

    root = Path(temp.name).resolve()
    home = root / "home"
    project = root / "project"
    source = project / "src"
    # Import defaults from the detached package as well.
    copytree(
        ROOT / "src" / "quantflow",
        source / "quantflow",
        ignore=ignore_patterns("__pycache__", "*.pyc"),
    )
    if any(name == "quantflow" or name.startswith("quantflow.") for name in sys.modules):
        raise pytest.UsageError("Start pytest in a fresh Python process to isolate QuantFlow.")
    env.syspath_prepend(str(source))
    env.setenv("PYTHONPATH", os.pathsep.join((str(SUPPORT), str(source))))
    if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
        env.setenv("PLAYWRIGHT_BROWSERS_PATH", user_cache_dir("ms-playwright", appauthor=False))
    for name, value in home_environment(home).items():
        env.setenv(name, value)
    for name in ("NO_PROXY", "no_proxy"):
        env.setenv(name, "localhost,127.0.0.1,::1", prepend=",")
    if not config.getoption("--live-market"):
        env.delenv("TUSHARE_TOKEN", raising=False)

    event_log = root / "blocked-network.log"
    env.setenv(NETWORK_LOG, str(event_log))
    install(env.setattr)
    config.stash[NETWORK_EVENTS] = event_log
    config.stash[TEST_PROJECT] = project
    prepare_project(project, ROOT)


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    selected, deselected = [], []
    for item in items:
        browser = item.path.is_relative_to(ROOT / "tests" / "web" / "e2e")
        if browser:
            item.add_marker(pytest.mark.browser)
        if (
            browser and not config.getoption("--run-browser") and not config.option.collectonly
        ) or (
            item.get_closest_marker("integration")
            and not config.getoption("--live-market")
            and not config.option.collectonly
        ):
            deselected.append(item)
        else:
            selected.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected


@pytest.fixture(scope="session")
def test_project(pytestconfig):
    return pytestconfig.stash[TEST_PROJECT]


@pytest.fixture(autouse=True)
def isolated_test_environment(test_project, request, monkeypatch):
    monkeypatch.chdir(test_project)
    if request.node.get_closest_marker("integration"):
        monkeypatch.delenv(NETWORK_LOG)
    else:
        monkeypatch.delenv("TUSHARE_TOKEN", raising=False)


def _blocked_hosts(config):
    path = config.stash.get(NETWORK_EVENTS, None)
    if path is None or not path.exists():
        return ""
    with path.open(encoding="utf-8") as events:
        events.seek(config.stash.get(NETWORK_OFFSET, 0))
        hosts = events.read().splitlines()
        config.stash[NETWORK_OFFSET] = events.tell()
    return ", ".join(sorted(set(hosts)))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if hosts := _blocked_hosts(item.config):
        message = f"Offline test attempted outbound network access: {hosts}"
        report.longrepr = f"{report.longrepr}\n{message}" if report.longrepr else message
        report.outcome = "failed"


def pytest_sessionfinish(session, exitstatus):
    if hosts := _blocked_hosts(session.config):
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter:
            reporter.write_line(f"Offline test session attempted outbound network access: {hosts}")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
