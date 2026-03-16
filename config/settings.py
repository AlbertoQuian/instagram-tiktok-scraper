# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""
Global settings loaded dynamically from accounts.json.
"""

import json
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
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


# ── Instagram settings ────────────────────────────────────────────────
INSTAGRAM_SETTINGS = {
    "download_videos": True,
    "take_screenshots": True,
    "cookies_path": BASE_DIR / "config" / "instagram_cookies.json",
}

# ── TikTok settings ──────────────────────────────────────────────────
TIKTOK_SETTINGS = {
    "download_videos": True,
    "take_screenshots": True,
    "reconstruct_carousels": True,
}

# ── CSV export settings ──────────────────────────────────────────────
EXPORT_SETTINGS = {
    "output_dir": DATA_DIR / "exports",
    "filename": "dataset.csv",
}

# ── Rate limiting (seconds between requests) ─────────────────────────
RATE_LIMIT = {
    "instagram": 3,
    "tiktok": 2,
}
