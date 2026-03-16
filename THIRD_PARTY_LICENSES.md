# Third-Party Licenses

This project uses the third-party software listed below. Each component
retains its own license and copyright.

## Python Packages

| Package | SPDX Identifier | License | Repository |
|---------|----------------|---------|------------|
| yt-dlp | `Unlicense` | [The Unlicense](https://unlicense.org/) | <https://github.com/yt-dlp/yt-dlp> |
| curl_cffi | `MIT` | MIT License | <https://github.com/lexiforest/curl_cffi> |
| Playwright for Python | `Apache-2.0` | Apache License 2.0 | <https://github.com/microsoft/playwright-python> |
| httpx | `BSD-3-Clause` | BSD 3-Clause License | <https://github.com/encode/httpx> |
| pandas | `BSD-3-Clause` | BSD 3-Clause License | <https://github.com/pandas-dev/pandas> |
| lingua-language-detector | `Apache-2.0` | Apache License 2.0 | <https://github.com/pemistahl/lingua-py> |
| TikTokApi *(optional)* | `MIT` | MIT License | <https://github.com/davidteather/TikTok-Api> |

## External Tools

| Tool | SPDX Identifier | License | Website |
|------|----------------|---------|---------|
| ffmpeg / ffprobe | `LGPL-2.1-or-later` | GNU Lesser General Public License v2.1+ | <https://ffmpeg.org/> |
| Chromium | `BSD-3-Clause` | BSD-style (The Chromium Authors) | <https://www.chromium.org/> |

## License Compatibility

This project is distributed under the
[GNU General Public License v3.0](LICENSE) (GPL-3.0-or-later).

- **Permissive licenses** (MIT, BSD-3-Clause, Apache-2.0, Unlicense) are
  compatible with the GPL v3.
- **ffmpeg** is invoked only at runtime as a subprocess via `subprocess.run`;
  the project does not distribute ffmpeg binaries nor statically link against
  any ffmpeg library. Users must install ffmpeg separately.
- **Chromium** is downloaded separately by Playwright at install time
  (`playwright install chromium`); no Chromium binaries are bundled with this
  repository.
