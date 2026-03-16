# Instagram & TikTok Scraper

![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
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
- **Automatic language detection** via lingua-py (ISO 639-1 codes)
- **Configurable** account list with optional category grouping
- **Rate limiting** and retry logic with exponential back-off

## Requirements

| Dependency | Notes |
|---|---|
| **Python** | 3.10 or newer |
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

1. Copy the example configuration:

```bash
cp config/accounts_example.json config/accounts.json
```

2. Edit `config/accounts.json` with your target accounts:

```json
{
    "project": "My Research Project",
    "study_period": {
        "start": "2024-01-01",
        "end": "2024-06-30"
    },
    "accounts": [
        {
            "account_name": "Account Display Name",
            "account_id": "SHORT_ID",
            "category": "optional_category",
            "instagram": "ig_username",
            "tiktok": "tiktok_username"
        }
    ]
}
```

Each **account** represents a logical entity (brand, organization, public
figure, etc.) that may have profiles on one or both platforms. The `category`
field is optional and can represent any grouping you need (country, topic,
sector, etc.). When present, data is stored in a subdirectory named after
the category.

### Instagram Session Cookies

Instagram aggressively blocks unauthenticated requests. **Without session
cookies, the scraper will retrieve zero posts for most profiles.** Providing
your session cookies allows the scraper to make requests as your logged-in
browser session.

#### How to export your cookies

1. Install a browser extension that can export cookies in **JSON format**:
   - Firefox: [Cookie Editor](https://addons.mozilla.org/firefox/addon/cookie-editor/)
   - Chrome: [Cookie Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm)
2. Log in to [instagram.com](https://www.instagram.com) in your browser.
3. Open **Cookie Editor**, filter by `instagram.com`, and export **all
   cookies** as JSON.
4. Save the exported file to `config/instagram_cookies.json`.

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

> **Important:** The cookie file is automatically excluded from version control
> via `.gitignore`. **Never commit your session cookies to a public
> repository.** Cookies expire periodically; re-export them if the scraper
> stops retrieving data.

## Usage

```bash
# Scrape all configured accounts on both platforms
python main.py

# Scrape only Instagram
python main.py --platform instagram

# Scrape only TikTok for a specific category
python main.py --platform tiktok --category spain

# Override the study period
python main.py --start-date 2024-03-01 --end-date 2024-06-30

# Scrape and export a consolidated CSV
python main.py --export

# Generate screenshots from existing metadata (no scraping)
python main.py --screenshots-only

# Scrape only specific accounts (comma-separated handles)
SCRAPE_ACCOUNTS="handle1,handle2" python main.py
```

| Flag | Description |
|---|---|
| `--platform` | `instagram`, `tiktok`, or `all` (default: `all`) |
| `--category` | Scrape only accounts matching a category label |
| `--export` | Export a consolidated CSV after scraping |
| `--screenshots-only` | Generate screenshots from existing metadata without scraping |
| `--start-date` | Override the study period start date (`YYYY-MM-DD`) |
| `--end-date` | Override the study period end date (`YYYY-MM-DD`) |

**Environment variable:** `SCRAPE_ACCOUNTS` — comma-separated list of handles
to restrict scraping to specific accounts.

## Project Structure

```
├── main.py                      # CLI entry point
├── config/
│   ├── settings.py              # Global paths and config loader
│   ├── accounts.json            # Your account configuration (git-ignored)
│   ├── accounts_example.json    # Template configuration
│   └── instagram_cookies.json   # Instagram session cookies (git-ignored)
├── scrapers/
│   ├── instagram_playwright.py  # Instagram scraper (Playwright + API interception)
│   └── tiktok_scraper.py        # TikTok scraper (yt-dlp + carousel reconstruction)
├── utils/
│   ├── export.py                # CSV export utility
│   └── language.py              # Language detection (lingua-py)
├── data/                        # All scraped data (git-ignored)
│   ├── raw/
│   │   ├── instagram/
│   │   │   └── [<category>/]<username>/
│   │   │       ├── <username>_metadata.json
│   │   │       ├── media/
│   │   │       └── screenshots/
│   │   └── tiktok/
│   │       └── [<category>/]<username>/
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
├── paper.md                      # JOSS paper
├── paper.bib                     # JOSS paper references
└── .gitignore
```

## Output Data

### Metadata JSON

Each scraped profile generates a `<username>_metadata.json` file containing an
array of post objects with engagement metrics, timestamps, captions, hashtags,
and download paths.

### Consolidated CSV

The `--export` flag generates a unified CSV with the following columns:

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
| Runtime | Python 3.10+ |

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
