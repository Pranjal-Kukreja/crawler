"""Crawler tests against a tiny fake site (no real network)."""
import httpx

from src.crawler import crawl, extract_links, page_type_guess
from src.fetcher import Fetcher
from tests.test_fetcher import CFG, ROBOTS, FakeClock

SITE = {
    "/departments/cse": '<a href="/departments/cse/faculty">f</a>'
                        '<a href="/departments/cse?page=2">next</a>'
                        '<a href="https://example.com/x">out</a>'
                        '<a href="/notices/n1">notice</a>'
                        '<a href="/files/a.pdf">pdf</a>'
                        '<a href="mailto:a@b.c">mail</a>',
    "/departments/cse/faculty": '<a href="/research/r1">r</a>',
    "/research/r1": '<a href="/research/r2">deeper</a>',
    "/research/r2": "<p>too deep</p>",
}


def make(tmp_path, max_depth=2, max_pages=500):
    requested = []

    def handler(request):
        requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        body = SITE.get(request.url.path)
        return httpx.Response(200, text=body) if body else httpx.Response(404)

    cfg = {**CFG, "seeds": ["https://www.iitp.ac.in/departments/cse"],
           "crawl": {"max_depth": max_depth, "max_pages": max_pages},
           "fetch": {**CFG["fetch"], "raw_dir": str(tmp_path / "raw")}}
    clock = FakeClock()
    fetcher = Fetcher(cfg, client=httpx.Client(transport=httpx.MockTransport(handler)),
                      sleep=clock.sleep, clock=clock.now)
    return cfg, fetcher, requested


def by_url(rows):
    return {r["url"].replace("https://www.iitp.ac.in", ""): r for r in rows}


def test_follows_in_scope_links_and_stops_at_depth(tmp_path):
    cfg, fetcher, requested = make(tmp_path)
    rows = by_url(crawl(cfg, fetcher, log=lambda m: None))
    assert rows["/departments/cse/faculty"]["accepted"]
    assert rows["/research/r1"]["status"] == 200           # depth 2: fetched
    assert "/research/r2" not in rows                      # depth 3: links on r1 are not followed
    assert "/research/r2" not in requested


def test_rejects_are_listed_with_a_reason(tmp_path):
    cfg, fetcher, _ = make(tmp_path)
    rows = by_url(crawl(cfg, fetcher, log=lambda m: None))
    assert rows["/departments/cse?page=2"]["reject_reason"] == "has query string"
    assert rows["/notices/n1"]["reject_reason"] == "outside allowed prefixes"
    assert rows["/files/a.pdf"]["accepted"] is False
    assert rows["/departments/cse"]["linked_from"] == "seed"
    assert not any(u.startswith("mailto") for u in rows)


def test_rejected_urls_are_never_requested(tmp_path):
    cfg, fetcher, requested = make(tmp_path)
    crawl(cfg, fetcher, log=lambda m: None)
    assert set(requested) <= {"/robots.txt", "/departments/cse",
                              "/departments/cse/faculty", "/research/r1"}


def test_page_cap(tmp_path):
    cfg, fetcher, _ = make(tmp_path, max_pages=2)
    rows = crawl(cfg, fetcher, log=lambda m: None)
    assert sum(1 for r in rows if r["status"] == 200) == 2


def test_rerun_makes_zero_new_requests_for_cached_urls(tmp_path):
    cfg, first, _ = make(tmp_path)
    crawl(cfg, first, log=lambda m: None)
    cfg, second, requested = make(tmp_path)               # a new run, same raw folder
    crawl(cfg, second, log=lambda m: None)
    assert requested == ["/robots.txt"]                    # only robots.txt is re-read


def test_helpers():
    assert page_type_guess("https://www.iitp.ac.in/departments/cse") == "department"
    assert page_type_guess("https://www.iitp.ac.in/departments/cse/faculty") == "faculty"
    assert page_type_guess("https://www.iitp.ac.in/admissions") == "admissions"
    links = extract_links('<a href="../x">a</a><a href="#top">b</a>', "https://h/a/b")
    assert links == ["https://h/x"]
