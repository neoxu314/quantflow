"""Declare fixture file ownership explicitly, just as a run would at write time."""
from pathlib import Path

from quantflow.artifacts import atomic_json, register_artifact, finish_manifest


def own_test_artifacts(run_id, root, paths):
    root = Path(root)
    atomic_json(root / "manifest.json", {"schema_version": 1, "run_id": run_id,
                                        "status": "running", "artifacts": {}}, register=False)
    for path in paths:
        register_artifact(path)
    finish_manifest(root, "completed")
