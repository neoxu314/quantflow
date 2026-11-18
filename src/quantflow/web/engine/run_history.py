"""RunHistory — SQLite persistence for execution history."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

QUANTFLOW_DIR = Path.home() / ".quantflow"
DB_PATH = QUANTFLOW_DIR / "runs.db"

_INIT_SQL = """
CREATE TABLE IF NOT EXISTS run_history (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, run_type TEXT NOT NULL,
    config TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    started_at TEXT, finished_at TEXT, duration_ms INTEGER, error TEXT,
    output_path TEXT, report_path TEXT, signal_count INTEGER DEFAULT 0,
    preset_id TEXT, log_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_run_status ON run_history(status);
CREATE INDEX IF NOT EXISTS idx_run_created ON run_history(created_at DESC);
"""

RUN_TYPES = ("stock_scan", "watchlist_run", "task_run")
STATUSES = ("queued", "running", "completed", "failed", "cancelled",
            "interrupted", "cancelling", "partial")

# Added after the initial release: keep old databases working without a
# destructive migration. Applied on every connection open, idempotently.
_MIGRATIONS = ("ALTER TABLE run_history ADD COLUMN log_path TEXT",)


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
    log_path: Optional[str] = None


def _row_to_record(row: tuple) -> RunRecord:
    # tolerate older rows written before log_path existed
    log_path = row[14] if len(row) > 14 else None
    return RunRecord(
        id=row[0], name=row[1], run_type=row[2], config=json.loads(row[3]),
        status=row[4], created_at=row[5], started_at=row[6],
        finished_at=row[7], duration_ms=row[8], error=row[9],
        output_path=row[10], report_path=row[11],
        signal_count=row[12] or 0, preset_id=row[13],
        log_path=log_path,
    )


class _ConnectionManager:
    _lock = threading.RLock()
    _conn: Optional[sqlite3.Connection] = None

    @classmethod
    def get(cls) -> sqlite3.Connection:
        with cls._lock:
            conn = cls._conn
            if conn is not None:
                return conn
            QUANTFLOW_DIR.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(str(DB_PATH), timeout=15,
                                   check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_INIT_SQL)
            # Idempotent forward migrations for databases created by older
            # versions (which lack newer optional columns).
            cols = {r[1] for r in conn.execute("PRAGMA table_info(run_history)")}
            for ddl in _MIGRATIONS:
                col = ddl.split("ADD COLUMN ")[1].split()[0]
                if col not in cols:
                    try:
                        conn.execute(ddl)
                    except sqlite3.OperationalError:
                        pass
            conn.commit()
            cls._conn = conn
            return conn

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            if cls._conn is not None:
                try:
                    cls._conn.close()
                except Exception:
                    pass
                cls._conn = None


class RunHistory:
    def create_run(self, name: str, run_type: str, config: dict,
                   preset_id: Optional[str] = None) -> str:
        """Insert a new run record with status='queued'. Returns UUID."""
        import uuid
        if run_type not in RUN_TYPES:
            raise ValueError(f"Invalid run_type '{run_type}'")
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with _ConnectionManager._lock:
            conn = _ConnectionManager.get()
            conn.execute(
                "INSERT INTO run_history "
                "(id,name,run_type,config,status,created_at,preset_id) "
                "VALUES (?,?,?,?,'queued',?,?)",
                (run_id, name, run_type, json.dumps(config), now, preset_id),
            )
            conn.commit()
        return run_id

    def update_status(self, run_id: str, status: str, **kwargs) -> None:
        """Update run status and optional fields."""
        if status not in STATUSES:
            raise ValueError(f"Invalid status '{status}'")
        fields = ["status = ?"]
        values: list = [status]
        for key in ("started_at", "finished_at", "error",
                     "output_path", "report_path", "log_path"):
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
        with _ConnectionManager._lock:
            conn = _ConnectionManager.get()
            current = conn.execute("SELECT status FROM run_history WHERE id = ?", (run_id,)).fetchone()
            if current is None:
                return
            if current[0] in ("cancelled", "interrupted", "cancelling") and status in ("running", "completed", "partial"):
                return
            conn.execute(
                f"UPDATE run_history SET {', '.join(fields)} WHERE id = ?",
                values)
            conn.commit()

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        return self._get_one("SELECT * FROM run_history WHERE id = ?", (run_id,))

    def list_runs(self, status: Optional[str] = None,
                  limit: int = 50, offset: int = 0) -> list[RunRecord]:
        with _ConnectionManager._lock:
            conn = _ConnectionManager.get()
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

    def _get_one(self, sql: str, params: tuple) -> Optional[RunRecord]:
        with _ConnectionManager._lock:
            conn = _ConnectionManager.get()
            row = conn.execute(sql, params).fetchone()
        return _row_to_record(row) if row else None

    def delete_run(self, run_id: str) -> bool:
        """Delete a run record from the database. Returns True if found."""
        with _ConnectionManager._lock:
            conn = _ConnectionManager.get()
            cursor = conn.execute(
                "DELETE FROM run_history WHERE id = ?", (run_id,))
            conn.commit()
        return cursor.rowcount > 0

    def reconcile_stale_runs(self) -> int:
        """Mark runs left in a non-terminal state by a previous server
        process (e.g. laptop lid closed / hard restart) as ``interrupted``.

        Called once at server startup.  Only ``queued`` and ``running`` are
        affected; a run actively executing in this process is never touched
        because this runs before the engine starts processing anything.

        Returns the number of rows updated.
        """
        now = datetime.now(timezone.utc).isoformat()
        with _ConnectionManager._lock:
            conn = _ConnectionManager.get()
            cursor = conn.execute(
                "UPDATE run_history SET status = 'interrupted', "
                "finished_at = ?, error = ? "
                "WHERE status IN ('queued', 'running', 'cancelling')",
                (now, "Interrupted: server restarted while run was active"))
            conn.commit()
        if cursor.rowcount:
            logger.info("Reconciled %d stale run(s) to 'interrupted'",
                        cursor.rowcount)
        return cursor.rowcount
