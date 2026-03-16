# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""
Language detection utility using lingua-py.
"""

import logging
import re

logger = logging.getLogger(__name__)

try:
    from lingua import Language, LanguageDetectorBuilder

    _DETECTOR = (
        LanguageDetectorBuilder.from_all_languages()
        .with_minimum_relative_distance(0.15)
        .build()
    )
    _MIN_CONFIDENCE = 0.08
except ImportError:
    _DETECTOR = None
    _MIN_CONFIDENCE = 0.0
    logger.warning("lingua-language-detector not installed — language detection disabled")


def detect_language(text: str) -> str:
    """Detect language of *text* and return its ISO 639-1 code (e.g. 'es', 'en').

    Returns an empty string when detection fails or lingua is not installed.
    """
    if not _DETECTOR or not text:
        return ""

    # Strip URLs, hashtags and mentions for cleaner detection
    clean = re.sub(r"https?://\S+", "", text)
    clean = re.sub(r"[@#]\w+", "", clean).strip()
    if len(clean) < 10:
        return ""

    result = _DETECTOR.detect_language_of(clean)
    if result is not None:
        return result.iso_code_639_1.name.lower()

    # Fallback: pick top confidence value if above minimum threshold
    confidences = _DETECTOR.compute_language_confidence_values(clean)
    if confidences and confidences[0].value >= _MIN_CONFIDENCE:
        return confidences[0].language.iso_code_639_1.name.lower()
    return ""
