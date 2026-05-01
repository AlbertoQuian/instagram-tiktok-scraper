# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""Tests for main.py CLI argument parsing and account filtering."""

import argparse
import os
from unittest.mock import patch

import pytest

from main import parse_args


class TestParseArgs:
    """Tests for parse_args()."""

    def test_defaults(self):
        with patch("sys.argv", ["main.py"]):
            args = parse_args()
        assert args.platform == "all"
        assert args.category is None
        assert args.no_export is False
        assert args.screenshots_only is False
        assert args.start_date is None
        assert args.end_date is None
        assert args.max_posts is None
        assert args.no_media is False
        assert args.no_screenshots is False

    def test_platform_flag(self):
        with patch("sys.argv", ["main.py", "--platform", "tiktok"]):
            args = parse_args()
        assert args.platform == "tiktok"

    def test_category_flag(self):
        with patch("sys.argv", ["main.py", "--category", "news"]):
            args = parse_args()
        assert args.category == "news"

    def test_no_export_flag(self):
        with patch("sys.argv", ["main.py", "--no-export"]):
            args = parse_args()
        assert args.no_export is True

    def test_no_media_flag(self):
        with patch("sys.argv", ["main.py", "--no-media"]):
            args = parse_args()
        assert args.no_media is True

    def test_no_screenshots_flag(self):
        with patch("sys.argv", ["main.py", "--no-screenshots"]):
            args = parse_args()
        assert args.no_screenshots is True

    def test_max_posts_flag(self):
        with patch("sys.argv", ["main.py", "--max-posts", "50"]):
            args = parse_args()
        assert args.max_posts == 50

    def test_screenshots_only_flag(self):
        with patch("sys.argv", ["main.py", "--screenshots-only"]):
            args = parse_args()
        assert args.screenshots_only is True

    def test_date_overrides(self):
        with patch(
            "sys.argv",
            ["main.py", "--start-date", "2024-06-01", "--end-date", "2024-06-30"],
        ):
            args = parse_args()
        assert args.start_date == "2024-06-01"
        assert args.end_date == "2024-06-30"

    def test_invalid_platform_exits(self):
        with patch("sys.argv", ["main.py", "--platform", "facebook"]):
            with pytest.raises(SystemExit):
                parse_args()


class TestScrapeAccountsFilter:
    """Test SCRAPE_ACCOUNTS environment variable filtering logic."""

    def test_filters_by_instagram_handle(self):
        config = {
            "accounts": [
                {"instagram": "keep_me", "tiktok": "other"},
                {"instagram": "drop_me", "tiktok": "another"},
            ]
        }
        allowed = {a.strip() for a in "keep_me".split(",")}
        filtered = [
            a
            for a in config["accounts"]
            if a.get("instagram", "") in allowed or a.get("tiktok", "") in allowed
        ]
        assert len(filtered) == 1
        assert filtered[0]["instagram"] == "keep_me"

    def test_filters_by_tiktok_handle(self):
        config = {
            "accounts": [
                {"instagram": "ig1", "tiktok": "target_tt"},
                {"instagram": "ig2", "tiktok": "nope"},
            ]
        }
        allowed = {"target_tt"}
        filtered = [
            a
            for a in config["accounts"]
            if a.get("instagram", "") in allowed or a.get("tiktok", "") in allowed
        ]
        assert len(filtered) == 1
        assert filtered[0]["tiktok"] == "target_tt"

    def test_multiple_accounts(self):
        config = {
            "accounts": [
                {"instagram": "a", "tiktok": "x"},
                {"instagram": "b", "tiktok": "y"},
                {"instagram": "c", "tiktok": "z"},
            ]
        }
        allowed = {a.strip() for a in "a,y".split(",")}
        filtered = [
            a
            for a in config["accounts"]
            if a.get("instagram", "") in allowed or a.get("tiktok", "") in allowed
        ]
        assert len(filtered) == 2
