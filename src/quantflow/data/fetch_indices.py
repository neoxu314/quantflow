"""Fetch indices components from Wikipedia and generate watchlist YAMLs.

This script automatically pulls S&P 500, Nasdaq 100, and DJIA constituents
and converts them into the project's watchlist format (`watchlists/*.yaml`).
"""

import pandas as pd
import logging
import yaml
import os
import re
import urllib.request

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Mapping of index names to (URL, Ticker Cols, Name Cols, Filename)
INDICES = {
    "S&P 500": {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "ticker_cols": ["Symbol", "Ticker"],
        "name_cols": ["Security", "Company"],
        "filename": "sp_500.yaml"
    },
    "Nasdaq 100": {
        "url": "https://en.wikipedia.org/wiki/Nasdaq-100",
        "ticker_cols": ["Ticker", "Symbol"],
        "name_cols": ["Company", "Name", "Security"],
        "filename": "nasdaq_100.yaml"
    },
    "DJIA": {
        "url": "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average",
        "ticker_cols": ["Symbol", "Ticker"],
        "name_cols": ["Company", "Name", "Security"],
        "filename": "djia.yaml"
    }
}

# Custom User-Agent to bypass 403 on Wikipedia
def build_opener():
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)')]
    return opener

urllib.request.install_opener(build_opener())


def clean_ticker(ticker: str) -> str:
    t = re.sub(r'[\^].*$', '', ticker).strip()
    if not t or t == "-":
        return ""
    if "." in t:
        t = t.replace(".", "-")
    return f"{t}.US"


def clean_name(name: str) -> str:
    if not isinstance(name, str):
        return ""
    return name.strip()


def fetch_and_save(name: str, url: str, ticker_cols, name_cols, filename: str):
    logging.info(f"Fetching {name}...")
    try:
        tables = pd.read_html(url)
        df = None
        
        for table in tables:
            ticker_col = None
            name_col = None
            
            for c in ticker_cols:
                matches = [x for x in table.columns if c.lower() == str(x).lower()]
                if matches:
                    ticker_col = matches[0]
                    break
            
            for c in name_cols:
                matches = [x for x in table.columns if c.lower() == str(x).lower()]
                if matches:
                    name_col = matches[0]
                    break
            
            if ticker_col and name_col:
                df = table[[ticker_col, name_col]].copy()
                break
        
        if df is None:
            raise ValueError(f"Could not find valid table in tables from {url}")
            
        df.columns = ['ticker', 'name']
        df['ticker'] = df['ticker'].apply(clean_ticker)
        df['name'] = df['name'].apply(clean_name)
        
        df = df[df['ticker'] != ""].drop_duplicates(subset=['ticker'])
        
        # Navigate from src/quantflow/data up to project root: data -> quantflow -> src -> project_root
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        filepath = os.path.join(project_root, "watchlists", filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        watchlist = {
            "name": f"{name}_Components",
            "description": f"Auto-generated {name} components from Wikipedia",
            "items": []
        }
        
        for _, row in df.iterrows():
            watchlist["items"].append({
                "code": row['ticker'],
                "name": row['name'],
                "tags": [name]
            })
            
        with open(filepath, 'w') as f:
            yaml.dump(watchlist, f, sort_keys=False, allow_unicode=True)
            
        logging.info(f"Successfully fetched {len(df)} tickers. Saved to {filepath}")
        
    except Exception as e:
        logging.error(f"Failed to fetch {name}: {e}")


if __name__ == "__main__":
    for name, info in INDICES.items():
        fetch_and_save(name, info["url"], info["ticker_cols"], info["name_cols"], info["filename"])