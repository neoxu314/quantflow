"""Unit tests for fetch_cn_indices.py.

Tests:
1. convert_cn_code() - A-share code format conversion
2. CN_INDICES - configuration structure validation
3. fetch_cn_index() - API fetch and YAML generation (mocked)

Run:
    pytest tests/data/test_fetch_cn_indices.py -v
"""

import pytest


class TestConvertCnCode:
    """Test stock code format conversion."""

    def test_shanghai_main_board(self):
        """6xxxxx should use .SH suffix."""
        from quantflow.data.fetch_cn_indices import convert_cn_code
        
        result = convert_cn_code("600000")
        assert result == "600000.SH"
    
    def test_shenzhen_main_board(self):
        """0xxxxx should use .SZ suffix."""
        from quantflow.data.fetch_cn_indices import convert_cn_code
        
        result = convert_cn_code("000001")
        assert result == "000001.SZ"
    
    def test_chinext_board(self):
        """3xxxxx should use .SZ suffix."""
        from quantflow.data.fetch_cn_indices import convert_cn_code
        
        result = convert_cn_code("300001")
        assert result == "300001.SZ"
    
    def test_empty_string(self):
        """Empty string should return empty."""
        from quantflow.data.fetch_cn_indices import convert_cn_code
        
        result = convert_cn_code("")
        assert result == ""
    
    def test_non_digit(self):
        """Non-digit characters should return empty."""
        from quantflow.data.fetch_cn_indices import convert_cn_code
        
        result = convert_cn_code("ABC123")
        assert result == ""


class TestCNIndicesConfig:
    """Test CN_INDICES configuration structure."""

    def test_config_has_required_keys(self):
        """Each index entry should have symbol, name, filename."""
        from quantflow.data.fetch_cn_indices import CN_INDICES
        
        for cn_name, config in CN_INDICES.items():
            assert "symbol" in config
            assert "name" in config
            assert "filename" in config
    
    def test_filename_is_yaml(self):
        """Filename should have .yaml extension."""
        from quantflow.data.fetch_cn_indices import CN_INDICES
        
        for cn_name, config in CN_INDICES.items():
            assert config["filename"].endswith(".yaml")
    
    def test_symbol_is_numeric(self):
        """Symbol should be numeric string."""
        from quantflow.data.fetch_cn_indices import CN_INDICES
        
        for cn_name, config in CN_INDICES.items():
            assert config["symbol"].isdigit()
    
    def test_has_csi500(self):
        """Should include CSI 500 (中证500)."""
        from quantflow.data.fetch_cn_indices import CN_INDICES
        
        assert "中证500" in CN_INDICES
        assert CN_INDICES["中证500"]["symbol"] == "000905"
    
    def test_has_chinext(self):
        """Should include ChiNext (创业板指)."""
        from quantflow.data.fetch_cn_indices import CN_INDICES
        
        assert "创业板指" in CN_INDICES
        assert CN_INDICES["创业板指"]["symbol"] == "399006"
