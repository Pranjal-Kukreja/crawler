"""Breadth-first crawler: start at the seeds, follow in-scope links, write the inventory.

Depth 0 is a seed. Links found on a depth-N page are queued at depth N+1, and we
stop queueing past max_depth. The crawler never touches the network itself: it
asks the Fetcher, so every politeness rule still applies.
"""
import csv
import sys
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.config import load_config
from src.fetcher import Fetcher, Refused, TooManyBlocks
from src.urls import in_scope, normalise

INVENTORY_FIELDS = ["url", "status", "page_type_guess", "linked_from", "accepted", "reject_reason"]


def page_type_guess(url):
    """A rough label from the URL path. Step 4 refines this by looking at the page."""
    parts = [p for p in urlsplit(url).path.lower().split("/") if p]
    if not parts:
        return "home"
    if parts[0] == "departments":
        if any(p in ("faculty", "people") for p in parts[2:]):
            return "faculty"
        return "department" if len(parts) == 2 else "department_sub"
    if parts[0] in ("admissions", "research", "administration", "news"):
        return parts[0]
    if parts[0] == "services-amenities":
        return "services"
    return "other"


def extract_links(html, base_url):
    """Every <a href> on the page, made absolute. Skips mailto:, tel:, javascript:."""
    soup = BeautifulSoup(html, "lxml")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        links.append(urljoin(base_url, href))
    return links


def crawl(cfg, fetcher, log=print):
    """Return the inventory rows (a list of dicts). Fetches at most max_pages pages."""
    max_depth, max_pages = cfg["crawl"]["max_depth"], cfg["crawl"]["max_pages"]
    rows = {}            # normalised url -> inventory row, so each URL appears once
    queue = deque()

    def add(url, linked_from, depth):
        url = normalise(url)
        if url in rows:
            return
        ok, reason = in_scope(url, cfg)
        rows[url] = {
            "url": url, "status": "", "page_type_guess": page_type_guess(url),
            "linked_from": linked_from, "accepted": ok, "reject_reason": reason,
        }
        if ok:
            queue.append((url, depth))

    for seed in cfg["seeds"]:
        add(seed, "seed", 0)

    fetched = 0
    while queue:
        url, depth = queue.popleft()
        if fetched >= max_pages:
            rows[url].update(accepted=False, reject_reason="page cap reached")
            continue
        try:
            page = fetcher.fetch(url)
        except Refused as e:
            rows[url].update(accepted=False, reject_reason=f"refused: {e}")
            continue
        except TooManyBlocks:
            log("STOP: too many 403/429 in a row. Saving what we have so far.")
            rows[url].update(status="blocked")
            break
        fetched += 1
        rows[url]["status"] = page.status
        log(f"[{fetched}] depth {depth} {page.status} {'cache' if page.from_cache else 'net  '} {url}")
        if page.status != 200 or depth >= max_depth:
            continue
        for link in extract_links(page.text, url):
            add(link, url, depth + 1)

    return list(rows.values())


def write_inventory(rows, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INVENTORY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def robots_matches_local(fetcher, host, local_path="robots.txt"):
    """Compare the live robots.txt with the copy saved in this folder (ignoring blank lines)."""
    def clean(text):
        return [ln.strip() for ln in text.splitlines() if ln.strip()]
    return clean(fetcher.robots_text[host]) == clean(Path(local_path).read_text())


def main():
    cfg = load_config()
    fetcher = Fetcher(cfg)
    host = cfg["allowed_hosts"][0]
    fetcher._policy(host)  # reads the live robots.txt (one request)
    if not robots_matches_local(fetcher, host):
        print("STOP: the live robots.txt differs from ./robots.txt. Compare them before crawling.")
        sys.exit(2)
    print("live robots.txt matches ./robots.txt")

    rows = []
    try:
        rows = crawl(cfg, fetcher)
    finally:
        write_inventory(rows, "data/url_inventory.csv")
    accepted = sum(1 for r in rows if r["accepted"])
    print(f"\n{len(rows)} URLs seen, {accepted} accepted, "
          f"{fetcher.network_requests} network requests this run")


if __name__ == "__main__":
    main()
