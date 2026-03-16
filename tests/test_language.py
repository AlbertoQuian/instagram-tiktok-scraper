# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""Tests for utils/language.py"""

from unittest.mock import patch
from utils.language import detect_language


class TestDetectLanguage:
    """Tests for detect_language()."""

    def test_english_text(self):
        result = detect_language(
            "This is a perfectly normal English sentence with enough words."
        )
        assert result == "en"

    def test_spanish_text(self):
        result = detect_language(
            "Esta es una frase perfectamente normal en español con suficientes palabras."
        )
        assert result == "es"

    def test_empty_string_returns_empty(self):
        assert detect_language("") == ""

    def test_none_returns_empty(self):
        assert detect_language(None) == ""

    def test_short_text_returns_empty(self):
        assert detect_language("Hello") == ""

    def test_only_urls_returns_empty(self):
        assert detect_language("https://example.com https://test.org") == ""

    def test_only_hashtags_returns_empty(self):
        assert detect_language("#one #two #three #four #five") == ""

    def test_only_mentions_returns_empty(self):
        assert detect_language("@user1 @user2 @user3 @user4 @user5") == ""

    def test_strips_urls_before_detection(self):
        text = "This is an English sentence with a link https://example.com inside it."
        result = detect_language(text)
        assert result == "en"

    def test_strips_hashtags_before_detection(self):
        text = "Esta es una frase en español con hashtags #algo #demo en medio."
        result = detect_language(text)
        assert result == "es"

    def test_detector_not_installed(self):
        with patch("utils.language._DETECTOR", None):
            assert detect_language("Some long enough English text here.") == ""

    def test_short_english_with_hashtags(self):
        """Regression: short captions with hashtags must still detect language."""
        result = detect_language(
            "Are these women the future of F1? #Formula1 #F1 #BBCNews"
        )
        assert result == "en"

    def test_short_spanish_text(self):
        result = detect_language("El futuro del periodismo digital")
        assert result == "es"
