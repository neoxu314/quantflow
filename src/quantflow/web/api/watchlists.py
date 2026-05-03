"""Watchlist CRUD API."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(prefix="/api", tags=["Watchlists"])

PROJECT_ROOT = Path(__file__).resolve().parents[4]
WATCHLISTS_DIR = PROJECT_ROOT / "watchlists"


class WatchlistItemModel(BaseModel):
    code: str
    name: Optional[str] = None
    tags: List[str] = []
    weight: float = 1.0
    notes: str = ""


class WatchlistModel(BaseModel):
    name: str
    description: str = ""
    items: List[WatchlistItemModel] = []


class WatchlistSummary(BaseModel):
    filename: str
    name: str
    itemCount: int
    path: str


class SearchResult(BaseModel):
    code: str
    found: bool
    inLists: List[str] = []


def _ensure_watchlists_dir():
    """Ensure watchlists directory exists."""
    WATCHLISTS_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/watchlists", response_model=List[WatchlistSummary])
def list_watchlists():
    """List all watchlist files."""
    _ensure_watchlists_dir()
    import yaml

    summaries = []
    for yfile in sorted(WATCHLISTS_DIR.glob("*.yaml")):
        with open(yfile, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        summaries.append(WatchlistSummary(
            filename=yfile.name,
            name=data.get("name", yfile.stem),
            itemCount=len(data.get("items", [])),
            path=f"watchlists/{yfile.name}",
        ))
    return summaries


@router.get("/watchlists/{filename:path}")
def get_watchlist(filename: str):
    """Get a single watchlist's contents."""
    import yaml

    filepath = WATCHLISTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Watchlist not found: {filename}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return {
        "filename": filename,
        "name": data.get("name", ""),
        "description": data.get("description", ""),
        "items": data.get("items", []),
    }


@router.put("/watchlists/{filename:path}", status_code=201)
def save_watchlist(filename: str, watchlist: WatchlistModel):
    """Create or replace a watchlist."""
    import yaml

    if not filename.endswith(".yaml") and not filename.endswith(".yml"):
        filename += ".yaml"

    # Validate filename is safe (no path traversal)
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = WATCHLISTS_DIR / filename

    data = {
        "name": watchlist.name,
        "description": watchlist.description,
        "items": [
            {"code": item.code, "name": item.name, "tags": item.tags}
            for item in watchlist.items
        ],
    }

    _ensure_watchlists_dir()
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return {"filename": filename, "itemCount": len(watchlist.items)}


@router.delete("/watchlists/{filename:path}")
def delete_watchlist(filename: str):
    """Delete a watchlist file."""
    if "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    filepath = WATCHLISTS_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Watchlist not found: {filename}")

    filepath.unlink()
    return {"filename": filename, "deleted": True}


@router.post("/watchlists/search")
def search_stock(query: dict):
    """Search for a stock code across all watchlists."""
    import yaml
    from quantflow.data.base import StockCode

    raw_code = query.get("code", "").strip()
    if not raw_code:
        raise HTTPException(status_code=400, detail="Code is required")

    # Try to auto-complete format
    if "." not in raw_code:
        # Fuzzy match: find watchlist items containing the code
        fuzzy_results = []
        in_lists = []
        _ensure_watchlists_dir()
        for yfile in WATCHLISTS_DIR.glob("*.yaml"):
            with open(yfile, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            for item in data.get("items", []):
                item_code = item.get("code", "")
                if raw_code.upper() in item_code.upper():
                    fuzzy_results.append({"code": item_code, "name": item.get("name")})
                    if yfile.name not in in_lists:
                        in_lists.append(yfile.name)
        return {
            "code": raw_code,
            "found": len(fuzzy_results) > 0,
            "inLists": in_lists,
            "fuzzyMatches": fuzzy_results[:20],
        }

    # Exact format search (contains .)
    _ensure_watchlists_dir()
    in_lists = []
    for yfile in WATCHLISTS_DIR.glob("*.yaml"):
        with open(yfile, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for item in data.get("items", []):
            if item.get("code") == raw_code:
                if yfile.name not in in_lists:
                    in_lists.append(yfile.name)
                break

    return {
        "code": raw_code,
        "found": len(in_lists) > 0,
        "inLists": in_lists,
        "fuzzyMatches": [],
    }
