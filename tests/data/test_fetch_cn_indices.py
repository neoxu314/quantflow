"""Unit tests for fetch_cn_indices.py.

Tests:
1. convert_cn_code() - A-share code format conversion
2. CN_INDICES - configuration structure validation
3. fetch_cn_index() - API fetch and YAML generation (mocked)

Run:
    pytest tests/data/test_fetch_cn_indices.py -v
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import yaml


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

    def test_whitespace_code(self):
        """Should strip whitespace from codes."""
        from quantflow.data.fetch_cn_indices import convert_cn_code

        result = convert_cn_code("  600000  ")
        assert result == "600000.SH"

    def test_unknown_pattern_defaults_sz(self):
        """Unknown patterns (4/5/7/8/9) should default to SZ."""
        from quantflow.data.fetch_cn_indices import convert_cn_code

        result = convert_cn_code("400001")
        assert result == "400001.SZ"

        result = convert_cn_code("500001")
        assert result == "500001.SZ"

        result = convert_cn_code("700001")
        assert result == "700001.SZ"


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

    def test_has_hs300(self):
        """Should include HS 300 (沪深300)."""
        from quantflow.data.fetch_cn_indices import CN_INDICES

        assert "沪深300" in CN_INDICES
        assert CN_INDICES["沪深300"]["symbol"] == "000300"


class TestFetchCnIndex:
    """Test fetch_cn_index() function."""

    @patch("quantflow.data.fetch_cn_indices.ak")
    def test_fetch_and_convert(self, mock_ak, tmp_path):
        """Should fetch data, convert codes, write YAML."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index

        # Mock akshare response - include all 3 columns to match real API
        mock_ak.index_stock_cons.return_value = pd.DataFrame([
            {"品种代码": "600000", "品种名称": "浦发银行", "纳入日期": "2020-01-01"},
            {"品种代码": "000001", "品种名称": "平安银行", "纳入日期": "2020-01-01"},
            {"品种代码": "300001", "品种名称": "特锐德", "纳入日期": "2020-01-01"}
        ])

        # Call function directly with tmp_path
        fetch_cn_index(
            index_name="中证500",
            symbol="000905",
            en_name="CSI 500",
            filename="test_output.yaml",
            output_dir=tmp_path
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

    @patch("quantflow.data.fetch_cn_indices.ak")
    def test_empty_dataframe(self, mock_ak, tmp_path):
        """Should handle empty DataFrame gracefully."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index

        # Mock empty response
        mock_ak.index_stock_cons.return_value = pd.DataFrame()

        # Call function
        fetch_cn_index(
            index_name="中证500",
            symbol="000905",
            en_name="CSI 500",
            filename="test_empty.yaml",
            output_dir=tmp_path
        )

        # Should not create file for empty data
        yaml_file = tmp_path / "test_empty.yaml"
        assert not yaml_file.exists()

    @patch("quantflow.data.fetch_cn_indices.ak")
    def test_api_error(self, mock_ak, tmp_path):
        """Should handle API errors gracefully."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index

        # Mock API error
        mock_ak.index_stock_cons.side_effect = Exception("Network error")

        # Should not raise, just log error
        fetch_cn_index(
            index_name="中证500",
            symbol="000905",
            en_name="CSI 500",
            filename="test_error.yaml",
            output_dir=tmp_path
        )

        # Should not create file on error
        yaml_file = tmp_path / "test_error.yaml"
        assert not yaml_file.exists()

    @patch("quantflow.data.fetch_cn_indices.ak")
    def test_duplicate_codes(self, mock_ak, tmp_path):
        """Should remove duplicate codes."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index

        # Mock response with duplicates - include all 3 columns
        mock_ak.index_stock_cons.return_value = pd.DataFrame([
            {"品种代码": "600000", "品种名称": "浦发银行", "纳入日期": "2020-01-01"},
            {"品种代码": "600000", "品种名称": "浦发银行", "纳入日期": "2020-01-01"},  # Duplicate
            {"品种代码": "000001", "品种名称": "平安银行", "纳入日期": "2020-01-01"}
        ])

        fetch_cn_index(
            index_name="中证500",
            symbol="000905",
            en_name="CSI 500",
            filename="test_duplicates.yaml",
            output_dir=tmp_path
        )

        # Verify file created
        yaml_file = tmp_path / "test_duplicates.yaml"
        assert yaml_file.exists()

        # Verify duplicates removed
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        codes = [item["code"] for item in data["items"]]
        assert len(codes) == 2  # Only 2 unique codes
        assert codes.count("600000.SH") == 1

    @patch("quantflow.data.fetch_cn_indices.ak")
    def test_invalid_codes_filtered(self, mock_ak, tmp_path):
        """Should filter out invalid codes."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index

        # Mock response with invalid codes - include all 3 columns
        mock_ak.index_stock_cons.return_value = pd.DataFrame([
            {"品种代码": "600000", "品种名称": "浦发银行", "纳入日期": "2020-01-01"},
            {"品种代码": "", "品种名称": "Invalid", "纳入日期": "2020-01-01"},  # Empty
            {"品种代码": "ABC123", "品种名称": "Non-digit", "纳入日期": "2020-01-01"},  # Non-digit
            {"品种代码": "000001", "品种名称": "平安银行", "纳入日期": "2020-01-01"}
        ])

        fetch_cn_index(
            index_name="中证500",
            symbol="000905",
            en_name="CSI 500",
            filename="test_invalid.yaml",
            output_dir=tmp_path
        )

        # Verify file created
        yaml_file = tmp_path / "test_invalid.yaml"
        assert yaml_file.exists()

        # Verify only valid codes included
        with open(yaml_file) as f:
            data = yaml.safe_load(f)

        codes = [item["code"] for item in data["items"]]
        assert "600000.SH" in codes
        assert "000001.SZ" in codes
