"""Atomic artifacts and per-run ownership manifests."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

MANIFEST = "manifest.json"


class ArtifactWriteError(OSError):
    """A required research artifact could not be persisted."""


def json_value(value):
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        return json_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _atomic_text(path, content, register=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".quantflow-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if register:
        register_artifact(path)


def atomic_text(path, content, register=True):
    try:
        _atomic_text(path, content, register)
    except OSError as exc:
        raise ArtifactWriteError(f"Cannot persist {path}: {exc}") from exc


def atomic_json(path, payload, register=True):
    try:
        content = json.dumps(json_value(payload), ensure_ascii=False, allow_nan=False, indent=2)
    except (TypeError, ValueError) as exc:
        raise ArtifactWriteError(f"Cannot serialize {path}: {exc}") from exc
    atomic_text(path, content, register)


def safe_name(name):
    value = str(name)
    if not value or value in (".", "..") or any(c in value for c in "/\\\x00:"):
        raise ValueError(f"Unsafe artifact name: {name!r}")
    return value


def create_run_directory(base, run_id=None, config=None):
    run_id = safe_name(run_id or str(uuid4()))
    root = Path(base).resolve() / "runs" / run_id
    root.mkdir(parents=True, exist_ok=False)
    atomic_json(
        root / MANIFEST,
        {
            "schema_version": 1,
            "run_id": run_id,
            "status": "running",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config": config or {},
            "artifacts": {},
        },
        register=False,
    )
    return root


def register_artifact(path):
    path = Path(path).resolve()
    for root in path.parents:
        manifest = root / MANIFEST
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1 or "run_id" not in data:
                continue
            data["artifacts"][path.relative_to(root).as_posix()] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
            atomic_json(manifest, data, register=False)
            return


def finish_manifest(root, status, **metadata):
    manifest = Path(root) / MANIFEST
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data.update(metadata, status=status, finished_at=datetime.now(timezone.utc).isoformat())
    for relative in data["artifacts"]:
        path = Path(root) / relative
        if path.is_file() and not path.is_symlink():
            data["artifacts"][relative] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    atomic_json(manifest, data, register=False)


def delete_owned_artifacts(root, run_id):
    """Legacy shared outputs without a manifest deliberately remain untouched."""
    root = Path(root).resolve()
    manifest = root / MANIFEST
    if not manifest.is_file():
        return
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("run_id") != run_id:
        raise ValueError("Artifact manifest belongs to a different run")
    for relative, info in data["artifacts"].items():
        path = root / relative
        if path.is_symlink() or root not in path.resolve().parents:
            continue
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == info["sha256"]:
            path.unlink()
    manifest.unlink()
    for directory in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not directory.is_symlink():
            try:
                directory.rmdir()
            except OSError:
                pass
    try:
        root.rmdir()
    except OSError:
        pass
