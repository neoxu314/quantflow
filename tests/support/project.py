"""Prepare the writable project fixture used by CLI, API and browser tests."""

from pathlib import Path
from shutil import copyfile


def home_environment(home: Path) -> dict[str, str]:
    home.mkdir(parents=True, exist_ok=True)
    return {
        "HOME": str(home),
        "USERPROFILE": str(home),
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
    }


def prepare_project(root: Path, source: Path) -> None:
    import yaml

    from quantflow.config.loader import ConfigLoader

    config_dir = root / "config"
    config_dir.mkdir()
    defaults = ConfigLoader()._get_defaults()
    defaults.update(
        {
            "web": {"host": "127.0.0.1", "port": 8080},
            "lookback": {"calendar_multiplier": 2, "buffer_days": 30},
            "tushare": {"token": ""},
            "yfinance": {"batch": {"chunk_size": 35, "sleep_min": 0, "sleep_max": 0}},
        }
    )
    (config_dir / "quantflow.yaml").write_text(
        yaml.safe_dump(defaults, sort_keys=False),
        encoding="utf-8",
    )
    copyfile(source / "config" / "indicators.yaml", config_dir / "indicators.yaml")
    watchlists = root / "watchlists"
    watchlists.mkdir()
    (watchlists / "djia.yaml").write_text(
        "name: DJIA\nitems:\n- code: AAPL.US\n  name: Apple\n",
        encoding="utf-8",
    )
    (config_dir / "tasks_test.yaml").write_text(
        "tasks:\n- name: djia\n  watchlist: watchlists/djia.yaml\n"
        "  strategies: [daily_bull_mid_range, daily_bull_oversold]\n",
        encoding="utf-8",
    )
