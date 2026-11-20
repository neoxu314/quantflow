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


def finish_manifest(root, status, *, finished_at=None, **metadata):
    manifest = Path(root) / MANIFEST
    data = json.loads(manifest.read_text(encoding="utf-8"))
    finished_at = finished_at or datetime.now(timezone.utc).isoformat()
    data.update(metadata, status=status, finished_at=finished_at)
    for relative in data["artifacts"]:
        path = Path(root) / relative
        if path.is_file() and not path.is_symlink():
            data["artifacts"][relative] = {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
    atomic_json(manifest, data, register=False)


def recover_finalized_run(root, run_id):
    """Recover terminal database fields only from a verified finalized manifest."""
    root = Path(root)
    manifest = root / MANIFEST
    if root.name != run_id or root.parent.name != "runs" or root.is_symlink() or manifest.is_symlink():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        status, result = data["status"], data["run_result"]
        if (
            data["run_id"] != run_id or data["schema_version"] != 1
            or status not in ("completed", "partial", "failed", "cancelled")
            or not isinstance(result, dict)
        ):
            return None
        finished = datetime.fromisoformat(data["finished_at"])
        if finished.tzinfo is None:
            return None
        artifacts = data["artifacts"]
        root = root.resolve()
        for relative, details in artifacts.items():
            path = root / relative
            if (
                Path(relative).is_absolute() or not path.resolve().is_relative_to(root)
                or path.is_symlink() or path.stat().st_size != details["size"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != details["sha256"]
            ):
                return None
        report = result.get("report")
        if (report and report not in artifacts) or (status in ("completed", "partial") and not report):
            return None
        count = result.get("signal_count", 0)
        error = result.get("error")
        if type(count) is not int or count < 0 or (error is not None and not isinstance(error, str)):
            return None
        return {
            "status": status, "finished_at": data["finished_at"], "signal_count": count,
            "report_path": str(root / report) if report else None, "error": error,
        }
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError):
        return None


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
