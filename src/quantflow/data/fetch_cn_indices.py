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
        logger.warning(f"Unknown code pattern: {code}, defaulting to SZ")
        return f"{code}.SZ"
