import hashlib
import json
import sqlite3

import pytest

from quantflow.backup import create_backup, verify_backup
from quantflow.web.engine.run_history import _INIT_SQL


def test_backup_restores_live_wal_and_verifies_files(tmp_path):
    state, output = tmp_path / "state", tmp_path / "backups"
    state.mkdir()
    run = tmp_path / "output" / "runs" / "owned"
    run.mkdir(parents=True)
    report = run / "report.md"
    report.write_text("edited report")
    (run / "manifest.json").write_text(json.dumps({
        "run_id": "owned",
        "artifacts": {
            "report.md": {"sha256": hashlib.sha256(b"original").hexdigest()},
            "../private.txt": {"sha256": ""},
        },
    }))
    (run.parent / "private.txt").write_text("outside the run")
    with sqlite3.connect(state / "runs.db") as live:
        live.execute("PRAGMA journal_mode=WAL")
        live.executescript(_INIT_SQL)
        live.execute(
            "INSERT INTO run_history (id, name, run_type, config, status, created_at, "
            "output_path, report_path, log_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("owned", "Run", "task_run", "{}", "completed", "2026-11-20",
             str(run), str(report), str(run / "missing.log")),
        )
        live.commit()
        backup = create_backup(state, output)
        index = verify_backup(backup)
        assert live.execute("SELECT count(*) FROM run_history").fetchone()[0] == 1

    assert index["database"]["run_count"] == 1
    assert {item["reason"] for item in index["issues"]} == {
        "differs_from_run_manifest", "outside_run_directory", "missing_or_symlink",
    }
    saved_names = {item["source"] for item in index["files"].values()}
    assert saved_names == {str(report), str(run / "manifest.json")}
    archived = next(backup / name for name, item in index["files"].items()
                    if item["source"] == str(report))
    assert archived.read_text() == "edited report"
    archived.write_text("modified backup copy")
    with pytest.raises(ValueError, match="Cannot verify backup file"):
        verify_backup(backup)
