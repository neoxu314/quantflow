"""Runs API endpoints."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from queue import Empty
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

from quantflow.web.engine.preflight import PreflightChecker
from quantflow.web.engine.run_engine import RunEngine

router = APIRouter(prefix="/api/runs", tags=["Runs"])


def _get_engine() -> RunEngine:
    if not hasattr(_get_engine, "_instance"):
        raise HTTPException(status_code=500,
                            detail="RunEngine not initialized")
    return _get_engine._instance


def _set_engine(engine: RunEngine) -> None:
    _get_engine._instance = engine


@router.get("/")
def list_runs(status: Optional[str] = None, limit: int = 50,
              offset: int = 0):
    runs = _get_engine()._history.list_runs(
        status=status, limit=limit, offset=offset)
    return {"runs": [_with_log_path(r) for r in runs], "total": len(runs)}


@router.get("/queue")
def get_queue_status():
    s = _get_engine()._queue.get_state()
    return {
        "active_run_id": s.active_run_id,
        "pending_count": s.pending_count,
        "total_queued": s.total_queued,
    }


@router.post("/")
def create_run(body: dict):
    run_type = body.get("run_type")
    if not run_type:
        raise HTTPException(status_code=400, detail="run_type required")

    config = _build_config(run_type, body)
    result = PreflightChecker.validate(run_type, config)
    if not result.ok:
        return {"ok": False, "errors": result.errors}

    if body.get("validate_only"):
        return {"ok": True}

    name = body.get("name") or _auto_name(run_type, config)
    engine = _get_engine()
    run_id = engine._history.create_run(
        name, run_type, config, preset_id=body.get("preset_id"))

    from quantflow.web.engine.run_queue import QueueFullError
    try:
        became_active = engine.enqueue(run_id)
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    return {
        "ok": True, "run_id": run_id,
        "status": "active" if became_active else "queued",
    }


@router.get("/{run_id}")
def get_run(run_id: str):
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404,
                            detail=f"Run {run_id} not found")
    return {"run": _with_log_path(run)}


@router.post("/{run_id}/cancel")
def cancel_run(run_id: str):
    engine = _get_engine()
    with engine._state_lock:
        run = engine._history.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if engine._queue.cancel(run_id):
            engine._history.update_status(run_id, "cancelled",
                finished_at=datetime.now(timezone.utc).isoformat())
            engine._sse.publish_status(run_id, "cancelled")
            return {"ok": True, "status": "cancelled"}
        if engine._queue.active == run_id and engine.cancel(run_id):
            return {"ok": True, "status": "cancelling"}
        raise HTTPException(status_code=400, detail="Run is not active or queued")


@router.delete("/{run_id}")
def delete_run(run_id: str):
    from quantflow.artifacts import delete_owned_artifacts
    from quantflow.execution.checkpoint import Checkpoint
    engine = _get_engine()
    with engine._state_lock:
        run = engine._history.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run_id in engine._workers or run.status in ("running", "cancelling"):
            raise HTTPException(status_code=409, detail="Cancel the run and wait for it to stop before deleting")
        engine._queue.cancel(run_id)
        next_run = engine._queue.finish(run_id)
        if run.output_path:
            delete_owned_artifacts(run.output_path, run_id)
        engine._history.delete_run(run_id)
        engine._sse.disconnect_all(run_id)
        Checkpoint(run_id).delete()
        if next_run:
            engine.start_processing(next_run)
    return {"ok": True}


@router.get("/{run_id}/logs")
def get_log_file(run_id: str, tail: int = 500):
    """Return the real on-disk log file for a run.

    Unlike the SSE ``log`` events (human-readable summaries published to the
    live UI), this is the actual Python logging output written to
    ``<output>/logs/*.log``.  By default the last ``tail`` lines are returned;
    pass ``tail=0`` for the complete file.
    """
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")

    log_path = Path(run.log_path) if run.log_path else None
    if log_path is None or not log_path.exists():
        return {
            "path": str(log_path) if log_path else None,
            "content": "",
            "exists": False,
            "message": ("Log file not configured for this run"
                        if log_path is None else "Log file not found"),
        }
    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"path": str(log_path), "content": "", "exists": False,
                "message": f"Cannot read log: {e}"}
    if tail and tail > 0:
        lines = content.splitlines()
        if len(lines) > tail:
            content = "\n".join(lines[-tail:])
    return {"path": str(log_path), "content": content,
            "exists": True, "tail": tail}


def _resume_error(engine, run, checkpoint):
    if run.status not in ("failed", "partial", "cancelled", "interrupted"):
        return f"Run in status '{run.status}' cannot be resumed"
    if run.run_type not in ("watchlist_run", "task_run"):
        return f"Run type '{run.run_type}' does not support resume"
    if checkpoint is None:
        return "No checkpoint available. Start a new run."
    try:
        engine.check_resume_plan(run, checkpoint)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return str(exc)
    return None


@router.get("/{run_id}/checkpoint")
def get_checkpoint(run_id: str):
    """Return checkpoint status for a run (for the Resume button/UI)."""
    from quantflow.execution.checkpoint import Checkpoint

    engine = _get_engine()
    run = engine._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    checkpoint = Checkpoint.load(run_id)
    error = _resume_error(engine, run, checkpoint)
    response = {"exists": checkpoint is not None, "can_resume": error is None}
    if checkpoint:
        response["summary"] = checkpoint.summary()
    if error:
        response["reason"] = "no_checkpoint" if checkpoint is None else error
    return response


@router.post("/{run_id}/resume")
def resume_run(run_id: str):
    """Create a new run continuing the verified plan of an incomplete run."""
    from quantflow.execution.checkpoint import Checkpoint

    engine = _get_engine()
    original = engine._history.get_run(run_id)
    if not original:
        raise HTTPException(status_code=404, detail="Not found")
    error = _resume_error(engine, original, Checkpoint.load(run_id))
    if error:
        raise HTTPException(status_code=400, detail=error)
    config = dict(original.config)
    config["resume_from"] = run_id
    new_id = engine._history.create_run(
        f"{original.name} (resume)", original.run_type, config,
        preset_id=original.preset_id)
    # Copy the checkpoint so the new run can validate and reuse completed items.
    if not Checkpoint.copy_to(run_id, new_id):
        engine._history.delete_run(new_id)
        raise HTTPException(status_code=400, detail="Cannot copy checkpoint")

    from quantflow.web.engine.run_queue import QueueFullError
    try:
        became_active = engine.enqueue(new_id)
    except QueueFullError as exc:
        Checkpoint(new_id).delete()
        raise HTTPException(status_code=429, detail=str(exc))
    return {"ok": True, "run_id": new_id, "resumed_from": run_id,
            "status": "active" if became_active else "queued"}


@router.get("/{run_id}/report")
def get_report(run_id: str):
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    if not run.report_path:
        return {"report": None, "message": "No report available"}
    rp = Path(run.report_path)
    if not rp.exists():
        return {"report": None, "message": "Report file not found"}
    return {"report": rp.read_text(), "path": str(rp), "legacy_warning": _legacy_warning(run)}


def _legacy_warning(run):
    manifest = Path(run.output_path) / "manifest.json" if run.output_path else None
    if manifest and manifest.is_file():
        try:
            if json.loads(manifest.read_text()).get("run_id") == run.id:
                return None
        except (OSError, ValueError):
            pass
    return "This older report may have been replaced by a later run. Its historical version cannot be verified."


@router.get("/{run_id}/indicator-data")
def get_indicator_data(run_id: str):
    """Return indicator calculation results for stock_scan runs."""
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    if run.run_type != "stock_scan":
        return {"data": None, "message": "Not a stock scan run"}
    data_path = run.report_path
    if not data_path:
        return {"data": None, "message": "No data available"}
    dp = Path(data_path)
    if not dp.exists():
        return {"data": None, "message": "Data file not found"}
    data = json.loads(dp.read_text())
    return {
        "data": data,
        "code": run.config.get("code"),
        "bar_count": len(data),
        "legacy_warning": _legacy_warning(run),
    }


@router.post("/{run_id}/open-folder")
def open_folder(run_id: str):
    """Open the output folder in system file browser."""
    import platform
    import subprocess

    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    folder_path = run.output_path
    if not folder_path:
        return {"ok": False, "message": "No output path"}

    p = Path(folder_path)
    if not p.exists():
        return {"ok": False, "message": "Folder does not exist"}

    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.run(["open", str(p)], check=True)
        elif system == "Windows":
            subprocess.run(["explorer", str(p)], check=True)
        else:
            subprocess.run(["xdg-open", str(p)], check=True)
        return {"ok": True, "path": str(p)}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.get("/{run_id}/files")
def get_files(run_id: str):
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    if not run.output_path:
        return {"files": []}
    from quantflow.artifacts import MANIFEST
    output_dir = Path(run.output_path)
    manifest = output_dir / MANIFEST
    if not manifest.is_file():
        return {"files": [], "message": "Legacy run has no owned artifact manifest"}
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data.get("run_id") != run_id:
        raise HTTPException(status_code=409, detail="Artifact ownership mismatch")
    files = []
    for relative in data["artifacts"]:
        path = output_dir / relative
        if output_dir.resolve() not in path.resolve().parents or path.is_symlink():
            continue
        if path.is_file() and path.suffix in (".json", ".md"):
            files.append({"name": path.name, "relative_path": relative, "path": str(path),
                          "size": _human_size(path.stat().st_size), "type": path.suffix.lstrip(".")})
    return {"files": files}


@router.get("/{run_id}/logs:sse")
async def stream_logs(run_id: str):
    from quantflow.web.engine.sse import _DISCONNECTED
    sse = _get_engine()._sse
    if not _get_engine()._history.get_run(run_id):
        raise HTTPException(status_code=404, detail="Not found")
    q = sse.subscribe(run_id)

    async def _gen():
        loop = asyncio.get_event_loop()
        # Send a keepalive comment on timeout so proxies/browsers don't close
        # an idle stream. queue.Empty is NOT a reason to end the stream —
        # ending it here silently dropped all progress/log events for runs
        # with >1s gaps between events (e.g. network-bound stock fetches).
        try:
            while True:
                try:
                    msg = await loop.run_in_executor(
                        None, q.get, True, 1.0)
                except Empty:
                    yield ": keepalive\n\n"
                    continue
                if msg is _DISCONNECTED:
                    break
                if isinstance(msg, dict):
                    yield (
                        f"event: {msg['event']}\n"
                        f"data: {json.dumps(msg['data'])}\n\n"
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            sse.unsubscribe(run_id, q)

    return StreamingResponse(
        _gen(), media_type="text/event-stream")


def _build_config(run_type: str, body: dict) -> dict:
    if run_type == "stock_scan":
        return {
            "code": body.get("code"),
            "start_date": body.get("start_date"),
            "end_date": body.get("end_date"),
            "indicators": body.get(
                "indicators", ["kdj", "dual_line"]),
            "output_path": body.get("output_path"),
        }
    if run_type == "watchlist_run":
        return {
            "watchlist": body.get("watchlist"),
            "strategies": body.get("strategies"),
            "days_back": body.get("days_back"),
            "output_path": body.get("output_path"),
        }
    if run_type == "task_run":
        return {
            "task_config": body.get("task_config"),
            "output_path": body.get("output_path"),
            "daily": body.get("daily", False),
        }
    return {}


def _auto_name(run_type: str, config: dict) -> str:
    if run_type == "stock_scan":
        return f"{config.get('code', 'Unknown')} Scan"
    if run_type == "watchlist_run":
        wl = config.get("watchlist", "")
        return f"{Path(wl).stem} Monitor"
    tp = config.get("task_config", "")
    return f"{Path(tp).stem} Task"


def _with_log_path(run) -> dict:
    """Attach the log file path and the active run progress snapshot."""
    data = {**_to_dict(run), "log_path": getattr(run, "log_path", None)}
    if run.status in ("running", "cancelling"):
        data["progress"] = _get_engine()._sse.progress(run.id)
    return data


def _to_dict(run):
    return {
        "id": run.id, "name": run.name, "run_type": run.run_type,
        "config": run.config, "status": run.status,
        "created_at": run.created_at, "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_ms": run.duration_ms, "error": run.error,
        "output_path": run.output_path,
        "report_path": run.report_path,
        "signal_count": run.signal_count,
        "preset_id": run.preset_id,
    }


def _human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 ** 2):.1f} MB"
