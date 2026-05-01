# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""Tests for Instagram metadata normalization."""

from pathlib import Path

from scrapers.instagram_playwright import InstagramPlaywrightScraper


def test_instagram_video_metadata_uses_play_count_and_duration(tmp_path):
    scraper = InstagramPlaywrightScraper({}, tmp_path)
    post = scraper._build_post_dict(
        {
            "shortcode": "ABC123",
            "taken_at_timestamp": 1_700_000_000,
            "caption": {"text": "Video #test"},
            "like_count": 12,
            "comment_count": 3,
            "play_count": 456,
            "media_type": 2,
            "duration": 7.25,
        },
        "testuser",
        "Test User",
        "T001",
        "news",
    )

    assert post["format"] == "video"
    assert post["views"] == 456
    assert post["duration"] == 7.25


def test_instagram_video_metadata_preserves_zero_views(tmp_path):
    scraper = InstagramPlaywrightScraper({}, Path(tmp_path))
    post = scraper._build_post_dict(
        {
            "shortcode": "DEF456",
            "taken_at_timestamp": 1_700_000_000,
            "like_count": 0,
            "comment_count": 0,
            "video_view_count": 0,
            "media_type": 2,
        },
        "testuser",
        "Test User",
        "T001",
        "news",
    )

    assert post["views"] == 0