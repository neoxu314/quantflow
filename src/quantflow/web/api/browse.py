"""Directory browse API for selecting output paths."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/browse", tags=["Browse"])

# Project root for relative path calculation
PROJECT_ROOT = Path(__file__).resolve().parents[4]


@router.get("/")
def browse_dirs(path: str = ""):
    """List subdirectories at the given path. Returns empty dir list
    for inaccessible paths rather than 404."""
    target = Path(path) if path and os.path.isabs(path) else PROJECT_ROOT

    if not target.exists() or not target.is_dir():
        return {
            "current_path": str(target),
            "relative_path": _rel(target),
            "parent_path": "",
            "name": target.name or "/",
            "directories": [],
            "has_parent": False,
        }

    parent = target.parent
    try:
        entries = sorted(
            [d.name for d in target.iterdir() if d.is_dir()],
            key=lambda n: n.lower(),
        )
    except PermissionError:
        entries = []

    return {
        "current_path": str(target),
        "relative_path": _rel(target),
        "parent_path": str(parent) if target != parent else "",
        "name": target.name or "/",
        "directories": entries,
        "has_parent": target != target.parent,
    }


@router.post("/mkdir")
def mkdir(body: dict):
    parent = body.get("path", "")
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    parent_path = Path(parent) if parent else PROJECT_ROOT
    target = parent_path / name
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "ok": True,
        "path": str(target),
        "relative_path": _rel(target),
    }


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)
