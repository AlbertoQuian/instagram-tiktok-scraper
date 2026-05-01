#!/usr/bin/env zsh
set -euo pipefail

cd "${0:A:h}"

if [[ ! -x "venv/bin/python" ]]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Installing/updating Python dependencies..."
"venv/bin/python" -m pip install -r requirements.txt

echo "Installing Playwright Chromium if needed..."
"venv/bin/python" -m playwright install chromium

echo "Starting Instagram & TikTok Scraper GUI..."
export SCRAPER_WEB_OPEN_BROWSER=1
"venv/bin/python" run_web.py
