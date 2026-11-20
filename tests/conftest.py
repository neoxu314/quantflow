"""pytest configuration for all tests.

CRITICAL SAFETY: Protects production data files.

Hook: pytest_sessionfinish - verifies no production files modified.
"""
import pytest
from pathlib import Path
import hashlib


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Production paths to protect (CRITICAL: NEVER modify these in tests!)
PRODUCTION_PATHS = [
    "watchlists/*.yaml",
    "config/tasks*.yaml",
    "config/quantflow.yaml",
    "config/indicators.yaml",
]


def _compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of file content."""
    if not file_path.exists():
        return ""
    content = file_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def _snapshot_production_files() -> dict:
    """Create hash snapshot of all production files."""
    snapshot = {}
    for pattern in PRODUCTION_PATHS:
        for file_path in PROJECT_ROOT.glob(pattern):
            # Skip backup files, test files, and hidden files
            if ".bak" in file_path.name:
                continue
            if "_test_" in file_path.name or "_e2e_" in file_path.name:
                continue
            if file_path.name.startswith("."):
                continue
            snapshot[str(file_path.relative_to(PROJECT_ROOT))] = _compute_file_hash(file_path)
    return snapshot


def pytest_sessionstart(session):
    """Called after Session object has been created.
    
    CRITICAL SAFETY: Take snapshot of production files before any tests run.
    """
    session.quantflow_production_snapshot = _snapshot_production_files()


def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finished.
    
    CRITICAL SAFETY: Verify no production files were modified during test session.
    If modified, fail the session and list the changed files.
    """
    original = getattr(session, "quantflow_production_snapshot", None)
    if original is None:
        return

    current = _snapshot_production_files()
    modified_files = [
        path for path in sorted(original.keys() | current.keys())
        if original.get(path) != current.get(path)
    ]

    # If production files were modified, print CRITICAL warning
    if modified_files:
        msg = "\n\n" + "=" * 80
        msg += "\n🔴 CRITICAL SAFETY VIOLATION DETECTED!\n"
        msg += "=" * 80
        msg += "\n\nProduction files were modified during test session:\n"
        for f in modified_files:
            msg += f"  - {f}\n"
        msg += "\nTests must NEVER modify production data files.\n"
        msg += "Use tmp_path fixture instead.\n\n"
        msg += "\n" + "=" * 80 + "\n\n"
        
        # Print to stderr (pytest captures stdout)
        import sys
        sys.stderr.write(msg)
        sys.stderr.flush()
        
        # Force test session to fail
        session.exitstatus = 1