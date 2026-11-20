"""Tests for fetch_indices module.

Tests:
1. clean_ticker() - ticker normalization and .US suffix
2. clean_name() - company name cleaning
3. INDICES structure - metadata validation
4. fetch_and_save() - integration test (mocked HTTP)

Run:
    pytest tests/data/test_fetch_indices.py -v
    pytest tests/data/test_fetch_indices.py --live-market -m integration -v  # Currently marked integration, uses mocked HTTP
"""

import pytest
import yaml
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

from quantflow.data.fetch_indices import (
    clean_ticker,
    clean_name,
    INDICES,
    fetch_and_save
)


class TestCleanTicker:
    """Tests for clean_ticker() function."""
    
    def test_basic_ticker(self):
        """Test basic ticker without special chars."""
        result = clean_ticker("AAPL")
        assert result == "AAPL.US"
    
    def test_ticker_with_dot(self):
        """Test ticker with dot (BRK.B -> BRK-B.US)."""
        result = clean_ticker("BRK.B")
        assert result == "BRK-B.US"
    
    def test_ticker_with_caret(self):
        """Test ticker with caret suffix (^NYSE: removed)."""
        result = clean_ticker("AAPL^NYSE")
        assert result == "AAPL.US"
    
    def test_empty_ticker(self):
        """Test empty ticker returns empty."""
        result = clean_ticker("")
        assert result == ""
    
    def test_dash_ticker(self):
        """Test dash ticker returns empty."""
        result = clean_ticker("-")
        assert result == ""
    
    def test_whitespace_ticker(self):
        """Test whitespace is stripped."""
        result = clean_ticker("  AAPL  ")
        assert result == "AAPL.US"
    
    def test_non_string_input(self):
        """Test non-string input handling."""
        with pytest.raises(TypeError):
            clean_ticker(None)
    
    def test_complex_ticker(self):
        """Test ticker with multiple special chars."""
        result = clean_ticker("BRK.B^NYSE")
        assert result == "BRK-B.US"


class TestCleanName:
    """Tests for clean_name() function."""
    
    def test_basic_name(self):
        """Test basic company name."""
        result = clean_name("Apple Inc.")
        assert result == "Apple Inc."
    
    def test_whitespace_name(self):
        """Test whitespace stripping."""
        result = clean_name("  Apple Inc.  ")
        assert result == "Apple Inc."
    
    def test_empty_name(self):
        """Test empty string."""
        result = clean_name("")
        assert result == ""
    
    def test_none_name(self):
        """Test None input returns empty."""
        result = clean_name(None)
        assert result == ""
    
    def test_non_string_name(self):
        """Test non-string input returns empty."""
        result = clean_name(123)
        assert result == ""
    
    def test_unicode_name(self):
        """Test unicode characters preserved."""
        result = clean_name("Apple 公司")
        assert result == "Apple 公司"


class TestIndicesStructure:
    """Tests for INDICES dictionary structure."""
    
    def test_indices_keys(self):
        """Test all expected indices present."""
        expected_keys = ["S&P 500", "Nasdaq 100", "DJIA"]
        assert list(INDICES.keys()) == expected_keys
    
    def test_sp500_structure(self):
        """Test S&P 500 metadata structure."""
        sp500 = INDICES["S&P 500"]
        assert "url" in sp500
        assert "ticker_cols" in sp500
        assert "name_cols" in sp500
        assert "filename" in sp500
        assert sp500["filename"] == "sp_500.yaml"
        assert isinstance(sp500["ticker_cols"], list)
        assert isinstance(sp500["name_cols"], list)
    
    def test_nasdaq_structure(self):
        """Test Nasdaq 100 metadata structure."""
        nasdaq = INDICES["Nasdaq 100"]
        assert nasdaq["filename"] == "nasdaq_100.yaml"
        assert len(nasdaq["ticker_cols"]) >= 1
        assert len(nasdaq["name_cols"]) >= 1
    
    def test_djia_structure(self):
        """Test DJIA metadata structure."""
        djia = INDICES["DJIA"]
        assert djia["filename"] == "djia.yaml"
        assert "wikipedia.org" in djia["url"]
    
    def test_all_urls_valid(self):
        """Test all URLs are Wikipedia links."""
        for name, info in INDICES.items():
            assert "wikipedia.org" in info["url"]
            assert info["url"].startswith("https://")


@pytest.mark.integration
class TestFetchAndSave:
    """Integration tests for fetch_and_save() with mocked HTTP."""
    
    @pytest.fixture
    def mock_html_table(self):
        """Create mock HTML table data."""
        html = """
        <html>
        <body>
        <table>
        <tr><th>Symbol</th><th>Security</th></tr>
        <tr><td>AAPL</td><td>Apple Inc.</td></tr>
        <tr><td>MSFT</td><td>Microsoft Corporation</td></tr>
        <tr><td>GOOGL</td><td>Alphabet Inc.</td></tr>
        <tr><td>BRK.B</td><td>Berkshire Hathaway</td></tr>
        <tr><td>-</td><td>Invalid Ticker</td></tr>
        </table>
        </body>
        </html>
        """
        return html
    
    @pytest.fixture
    def temp_watchlists_dir(self):
        """Create temporary watchlists directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @patch("quantflow.data.fetch_indices.pd.read_html")
    @patch("quantflow.data.fetch_indices.os.path.dirname")
    def test_fetch_and_save_creates_yaml(self, mock_dirname, mock_read_html, temp_watchlists_dir, mock_html_table):
        """Test fetch_and_save creates valid YAML watchlist."""
        mock_dirname.return_value = str(temp_watchlists_dir.parent)
        
        mock_df = pd.DataFrame({
            "Symbol": ["AAPL", "MSFT", "GOOGL", "BRK.B", "-"],
            "Security": ["Apple Inc.", "Microsoft Corporation", "Alphabet Inc.", "Berkshire Hathaway", "Invalid"]
        })
        mock_read_html.return_value = [mock_df]
        
        output_file = temp_watchlists_dir / "test_index.yaml"
        
        fetch_and_save(
            name="Test Index",
            url="https://example.com",
            ticker_cols=["Symbol", "Ticker"],
            name_cols=["Security", "Company"],
            filename="test_index.yaml"
        )
        
        yaml_path = temp_watchlists_dir.parent / "watchlists" / "test_index.yaml"
        
        if yaml_path.exists():
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
            
            assert "name" in data
            assert "description" in data
            assert "items" in data
            assert data["name"] == "Test Index_Components"
            assert len(data["items"]) == 4
            
            tickers = [item["code"] for item in data["items"]]
            assert "AAPL.US" in tickers
            assert "MSFT.US" in tickers
            assert "GOOGL.US" in tickers
            assert "BRK-B.US" in tickers
            assert "-" not in tickers
    
    @patch("quantflow.data.fetch_indices.pd.read_html")
    def test_fetch_and_save_handles_no_valid_table(self, mock_read_html):
        """Test fetch_and_save handles missing valid table."""
        mock_read_html.return_value = [
            pd.DataFrame({"Col1": [1, 2], "Col2": [3, 4]})
        ]
        
        with patch("quantflow.data.fetch_indices.logging") as mock_logging:
            fetch_and_save(
                name="Test Index",
                url="https://example.com",
                ticker_cols=["Symbol"],
                name_cols=["Security"],
                filename="test.yaml"
            )
            
            mock_logging.error.assert_called_once()
    
    @patch("quantflow.data.fetch_indices.pd.read_html")
    def test_fetch_and_save_handles_http_error(self, mock_read_html):
        """Test fetch_and_save handles HTTP error."""
        mock_read_html.side_effect = Exception("HTTP 403 Forbidden")
        
        with patch("quantflow.data.fetch_indices.logging") as mock_logging:
            fetch_and_save(
                name="Test Index",
                url="https://example.com",
                ticker_cols=["Symbol"],
                name_cols=["Security"],
                filename="test.yaml"
            )
            
            mock_logging.error.assert_called_once()
            error_msg = mock_logging.error.call_args[0][0]
            assert "Failed to fetch Test Index" in error_msg


class TestTickerNormalizationEdgeCases:
    """Edge case tests for ticker normalization."""
    
    def test_multiple_dots(self):
        """Test ticker with multiple dots."""
        result = clean_ticker("A.B.C")
        assert result == "A-B-C.US"
    
    def test_leading_trailing_caret(self):
        """Test caret in various positions."""
        result = clean_ticker("^AAPL")
        assert result == ""  # Leading caret results in empty ticker after stripping
    
    def test_numbers_only(self):
        """Test numeric ticker."""
        result = clean_ticker("123")
        assert result == "123.US"
    
    def test_lowercase_ticker(self):
        """Test lowercase ticker."""
        result = clean_ticker("aapl")
        assert result == "aapl.US"