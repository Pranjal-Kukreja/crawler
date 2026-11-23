"""Department overview records: which programmes each department offers.

Source: each department's /courses page. Every programme is a card with a name, a duration,
an optional description and a link to its syllabus. One record per programme. Faculty are
not parsed (parked by the user), and no phones or emails are stored.
"""
import csv
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from src.config import load_config
from src.fetcher import Fetcher


def clean(text):
    return " ".join(text.split())


def parse_courses_page(html, page_url, fetched_at=""):
    soup = BeautifulSoup(html, "lxml")
    title = clean(soup.title.get_text()) if soup.title else ""
    m = re.search(r"Department of (.+?)\s*\|", title)
    department_name = f"Department of {m.group(1)}" if m else ""
    department = urlsplit(page_url).path.split("/")[2]
    records = []
    for a in soup.find_all("a", href=True):
        if "detailed syllabus" not in a.get_text(" ").lower():
            continue
        card = a.parent
        for _ in range(4):                      # climb to the card that holds name, duration, link
            if len([c for c in card.children if getattr(c, "name", None)]) >= 3:
                break
            card = card.parent
        kids = [clean(c.get_text(" ")) for c in card.children if getattr(c, "name", None)]
        name, duration = kids[0], re.sub(r"^Duration\s*:\s*", "", kids[1]) if len(kids) > 1 else ""
        description = kids[2] if len(kids) > 3 else ""
        records.append({
            "department": department, "department_name": department_name,
            "programme": name, "duration": duration, "description": description,
            "syllabus_url": urljoin(page_url, a["href"].strip()),
            "source_url": page_url, "fetched_at": fetched_at,
        })
    return records


def main():
    fetcher = Fetcher(load_config())
    pages = sorted(r["url"] for r in csv.DictReader(open("data/url_inventory.csv"))
                   if r["accepted"] == "True" and re.fullmatch(r"https://www\.iitp\.ac\.in/departments/[^/]+/courses", r["url"]))
    records = []
    for url in pages:
        page = fetcher.cached(url)
        if page is None:
            print("not in cache:", url)
            continue
        records += parse_courses_page(page.text, url, fetcher.saved_at(url))
    Path("data/out").mkdir(parents=True, exist_ok=True)
    Path("data/out/department_overview.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    print(f"{len(pages)} courses pages, {len(records)} programme records; network requests: {fetcher.network_requests}")


if __name__ == "__main__":
    main()
