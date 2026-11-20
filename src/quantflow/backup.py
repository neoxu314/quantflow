"""Create and verify a portable backup of Runs and their recorded files."""

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from quantflow.artifacts import atomic_json

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_readonly(path):
    return closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True))


def create_backup(state_dir, output_dir, project_root=PROJECT_ROOT):
    """Copy SQLite's committed view and index the exact bytes of available files."""
    state_dir, output_dir = Path(state_dir), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = Path(tempfile.mkdtemp(prefix=f"runs-{stamp}-", dir=output_dir))
    index = {"schema_version": 1, "database": {}, "files": {}, "issues": []}
    copied = {}

    def record_file(source, destination, expected_hash=None):
        source = Path(source)
        if source in copied:
            return copied[source]
        if not source.is_file() or source.is_symlink():
            index["issues"].append({"path": str(source), "reason": "missing_or_symlink"})
            return
        target = backup / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            before = source.stat()
            shutil.copy2(source, target)
            after = source.stat()
        except FileNotFoundError:
            target.unlink(missing_ok=True)
            index["issues"].append({"path": str(source), "reason": "removed_during_backup"})
            return None
        digest = _sha256(target)
        index["files"][destination.as_posix()] = {"source": str(source), "sha256": digest}
        copied[source] = target
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns
        ):
            index["issues"].append({"path": str(source), "reason": "changed_during_backup"})
        elif expected_hash and expected_hash != digest:
            index["issues"].append({"path": str(source), "reason": "differs_from_run_manifest"})
        return target

    try:
        database = backup / "runs.db"
        with (
            _open_readonly(state_dir / "runs.db") as live,
            closing(sqlite3.connect(database)) as dest,
        ):
            live.backup(dest)
            dest.row_factory = sqlite3.Row
            records = [dict(row) for row in dest.execute("SELECT * FROM run_history")]
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Runs backup failed SQLite integrity check")
        index["database"] = {"sha256": _sha256(database), "run_count": len(records)}
        for position, run in enumerate(records):
            group = Path("artifacts") / str(position)
            if run["status"] in ("queued", "running", "cancelling"):
                index["issues"].append({"run_id": run["id"], "reason": "run_was_active"})
            path = run.get("output_path")
            if path:
                root = (Path(project_root) / path).resolve()
                manifest = root / "manifest.json"
                if manifest.is_file() and not manifest.is_symlink():
                    archived_manifest = record_file(manifest, group / "output" / manifest.name)
                    try:
                        data = (
                            json.loads(archived_manifest.read_text()) if archived_manifest else {}
                        )
                    except (OSError, ValueError):
                        data = {}
                    if (
                        not isinstance(data, dict)
                        or data.get("run_id") != run["id"]
                        or not isinstance(data.get("artifacts"), dict)
                    ):
                        index["issues"].append({
                            "path": str(manifest), "reason": "unverified_manifest",
                        })
                    else:
                        for name, info in data["artifacts"].items():
                            relative = Path(name)
                            source = root / relative
                            if (
                                relative.is_absolute()
                                or ".." in relative.parts
                                or source == root
                                or not source.resolve().is_relative_to(root)
                            ):
                                index["issues"].append({
                                    "path": str(source), "reason": "outside_run_directory"
                                })
                                continue
                            expected = info.get("sha256") if isinstance(info, dict) else None
                            record_file(source, group / "output" / relative, expected)
            for field in ("report_path", "log_path"):
                if run.get(field):
                    source = (Path(project_root) / run[field]).absolute()
                    record_file(source, group / field / source.name)
        for subfolder in ("checkpoints", "presets"):
            folder = state_dir / subfolder
            if folder.is_dir() and not folder.is_symlink():
                for source in sorted(folder.glob("*.json")):
                    record_file(source, Path(subfolder) / source.name)
        atomic_json(backup / "backup-index.json", index, register=False)
    except BaseException:
        shutil.rmtree(backup)
        raise
    return backup


def verify_backup(backup):
    """Check file hashes and restore the database to an isolated SQLite instance."""
    backup = Path(backup).resolve()
    index = json.loads((backup / "backup-index.json").read_text())
    if index.get("schema_version") != 1:
        raise ValueError("Unsupported Runs backup version")
    database = backup / "runs.db"
    expected = {"runs.db": index["database"], **index["files"]}
    for relative, info in expected.items():
        path = backup / relative
        if (
            path.is_symlink() or not path.resolve().is_relative_to(backup)
            or not path.is_file() or _sha256(path) != info["sha256"]
        ):
            raise ValueError(f"Cannot verify backup file: {relative}")
    with _open_readonly(database) as source, closing(sqlite3.connect(":memory:")) as restored:
        source.backup(restored)
        if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Restored Runs database failed its integrity check")
        count = restored.execute("SELECT COUNT(*) FROM run_history").fetchone()[0]
        if count != index["database"]["run_count"]:
            raise ValueError("Restored Runs count differs from the backup index")
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="Parent directory for new backups")
    parser.add_argument("--verify", type=Path, help="Verify a backup and rehearse SQLite restore")
    args = parser.parse_args()
    state_dir = Path.home() / ".quantflow"
    try:
        backup = args.verify or create_backup(state_dir, args.output_dir or state_dir / "backups")
        index = verify_backup(backup)
    except (OSError, ValueError, sqlite3.Error) as exc:
        parser.exit(1, f"Runs backup failed: {exc}\n")
    print(backup)
    print(f"Verified {index['database']['run_count']} runs and {len(index['files'])} files.")
    if index["issues"]:
        print(f"Review {len(index['issues'])} findings in backup-index.json.")


if __name__ == "__main__":
    main()
