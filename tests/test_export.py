# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""Tests for utils/export.py"""

import json
import pandas as pd
import pytest
from types import SimpleNamespace
from pathlib import Path

from utils.export import (
    CSV_COLUMNS,
    build_csv_row,
    collect_metadata_files,
    export_to_csv,
    parse_metadata_file,
)


class TestCSVColumns:
    """Verify the canonical column list."""

    def test_column_count(self):
        assert len(CSV_COLUMNS) == 24

    def test_first_and_last(self):
        assert CSV_COLUMNS[0] == "category"
        assert CSV_COLUMNS[-1] == "notes"


class TestCollectMetadataFiles:
    """Tests for collect_metadata_files()."""

    def test_finds_metadata_files(self, raw_tree):
        files = collect_metadata_files(raw_tree)
        assert len(files) == 2
        assert all(f.name.endswith("_metadata.json") for f in files)

    def test_returns_empty_for_empty_dir(self, tmp_path):
        assert collect_metadata_files(tmp_path) == []


class TestParseMetadataFile:
    """Tests for parse_metadata_file()."""

    def test_returns_platform_and_category(self, raw_tree):
        ig_meta = list((raw_tree / "instagram").rglob("*_metadata.json"))[0]
        platform, category, posts = parse_metadata_file(ig_meta, raw_tree)
        assert platform == "instagram"
        assert category == "news"
        assert len(posts) == 1

    def test_tiktok_platform(self, raw_tree):
        tt_meta = list((raw_tree / "tiktok").rglob("*_metadata.json"))[0]
        platform, category, posts = parse_metadata_file(tt_meta, raw_tree)
        assert platform == "tiktok"
        assert category == "news"
        assert len(posts) == 1

    def test_handles_invalid_json(self, tmp_path):
        raw = tmp_path / "raw"
        d = raw / "instagram" / "cat" / "user"
        d.mkdir(parents=True)
        bad = d / "user_metadata.json"
        bad.write_text("{invalid json", encoding="utf-8")
        _, _, posts = parse_metadata_file(bad, raw)
        assert posts == []


class TestBuildCSVRow:
    """Tests for build_csv_row()."""

    def test_all_columns_present(self, sample_post, tmp_path):
        row = build_csv_row(sample_post, "instagram", "news", tmp_path / "meta.json")
        assert set(row.keys()) == set(CSV_COLUMNS)

    def test_media_files_joined(self, sample_post, tmp_path):
        sample_post["media_files"] = ["a.jpg", "b.jpg"]
        row = build_csv_row(sample_post, "instagram", "news", tmp_path / "m.json")
        assert row["media_files"] == "a.jpg; b.jpg"

    def test_hashtags_joined(self, sample_post, tmp_path):
        sample_post["hashtags"] = ["foo", "bar", "baz"]
        row = build_csv_row(sample_post, "instagram", "news", tmp_path / "m.json")
        assert row["hashtags"] == "foo, bar, baz"

    def test_missing_fields_filled_with_defaults(self, tmp_path):
        row = build_csv_row({}, "tiktok", "cat", tmp_path / "m.json")
        assert row["platform"] == "tiktok"
        assert row["category"] == "cat"
        # Engagement fields default to None when missing (preserves the
        # distinction between zero-engagement and unknown values).
        assert row["likes"] is None
        assert row["media_files"] == ""

    def test_missing_video_duration_is_unknown_not_zero(self, tmp_path):
        post = {"format": "video", "media_files": []}
        row = build_csv_row(post, "instagram", "news", tmp_path / "m.json")
        assert row["duration"] is None

    def test_uses_video_duration_alias(self, tmp_path):
        post = {"format": "video", "video_duration": 12.5}
        row = build_csv_row(post, "instagram", "news", tmp_path / "m.json")
        assert row["duration"] == 12.5

    def test_probes_local_video_duration(self, tmp_path, monkeypatch):
        media_dir = tmp_path / "raw" / "instagram" / "test" / "media"
        media_dir.mkdir(parents=True)
        (media_dir / "video.mp4").write_bytes(b"")
        meta_path = media_dir.parent / "test_metadata.json"

        def fake_run(*args, **kwargs):
            return SimpleNamespace(stdout="45.090295\n")

        monkeypatch.setattr("utils.export.subprocess.run", fake_run)
        post = {"format": "video", "media_files": ["video.mp4"]}
        row = build_csv_row(post, "instagram", "news", meta_path)
        assert row["duration"] == 45.09


class TestExportToCSV:
    """Tests for export_to_csv()."""

    def test_creates_csv_with_correct_shape(self, raw_tree, tmp_path):
        out_dir = tmp_path / "exports"
        csv_path = export_to_csv(raw_tree, out_dir, "test.csv")
        assert csv_path.exists()
        df = pd.read_csv(csv_path)
        assert list(df.columns) == CSV_COLUMNS
        assert len(df) == 2  # one IG + one TT post

    def test_csv_sorted_by_category_account_date(self, raw_tree, tmp_path):
        out_dir = tmp_path / "exports"
        csv_path = export_to_csv(raw_tree, out_dir)
        df = pd.read_csv(csv_path)
        assert df["category"].is_monotonic_increasing

    def test_output_dir_created_if_missing(self, raw_tree, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        csv_path = export_to_csv(raw_tree, nested)
        assert csv_path.exists()
