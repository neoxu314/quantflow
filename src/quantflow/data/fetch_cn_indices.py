"""Fetch A-share index constituents from akshare and generate watchlist YAMLs.

This script fetches HS 300 (沪深300), CSI 500 (中证500) and ChiNext (创业板指) constituents
from akshare and saves them to watchlists/*.yaml.
"""

import logging
from pathlib import Path
from typing import Optional

import akshare as ak
import yaml

logger = logging.getLogger(__name__)


CN_INDICES = {
    "沪深300": {
        "symbol": "000300",
        "name": "HS 300",
        "filename": "hushen_300.yaml"
    },
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


def fetch_cn_index(
    index_name: str,
    symbol: str,
    en_name: str,
    filename: str,
    output_dir: Optional[Path] = None
) -> None:
    """Fetch A-share index constituents and save to YAML.

    Args:
        index_name: Chinese name (e.g., "中证500")
        symbol: Index code (e.g., "000905")
        en_name: English name (e.g., "CSI 500")
        filename: Output YAML filename (e.g., "zhongzheng_500.yaml")
        output_dir: Optional output directory (defaults to project_root/watchlists)
    """
    logger.info(f"Fetching {index_name} constituents...")

    try:
        df = ak.index_stock_cons(symbol=symbol)

        if df.empty:
            logger.warning(f"Empty DataFrame for {index_name}")
            return

        # Expected columns: 品种代码, 品种名称
        df = df.loc[:, ["品种代码", "品种名称"]].copy()
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

        # Determine output path
        if output_dir is None:
            # Find project root (4 levels up from this file)
            project_root = Path(__file__).parent.parent.parent.parent
            filepath = project_root / "watchlists" / filename
        else:
            filepath = output_dir / filename

        # Write YAML
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w") as f:
            yaml.dump(watchlist, f, sort_keys=False, allow_unicode=True, default_flow_style=False)

        logger.info(f"Saved {len(df)} stocks to {filepath}")

    except Exception as e:
        logger.error(f"Failed to fetch {index_name}: {e}")


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
