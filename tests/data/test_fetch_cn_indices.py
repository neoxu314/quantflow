"""Unit tests for fetch_cn_indices.py.

Tests:
1. convert_cn_code() - A-share code format conversion
2. CN_INDICES - configuration structure validation
3. fetch_cn_index() - API fetch and YAML generation (mocked)

Run:
    pytest tests/data/test_fetch_cn_indices.py -v
"""

import pytest
import pandas as pd
import yaml
from unittest.mock import Mock, patch, MagicMock


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


class TestFetchCnIndex:
    """Test fetch_cn_index() function."""

    @patch("quantflow.data.fetch_cn_indices.ak", create=True)
    def test_fetch_and_convert(self, mock_ak, tmp_path):
        """Should fetch data, convert codes, write YAML."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index
        
        # Mock akshare response
        mock_df = pd.DataFrame({
            "品种代码": ["600000", "000001", "300001"],
            "品种名称": ["浦发银行", "平安银行", "特锐德"]
        })
        mock_ak.index_stock_cons.return_value = mock_df
        
        # Mock project root path
        with patch("quantflow.data.fetch_cn_indices.Path") as mock_path:
            # Create chain: Path(__file__) -> parent^4 -> mock_project_root
            mock_file = MagicMock()
            mock_p1 = MagicMock()
            mock_p2 = MagicMock()
            mock_p3 = MagicMock()
            mock_project_root = MagicMock()
            
            mock_file.parent = mock_p1
            mock_p1.parent = mock_p2
            mock_p2.parent = mock_p3
            mock_p3.parent = mock_project_root
            
            mock_path.return_value = mock_file
            
            # Setup division: mock_project_root / "watchlists" returns intermediate
            # intermediate / filename returns tmp_path / filename
            mock_intermediate = MagicMock()
            mock_intermediate.__truediv__ = lambda self, key: tmp_path / key
            mock_project_root.__truediv__ = lambda self, key: mock_intermediate
            
            # Call function
            fetch_cn_index(
                index_name="中证500",
                symbol="000905",
                en_name="CSI 500",
                filename="test_output.yaml"
            )
        
        # Verify akshare called with correct symbol
        mock_ak.index_stock_cons.assert_called_once_with(symbol="000905")
        
        # Verify YAML file created
        yaml_file = tmp_path / "test_output.yaml"
        assert yaml_file.exists()
        
        # Verify YAML content
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        
        assert data["name"] == "中证500_Components"
        assert "CSI 500" in data["description"]
        assert len(data["items"]) == 3
        
        # Verify code format
        codes = [item["code"] for item in data["items"]]
        assert "600000.SH" in codes
        assert "000001.SZ" in codes
        assert "300001.SZ" in codes
        
        # Verify tags
        for item in data["items"]:
            assert "中证500" in item["tags"]

    @patch("quantflow.data.fetch_cn_indices.ak", create=True)
    def test_empty_dataframe(self, mock_ak, tmp_path):
        """Should handle empty DataFrame gracefully."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index
        
        # Mock empty response
        mock_ak.index_stock_cons.return_value = pd.DataFrame()
        
        with patch("quantflow.data.fetch_cn_indices.Path") as mock_path:
            # Create parent chain
            mock_file = MagicMock()
            mock_p1 = MagicMock()
            mock_p2 = MagicMock()
            mock_p3 = MagicMock()
            mock_project_root = MagicMock()
            
            mock_file.parent = mock_p1
            mock_p1.parent = mock_p2
            mock_p2.parent = mock_p3
            mock_p3.parent = mock_project_root
            
            mock_path.return_value = mock_file
            
            mock_intermediate = MagicMock()
            mock_intermediate.__truediv__ = lambda self, key: tmp_path / key
            mock_project_root.__truediv__ = lambda self, key: mock_intermediate
            
            fetch_cn_index(
                index_name="中证500",
                symbol="000905",
                en_name="CSI 500",
                filename="test_empty.yaml"
            )
        
        # Should not create file for empty data
        yaml_file = tmp_path / "test_empty.yaml"
        assert not yaml_file.exists()

    @patch("quantflow.data.fetch_cn_indices.ak", create=True)
    def test_api_error(self, mock_ak, tmp_path):
        """Should handle API errors gracefully."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index
        
        # Mock API error
        mock_ak.index_stock_cons.side_effect = Exception("Network error")
        
        with patch("quantflow.data.fetch_cn_indices.Path") as mock_path:
            # Create parent chain
            mock_file = MagicMock()
            mock_p1 = MagicMock()
            mock_p2 = MagicMock()
            mock_p3 = MagicMock()
            mock_project_root = MagicMock()
            
            mock_file.parent = mock_p1
            mock_p1.parent = mock_p2
            mock_p2.parent = mock_p3
            mock_p3.parent = mock_project_root
            
            mock_path.return_value = mock_file
            
            mock_intermediate = MagicMock()
            mock_intermediate.__truediv__ = lambda self, key: tmp_path / key
            mock_project_root.__truediv__ = lambda self, key: mock_intermediate
            
            # Should not raise, just log error
            fetch_cn_index(
                index_name="中证500",
                symbol="000905",
                en_name="CSI 500",
                filename="test_error.yaml"
            )
        
        # Should not create file on error
        yaml_file = tmp_path / "test_error.yaml"
        assert not yaml_file.exists()
