# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""
Global settings loaded dynamically from accounts.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, Union

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent


def resolve_data_dir(value: Optional[Union[str, Path]] = None) -> Path:
    configured = value or os.environ.get("SCRAPER_DATA_DIR") or BASE_DIR / "data"
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return path.resolve()


DATA_DIR = resolve_data_dir()
RAW_DIR = DATA_DIR / "raw"
ACCOUNTS_FILE = BASE_DIR / "config" / "accounts.json"


def load_accounts() -> dict:
    """Load account configuration from the JSON file."""
    if not ACCOUNTS_FILE.exists():
        raise FileNotFoundError(
            f"Accounts file not found: {ACCOUNTS_FILE}\n"
            "Copy config/accounts_example.json to config/accounts.json and configure it."
        )
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_study_period() -> tuple[str, str]:
    """Return (start_date, end_date) from the accounts config."""
    cfg = load_accounts()
    period = cfg.get("study_period", {})
    return period.get("start", "2024-01-01"), period.get("end", "2024-12-31")


# Default maximum number of posts fetched per profile
MAX_POSTS_PER_PROFILE = 200

# ── Instagram settings ────────────────────────────────────────────────
INSTAGRAM_SETTINGS = {
    "download_videos": True,
    "take_screenshots": True,
    "cookies_path": BASE_DIR / "config" / "instagram_cookies.json",
    "max_posts_per_profile": MAX_POSTS_PER_PROFILE,
    # Seconds between profiles (anti-rate-limit)
    "pause_between_profiles": 5,
}

# ── TikTok settings ──────────────────────────────────────────────────
TIKTOK_SETTINGS = {
    "download_videos": True,
    "take_screenshots": True,
    "reconstruct_carousels": True,
    "cookies_path": BASE_DIR / "config" / "tiktok_cookies.txt",
    "max_posts_per_profile": MAX_POSTS_PER_PROFILE,
    # yt-dlp inter-request sleep range (seconds)
    "sleep_interval": 3,
    "max_sleep_interval": 6,
    # Seconds between profiles
    "pause_between_profiles": 3,
}

# ── CSV export settings ──────────────────────────────────────────────
EXPORT_SETTINGS = {
    "output_dir": DATA_DIR / "exports",
    "filename": "dataset.csv",
}
