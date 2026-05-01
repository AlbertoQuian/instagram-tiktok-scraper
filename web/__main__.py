"""Run the web interface with `python -m web`."""
from __future__ import annotations

import os
import threading
import webbrowser

from .app import create_app


if __name__ == "__main__":
    host = os.environ.get("SCRAPER_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("SCRAPER_WEB_PORT", "5000"))
    debug = os.environ.get("SCRAPER_WEB_DEBUG", "0") == "1"
    if os.environ.get("SCRAPER_WEB_OPEN_BROWSER") == "1":
        threading.Timer(1.0, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    create_app().run(host=host, port=port, debug=debug)
