"""Watchlist management."""

import json
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

from quantflow.data.base import StockCode


@dataclass
class WatchlistItem:
    code: StockCode
    weight: float = 1.0
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    
    def to_dict(self) -> dict:
        return {
            "code": self.code.standard,
            "name": self.code.name,
            "weight": self.weight,
            "tags": self.tags,
            "notes": self.notes,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "WatchlistItem":
        code = StockCode.from_standard(data["code"], name=data.get("name"))
        return cls(
            code=code,
            weight=data.get("weight", 1.0),
            tags=data.get("tags", []),
            notes=data.get("notes", ""),
        )


class Watchlist:
    
    def __init__(
        self,
        name: str,
        items: Optional[List[WatchlistItem]] = None,
        description: str = ""
    ):
        self.name = name
        self.items = items or []
        self.description = description
    
    def add_item(self, item: WatchlistItem) -> None:
        existing = [i for i in self.items if i.code.standard == item.code.standard]
        if existing:
            self.items.remove(existing[0])
        self.items.append(item)
    
    def remove_item(self, code: StockCode) -> None:
        self.items = [i for i in self.items if i.code.standard != code.standard]
    
    def get_codes(self) -> List[StockCode]:
        return [item.code for item in self.items]
    
    def filter_by_tags(self, tags: List[str]) -> List[WatchlistItem]:
        return [
            item for item in self.items
            if any(tag in item.tags for tag in tags)
        ]
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "items": [item.to_dict() for item in self.items],
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Watchlist":
        items = [WatchlistItem.from_dict(item) for item in data.get("items", [])]
        return cls(
            name=data["name"],
            items=items,
            description=data.get("description", ""),
        )
    
    def save(self, path: str) -> None:
        data = self.to_dict()
        
        if path.endswith(".yaml") or path.endswith(".yml"):
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False)
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load(cls, path: str) -> "Watchlist":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Watchlist file not found: {path}")
        
        with open(path, "r", encoding="utf-8") as f:
            if path.endswith(".yaml") or path.endswith(".yml"):
                data = yaml.safe_load(f)
            else:
                data = json.load(f)
        
        return cls.from_dict(data)