"""Contract tests: validate output_path/report_path structure assumptions."""
from pathlib import Path
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from quantflow.web.engine import run_history
from quantflow.web.api import runs as runs_api
from quantflow.web.engine.run_engine import RunEngine
from quantflow.web.engine.run_queue import RunQueue
from quantflow.web.engine.sse import SSEManager


@pytest.fixture
def setup_db():
    import sqlite3
    run_history._MEMORY_CONN = None
    run_history.DB_PATH = Path(":memory:")
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.executescript(run_history._INIT_SQL)
    run_history._MEMORY_CONN = conn


@pytest.fixture
def client(setup_db):
    from fastapi import FastAPI
    api_app = FastAPI()
    h = run_history.RunHistory()
    engine = RunEngine(RunQueue(), h, SSEManager())
    runs_api._set_engine(engine)
    api_app.include_router(runs_api.router)
    return TestClient(api_app)


class TestOutputReportPathContract:
    """Validate path structure invariants."""
    
    def test_task_run_daily_report_path_contains_date(self, setup_db, tmp_path):
        """daily mode: report_path must contain YYYY-MM-DD directory."""
        h = run_history.RunHistory()
        rid = h.create_run("Daily", "task_run", {"daily": True})
        
        output_dir = tmp_path / rid
        date_str = datetime.now().strftime("%Y-%m-%d")
        date_dir = output_dir / date_str
        date_dir.mkdir(parents=True)
        
        report_file = date_dir / "Daily_Report.md"
        report_file.write_text("# R")
        
        h.update_status(
            rid, "completed",
            output_path=str(output_dir),
            report_path=str(report_file)
        )
        
        run = h.get_run(rid)
        assert run.report_path is not None
        
        # Contract: report_path contains date
        assert date_str in run.report_path
        
        # Contract: output_path does NOT contain date
        assert date_str not in run.output_path
        
    def test_task_run_normal_report_path_in_output_path(self, setup_db, tmp_path):
        """normal mode: report_path must be inside output_path."""
        h = run_history.RunHistory()
        rid = h.create_run("Normal", "task_run", {"daily": False})
        
        output_dir = tmp_path / rid
        output_dir.mkdir()
        
        report_file = output_dir / "Daily_Report.md"
        report_file.write_text("# R")
        
        h.update_status(
            rid, "completed",
            output_path=str(output_dir),
            report_path=str(report_file)
        )
        
        run = h.get_run(rid)
        
        # Contract: report_path is inside output_path
        assert Path(run.report_path).parent == Path(run.output_path)
        
    def test_all_run_types_report_path_exists_if_completed(self, setup_db, tmp_path):
        """completed runs must have valid report_path (file exists)."""
        h = run_history.RunHistory()
        
        # Test all run types
        for run_type in ["stock_scan", "watchlist_run", "task_run"]:
            rid = h.create_run(f"Test {run_type}", run_type, {})
            
            output_dir = tmp_path / f"{run_type}_output"
            output_dir.mkdir()
            
            # Create appropriate report file
            if run_type == "stock_scan":
                report_file = output_dir / "indicators.json"
            elif run_type == "watchlist_run":
                report_file = output_dir / "report.md"
            else:
                report_file = output_dir / "Daily_Report.md"
            
            report_file.write_text("test content")
            
            h.update_status(
                rid, "completed",
                output_path=str(output_dir),
                report_path=str(report_file)
            )
            
            run = h.get_run(rid)
            assert run.report_path is not None
            assert Path(run.report_path).exists()