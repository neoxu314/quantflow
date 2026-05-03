"""Task CRUD API - manages tasks across multiple tasks_*.yaml files."""
import yaml
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["Tasks"])

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CONFIG_DIR = PROJECT_ROOT / "config"


class TaskModel(BaseModel):
    name: str
    watchlist: str
    strategies: List[str] = []
    output: str = "./output"
    days_back: Optional[int] = None


class TaskResponse(BaseModel):
    id: str
    filename: str
    name: str
    watchlist: str
    strategies: List[str]
    output: str
    days_back: Optional[int]


class TaskFileInfo(BaseModel):
    filename: str
    taskCount: int


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
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


@router.get("/tasks")
def list_tasks(filename: Optional[str] = Query(None)):
    """List all tasks or filter by config file."""
    all_tasks = load_all_tasks()
    if filename:
        return [t for t in all_tasks if t.filename == filename]
    return all_tasks


@router.get("/task-files")
def list_task_files():
    """List all task config files with their task counts."""
    files = []
    for yfile in _find_task_files():
        with open(yfile, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data or "tasks" not in data:
            count = 0
        else:
            count = len(data["tasks"])
        files.append(TaskFileInfo(filename=yfile.name, taskCount=count))
    return files


class TaskFileModel(BaseModel):
    filename: str


@router.post("/task-files", status_code=201)
def create_task_file(model: TaskFileModel):
    """Create a new task config file."""
    filename = model.filename
    if not filename.endswith(".yaml"):
        filename += ".yaml"
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filename.startswith("tasks"):
        filename = "tasks_" + filename

    filepath = CONFIG_DIR / filename
    if filepath.exists():
        raise HTTPException(status_code=409, detail=f"File already exists: {filename}")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _write_task_file(filename, {"tasks": []})
    return {"filename": filename}


@router.delete("/task-files/{filename}")
def delete_task_file(filename: str):
    """Delete a task config file."""
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = CONFIG_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")

    filepath.unlink()
    return {"filename": filename, "deleted": True}


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
