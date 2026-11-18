"""Execution Job definition."""

from dataclasses import dataclass
from typing import List, Any


@dataclass
class ExecutionJob:
    name: str
    items: List[Any]
    strategies: List[Any]
    output_dir: str
    days_back: int = 365
    end_date: str = None
    as_of: str = None
    adjust: str = None
