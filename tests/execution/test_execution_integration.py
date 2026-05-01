"""Execution Layer Integration Test."""
import pytest
from pathlib import Path

from quantflow.data.base import StockCode
from quantflow.execution.watchlist import WatchlistItem
from quantflow.execution.job import ExecutionJob
from quantflow.execution.executor import Executor
from quantflow.strategies.buy import DailyBullishOversoldBuy


@pytest.mark.integration
def test_execution_pipeline():
    items = [
        WatchlistItem(code=StockCode.from_standard("002594.SZ"), weight=1.0)
    ]
    
    job = ExecutionJob(
        name="verify_test",
        items=items,
        strategies=[DailyBullishOversoldBuy()],
        output_dir="tests/execution/tmp_output",
        days_back=120
    )

    executor = Executor()
    output_path = Path(job.output_dir) / f"{job.name}.json"
    if output_path.exists():
        output_path.unlink()

    results = executor.execute(job)
    
    assert output_path.exists(), "Executor failed to save the result file."
    output_path.unlink()