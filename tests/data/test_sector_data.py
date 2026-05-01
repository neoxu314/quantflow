"""Tests for sector data fetching and caching.

Tests:
1. Fetch sector lists from all sources (EM/THS/SW)
2. Verify data structure and counts
3. Fetch constituent stocks for selected sectors
4. Save data to cache
5. Validate cached data

Run:
    pytest tests/data/test_sector_data.py -v --tb=short
"""

import pytest
import pandas as pd
import json
from pathlib import Path

from quantflow.data.adapters.akshare import AKShareDataSource
from quantflow.data.sector_cache import SectorCache


@pytest.mark.integration
class TestSectorListFetch:
    """Tests for fetching sector lists from all sources."""
    
    @pytest.fixture
    def em_source(self):
        return AKShareDataSource(classification="em")
    
    @pytest.fixture
    def ths_source(self):
        return AKShareDataSource(classification="ths")
    
    @pytest.fixture
    def sw_l1_source(self):
        return AKShareDataSource(classification="sw_l1")
    
    @pytest.fixture
    def sw_l2_source(self):
        return AKShareDataSource(classification="sw_l2")
    
    @pytest.fixture
    def sw_l3_source(self):
        return AKShareDataSource(classification="sw_l3")
    
    @pytest.fixture
    def cache(self):
        return SectorCache()
    
    def test_em_industry_list(self, em_source, cache):
        """Test EM industry board list."""
        df = em_source.get_industry_list()
        
        assert not df.empty, "EM industry list should not be empty"
        assert "code" in df.columns, "Should have 'code' column"
        assert "name" in df.columns, "Should have 'name' column"
        
        # Validate count range
        count = len(df)
        assert 50 <= count <= 100, f"EM industry count {count} outside expected range (50-100)"
        
        # Save to cache
        saved = cache.save_sector_data("em", "industries", df)
        assert saved, "Should save successfully"
        
        print(f"\nEM Industries: {count} boards")
        print(f"Sample: {df.head(3).to_string()}")
    
    def test_em_concept_list(self, em_source, cache):
        """Test EM concept board list."""
        df = em_source.get_concept_list()
        
        assert not df.empty, "EM concept list should not be empty"
        assert "code" in df.columns
        assert "name" in df.columns
        
        count = len(df)
        assert 200 <= count <= 600, f"EM concept count {count} outside expected range (200-600)"
        
        saved = cache.save_sector_data("em", "concepts", df)
        assert saved
        
        print(f"\nEM Concepts: {count} boards")
    
    def test_ths_industry_list(self, ths_source, cache):
        """Test THS industry board list."""
        df = ths_source.get_industry_list()
        
        assert not df.empty, "THS industry list should not be empty"
        assert "code" in df.columns
        assert "name" in df.columns
        
        count = len(df)
        assert 50 <= count <= 150, f"THS industry count {count} outside expected range (50-150)"
        
        saved = cache.save_sector_data("ths", "industries", df)
        assert saved
        
        print(f"\nTHS Industries: {count} boards")
    
    def test_ths_concept_list(self, ths_source, cache):
        """Test THS concept board list."""
        df = ths_source.get_concept_list()
        
        assert not df.empty, "THS concept list should not be empty"
        assert "code" in df.columns
        assert "name" in df.columns
        
        count = len(df)
        assert 300 <= count <= 700, f"THS concept count {count} outside expected range (300-700)"
        
        saved = cache.save_sector_data("ths", "concepts", df)
        assert saved
        
        print(f"\nTHS Concepts: {count} boards")
    
    def test_sw_l1_list(self, sw_l1_source, cache):
        """Test Shenwan L1 industry list."""
        df = sw_l1_source.get_industry_list()
        
        assert not df.empty, "SW L1 list should not be empty"
        assert "code" in df.columns
        assert "name" in df.columns
        
        count = len(df)
        assert 20 <= count <= 40, f"SW L1 count {count} outside expected range (20-40)"
        
        saved = cache.save_sector_data("sw", "l1", df)
        assert saved
        
        print(f"\nSW L1: {count} industries")
        print(f"Sample: {df.head(5).to_string()}")
    
    def test_sw_l2_list(self, sw_l2_source, cache):
        """Test Shenwan L2 industry list."""
        df = sw_l2_source.get_industry_list()
        
        assert not df.empty, "SW L2 list should not be empty"
        assert "code" in df.columns
        assert "name" in df.columns
        
        count = len(df)
        assert 100 <= count <= 150, f"SW L2 count {count} outside expected range (100-150)"
        
        saved = cache.save_sector_data("sw", "l2", df)
        assert saved
        
        print(f"\nSW L2: {count} industries")
    
    def test_sw_l3_list(self, sw_l3_source, cache):
        """Test Shenwan L3 industry list."""
        df = sw_l3_source.get_industry_list()
        
        assert not df.empty, "SW L3 list should not be empty"
        assert "code" in df.columns
        assert "name" in df.columns
        
        count = len(df)
        assert 200 <= count <= 400, f"SW L3 count {count} outside expected range (200-400)"
        
        saved = cache.save_sector_data("sw", "l3", df)
        assert saved
        
        print(f"\nSW L3: {count} industries")
    
    def test_sw_no_concepts(self, sw_l3_source):
        """Test that Shenwan has no concept boards."""
        df = sw_l3_source.get_concept_list()
        
        assert df.empty, "Shenwan should return empty DataFrame for concepts"


@pytest.mark.integration
class TestConstituentFetch:
    """Tests for fetching constituent stocks from sectors."""
    
    @pytest.fixture
    def em_source(self):
        return AKShareDataSource(classification="em")
    
    @pytest.fixture
    def ths_source(self):
        return AKShareDataSource(classification="ths")
    
    @pytest.fixture
    def sw_source(self):
        return AKShareDataSource(classification="sw_l3")
    
    def test_em_industry_constituents(self, em_source):
        """Test EM industry constituent stocks."""
        # First get an industry code
        industries = em_source.get_industry_list()
        assert not industries.empty
        
        # Pick first industry
        industry_code = industries.iloc[0]["code"]
        industry_name = industries.iloc[0]["name"]
        
        stocks = em_source.get_industry_constituents(industry_code)
        
        assert len(stocks) > 0, f"Industry {industry_name} should have constituents"
        assert all(isinstance(s, type(stocks[0])) for s in stocks), "All should be StockCode objects"
        
        print(f"\nEM Industry '{industry_name}' ({industry_code}): {len(stocks)} stocks")
        print(f"Sample codes: {[s.standard for s in stocks[:5]]}")
    
    def test_em_concept_constituents(self, em_source):
        """Test EM concept constituent stocks."""
        concepts = em_source.get_concept_list()
        assert not concepts.empty
        
        # Pick a concept (try to find a common one)
        concept = concepts.iloc[0]
        concept_code = concept["code"]
        concept_name = concept["name"]
        
        stocks = em_source.get_concept_constituents(concept_code)
        
        assert len(stocks) > 0, f"Concept {concept_name} should have constituents"
        
        print(f"\nEM Concept '{concept_name}' ({concept_code}): {len(stocks)} stocks")
    
    def test_sw_industry_constituents(self, sw_source):
        """Test Shenwan industry constituent stocks."""
        industries = sw_source.get_industry_list()
        assert not industries.empty
        
        # Pick first industry
        industry_code = industries.iloc[0]["code"]
        industry_name = industries.iloc[0]["name"]
        
        stocks = sw_source.get_industry_constituents(industry_code)
        
        assert len(stocks) > 0, f"SW industry {industry_name} should have constituents"
        
        print(f"\nSW Industry '{industry_name}' ({industry_code}): {len(stocks)} stocks")


@pytest.mark.integration
class TestCacheValidation:
    """Tests for validating cached sector data."""
    
    @pytest.fixture
    def cache(self):
        return SectorCache()
    
    def test_metadata_structure(self, cache):
        """Test metadata file structure after refresh."""
        # Ensure data exists
        cache.refresh_all()
        
        metadata = cache.load_metadata()
        
        assert "last_update" in metadata, "Should have last_update"
        assert "sources" in metadata, "Should have sources"
        assert metadata["last_update"] is not None, "Should have update time"
        
        print(f"\nMetadata last_update: {metadata['last_update']}")
    
    def test_sector_file_structure(self, cache):
        """Test sector data file structure."""
        sources_types = [
            ("ths", "industries"),
            ("ths", "concepts"),
            ("sw", "l1"),
            ("sw", "l2"),
            ("sw", "l3"),
        ]
        
        for source, sector_type in sources_types:
            path = cache._get_sector_path(source, sector_type)
            
            if not path.exists():
                print(f"  Skip {source}/{sector_type} (not cached)")
                continue
            
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            assert "meta" in data, "Should have meta section"
            assert "data" in data, "Should have data section"
            assert "update_time" in data["meta"], "Should have update_time"
            assert "total_count" in data["meta"], "Should have total_count"
            
            print(f"\n{source}/{sector_type}:")
            print(f"  Count: {data['meta']['total_count']}")
            print(f"  Update: {data['meta']['update_time']}")
    
    def test_cache_is_valid(self, cache):
        """Test cache validity check."""
        cache.refresh_all()
        
        assert cache.is_cache_valid(max_age_days=30), "Cache should be valid after refresh"
        assert cache.is_cache_valid(max_age_days=0), "Cache should be valid for 0 days (just refreshed)"
    
    def test_search_by_name(self, cache):
        """Test sector name search."""
        cache.refresh_all()
        
        # Search for common terms
        results = cache.search_by_name("电子")
        
        assert len(results) > 0, "Should find '电子' related sectors"
        
        print(f"\nSearch '电子': found {len(results)} results")
        for r in results[:5]:
            print(f"  {r['source']}/{r['type']}: {r['name']} ({r['code']})")
    
    def test_list_all_sectors(self, cache):
        """Test listing all sectors."""
        cache.refresh_all()
        
        all_df = cache.list_all_sectors()
        
        assert not all_df.empty, "Should have sectors"
        assert "source" in all_df.columns
        assert "sector_type" in all_df.columns
        assert "code" in all_df.columns
        assert "name" in all_df.columns
        
        print(f"\nAll sectors total: {len(all_df)}")
        print(f"By source: {all_df.groupby('source').size().to_dict()}")


@pytest.mark.integration
class TestRefreshAll:
    """Test full refresh of all sector data."""
    
    @pytest.fixture
    def cache(self):
        return SectorCache()
    
    def test_refresh_all_sources(self, cache):
        """Test refreshing all sources and validate results."""
        results = cache.refresh_all()
        
        assert "start_time" in results
        assert "end_time" in results
        assert "sources" in results
        assert "summary" in results
        
        # Check summary
        summary = results["summary"]
        print(f"\nRefresh Summary:")
        print(f"  Total count: {summary['total_count']}")
        print(f"  Total errors: {summary['total_errors']}")
        print(f"  Success: {summary['success']}")
        
        # Check each source
        for source, source_result in results["sources"].items():
            print(f"\n{source.upper()}:")
            for sector_type, info in source_result.get("sectors", {}).items():
                print(f"  {sector_type}: {info['count']} records")
            
            if source_result.get("errors"):
                print(f"  Errors: {source_result['errors']}")
        
        # Validate no critical errors
        assert summary["total_errors"] <= 2, f"Too many errors: {summary['total_errors']}"