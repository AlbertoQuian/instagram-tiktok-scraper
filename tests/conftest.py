# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""Shared pytest fixtures."""

import json
import pytest
from pathlib import Path


@pytest.fixture
def tmp_accounts(tmp_path):
    """Create a minimal accounts.json in a temp directory and return its path."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    accounts = {
        "project": "Test Project",
        "study_period": {"start": "2024-01-01", "end": "2024-06-30"},
        "accounts": [
            {
                "account_name": "Test Account",
                "account_id": "TEST01",
                "category": "test_cat",
                "instagram": "test_ig",
                "tiktok": "test_tt",
            }
        ],
    }
    path = config_dir / "accounts.json"
    path.write_text(json.dumps(accounts), encoding="utf-8")
    return path


@pytest.fixture
def sample_post():
    """Return a representative post dict."""
    return {
        "post_id": "ABC123",
        "post_url": "https://www.instagram.com/p/ABC123/",
        "account_name": "Test Account",
        "account_id": "TEST01",
        "category": "news",
        "date": "2024-03-15T12:00:00+00:00",
        "caption": "Hello world #test #demo",
        "hashtags": ["test", "demo"],
        "likes": 42,
        "comments": 5,
        "views": 0,
        "shares": 0,
        "fb_likes": 0,
        "format": "image",
        "duration": 0,
        "music_title": "",
        "music_author": "",
        "media_files": ["ABC123.jpg"],
        "thumbnail": "",
        "language": "en",
        "notes": "",
    }


@pytest.fixture
def raw_tree(tmp_path, sample_post):
    """Create a minimal raw/ directory tree with one metadata file per platform."""
    raw = tmp_path / "raw"

    # Instagram metadata
    ig_dir = raw / "instagram" / "news" / "test_ig"
    ig_dir.mkdir(parents=True)
    ig_meta = ig_dir / "test_ig_metadata.json"
    ig_meta.write_text(json.dumps([sample_post]), encoding="utf-8")

    # TikTok metadata
    tt_post = sample_post.copy()
    tt_post.update(
        post_id="7890",
        post_url="https://www.tiktok.com/@test_tt/video/7890",
        format="video",
        duration=15,
        shares=10,
        music_title="Original Sound",
        music_author="test_tt",
        media_files=["7890.mp4"],
    )
    tt_dir = raw / "tiktok" / "news" / "test_tt"
    tt_dir.mkdir(parents=True)
    tt_meta = tt_dir / "test_tt_metadata.json"
    tt_meta.write_text(json.dumps([tt_post]), encoding="utf-8")

    return raw
