# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""
Consolidate scraped metadata from all platforms into a single CSV dataset.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".mov", ".m4v"}

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


def _as_number(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    return int(number) if number.is_integer() else round(number, 3)


def _resolve_media_path(media_file: str, meta_path: Path) -> Path | None:
    if not media_file or media_file.startswith(("http://", "https://")):
        return None

    media_path = Path(media_file)
    if media_path.is_absolute():
        candidates = [media_path]
    else:
        candidates = [
            meta_path.parent / media_path,
            meta_path.parent / "media" / media_path,
            meta_path.parent / "media" / media_path.name,
        ]

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _probe_media_duration(media_files: list[str], meta_path: Path):
    for media_file in media_files:
        media_path = _resolve_media_path(str(media_file), meta_path)
        if not media_path or media_path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(media_path),
                ],
                capture_output=True,
                check=False,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            continue
        duration = _as_number(result.stdout.strip())
        if isinstance(duration, (int, float)) and duration > 0:
            return duration
    return None


def _post_duration(post: dict, meta_path: Path, media_files: list[str]):
    for field in ("duration", "video_duration"):
        duration = _as_number(post.get(field))
        if duration is not None and duration != 0:
            return duration

    if str(post.get("format", "")).lower() == "video":
        return _probe_media_duration(media_files, meta_path)
    return None


def build_csv_row(post: dict, platform: str, category: str, meta_path: Path) -> dict:
    """Build a single CSV row from a post dictionary."""
    media = post.get("media_files", [])
    if isinstance(media, list):
        media_str = "; ".join(str(m) for m in media)
        media_files = [str(m) for m in media]
    else:
        media_str = str(media)
        media_files = [item.strip() for item in media_str.split(";") if item.strip()]

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
        "duration": _post_duration(post, meta_path, media_files),
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
