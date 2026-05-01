# Instagram & TikTok Scraper
# Copyright (c) 2025 Alberto Quian – Universidade de Santiago de Compostela
# Licensed under the GNU General Public License v3.0. See LICENSE for details.
"""Generate the architecture diagram (architecture.png) shipped with the JOSS paper.

Run from the repository root:

    python scripts/generate_architecture.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUTPUT = Path(__file__).resolve().parent.parent / "architecture.png"

NODES = [
    # (x, y, w, h, color, title, subtitle, italic)
    (1.0, 13.5, 3.0, 1.1, "#3D85C6", "CLI", "main.py", "argparse"),
    (7.0, 13.5, 3.0, 1.1, "#0F8A92", "Web GUI", "run_web.py\nweb/app.py", "Flask + ES/EN"),
    (3.7, 11.5, 3.6, 1.2, "#E69138", "Configuration",
     "config/settings.py\nconfig/accounts.json", ""),
    (0.6, 9.0, 3.6, 1.3, "#8E7CC3", "Instagram Scraper",
     "Playwright + GraphQL API\ninterception", ""),
    (6.8, 9.0, 3.6, 1.3, "#8E7CC3", "TikTok Scraper",
     "yt-dlp + curl_cffi\nPlaywright + ffmpeg", ""),
    (3.7, 6.5, 3.6, 1.2, "#6AA84F", "Metadata JSON",
     "Per-account files\ndata/raw/", ""),
    (3.7, 4.5, 3.6, 1.1, "#6AA84F", "Language Detection",
     "utils/language.py", "lingua-py"),
    (3.7, 2.5, 3.6, 1.1, "#CC0000", "CSV Export",
     "utils/export.py", "pandas"),
    (3.7, 0.5, 3.6, 1.1, "#CC0000", "Output CSV",
     "24 columns\nUTF-8", ""),
]

EDGES = [
    (0, 2), (1, 2), (2, 3), (2, 4),
    (3, 5), (4, 5),
    (5, 6), (6, 7), (7, 8),
]


def _node_center(node):
    x, y, w, h, *_ = node
    return (x + w / 2.0, y + h / 2.0)


def _edge_anchor(src, dst):
    """Return (start, end) anchored at the borders of the boxes."""
    sx, sw, sh = src[0], src[2], src[3]
    dx, dw, dh = dst[0], dst[2], dst[3]
    s_top = (sx + sw / 2.0, src[1] + sh)
    s_bot = (sx + sw / 2.0, src[1])
    d_top = (dx + dw / 2.0, dst[1] + dh)
    d_bot = (dx + dw / 2.0, dst[1])
    if dst[1] < src[1]:
        return s_bot, d_top
    return s_top, d_bot


def main():
    fig, ax = plt.subplots(figsize=(7, 12.5), dpi=130)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 15.2)
    ax.set_axis_off()

    for node in NODES:
        x, y, w, h, color, title, subtitle, italic = node
        box = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.04,rounding_size=0.18",
            linewidth=0,
            facecolor=color,
            alpha=0.95,
        )
        ax.add_patch(box)
        cx, cy = _node_center(node)
        ax.text(cx, y + h - 0.32, title,
                ha="center", va="center",
                fontsize=12, fontweight="bold",
                color="white")
        ax.text(cx, cy - 0.12, subtitle,
                ha="center", va="center",
                fontsize=9, color="white", linespacing=1.25)
        if italic:
            ax.text(cx, y + 0.18, italic,
                    ha="center", va="center",
                    fontsize=8.5, fontstyle="italic", color="white")

    for src_idx, dst_idx in EDGES:
        start, end = _edge_anchor(NODES[src_idx], NODES[dst_idx])
        arrow = FancyArrowPatch(
            start, end,
            arrowstyle="-|>",
            mutation_scale=15,
            color="#444444",
            linewidth=1.4,
            connectionstyle="arc3,rad=0.05",
        )
        ax.add_patch(arrow)

    plt.tight_layout()
    plt.savefig(OUTPUT, dpi=160, bbox_inches="tight",
                facecolor="white")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
