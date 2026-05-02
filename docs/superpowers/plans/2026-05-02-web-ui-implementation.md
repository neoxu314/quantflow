# QuantFlow Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional web-based UI to QuantFlow for managing watchlists and tasks visually, with zero intrusion to existing CLI/system.

**Architecture:** FastAPI serves a static SPA and REST APIs. Watchlist/Task APIs read/write existing YAML files directly. CLI gets a new `web` subcommand. TypeScript frontend runs browser-native (no build step).

**Tech Stack:** Python (FastAPI, uvicorn, PyYAML), TypeScript (ES Module), HTML, Tailwind CSS (CDN)

**Key constraints:**
- DO NOT modify existing YAML file formats
- DO NOT modify existing data models (Watchlist, TaskConfig, etc.)
- All new code lives in `src/quantflow/web/` except CLI routing and config additions

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/quantflow/web/__init__.py` | Package init |
| Create | `src/quantflow/web/config.py` | Load web config (port, host) from quantflow.yaml |
| Create | `src/quantflow/web/server.py` | FastAPI app factory, route registration, server startup with auto-open browser |
| Create | `src/quantflow/web/api/__init__.py` | API package init |
| Create | `src/quantflow/web/api/config.py` | GET /api/config, GET /api/strategies |
| Create | `src/quantflow/web/api/watchlists.py` | Watchlist CRUD + search APIs |
| Create | `src/quantflow/web/api/tasks.py` | Task CRUD APIs (multi-file aware) |
| Create | `src/quantflow/web/static/index.html` | SPA with tabs for Watchlists/Tasks/Settings |
| Create | `src/quantflow/web/static/app.ts` | Browser-native TypeScript app logic |
| Modify | `src/quantflow/cli.py` | Add `web()` function + routing |
| Modify | `config/quantflow.yaml` | Add `web:` config section |
| Modify | `pyproject.toml` | Add fastapi, uvicorn[standard] deps |
| Create | `tests/web/conftest.py` | Test fixtures (temp dirs, test client) |
| Create | `tests/web/test_config_api.py` | Tests for config API |
| Create | `tests/web/test_watchlist_api.py` | Tests for watchlist API |
| Create | `tests/web/test_task_api.py` | Tests for task API |
| Create | `tests/web/test_web_config.py` | Tests for web config loader |

---

## Phase 1: Project Setup + Web Config

### Task 1: Dependencies + Web Config Module

#### Step 1: Add web dependencies to pyproject.toml

Read current `pyproject.toml` and add `fastapi` and `uvicorn[standard]` to dependencies:

```python
# In pyproject.toml dependencies array, add:
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
```

The dependencies block becomes:
```toml
dependencies = [
    "pandas>=2.0.0",
    "numpy>=1.24.0",
    "baostock>=0.8.9",
    "tushare>=1.3.0",
    "akshare>=1.10.0",
    "yfinance>=0.2.30",
    "pyyaml>=6.0",
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
]
```

#### Step 2: Add web section to quantflow.yaml

Append to `config/quantflow.yaml`:
```yaml
web:
  port: 8080
  host: "127.0.0.1"
```

#### Step 3: Create web package init

Create `src/quantflow/web/__init__.py`:
```python
"""QuantFlow Web UI - optional web interface for watchlist and task management."""
```

#### Step 4: Create web config loader

Create `src/quantflow/web/config.py`:
```python
"""Web UI configuration loader."""
from pathlib import Path
from typing import Optional


class WebConfig:
    """Web UI configuration from quantflow.yaml."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080):
        self.host = host
        self.port = port

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "WebConfig":
        """Load web config from quantflow.yaml."""
        import yaml

        defaults = cls()

        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config" / "quantflow.yaml"

        path = Path(config_path)
        if not path.exists():
            return defaults

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        web_cfg = data.get("web", {})
        return cls(
            host=web_cfg.get("host", defaults.host),
            port=int(web_cfg.get("port", defaults.port)),
        )
```

#### Step 5: Write web config tests

Create `tests/web/conftest.py`:
```python
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
```

Create `tests/web/__init__.py`:
```python
```

Create `tests/web/test_web_config.py`:
```python
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
```

#### Step 6: Install deps and run tests

```bash
pip install -e . && pytest tests/web/test_web_config.py -v
```
Expected: All 2 tests pass.

#### Step 7: Commit

```bash
git add pyproject.toml config/quantflow.yaml src/quantflow/web/ tests/web/
git commit -m "feat(web): add web config loader and dependencies"
```

---

## Phase 2: System Config API + Strategy List

### Task 2: Config API

#### Step 1: Create API package init

Create `src/quantflow/web/api/__init__.py`:
```python
"""Web API routes."""
```

#### Step 2: Create config API module

Create `src/quantflow/web/api/config.py`:
```python
"""System config and strategies API."""
from pathlib import Path
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["Config"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "quantflow.yaml"


@router.get("/config")
def get_system_config():
    """Get system configuration (read-only)."""
    import yaml

    if not CONFIG_PATH.exists():
        return {"error": "Config file not found", "path": str(CONFIG_PATH)}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return {
        "markets": data.get("data", {}).get("markets", {}),
        "defaults": data.get("data", {}).get("defaults", {}),
        "lookback": data.get("lookback", {}),
        "yfinance": data.get("yfinance", {}),
        "web": data.get("web", {}),
        "filePath": str(CONFIG_PATH.relative_to(PROJECT_ROOT)),
    }


@router.get("/strategies")
def get_strategies():
    """Get available strategy list."""
    try:
        from quantflow.orchestration.registry import STRATEGY_REGISTRY
        from quantflow.strategies.base import StrategyBase

        strategy_info = []
        for sid, cls in STRATEGY_REGISTRY.items():
            name = cls.__name__
            is_buy = "Buy" in name
            strategy_info.append({
                "id": sid,
                "name": name,
                "type": "buy" if is_buy else "sell",
            })

        return {"strategies": strategy_info}
    except ImportError:
        return {"strategies": [], "error": "Strategy registry not available"}
```

#### Step 3: Write config API tests

Create `tests/web/test_config_api.py`:
```python
"""Tests for config API."""
import pytest
from pathlib import Path
from unittest.mock import patch


def test_get_strategies_available():
    """Returns strategies from registry."""
    from quantflow.web.api.config import router

    # Check that the /strategies endpoint handler exists
    routes = [r.path for r in router.routes]
    assert "/api/strategies" in routes


def test_get_config_not_found(tmp_path, monkeypatch):
    """Returns error when config file not found."""
    from quantflow.web.api import config as config_module

    fake_path = tmp_path / "config" / "nonexistent.yaml"
    with patch.object(config_module, "CONFIG_PATH", fake_path):
        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(config_module.router)
        client = TestClient(app)
        resp = client.get("/api/config")

        assert resp.status_code == 200
        assert "error" in resp.json()
```

#### Step 4: Run tests

```bash
pytest tests/web/test_config_api.py -v
```
Expected: All tests pass.

#### Step 5: Commit

```bash
git add src/quantflow/web/api/__init__.py src/quantflow/web/api/config.py tests/web/test_config_api.py
git commit -m "feat(web): add config and strategies API endpoints"
```

---

## Phase 3: Watchlist API

### Task 3: Watchlist CRUD API

#### Step 1: Create watchlist API module

Create `src/quantflow/web/api/watchlists.py`:
```python
"""Watchlist CRUD API."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api", tags=["Watchlists"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
WATCHLISTS_DIR = PROJECT_ROOT / "watchlists"


class WatchlistItemModel(BaseModel):
    code: str
    name: Optional[str] = None
    tags: List[str] = []
    weight: float = 1.0
    notes: str = ""


class WatchlistModel(BaseModel):
    name: str
    description: str = ""
    items: List[WatchlistItemModel] = []


class WatchlistSummary(BaseModel):
    filename: str
    name: str
    itemCount: int
    path: str


class SearchResult(BaseModel):
    code: str
    found: bool
    inLists: List[str] = []


def _ensure_watchlists_dir():
    """Ensure watchlists directory exists."""
    WATCHLISTS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/watchlists", response_model=List[WatchlistSummary])
def list_watchlists():
    """List all watchlist files."""
    _ensure_watchlists_dir()
    import yaml

    summaries = []
    for yfile in sorted(WATCHLISTS_DIR.glob("*.yaml")):
        with open(yfile, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        summaries.append(WatchlistSummary(
            filename=yfile.name,
            name=data.get("name", yfile.stem),
            itemCount=len(data.get("items", [])),
            path=f"watchlists/{yfile.name}",
        ))
    return summaries


@router.get("/watchlists/{filename}")
def get_watchlist(filename: str):
    """Get a single watchlist's contents."""
    import yaml

    filepath = WATCHLISTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Watchlist not found: {filename}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return {
        "filename": filename,
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "items": data.get("items", []),
    }


@router.put("/watchlists/{filename}", status_code=201)
def save_watchlist(filename: str, watchlist: WatchlistModel):
    """Create or replace a watchlist."""
    import yaml

    if not filename.endswith(".yaml") and not filename.endswith(".yml"):
        filename += ".yaml"

    # Validate filename is safe (no path traversal)
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = WATCHLISTS_DIR / filename

    data = {
        "name": watchlist.name,
        "description": watchlist.description,
        "items": [
            {"code": item.code, "name": item.name, "tags": item.tags}
            for item in watchlist.items
        ],
    }

    _ensure_watchlists_dir()
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    return {"filename": filename, "itemCount": len(watchlist.items)}


@router.delete("/watchlists/{filename}")
def delete_watchlist(filename: str):
    """Delete a watchlist file."""
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = WATCHLISTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Watchlist not found: {filename}")

    filepath.unlink()
    return {"filename": filename, "deleted": True}


@router.post("/watchlists/search")
def search_stock(query: dict):
    """Search for a stock code across all watchlists."""
    import yaml
    from quantflow.data.base import StockCode

    raw_code = query.get("code", "").strip()
    if not raw_code:
        raise HTTPException(status_code=400, detail="Code is required")

    # Try to auto-complete format
    if "." not in raw_code:
        # Fuzzy match: find watchlist items containing the code
        fuzzy_results = []
        in_lists = []
        _ensure_watchlists_dir()
        for yfile in WATCHLISTS_DIR.glob("*.yaml"):
            with open(yfile, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for item in data.get("items", []):
                item_code = item.get("code", "")
                if raw_code.upper() in item_code.upper():
                    fuzzy_results.append({"code": item_code, "name": item.get("name")})
                    if yfile.name not in in_lists:
                        in_lists.append(yfile.name)
        return {
            "code": raw_code,
            "found": len(fuzzy_results) > 0,
            "inLists": in_lists,
            "fuzzyMatches": fuzzy_results[:20],
        }

    # Exact format search (contains .)
    _ensure_watchlists_dir()
    in_lists = []
    for yfile in WATCHLISTS_DIR.glob("*.yaml"):
        with open(yfile, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for item in data.get("items", []):
            if item.get("code") == raw_code:
                if yfile.name not in in_lists:
                    in_lists.append(yfile.name)
                break

    return {
        "code": raw_code,
        "found": len(in_lists) > 0,
        "inLists": in_lists,
        "fuzzyMatches": [],
    }
```

#### Step 2: Write watchlist API tests

Create `tests/web/test_watchlist_api.py`:
```python
"""Tests for watchlist API endpoints."""
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from quantflow.web.api.watchlists import router, WATCHLISTS_DIR


@pytest.fixture
def app():
    """Create test FastAPI app with watchlist router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(tmp_path, app):
    """Create TestClient with mocked watchlist dir."""
    (tmp_path / "watchlists").mkdir()

    # Mock the WATCHLISTS_DIR
    import quantflow.web.api.watchlists as wl_module
    original = wl_module.WATCHLISTS_DIR
    wl_module.WATCHLISTS_DIR = tmp_path / "watchlists"

    c = TestClient(app)
    yield c

    # Restore original
    wl_module.WATCHLISTS_DIR = original


def test_list_empty_watchlists(client):
    """Returns empty list when no watchlists exist."""
    resp = client.get("/api/watchlists")
    assert resp.status_code == 200
    assert resp.json() == []


def test_save_new_watchlist(client):
    """Can create a new watchlist."""
    resp = client.put("/api/watchlists/test.yaml", json={
        "name": "Test_List",
        "description": "Test watchlist",
        "items": [
            {"code": "002594.SZ", "name": "比亚迪", "tags": ["Personal"]},
        ],
    })
    assert resp.status_code == 201
    assert resp.json()["itemCount"] == 1


def test_get_watchlist(client):
    """Can retrieve a watchlist."""
    # First create one
    client.put("/api/watchlists/fetch_test.yaml", json={
        "name": "Fetch_Test",
        "items": [{"code": "NVDA.US", "name": "Nvidia"}],
    })

    resp = client.get("/api/watchlists/fetch_test.yaml")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Fetch_Test"
    assert len(data["items"]) == 1


def test_get_nonexistent_watchlist(client):
    """Returns 404 for missing watchlist."""
    resp = client.get("/api/watchlists/nonexistent.yaml")
    assert resp.status_code == 404


def test_delete_watchlist(client):
    """Can delete a watchlist."""
    # Create
    client.put("/api/watchlists/del_test.yaml", json={
        "name": "Delete_Test",
        "items": [],
    })

    # Delete
    resp = client.delete("/api/watchlists/del_test.yaml")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify gone
    resp = client.get("/api/watchlists/del_test.yaml")
    assert resp.status_code == 404


def test_search_stock_found(client, tmp_path):
    """Search finds stock in watchlists."""
    # Create watchlist with known stock
    wpath = tmp_path / "watchlists"
    wpath.mkdir(exist_ok=True)
    (wpath / "test.yaml").write_text(
        yaml.dump({
            "name": "Test",
            "items": [{"code": "NVDA.US", "name": "Nvidia"}],
        }),
        encoding="utf-8",
    )

    resp = client.post("/api/watchlists/search", json={"code": "NVDA.US"})
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    assert "test.yaml" in resp.json()["inLists"]


def test_search_stock_not_found(client):
    """Search returns found=False for unknown stock."""
    resp = client.post("/api/watchlists/search", json={"code": "FAKE.XX"})
    assert resp.status_code == 200
    assert resp.json()["found"] is False
    assert resp.json()["inLists"] == []


def test_search_fuzzy_match(client, tmp_path):
    """Fuzzy search finds partial matches."""
    wpath = tmp_path / "watchlists"
    wpath.mkdir(exist_ok=True)
    (wpath / "fuzzy.yaml").write_text(
        yaml.dump({
            "name": "Fuzzy_Test",
            "items": [
                {"code": "NVDA.US", "name": "Nvidia"},
                {"code": "TSLA.US", "name": "Tesla"},
            ],
        }),
        encoding="utf-8",
    )

    resp = client.post("/api/watchlists/search", json={"code": "NV"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["found"] is True
    assert isinstance(data["fuzzyMatches"], list)
    assert any(m["code"] == "NVDA.US" for m in data["fuzzyMatches"])


def test_path_traversal_blocked(client):
    """Blocks path traversal attempts."""
    resp = client.put("/api/watchlists/../../etc/passwd.yaml", json={
        "name": "hack",
        "items": [],
    })
    assert resp.status_code == 400
```

#### Step 3: Run tests

```bash
pytest tests/web/test_watchlist_api.py -v
```
Expected: All 9 tests pass.

#### Step 4: Commit

```bash
git add src/quantflow/web/api/watchlists.py tests/web/test_watchlist_api.py
git commit -m "feat(web): add watchlist CRUD and search API endpoints"
```

---

## Phase 4: Task API

### Task 4: Task CRUD API (Multi-file aware)

#### Step 1: Create task API module

Create `src/quantflow/web/api/tasks.py`:
```python
"""Task CRUD API - manages tasks across multiple tasks_*.yaml files."""
import yaml
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["Tasks"])

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


class TaskModel(BaseModel):
    name: str
    watchlist: str
    strategies: List[str] = []
    output: str = "./output"
    days_back: Optional[int] = None


class TaskResponse(BaseModel):
    id: str  # format: filename:task_name
    filename: str
    name: str
    watchlist: str
    strategies: List[str]
    output: str
    days_back: Optional[int]


def _find_task_files() -> List[Path]:
    """Find all tasks_*.yaml files in config directory."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(CONFIG_DIR.glob("tasks*.yaml"))


def load_all_tasks() -> List[TaskResponse]:
    """Load all tasks from all task config files."""
    tasks = []
    for yfile in _find_task_files():
        with open(yfile, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or "tasks" not in data:
            continue
        for task in data["tasks"]:
            tasks.append(TaskResponse(
                id=f"{yfile.name}:{task['name']}",
                filename=yfile.name,
                name=task["name"],
                watchlist=task["watchlist"],
                strategies=task.get("strategies", []),
                output=task.get("output", "./output"),
                days_back=task.get("days_back"),
            ))
    return tasks


def _read_task_file(filename: str) -> dict:
    """Read a task config file."""
    filepath = CONFIG_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Task config not found: {filename}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {"tasks": []}


def _write_task_file(filename: str, data: dict):
    """Write back a task config file."""
    filepath = CONFIG_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


@router.get("/tasks")
def list_tasks():
    """List all tasks across all config files."""
    return load_all_tasks()


@router.post("/tasks", status_code=201)
def add_task(task: TaskModel, filename: Optional[str] = None):
    """Add a new task to a task config file."""
    if filename is None:
        # Default to first existing file, or create new one
        existing = _find_task_files()
        filename = existing[0].name if existing else "tasks.yaml"

    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    data = _read_task_file(filename)
    if "tasks" not in data:
        data["tasks"] = []

    # Check for duplicate name in same file
    for t in data["tasks"]:
        if t["name"] == task.name:
            raise HTTPException(
                status_code=409,
                detail=f"Task '{task.name}' already exists in {filename}",
            )

    new_task = {
        "name": task.name,
        "watchlist": task.watchlist,
        "strategies": task.strategies,
        "output": task.output,
    }
    if task.days_back is not None:
        new_task["days_back"] = task.days_back

    data["tasks"].append(new_task)
    _write_task_file(filename, data)

    return {
        "id": f"{filename}:{task.name}",
        "filename": filename,
        "name": task.name,
    }


@router.put("/tasks/{task_id}")
def update_task(task_id: str, task: TaskModel):
    """Update an existing task."""
    if ":" not in task_id:
        raise HTTPException(status_code=400, detail="Invalid task ID format. Expected 'filename:task_name'")

    filename, task_name = task_id.split(":", 1)
    data = _read_task_file(filename)

    found = False
    for i, t in enumerate(data.get("tasks", [])):
        if t["name"] == task_name:
            data["tasks"][i] = {
                "name": task.name,
                "watchlist": task.watchlist,
                "strategies": task.strategies,
                "output": task.output,
            }
            if task.days_back is not None:
                data["tasks"][i]["days_back"] = task.days_back
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    _write_task_file(filename, data)
    return {"id": task_id, "name": task.name, "updated": True}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task from its config file."""
    if ":" not in task_id:
        raise HTTPException(status_code=400, detail="Invalid task ID format. Expected 'filename:task_name'")

    filename, task_name = task_id.split(":", 1)

    # Security: only allow tasks*.yaml files
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filename.startswith("tasks") or not filename.endswith(".yaml"):
        raise HTTPException(status_code=400, detail="Invalid task config filename")

    data = _read_task_file(filename)
    original_count = len(data.get("tasks", []))
    data["tasks"] = [t for t in data.get("tasks", []) if t["name"] != task_name]

    if len(data["tasks"]) == original_count:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    _write_task_file(filename, data)
    return {"id": task_id, "deleted": True}
```

#### Step 2: Write task API tests

Create `tests/web/test_task_api.py`:
```python
"""Tests for task API endpoints."""
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from quantflow.web.api.tasks import router, CONFIG_DIR


@pytest.fixture
def app():
    """Create test FastAPI app with task router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def app_with_config(tmp_path, app):
    """Create app with mocked config dir populated with test task files."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "tasks_test.yaml").write_text(
        yaml.dump({
            "tasks": [
                {
                    "name": "test_task_1",
                    "watchlist": "watchlists/personal_focus_us.yaml",
                    "strategies": ["daily_bull_oversold"],
                    "output": "./output/test1",
                }
            ]
        }),
        encoding="utf-8",
    )

    import quantflow.web.api.tasks as task_module
    original = task_module.CONFIG_DIR
    task_module.CONFIG_DIR = tmp_path / "config"

    c = TestClient(app)
    yield c

    task_module.CONFIG_DIR = original


def test_list_all_tasks(app_with_config):
    """Lists tasks from all task config files."""
    resp = app_with_config.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_list_empty_tasks(app_with_config, tmp_path):
    """Returns empty list when no tasks exist."""
    # Remove test file
    test_file = tmp_path / "config" / "tasks_test.yaml"
    if test_file.exists():
        test_file.unlink()

    resp = app_with_config.get("/api/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


def test_add_task(app_with_config):
    """Adds a new task to config file."""
    resp = app_with_config.post("/api/tasks", json={
        "name": "new_task",
        "watchlist": "watchlists/test.yaml",
        "strategies": ["kdj_golden_cross"],
        "output": "./output/new",
    }, params={"filename": "tasks_test.yaml"})

    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "new_task"

    # Verify persistence
    resp = app_with_config.get("/api/tasks")
    names = [t["name"] for t in resp.json()]
    assert "new_task" in names


def test_add_duplicate_task(app_with_config):
    """Rejects duplicate task names in same file."""
    resp = app_with_config.post("/api/tasks", json={
        "name": "test_task_1",
        "watchlist": "watchlists/test.yaml",
        "strategies": [],
    }, params={"filename": "tasks_test.yaml"})

    assert resp.status_code == 409


def test_update_task(app_with_config):
    """Updates existing task."""
    task_id = "tasks_test.yaml:test_task_1"
    resp = app_with_config.put(f"/api/tasks/{task_id}", json={
        "name": "test_task_1",
        "watchlist": "watchlists/updated.yaml",
        "strategies": ["daily_bull_oversold", "kdj_golden_cross"],
        "output": "./output/updated",
    })

    assert resp.status_code == 200
    assert resp.json()["updated"] is True


def test_update_nonexistent_task(app_with_config):
    """Returns 404 for missing task."""
    resp = app_with_config.put("/api/tasks/tasks_test.yaml:nonexistent", json={
        "name": "nonexistent",
        "watchlist": "watchlists/x.yaml",
        "strategies": [],
    })
    assert resp.status_code == 404


def test_delete_task(app_with_config):
    """Deletes a task from config file."""
    # First add a task to delete
    app_with_config.post("/api/tasks", json={
        "name": "to_delete",
        "watchlist": "watchlists/x.yaml",
        "strategies": [],
    }, params={"filename": "tasks_test.yaml"})

    resp = app_with_config.delete("/api/tasks/tasks_test.yaml:to_delete")
    assert resp.status_code == 200
    assert resp.json()["deleted"] is True

    # Verify removed
    resp = app_with_config.get("/api/tasks")
    names = [t["name"] for t in resp.json()]
    assert "to_delete" not in names


def test_path_traversal_blocked(app_with_config):
    """Blocks path traversal in task operations."""
    resp = app_with_config.post("/api/tasks", json={
        "name": "hack",
        "watchlist": "x",
    }, params={"filename": "../../etc/passwd.yaml"})
    assert resp.status_code == 400


def test_delete_invalid_task_id(app_with_config):
    """Rejects invalid task ID format."""
    resp = app_with_config.delete("/api/tasks/invalid_id_without_colon")
    assert resp.status_code == 400


def test_delete_non_tasks_file(app_with_config):
    """Rejects deleting from non-task config files."""
    resp = app_with_config.delete("/api/tasks/quantflow.yaml:test")
    assert resp.status_code == 400
```

#### Step 3: Run tests

```bash
pytest tests/web/test_task_api.py -v
```
Expected: All 10 tests pass.

#### Step 4: Commit

```bash
git add src/quantflow/web/api/tasks.py tests/web/test_task_api.py
git commit -m "feat(web): add task CRUD API with multi-file support"
```

---

## Phase 5: FastAPI Server Assembly

### Task 5: Server module + CLI integration

#### Step 1: Create server module

Create `src/quantflow/web/server.py`:
```python
"""Web UI server - FastAPI application and startup logic."""
import webbrowser
from pathlib import Path
from threading import Timer

import uvicorn

from quantflow.web.config import WebConfig


def create_app():
    """Create the FastAPI application."""
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    app = FastAPI(
        title="QuantFlow Web",
        description="Web UI for QuantFlow stock monitoring system",
        version="0.1.0",
    )

    # Register API routes
    from quantflow.web.api.config import router as config_router
    from quantflow.web.api.watchlists import router as watchlist_router
    from quantflow.web.api.tasks import router as task_router

    app.include_router(config_router)
    app.include_router(watchlist_router)
    app.include_router(task_router)

    # Serve static files (frontend)
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


def start_server(config: WebConfig = None):
    """Start the web server."""
    if config is None:
        config = WebConfig.load()

    app = create_app()

    url = f"http://{config.host}:{config.port}"
    print(f"\n{'='*50}")
    print(f"  QuantFlow Web UI")
    print(f"  URL: {url}")
    print(f"{'='*50}\n")

    # Open browser after a short delay (so server is ready)
    def _open_browser():
        webbrowser.open(url)

    Timer(1.5, _open_browser).start()

    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
```

#### Step 2: Add web() function to CLI

Modify `src/quantflow/cli.py` - add the `web` function:

Add imports at top after existing imports:
```python
# Add after existing imports
from quantflow.web.config import WebConfig
```

Append the `web` function after the `tasks()` function:
```python
def web():
    """Launch QuantFlow Web UI."""
    from quantflow.web.server import start_server
    from quantflow.web.config import WebConfig

    config = WebConfig.load()
    print(f"Starting QuantFlow Web UI on {config.host}:{config.port}...")
    start_server(config)
```

Modify the `__main__` block to add `web` routing:
```python
# Change the last section from:
#         if command == "scan": scan()
#         elif command == "monitor": monitor()
#         elif command == "tasks": tasks()
#         else: print(f"Unknown command: {command}")

# To:
        if command == "scan": scan()
        elif command == "monitor": monitor()
        elif command == "tasks": tasks()
        elif command == "web": web()
        else: print(f"Unknown command: {command}")

# And change the usage text from:
#         print("Commands: scan, monitor, tasks")
# To:
        print("Commands: scan, monitor, tasks, web")
```

#### Step 3: Write server test

Append to `tests/web/test_config_api.py`:
```python
def test_create_app():
    """App includes all routes."""
    from quantflow.web.server import create_app

    app = create_app()
    routes = [r.path for r in app.routes]

    assert "/api/config" in routes
    assert "/api/strategies" in routes
    assert "/api/watchlists" in routes
    assert "/api/watchlists/{filename}" in routes
    assert "/api/watchlists/search" in routes
    assert "/api/tasks" in routes
    assert "/api/tasks/{task_id}" in routes
```

#### Step 4: Run all web tests

```bash
pytest tests/web/ -v
```
Expected: All ~22 tests pass.

#### Step 5: Test CLI integration manually

```bash
python -m quantflow.cli web
```

Expected:
- Server starts on configured port
- Browser opens automatically
- URL printed to console
- Access `/api/strategies` returns JSON

#### Step 6: Commit

```bash
git add src/quantflow/web/server.py src/quantflow/cli.py tests/web/test_config_api.py
git commit -m "feat(web): add FastAPI server and CLI web command"
```

---

## Phase 6: Frontend SPA

### Task 6: HTML + TypeScript Frontend

#### Step 1: Create HTML layout

Create `src/quantflow/web/static/index.html`:
```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>QuantFlow Web</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script type="module" src="/app.ts"></script>
    <style>
        .tab-active { @apply border-blue-500 text-blue-600; }
        .tab-inactive { @apply border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <!-- Header -->
    <header class="bg-white shadow">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex justify-between items-center py-4">
                <h1 class="text-2xl font-bold text-gray-900">🚀 QuantFlow Web</h1>
                <span class="text-sm text-gray-400">v0.1.0</span>
            </div>
        </div>
    </header>

    <!-- Modified indicator -->
    <div id="save-indicator" class="hidden fixed top-4 right-4 bg-yellow-400 text-white px-4 py-2 rounded-lg shadow-lg z-50">
        ⚠️ Unsaved changes
    </div>

    <!-- Tabs -->
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-4">
        <nav class="flex border-b border-gray-200 bg-white rounded-t-lg" role="tablist">
            <button id="tab-watchlists" class="tab-active px-6 py-3 border-b-2 font-medium text-sm" role="tab" data-tab="watchlists">
                📋 Watchlists
            </button>
            <button id="tab-tasks" class="tab-inactive px-6 py-3 border-b-2 font-medium text-sm" role="tab" data-tab="tasks">
                ⚡ Tasks
            </button>
            <button id="tab-settings" class="tab-inactive px-6 py-3 border-b-2 font-medium text-sm" role="tab" data-tab="settings">
                ⚙️ Settings
            </button>
        </nav>
    </div>

    <!-- Tab Contents -->
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
        <!-- Watchlists Tab -->
        <div id="panel-watchlists" class="bg-white shadow rounded-b-lg p-6 mt-0">
            <!-- Global Search -->
            <div class="mb-4 p-4 bg-gray-50 rounded-lg">
                <h3 class="text-sm font-medium text-gray-700 mb-2">🔍 Global Stock Search</h3>
                <div class="flex gap-2">
                    <div class="relative flex-1">
                        <input id="search-input" type="text" placeholder="Enter stock code (e.g. NVDA, 002594)..."
                               class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                        <div id="search-results" class="hidden absolute top-full left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-60 overflow-y-auto z-10"></div>
                    </div>
                </div>
                <div id="search-status" class="mt-2 text-sm text-gray-600 hidden"></div>
            </div>

            <!-- Main Content: Sidebar + Table -->
            <div class="flex gap-4">
                <!-- Sidebar: Watchlist List -->
                <div class="w-64 flex-shrink-0">
                    <div class="flex justify-between items-center mb-2">
                        <h3 class="font-medium text-gray-700">Watchlists</h3>
                        <button id="btn-new-watchlist" class="text-sm bg-blue-500 text-white px-2 py-1 rounded hover:bg-blue-600">+ New</button>
                    </div>
                    <ul id="watchlist-list" class="space-y-1 max-h-[600px] overflow-y-auto">
                        <!-- Dynamically populated -->
                    </ul>
                </div>

                <!-- Main: Stock Table -->
                <div class="flex-1">
                    <div id="watchlist-empty" class="text-gray-500 text-center py-8">Select a watchlist to view its stocks</div>
                    <div id="watchlist-content" class="hidden">
                        <div class="flex justify-between items-center mb-3">
                            <h3 id="watchlist-title" class="font-medium text-gray-900"></h3>
                            <div class="flex gap-2">
                                <button id="btn-add-stock" class="text-sm bg-green-500 text-white px-3 py-1 rounded hover:bg-green-600">+ Add Stock</button>
                                <button id="btn-batch-import" class="text-sm bg-purple-500 text-white px-3 py-1 rounded hover:bg-purple-600">📥 Batch</button>
                                <button id="btn-save-watchlist" class="hidden text-sm bg-yellow-500 text-white px-3 py-1 rounded hover:bg-yellow-600">💾 Save</button>
                            </div>
                        </div>
                        <table class="min-w-full divide-y divide-gray-200">
                            <thead class="bg-gray-50">
                                <tr>
                                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Code</th>
                                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Tags</th>
                                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                                </tr>
                            </thead>
                            <tbody id="stock-table" class="bg-white divide-y divide-gray-200">
                                <!-- Dynamically populated -->
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>

        <!-- Tasks Tab -->
        <div id="panel-tasks" class="hidden bg-white shadow rounded-b-lg p-6 mt-0">
            <div class="flex justify-between items-center mb-4">
                <h3 class="font-medium text-gray-900">Task Configurations</h3>
                <button id="btn-new-task" class="text-sm bg-blue-500 text-white px-3 py-1 rounded hover:bg-blue-600">+ New Task</button>
            </div>
            <table class="min-w-full divide-y divide-gray-200">
                <thead class="bg-gray-50">
                    <tr>
                        <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                        <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Watchlist</th>
                        <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Strategies</th>
                        <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Output</th>
                        <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Config File</th>
                        <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                    </tr>
                </thead>
                <tbody id="task-table" class="bg-white divide-y divide-gray-200">
                    <!-- Dynamically populated -->
                </tbody>
            </table>
            <div id="task-empty" class="text-gray-500 text-center py-8 hidden">No tasks configured</div>
        </div>

        <!-- Settings Tab -->
        <div id="panel-settings" class="hidden bg-white shadow rounded-b-lg p-6 mt-0">
            <h3 class="font-medium text-gray-900 mb-4">System Configuration (Read-Only)</h3>
            <pre id="config-display" class="bg-gray-50 p-4 rounded-lg text-sm overflow-auto max-h-[600px] font-mono"></pre>
        </div>
    </div>

    <!-- Modal: Add Stock -->
    <div id="modal-add-stock" class="hidden fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-white rounded-lg p-6 w-96">
            <h3 class="text-lg font-medium mb-4">Add Stock</h3>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700">Stock Code</label>
                <input id="add-stock-code" type="text" placeholder="e.g. NVDA.US, 002594.SZ"
                       class="w-full border border-gray-300 rounded px-3 py-2 mt-1 focus:ring-2 focus:ring-blue-500">
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700">Name</label>
                <input id="add-stock-name" type="text" placeholder="e.g. Nvidia, 比亚迪"
                       class="w-full border border-gray-300 rounded px-3 py-2 mt-1">
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700">Tags (comma-separated)</label>
                <input id="add-stock-tags" type="text" placeholder="e.g. Personal, AI"
                       class="w-full border border-gray-300 rounded px-3 py-2 mt-1">
            </div>
            <div id="add-stock-warning" class="hidden mb-4 text-sm text-yellow-600 bg-yellow-50 p-2 rounded"></div>
            <div class="flex justify-end gap-2">
                <button id="btn-cancel-add" class="px-4 py-2 text-gray-600 bg-gray-200 rounded hover:bg-gray-300">Cancel</button>
                <button id="btn-confirm-add" class="px-4 py-2 text-white bg-blue-500 rounded hover:bg-blue-600">Add</button>
            </div>
        </div>
    </div>

    <!-- Modal: Batch Import -->
    <div id="modal-batch" class="hidden fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-white rounded-lg p-6 w-[500px]">
            <h3 class="text-lg font-medium mb-2">Batch Import Stocks</h3>
            <p class="text-sm text-gray-500 mb-3">One code per line. Format: CODE [Name]</p>
            <textarea id="batch-input" rows="8" placeholder="002594.SZ 比亚迪&#10;NVDA.US Nvidia&#10;600000.SH 浦发银行"
                      class="w-full border border-gray-300 rounded px-3 py-2 font-mono text-sm"></textarea>
            <div class="flex justify-end gap-2 mt-4">
                <button id="btn-cancel-batch" class="px-4 py-2 text-gray-600 bg-gray-200 rounded hover:bg-gray-300">Cancel</button>
                <button id="btn-confirm-batch" class="px-4 py-2 text-white bg-purple-500 rounded hover:bg-purple-600">Import</button>
            </div>
        </div>
    </div>

    <!-- Modal: Task Edit -->
    <div id="modal-task" class="hidden fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-white rounded-lg p-6 w-[500px] max-h-[80vh] overflow-y-auto">
            <h3 id="task-modal-title" class="text-lg font-medium mb-4">New Task</h3>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700">Task Name</label>
                <input id="task-name" type="text" class="w-full border border-gray-300 rounded px-3 py-2 mt-1">
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700">Watchlist</label>
                <select id="task-watchlist" class="w-full border border-gray-300 rounded px-3 py-2 mt-1"></select>
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">Strategies</label>
                <div id="task-strategies" class="space-y-2"></div>
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700">Output Directory</label>
                <input id="task-output" type="text" placeholder="./output" class="w-full border border-gray-300 rounded px-3 py-2 mt-1">
            </div>
            <div id="task-config-select" class="mb-4">
                <label class="block text-sm font-medium text-gray-700">Config File</label>
                <select id="task-config-file" class="w-full border border-gray-300 rounded px-3 py-2 mt-1"></select>
            </div>
            <div class="flex justify-end gap-2">
                <button id="btn-cancel-task" class="px-4 py-2 text-gray-600 bg-gray-200 rounded hover:bg-gray-300">Cancel</button>
                <button id="btn-save-task" class="px-4 py-2 text-white bg-blue-500 rounded hover:bg-blue-600">Save</button>
            </div>
        </div>
    </div>

    <!-- Confirm Dialog -->
    <div id="modal-confirm" class="hidden fixed inset-0 bg-gray-600 bg-opacity-50 flex items-center justify-center z-50">
        <div class="bg-white rounded-lg p-6 w-80">
            <h3 id="confirm-title" class="text-lg font-medium mb-2"></h3>
            <p id="confirm-message" class="text-gray-600 mb-4"></p>
            <div class="flex justify-end gap-2">
                <button id="btn-confirm-cancel" class="px-4 py-2 text-gray-600 bg-gray-200 rounded hover:bg-gray-300">Cancel</button>
                <button id="btn-confirm-ok" class="px-4 py-2 text-white bg-red-500 rounded hover:bg-red-600">Confirm</button>
            </div>
        </div>
    </div>

    <!-- Toast Notification -->
    <div id="toast" class="hidden fixed bottom-4 right-4 bg-green-500 text-white px-4 py-2 rounded-lg shadow-lg z-50">
        <span id="toast-message"></span>
    </div>
</body>
</html>
```

#### Step 2: Create TypeScript app logic

Create `src/quantflow/web/static/app.ts`:
```typescript
/**
 * QuantFlow Web UI - Main Application Logic
 * Browser-native TypeScript (ES Module)
 */

// ==================== Types ====================
interface WatchlistItem {
    code: string;
    name?: string;
    tags?: string[];
}

interface WatchlistData {
    filename: string;
    name: string;
    description: string;
    items: WatchlistItem[];
}

interface WatchlistSummary {
    filename: string;
    name: string;
    itemCount: number;
    path: string;
}

interface TaskData {
    id: string;
    filename: string;
    name: string;
    watchlist: string;
    strategies: string[];
    output: string;
    days_back?: number | null;
}

interface StrategyInfo {
    id: string;
    name: string;
    type: string;
}

// ==================== State ====================
let state = {
    watchlists: [] as WatchlistSummary[],
    selectedWatchlist: null as string | null,
    currentWatchlistData: null as WatchlistData | null,
    watchlistDirty: false,
    tasks: [] as TaskData[],
    strategies: [] as StrategyInfo[],
    configFiles: [] as string[],
};

// ==================== API Helpers ====================
async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const resp = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
    });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
    }
    return resp.json();
}

// ==================== Init ====================
async function init() {
    await Promise.all([loadStrategies(), loadWatchlists(), loadTasks(), loadConfig()]);
    setupEventListeners();
    setupBeforeUnload();
}

async function loadStrategies() {
    try {
        const res = await api<{strategies: StrategyInfo[]}>("/api/strategies");
        state.strategies = res.strategies;
    } catch (e) {
        console.error("Failed to load strategies:", e);
    }
}

async function loadWatchlists() {
    try {
        state.watchlists = await api<WatchlistSummary[]>("/api/watchlists");
        renderWatchlistSidebar();
    } catch (e) {
        console.error("Failed to load watchlists:", e);
    }
}

async function loadTasks() {
    try {
        state.tasks = await api<TaskData[]>("/api/tasks");
        renderTaskTable();
        extractConfigFiles();
    } catch (e) {
        console.error("Failed to load tasks:", e);
    }
}

async function loadConfig() {
    try {
        const config = await api('/api/config');
        document.getElementById('config-display')!.textContent = JSON.stringify(config, null, 2);
    } catch (e) {
        console.error("Failed to load config:", e);
    }
}

function extractConfigFiles() {
    const files = [...new Set(state.tasks.map(t => t.filename))];
    // Also scan for tasks*.yaml by checking unique filenames
    state.configFiles = files;
}

// ==================== Tab Navigation ====================
function switchTab(tab: string) {
    const tabs = ['watchlists', 'tasks', 'settings'];
    for (const t of tabs) {
        const tabBtn = document.getElementById(`tab-${t}`)!;
        const panel = document.getElementById(`panel-${t}`)!;
        if (t === tab) {
            tabBtn.className = tabBtn.className.replace('tab-inactive', 'tab-active');
            panel.classList.remove('hidden');
        } else {
            tabBtn.className = tabBtn.className.replace('tab-active', 'tab-inactive');
            panel.classList.add('hidden');
        }
    }
}

// ==================== Watchlist Rendering ====================
function renderWatchlistSidebar() {
    const list = document.getElementById('watchlist-list')!;
    list.innerHTML = '';
    for (const wl of state.watchlists) {
        const li = document.createElement('li');
        const isSelected = state.selectedWatchlist === wl.filename;
        li.innerHTML = `
            <button data-filename="${wl.filename}"
                    class="w-full text-left px-3 py-2 rounded text-sm transition-colors
                           ${isSelected ? 'bg-blue-100 text-blue-700 font-medium' : 'hover:bg-gray-100 text-gray-700'}">
                <div class="truncate">${wl.name}</div>
                <div class="text-xs text-gray-400">${wl.itemCount} stocks</div>
            </button>
        `;
        li.querySelector('button')!.addEventListener('click', () => selectWatchlist(wl.filename));
        list.appendChild(li);
    }
}

async function selectWatchlist(filename: string) {
    // Warn about unsaved changes
    if (state.watchlistDirty && state.selectedWatchlist !== filename) {
        if (!confirm('You have unsaved changes. Discard them?')) return;
        state.currentWatchlistData = null;
        state.watchlistDirty = false;
        updateModifiedUI();
    }

    state.selectedWatchlist = filename;
    renderWatchlistSidebar();

    try {
        state.currentWatchlistData = await api<WatchlistData>(`/api/watchlists/${filename}`);
        state.watchlistDirty = false;
        renderStockTable();
        document.getElementById('watchlist-empty')!.classList.add('hidden');
        document.getElementById('watchlist-content')!.classList.remove('hidden');
        document.getElementById('watchlist-title')!.textContent = `${state.currentWatchlistData.name} (${state.currentWatchlistData.items.length} stocks)`;
    } catch (e: any) {
        alert(`Failed to load watchlist: ${e.message}`);
    }
}

function renderStockTable() {
    if (!state.currentWatchlistData) return;
    const tbody = document.getElementById('stock-table')!;
    tbody.innerHTML = '';
    const items = state.currentWatchlistData.items;

    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="px-4 py-4 text-center text-gray-500">No stocks in this watchlist</td></tr>';
        return;
    }

    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-gray-50';
        tr.innerHTML = `
            <td class="px-4 py-2 text-sm text-gray-900">${item.code}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${item.name || '-'}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${(item.tags || []).map(t => `<span class="bg-gray-100 px-1.5 py-0.5 rounded text-xs">${t}</span>`).join(' ') || '-'}</td>
            <td class="px-4 py-2 text-sm">
                <button data-idx="${i}" class="text-blue-600 hover:text-blue-800 mr-2 delete-stock-btn">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    }

    // Bind delete buttons
    tbody.querySelectorAll('.delete-stock-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const idx = parseInt((e.target as HTMLElement).dataset.idx || '0');
            state.currentWatchlistData!.items.splice(idx, 1);
            markWatchlistDirty();
            renderStockTable();
        });
    });
}

function markWatchlistDirty() {
    state.watchlistDirty = true;
    updateModifiedUI();
}

function updateModifiedUI() {
    const indicator = document.getElementById('save-indicator')!;
    const saveBtn = document.getElementById('btn-save-watchlist')!;
    if (state.watchlistDirty) {
        indicator.classList.remove('hidden');
        saveBtn.classList.remove('hidden');
    } else {
        indicator.classList.add('hidden');
        saveBtn.classList.add('hidden');
    }
}

// ==================== Task Rendering ====================
function renderTaskTable() {
    const tbody = document.getElementById('task-table')!;
    const empty = document.getElementById('task-empty')!;
    tbody.innerHTML = '';

    if (state.tasks.length === 0) {
        empty.classList.remove('hidden');
        return;
    }
    empty.classList.add('hidden');

    for (const task of state.tasks) {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-gray-50';
        tr.innerHTML = `
            <td class="px-4 py-2 text-sm font-medium text-gray-900">${task.name}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${task.watchlist}</td>
            <td class="px-4 py-2 text-sm text-gray-600">${task.strategies.join(', ')}</td>
            <td class="px-4 py-2 text-sm text-gray-600 font-mono text-xs">${task.output}</td>
            <td class="px-4 py-2 text-sm text-gray-500 font-mono text-xs">${task.filename}</td>
            <td class="px-4 py-2 text-sm">
                <button data-id="${task.id}" class="text-blue-600 hover:text-blue-800 mr-2 edit-task-btn">Edit</button>
                <button data-id="${task.id}" class="text-red-600 hover:text-red-800 delete-task-btn">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    }

    tbody.querySelectorAll('.edit-task-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const id = (e.target as HTMLElement).dataset.id || '';
            openTaskModal(id);
        });
    });

    tbody.querySelectorAll('.delete-task-btn').forEach(btn => {
        btn.addEventListener('click', async (e) => {
            const id = (e.target as HTMLElement).dataset.id || '';
            const name = state.tasks.find(t => t.id === id)?.name || id;
            if (confirm(`Delete task "${name}"?`)) {
                try {
                    await api(`/api/tasks/${id}`, { method: 'DELETE' });
                    toast(`Task "${name}" deleted`);
                    loadTasks();
                } catch (err: any) {
                    alert(`Failed: ${err.message}`);
                }
            }
        });
    });
}

// ==================== Modals ====================
function openModal(id: string) { document.getElementById(id)!.classList.remove('hidden'); }
function closeModal(id: string) { document.getElementById(id)!.classList.add('hidden'); }

function openAddStockModal() {
    document.getElementById('add-stock-code')!.value = '';
    document.getElementById('add-stock-name')!.value = '';
    document.getElementById('add-stock-tags')!.value = '';
    document.getElementById('add-stock-warning')!.classList.add('hidden');
    openModal('modal-add-stock');
}

async function confirmAddStock() {
    const code = (document.getElementById('add-stock-code') as HTMLInputElement).value.trim();
    const name = (document.getElementById('add-stock-name') as HTMLInputElement).value.trim();
    const tagsStr = (document.getElementById('add-stock-tags') as HTMLInputElement).value.trim();

    if (!code) { alert('Code is required'); return; }

    // Check if already exists
    try {
        const res = await api('/api/watchlists/search', {
            method: 'POST',
            body: JSON.stringify({ code }),
        });
        if (res.found) {
            const warning = document.getElementById('add-stock-warning')!;
            warning.textContent = `⚠️ Already in: ${res.inLists.join(', ')}`;
            warning.classList.remove('hidden');
        }
    } catch (e) { /* ignore check errors */ }

    if (!state.currentWatchlistData || !state.currentWatchlistData.items) {
        state.currentWatchlistData = { filename: '', name: '', description: '', items: [] };
    }

    state.currentWatchlistData.items.push({
        code,
        name: name || undefined,
        tags: tagsStr ? tagsStr.split(',').map(s => s.trim()).filter(Boolean) : [],
    });

    markWatchlistDirty();
    renderStockTable();
    closeModal('modal-add-stock');
}

function openBatchModal() {
    (document.getElementById('batch-input') as HTMLTextAreaElement).value = '';
    openModal('modal-batch');
}

function confirmBatchImport() {
    const text = (document.getElementById('batch-input') as HTMLTextAreaElement).value.trim();
    if (!text) { alert('No data to import'); return; }

    const lines = text.split('\n').filter(l => l.trim());
    let added = 0;
    for (const line of lines) {
        const parts = line.trim().split(/\s+/);
        const code = parts[0];
        const name = parts.slice(1).join(' ') || undefined;
        if (code) {
            state.currentWatchlistData!.items.push({ code, name: name || undefined, tags: ['Personal'] });
            added++;
        }
    }

    markWatchlistDirty();
    renderStockTable();
    closeModal('modal-batch');
    toast(`Imported ${added} stocks`);
}

async function saveWatchlist() {
    if (!state.currentWatchlistData) return;
    try {
        const filename = state.selectedWatchlist!;
        // Extract just code, name, tags for saving
        const cleanItems = state.currentWatchlistData.items.map(item => ({
            code: item.code,
            name: item.name,
            tags: item.tags || [],
        }));

        await api(`/api/watchlists/${filename}`, {
            method: 'PUT',
            body: JSON.stringify({
                name: state.currentWatchlistData.name,
                description: state.currentWatchlistData.description || '',
                items: cleanItems,
            }),
        });
        state.watchlistDirty = false;
        updateModifiedUI();
        loadWatchlists();
        toast('Watchlist saved');
    } catch (e: any) {
        alert(`Failed to save: ${e.message}`);
    }
}

async function openNewWatchlistModal() {
    const name = prompt('Watchlist name:');
    if (!name) return;

    const filename = name.replace(/[^a-zA-Z0-9_-\s]/g, '').trim().replace(/\s+/g, '_') + '.yaml';
    try {
        await api(`/api/watchlists/${filename}`, {
            method: 'PUT',
            body: JSON.stringify({
                name: name.replace(/\s+/g, '_'),
                description: '',
                items: [],
            }),
        });
        toast(`Created ${filename}`);
        loadWatchlists();
    } catch (e: any) {
        alert(`Failed: ${e.message}`);
    }
}

// ==================== Task Modal ====================
async function openTaskModal(taskId?: string) {
    const isEdit = !!taskId;
    document.getElementById('task-modal-title')!.textContent = isEdit ? 'Edit Task' : 'New Task';
    (document.getElementById('task-config-select') as HTMLElement).style.display = isEdit ? 'none' : 'block';

    // Populate watchlist dropdown
    const wlSelect = document.getElementById('task-watchlist') as HTMLSelectElement;
    wlSelect.innerHTML = '';
    for (const wl of state.watchlists) {
        const opt = document.createElement('option');
        opt.value = `watchlists/${wl.filename}`;
        opt.textContent = wl.name;
        wlSelect.appendChild(opt);
    }

    // Populate strategy checkboxes
    const stratContainer = document.getElementById('task-strategies')!;
    stratContainer.innerHTML = '';
    for (const s of state.strategies) {
        const label = document.createElement('label');
        label.className = 'flex items-center gap-2';
        label.innerHTML = `
            <input type="checkbox" value="${s.id}" class="task-strategy-cb">
            <span class="text-sm">${s.name} (${s.type})</span>
        `;
        stratContainer.appendChild(label);
    }

    // Populate config file dropdown (for new tasks)
    const fileSelect = document.getElementById('task-config-file') as HTMLSelectElement;
    fileSelect.innerHTML = '';
    // Derive config files from unique filenames in tasks
    const configFiles = [...new Set(state.tasks.map(t => t.filename))];
    if (configFiles.length === 0) {
        const opt = document.createElement('option');
        opt.value = 'tasks.yaml';
        opt.textContent = 'tasks.yaml (new)';
        fileSelect.appendChild(opt);
    }
    for (const f of configFiles) {
        const opt = document.createElement('option');
        opt.value = f;
        opt.textContent = f;
        fileSelect.appendChild(opt);
    }

    if (isEdit) {
        const task = state.tasks.find(t => t.id === taskId);
        if (!task) return;
        (document.getElementById('task-name') as HTMLInputElement).value = task.name;
        (document.getElementById('task-output') as HTMLInputElement).value = task.output;
        wlSelect.value = task.watchlist;
        // Check strategies
        stratContainer.querySelectorAll('.task-strategy-cb').forEach((cb: HTMLInputElement) => {
            cb.checked = task.strategies.includes(cb.value);
        });
    } else {
        (document.getElementById('task-name') as HTMLInputElement).value = '';
        (document.getElementById('task-output') as HTMLInputElement).value = './output';
    }

    // Bind save button
    const saveBtn = document.getElementById('btn-save-task')!;
    // Remove old listeners by cloning
    const newSaveBtn = saveBtn.cloneNode(true) as HTMLButtonElement;
    saveBtn.parentNode!.replaceChild(newSaveBtn, saveBtn);

    newSaveBtn.addEventListener('click', async () => {
        const taskName = (document.getElementById('task-name') as HTMLInputElement).value.trim();
        if (!taskName) { alert('Task name is required'); return; }

        const strategies = [...stratContainer.querySelectorAll('.task-strategy-cb:checked')].map(cb => (cb as HTMLInputElement).value);
        const output = (document.getElementById('task-output') as HTMLInputElement).value.trim() || './output';

        const payload = {
            name: taskName,
            watchlist: wlSelect.value,
            strategies,
            output,
        };

        try {
            if (isEdit) {
                await api(`/api/tasks/${taskId}`, {
                    method: 'PUT',
                    body: JSON.stringify(payload),
                });
                toast('Task updated');
            } else {
                const file = (document.getElementById('task-config-file') as HTMLSelectElement).value;
                await api(`/api/tasks?filename=${encodeURIComponent(file)}`, {
                    method: 'POST',
                    body: JSON.stringify(payload),
                });
                toast('Task created');
            }
            closeModal('modal-task');
            loadTasks();
        } catch (e: any) {
            alert(`Failed: ${e.message}`);
        }
    });

    openModal('modal-task');
}

// ==================== Search ====================
let searchTimeout: number | null = null;

async function handleSearch() {
    const input = (document.getElementById('search-input') as HTMLInputElement).value.trim();
    const resultsDiv = document.getElementById('search-results')!;
    const statusDiv = document.getElementById('search-status')!;

    if (input.length < 2) {
        resultsDiv.classList.add('hidden');
        statusDiv.classList.add('hidden');
        return;
    }

    try {
        const res = await api('/api/watchlists/search', {
            method: 'POST',
            body: JSON.stringify({ code: input }),
        });

        resultsDiv.classList.remove('hidden');

        if (res.found) {
            statusDiv.classList.remove('hidden');
            statusDiv.innerHTML = `<span class="text-green-600">✓ Found in:</span> ${res.inLists.join(', ')}`;
            resultsDiv.innerHTML = res.inLists.map(l =>
                `<div class="px-3 py-2 text-sm text-gray-600 hover:bg-gray-50">In: ${l}</div>`
            ).join('');
        } else if (res.fuzzyMatches && res.fuzzyMatches.length > 0) {
            statusDiv.classList.add('hidden');
            resultsDiv.innerHTML = res.fuzzyMatches.map(m =>
                `<div class="px-3 py-2 text-sm hover:bg-gray-50">
                    <span class="text-gray-900">${m.code}</span>
                    <span class="text-gray-500 ml-2">${m.name || ''}</span>
                </div>`
            ).join('');
        } else {
            statusDiv.classList.remove('hidden');
            statusDiv.innerHTML = `<span class="text-red-500">✗ Not found in any watchlist</span>`;
            resultsDiv.innerHTML = '<div class="px-3 py-2 text-sm text-gray-400">No matches</div>';
        }
    } catch (e) {
        console.error('Search failed:', e);
    }
}

// ==================== Toast ====================
function toast(msg: string) {
    const el = document.getElementById('toast')!;
    document.getElementById('toast-message')!.textContent = msg;
    el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 3000);
}

// ==================== Before Unload ====================
function setupBeforeUnload() {
    window.addEventListener('beforeunload', (e) => {
        if (state.watchlistDirty) {
            e.preventDefault();
            (e as BeforeUnloadEvent).returnValue = '';
        }
    });
}

// ==================== Event Listeners ====================
function setupEventListeners() {
    // Tab switching
    document.querySelectorAll('[role="tab"]').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab!));
    });

    // Watchlist sidebar
    document.getElementById('btn-new-watchlist')!.addEventListener('click', openNewWatchlistModal);

    // Stock add/batch/save
    document.getElementById('btn-add-stock')!.addEventListener('click', openAddStockModal);
    document.getElementById('btn-batch-import')!.addEventListener('click', openBatchModal);
    document.getElementById('btn-save-watchlist')!.addEventListener('click', saveWatchlist);

    // Modal buttons
    document.getElementById('btn-cancel-add')!.addEventListener('click', () => closeModal('modal-add-stock'));
    document.getElementById('btn-confirm-add')!.addEventListener('click', confirmAddStock);
    document.getElementById('btn-cancel-batch')!.addEventListener('click', () => closeModal('modal-batch'));
    document.getElementById('btn-confirm-batch')!.addEventListener('click', confirmBatchImport);
    document.getElementById('btn-cancel-task')!.addEventListener('click', () => closeModal('modal-task'));

    // Search
    document.getElementById('search-input')!.addEventListener('input', () => {
        if (searchTimeout) clearTimeout(searchTimeout);
        searchTimeout = setTimeout(handleSearch, 300) as unknown as number;
    });

    document.getElementById('btn-new-task')!.addEventListener('click', () => openTaskModal());

    // Task modal (save button handled inside openTaskModal)

    // Click outside dropdown to close search results
    document.addEventListener('click', (e) => {
        const searchContainer = document.getElementById('search-results');
        const searchInput = document.getElementById('search-input');
        if (searchContainer && !searchContainer.contains(e.target) && (e.target as HTMLElement) !== searchInput) {
            searchContainer.classList.add('hidden');
        }
    });
}

// ==================== Start ====================
init();
```

#### Step 3: Test frontend manually

```bash
python -m quantflow.cli web
```
Expected:
- Browser opens automatically
- Three tabs render correctly
- API calls work (watchlists load, strategies load)

#### Step 4: Commit

```bash
git add src/quantflow/web/static/
git commit -m "feat(web): add frontend SPA with watchlist and task management"
```

---

## Verification Script

After all tasks, run the complete verification:

```bash
# Install deps
pip install -e ".[dev]"

# Run tests
pytest tests/web/ -v
# Expected: All 22+ tests pass

# Lint
ruff check src/quantflow/web/
# Expected: No errors

# Manual: Start server
python -m quantflow.cli web
# Expected: Browser opens, all three tabs functional
```
