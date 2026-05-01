@echo off
setlocal
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    python -m venv venv
)

echo Installing/updating Python dependencies...
"venv\Scripts\python.exe" -m pip install -r requirements.txt

echo Installing Playwright Chromium if needed...
"venv\Scripts\python.exe" -m playwright install chromium

echo Starting Instagram ^& TikTok Scraper GUI...
set SCRAPER_WEB_OPEN_BROWSER=1
"venv\Scripts\python.exe" run_web.py

pause
