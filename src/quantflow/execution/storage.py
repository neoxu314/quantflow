"""Execution result storage."""

import json
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


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
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "buy_signals": self.buy_signals,
            "sell_signals": self.sell_signals,
            "reasons": self.reasons,
            "matched_buy_strategies": self.matched_buy_strategies,
            "matched_sell_strategies": self.matched_sell_strategies,
            "timestamp": self.timestamp.isoformat()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionResultItem":
        """Rebuild a result from a checkpoint/JSON record."""
        d = dict(data)
        ts = d.pop("timestamp", None)
        item = cls(**{k: v for k, v in d.items()
                      if k in cls.__dataclass_fields__})
        if ts:
            try:
                item.timestamp = datetime.fromisoformat(ts)
            except (TypeError, ValueError):
                pass
        return item


class Storage:
    def __init__(self, base_path: str = "./output"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def save_results(self, path: str, items: List[ExecutionResultItem]):
        data = [item.to_dict() for item in items]
        try:
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(items)} results to {path}")
        except Exception as e:
            logger.error(f"Storage failed: {e}")