"""Flask GUI for the Instagram & TikTok scraper."""
from __future__ import annotations

import json
import os
import shutil
import shlex
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from flask import (
    Flask,
    Response,
    g,
    jsonify,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (  # noqa: E402
    ACCOUNTS_FILE,
    BASE_DIR,
    DATA_DIR,
    EXPORT_SETTINGS,
    INSTAGRAM_SETTINGS,
    RAW_DIR,
    TIKTOK_SETTINGS,
)
from utils.export import collect_metadata_files, export_to_csv, parse_metadata_file  # noqa: E402
from web.i18n import DEFAULT_LANGUAGE, LANGUAGES, translate  # noqa: E402

DEFAULT_CONFIG: Dict[str, Any] = {
    "project": "",
    "study_period": {"start": "", "end": ""},
    "accounts": [],
}

PLACEHOLDER_PROJECT_NAMES = {"my research project", "research project", "audit smoke test"}

JS_TRANSLATION_KEYS = [
    "running",
    "completed",
    "failed",
    "connection_error",
    "saved",
    "select_platform",
    "select_account",
    "invalid_json",
    "empty_cookies",
    "exporting",
    "saving",
    "starting",
    "account_name_placeholder",
    "account_id_placeholder",
    "category_placeholder",
    "instagram_placeholder",
    "tiktok_placeholder",
    "remove",
    "ready",
    "confirm_reset_config",
    "confirm_clear_data",
    "custom_limit_placeholder",
]

app = Flask(
    __name__,
    template_folder=str(Path(__file__).parent / "templates"),
    static_folder=str(Path(__file__).parent / "static"),
)
app.secret_key = os.environ.get("SCRAPER_WEB_SECRET", os.urandom(32))

_tasks: Dict[str, Dict[str, Any]] = {}
_tasks_lock = threading.Lock()


def _clone_default_config() -> Dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_CONFIG))


def _load_config() -> Dict[str, Any]:
    if not ACCOUNTS_FILE.exists():
        return _clone_default_config()
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _clone_default_config()
    if not isinstance(config, dict):
        return _clone_default_config()
    config.setdefault("project", DEFAULT_CONFIG["project"])
    config.setdefault("study_period", dict(DEFAULT_CONFIG["study_period"]))
    config.setdefault("accounts", [])
    return config


def _save_config(config: Dict[str, Any]) -> None:
    ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=4, ensure_ascii=False)
        handle.write("\n")


def _project_name(config: Dict[str, Any]) -> str:
    project = config.get("project")
    if isinstance(project, dict):
        value = str(project.get("name") or project.get("title") or "").strip()
    else:
        value = str(project or "").strip()
    if not value or value.lower() in PLACEHOLDER_PROJECT_NAMES:
        return translate(g.lang, "project.default")
    return value


def _study_period(config: Dict[str, Any]) -> Dict[str, str]:
    period = config.get("study_period") or {}
    if not isinstance(period, dict):
        period = {}
    return {
        "start": str(period.get("start") or period.get("start_date") or ""),
        "end": str(period.get("end") or period.get("end_date") or ""),
    }


def _normalize_platform(value: str) -> str:
    value_lower = (value or "").strip().lower()
    if value_lower == "instagram":
        return "Instagram"
    if value_lower == "tiktok":
        return "TikTok"
    return value or "Unknown"


def _normalize_handle(value: Any) -> str:
    handle = str(value or "").strip()
    if handle.startswith("http://") or handle.startswith("https://"):
        parsed = urlparse(handle)
        parts = [part for part in parsed.path.split("/") if part]
        if parts:
            handle = parts[0]
        else:
            handle = ""
    return handle.lstrip("@").strip()


def _clean_account(raw: Dict[str, Any], index: int) -> Dict[str, str]:
    account_name = str(raw.get("account_name") or raw.get("name") or "").strip()
    instagram = _normalize_handle(raw.get("instagram"))
    tiktok = _normalize_handle(raw.get("tiktok"))
    if not account_name:
        account_name = instagram or tiktok or f"Account {index + 1}"
    account_id = str(raw.get("account_id") or raw.get("id") or "").strip()
    if not account_id:
        account_id = f"A{index + 1:03d}"
    return {
        "account_name": account_name,
        "account_id": account_id,
        "category": str(raw.get("category") or raw.get("label") or "").strip(),
        "instagram": instagram,
        "tiktok": tiktok,
    }


def _accounts(config: Dict[str, Any]) -> List[Dict[str, str]]:
    raw_accounts = config.get("accounts", [])
    if not isinstance(raw_accounts, list):
        return []
    accounts = []
    for index, account in enumerate(raw_accounts):
        if not isinstance(account, dict):
            continue
        cleaned = _clean_account(account, index)
        if cleaned["instagram"] or cleaned["tiktok"]:
            accounts.append(cleaned)
    return accounts


def _categories(accounts: List[Dict[str, str]]) -> List[str]:
    return sorted({account.get("category", "") for account in accounts if account.get("category")})


def _media_count(post: Dict[str, Any]) -> int:
    media_files = post.get("media_files") or []
    if isinstance(media_files, list):
        return len([item for item in media_files if item])
    if isinstance(media_files, str):
        return len([item for item in media_files.split(";") if item.strip()])
    return 0


def _post_account(post: Dict[str, Any]) -> str:
    return str(post.get("account_name") or post.get("username") or post.get("account") or "")


def _post_category(post: Dict[str, Any], fallback: str = "") -> str:
    return str(post.get("category") or fallback or "")


def _load_all_posts() -> List[Dict[str, Any]]:
    posts: List[Dict[str, Any]] = []
    for meta_path in collect_metadata_files(RAW_DIR):
        platform, category, parsed_posts = parse_metadata_file(meta_path, RAW_DIR)
        for post in parsed_posts:
            if not isinstance(post, dict):
                continue
            item = dict(post)
            item.setdefault("platform", _normalize_platform(platform))
            item.setdefault("category", category)
            item["_metadata_path"] = str(meta_path)
            item["_metadata_relpath"] = _safe_relative_path(meta_path, RAW_DIR)
            item["_category"] = _post_category(item, category)
            item["_account"] = _post_account(item)
            item["_media_count"] = _media_count(item)
            posts.append(item)
    posts.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
    return posts


def _stats(posts: List[Dict[str, Any]], accounts: List[Dict[str, str]]) -> Dict[str, Any]:
    by_platform: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    media_files = 0
    with_likes = 0
    with_views = 0
    for post in posts:
        platform = _normalize_platform(str(post.get("platform") or ""))
        by_platform[platform] = by_platform.get(platform, 0) + 1
        category = str(post.get("_category") or "")
        if category:
            by_category[category] = by_category.get(category, 0) + 1
        media_files += int(post.get("_media_count") or 0)
        if post.get("likes") not in (None, "", 0):
            with_likes += 1
        if post.get("views") not in (None, "", 0):
            with_views += 1
    return {
        "total": len(posts),
        "instagram": by_platform.get("Instagram", 0),
        "tiktok": by_platform.get("TikTok", 0),
        "accounts": len(accounts),
        "categories": len(_categories(accounts)),
        "with_likes": with_likes,
        "with_views": with_views,
        "media": media_files,
        "by_platform": dict(sorted(by_platform.items())),
        "by_category": dict(sorted(by_category.items())),
    }


def _cookie_status_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "message_key": "cookies.missing", "count": 0}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            cookies = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "error", "message": str(exc), "count": 0}
    if not isinstance(cookies, list):
        return {"status": "error", "message": "JSON root must be a list", "count": 0}
    session_cookie = next((item for item in cookies if isinstance(item, dict) and item.get("name") == "sessionid"), None)
    if session_cookie:
        expires = session_cookie.get("expires") or session_cookie.get("expirationDate")
        if expires:
            expiry = datetime.fromtimestamp(float(expires))
            if expiry < datetime.now():
                return {
                    "status": "expired",
                    "message_key": "cookies.expired",
                    "message_kwargs": {"date": expiry.strftime("%Y-%m-%d %H:%M")},
                    "count": len(cookies),
                }
        return {"status": "valid", "message_key": "cookies.valid", "count": len(cookies)}
    return {"status": "unknown", "message_key": "cookies.no_session", "count": len(cookies)}


def _cookie_status_text(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "message_key": "cookies.optional_missing", "count": 0}
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    except OSError as exc:
        return {"status": "error", "message": str(exc), "count": 0}
    return {"status": "valid", "message_key": "cookies.valid", "count": len(lines)}


def _translated_status(status: Dict[str, Any]) -> Dict[str, Any]:
    item = dict(status)
    key = item.get("message_key")
    if key:
        item["message"] = translate(g.lang, key, **item.get("message_kwargs", {}))
    return item


def _normalize_playwright_cookies(cookies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    allowed = {"name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite"}
    same_site_map = {"no_restriction": "None", "lax": "Lax", "strict": "Strict", "none": "None"}
    normalized = []
    for cookie in cookies:
        if not isinstance(cookie, dict) or not cookie.get("name") or "value" not in cookie:
            continue
        item = {key: cookie[key] for key in allowed if key in cookie}
        if "expires" not in item and cookie.get("expirationDate"):
            item["expires"] = cookie["expirationDate"]
        item.setdefault("domain", cookie.get("domain", ""))
        item.setdefault("path", cookie.get("path", "/"))
        raw_same_site = str(item.get("sameSite") or "None").lower()
        item["sameSite"] = same_site_map.get(raw_same_site, "None")
        normalized.append(item)
    return normalized


def _write_netscape_cookies(cookies: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Netscape HTTP Cookie File\n")
        for cookie in cookies:
            domain = str(cookie.get("domain") or "")
            if not domain:
                continue
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            cookie_path = str(cookie.get("path") or "/")
            secure = "TRUE" if cookie.get("secure") else "FALSE"
            expires = int(cookie.get("expires") or cookie.get("expirationDate") or 2147483647)
            name = str(cookie.get("name") or "")
            value = str(cookie.get("value") or "")
            handle.write(
                f"{domain}\t{include_subdomains}\t{cookie_path}\t{secure}\t{expires}\t{name}\t{value}\n"
            )


def _capture_browser_cookies(task_id: str, platform: str, language: str) -> None:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        _update_task(task_id, status="failed", error=str(exc))
        _append_log(task_id, str(exc))
        return

    login_url = "https://www.instagram.com/" if platform == "instagram" else "https://www.tiktok.com/"
    cookie_name = "sessionid" if platform == "instagram" else "tt_chain_token"
    _append_log(task_id, translate(language, "cookies.browser_opening", platform=platform.title()))
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(login_url, wait_until="domcontentloaded", timeout=60_000)
            deadline = time.time() + 300
            saved = False
            while time.time() < deadline:
                cookies = context.cookies()
                has_cookie = any(cookie.get("name") == cookie_name for cookie in cookies)
                if has_cookie or (platform == "tiktok" and len(cookies) > 3):
                    if platform == "instagram":
                        path = Path(INSTAGRAM_SETTINGS["cookies_path"])
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with open(path, "w", encoding="utf-8") as handle:
                            json.dump(_normalize_playwright_cookies(cookies), handle, indent=2, ensure_ascii=False)
                            handle.write("\n")
                    else:
                        _write_netscape_cookies(cookies, Path(TIKTOK_SETTINGS["cookies_path"]))
                    saved = True
                    break
                page.wait_for_timeout(2000)
            browser.close()
            if saved:
                _append_log(task_id, translate(language, "cookies.browser_saved"))
                _update_task(task_id, status="completed")
            else:
                message = translate(language, "cookies.browser_timeout")
                _append_log(task_id, message)
                _update_task(task_id, status="failed", error=message)
    except PlaywrightTimeoutError as exc:
        _update_task(task_id, status="failed", error=str(exc))
        _append_log(task_id, str(exc))
    except Exception as exc:
        _update_task(task_id, status="failed", error=str(exc))
        _append_log(task_id, str(exc))


def _new_task(name: str) -> str:
    task_id = f"{name}-{uuid4().hex[:8]}"
    with _tasks_lock:
        _tasks[task_id] = {
            "name": name,
            "status": "running",
            "started": datetime.now().isoformat(timespec="seconds"),
            "log": [],
            "error": None,
        }
    return task_id


def _append_log(task_id: str, message: str) -> None:
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            return
        task.setdefault("log", []).append(message)
        task["log"] = task["log"][-2000:]


def _update_task(task_id: str, **kwargs: Any) -> None:
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)


def _run_command_task(task_id: str, command: List[str], env: Optional[Dict[str, str]] = None) -> None:
    display = " ".join(shlex.quote(part) for part in command)
    _append_log(task_id, display)
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(BASE_DIR),
            env=env or os.environ.copy(),
            bufsize=1,
        )
        if process.stdout:
            for line in process.stdout:
                _append_log(task_id, line.rstrip())
        process.wait()
    except Exception as exc:
        _update_task(task_id, status="failed", error=str(exc))
        _append_log(task_id, str(exc))
        return
    if process.returncode == 0:
        _update_task(task_id, status="completed")
    else:
        message = f"Exit code: {process.returncode}"
        _update_task(task_id, status="failed", error=message)
        _append_log(task_id, message)


def _safe_relative_path(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return path.name


def _iter_media_references(post: Dict[str, Any]) -> List[str]:
    values: List[str] = []
    media_files = post.get("media_files") or []
    if isinstance(media_files, list):
        values.extend(str(item) for item in media_files if item)
    elif isinstance(media_files, str):
        values.extend(item.strip() for item in media_files.split(";") if item.strip())
    for key in ("thumbnail", "screenshot"):
        if post.get(key):
            values.append(str(post[key]))
    return values


def _resolve_media_items(post: Dict[str, Any]) -> List[Dict[str, str]]:
    metadata_path = Path(str(post.get("_metadata_path") or ""))
    meta_dir = metadata_path.parent if metadata_path else RAW_DIR
    platform = str(post.get("platform") or "").lower()
    items: List[Dict[str, str]] = []
    seen = set()
    for reference in _iter_media_references(post):
        ref_path = Path(reference)
        if ref_path.is_absolute():
            continue
        candidates = [
            RAW_DIR / ref_path,
            RAW_DIR / platform / ref_path,
            meta_dir / ref_path,
            meta_dir / "media" / ref_path.name,
            meta_dir / "screenshots" / ref_path.name,
        ]
        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                continue
            rel = _safe_relative_path(candidate, RAW_DIR)
            if rel in seen:
                break
            seen.add(rel)
            suffix = candidate.suffix.lower()
            media_type = "video" if suffix in {".mp4", ".mov", ".webm", ".m4v"} else "image"
            items.append({"path": rel, "name": candidate.name, "type": media_type})
            break
    return items


def _language_url(language: str) -> str:
    endpoint = request.endpoint or "index"
    values = dict(request.view_args or {})
    args = request.args.to_dict(flat=True)
    args["lang"] = language
    values.update(args)
    return url_for(endpoint, **values)


@app.before_request
def _set_language() -> None:
    requested = request.args.get("lang")
    if requested in LANGUAGES:
        session["lang"] = requested
    if "lang" not in session:
        match = request.accept_languages.best_match(list(LANGUAGES.keys()))
        session["lang"] = match or DEFAULT_LANGUAGE
    g.lang = session.get("lang", DEFAULT_LANGUAGE)


@app.context_processor
def _inject_globals() -> Dict[str, Any]:
    config = _load_config()
    period = _study_period(config)
    return {
        "_": lambda key, **kwargs: translate(g.lang, key, **kwargs),
        "current_lang": g.lang,
        "languages": LANGUAGES,
        "language_url": _language_url,
        "project_name": _project_name(config),
        "study_start": period["start"],
        "study_end": period["end"],
        "js_text": {key: translate(g.lang, f"js.{key}") for key in JS_TRANSLATION_KEYS},
    }


@app.route("/")
def index() -> str:
    config = _load_config()
    accounts = _accounts(config)
    posts = _load_all_posts()
    period = _study_period(config)
    return render_template(
        "index.html",
        stats=_stats(posts, accounts),
        accounts=accounts,
        categories=_categories(accounts),
        study_period=period,
        instagram_cookie=_translated_status(_cookie_status_json(Path(INSTAGRAM_SETTINGS["cookies_path"]))),
        tiktok_cookie=_translated_status(_cookie_status_text(Path(TIKTOK_SETTINGS["cookies_path"]))),
        csv_path=EXPORT_SETTINGS["output_dir"] / EXPORT_SETTINGS["filename"],
    )


@app.route("/guide")
def guide_view() -> str:
    return render_template("guide.html")


@app.route("/data")
def data_view() -> str:
    posts = _load_all_posts()
    platform = request.args.get("platform", "all")
    category = request.args.get("category", "all")
    account = request.args.get("account", "all")

    filtered = posts
    if platform != "all":
        filtered = [post for post in filtered if str(post.get("platform", "")).lower() == platform.lower()]
    if category != "all":
        filtered = [post for post in filtered if str(post.get("_category", "")) == category]
    if account != "all":
        filtered = [post for post in filtered if str(post.get("_account", "")) == account]

    accounts = sorted({str(post.get("_account")) for post in posts if post.get("_account")})
    categories = sorted({str(post.get("_category")) for post in posts if post.get("_category")})
    platforms = sorted({_normalize_platform(str(post.get("platform") or "")) for post in posts if post.get("platform")})
    limit = int(request.args.get("limit", "500") or "500")
    visible = filtered[:limit]
    return render_template(
        "data.html",
        posts=visible,
        total_posts=len(filtered),
        platforms=platforms,
        categories=categories,
        accounts=accounts,
        current_platform=platform,
        current_category=category,
        current_account=account,
    )


@app.route("/post/<post_id>")
def post_detail(post_id: str) -> str:
    post = next((item for item in _load_all_posts() if str(item.get("post_id")) == post_id), None)
    if post is None:
        return render_template("404.html"), 404
    return render_template("post_detail.html", post=post, media_items=_resolve_media_items(post))


@app.route("/media/<path:filepath>")
def serve_media(filepath: str) -> Response:
    candidate = (RAW_DIR / filepath).resolve()
    try:
        candidate.relative_to(RAW_DIR.resolve())
    except ValueError:
        return Response("Forbidden", status=403)
    if not candidate.exists() or not candidate.is_file():
        return Response("Not found", status=404)
    return send_file(candidate)


@app.route("/accounts")
def accounts_view() -> str:
    config = _load_config()
    return render_template("accounts.html", accounts=_accounts(config), categories=_categories(_accounts(config)))


@app.route("/settings")
def settings_view() -> str:
    config = _load_config()
    project = config.get("project")
    if isinstance(project, dict):
        project_value = str(project.get("name") or project.get("title") or "")
    else:
        project_value = str(project or "")
    if project_value.lower() in PLACEHOLDER_PROJECT_NAMES:
        project_value = ""
    return render_template("settings.html", project_name_value=project_value, study_period=_study_period(config))


@app.route("/cookies")
def cookies_view() -> str:
    instagram_path = Path(INSTAGRAM_SETTINGS["cookies_path"])
    tiktok_path = Path(TIKTOK_SETTINGS["cookies_path"])
    return render_template(
        "cookies.html",
        instagram_cookie=_translated_status(_cookie_status_json(instagram_path)),
        tiktok_cookie=_translated_status(_cookie_status_text(tiktok_path)),
    )


@app.route("/api/settings/project", methods=["POST"])
def update_project_settings() -> Response:
    data = request.get_json(silent=True) or {}
    config = _load_config()
    project = str(data.get("project") or "").strip()
    start = str(data.get("start") or "").strip()
    end = str(data.get("end") or "").strip()
    config["project"] = project
    config["study_period"] = {"start": start, "end": end}
    _save_config(config)
    return jsonify({"success": True, "message": translate(g.lang, "js.saved")})


@app.route("/api/reset/config", methods=["POST"])
def reset_config() -> Response:
    _save_config(_clone_default_config())
    return jsonify({"success": True, "message": translate(g.lang, "js.saved")})


@app.route("/api/reset/data", methods=["POST"])
def reset_data() -> Response:
    if RAW_DIR.exists():
        shutil.rmtree(RAW_DIR)
    exports_dir = Path(EXPORT_SETTINGS["output_dir"])
    if exports_dir.exists():
        shutil.rmtree(exports_dir)
    return jsonify({"success": True, "message": translate(g.lang, "js.saved")})


@app.route("/api/settings/accounts", methods=["POST"])
def update_accounts_settings() -> Response:
    data = request.get_json(silent=True) or {}
    raw_accounts = data.get("accounts", [])
    if not isinstance(raw_accounts, list):
        return jsonify({"error": "accounts must be a list"}), 400
    accounts = []
    for index, raw in enumerate(raw_accounts):
        if not isinstance(raw, dict):
            continue
        cleaned = _clean_account(raw, index)
        if cleaned["instagram"] or cleaned["tiktok"]:
            accounts.append(cleaned)
    config = _load_config()
    config["accounts"] = accounts
    _save_config(config)
    return jsonify({"success": True, "message": translate(g.lang, "js.saved")})


@app.route("/api/cookies/instagram", methods=["POST"])
def update_instagram_cookies() -> Response:
    data = request.get_json(silent=True) or {}
    raw = data.get("cookies", "")
    if not str(raw).strip():
        return jsonify({"error": translate(g.lang, "js.empty_cookies")}), 400
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return jsonify({"error": translate(g.lang, "js.invalid_json")}), 400
    if not isinstance(parsed, list):
        return jsonify({"error": translate(g.lang, "js.invalid_json")}), 400
    parsed = _normalize_playwright_cookies(parsed)
    if not parsed:
        return jsonify({"error": translate(g.lang, "js.invalid_json")}), 400
    path = Path(INSTAGRAM_SETTINGS["cookies_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(parsed, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return jsonify({"success": True, "message": translate(g.lang, "js.saved")})


@app.route("/api/cookies/tiktok", methods=["POST"])
def update_tiktok_cookies() -> Response:
    data = request.get_json(silent=True) or {}
    raw = str(data.get("cookies", "")).strip()
    if not raw:
        return jsonify({"error": translate(g.lang, "js.empty_cookies")}), 400
    path = Path(TIKTOK_SETTINGS["cookies_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw + "\n", encoding="utf-8")
    return jsonify({"success": True, "message": translate(g.lang, "js.saved")})


@app.route("/api/cookies/connect/<platform>", methods=["POST"])
def connect_cookies(platform: str) -> Response:
    if platform not in {"instagram", "tiktok"}:
        return jsonify({"error": "Invalid platform"}), 400
    task_id = _new_task(f"connect-{platform}")
    thread = threading.Thread(target=_capture_browser_cookies, args=(task_id, platform, g.lang), daemon=True)
    thread.start()
    return jsonify({"task_id": task_id})


@app.route("/api/cookies/delete/<platform>", methods=["POST"])
def delete_cookies(platform: str) -> Response:
    paths = {
        "instagram": Path(INSTAGRAM_SETTINGS["cookies_path"]),
        "tiktok": Path(TIKTOK_SETTINGS["cookies_path"]),
    }
    path = paths.get(platform)
    if path is None:
        return jsonify({"error": "Invalid platform"}), 400
    if path.exists():
        path.unlink()
    return jsonify({"success": True, "message": translate(g.lang, "js.saved")})


@app.route("/api/run/scrape", methods=["POST"])
def run_scrape() -> Response:
    data = request.get_json(silent=True) or {}
    platform = str(data.get("platform") or "all").lower()
    if platform not in {"all", "instagram", "tiktok"}:
        return jsonify({"error": translate(g.lang, "js.select_platform")}), 400
    if not _accounts(_load_config()):
        return jsonify({"error": translate(g.lang, "js.select_account")}), 400
    command = [sys.executable, str(BASE_DIR / "main.py"), "--platform", platform]
    category = str(data.get("category") or "all")
    if category and category != "all":
        command.extend(["--category", category])
    start_date = str(data.get("start_date") or "").strip()
    end_date = str(data.get("end_date") or "").strip()
    max_posts = str(data.get("max_posts") or "").strip()
    command.extend(["--start-date", start_date or "1970-01-01"])
    command.extend(["--end-date", end_date or datetime.now().strftime("%Y-%m-%d")])
    if max_posts:
        command.extend(["--max-posts", max_posts])
    if not data.get("download_media", True):
        command.append("--no-media")
    if not data.get("take_screenshots", True):
        command.append("--no-screenshots")
    if not data.get("export_after", True):
        command.append("--no-export")

    selected_accounts = [str(item).strip() for item in data.get("accounts", []) if str(item).strip()]
    env = os.environ.copy()
    if selected_accounts:
        env["SCRAPE_ACCOUNTS"] = ",".join(selected_accounts)

    task_id = _new_task("scrape")
    thread = threading.Thread(target=_run_command_task, args=(task_id, command, env), daemon=True)
    thread.start()
    return jsonify({"task_id": task_id})


@app.route("/api/run/screenshots", methods=["POST"])
def run_screenshots() -> Response:
    data = request.get_json(silent=True) or {}
    platform = str(data.get("platform") or "all").lower()
    if platform not in {"all", "instagram", "tiktok"}:
        return jsonify({"error": translate(g.lang, "js.select_platform")}), 400
    command = [sys.executable, str(BASE_DIR / "main.py"), "--platform", platform, "--screenshots-only"]
    task_id = _new_task("screenshots")
    thread = threading.Thread(target=_run_command_task, args=(task_id, command, os.environ.copy()), daemon=True)
    thread.start()
    return jsonify({"task_id": task_id})


@app.route("/api/run/export", methods=["POST"])
def run_export() -> Response:
    try:
        output_path = export_to_csv(
            raw_dir=RAW_DIR,
            output_dir=EXPORT_SETTINGS["output_dir"],
            filename=EXPORT_SETTINGS["filename"],
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    return jsonify({"success": True, "path": str(output_path)})


@app.route("/api/task/<task_id>")
def task_status(task_id: str) -> Response:
    with _tasks_lock:
        task = dict(_tasks.get(task_id) or {})
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)


@app.route("/api/stats")
def api_stats() -> Response:
    config = _load_config()
    return jsonify(_stats(_load_all_posts(), _accounts(config)))


@app.route("/download/csv")
def download_csv() -> Response:
    csv_path = EXPORT_SETTINGS["output_dir"] / EXPORT_SETTINGS["filename"]
    if not csv_path.exists():
        csv_path = export_to_csv(
            raw_dir=RAW_DIR,
            output_dir=EXPORT_SETTINGS["output_dir"],
            filename=EXPORT_SETTINGS["filename"],
        )
    return send_file(csv_path, as_attachment=True, download_name=EXPORT_SETTINGS["filename"])


@app.errorhandler(404)
def not_found(_: Exception) -> tuple[str, int]:
    return render_template("404.html"), 404


def create_app() -> Flask:
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=True)
