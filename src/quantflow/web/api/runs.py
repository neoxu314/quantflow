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

    became_active = engine._queue.enqueue(run_id)
    if became_active:
        engine.start_processing(run_id)

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
    queue = engine._queue
    cancelled = queue.cancel(run_id)
    # If it was active, also cancel engine
    if queue.active == run_id:
        engine.cancel(run_id)
        nxt = queue.dequeue()
        if nxt:
            engine.start_processing(nxt)
    if cancelled or queue.active != run_id:
        engine._history.update_status(
            run_id, "cancelled",
            finished_at=datetime.now(timezone.utc).isoformat())
        engine._sse.publish_status(run_id, "cancelled")
        return {"ok": True}
    raise HTTPException(status_code=400,
                        detail="Run cannot be cancelled")


@router.delete("/{run_id}")
def delete_run(run_id: str):
    """Delete a run record and all associated output files."""
    engine = _get_engine()
    run = engine._history.get_run(run_id)
    if not run:
        raise HTTPException(
            status_code=404, detail=f"Run {run_id} not found")

    if run.status == "running":
        engine.cancel(run_id)
        engine._queue.cancel(run_id)
    elif run.status == "queued":
        engine._queue.cancel(run_id)

    if run.report_path:
        rp = Path(run.report_path)
        if rp.exists():
            rp.unlink()

    if run.output_path:
        op = Path(run.output_path)
        
        if run.run_type == "task_run":
            # task_run: only delete task output files, not entire directory
            # to prevent accidental deletion of user's other files
            if op.exists() and op.is_dir():
                _delete_task_run_outputs(run, op)
        elif run.run_type == "stock_scan":
            # stock_scan: only delete the specific indicator JSON file
            # output_path is shared directory, may contain files from other runs
            _delete_stock_scan_outputs(run, op)
        else:
            # watchlist_run: only delete the specific JSON file
            # output_path is shared directory, may contain files from other runs
            _delete_watchlist_run_outputs(run, op)

    engine._history.delete_run(run_id)
    engine._sse.disconnect_all(run_id)
    # Remove the resume checkpoint associated with this run (if any).
    from quantflow.execution.checkpoint import Checkpoint
    Checkpoint(run_id).delete()

    return {"ok": True}


def _delete_task_run_outputs(run, output_dir: Path):
    """Delete task_run output files without deleting entire directory.
    
    For task_run, output_path is user-specified directory that may contain
    other user files. We only delete task-generated files:
    - Daily_Report.md
    - Combined_Results.json
    - {task_name}.md (per-task reports)
    
    If daily mode, also delete date subdirectory.
    """
    import os
    from datetime import datetime
    
    # Determine base directory (daily mode has date subdirectory)
    daily = run.config.get("daily", False)
    if daily:
        # Extract date from run.finished_at or created_at
        timestamp_str = run.finished_at or run.created_at
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                date_str = dt.strftime("%Y-%m-%d")
                base_dir = output_dir / date_str
            except Exception:
                # Fallback: try to find date directory
                base_dir = output_dir
        else:
            base_dir = output_dir
    else:
        base_dir = output_dir
    
    if not base_dir.exists():
        return
    
    # Files to delete
    files_to_delete = [
        base_dir / "Daily_Report.md",
        base_dir / "Combined_Results.json",
    ]
    
    # Always delete run.name.json (Executor output for single-task runs)
    # This covers cases where task_config is missing or invalid
    files_to_delete.append(base_dir / f"{run.name}.json")
    
    # Load task config to get task names (for additional task reports)
    task_config_path = run.config.get("task_config")
    if task_config_path:
        # Resolve absolute path
        PROJECT_ROOT = Path(__file__).resolve().parents[4]
        if not os.path.isabs(task_config_path):
            task_config_path = PROJECT_ROOT / task_config_path
        
        # Load task names
        try:
            from quantflow.orchestration.loader import TaskConfig
            configs = TaskConfig.load(str(task_config_path))
            task_names = [cfg.name for cfg in configs]
            
            for task_name in task_names:
                files_to_delete.append(base_dir / f"{task_name}.md")
                files_to_delete.append(base_dir / f"{task_name}.json")  # Executor output
        except Exception:
            # Failed to load, continue with generic files only
            pass
    
    # Delete task output files
    for f in files_to_delete:
        if f.exists():
            f.unlink()
    
    # If daily mode and date directory is now empty, delete it
    if daily and base_dir != output_dir:
        try:
            # Check if directory is empty (or contains only empty subdirectories)
            remaining = list(base_dir.iterdir())
            if not remaining:
                base_dir.rmdir()  # Use rmdir() for empty directories
        except Exception:
            pass


def _delete_stock_scan_outputs(run, output_dir: Path):
    """Delete stock_scan output file without deleting entire directory.
    
    For stock_scan, output_path is a shared directory (no run_id isolation).
    We only delete the specific indicator JSON file:
    - {code}_indicators.json
    
    The report_path is already deleted in delete_run().
    """
    # Get stock code from run config
    code = run.config.get("code", "")
    if not code:
        # Fallback: try to extract from run.name if it contains a stock code
        # e.g., "Scan 600000.SH" → "600000.SH"
        parts = run.name.split()
        for part in parts:
            if "." in part or part.isdigit():
                code = part
                break
    
    if code:
        # Safe code (replace slashes to match file naming)
        safe_code = code.replace("/", "_").replace("\\", "_")
        indicator_file = output_dir / f"{safe_code}_indicators.json"
        
        if indicator_file.exists():
            indicator_file.unlink()


def _delete_watchlist_run_outputs(run, output_dir: Path):
    """Delete watchlist_run output files without deleting entire directory.
    
    For watchlist_run, output_path is a shared directory (no run_id isolation).
    Files generated:
    - {job.name}.json (Executor output)
    - {job.name}.md (Markdown report, already deleted via report_path)
    
    The job.name format is "web-{wl.name}" where wl.name comes from YAML content
    (not file name!). We must load the watchlist to get the correct name.
    """
    # Load watchlist to get wl.name from YAML content
    wl_path = run.config.get("watchlist", "")
    if not wl_path:
        return
    
    try:
        from pathlib import Path as _Path
        import os
        
        # Resolve absolute path
        PROJECT_ROOT = Path(__file__).resolve().parents[4]
        if not os.path.isabs(wl_path):
            wl_path = str(PROJECT_ROOT / wl_path)
        
        # Load watchlist to get name field from YAML
        from quantflow.execution.watchlist import Watchlist
        wl = Watchlist.load(wl_path)
        wl_name = wl.name
        
        # job.name format: "web-{wl_name}" (see run_engine.py:286)
        job_name = f"web-{wl_name}"
        
        # Executor saves results as {output_dir}/{job_name}.json
        json_file = output_dir / f"{job_name}.json"
        
        if json_file.exists():
            json_file.unlink()
    except Exception:
        # Fallback: if load fails, try using file stem (may not match)
        wl_name = Path(wl_path).stem
        job_name = f"web-{wl_name}"
        json_file = output_dir / f"{job_name}.json"
        if json_file.exists():
            json_file.unlink()


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


@router.get("/{run_id}/checkpoint")
def get_checkpoint(run_id: str):
    """Return checkpoint status for a run (for the Resume button/UI)."""
    from quantflow.execution.checkpoint import Checkpoint
    run = _get_engine()._history.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    cp = Checkpoint.load(run_id)
    if cp is None:
        return {"exists": False, "can_resume": False,
                "reason": "no_checkpoint"}
    summary = cp.summary()
    # A completed run has nothing left to resume.
    return {"exists": True, "can_resume": run.status in
            ("failed", "cancelled", "interrupted", "running"),
            "summary": summary}


@router.post("/{run_id}/resume")
def resume_run(run_id: str):
    """Create a new run that continues from ``run_id``'s checkpoint.

    Only runs that are in a terminal (but incomplete) state can be resumed.
    A new run record is created with ``resume_from`` set, preserving the
    original in the history list.
    """
    from quantflow.execution.checkpoint import Checkpoint
    engine = _get_engine()
    original = engine._history.get_run(run_id)
    if not original:
        raise HTTPException(status_code=404, detail="Not found")
    if original.status not in ("failed", "cancelled", "interrupted"):
        raise HTTPException(
            status_code=400,
            detail=f"Run in status '{original.status}' cannot be resumed")
    if original.run_type not in ("watchlist_run", "task_run"):
        raise HTTPException(
            status_code=400,
            detail=f"Run type '{original.run_type}' does not support resume")

    config = dict(original.config)
    config["resume_from"] = run_id
    new_id = engine._history.create_run(
        f"{original.name} (resume)", original.run_type, config,
        preset_id=original.preset_id)
    # Copy the original checkpoint forward so completed items are skipped.
    if not Checkpoint.copy_to(run_id, new_id):
        logger.warning("No checkpoint found for run %s on resume", run_id)

    became_active = engine._queue.enqueue(new_id)
    if became_active:
        engine.start_processing(new_id)
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
    return {"report": rp.read_text(), "path": str(rp)}


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
    files = []
    output_dir = Path(run.output_path)
    if not output_dir.exists():
        return {"files": files}
    for f in output_dir.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".md"):
            files.append({
                "name": f.name, "path": str(f),
                "size": _human_size(f.stat().st_size),
                "type": f.suffix.lstrip("."),
            })
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
    """Serialize a run, exposing the real on-disk log path to the Web UI."""
    return {**_to_dict(run), "log_path": getattr(run, "log_path", None)}


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
