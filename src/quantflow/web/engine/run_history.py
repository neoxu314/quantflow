"""RunHistory — SQLite persistence for execution history."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[4]
QUANTFLOW_DIR = PROJECT_ROOT / ".quantflow"
DB_PATH = QUANTFLOW_DIR / "runs.db"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS run_history (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, run_type TEXT NOT NULL,
    config TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    started_at TEXT, finished_at TEXT, duration_ms INTEGER, error TEXT,
    output_path TEXT, report_path TEXT, signal_count INTEGER DEFAULT 0,
    preset_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_status ON run_history(status);
CREATE INDEX IF NOT EXISTS idx_run_created ON run_history(created_at DESC);
"""

RUN_TYPES = ("stock_scan", "watchlist_run", "task_run")
STATUSES = ("queued", "running", "completed", "failed", "cancelled")


@dataclass
class RunRecord:
    id: str
    name: str
    run_type: str
    config: dict
    status: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    output_path: Optional[str] = None
    report_path: Optional[str] = None
    signal_count: int = 0
    preset_id: Optional[str] = None


_MEMORY_CONN: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _MEMORY_CONN
    if DB_PATH == Path(":memory:"):
        if _MEMORY_CONN is None:
            _MEMORY_CONN = sqlite3.connect(":memory:")
            _MEMORY_CONN.executescript(_INIT_SQL)
        return _MEMORY_CONN
    QUANTFLOW_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_INIT_SQL)
    conn.commit()
    return conn


def _close(conn: sqlite3.Connection) -> None:
    if conn is not _MEMORY_CONN:
        conn.close()


def _row_to_record(row: tuple) -> RunRecord:
    return RunRecord(
        id=row[0], name=row[1], run_type=row[2], config=json.loads(row[3]),
        status=row[4], created_at=row[5], started_at=row[6],
        finished_at=row[7], duration_ms=row[8], error=row[9],
        output_path=row[10], report_path=row[11],
        signal_count=row[12] or 0, preset_id=row[13],
    )


class RunHistory:
    def create_run(self, name: str, run_type: str, config: dict,
                   preset_id: Optional[str] = None) -> str:
        """Insert a new run record with status='queued'. Returns UUID."""
        import uuid
        if run_type not in RUN_TYPES:
            raise ValueError(f"Invalid run_type '{run_type}'")
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO run_history "
                "(id,name,run_type,config,status,created_at,preset_id) "
                "VALUES (?,?,?,?,'queued',?,?)",
                (run_id, name, run_type, json.dumps(config), now, preset_id),
            )
            conn.commit()
        finally:
            _close(conn)
        return run_id

    def update_status(self, run_id: str, status: str, **kwargs) -> None:
        """Update run status and optional fields."""
        if status not in STATUSES:
            raise ValueError(f"Invalid status '{status}'")
        fields = ["status = ?"]
        values: list = [status]
        for key in ("started_at", "finished_at", "error",
                     "output_path", "report_path"):
            if key in kwargs and kwargs[key] is not None:
                fields.append(f"{key} = ?")
                values.append(kwargs[key])
        if "duration_ms" in kwargs and kwargs["duration_ms"] is not None:
            fields.append("duration_ms = ?")
            values.append(int(kwargs["duration_ms"]))
        if "signal_count" in kwargs and kwargs["signal_count"] is not None:
            fields.append("signal_count = ?")
            values.append(int(kwargs["signal_count"]))
        values.append(run_id)
        conn = _connect()
        try:
            conn.execute(
                f"UPDATE run_history SET {', '.join(fields)} WHERE id = ?",
                values)
            conn.commit()
        finally:
            _close(conn)

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        return self._get_one("SELECT * FROM run_history WHERE id = ?", (run_id,))

    def list_runs(self, status: Optional[str] = None,
                  limit: int = 50, offset: int = 0) -> list[RunRecord]:
        conn = _connect()
        try:
            if status:
                rows = conn.execute(
                    "SELECT * FROM run_history WHERE status=? "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (status, limit, offset)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM run_history "
                    "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset)).fetchall()
            return [_row_to_record(r) for r in rows]
        finally:
            _close(conn)

    def _get_one(self, sql: str, params: tuple) -> Optional[RunRecord]:
        conn = _connect()
        try:
            row = conn.execute(sql, params).fetchone()
            return _row_to_record(row) if row else None
        finally:
            _close(conn)

    def delete_run(self, run_id: str) -> bool:
        """Delete a run record from the database. Returns True if found."""
        conn = _connect()
        try:
            cursor = conn.execute(
                "DELETE FROM run_history WHERE id = ?", (run_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            _close(conn)
