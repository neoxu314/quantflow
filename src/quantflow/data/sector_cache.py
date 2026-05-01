"""Sector data cache management module.

Provides caching and management for sector/industry/concept data from multiple sources:
- EM (东方财富): Industry + Concept boards
- THS (同花顺): Industry + Concept boards
- SW (申万): L1/L2/L3 industry classification

Usage:
    from quantflow.data.sector_cache import SectorCache
    
    cache = SectorCache()
    
    # Refresh all sector data
    cache.refresh_all()
    
    # Search for sector by name
    results = cache.search_by_name("半导体")
    
    # Load cached data
    em_industries = cache.load_industries("em")
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import pandas as pd

from quantflow.data.adapters.akshare import AKShareDataSource

logger = logging.getLogger(__name__)


class SectorCache:
    """Sector data cache manager.
    
    Stores sector data in JSON files with timestamps for tracking updates.
    """
    
    DEFAULT_CACHE_DIR = "data/sectors"
    
    SOURCES = ["em", "ths", "sw"]
    SECTOR_TYPES = {
        "em": ["industries", "concepts"],
        "ths": ["industries", "concepts"],
        "sw": ["l1", "l2", "l3"],
    }
    
    # Expected count ranges for validation
    EXPECTED_COUNTS = {
        "em_industries": (50, 100),
        "em_concepts": (200, 600),
        "ths_industries": (50, 150),
        "ths_concepts": (300, 700),
        "sw_l1": (20, 40),
        "sw_l2": (100, 150),
        "sw_l3": (200, 400),
    }
    
    def __init__(self, cache_dir: Optional[str] = None):
        """
        Args:
            cache_dir: Directory for storing cache files. 
                       Default: data/sectors (relative to project root)
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Find project root
            project_root = Path(__file__).parent.parent.parent.parent
            self.cache_dir = project_root / self.DEFAULT_CACHE_DIR
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._init_subdirs()
    
    def _init_subdirs(self):
        """Initialize subdirectories for each source"""
        for source in self.SOURCES:
            subdir = self.cache_dir / source
            subdir.mkdir(parents=True, exist_ok=True)
    
    def _get_metadata_path(self) -> Path:
        """Get metadata file path"""
        return self.cache_dir / "metadata.json"
    
    def _get_sector_path(self, source: str, sector_type: str) -> Path:
        """Get sector data file path"""
        return self.cache_dir / source / f"{sector_type}.json"
    
    def _now(self) -> str:
        """Get current timestamp string"""
        return datetime.now().isoformat()
    
    def load_metadata(self) -> Dict[str, Any]:
        """Load metadata from cache
        
        Returns:
            Metadata dict with update history
        """
        metadata_path = self._get_metadata_path()
        if metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"last_update": None, "sources": {}}
    
    def save_metadata(self, metadata: Dict[str, Any]):
        """Save metadata to cache"""
        metadata_path = self._get_metadata_path()
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    def load_industries(self, source: str) -> pd.DataFrame:
        """Load industry board list from cache
        
        Args:
            source: Data source (em, ths, sw)
        
        Returns:
            DataFrame with columns: code, name
        """
        if source == "sw":
            # For Shenwan, default to L3 (most detailed)
            return self.load_sector_data("sw", "l3")
        return self.load_sector_data(source, "industries")
    
    def load_concepts(self, source: str) -> pd.DataFrame:
        """Load concept board list from cache
        
        Note: Shenwan (sw) has no concepts, returns empty DataFrame
        
        Args:
            source: Data source (em, ths)
        
        Returns:
            DataFrame with columns: code, name
        """
        if source == "sw":
            logger.warning("Shenwan classification has no concept boards")
            return pd.DataFrame(columns=["code", "name"])
        return self.load_sector_data(source, "concepts")
    
    def load_sector_data(self, source: str, sector_type: str) -> pd.DataFrame:
        """Load sector data from cache
        
        Args:
            source: Data source (em, ths, sw)
            sector_type: Sector type (industries, concepts, l1, l2, l3)
        
        Returns:
            DataFrame with columns: code, name
        """
        path = self._get_sector_path(source, sector_type)
        
        if not path.exists():
            logger.warning(f"No cached data for {source}/{sector_type}")
            return pd.DataFrame(columns=["code", "name"])
        
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if "data" not in data:
            return pd.DataFrame(columns=["code", "name"])
        
        df = pd.DataFrame(data["data"])
        return df
    
    def save_sector_data(self, source: str, sector_type: str, df: pd.DataFrame) -> bool:
        """Save sector data to cache
        
        Args:
            source: Data source
            sector_type: Sector type
            df: DataFrame with sector data
        
        Returns:
            True if saved successfully
        """
        if df.empty:
            logger.warning(f"Empty data for {source}/{sector_type}, skipping save")
            return False
        
        # Validate count is in expected range
        count_key = f"{source}_{sector_type}"
        if count_key in self.EXPECTED_COUNTS:
            min_count, max_count = self.EXPECTED_COUNTS[count_key]
            count = len(df)
            if count < min_count or count > max_count:
                logger.warning(
                    f"Count {count} for {count_key} outside expected range ({min_count}-{max_count})"
                )
        
        path = self._get_sector_path(source, sector_type)
        
        data = {
            "meta": {
                "source": source,
                "type": sector_type,
                "update_time": self._now(),
                "total_count": len(df),
            },
            "data": df.to_dict("records"),
        }
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(df)} records to {path}")
        return True
    
    def refresh_source(self, source: str) -> Dict[str, Any]:
        """Refresh all sector data for a specific source
        
        Args:
            source: Data source (em, ths, sw)
        
        Returns:
            Dict with refresh results
        """
        results = {"source": source, "sectors": {}, "errors": []}
        
        sector_types = self.SECTOR_TYPES.get(source, [])
        
        for sector_type in sector_types:
            try:
                # For Shenwan, create source for each level
                if source == "sw":
                    classification = f"sw_{sector_type}"
                else:
                    classification = source
                
                akshare_source = AKShareDataSource(classification=classification)
                
                if sector_type in ["industries", "l1", "l2", "l3"]:
                    df = akshare_source.get_industry_list()
                elif sector_type == "concepts":
                    df = akshare_source.get_concept_list()
                else:
                    continue
                
                # Validate structure
                if "code" not in df.columns or "name" not in df.columns:
                    results["errors"].append(f"{sector_type}: Missing required columns")
                    continue
                
                # Save to cache
                saved = self.save_sector_data(source, sector_type, df)
                results["sectors"][sector_type] = {
                    "count": len(df),
                    "saved": saved,
                }
                
            except Exception as e:
                error_msg = f"{sector_type}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(f"Failed to refresh {source}/{sector_type}: {e}")
        
        return results
    
    def refresh_all(self) -> Dict[str, Any]:
        """Refresh all sector data from all sources
        
        Returns:
            Dict with refresh results for each source
        """
        results = {
            "start_time": self._now(),
            "sources": {},
            "summary": {},
        }
        
        total_count = 0
        total_errors = 0
        
        for source in self.SOURCES:
            source_result = self.refresh_source(source)
            results["sources"][source] = source_result
            
            # Count totals
            for sector_type, info in source_result.get("sectors", {}).items():
                total_count += info.get("count", 0)
            total_errors += len(source_result.get("errors", []))
        
        results["end_time"] = self._now()
        results["summary"] = {
            "total_count": total_count,
            "total_errors": total_errors,
            "success": total_errors == 0,
        }
        
        # Update metadata
        self._update_metadata(results)
        
        return results
    
    def _update_metadata(self, refresh_results: Dict[str, Any]):
        """Update metadata after refresh"""
        metadata = self.load_metadata()
        metadata["last_update"] = refresh_results["end_time"]
        
        if "sources" not in metadata:
            metadata["sources"] = {}
        
        for source, source_result in refresh_results.get("sources", {}).items():
            if source not in metadata["sources"]:
                metadata["sources"][source] = {}
            
            for sector_type, info in source_result.get("sectors", {}).items():
                metadata["sources"][source][sector_type] = {
                    "file": f"{source}/{sector_type}.json",
                    "count": info.get("count", 0),
                    "last_update": refresh_results["end_time"],
                }
        
        self.save_metadata(metadata)
    
    def is_cache_valid(self, max_age_days: int = 30) -> bool:
        """Check if cache is valid (not too old)
        
        Args:
            max_age_days: Maximum age in days (default 30)
        
        Returns:
            True if cache is valid
        """
        metadata = self.load_metadata()
        
        if not metadata.get("last_update"):
            return False
        
        try:
            last_update = datetime.fromisoformat(metadata["last_update"])
            age_days = (datetime.now() - last_update).days
            return age_days <= max_age_days
        except Exception:
            return False
    
    def search_by_name(self, name: str, source: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search sectors by name (supports fuzzy matching)
        
        Args:
            name: Search term (partial match)
            source: Optional source filter (em, ths, sw)
        
        Returns:
            List of matching sectors with source, type, code, name
        """
        results = []
        
        sources_to_search = [source] if source else self.SOURCES
        
        for src in sources_to_search:
            sector_types = self.SECTOR_TYPES.get(src, [])
            
            for sector_type in sector_types:
                df = self.load_sector_data(src, sector_type)
                
                if df.empty:
                    continue
                
                # Fuzzy match (case-insensitive partial match)
                matches = df[df["name"].str.contains(name, case=False, na=False)]
                
                for _, row in matches.iterrows():
                    results.append({
                        "source": src,
                        "type": sector_type,
                        "code": row["code"],
                        "name": row["name"],
                    })
        
        return results
    
    def get_sector_info(self, code: str, source: str, sector_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get info for a specific sector code
        
        Args:
            code: Sector code
            source: Data source
            sector_type: Optional sector type filter
        
        Returns:
            Dict with sector info or None if not found
        """
        sector_types = [sector_type] if sector_type else self.SECTOR_TYPES.get(source, [])
        
        for st in sector_types:
            df = self.load_sector_data(source, st)
            
            if df.empty:
                continue
            
            match = df[df["code"] == code]
            if len(match) > 0:
                row = match.iloc[0]
                return {
                    "source": source,
                    "type": st,
                    "code": row["code"],
                    "name": row["name"],
                }
        
        return None
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics
        
        Returns:
            Dict with cache stats
        """
        metadata = self.load_metadata()
        
        stats = {
            "cache_dir": str(self.cache_dir),
            "last_update": metadata.get("last_update"),
            "is_valid": self.is_cache_valid(),
            "sources": {},
        }
        
        for source in self.SOURCES:
            source_stats = {}
            for sector_type in self.SECTOR_TYPES.get(source, []):
                df = self.load_sector_data(source, sector_type)
                source_stats[sector_type] = {
                    "count": len(df),
                    "has_data": not df.empty,
                }
            stats["sources"][source] = source_stats
        
        return stats
    
    def list_all_sectors(self, source: Optional[str] = None, sector_type: Optional[str] = None) -> pd.DataFrame:
        """List all sectors with optional filters
        
        Args:
            source: Optional source filter
            sector_type: Optional sector type filter
        
        Returns:
            DataFrame with all matching sectors
        """
        all_data = []
        
        sources = [source] if source else self.SOURCES
        
        for src in sources:
            types = [sector_type] if sector_type else self.SECTOR_TYPES.get(src, [])
            
            for st in types:
                df = self.load_sector_data(src, st)
                
                if df.empty:
                    continue
                
                df_copy = df.copy()
                df_copy["source"] = src
                df_copy["sector_type"] = st
                all_data.append(df_copy)
        
        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame(columns=["source", "sector_type", "code", "name"])