#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -x "venv/bin/python" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Installing/updating Python dependencies..."
"venv/bin/python" -m pip install --upgrade pip >/dev/null
"venv/bin/python" -m pip install -r requirements.txt

echo "Installing Playwright Chromium if needed..."
"venv/bin/python" -m playwright install chromium

echo "Starting Instagram & TikTok Scraper GUI..."
export SCRAPER_WEB_OPEN_BROWSER=1
"venv/bin/python" run_web.py
