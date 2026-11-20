"""Verify strict JSON emitted by the production artifact writer."""

import json

import numpy as np
import pandas as pd
import pytest

from quantflow.artifacts import ArtifactWriteError, atomic_json, create_run_directory


def read_strict_json(path):
    def invalid_constant(value):
        pytest.fail(f"Invalid JSON constant in {path.name}: {value}")

    return json.loads(path.read_text(), parse_constant=invalid_constant)


def test_artifact_round_trip_preserves_values_and_replaces_nonfinite_numbers(tmp_path):
    path = create_run_directory(tmp_path, "scan") / "indicators.json"
    atomic_json(
        path,
        [
            {
                "date": pd.Timestamp("2025-06-04"),
                "close": np.float64(139.5),
                "count": np.int64(3),
                "active": np.bool_(True),
                "zero": 0,
                "comment": "复核",
                "warmup": [float("nan"), np.float64("inf"), float("-inf")],
            }
        ],
    )

    records = read_strict_json(path)
    assert records == [
        {
            "date": "2025-06-04T00:00:00",
            "close": 139.5,
            "count": 3,
            "active": True,
            "zero": 0,
            "comment": "复核",
            "warmup": [None, None, None],
        }
    ]
    assert records[0]["active"] is True
    assert "indicators.json" in read_strict_json(path.parent / "manifest.json")["artifacts"]


def test_unserializable_update_keeps_the_existing_artifact(tmp_path):
    path = tmp_path / "indicators.json"
    atomic_json(path, [])
    with pytest.raises(ArtifactWriteError, match="Cannot serialize"):
        atomic_json(path, [object()])
    assert read_strict_json(path) == []
