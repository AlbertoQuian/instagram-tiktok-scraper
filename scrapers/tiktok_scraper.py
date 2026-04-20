# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""
TikTok scraper.
Primary method: yt-dlp (no login required).
Optional fallback: TikTokApi (unofficial, may require ms_token).
Supports:
  - Regular video download
  - Carousel reconstruction (image slides → MP4 slideshow)
  - Screenshot generation via embed URLs
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from utils.language import detect_language

logger = logging.getLogger(__name__)


class TikTokScraper:
    """TikTok profile scraper using yt-dlp and optional TikTokApi."""

    def __init__(self, settings: dict, output_dir: Path):
        self.settings = settings
        self.output_dir = output_dir
        self.download_videos = settings.get("download_videos", True)
        self.take_screenshots = settings.get("take_screenshots", True)
        self.max_posts = settings.get("max_posts_per_profile", 200)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def scrape_profile_ytdlp(
        self,
        username: str,
        account_name: str,
        account_id: str,
        category: str,
        start_date: str,
        end_date: str,
        max_posts: int | None = None,
    ) -> list[dict]:
        """
        Scrape a TikTok profile using yt-dlp.

        Returns:
            List of dicts with post metadata.
        """
        max_posts = max_posts or self.max_posts

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

        logger.info(
            "Scraping TikTok @%s (%s, %s) — period %s to %s",
            username, account_name, category or "no-category", start_date, end_date,
        )

        profile_dir = self.output_dir / category / username if category else self.output_dir / username
        media_dir = profile_dir / "media"
        screenshots_dir = profile_dir / "screenshots"
        for d in (profile_dir, media_dir, screenshots_dir):
            d.mkdir(parents=True, exist_ok=True)

        url = f"https://www.tiktok.com/@{username}"
        output_template = str(media_dir / "%(id)s.%(ext)s")

        # ── yt-dlp real download (or metadata-only with --skip-download) ─
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--impersonate", "Chrome-136:Macos-15",
            "-o", output_template,
            "--write-info-json",
            "--write-thumbnail",
            "--convert-thumbnails", "jpg",
            "--no-overwrites",
            "--dateafter", start_date.replace("-", ""),
            "--datebefore", end_date.replace("-", ""),
            "--sleep-interval", "3",
            "--max-sleep-interval", "6",
            "--playlist-items", f"1-{max_posts}",
            url,
        ]

        if not self.download_videos:
            cmd.append("--skip-download")

        # Cookies support
        cookie_path = self.settings.get("cookies_path")
        if cookie_path and Path(cookie_path).exists():
            cmd.extend(["--cookies", str(cookie_path)])
        elif Path("config/tiktok_cookies.txt").exists():
            cmd.extend(["--cookies", "config/tiktok_cookies.txt"])

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=1800,
            )
            if result.returncode != 0:
                logger.warning("yt-dlp warnings for @%s: %s", username, result.stderr[:500])
        except subprocess.TimeoutExpired:
            logger.error("yt-dlp timed out for @%s", username)
            return []
        except FileNotFoundError:
            logger.error("yt-dlp not found. Install with: pip install yt-dlp")
            return []
        except Exception as e:
            logger.error("yt-dlp error for @%s: %s", username, e)
            return []

        # ── Read metadata from .info.json files ─────────────────────────
        posts = []
        for info_file in sorted(media_dir.glob("*.info.json")):
            try:
                with open(info_file, "r", encoding="utf-8") as f:
                    info = json.load(f)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Error reading %s: %s", info_file, e)
                continue

            post = self._extract_ytdlp_data(info, username, account_name, account_id, category)
            if not post:
                continue

            # Date filter (double-check, yt-dlp dateafter/before should handle this)
            date_str = post.get("date", "")
            if date_str:
                try:
                    post_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if post_dt.tzinfo is None:
                        post_dt = post_dt.replace(tzinfo=timezone.utc)
                    if post_dt < start_dt or post_dt > end_dt:
                        continue
                except (ValueError, TypeError):
                    pass

            # Locate downloaded media files
            video_id = post["post_id"]
            media_files = []
            for ext in ("mp4", "webm", "mkv"):
                vf = media_dir / f"{video_id}.{ext}"
                if vf.exists():
                    media_files.append(vf.name)
            post["media_files"] = media_files

            # Locate thumbnail (yt-dlp may save as .image)
            for ext in ("jpg", "jpeg", "webp", "png"):
                tf = media_dir / f"{video_id}.{ext}"
                if tf.exists():
                    post["thumbnail"] = tf.name
                    break
            else:
                # Fallback: rename .image → .jpg
                img_file = media_dir / f"{video_id}.image"
                if img_file.exists():
                    new_tf = media_dir / f"{video_id}.jpg"
                    try:
                        img_file.rename(new_tf)
                        post["thumbnail"] = new_tf.name
                    except OSError:
                        post["thumbnail"] = img_file.name

            # Cleanup orphaned .image if .jpg exists
            orphan = media_dir / f"{video_id}.image"
            if orphan.exists() and (media_dir / f"{video_id}.jpg").exists():
                orphan.unlink()

            post["language"] = detect_language(post.get("caption", ""))
            posts.append(post)

        logger.info("Found %d posts in study period for @%s", len(posts), username)

        # Reconstruct carousels as MP4 slideshows
        self._reconstruct_carousels(posts, media_dir)

        # Update media_files for newly reconstructed carousels
        for post in posts:
            vid = post.get("post_id", "")
            if not post.get("media_files") and vid:
                for ext in ("mp4", "webm", "mkv"):
                    vf = media_dir / f"{vid}.{ext}"
                    if vf.exists():
                        post["media_files"] = [vf.name]
                        break

        # Screenshots
        if self.take_screenshots and posts:
            self._take_screenshots(posts, screenshots_dir)

        # Save metadata
        meta_file = profile_dir / f"{username}_metadata.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)

        logger.info(
            "TikTok @%s complete: %d posts saved (%s)",
            username, len(posts), meta_file,
        )
        return posts

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------
    def _extract_ytdlp_data(
        self, entry: dict, username: str, account_name: str, account_id: str, category: str,
    ) -> dict | None:
        """Convert a yt-dlp .info.json entry to a standardized post dict."""
        # Skip playlist/channel metadata files written by yt-dlp
        if entry.get("_type") in ("playlist", "multi_video"):
            return None

        video_id = entry.get("id", "")
        if not video_id:
            return None

        # Timestamp — .info.json may have upload_date (YYYYMMDD) or timestamp
        upload_date = entry.get("upload_date", "")
        date_str = ""
        if upload_date:
            try:
                date_obj = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
                date_str = date_obj.isoformat()
            except ValueError:
                pass
        if not date_str:
            ts = entry.get("timestamp") or entry.get("epoch", 0)
            if ts:
                try:
                    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                except (ValueError, OSError):
                    pass

        caption = entry.get("description", "") or entry.get("title", "")
        hashtags = re.findall(r"#(\w+)", caption)

        # Engagement
        likes = entry.get("like_count", 0) or 0
        comments = entry.get("comment_count", 0) or 0
        views = entry.get("view_count", 0) or 0
        shares = entry.get("repost_count", 0) or entry.get("share_count", 0) or 0

        # Format detection: carousel vs video
        fmt = "Video"
        if entry.get("imagePost") or (not entry.get("formats") and entry.get("duration", 0) == 0):
            fmt = "Carousel"

        # Duration
        duration = entry.get("duration", 0) or 0

        # Music metadata
        music_title = entry.get("track", "")
        music_author = entry.get("artist", "")

        # Thumbnail
        thumb = entry.get("thumbnail", "")

        post_url = entry.get("webpage_url", f"https://www.tiktok.com/@{username}/video/{video_id}")

        return {
            "post_id": video_id,
            "post_url": post_url,
            "username": username,
            "account_name": account_name,
            "account_id": account_id,
            "platform": "TikTok",
            "category": category,
            "date": date_str,
            "caption": caption,
            "hashtags": hashtags,
            "likes": likes,
            "comments": comments,
            "views": views,
            "shares": shares,
            "format": fmt,
            "duration": duration,
            "music_title": music_title,
            "music_author": music_author,
            "thumbnail": thumb,
            "media_files": [],
            "language": "",
            "notes": "",
        }

    # ------------------------------------------------------------------
    # Carousel reconstruction (Playwright-based image extraction → MP4)
    # ------------------------------------------------------------------
    def _reconstruct_carousels(self, posts: list[dict], media_dir: Path) -> None:
        """
        Reconstruct carousel (photomode) posts as MP4 videos.
        Extracts images via Playwright from __UNIVERSAL_DATA_FOR_REHYDRATION__,
        downloads audio with yt-dlp, and uses ffmpeg to create a slideshow.
        """
        carousel_posts = []
        for post in posts:
            video_id = post.get("post_id", "")
            if not video_id:
                continue
            has_video = any(
                (media_dir / f"{video_id}.{ext}").exists()
                for ext in ("mp4", "webm", "mkv")
            )
            if not has_video and (media_dir / f"{video_id}.info.json").exists():
                carousel_posts.append(post)

        if not carousel_posts:
            return

        logger.info("Reconstructing %d carousels as MP4 slideshows...", len(carousel_posts))

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed — skipping carousel reconstruction")
            return

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1080, "height": 1920})

                for post in carousel_posts:
                    video_id = post.get("post_id", "")
                    post_url = post.get("post_url", "")
                    output_mp4 = media_dir / f"{video_id}.mp4"

                    if output_mp4.exists():
                        continue

                    logger.info("Processing carousel %s ...", video_id)

                    try:
                        # 1. Extract image URLs via Playwright
                        page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(3000)
                        self._dismiss_tiktok_dialogs(page)
                        page.wait_for_timeout(500)

                        image_urls = page.evaluate("""() => {
                            try {
                                const script = document.getElementById('__UNIVERSAL_DATA_FOR_REHYDRATION__');
                                if (!script) return [];
                                const data = JSON.parse(script.textContent);
                                const detail = data['__DEFAULT_SCOPE__']['webapp.video-detail'];
                                const imagePost = detail.itemInfo.itemStruct.imagePost;
                                if (!imagePost || !imagePost.images) return [];
                                return imagePost.images.map(img => {
                                    const urls = img.imageURL.urlList;
                                    return urls[urls.length - 1] || urls[0];
                                });
                            } catch(e) { return []; }
                        }""")

                        if not image_urls:
                            logger.warning("No carousel images found for %s", video_id)
                            continue

                        logger.info("  %d slides found", len(image_urls))

                        # 2. Download slides to a temp directory
                        tmpdir_path = tempfile.mkdtemp(prefix=f"carousel_{video_id}_")
                        slide_paths = []
                        for i, img_url in enumerate(image_urls, 1):
                            dest = os.path.join(tmpdir_path, f"slide_{i:03d}.jpg")
                            try:
                                req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                                with urllib.request.urlopen(req, timeout=15) as resp:
                                    with open(dest, "wb") as f:
                                        f.write(resp.read())
                                slide_paths.append(dest)
                            except Exception as e:
                                logger.warning("  Error downloading slide %d: %s", i, e)

                        if not slide_paths:
                            logger.warning("  No slides downloaded for %s", video_id)
                            shutil.rmtree(tmpdir_path, ignore_errors=True)
                            continue

                        logger.info("  %d/%d slides downloaded", len(slide_paths), len(image_urls))

                        # 3. Download audio
                        m4a_path = media_dir / f"{video_id}.m4a"
                        if not m4a_path.exists():
                            logger.info("  Downloading audio...")
                            self._download_audio_only(post_url, video_id, media_dir)

                        # 4. Create slideshow with ffmpeg
                        audio_file = str(m4a_path) if m4a_path.exists() else None
                        self._ffmpeg_slideshow(
                            slide_paths, audio_file, str(output_mp4), tmpdir_path,
                        )

                        # 5. Cleanup
                        shutil.rmtree(tmpdir_path, ignore_errors=True)

                        if output_mp4.exists():
                            logger.info("  Video created: %s (%.1f MB)",
                                        output_mp4.name,
                                        output_mp4.stat().st_size / 1024 / 1024)
                            post["media_files"] = [output_mp4.name]
                            post["format"] = "Carousel"
                            post["notes"] = f"carousel_reconstructed ({len(slide_paths)} slides)"
                            # Remove loose .m4a since it's embedded in the mp4
                            if m4a_path.exists():
                                m4a_path.unlink()
                        else:
                            logger.warning("  Failed to create video for %s", video_id)

                    except Exception as e:
                        logger.warning("Error reconstructing carousel %s: %s", video_id, e)

                    page.wait_for_timeout(1500)

                browser.close()
        except Exception as e:
            logger.warning("Playwright error during carousel reconstruction: %s", e)

    def _download_audio_only(self, post_url: str, video_id: str, dest_dir: Path) -> bool:
        """Download only the audio track of a TikTok post."""
        output_template = str(dest_dir / f"{video_id}.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-warnings",
            "--impersonate", "Chrome-136:Macos-15",
            "-f", "ba",
            "-o", output_template,
            "--no-overwrites",
            post_url,
        ]
        cookie_path = self.settings.get("cookies_path")
        if cookie_path and Path(cookie_path).exists():
            cmd.extend(["--cookies", str(cookie_path)])
        elif Path("config/tiktok_cookies.txt").exists():
            cmd.extend(["--cookies", "config/tiktok_cookies.txt"])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return result.returncode == 0
        except Exception as e:
            logger.warning("Error downloading audio %s: %s", video_id, e)
            return False

    @staticmethod
    def _get_audio_duration(audio_path: str | Path) -> float:
        """Get audio duration in seconds via ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path),
                ],
                capture_output=True, text=True, timeout=15,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def _ffmpeg_slideshow(
        self, slides: list[str], audio: str | None, output: str, tmpdir: str,
    ) -> bool:
        """Create an MP4 slideshow from slides with optional audio overlay."""
        if not slides:
            return False

        # Calculate slide duration based on audio length
        slide_duration = 3.0
        if audio and os.path.exists(audio):
            audio_dur = self._get_audio_duration(audio)
            if audio_dur > 0 and len(slides) > 0:
                slide_duration = audio_dur / len(slides)
                slide_duration = max(1.0, min(slide_duration, 8.0))

        concat_file = os.path.join(tmpdir, "slides.txt")
        with open(concat_file, "w") as f:
            for slide in slides:
                safe_path = str(slide).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")
                f.write(f"duration {slide_duration}\n")
            # Repeat last frame to avoid ffmpeg cut
            safe_path = str(slides[-1]).replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
            ]
            if audio and os.path.exists(audio):
                cmd.extend(["-i", str(audio)])
            cmd.extend([
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:-1:-1:color=black",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
            ])
            if audio and os.path.exists(audio):
                cmd.extend(["-c:a", "aac", "-b:a", "128k", "-shortest"])
            cmd.append(str(output))

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.warning("ffmpeg exited %d: %s", result.returncode,
                               result.stderr[-1500:])
            return os.path.exists(output)

        except Exception as e:
            logger.warning("ffmpeg error: %s", e)
            return False

    # ------------------------------------------------------------------
    # Screenshots
    # ------------------------------------------------------------------
    def _take_screenshots(self, posts: list[dict], dest_dir: Path):
        """Take screenshots of posts using TikTok embed v2 URLs."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed — skipping TikTok screenshots")
            return

        logger.info("Taking screenshots for %d TikTok posts...", len(posts))

        # Pre-set TikTok consent cookies to avoid cookie banners
        tiktok_cookies = [
            {"name": "cookie-consent", "value": "{%22ga%22:true,%22af%22:true,%22fbp%22:true,%22lip%22:true,%22bing%22:true,%22ttads%22:true,%22reddit%22:true,%22hubspot%22:true,%22version%22:%22v10%22}", "domain": ".tiktok.com", "path": "/"},
            {"name": "ttwid", "value": "1", "domain": ".tiktok.com", "path": "/"},
        ]

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 380, "height": 740},
                locale="en-US",
            )
            context.add_cookies(tiktok_cookies)
            page = context.new_page()

            for post in posts:
                post_id = post.get("post_id", "")
                dest = dest_dir / f"{post_id}.jpg"
                if dest.exists():
                    continue

                if not post_id:
                    continue

                embed_url = f"https://www.tiktok.com/embed/v2/{post_id}"

                try:
                    page.goto(embed_url, wait_until="domcontentloaded", timeout=30_000)
                    page.wait_for_timeout(2000)
                    self._dismiss_tiktok_dialogs(page)
                    try:
                        page.wait_for_selector(
                            'video, img, [class*="video"], [class*="image"]',
                            timeout=8_000,
                        )
                    except Exception:
                        pass
                    time.sleep(2)
                    page.screenshot(
                        path=str(dest), full_page=False, type="jpeg", quality=80,
                    )
                    logger.debug("Screenshot saved: %s", dest)
                except Exception as e:
                    logger.debug("Error taking screenshot of %s: %s", post_id, e)

                time.sleep(1)

            browser.close()

    @staticmethod
    def _dismiss_tiktok_dialogs(page):
        """Dismiss TikTok cookie / login popups via clicks and JS removal."""
        # Try clicking known consent buttons
        selectors = [
            'button:has-text("Accept all")',
            'button:has-text("Decline optional")',
            'button:has-text("Allow all")',
            'button:has-text("Decline optional cookies")',
            '[class*="cookies"] button',
            '[data-e2e="modal-close-inner-button"]',
            'button[aria-label="Close"]',
        ]
        for sel in selectors:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(0.5)
            except Exception:
                pass

        # Forcefully remove cookie banners and overlays via JavaScript
        page.evaluate("""
            () => {
                // Remove elements by common cookie-banner selectors
                const sels = [
                    '[class*="cookie"]', '[class*="Cookie"]',
                    '[class*="consent"]', '[class*="Consent"]',
                    '[id*="cookie"]', '[id*="consent"]',
                    '[class*="banner"]', '[class*="overlay"]',
                    'tiktok-cookie-banner', '[data-testid*="cookie"]',
                ];
                for (const s of sels) {
                    document.querySelectorAll(s).forEach(el => el.remove());
                }
                // Remove any fixed/sticky overlays covering the page
                document.querySelectorAll('div').forEach(el => {
                    const st = window.getComputedStyle(el);
                    if ((st.position === 'fixed' || st.position === 'sticky')
                        && st.zIndex > 100 && el.offsetHeight > 100) {
                        el.remove();
                    }
                });
            }
        """)
        time.sleep(0.3)

    # ------------------------------------------------------------------
    # Batch: all accounts
    # ------------------------------------------------------------------
    def scrape_all_accounts(
        self,
        accounts_config: dict,
        start_date: str,
        end_date: str,
        max_posts: int | None = None,
        category: str | None = None,
    ) -> dict:
        """Scrape all configured TikTok accounts."""
        max_posts = max_posts or self.max_posts
        all_results = {}
        accounts = accounts_config.get("accounts", [])

        for account in accounts:
            acct_category = account.get("category", "")
            if category and acct_category != category:
                continue

            tt_handle = account.get("tiktok", "")
            if not tt_handle:
                logger.warning("No TikTok handle for %s", account.get("account_name", "?"))
                continue

            logger.info("=" * 60)
            logger.info("Processing: %s (@%s) [%s]", account.get("account_name", ""), tt_handle, acct_category or "no-category")
            logger.info("=" * 60)

            try:
                posts = self.scrape_profile_ytdlp(
                    username=tt_handle,
                    account_name=account.get("account_name", ""),
                    account_id=account.get("account_id", ""),
                    category=acct_category,
                    start_date=start_date,
                    end_date=end_date,
                    max_posts=max_posts,
                )
                key = acct_category or "uncategorized"
                all_results.setdefault(key, []).extend(posts)
            except Exception as e:
                logger.error(
                    "Error scraping TikTok @%s (%s): %s",
                    tt_handle, account.get("account_name", ""), e,
                )

            # Pause between profiles
            time.sleep(3)

        return all_results

    def take_screenshots_from_metadata(self) -> int:
        """
        Generate screenshots for already-scraped posts by reading existing
        _metadata.json files. Useful for regenerating screenshots without re-scraping.
        """
        all_posts = []
        dir_map = {}

        for meta_file in self.output_dir.rglob("*_metadata.json"):
            profile_dir = meta_file.parent
            screenshots_dir = profile_dir / "screenshots"
            screenshots_dir.mkdir(parents=True, exist_ok=True)

            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    posts = json.load(f)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Error reading %s: %s", meta_file, e)
                continue

            for post in posts:
                pid = post.get("post_id", "")
                if pid:
                    dir_map[pid] = screenshots_dir
                    all_posts.append(post)

        if not all_posts:
            logger.info("No TikTok metadata files found")
            return 0

        self._take_screenshots_with_dir_map(all_posts, dir_map)
        return len(all_posts)

    def _take_screenshots_with_dir_map(self, posts: list[dict], dir_map: dict):
        """Take screenshots routing each post to its corresponding directory."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed — skipping TikTok screenshots")
            return

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 380, "height": 740},
                locale="en-US",
            )
            page = context.new_page()

            for post in posts:
                post_id = post.get("post_id", "")
                dest_dir = dir_map.get(post_id)
                if not dest_dir:
                    continue

                dest = dest_dir / f"{post_id}.jpg"
                if dest.exists():
                    continue

                if not post_id:
                    continue

                embed_url = f"https://www.tiktok.com/embed/v2/{post_id}"

                try:
                    page.goto(embed_url, wait_until="load", timeout=30_000)
                    self._dismiss_tiktok_dialogs(page)
                    try:
                        page.wait_for_selector(
                            'video, img, [class*="video"], [class*="image"]',
                            timeout=8_000,
                        )
                    except Exception:
                        pass
                    time.sleep(3)
                    page.screenshot(
                        path=str(dest), full_page=False, type="jpeg", quality=80,
                    )
                except Exception as e:
                    logger.debug("Error taking screenshot of %s: %s", post_id, e)

                time.sleep(1)

            browser.close()

    # ------------------------------------------------------------------
    # Optional TikTokApi fallback (unused by default)
    # ------------------------------------------------------------------
    async def _scrape_with_api(
        self, username: str, account_name: str, account_id: str, category: str,
        start_date: str, end_date: str, max_posts: int,
    ) -> list[dict]:
        """
        Alternative scraping via the unofficial TikTokApi library.
        Requires ms_token and may break on API changes.
        """
        try:
            from TikTokApi import TikTokApi
        except ImportError:
            logger.warning("TikTokApi not installed — cannot use API fallback")
            return []

        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

        ms_token = self.settings.get("ms_token", "")
        posts = []

        async with TikTokApi() as api:
            await api.create_sessions(
                ms_tokens=[ms_token] if ms_token else [],
                num_sessions=1,
                sleep_after=3,
            )
            user = api.user(username)
            async for video in user.videos(count=max_posts):
                data = video.as_dict
                post = self._extract_api_data(data, username, account_name, account_id, category)
                if not post:
                    continue

                date_str = post.get("date", "")
                if date_str:
                    try:
                        post_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        if post_dt.tzinfo is None:
                            post_dt = post_dt.replace(tzinfo=timezone.utc)
                        if post_dt < start_dt or post_dt > end_dt:
                            continue
                    except (ValueError, TypeError):
                        pass

                posts.append(post)

        return posts

    def _extract_api_data(
        self, data: dict, username: str, account_name: str, account_id: str, category: str,
    ) -> dict | None:
        """Convert TikTokApi video dict to a standardized post dict."""
        video_id = str(data.get("id", ""))
        if not video_id:
            return None

        create_time = data.get("createTime", 0)
        date_str = ""
        if create_time:
            try:
                date_str = datetime.fromtimestamp(int(create_time), tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                pass

        caption = data.get("desc", "")
        hashtags = [t.get("hashtagName", "") for t in data.get("textExtra", []) if t.get("hashtagName")]

        stats = data.get("stats", {})
        likes = stats.get("diggCount", 0) or stats.get("likeCount", 0)
        comments = stats.get("commentCount", 0)
        views = stats.get("playCount", 0) or stats.get("viewCount", 0)
        shares = stats.get("shareCount", 0)

        duration = data.get("video", {}).get("duration", 0)

        return {
            "post_id": video_id,
            "post_url": f"https://www.tiktok.com/@{username}/video/{video_id}",
            "username": username,
            "account_name": account_name,
            "account_id": account_id,
            "platform": "TikTok",
            "category": category,
            "date": date_str,
            "caption": caption,
            "hashtags": hashtags,
            "likes": likes,
            "comments": comments,
            "views": views,
            "shares": shares,
            "format": "Video",
            "duration": duration,
            "thumbnail": data.get("video", {}).get("cover", ""),
            "media_files": [],
            "notes": "",
        }
