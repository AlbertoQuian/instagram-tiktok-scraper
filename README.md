# Instagram & TikTok Scraper

![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)
![License: GPL v3](https://img.shields.io/badge/license-GPL%20v3-blue)
![Platforms: macOS · Linux · Windows](https://img.shields.io/badge/platforms-macOS%20%C2%B7%20Linux%20%C2%B7%20Windows-lightgrey)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19054043.svg)](https://doi.org/10.5281/zenodo.19054043)

A Python-based tool for scraping public Instagram and TikTok profiles,
designed for **academic research** and data analysis. Collects posts,
engagement metrics, media files, and screenshots within a configurable
date range.

---

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Account List](#account-list)
  - [Instagram Session Cookies](#instagram-session-cookies)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Output Data](#output-data)
- [Technical Stack](#technical-stack)
- [Ethical Use & Legal Notice](#ethical-use--legal-notice)
- [Testing](#testing)
- [Citation](#citation)
- [License](#license)
- [Author](#author)

## Features

- **Instagram scraping** via Playwright (headless Chromium + API interception)
  - Likes, comments, views, and exact timestamps
  - Photo, video, and carousel media download
  - Full-page embed screenshots (JPG)
- **TikTok scraping** via yt-dlp with browser impersonation (curl_cffi)
  - Video download with full metadata (engagement, music, duration)
  - Carousel reconstruction (images → MP4 slideshow via ffmpeg)
  - Embed screenshots (JPG)
- **Unified CSV export** consolidating data from both platforms
- **Browser-based GUI** for non-technical workflows, available in Spanish and English
- **Automatic language detection** via lingua-py (ISO 639-1 codes)
- **Configurable** account list with optional label grouping
- **Rate limiting** and retry logic with exponential back-off

## Requirements

| Dependency | Notes |
|---|---|
| **Python** | 3.9 or newer |
| **ffmpeg** | Required for TikTok carousel reconstruction and media processing |
| **Chromium** | Auto-installed by Playwright (see [Installation](#installation)) |

### Installing ffmpeg

<details>
<summary><strong>macOS</strong> (Homebrew)</summary>

```bash
brew install ffmpeg
```

</details>

<details>
<summary><strong>Ubuntu / Debian</strong></summary>

```bash
sudo apt update && sudo apt install ffmpeg
```

</details>

<details>
<summary><strong>Windows</strong></summary>

Download a release build from <https://www.gyan.dev/ffmpeg/builds/> and add the
`bin/` directory to your system `PATH`. Alternatively, install via
[Chocolatey](https://chocolatey.org/):

```powershell
choco install ffmpeg
```

</details>

Verify the installation:

```bash
ffmpeg -version
```

## Installation

```bash
git clone https://github.com/AlbertoQuian/instagram-tiktok-scraper.git
cd instagram-tiktok-scraper

python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
playwright install chromium
```

## Configuration

### Account List

The easiest path is the web interface: open **Accounts**, then paste an
Instagram or TikTok account URL/handle. A label is optional and can be any
grouping that makes sense for your work.

If you prefer editing JSON directly, copy the example configuration:

```bash
cp config/accounts_example.json config/accounts.json
```

Then edit `config/accounts.json` with your target accounts:

```json
{
    "project": "",
    "study_period": {
        "start": "",
        "end": ""
    },
    "storage": {
      "data_dir": ""
    },
    "accounts": [
        {
            "account_name": "Optional display name",
            "category": "optional_label",
            "instagram": "instagram_username_or_url",
            "tiktok": "tiktok_username_or_url"
        }
    ]
}
```

Each **account** represents a logical entity (brand, organization, public
figure, etc.) that may have profiles on one or both platforms. The `category`
field is an optional free label; it can represent a country, topic, campaign,
client, course, experiment, or any grouping you need. When present, data is
stored in a subdirectory named after the label.

The optional `storage.data_dir` field controls where scraped metadata, media,
screenshots, and CSV files are saved. Leave it blank to use the repository's
git-ignored `data/` directory. In the GUI, this is configured from **Settings**.

### Instagram Session Cookies

Instagram aggressively blocks unauthenticated requests. **Without a saved
browser session, the scraper may retrieve zero posts for many profiles.** The
GUI includes a **Connections** page that opens a browser window, lets you log
in normally, and stores the local session for the scraper. TikTok usually works
without a session, but the same page can save a TikTok session if needed.

Cookies are personal session credentials. They can stop working at any time
because platforms expire or revoke sessions. The cookie files are git-ignored;
never commit or share them.

#### Manual cookie import

The GUI's browser login is recommended. Manual import is available under the
advanced section of **Connections** if you already know how to export cookies.

1. Install a browser extension that can export cookies in **JSON format**:
   - Firefox: [Cookie Editor](https://addons.mozilla.org/firefox/addon/cookie-editor/)
   - Chrome: [Cookie Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
2. Log in to [instagram.com](https://www.instagram.com) in your browser.
3. Open **Cookie Editor**, filter by `instagram.com`, and export **all
   cookies** as JSON.
4. Paste the exported JSON into the advanced Instagram field, or save it to `config/instagram_cookies.json`.

The file must be a JSON array of cookie objects. Example structure:

```json
[
    {
        "name": "sessionid",
        "value": "YOUR_SESSION_ID",
        "domain": ".instagram.com",
        "path": "/",
        "secure": true,
        "httpOnly": true,
        "sameSite": "None"
    },
    {
        "name": "csrftoken",
        "value": "YOUR_CSRF_TOKEN",
        "domain": ".instagram.com",
        "path": "/",
        "secure": true,
        "httpOnly": false,
        "sameSite": "Lax"
    }
]
```

> **Important:** Cookie files are automatically excluded from version control
> via `.gitignore`. **Never commit your session cookies to a public
> repository.** Cookies expire periodically; reconnect if the scraper stops
> retrieving data.

## Usage

### Web Interface

Start the local GUI:

```bash
python run_web.py
```

Then open <http://127.0.0.1:5000>. The interface starts blank: add profiles by
pasting URLs or handles, switch between Spanish and English, connect sessions
when needed, choose where local results are saved, launch scraping jobs,
monitor logs, browse collected data, reset the local setup, and export the
consolidated CSV.

For a double-click launcher, use `launch_gui.command` on macOS/Linux or
`launch_gui.bat` on Windows. These launchers create the virtual environment
if needed, install dependencies, install Playwright Chromium, start the GUI,
and open the browser automatically.

You can also launch it with:

```bash
python -m web
```

### Command Line

```bash
# Scrape all configured accounts on both platforms
python main.py

# Scrape only Instagram
python main.py --platform instagram

# Scrape only TikTok for a specific label
python main.py --platform tiktok --category optional_label

# Override the study period
python main.py --start-date 2024-03-01 --end-date 2024-06-30

# Limit the number of posts per profile
python main.py --max-posts 50

# Scrape without an item limit
python main.py --max-posts 0

# Skip media downloads (collect metadata only)
python main.py --no-media

# Skip screenshots (faster runs)
python main.py --no-screenshots

# Skip the final CSV export (data still saved as JSON)
python main.py --no-export

# Generate screenshots from existing metadata (no scraping)
python main.py --screenshots-only

# Scrape only specific accounts (comma-separated handles)
SCRAPE_ACCOUNTS="handle1,handle2" python main.py
```

| Flag | Description |
|---|---|
| `--platform` | `instagram`, `tiktok`, or `all` (default: `all`) |
| `--category` | Scrape only accounts matching a category label |
| `--start-date` | Override the study period start date (`YYYY-MM-DD`) |
| `--end-date` | Override the study period end date (`YYYY-MM-DD`) |
| `--max-posts` | Maximum posts per profile; use `0` for no item limit |
| `--no-media` | Skip downloading media files |
| `--no-screenshots` | Skip taking post screenshots |
| `--no-export` | Skip the consolidated CSV export at the end |
| `--screenshots-only` | Generate screenshots from existing metadata without scraping |

A consolidated CSV is exported automatically after every run unless
`--no-export` is supplied.

**Environment variable:** `SCRAPE_ACCOUNTS` — comma-separated list of handles
to restrict scraping to specific accounts.

## Project Structure

```
├── main.py                      # CLI entry point
├── run_web.py                   # Local web interface launcher
├── launch_gui.command           # Double-click launcher for macOS/Linux
├── launch_gui.bat               # Double-click launcher for Windows
├── config/
│   ├── settings.py              # Global paths and config loader
│   ├── accounts.json            # Your account configuration (git-ignored)
│   ├── accounts_example.json    # Template configuration
│   ├── instagram_cookies.json   # Instagram session cookies (git-ignored)
│   └── tiktok_cookies.txt       # Optional TikTok session cookies (git-ignored)
├── scrapers/
│   ├── instagram_playwright.py  # Instagram scraper (Playwright + API interception)
│   └── tiktok_scraper.py        # TikTok scraper (yt-dlp + carousel reconstruction)
├── utils/
│   ├── export.py                # CSV export utility
│   └── language.py              # Language detection (lingua-py)
├── web/                         # Flask GUI, templates, static assets, i18n
├── data/                        # All scraped data (git-ignored)
│   ├── raw/
│   │   ├── instagram/
│   │   │   └── [<label>/]<username>/
│   │   │       ├── <username>_metadata.json
│   │   │       ├── media/
│   │   │       └── screenshots/
│   │   └── tiktok/
│   │       └── [<label>/]<username>/
│   │           ├── <username>_metadata.json
│   │           ├── media/
│   │           └── screenshots/
│   └── exports/
│       └── dataset.csv          # Consolidated CSV
├── tests/
│   ├── conftest.py               # Shared pytest fixtures
│   ├── test_cli.py               # CLI argument parsing tests
│   ├── test_export.py            # CSV export tests
│   ├── test_language.py          # Language detection tests
│   └── test_settings.py          # Configuration tests
├── requirements.txt
├── CITATION.cff                  # Machine-readable citation metadata
├── CONTRIBUTING.md               # Contribution guidelines
├── LICENSE                       # GNU General Public License v3.0
├── THIRD_PARTY_LICENSES.md
├── paper.md                      # paper
├── paper.bib                     # paper references
└── .gitignore
```

## Output Data

### Metadata JSON

Each scraped profile generates a `<username>_metadata.json` file containing an
array of post objects with engagement metrics, timestamps, captions, hashtags,
and download paths.

### Consolidated CSV

A unified CSV is generated automatically after every run (skip with
`--no-export`). It contains the following columns:

| Column | Description |
|---|---|
| `category` | Optional grouping label (country, topic, sector, etc.) |
| `account_name` | Display name of the account |
| `account_id` | Short identifier for the account |
| `platform` | `instagram` or `tiktok` |
| `post_id` | Unique post identifier |
| `post_url` | Direct URL to the post |
| `date` | Publication date (ISO 8601) |
| `caption` | Post text / caption |
| `hashtags` | Comma-separated hashtag list |
| `language` | Auto-detected language (ISO 639-1 code, e.g. `es`, `en`) |
| `likes` | Like count |
| `comments` | Comment count |
| `views` | View count (video posts) |
| `shares` | Share count (TikTok only; `0` for Instagram) |
| `fb_likes` | Facebook cross-post likes (Instagram only; `0` for TikTok) |
| `format` | Content format: `image`, `video`, or `carousel` |
| `duration` | Video duration in seconds (TikTok only; `0` for images) |
| `music_title` | Audio track title (TikTok only) |
| `music_author` | Audio track artist (TikTok only) |
| `media_files` | Paths to downloaded media |
| `thumbnail` | Thumbnail image path |
| `metadata_file` | Source metadata file path |
| `notes` | Additional notes |

## Technical Stack

| Component | Technology |
|---|---|
| Instagram scraping | [Playwright](https://playwright.dev/python/) (Chromium) + API interception |
| TikTok scraping | [yt-dlp](https://github.com/yt-dlp/yt-dlp) + [curl_cffi](https://github.com/lexiforest/curl_cffi) |
| Media processing | [ffmpeg / ffprobe](https://ffmpeg.org/) |
| Language detection | [lingua-py](https://github.com/pemistahl/lingua-py) |
| HTTP client | [httpx](https://github.com/encode/httpx) |
| Data export | [pandas](https://pandas.pydata.org/) |
| Web interface | [Flask](https://flask.palletsprojects.com/) |
| Runtime | Python 3.9+ |

## Testing

The project includes a test suite built with [pytest](https://docs.pytest.org/).
Run all tests with:

```bash
python -m pytest tests/ -v
```

Tests cover configuration loading, language detection, CSV export logic, and
CLI argument parsing — all without requiring network access or platform
credentials.

## Ethical Use & Legal Notice

This tool is intended for **academic and noncommercial research** on public
data. Before using it, please consider the following:

- **Terms of Service.** Automated scraping may conflict with the Terms of
  Service of Instagram and TikTok. You are solely responsible for ensuring
  your use complies with applicable platform policies.
- **Privacy and data protection.** Collected data may contain personal
  information protected by laws such as the
  [GDPR](https://gdpr.eu/) (EU/EEA). Handle all data in accordance with your
  institution's ethics review board and applicable data-protection regulations.
- **Rate limiting.** The scraper includes built-in delays and respects platform
  rate limits. Do not modify these settings in ways that could degrade service
  for other users.
- **Fediverse instance policies.** If you adapt this tool for federated
  platforms, review each instance's policies on research data collection.
- **No warranty.** Platform APIs and page structures change frequently. The
  software is provided "as is" and may stop working without notice.

## Citation

If you use this tool in academic work, please cite it using the metadata in
[CITATION.cff](CITATION.cff), or as:

```bibtex
@software{quian2026scraper,
  author       = {Quian, Alberto},
  title        = {Instagram \& TikTok Scraper},
  year         = {2026},
  institution  = {Universidade de Santiago de Compostela},
  url          = {https://github.com/AlbertoQuian/instagram-tiktok-scraper},
  doi          = {10.5281/zenodo.19054043},
  license      = {GPL-3.0}
}
```

Or in APA style:

> Quian, A. (2026). *Instagram & TikTok Scraper* (v1.0.0) [Computer software].
> Zenodo. https://doi.org/10.5281/zenodo.19054043

## License

This project is licensed under the
[GNU General Public License v3.0](LICENSE).

You are free to use, modify, and redistribute this software under the terms of
the GPL v3. See the full license text in [LICENSE](LICENSE) and third-party
attributions in [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Author

**Alberto Quian** · [Universidade de Santiago de Compostela](https://www.usc.gal/)
— developed for academic research purposes.
