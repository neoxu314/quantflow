"""Preset management — saved run configurations as YAML."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

QUANTFLOW_DIR = Path.home() / ".quantflow"
PRESETS_DIR = QUANTFLOW_DIR / "presets"


@dataclass
class Preset:
    id: str
    name: str
    run_type: str
    config: dict
    created_at: str = ""

    def to_dict(self) -> dict:
        return {"name": self.name, "run_type": self.run_type,
                "config": self.config, "created_at": self.created_at}

    @classmethod
    def from_dict(cls, pid: str, data: dict) -> "Preset":
        return cls(id=pid, name=data.get("name", pid),
                   run_type=data.get("run_type", "stock_scan"),
                   config=data.get("config", {}),
                   created_at=data.get("created_at", ""))


class PresetManager:
    @staticmethod
    def _ensure_dir():
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def list_presets() -> list[Preset]:
        PresetManager._ensure_dir()
        presets = []
        for p in sorted(PRESETS_DIR.glob("*.yaml")):
            try:
                with open(p) as f:
                    data = yaml.safe_load(f)
                if data:
                    presets.append(Preset.from_dict(p.stem, data))
            except Exception:
                pass
        return presets

    @staticmethod
    def create(name: str, run_type: str, config: dict) -> str:
        PresetManager._ensure_dir()
        pid = _slugify(name) or str(uuid.uuid4())[:8]
        path = PRESETS_DIR / f"{pid}.yaml"
        c = 1
        while path.exists():
            pid = (f"{_slugify(name) or str(uuid.uuid4())[:8]}-{c}")
            c += 1
            path = PRESETS_DIR / f"{pid}.yaml"

        preset = Preset(
            id=pid, name=name, run_type=run_type, config=config,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
        with open(path, "w") as f:
            yaml.dump(preset.to_dict(), f,
                      default_flow_style=False, allow_unicode=True,
                      sort_keys=False)
        return pid

    @staticmethod
    def get(pid: str) -> Optional[Preset]:
        path = PRESETS_DIR / f"{pid}.yaml"
        if not path.exists():
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        return Preset.from_dict(pid, data) if data else None

    @staticmethod
    def update(pid: str, name: str, run_type: str, config: dict) -> bool:
        path = PRESETS_DIR / f"{pid}.yaml"
        if not path.exists():
            return False
        preset = Preset(
            id=pid, name=name, run_type=run_type, config=config,
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M"))
        with open(path, "w") as f:
            yaml.dump(preset.to_dict(), f,
                      default_flow_style=False, allow_unicode=True,
                      sort_keys=False)
        return True

    @staticmethod
    def delete(pid: str) -> bool:
        path = PRESETS_DIR / f"{pid}.yaml"
        if not path.exists():
            return False
        path.unlink()
        return True


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip().lower()
    s = re.sub(r"[\s]+", "-", s)
    return s[:60] if s else ""
