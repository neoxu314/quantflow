# A-Share Index Constituents Watchlist Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fetch_cn_indices.py to fetch CSI 500 and ChiNext constituents from akshare, generate watchlist YAMLs.

**Architecture:** Create standalone fetch_cn_indices.py following fetch_indices.py pattern, use akshare API, convert codes to SH/SZ format, output YAML to watchlists/.

**Tech Stack:** Python 3.10+, akshare, yaml, pandas, pathlib

---

## File Structure

```
src/quantflow/data/
├── fetch_cn_indices.py      # NEW - fetch CSI 500 & ChiNext
├── fetch_indices.py         # EXISTING - US indices
└── ...

tests/data/
├── test_fetch_cn_indices.py # NEW - unit tests
├── test_fetch_indices.py    # EXISTING - US index tests
└── ...

watchlists/
├── zhongzheng_500.yaml      # NEW - CSI 500 constituents
├── chuangyeban.yaml         # NEW - ChiNext constituents
└── ...
```

---

### Task 1: Write convert_cn_code() unit tests

**Files:**
- Create: `tests/data/test_fetch_cn_indices.py`

- [ ] **Step 1: Write failing test for convert_cn_code()**

```python
"""Unit tests for fetch_cn_indices.py."""

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_fetch_cn_indices.py::TestConvertCnCode -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'quantflow.data.fetch_cn_indices'"

---

### Task 2: Implement convert_cn_code()

**Files:**
- Create: `src/quantflow/data/fetch_cn_indices.py`

- [ ] **Step 1: Create fetch_cn_indices.py with convert_cn_code()**

```python
"""Fetch A-share index constituents from akshare and generate watchlist YAMLs.

This script fetches CSI 500 (中证500) and ChiNext (创业板指) constituents
from akshare and saves them to watchlists/*.yaml.
"""

import logging
import yaml
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def convert_cn_code(code: str) -> str:
    """Convert A-share stock code to standard format.
    
    Rules:
    - 6xxxxx → SH (Shanghai Stock Exchange)
    - 0xxxxx → SZ (Shenzhen Stock Exchange)
    - 3xxxxx → SZ (ChiNext board on Shenzhen)
    
    Args:
        code: Raw stock code from akshare (e.g., "600000")
    
    Returns:
        Standard format code (e.g., "600000.SH") or empty string if invalid
    """
    if not code or not code.strip():
        return ""
    
    code = code.strip()
    
    if not code.isdigit():
        return ""
    
    if code.startswith("6"):
        return f"{code}.SH"
    elif code.startswith(("0", "3")):
        return f"{code}.SZ"
    else:
        # Fallback to SZ for unknown patterns
        return f"{code}.SZ"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/data/test_fetch_cn_indices.py::TestConvertCnCode -v`

Expected: PASS (5 tests)

- [ ] **Step 3: Commit**

```bash
git add src/quantflow/data/fetch_cn_indices.py tests/data/test_fetch_cn_indices.py
git commit -m "feat(data): add convert_cn_code() for A-share code format conversion"
```

---

### Task 3: Write CN_INDICES configuration tests

**Files:**
- Modify: `tests/data/test_fetch_cn_indices.py`

- [ ] **Step 1: Add CN_INDICES structure test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_fetch_cn_indices.py::TestCNIndicesConfig -v`

Expected: FAIL with "ImportError: cannot import name 'CN_INDICES'"

---

### Task 4: Implement CN_INDICES configuration

**Files:**
- Modify: `src/quantflow/data/fetch_cn_indices.py`

- [ ] **Step 1: Add CN_INDICES to fetch_cn_indices.py**

```python
# Add after imports, before convert_cn_code()

CN_INDICES = {
    "中证500": {
        "symbol": "000905",
        "name": "CSI 500",
        "filename": "zhongzheng_500.yaml"
    },
    "创业板指": {
        "symbol": "399006",
        "name": "ChiNext",
        "filename": "chuangyeban.yaml"
    }
}
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/data/test_fetch_cn_indices.py::TestCNIndicesConfig -v`

Expected: PASS (5 tests)

- [ ] **Step 3: Commit**

```bash
git add src/quantflow/data/fetch_cn_indices.py tests/data/test_fetch_cn_indices.py
git commit -m "feat(data): add CN_INDICES configuration for CSI 500 and ChiNext"
```

---

### Task 5: Write fetch_cn_index() unit tests

**Files:**
- Modify: `tests/data/test_fetch_cn_indices.py`

- [ ] **Step 1: Add fetch_cn_index() tests with mock**

```python
import pandas as pd
from unittest.mock import Mock, patch, MagicMock


class TestFetchCnIndex:
    """Test fetch_cn_index() function."""

    @patch("quantflow.data.fetch_cn_indices.ak")
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
            mock_project_root = MagicMock()
            mock_project_root.__truediv__ = lambda self, key: tmp_path / key
            mock_path.return_value = mock_project_root
            mock_path.__file__ = "dummy.py"
            
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
    
    @patch("quantflow.data.fetch_cn_indices.ak")
    def test_empty_dataframe(self, mock_ak, tmp_path):
        """Should handle empty DataFrame gracefully."""
        from quantflow.data.fetch_cn_indices import fetch_cn_index
        
        # Mock empty response
        mock_ak.index_stock_cons.return_value = pd.DataFrame()
        
        with patch("quantflow.data.fetch_cn_indices.Path") as mock_path:
            mock_project_root = MagicMock()
            mock_project_root.__truediv__ = lambda self, key: tmp_path / key
            mock_path.return_value = mock_project_root
            
            fetch_cn_index(
                index_name="中证500",
                symbol="000905",
                en_name="CSI 500",
                filename="test_empty.yaml"
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
        
        with patch("quantflow.data.fetch_cn_indices.Path") as mock_path:
            mock_project_root = MagicMock()
            mock_project_root.__truediv__ = lambda self, key: tmp_path / key
            mock_path.return_value = mock_project_root
            
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/data/test_fetch_cn_indices.py::TestFetchCnIndex -v`

Expected: FAIL with "ImportError: cannot import name 'fetch_cn_index'"

---

### Task 6: Implement fetch_cn_index()

**Files:**
- Modify: `src/quantflow/data/fetch_cn_indices.py`

- [ ] **Step 1: Add fetch_cn_index() to fetch_cn_indices.py**

```python
def fetch_cn_index(
    index_name: str,
    symbol: str,
    en_name: str,
    filename: str
) -> None:
    """Fetch A-share index constituents and save to YAML.
    
    Args:
        index_name: Chinese name (e.g., "中证500")
        symbol: Index code (e.g., "000905")
        en_name: English name (e.g., "CSI 500")
        filename: Output YAML filename (e.g., "zhongzheng_500.yaml")
    """
    import akshare as ak
    
    logger.info(f"Fetching {index_name} constituents...")
    
    try:
        df = ak.index_stock_cons(symbol=symbol)
        
        if df.empty:
            logger.warning(f"Empty DataFrame for {index_name}")
            return
        
        # Expected columns: 品种代码, 品种名称
        df = df[["品种代码", "品种名称"]].copy()
        df.columns = ["code", "name"]
        
        # Convert codes
        df["code"] = df["code"].apply(convert_cn_code)
        df = df[df["code"] != ""].drop_duplicates(subset=["code"])
        
        if df.empty:
            logger.warning(f"No valid codes for {index_name}")
            return
        
        # Build watchlist
        watchlist = {
            "name": f"{index_name}_Components",
            "description": f"Auto-generated {en_name} ({index_name}) constituents from akshare",
            "items": [
                {
                    "code": row["code"],
                    "name": row["name"],
                    "tags": [index_name]
                }
                for _, row in df.iterrows()
            ]
        }
        
        # Find project root (4 levels up from this file)
        project_root = Path(__file__).parent.parent.parent.parent
        filepath = project_root / "watchlists" / filename
        
        # Write YAML
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            yaml.dump(watchlist, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
        
        logger.info(f"Saved {len(df)} stocks to {filepath}")
        
    except Exception as e:
        logger.error(f"Failed to fetch {index_name}: {e}")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/data/test_fetch_cn_indices.py::TestFetchCnIndex -v`

Expected: PASS (3 tests)

- [ ] **Step 3: Commit**

```bash
git add src/quantflow/data/fetch_cn_indices.py tests/data/test_fetch_cn_indices.py
git commit -m "feat(data): add fetch_cn_index() to fetch A-share index constituents"
```

---

### Task 7: Add main execution block

**Files:**
- Modify: `src/quantflow/data/fetch_cn_indices.py`

- [ ] **Step 1: Add main execution block**

```python
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    for cn_name, config in CN_INDICES.items():
        fetch_cn_index(
            index_name=cn_name,
            symbol=config["symbol"],
            en_name=config["name"],
            filename=config["filename"]
        )
```

- [ ] **Step 2: Commit**

```bash
git add src/quantflow/data/fetch_cn_indices.py
git commit -m "feat(data): add main execution block for fetch_cn_indices"
```

---

### Task 8: Run all unit tests

**Files:**
- Test: `tests/data/test_fetch_cn_indices.py`

- [ ] **Step 1: Run all fetch_cn_indices tests**

Run: `pytest tests/data/test_fetch_cn_indices.py -v`

Expected: PASS (13 tests: 5 convert + 5 config + 3 fetch)

---

### Task 9: Manual integration test (fetch real data)

**Files:**
- Execute: `python -m quantflow.data.fetch_cn_indices`

- [ ] **Step 1: Run fetch_cn_indices.py to fetch real data**

Run: `python -m quantflow.data.fetch_cn_indices`

Expected: 
- Fetches CSI 500 constituents (~500 stocks)
- Fetches ChiNext constituents (~100 stocks)
- Creates `watchlists/zhongzheng_500.yaml`
- Creates `watchlists/chuangyeban.yaml`

- [ ] **Step 2: Verify YAML files exist**

Run: `ls -la watchlists/`

Expected: `zhongzheng_500.yaml` and `chuangyeban.yaml` present

- [ ] **Step 3: Check YAML content**

Run: `head -20 watchlists/zhongzheng_500.yaml`

Expected: 
```yaml
name: 中证500_Components
description: Auto-generated CSI 500 (中证500) constituents from akshare
items:
- code: 600000.SH
  name: 浦发银行
  tags:
  - 中证500
...
```

- [ ] **Step 4: Verify code format**

Run: `grep "code:" watchlists/zhongzheng_500.yaml | head -10`

Expected: All codes have `.SH` or `.SZ` suffix

- [ ] **Step 5: Verify ChiNext YAML**

Run: `head -20 watchlists/chuangyeban.yaml`

Expected: Similar structure with "创业板指" tag

---

### Task 10: Run linting and final verification

**Files:**
- Check: All modified files

- [ ] **Step 1: Run ruff linting**

Run: `ruff check src/quantflow/data/fetch_cn_indices.py`

Expected: No errors

- [ ] **Step 2: Run ruff format check**

Run: `ruff format --check src/quantflow/data/fetch_cn_indices.py`

Expected: No formatting issues

- [ ] **Step 3: Run all data layer tests**

Run: `pytest tests/data/ -v`

Expected: All tests pass (existing + new)

---

### Task 11: Update AGENTS.md documentation

**Files:**
- Modify: `src/quantflow/data/AGENTS.md`

- [ ] **Step 1: Add fetch_cn_indices.py reference**

Find the "WHERE TO LOOK" section and add after `fetch_indices.py` entry:

```markdown
| Generate CN Watchlists | `fetch_cn_indices.py` | `fetch_cn_index()` - Downloads CSI 500 & ChiNext constituents |
```

- [ ] **Step 2: Add to STRUCTURE section**

Find the structure tree and add after `fetch_indices.py`:

```markdown
├── fetch_cn_indices.py  # Fetches CSI 500, ChiNext from akshare -> generates watchlists
```

- [ ] **Step 3: Add test reference**

Find the TESTS section and add:

```markdown
| fetch_cn_indices | `test_fetch_cn_indices.py` | 13 | Unit (convert_cn_code, CN_INDICES structure, fetch_cn_index with mock) |
```

- [ ] **Step 4: Update test count**

Update total test count at the end:

```markdown
**Total: 150 unit + 10 integration = 160 tests**
```

(Previous: 137 unit, new: 13, total: 150)

- [ ] **Step 5: Commit documentation**

```bash
git add src/quantflow/data/AGENTS.md
git commit -m "docs: add fetch_cn_indices.py to AGENTS.md"
```

---

### Task 12: Final commit and verification

- [ ] **Step 1: Verify git status**

Run: `git status`

Expected: Clean working tree (all changes committed)

- [ ] **Step 2: Verify watchlists directory**

Run: `ls -la watchlists/`

Expected: `zhongzheng_500.yaml` and `chuangyeban.yaml` present with other watchlists

- [ ] **Step 3: Run final full test suite**

Run: `pytest tests/data/test_fetch_cn_indices.py -v`

Expected: All 13 tests PASS

---

## Success Criteria Checklist

- [ ] `fetch_cn_indices.py` created with `convert_cn_code()`, `CN_INDICES`, `fetch_cn_index()`
- [ ] All 13 unit tests pass
- [ ] Manual execution generates `zhongzheng_500.yaml` and `chuangyeban.yaml`
- [ ] YAML files contain correct code format (SH/SZ suffix)
- [ ] YAML files contain correct tags (中证500 / 创业板指)
- [ ] Code passes ruff linting
- [ ] AGENTS.md updated
- [ ] All changes committed

---

## Notes

- akshare is already in project dependencies (used in `adapters/akshare.py`)
- No new dependencies needed
- No config changes needed
- No web UI changes needed
- Follows existing pattern from `fetch_indices.py`