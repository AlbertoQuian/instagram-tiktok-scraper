#!/usr/bin/env python3
# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""
CLI entry point for the Instagram & TikTok scraper.
Orchestrates scraping, media downloads, screenshots, and CSV export.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from config.settings import (
    ACCOUNTS_FILE,
    EXPORT_SETTINGS,
    INSTAGRAM_SETTINGS,
    RAW_DIR,
    RATE_LIMIT,
    TIKTOK_SETTINGS,
    get_study_period,
)
from scrapers.instagram_playwright import InstagramPlaywrightScraper
from scrapers.tiktok_scraper import TikTokScraper
from utils.export import export_to_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_accounts() -> dict:
    """Load account configuration from JSON file."""
    if not ACCOUNTS_FILE.exists():
        logger.error(
            "Account config not found: %s\n"
            "Copy config/accounts_example.json to config/accounts.json and configure it.",
            ACCOUNTS_FILE,
        )
        sys.exit(1)
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Instagram & TikTok scraper for academic research",
    )
    parser.add_argument(
        "--platform",
        choices=["instagram", "tiktok", "all"],
        default="all",
        help="Platform to scrape (default: all)",
    )
    parser.add_argument(
        "--category",
        type=str,
        default=None,
        help="Scrape only accounts matching a specific category",
    )
    parser.add_argument(
        "--screenshots-only",
        action="store_true",
        help="Generate screenshots from existing metadata (no scraping)",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Override study period start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="Override study period end date (YYYY-MM-DD)",
    )
    return parser.parse_args()


def run_scraping(
    accounts_config: dict,
    platform: str,
    start_date: str,
    end_date: str,
    category: str | None = None,
) -> None:
    """Run the scraping pipeline for the selected platform(s)."""
    if platform in ("instagram", "all"):
        logger.info("=" * 60)
        logger.info("INSTAGRAM SCRAPING")
        logger.info("=" * 60)
        ig_scraper = InstagramPlaywrightScraper(
            settings=INSTAGRAM_SETTINGS,
            output_dir=RAW_DIR / "instagram",
        )
        ig_scraper.scrape_all_accounts(
            accounts_config=accounts_config,
            start_date=start_date,
            end_date=end_date,
            category=category,
        )

    if platform in ("tiktok", "all"):
        logger.info("=" * 60)
        logger.info("TIKTOK SCRAPING")
        logger.info("=" * 60)
        tt_scraper = TikTokScraper(
            settings=TIKTOK_SETTINGS,
            output_dir=RAW_DIR / "tiktok",
        )
        tt_scraper.scrape_all_accounts(
            accounts_config=accounts_config,
            start_date=start_date,
            end_date=end_date,
            category=category,
        )


def main() -> None:
    """Main entry point."""
    args = parse_args()
    accounts_config = load_accounts()

    # Determine study period
    default_start, default_end = get_study_period()
    start_date = args.start_date or default_start
    end_date = args.end_date or default_end

    # Filter by category
    category = args.category or None

    # Filter specific accounts via environment variable
    env_filter = os.environ.get("SCRAPE_ACCOUNTS")
    if env_filter:
        allowed = {a.strip() for a in env_filter.split(",")}
        accounts_config["accounts"] = [
            a for a in accounts_config.get("accounts", [])
            if a.get("instagram", "") in allowed
            or a.get("tiktok", "") in allowed
        ]
        logger.info("Filtered to accounts: %s", allowed)

    if args.screenshots_only:
        logger.info("Generating screenshots from existing metadata...")
        if args.platform in ("instagram", "all"):
            ig = InstagramPlaywrightScraper(
                settings=INSTAGRAM_SETTINGS,
                output_dir=RAW_DIR / "instagram",
            )
            ig.take_screenshots_from_metadata()
        if args.platform in ("tiktok", "all"):
            tt = TikTokScraper(
                settings=TIKTOK_SETTINGS,
                output_dir=RAW_DIR / "tiktok",
            )
            tt.take_screenshots_from_metadata()
        return

    # Run scraping
    run_scraping(accounts_config, args.platform, start_date, end_date, category)

    # Export CSV (always automatic after scraping)
    logger.info("Exporting consolidated CSV...")
    export_to_csv(
        raw_dir=RAW_DIR,
        output_dir=EXPORT_SETTINGS["output_dir"],
        filename=EXPORT_SETTINGS["filename"],
    )
    logger.info("Export complete.")


if __name__ == "__main__":
    main()
