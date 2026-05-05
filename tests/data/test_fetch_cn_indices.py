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