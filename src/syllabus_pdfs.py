"""Syllabus PDFs linked from the department pages and hosted on the academics site.

Commands (run from the project folder):
  python -m src.syllabus_pdfs list    # offline: read saved department pages, write the PDF list
  python -m src.syllabus_pdfs head    # header-only requests: sizes, nothing is downloaded
  python -m src.syllabus_pdfs download  # fetch the listed PDFs into curated_pdfs/<department>/

Only PDFs on the host named in config.yaml (pdf_downloads.host) are collected. PDFs on
www.iitp.ac.in are left alone (its robots.txt is ambiguous), so those stay manual.
"""
import csv
import hashlib
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.config import load_config
from src.fetcher import Fetcher
from src.urls import normalise

LIST_CSV = "data/academics_pdf_list.csv"
# PDFs the user approved one by one (not found by scanning department pages), same columns as LIST_CSV.
EXTRA_CSV = "data/academics_extra_pdfs.csv"
FIELDS = ["department", "programme", "duration", "url", "linked_from"]


def card_text(anchor):
    """The text of the card around a link: climb until the parent holds more than the link."""
    own = " ".join(anchor.get_text(" ", strip=True).split())
    node = anchor
    for _ in range(4):
        node = node.parent
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) > len(own) + 3:
            return text.replace(own, "").strip()
    return ""


def split_programme(text, filename):
    """'B.Tech. in AI Duration : 4 years' -> ('B.Tech. in AI', '4 years').
    Falls back to the file name if the card has no programme name."""
    m = re.match(r"(.*?)\s*Duration\s*:\s*(.*)$", text)
    if m and m.group(1):
        return m.group(1).strip(), m.group(2).strip()
    return text or filename, ""


def collect(cfg, fetcher):
    """Read the saved department pages (no network) and return one row per PDF URL."""
    pdf_host = cfg["pdf_downloads"]["host"]
    inventory = csv.DictReader(open("data/url_inventory.csv"))
    by_url = {}
    for r in inventory:
        path = urlsplit(r["url"]).path
        if r["accepted"] != "True" or not path.startswith("/departments/") or r["status"] != "200":
            continue
        page = fetcher.cached(r["url"])
        if page is None:
            print("not in cache, skipped:", r["url"])
            continue
        department = path.split("/")[2]
        for a in BeautifulSoup(page.text, "lxml").find_all("a", href=True):
            link = normalise(urljoin(r["url"], a["href"].strip()))
            parts = urlsplit(link)
            if parts.netloc != pdf_host or not parts.path.lower().endswith(".pdf"):
                continue
            filename = parts.path.rsplit("/", 1)[-1]
            programme, duration = split_programme(card_text(a), filename)
            row = {"department": department, "programme": programme, "duration": duration,
                   "url": link, "linked_from": r["url"]}
            # The same PDF is linked from two pages; keep the one that gave us a duration.
            if link not in by_url or (duration and not by_url[link]["duration"]):
                by_url[link] = row
    return sorted(by_url.values(), key=lambda r: (r["department"], r["url"]))


def write_list(rows, cfg):
    Path(LIST_CSV).parent.mkdir(parents=True, exist_ok=True)
    with open(LIST_CSV, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    # This file is the allowlist the fetcher reads: only these URLs on the academics host.
    Path(cfg["pdf_downloads"]["urls_file"]).write_text("\n".join(r["url"] for r in rows) + "\n")


def pdf_rows():
    """Every PDF we download: the department-page list plus the hand-approved extras."""
    rows = list(csv.DictReader(open(LIST_CSV)))
    if Path(EXTRA_CSV).exists():
        rows += list(csv.DictReader(open(EXTRA_CSV)))
    return rows


def head_all(rows, fetcher):
    """One header-only request per PDF. Stops and raises if the server won't answer properly."""
    sizes = {}
    for r in rows:
        resp = fetcher.head(r["url"])
        length = resp.headers.get("content-length")
        if resp.status_code != 200 or length is None:
            raise RuntimeError(
                f"header-only request not answered properly for {r['url']}: "
                f"status {resp.status_code}, content-length {length}"
            )
        sizes[r["url"]] = int(length)
    return sizes


def slug(text):
    """'B.Tech. in AI & Data Science' -> 'btech-in-ai-data-science' (safe for a file name)."""
    text = re.sub(r"[^a-z0-9]+", "-", text.lower().replace(".", "").replace("&", " "))
    return text.strip("-")


def download_all(rows, fetcher, out_dir):
    """Fetch each PDF (cached ones are not re-downloaded) and save it by programme name.
    Returns the list of (path, bytes)."""
    saved, used = [], set()
    for r in rows:
        page = fetcher.fetch(r["url"])
        if page.status != 200 or not page.content.startswith(b"%PDF"):
            raise RuntimeError(f"not a PDF: {r['url']} (status {page.status})")
        name = slug(r["programme"])
        while (r["department"], name) in used:   # two programmes with the same name
            name += "-2"
        used.add((r["department"], name))
        path = Path(out_dir) / r["department"] / f"{name}.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(page.content)
        saved.append((path, len(page.content)))
    return saved


MANIFEST_FIELDS = ["url", "department", "programme", "size", "sha256", "fetched_at", "file"]


def write_manifest(rows, fetcher, out_dir):
    """curated_pdfs/MANIFEST.csv: what each PDF is, where it came from and its checksum.
    The PDFs themselves stay out of git; this small file is what gets committed."""
    out = []
    for r in rows:
        path = Path(out_dir) / r["department"] / f"{slug(r['programme'])}.pdf"
        data = path.read_bytes()
        out.append({"url": r["url"], "department": r["department"], "programme": r["programme"],
                    "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                    "fetched_at": fetcher.saved_at(r["url"]), "file": str(path)})
    with open(Path(out_dir) / "MANIFEST.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(out)
    return out


def main():
    cfg = load_config()
    fetcher = Fetcher(cfg)
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "list":
        rows = collect(cfg, fetcher)
        write_list(rows, cfg)
        print(f"{len(rows)} PDFs on {cfg['pdf_downloads']['host']}; network requests: "
              f"{fetcher.network_requests}")
    elif cmd == "head":
        rows = list(csv.DictReader(open(LIST_CSV)))
        sizes = head_all(rows, fetcher)
        for r in rows:
            r["bytes"] = sizes[r["url"]]
        with open("data/academics_pdf_sizes.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS + ["bytes"])
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} PDFs, total {sum(sizes.values()) / 1e6:.1f} MB; "
              f"network requests: {fetcher.network_requests}")
    elif cmd == "download":
        rows = pdf_rows()
        saved = download_all(rows, fetcher, cfg["pdf_downloads"]["out_dir"])
        print(f"{len(saved)} PDFs saved, {sum(n for _, n in saved) / 1e6:.1f} MB; "
              f"network requests: {fetcher.network_requests}")
    elif cmd == "manifest":
        rows = pdf_rows()
        out = write_manifest(rows, fetcher, cfg["pdf_downloads"]["out_dir"])
        print(f"manifest: {len(out)} rows, network requests: {fetcher.network_requests}")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
