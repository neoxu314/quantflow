"""Tests for ExecutionJob dataclass."""

import pytest
import json
from pathlib import Path

from quantflow.data.base import StockCode
from quantflow.execution.watchlist import WatchlistItem
from quantflow.execution.job import ExecutionJob


class TestExecutionJob:
    def test_minimal(self):
        item = WatchlistItem(code=StockCode.from_standard("600000.SH"))
        job = ExecutionJob(
            name="test_job",
            items=[item],
            strategies=[],
            output_dir="/tmp/output",
        )
        assert job.name == "test_job"
        assert len(job.items) == 1
        assert job.strategies == []
        assert job.output_dir == "/tmp/output"
        assert job.days_back == 365

    def test_custom_days(self):
        job = ExecutionJob(name="short", items=[], strategies=[], output_dir="/tmp", days_back=60)
        assert job.days_back == 60
