"""Presets API endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from quantflow.web.engine.preflight import PreflightChecker
from quantflow.web.engine.presets import PresetManager

router = APIRouter(prefix="/api/presets", tags=["Presets"])


_engine = None

def _set_engine(engine) -> None:
    global _engine
    _engine = engine


def _get_engine():  # pragma: no cover - helper for tests if needed
    global _engine
    return _engine


@router.get("/")
def list_presets():
    presets = PresetManager.list_presets()
    return {
        "presets": [
            {
                "id": p.id,
                "name": p.name,
                "run_type": p.run_type,
                "config": p.config,
                "created_at": p.created_at,
            }
            for p in presets
        ]
    }


@router.post("/")
def create(body: dict):
    name, run_type = body.get("name"), body.get("run_type")
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    if run_type not in ("stock_scan", "watchlist_run", "task_run"):
        raise HTTPException(status_code=400,
                            detail="valid run_type required")
    pid = PresetManager.create(name, run_type,
                               body.get("config", {}))
    return {"ok": True, "preset_id": pid}


@router.put("/{pid}")
def update(pid: str, body: dict):
    if not PresetManager.get(pid):
        raise HTTPException(status_code=404, detail="Not found")
    ok = PresetManager.update(
        pid, body.get("name"), body.get("run_type"),
        body.get("config", {}))
    if not ok:
        raise HTTPException(status_code=500, detail="Update failed")
    return {"ok": True}


@router.delete("/{pid}")
def delete(pid: str):
    if not PresetManager.delete(pid):
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True}


@router.post("/{pid}/run")
def run_from_preset(pid: str):
    preset = PresetManager.get(pid)
    if not preset:
        raise HTTPException(status_code=404, detail="Not found")
    result = PreflightChecker.validate(preset.run_type,
                                       preset.config)
    if not result.ok:
        return {"ok": False, "errors": result.errors}

    engine = _get_engine()
    if not engine:
        raise HTTPException(status_code=500, detail="RunEngine not initialized")
    run_id = engine._history.create_run(
        preset.name, preset.run_type, preset.config,
        preset_id=pid)
    from quantflow.web.engine.run_queue import QueueFullError
    try:
        became_active = engine.enqueue(run_id)
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    return {
        "ok": True, "run_id": run_id,
        "status": "active" if became_active else "queued",
    }
