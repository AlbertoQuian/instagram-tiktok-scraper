# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""Tests for config/settings.py"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from config import settings


class TestLoadAccounts:
    """Tests for settings.load_accounts()."""

    def test_loads_valid_json(self, tmp_accounts):
        with patch.object(settings, "ACCOUNTS_FILE", tmp_accounts):
            data = settings.load_accounts()
        assert data["project"] == "Test Project"
        assert len(data["accounts"]) == 1

    def test_raises_when_file_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with patch.object(settings, "ACCOUNTS_FILE", missing):
            with pytest.raises(FileNotFoundError):
                settings.load_accounts()


class TestGetStudyPeriod:
    """Tests for settings.get_study_period()."""

    def test_returns_configured_period(self, tmp_accounts):
        with patch.object(settings, "ACCOUNTS_FILE", tmp_accounts):
            start, end = settings.get_study_period()
        assert start == "2024-01-01"
        assert end == "2024-06-30"

    def test_returns_defaults_when_no_period(self, tmp_path):
        cfg_file = tmp_path / "accounts.json"
        cfg_file.write_text(json.dumps({"accounts": []}), encoding="utf-8")
        with patch.object(settings, "ACCOUNTS_FILE", cfg_file):
            start, end = settings.get_study_period()
        assert start == "2024-01-01"
        assert end == "2024-12-31"


class TestSettingsConstants:
    """Verify that expected configuration dicts exist and have required keys."""

    def test_instagram_settings_keys(self):
        assert "download_videos" in settings.INSTAGRAM_SETTINGS
        assert "take_screenshots" in settings.INSTAGRAM_SETTINGS
        assert "cookies_path" in settings.INSTAGRAM_SETTINGS

    def test_tiktok_settings_keys(self):
        assert "download_videos" in settings.TIKTOK_SETTINGS
        assert "take_screenshots" in settings.TIKTOK_SETTINGS

    def test_export_settings_keys(self):
        assert "output_dir" in settings.EXPORT_SETTINGS
        assert "filename" in settings.EXPORT_SETTINGS

    def test_per_platform_pause(self):
        assert "pause_between_profiles" in settings.INSTAGRAM_SETTINGS
        assert "pause_between_profiles" in settings.TIKTOK_SETTINGS
        assert isinstance(settings.INSTAGRAM_SETTINGS["pause_between_profiles"], (int, float))
        assert isinstance(settings.TIKTOK_SETTINGS["pause_between_profiles"], (int, float))

    def test_max_posts_setting(self):
        assert isinstance(settings.MAX_POSTS_PER_PROFILE, int)
        assert settings.INSTAGRAM_SETTINGS["max_posts_per_profile"] >= 1
        assert settings.TIKTOK_SETTINGS["max_posts_per_profile"] >= 1

    def test_paths_are_path_objects(self):
        assert isinstance(settings.BASE_DIR, Path)
        assert isinstance(settings.DATA_DIR, Path)
        assert isinstance(settings.RAW_DIR, Path)
        assert isinstance(settings.ACCOUNTS_FILE, Path)
