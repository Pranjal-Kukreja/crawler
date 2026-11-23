"""Tests for the fetch layer. No real network: a fake site answers every request."""
from pathlib import Path

import httpx
import pytest

from src.fetcher import Fetcher, Refused, TooManyBlocks
from src.urls import in_scope, normalise

# The real robots.txt, saved by hand into tests/fixtures.
ROBOTS = (Path(__file__).parent / "fixtures" / "robots_iitp.txt").read_text()

CFG = {
    "user_agent": "IITP-KB-Student-Project (contact: test@example.com)",
    "allowed_hosts": ["www.iitp.ac.in"],
    "allowed_prefixes": ["/departments", "/admissions", "/research"],
    "blocked_query_keys": ["sort", "page", "filter"],
    "allowed_queries": [{"path_endswith": "/faculty/profile", "keys": ["id"]}],
    "fetch": {
        "min_delay_seconds": 1.5, "timeout_seconds": 5, "max_retries": 3,
        "backoff_base_seconds": 2, "max_consecutive_blocks": 5, "raw_dir": "",
    },
}


class FakeClock:
    """Time that only moves when something sleeps, so tests finish instantly."""
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.t += seconds


def make_fetcher(tmp_path, handler):
    """Build a Fetcher wired to a fake site. Returns (fetcher, clock, list_of_requested_paths)."""
    seen = []

    def wrapped(request):
        seen.append(request.url.raw_path.decode())
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS)
        return handler(request)

    cfg = {**CFG, "fetch": {**CFG["fetch"], "raw_dir": str(tmp_path / "raw")}}
    clock = FakeClock()
    fetcher = Fetcher(
        cfg,
        client=httpx.Client(transport=httpx.MockTransport(wrapped)),
        sleep=clock.sleep, clock=clock.now,
    )
    return fetcher, clock, seen


def ok(request):
    return httpx.Response(200, text="<html>hello</html>")


# ---- blocked paths are refused, and no request is even sent ----
@pytest.mark.parametrize("url", [
    "https://www.iitp.ac.in/api/x",
    "https://www.iitp.ac.in/?page=2",
    "https://www.iitp.ac.in/departments/cse?sort=name",
    "https://www.iitp.ac.in/departments/cse?filter=a",
    "https://www.iitp.ac.in/admin/login",
    "https://www.iitp.ac.in/dev/test",
    "https://www.iitp.ac.in/.next/static/x.js",
    "https://www.iitp.ac.in/private/a",
    "https://www.iitp.ac.in/search?q=cse",
])
def test_blocked_paths_are_refused(tmp_path, url):
    fetcher, _, seen = make_fetcher(tmp_path, ok)
    with pytest.raises(Refused):
        fetcher.fetch(url)
    assert seen == ["/robots.txt"]  # only robots.txt was requested, never the blocked URL


@pytest.mark.parametrize("url", [
    "https://insti-website.netlify.app/sitemap.xml",
    "http://localhost:3000/departments",
    "https://academics.iitp.ac.in/",
])
def test_other_hosts_are_refused(tmp_path, url):
    fetcher, _, seen = make_fetcher(tmp_path, ok)
    with pytest.raises(Refused):
        fetcher.fetch(url)
    assert seen == []  # not even robots.txt: we never talk to other hosts


def test_normal_page_is_fetched(tmp_path):
    fetcher, _, seen = make_fetcher(tmp_path, ok)
    page = fetcher.fetch("https://www.iitp.ac.in/admissions")
    assert page.status == 200 and "hello" in page.text and not page.from_cache


# ---- the delay ----
def test_delay_between_requests_is_honoured(tmp_path):
    fetcher, clock, seen = make_fetcher(tmp_path, ok)
    times = []
    for path in ["/admissions", "/research/a", "/research/b"]:
        fetcher.fetch(f"https://www.iitp.ac.in{path}")
        times.append(clock.t)
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert all(g >= 1.5 for g in gaps), gaps


# ---- the cache ----
def test_second_fetch_makes_no_request(tmp_path):
    fetcher, _, seen = make_fetcher(tmp_path, ok)
    fetcher.fetch("https://www.iitp.ac.in/admissions")
    before = len(seen)
    again = fetcher.fetch("https://www.iitp.ac.in/admissions/")  # same page, trailing slash
    assert again.from_cache and len(seen) == before


def test_cache_survives_a_new_run(tmp_path):
    first, _, _ = make_fetcher(tmp_path, ok)
    first.fetch("https://www.iitp.ac.in/admissions")
    second, _, seen = make_fetcher(tmp_path, ok)   # a fresh run, same raw folder
    page = second.fetch("https://www.iitp.ac.in/admissions")
    assert page.from_cache
    assert "/admissions" not in seen               # only robots.txt hit the network


# ---- retries and stopping ----
def test_retries_with_backoff_then_succeeds(tmp_path):
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, text="ok")

    fetcher, clock, _ = make_fetcher(tmp_path, flaky)
    assert fetcher.fetch("https://www.iitp.ac.in/admissions").status == 200
    assert calls["n"] == 3
    assert 2 in clock.sleeps and 4 in clock.sleeps  # backoff doubled


def test_stops_after_five_blocks_in_a_row(tmp_path):
    fetcher, _, seen = make_fetcher(tmp_path, lambda r: httpx.Response(403))
    with pytest.raises(TooManyBlocks):
        for i in range(10):
            fetcher.fetch(f"https://www.iitp.ac.in/research/p{i}")
    assert sum(1 for p in seen if p != "/robots.txt") == 5  # stopped on the 5th


def test_a_good_response_resets_the_block_counter(tmp_path):
    answers = iter([403, 403, 403, 403, 200, 403, 403, 403, 403])
    fetcher, _, _ = make_fetcher(tmp_path, lambda r: httpx.Response(next(answers)))
    for i in range(9):                       # 4 blocks, a success, 4 more: never 5 in a row
        fetcher.fetch(f"https://www.iitp.ac.in/research/p{i}")


def test_user_agent_carries_contact(tmp_path):
    agents = []

    def spy(request):
        agents.append(request.headers["user-agent"])
        return httpx.Response(200, text="x")

    fetcher, _, _ = make_fetcher(tmp_path, spy)
    fetcher.fetch("https://www.iitp.ac.in/admissions")
    assert agents == ["IITP-KB-Student-Project (contact: test@example.com)"]


# ---- URL cleaning and scope ----
def test_normalise():
    assert normalise("HTTPS://WWW.IITP.AC.IN/Admissions/#fees") == "https://www.iitp.ac.in/Admissions"
    assert normalise("https://www.iitp.ac.in") == "https://www.iitp.ac.in/"


@pytest.mark.parametrize("url,expected", [
    ("https://www.iitp.ac.in/departments/cse", True),
    ("https://www.iitp.ac.in/departments/cse?page=2", False),
    ("https://www.iitp.ac.in/departments/cse/faculty/profile?id=62", True),    # the one exception
    ("https://www.iitp.ac.in/departments/cse/faculty/profile?id=62&page=2", False),
    ("https://www.iitp.ac.in/departments/cse/faculty/profile?name=x", False),
    ("https://www.iitp.ac.in/departments/cse/faculty?id=62", False),
    ("https://www.iitp.ac.in/research/x.pdf", False),
    ("https://www.iitp.ac.in/researchers", False),   # not the same path segment as /research
    ("https://www.iitp.ac.in/notices/x", False),
    ("https://academics.iitp.ac.in/departments/x", False),
])
def test_scope(url, expected):
    assert in_scope(url, CFG)[0] is expected
