"""Reporter Interface."""

from abc import ABC, abstractmethod
from typing import List, Any
from datetime import datetime


class Reporter(ABC):
    """Abstract base class for task reports."""

    @abstractmethod
    def generate(
        self,
        task_name: str,
        strategies: List[Any],
        results: List[Any],
        watchlist: Any,
        output_dir: str,
        date_str: str,
    ) -> str:
        """Generate report and return file path."""
