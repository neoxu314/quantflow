"""Execution result storage."""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from quantflow.artifacts import atomic_json

logger = logging.getLogger(__name__)


@dataclass
class StockOutcome:
    code: str
    status: str
    source: Optional[str] = None
    bar_date: Optional[str] = None
    expected_session: Optional[str] = None
    error: Optional[str] = None
    snapshot_path: Optional[str] = None
    snapshot_sha256: Optional[str] = None


class ScanResults(list):
    """A list-compatible signal collection with explicit per-stock coverage."""

    def __init__(self, items=(), outcomes=()):
        super().__init__(items)
        self.outcomes = list(outcomes)

    @property
    def summary(self):
        counts = {
            s: sum(o.status == s for o in self.outcomes)
            for s in (
                "signal",
                "no_signal",
                "no_data",
                "stale",
                "suspended",
                "insufficient",
                "error",
            )
        }
        total = len(self.outcomes)
        analyzed = counts["signal"] + counts["no_signal"]
        status = "completed" if analyzed == total else ("partial" if analyzed else "failed")
        return dict(
            counts,
            total=total,
            analyzed=analyzed,
            status=status,
            coverage=analyzed / total if total else 1.0,
        )


@dataclass
class ExecutionResultItem:
    """Represents execution results for a single stock."""

    code: str
    name: str = ""
    buy_signals: int = 0
    sell_signals: int = 0
    reasons: List[str] = field(default_factory=list)
    matched_buy_strategies: List[str] = field(default_factory=list)
    matched_sell_strategies: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    bar_date: Optional[str] = None
    source: Optional[str] = None
    market: Optional[str] = None
    adjust: Optional[str] = None
    price: Optional[float] = None
    indicators: dict = field(default_factory=dict)
    strategy_params: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "buy_signals": self.buy_signals,
            "sell_signals": self.sell_signals,
            "reasons": self.reasons,
            "matched_buy_strategies": self.matched_buy_strategies,
            "matched_sell_strategies": self.matched_sell_strategies,
            "timestamp": self.timestamp.isoformat(),
            "bar_date": self.bar_date,
            "source": self.source,
            "market": self.market,
            "adjust": self.adjust,
            "price": self.price,
            "indicators": self.indicators,
            "strategy_params": self.strategy_params,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionResultItem":
        """Rebuild a result from a checkpoint/JSON record."""
        d = dict(data)
        ts = d.pop("timestamp", None)
        item = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        if ts:
            try:
                item.timestamp = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                pass
        return item


class Storage:
    def __init__(self, base_path: str = "./output"):
        self.base_path = Path(base_path)

    def save_results(self, path: str, items: List[ExecutionResultItem]):
        data = [item.to_dict() for item in items]
        atomic_json(path, data)
        logger.info("Saved %d results to %s", len(items), path)

    def save_coverage(self, path, results):
        atomic_json(
            path,
            {
                "schema_version": 1,
                "summary": results.summary,
                "outcomes": [asdict(o) for o in results.outcomes],
            },
        )
