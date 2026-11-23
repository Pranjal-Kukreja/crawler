"""Step 9 chart: active seconds per page for each scraper (median of the 3 runs), from benchmark/pages.csv.

    python -m benchmark.chart        # writes benchmark/active_seconds_per_page.png

Colours are the first two slots of the validated reference palette (blue, orange): worst colour-vision separation
24.7, normal-vision 33.6, contrast against the surface above 3:1. Identity also comes from the legend and from
the bar position (HTTP above Selenium in every pair), never from colour alone.
"""
import csv
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

BENCH = Path(__file__).parent
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
HTTP, SELENIUM = "#2a78d6", "#eb6834"


def label(url):
    parts = urlsplit(url)
    segs = [s for s in parts.path.split("/") if s]
    if parts.netloc.startswith("academics"):
        if "id" in parse_qs(parts.query):
            return {"78": "academics: Downloads (id 78)", "59": "academics: calendar (id 59)"}.get(
                parse_qs(parts.query)["id"][0], "academics article")
        return "syllabus: " + segs[-1].replace(".html", "")
    dept = segs[1] if len(segs) > 1 else ""
    return dept if len(segs) == 2 else f"{dept} / {segs[2]}"


def main():
    rows = list(csv.DictReader(open(BENCH / "pages.csv")))
    names = [label(r["url"]) for r in rows]
    h = [float(r["http_active_s"]) for r in rows]
    s = [float(r["selenium_active_s"]) for r in rows]
    fig, ax = plt.subplots(figsize=(10, 0.42 * len(rows) + 1.6), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    ys = range(len(rows))
    ax.barh([y - 0.2 for y in ys], h, height=0.36, color=HTTP, label="HTTP (httpx)", edgecolor=SURFACE, linewidth=1)
    ax.barh([y + 0.2 for y in ys], s, height=0.36, color=SELENIUM, label="Selenium (headless Chrome)", edgecolor=SURFACE, linewidth=1)
    ax.set_yticks(list(ys), names, fontsize=8, color=INK2)
    ax.invert_yaxis()
    ax.set_xlabel("active seconds per page (median of 3 runs; the 1.5 s delay is not included)", color=INK2, fontsize=9)
    ax.set_title("Active time per page, HTTP vs Selenium, same 27 pages", color=INK, fontsize=12, loc="left")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="x", colors=INK2, labelsize=8, length=0)
    ax.tick_params(axis="y", length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
    fig.tight_layout()
    out = BENCH / "active_seconds_per_page.png"
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print("wrote", out)


if __name__ == "__main__":
    main()
