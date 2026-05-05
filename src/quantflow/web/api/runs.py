"""Runs API endpoints."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

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
    return {"runs": [_to_dict(r) for r in runs], "total": len(runs)}


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
    return {"run": _to_dict(run)}


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
        if op.exists() and op.is_dir():
            import shutil
            shutil.rmtree(op, ignore_errors=True)

    engine._history.delete_run(run_id)
    engine._sse.disconnect_all(run_id)

    return {"ok": True}


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
        try:
            while True:
                msg = await loop.run_in_executor(
                    None, q.get, True, 1.0)
                if msg is _DISCONNECTED:
                    break
                if isinstance(msg, dict):
                    yield (
                        f"event: {msg['event']}\n"
                        f"data: {json.dumps(msg['data'])}\n\n"
                    )
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
