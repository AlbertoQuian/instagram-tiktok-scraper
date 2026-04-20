# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""
Consolidate scraped metadata from all platforms into a single CSV dataset.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "category",
    "account_name",
    "account_id",
    "platform",
    "post_id",
    "post_url",
    "date",
    "caption",
    "hashtags",
    "likes",
    "likes_hidden",
    "comments",
    "views",
    "shares",
    "fb_likes",
    "format",
    "duration",
    "music_title",
    "music_author",
    "media_files",
    "thumbnail",
    "metadata_file",
    "language",
    "notes",
]


def collect_metadata_files(raw_dir: Path) -> list[Path]:
    """Find all *_metadata.json files under the raw data directory."""
    files = sorted(raw_dir.rglob("*_metadata.json"))
    logger.info("Found %d metadata files", len(files))
    return files


def parse_metadata_file(meta_path: Path, raw_dir: Path) -> tuple[str, str, list[dict]]:
    """
    Parse a metadata JSON file.

    Returns:
        (platform, category, list_of_posts)
    """
    # Directory structure: raw_dir / platform / [category /] username / *_metadata.json
    try:
        rel = meta_path.relative_to(raw_dir)
    except ValueError:
        rel = meta_path
    parts = rel.parts
    platform = parts[0] if len(parts) > 0 else "unknown"
    # If there are 4+ parts: platform/category/username/file
    # If there are 3 parts: platform/username/file (no category)
    category = parts[1] if len(parts) >= 4 else ""

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            posts = json.load(f)
        if not isinstance(posts, list):
            posts = [posts]
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Error reading %s: %s", meta_path, e)
        posts = []

    return platform, category, posts


def build_csv_row(post: dict, platform: str, category: str, meta_path: Path) -> dict:
    """Build a single CSV row from a post dictionary."""
    media = post.get("media_files", [])
    if isinstance(media, list):
        media_str = "; ".join(str(m) for m in media)
    else:
        media_str = str(media)

    hashtags = post.get("hashtags", [])
    if isinstance(hashtags, list):
        hashtags_str = ", ".join(hashtags)
    else:
        hashtags_str = str(hashtags)

    return {
        "category": post.get("category", category),
        "account_name": post.get("account_name", ""),
        "account_id": post.get("account_id", ""),
        "platform": post.get("platform", platform),
        "post_id": post.get("post_id", ""),
        "post_url": post.get("post_url", ""),
        "date": post.get("date", ""),
        "caption": post.get("caption", ""),
        "hashtags": hashtags_str,
        "likes": post.get("likes"),
        "likes_hidden": post.get("likes_hidden", False),
        "comments": post.get("comments"),
        "views": post.get("views"),
        "shares": post.get("shares"),
        "fb_likes": post.get("fb_likes"),
        "format": post.get("format", ""),
        "duration": post.get("duration", 0),
        "music_title": post.get("music_title", ""),
        "music_author": post.get("music_author", ""),
        "media_files": media_str,
        "thumbnail": post.get("thumbnail", ""),
        "metadata_file": str(meta_path),
        "language": post.get("language", ""),
        "notes": post.get("notes", ""),
    }


def export_to_csv(
    raw_dir: Path,
    output_dir: Path,
    filename: str = "dataset.csv",
) -> Path:
    """
    Collect all metadata files, build CSV rows, and export a unified dataset.

    Returns:
        Path to the generated CSV file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / filename

    meta_files = collect_metadata_files(raw_dir)
    rows = []

    for meta_path in meta_files:
        platform, category, posts = parse_metadata_file(meta_path, raw_dir)
        for post in posts:
            row = build_csv_row(post, platform, category, meta_path)
            rows.append(row)

    df = pd.DataFrame(rows, columns=CSV_COLUMNS)

    # Sort by category, account, date
    df.sort_values(
        by=["category", "account_name", "date"],
        ascending=[True, True, True],
        inplace=True,
    )

    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    logger.info(
        "CSV exported: %s (%d rows, %d columns)",
        output_path, len(df), len(df.columns),
    )
    return output_path
