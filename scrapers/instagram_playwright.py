# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""
Instagram scraper using Playwright (headless browser).
No credentials required: accesses public profiles directly.
Intercepts the web_profile_info API to retrieve engagement metrics
(likes, comments, views) and exact timestamps without login.
Limitation: without authentication only ~12 recent posts per profile.
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
from datetime import datetime, timezone
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from utils.language import detect_language

logger = logging.getLogger(__name__)

# Maximum number of scrolls to load more grid posts
MAX_SCROLLS = 30
SCROLL_PAUSE = 2.0


class InstagramPlaywrightScraper:
    """Playwright-based Instagram scraper for public profiles."""

    def __init__(self, settings: dict, output_dir: Path):
        self.settings = settings
        self.output_dir = output_dir
        self.download_media = settings.get("download_videos", True)
        self.take_screenshots = settings.get("take_screenshots", True)
        self.cookies_path = self.settings.get("cookies_path") or Path("config/instagram_cookies.json")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def scrape_profile(
        self,
        username: str,
        account_name: str,
        account_id: str,
        category: str,
        start_date: str,
        end_date: str,
        max_posts: int = 200,
    ) -> list[dict]:
        """
        Scrape posts from a public Instagram profile by intercepting
        the web_profile_info API to get full engagement data.

        Returns:
            List of dicts with post metadata.
        """
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

        profile_dir = self.output_dir / category / username if category else self.output_dir / username
        media_dir = profile_dir / "media"
        screenshots_dir = profile_dir / "screenshots"
        profile_dir.mkdir(parents=True, exist_ok=True)
        media_dir.mkdir(exist_ok=True)
        screenshots_dir.mkdir(exist_ok=True)

        logger.info(
            "Scraping Instagram @%s (%s, %s) — period %s to %s",
            username, account_name, category or "no-category", start_date, end_date,
        )

        url = f"https://www.instagram.com/{username}/"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )

            # Load cookies if available
            cookies_file = Path(self.cookies_path)
            if cookies_file.exists():
                try:
                    with open(cookies_file, "r") as f:
                        cookies = json.load(f)
                    SAMESITE_MAP = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "none": "None"}
                    for c in cookies:
                        raw = str(c.get("sameSite", "None")).lower()
                        c["sameSite"] = SAMESITE_MAP.get(raw, "None")
                    context.add_cookies(cookies)
                    logger.info("Instagram cookies loaded from %s", cookies_file)
                except Exception as e:
                    logger.warning("Error loading cookies: %s", e)
            else:
                logger.info("No cookie file found at %s — using anonymous access.", cookies_file)

            page = context.new_page()

            # API interception: capture initial load + GraphQL pagination
            api_nodes: dict[str, dict] = {}
            _has_next = [True]
            _oldest_ts = [float('inf')]
            _end_cursor = [None]
            _request_template = [None]

            def _handle_api_response(response):
                resp_url = response.url
                if not any(k in resp_url for k in (
                    "web_profile_info", "graphql/query", "api/graphql",
                )):
                    return
                try:
                    body = response.json()
                except Exception:
                    return
                data = body.get("data", {})
                if not isinstance(data, dict):
                    return

                edges = []
                pg_info = {}

                # Format 1: web_profile_info (legacy)
                user = data.get("user")
                if isinstance(user, dict):
                    media = user.get("edge_owner_to_timeline_media", {})
                    if media.get("edges"):
                        edges = media["edges"]
                        pg_info = media.get("page_info", {})

                # Format 2: xdt_api user_timeline (2024+)
                if not edges:
                    for key, val in data.items():
                        if ("user_timeline" in key or "user" in key and "timeline" in key) and isinstance(val, dict):
                            if isinstance(val.get("edges"), list) and val["edges"]:
                                sample = val["edges"][0].get("node", {})
                                if "code" in sample or "shortcode" in sample:
                                    edges = val["edges"]
                                    pg_info = val.get("page_info", {})
                                    break

                # Format 3: generic GraphQL (fallback)
                if not edges:
                    for val in data.values():
                        if isinstance(val, dict) and isinstance(val.get("edges"), list) and val["edges"]:
                            sample = val["edges"][0].get("node", {})
                            if any(f in sample for f in ("shortcode", "code", "taken_at_timestamp", "taken_at")):
                                edges = val["edges"]
                                pg_info = val.get("page_info", {})
                                break

                for edge in edges:
                    node = edge.get("node", {})
                    sc = node.get("shortcode") or node.get("code")
                    if sc and sc not in api_nodes:
                        api_nodes[sc] = node
                        ts = node.get("taken_at_timestamp") or node.get("taken_at") or 0
                        if ts and ts < _oldest_ts[0]:
                            _oldest_ts[0] = ts

                if "has_next_page" in pg_info:
                    _has_next[0] = pg_info["has_next_page"]
                if pg_info.get("end_cursor"):
                    _end_cursor[0] = pg_info["end_cursor"]

            def _capture_request_template(request):
                """Capture the first profile GraphQL request to reuse session tokens."""
                if _request_template[0] is not None:
                    return
                if request.method != "POST" or "graphql" not in request.url:
                    return
                body = request.post_data or ""
                if "PolarisProfilePostsQuery" in body or "PolarisProfilePostsTabContentQuery_connection" in body:
                    _request_template[0] = {
                        "url": request.url,
                        "body": body,
                        "headers": {k: v for k, v in request.headers.items()
                                    if k.startswith(("x-", "content-type"))},
                    }

            page.on("response", _handle_api_response)
            page.on("request", _capture_request_template)

            try:
                page.goto(url, wait_until="networkidle", timeout=30_000)
            except PWTimeout:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            self._dismiss_dialogs(page)
            time.sleep(1)

            logger.info(
                "Initial load: %d posts intercepted for @%s",
                len(api_nodes), username,
            )

            # ── Fast API pagination ──────────────────────────────────
            if _has_next[0] and _end_cursor[0] and _request_template[0]:
                self._fast_api_paginate(
                    page, api_nodes, _has_next, _oldest_ts, _end_cursor,
                    _request_template[0], start_dt, max_posts,
                    username=username,
                )

            # ── Grid fallback (scroll) ───────────────────────────────
            if len(api_nodes) < 3:
                logger.info("Few API posts — attempting grid scroll fallback for @%s", username)
                grid_posts = self._collect_grid_posts(page, start_dt, end_dt, max_posts)
                if grid_posts:
                    logger.info("Grid fallback found %d posts", len(grid_posts))
            else:
                grid_posts = []

            # ── Build post list ──────────────────────────────────────
            posts = self._build_posts_from_api(
                api_nodes, username, account_name, account_id, category,
                start_dt, end_dt, media_dir,
            )

            # Merge grid posts not already present
            seen_ids = {p["post_id"] for p in posts}
            for gp in grid_posts:
                if gp.get("post_id") and gp["post_id"] not in seen_ids:
                    gp["account_name"] = account_name
                    gp["account_id"] = account_id
                    gp["category"] = category
                    posts.append(gp)

            # ── Reconstruct photo carousels as MP4 slideshows ────────
            if self.download_media:
                self._reconstruct_ig_carousels(posts, media_dir)

            # ── Repair silent MP4s (DASH-only video streams) ─────────
            if self.download_media:
                self._repair_silent_videos(posts, media_dir)

            # ── Save metadata BEFORE screenshots (so data is not lost if screenshots fail) ──
            meta_file = profile_dir / f"{username}_metadata.json"
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(posts, f, ensure_ascii=False, indent=2)
            logger.info("Metadata saved (%d posts) to %s", len(posts), meta_file)

            # ── Screenshots ──────────────────────────────────────────
            if self.take_screenshots and posts:
                logger.info(
                    "Cooldown before screenshots (10s) to avoid rate-limiting..."
                )
                time.sleep(10)
                logger.info("Taking screenshots for %d posts...", len(posts))
                for idx, post in enumerate(posts):
                    link = post.get("link") or post.get("post_url", "")
                    ss = self._take_post_screenshot(page, link, screenshots_dir, post["post_id"])
                    if ss:
                        post["screenshot"] = str(ss.relative_to(self.output_dir))
                    # Progressive delay: 3s base, extra 1s every 10 screenshots, max 8s
                    delay = min(3 + (idx // 10), 8)
                    time.sleep(delay)

                # Re-save metadata with screenshot paths
                with open(meta_file, "w", encoding="utf-8") as f:
                    json.dump(posts, f, ensure_ascii=False, indent=2)

            browser.close()

        logger.info(
            "Instagram @%s complete: %d posts saved (%s)",
            username, len(posts), meta_file,
        )
        return posts

    # ------------------------------------------------------------------
    # Fast API pagination
    # ------------------------------------------------------------------
    # Known doc_id for PolarisProfilePostsTabContentQuery_connection
    PAGINATION_DOC_ID = "34030839746560163"
    PAGINATION_FRIENDLY_NAME = "PolarisProfilePostsTabContentQuery_connection"

    def _fast_api_paginate(
        self, page, api_nodes, _has_next, _oldest_ts, _end_cursor,
        template, start_dt, max_posts, username=None,
    ):
        """Paginate via direct GraphQL fetch() calls using captured session tokens.

        Rebuilds the request from scratch each page (like the political-party
        scraper) instead of doing fragile regex replacement on the captured body.
        """
        from urllib.parse import parse_qs, urlencode

        logger.info("Starting fast API pagination (cursor: %s...)", str(_end_cursor[0])[:20])
        max_pages = 500

        # Parse the captured template to reuse session tokens
        raw_params = parse_qs(template["body"])
        base_params = {k: v[0] for k, v in raw_params.items()}

        # Build headers from the captured template
        tpl_headers = template.get("headers", {})
        fetch_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-IG-App-ID": tpl_headers.get("x-ig-app-id", "936619743392459"),
            "X-ASBD-ID": tpl_headers.get("x-asbd-id", "359341"),
            "X-FB-Friendly-Name": self.PAGINATION_FRIENDLY_NAME,
            "X-FB-LSD": tpl_headers.get("x-fb-lsd", base_params.get("lsd", "")),
            "X-CSRFToken": tpl_headers.get("x-csrftoken", ""),
        }
        bloks = tpl_headers.get("x-bloks-version-id")
        if bloks:
            fetch_headers["X-Bloks-Version-ID"] = bloks

        # Override pagination fields
        base_params["doc_id"] = self.PAGINATION_DOC_ID
        base_params["fb_api_req_friendly_name"] = self.PAGINATION_FRIENDLY_NAME

        # Extract username from template variables if not provided
        if not username:
            try:
                old_vars = json.loads(base_params.get("variables", "{}"))
                username = old_vars.get("username", "")
            except Exception:
                username = ""

        cursor = _end_cursor[0]

        for page_num in range(max_pages):
            variables = json.dumps({
                "after": cursor,
                "before": None,
                "data": {
                    "count": 12,
                    "include_reel_media_seen_timestamp": True,
                    "include_relationship_info": True,
                    "latest_besties_reel_media": True,
                    "latest_reel_media": True,
                },
                "first": 12,
                "last": None,
                "username": username,
            })
            base_params["variables"] = variables
            body = urlencode(base_params)

            try:
                result = page.evaluate(
                    """async ({body, headers}) => {
                        const r = await fetch('/graphql/query', {
                            method: 'POST',
                            headers: headers,
                            body: body,
                            credentials: 'same-origin',
                        });
                        return await r.json();
                    }""",
                    {"body": body, "headers": fetch_headers},
                )
            except Exception as exc:
                logger.warning("API pagination error on page %d: %s", page_num + 1, exc)
                break

            data = result.get("data", {}) if isinstance(result, dict) else {}
            edges = []
            pg_info = {}

            # Look for edges in response — try user_timeline first, then generic
            for key, val in data.items():
                if "user_timeline" in key and isinstance(val, dict):
                    edges = val.get("edges", [])
                    pg_info = val.get("page_info", {})
                    break

            if not edges:
                for val in data.values():
                    if isinstance(val, dict):
                        if isinstance(val.get("edges"), list) and val["edges"]:
                            edges = val["edges"]
                            pg_info = val.get("page_info", {})
                            break
                        for sub in val.values():
                            if isinstance(sub, dict) and isinstance(sub.get("edges"), list) and sub["edges"]:
                                edges = sub["edges"]
                                pg_info = sub.get("page_info", {})
                                break
                    if edges:
                        break

            if not edges:
                logger.info("API pagination: no edges on page %d. Total: %d", page_num + 1, len(api_nodes))
                break

            new_count = 0
            for edge in edges:
                node = edge.get("node", {})
                sc = node.get("shortcode") or node.get("code")
                if sc and sc not in api_nodes:
                    api_nodes[sc] = node
                    new_count += 1
                    ts = node.get("taken_at_timestamp") or node.get("taken_at") or 0
                    if ts and ts < _oldest_ts[0]:
                        _oldest_ts[0] = ts

            cursor = pg_info.get("end_cursor")
            has_next = pg_info.get("has_next_page", False)
            _has_next[0] = has_next
            _end_cursor[0] = cursor

            logger.debug("API page %d: +%d posts (total %d)", page_num + 1, new_count, len(api_nodes))

            # Reached posts before study period?
            if _oldest_ts[0] != float('inf') and _oldest_ts[0] < start_dt.timestamp():
                logger.info("Reached posts before study period — stopping pagination")
                break

            if not has_next or not cursor:
                logger.info("API pagination: end of feed on page %d. Total: %d", page_num + 1, len(api_nodes))
                break

            if (page_num + 1) % 10 == 0:
                oldest_str = (
                    datetime.fromtimestamp(_oldest_ts[0], tz=timezone.utc).date()
                    if _oldest_ts[0] != float('inf') else '?'
                )
                logger.info(
                    "API page %d: %d posts, oldest: %s",
                    page_num + 1, len(api_nodes), oldest_str,
                )

            time.sleep(0.5)

        logger.info("API pagination complete: %d total posts intercepted", len(api_nodes))

    # ------------------------------------------------------------------
    # Grid fallback (scroll-based)
    # ------------------------------------------------------------------
    def _collect_grid_posts(self, page, start_dt, end_dt, max_posts):
        """Collect posts by scrolling the profile grid (fallback method)."""
        posts = []
        seen = set()

        for scroll_n in range(MAX_SCROLLS):
            links = page.query_selector_all('a[href*="/p/"], a[href*="/reel/"]')
            new_this_round = 0

            for link_el in links:
                href = link_el.get_attribute("href") or ""
                sc = self._extract_shortcode(href)
                if not sc or sc in seen:
                    continue
                seen.add(sc)
                new_this_round += 1

                # Try to get caption and date from alt text
                img = link_el.query_selector("img")
                alt = img.get_attribute("alt") if img else ""
                caption = self._parse_caption_from_alt(alt)
                date_str = self._parse_date_from_alt(alt)

                post = {
                    "post_id": sc,
                    "post_url": f"https://www.instagram.com/p/{sc}/",
                    "link": href,
                    "caption": caption,
                    "date": date_str,
                    "likes": None,
                    "comments": None,
                    "views": None,
                    "format": "image",
                    "media_files": [],
                    "notes": "grid_fallback (no engagement data)",
                }
                posts.append(post)

                if len(posts) >= max_posts:
                    break

            if len(posts) >= max_posts:
                break
            if new_this_round == 0 and scroll_n > 2:
                break

            page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            time.sleep(SCROLL_PAUSE)

        return posts

    # ------------------------------------------------------------------
    # Build post dicts from API nodes
    # ------------------------------------------------------------------
    def _build_posts_from_api(
        self, api_nodes, username, account_name, account_id, category,
        start_dt, end_dt, media_dir,
    ):
        """Convert intercepted API nodes to post dicts, filtering by date."""
        posts = []
        for sc, node in api_nodes.items():
            post = self._build_post_dict(node, username, account_name, account_id, category)
            if not post:
                continue

            # Date filter
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

            # Download media
            if self.download_media:
                # Carousel: legacy edge_sidecar_to_children or newer carousel_media
                sidecar = node.get("edge_sidecar_to_children", {})
                carousel_media = node.get("carousel_media", [])
                if sidecar.get("edges"):
                    media_list = []
                    for i, child_edge in enumerate(sidecar["edges"]):
                        child = child_edge.get("node", {})
                        child_id = f"{sc}_{i+1}"
                        child_video = child.get("video_url", "")
                        if not child_video:
                            versions = child.get("video_versions", [])
                            if versions:
                                child_video = versions[0].get("url", "")
                        if child_video:
                            res = self._download_media_file(child_video, media_dir, child_id, "mp4")
                            if res:
                                media_list.append(str(res.name))
                        child_img = child.get("display_url", "")
                        if not child_img:
                            iv2 = child.get("image_versions2", {})
                            candidates = iv2.get("candidates", [])
                            if candidates:
                                child_img = candidates[0].get("url", "")
                        if child_img:
                            res = self._download_media_file(child_img, media_dir, child_id, "jpg")
                            if res:
                                media_list.append(str(res.name))
                    if media_list:
                        post["media_files"] = media_list
                elif carousel_media:
                    media_list = []
                    for i, child in enumerate(carousel_media):
                        child_id = f"{sc}_{i+1}"
                        child_video = child.get("video_url", "")
                        if not child_video:
                            versions = child.get("video_versions", [])
                            if versions:
                                child_video = versions[0].get("url", "")
                        if child_video:
                            res = self._download_media_file(child_video, media_dir, child_id, "mp4")
                            if res:
                                media_list.append(str(res.name))
                        child_img = child.get("display_url", "")
                        if not child_img:
                            iv2 = child.get("image_versions2", {})
                            candidates = iv2.get("candidates", [])
                            if candidates:
                                child_img = candidates[0].get("url", "")
                        if child_img:
                            res = self._download_media_file(child_img, media_dir, child_id, "jpg")
                            if res:
                                media_list.append(str(res.name))
                    if media_list:
                        post["media_files"] = media_list
                else:
                    # Single post: download video from video_url, image from display_url
                    media_list = []
                    video_url = node.get("video_url", "")
                    if not video_url:
                        versions = node.get("video_versions", [])
                        if versions:
                            video_url = versions[0].get("url", "")
                    if video_url:
                        res = self._download_media_file(video_url, media_dir, sc, "mp4")
                        if res:
                            media_list.append(str(res.name))
                    display_url = node.get("display_url", "")
                    if not display_url:
                        iv2 = node.get("image_versions2", {})
                        candidates = iv2.get("candidates", [])
                        if candidates:
                            display_url = candidates[0].get("url", "")
                    if display_url:
                        res = self._download_media_file(display_url, media_dir, sc, "jpg")
                        if res:
                            media_list.append(str(res.name))
                    if media_list:
                        post["media_files"] = media_list

            post["language"] = detect_language(post.get("caption", ""))
            posts.append(post)

        logger.info("Built %d posts within study period for @%s", len(posts), username)
        return posts

    def _build_post_dict(self, node: dict, username: str, account_name: str, account_id: str, category: str) -> dict | None:
        """Convert a single API node to a standardized post dict."""
        sc = node.get("shortcode") or node.get("code")
        if not sc:
            return None

        # Timestamp
        ts = node.get("taken_at_timestamp") or node.get("taken_at") or 0
        date_str = ""
        if ts:
            try:
                date_str = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            except (ValueError, OSError):
                pass

        # Caption
        caption = ""
        edge_cap = node.get("edge_media_to_caption", {})
        if isinstance(edge_cap, dict) and edge_cap.get("edges"):
            first = edge_cap["edges"][0]
            caption = first.get("node", {}).get("text", "")
        if not caption:
            caption = node.get("caption", {})
            if isinstance(caption, dict):
                caption = caption.get("text", "")
            elif not isinstance(caption, str):
                caption = ""

        # Hashtags
        hashtags = re.findall(r"#(\w+)", caption)

        # Engagement – prefer modern fields first, fall back to legacy
        likes_hidden = bool(node.get("like_and_view_counts_disabled"))
        if likes_hidden:
            # Instagram hides like/view counts: like_count only reflects preview
            # likers (mutual followers), not the real total. Store None.
            likes = None
            views = None
        else:
            likes = node.get("like_count")
            if likes is None:
                likes = (
                    node.get("edge_liked_by", {}).get("count")
                    or node.get("edge_media_preview_like", {}).get("count")
                )
            views = node.get("video_view_count") or node.get("view_count")
        comments = node.get("comment_count")
        if comments is None:
            comments = node.get("edge_media_to_comment", {}).get("count")
        fb_likes = node.get("fb_like_count")

        # Format
        typename = node.get("__typename", "")
        is_video = node.get("is_video", False)
        media_type = node.get("media_type", 0)
        has_sidecar = bool(node.get("edge_sidecar_to_children", {}).get("edges"))
        has_carousel = bool(node.get("carousel_media"))

        if "Sidecar" in typename or media_type == 8 or has_sidecar or has_carousel:
            fmt = "carousel"
        elif is_video or media_type == 2:
            fmt = "video"
        else:
            fmt = "image"

        # Thumbnail
        thumb = node.get("thumbnail_src", "") or node.get("display_url", "")

        link = f"/p/{sc}/"
        notes = ""
        if node.get("product_type") == "clips":
            fmt = "video"
            notes = "reel"
            link = f"/reel/{sc}/"

        return {
            "platform": "Instagram",
            "post_id": sc,
            "post_url": f"https://www.instagram.com/p/{sc}/",
            "link": link,
            "username": username,
            "account_name": account_name,
            "account_id": account_id,
            "category": category,
            "date": date_str,
            "caption": caption,
            "hashtags": hashtags,
            "likes": likes,
            "likes_hidden": likes_hidden,
            "comments": comments,
            "views": views,
            "shares": None,
            "fb_likes": fb_likes,
            "format": fmt,
            "thumbnail": thumb,
            "media_files": [],
            "metadata_file": "",
            "language": "",
            "notes": notes,
        }

    @staticmethod
    def _extract_shortcode(link: str) -> str:
        """Extract shortcode from /p/ABC123/ or /reel/ABC123/."""
        m = re.search(r"/(?:p|reel)/([A-Za-z0-9_-]+)", link)
        return m.group(1) if m else ""

    @staticmethod
    def _parse_caption_from_alt(alt: str) -> str:
        """Extract caption text from an image alt attribute.
        Typical format: 'Photo by <User> on <date>. May be an image of ...'
        """
        if not alt:
            return ""
        parts = alt.split(". ", 1)
        if len(parts) > 1:
            return parts[1].strip()
        return alt

    @staticmethod
    def _parse_date_from_alt(alt: str) -> str:
        """Try to extract a date from the image alt text.
        Format: '... on January 15, 2024 ...'
        """
        months = (
            "January|February|March|April|May|June|"
            "July|August|September|October|November|December"
        )
        pattern = rf"on\s+((?:{months})\s+\d{{1,2}},\s+\d{{4}})"
        m = re.search(pattern, alt)
        if m:
            try:
                dt = datetime.strptime(m.group(1), "%B %d, %Y")
                return dt.isoformat()
            except ValueError:
                pass
        return ""

    # ------------------------------------------------------------------
    # Media download
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Carousel reconstruction (photo carousels → MP4 slideshow)
    # ------------------------------------------------------------------
    def _reconstruct_ig_carousels(self, posts: list[dict], media_dir: Path) -> None:
        """Reconstruct Instagram photo carousels as MP4 slideshows via ffmpeg."""
        carousel_posts = []
        for post in posts:
            if post.get("format") != "carousel":
                continue
            media_files = post.get("media_files", [])
            if not media_files:
                continue
            # Only reconstruct if all media are images (no video slides)
            image_files = [f for f in media_files if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
            if len(image_files) < 2:
                continue
            # Skip if it contains any video slides
            if any(f.lower().endswith((".mp4", ".webm", ".mkv")) for f in media_files):
                continue
            carousel_posts.append((post, image_files))

        if not carousel_posts:
            return

        logger.info("Reconstructing %d Instagram photo carousels as MP4 slideshows...", len(carousel_posts))

        for post, image_files in carousel_posts:
            post_id = post.get("post_id", "")
            output_mp4 = media_dir / f"{post_id}_slideshow.mp4"

            if output_mp4.exists():
                logger.debug("Slideshow already exists: %s", output_mp4.name)
                post["media_files"] = image_files + [output_mp4.name]
                post["notes"] = f"carousel_reconstructed ({len(image_files)} slides)"
                continue

            slide_paths = []
            for fname in image_files:
                fpath = media_dir / fname
                if fpath.exists():
                    slide_paths.append(str(fpath))

            if len(slide_paths) < 2:
                continue

            ok = self._ffmpeg_ig_slideshow(slide_paths, str(output_mp4))
            if ok and output_mp4.exists():
                logger.info("  Slideshow created: %s (%.1f MB, %d slides)",
                            output_mp4.name,
                            output_mp4.stat().st_size / 1024 / 1024,
                            len(slide_paths))
                post["media_files"] = image_files + [output_mp4.name]
                post["notes"] = f"carousel_reconstructed ({len(slide_paths)} slides)"
            else:
                logger.warning("  Failed to create slideshow for %s", post_id)

    @staticmethod
    def _ffmpeg_ig_slideshow(
        slides: list[str], output: str, slide_duration: float = 3.0,
    ) -> bool:
        """Create an MP4 slideshow from image slides (no audio)."""
        if not slides:
            return False

        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="ig_carousel_")
        concat_file = os.path.join(tmpdir, "slides.txt")

        try:
            with open(concat_file, "w") as f:
                for slide in slides:
                    safe_path = str(slide).replace("\\", "/").replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")
                    f.write(f"duration {slide_duration}\n")
                # Repeat last frame to avoid ffmpeg cut
                safe_path = str(slides[-1]).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", concat_file,
                "-vf", "scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:-1:-1:color=black",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30",
                str(output),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                logger.warning("ffmpeg exited %d: %s", result.returncode,
                               result.stderr[-1500:])
            return os.path.exists(output)

        except Exception as e:
            logger.warning("ffmpeg error creating Instagram slideshow: %s", e)
            return False
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Silent-video repair (DASH-only video streams without audio)
    # ------------------------------------------------------------------
    def _repair_silent_videos(self, posts: list[dict], media_dir: Path) -> None:
        """Detect MP4s without an audio stream and re-download them with yt-dlp.

        Instagram's private GraphQL endpoint sometimes returns ``video_url``
        values pointing to a DASH video-only segment (no audio track).  When
        that happens, the downloaded MP4 is silent.  yt-dlp can fetch the
        same post with proper format selection (``bv*+ba/b``) and merge the
        two streams into a playable file with audio.
        """
        if not shutil.which("yt-dlp"):
            return

        for post in posts:
            post_url = post.get("post_url") or ""
            if not post_url:
                continue
            files = post.get("media_files") or []
            if isinstance(files, str):
                files = [files]
            mp4s = [media_dir / f for f in files if str(f).lower().endswith(".mp4")]
            silent = [m for m in mp4s if m.exists() and not self._has_audio_stream(m)]
            if not silent:
                continue

            logger.info(
                "Detected %d silent MP4(s) in %s — attempting repair via yt-dlp",
                len(silent), post_url,
            )

            # Re-download the post via yt-dlp with proper A/V merging.
            tmpdir = Path(tempfile.mkdtemp(prefix="ig_repair_"))
            try:
                cmd = [
                    "yt-dlp",
                    "--no-warnings",
                    "--quiet",
                    "-f", "bv*+ba/b",
                    "--merge-output-format", "mp4",
                    "-o", str(tmpdir / "%(id)s.%(ext)s"),
                    post_url,
                ]
                # Pass cookies if available — required for Reels/private content
                if self.cookies_path and Path(self.cookies_path).exists():
                    # Convert JSON cookies to Netscape format yt-dlp can read
                    netscape = self._cookies_to_netscape(Path(self.cookies_path), tmpdir)
                    if netscape:
                        cmd.extend(["--cookies", str(netscape)])
                try:
                    subprocess.run(cmd, capture_output=True, timeout=300, check=False)
                except Exception as e:
                    logger.warning("yt-dlp repair failed for %s: %s", post_url, e)
                    continue

                # Replace each silent file with the freshly downloaded one (if any)
                rebuilt = sorted(tmpdir.glob("*.mp4"))
                if not rebuilt:
                    logger.info(
                        "yt-dlp could not re-download %s — leaving silent files as-is",
                        post_url,
                    )
                    continue
                rebuilt_with_audio = [r for r in rebuilt if self._has_audio_stream(r)]
                if not rebuilt_with_audio:
                    logger.info(
                        "Source content of %s appears to have no audio track "
                        "(originally published muted) — keeping original files",
                        post_url,
                    )
                    continue
                # Pair silent files with rebuilt-with-audio files in order
                for i, silent_mp4 in enumerate(silent):
                    src = rebuilt_with_audio[i] if i < len(rebuilt_with_audio) else rebuilt_with_audio[-1]
                    try:
                        shutil.copy2(src, silent_mp4)
                        logger.info(
                            "Repaired silent IG video: %s", silent_mp4.name
                        )
                    except Exception as e:
                        logger.warning("Could not replace %s: %s", silent_mp4, e)
            finally:
                shutil.rmtree(tmpdir, ignore_errors=True)

    @staticmethod
    def _has_audio_stream(path: Path) -> bool:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=15,
            )
            return "audio" in r.stdout
        except Exception:
            return True  # be conservative: assume OK if we cannot check

    @staticmethod
    def _cookies_to_netscape(json_path: Path, out_dir: Path) -> Path | None:
        """Convert Playwright-style JSON cookies to Netscape format for yt-dlp."""
        try:
            cookies = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        out = out_dir / "cookies.txt"
        with open(out, "w", encoding="utf-8") as f:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c.get("domain", "")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path = c.get("path", "/")
                secure = "TRUE" if c.get("secure") else "FALSE"
                exp = int(c.get("expires") or c.get("expirationDate") or 0)
                if exp <= 0:
                    exp = 2147483647
                name = c.get("name", "")
                value = c.get("value", "")
                f.write(f"{domain}\t{flag}\t{path}\t{secure}\t{exp}\t{name}\t{value}\n")
        return out

    def _download_media_file(
        self, url: str, dest_dir: Path, post_id: str, ext: str = "jpg"
    ) -> Path | None:
        """Download a media file from an Instagram CDN URL."""
        if not url or not post_id:
            return None

        dest = dest_dir / f"{post_id}.{ext}"
        if dest.exists():
            return dest

        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                dest.write_bytes(resp.content)
            logger.debug("Media downloaded: %s", dest)
            return dest
        except Exception as e:
            logger.warning("Error downloading media %s: %s", post_id, e)
            return None

    # ------------------------------------------------------------------
    # Screenshots
    # ------------------------------------------------------------------
    def _take_post_screenshot(
        self, page, link: str, dest_dir: Path, post_id: str,
        max_retries: int = 5,
    ) -> Path | None:
        """Take a full-page screenshot of a post using /embed/captioned/
        to capture the image, caption text, and date. Saved as JPG.
        Handles HTTP 429 rate-limiting with exponential backoff."""
        if not link or not post_id:
            return None

        full_url = f"https://www.instagram.com{link}" if link.startswith("/") else link
        embed_url = full_url.rstrip("/") + "/embed/captioned/"
        dest = dest_dir / f"{post_id}.jpg"
        if dest.exists() and dest.stat().st_size > 10_000:
            return dest
        # Remove previous blank screenshot if present
        if dest.exists():
            dest.unlink()

        for attempt in range(1, max_retries + 1):
            try:
                resp = page.goto(embed_url, wait_until="load", timeout=45_000)

                # Handle rate-limiting (429)
                if resp and resp.status == 429:
                    wait = min(30 * attempt, 120)
                    logger.warning(
                        "Rate-limited (429) on screenshot %s — waiting %ds (attempt %d/%d)",
                        post_id, wait, attempt, max_retries,
                    )
                    time.sleep(wait)
                    continue

                # Wait for actual media content to render
                try:
                    page.wait_for_selector(
                        'img, video, .EmbeddedMediaImage',
                        timeout=10_000,
                    )
                except Exception:
                    # Check if the page has any meaningful content
                    body_len = len(page.inner_text("body").strip())
                    if body_len < 20:
                        wait = min(15 * attempt, 90)
                        logger.debug(
                            "Empty embed page for %s (body=%d chars) — waiting %ds",
                            post_id, body_len, wait,
                        )
                        time.sleep(wait)
                        continue

                time.sleep(1.5)
                self._dismiss_dialogs(page)
                page.screenshot(
                    path=str(dest), full_page=True, type="jpeg", quality=80,
                )

                # Verify screenshot is not blank (< 10 KB = likely empty white page)
                if dest.stat().st_size < 10_000:
                    logger.debug(
                        "Screenshot %s too small (%d bytes) — likely blank, retrying",
                        post_id, dest.stat().st_size,
                    )
                    dest.unlink()
                    wait = min(15 * attempt, 90)
                    time.sleep(wait)
                    continue

                logger.debug("Screenshot saved: %s (%d bytes)", dest, dest.stat().st_size)
                return dest
            except Exception as e:
                if attempt < max_retries:
                    wait = 5 * attempt
                    logger.debug(
                        "Retry %d/%d for screenshot %s (wait %ds)",
                        attempt, max_retries, post_id, wait,
                    )
                    time.sleep(wait)
                else:
                    logger.warning(
                        "Error taking screenshot of %s after %d attempts: %s",
                        post_id, max_retries, e,
                    )
        return None

    # ------------------------------------------------------------------
    # Dialog dismissal
    # ------------------------------------------------------------------
    @staticmethod
    def _dismiss_dialogs(page):
        """Dismiss cookie consent and login popups."""
        selectors = [
            'button:has-text("Allow all cookies")',
            'button:has-text("Accept all")',
            'button:has-text("Allow essential")',
            'button:has-text("Decline optional cookies")',
            '[role="dialog"] button:has-text("Not Now")',
            '[role="dialog"] button:has-text("Not now")',
            '[role="dialog"] button[aria-label="Close"]',
            '[role="dialog"] button[aria-label="Cerrar"]',
            '[role="presentation"] button svg[aria-label="Close"]',
        ]
        for sel in selectors:
            try:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    time.sleep(0.5)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Batch: all accounts
    # ------------------------------------------------------------------
    def scrape_all_accounts(
        self,
        accounts_config: dict,
        start_date: str,
        end_date: str,
        max_posts: int = 200,
        category: str | None = None,
    ) -> dict:
        """Scrape all configured Instagram accounts."""
        all_results = {}
        accounts = accounts_config.get("accounts", [])
        pause = self.settings.get("pause_between_profiles", 5)

        for account in accounts:
            acct_category = account.get("category", "")
            if category and acct_category != category:
                continue

            ig_handle = account.get("instagram", "")
            if not ig_handle:
                logger.warning("No Instagram handle for %s", account.get("account_name", "?"))
                continue

            logger.info("=" * 60)
            logger.info("Processing: %s (@%s) [%s]", account.get("account_name", ""), ig_handle, acct_category or "no-category")
            logger.info("=" * 60)

            try:
                posts = self.scrape_profile(
                    username=ig_handle,
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
                    "Error scraping Instagram @%s (%s): %s",
                    ig_handle, account.get("account_name", ""), e,
                )

            # Pause between profiles
            time.sleep(pause)

        return all_results

    def take_screenshots_from_metadata(self) -> int:
        """
        Generate screenshots for already-scraped posts by reading existing
        _metadata.json files. Useful for regenerating screenshots without re-scraping.
        """
        total = 0
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="en-US",
            )
            # Load cookies if available
            try:
                cookies_path = Path(self.cookies_path)
                if cookies_path.exists():
                    with open(cookies_path, "r", encoding="utf-8") as f:
                        raw_cookies = json.load(f)
                    clean = []
                    for c in raw_cookies:
                        entry = {k: v for k, v in c.items() if k != "sameSite"}
                        ss = c.get("sameSite", "None")
                        entry["sameSite"] = {"Strict": "Strict", "Lax": "Lax"}.get(ss, "None")
                        clean.append(entry)
                    context.add_cookies(clean)
            except Exception as e:
                logger.warning("Error loading cookies for screenshots: %s", e)

            page = context.new_page()
            self._dismiss_dialogs(page)

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

                for idx, post in enumerate(posts):
                    link = post.get("link") or post.get("post_url", "")
                    post_id = post.get("post_id", "")
                    if link and post_id:
                        self._take_post_screenshot(page, link, screenshots_dir, post_id)
                        total += 1
                        delay = 3 + (2 * (idx // 5))
                        time.sleep(delay)

            browser.close()
        logger.info("Screenshots processed for %d Instagram posts", total)
        return total
