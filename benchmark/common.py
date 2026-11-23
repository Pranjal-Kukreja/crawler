"""Everything the two runners share, so that they cannot differ in these things (DECISION.md, "What is compared").

  - the page list (benchmark/urls.txt) and the rule that only those URLs are ever requested
  - the robots.txt fetch and check (src/robots_policy.py), the 1.5 s per-host delay, the user-agent
  - the psutil sampler, the failure rule, the safe-stop rule, and the per-page fields that are compared
Nothing here reads data/raw/.
"""
import json
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import psutil

from benchmark.extract import main_text
from src.config import load_config
from src.robots_policy import RobotsPolicy

BENCH = Path(__file__).parent
OUT = BENCH / "out"
MIN_TEXT = 200            # DECISION.md, Step 2: fewer characters than this is a failed load
STOP_AFTER_BLOCKS = 5     # consecutive 403/429 answers; the pipeline's own rule
TIMEOUT = 20              # seconds, the pipeline's timeout_seconds


class StopRun(Exception):
    """The site answered 403/429 too many times in a row. Stop the run, as the pipeline does."""


def load_urls(path=BENCH / "urls.txt"):
    """[(url, group)] from the page list; the comment after the URL starts with the group name."""
    out = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, comment = line.partition("#")
        out.append((url.strip(), comment.split("|")[0].strip()))
    return out


def config():
    cfg = load_config()
    return cfg, cfg["user_agent"], cfg["fetch"]["min_delay_seconds"]


class Pacer:
    """At least `delay` seconds between two requests to the same host. The sleep is measured, never counted as active time."""

    def __init__(self, delay, sleep=time.sleep, clock=time.monotonic):
        self.delay, self.sleep, self.clock = delay, sleep, clock
        self.last = {}

    def wait(self, host, delay=None):
        delay = max(self.delay, delay or 0)
        slept = 0.0
        if host in self.last:
            slept = max(0.0, delay - (self.clock() - self.last[host]))
            if slept:
                self.sleep(slept)
        return slept

    def mark(self, host):
        self.last[host] = self.clock()


def fetch_robots(hosts, user_agent, pacer, blocked_query_keys=()):
    """One robots.txt per host, fetched the same way for both scrapers. Returns ({host: RobotsPolicy}, {host: text}, requests)."""
    policies, texts, n = {}, {}, 0
    with httpx.Client(headers={"User-Agent": user_agent}, timeout=TIMEOUT, follow_redirects=True) as client:
        for host in hosts:
            pacer.wait(host)
            resp = client.get(f"https://{host}/robots.txt")
            pacer.mark(host)
            n += 1
            if resp.status_code >= 500:
                raise RuntimeError(f"robots.txt of {host} unavailable ({resp.status_code}); not running")
            texts[host] = resp.text if resp.status_code == 200 else ""
            policies[host] = RobotsPolicy(texts[host], user_agent, blocked_query_keys)
    return policies, texts, n


def crawl_delay(policy, delay):
    return max(delay, policy.crawl_delay() or 0)


def cdp_block_patterns(robots_text, user_agent):
    """URL patterns for Chrome's Network.setBlockedURLs, from the Disallow lines of the group that applies to us."""
    token = user_agent.split()[0].lower()
    patterns, agents, in_agents = [], [], False
    for raw in robots_text.splitlines():
        line = raw.split("#")[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if not in_agents:
                agents, in_agents = [], True
            agents.append(value.lower())
        else:
            in_agents = False
            if field == "disallow" and value and any(a == "*" or token.startswith(a) for a in agents):
                path = value.rstrip("$")
                pat = "*://*" + path
                patterns.append(pat if pat.endswith("*") else pat + "*")
    return list(dict.fromkeys(patterns))


def page_fields(html):
    """What is compared between scrapers: main text, title, headings, link set. Extraction time is kept apart."""
    from bs4 import BeautifulSoup

    t0 = time.perf_counter()
    text = main_text(html)
    extract_seconds = time.perf_counter() - t0
    soup = BeautifulSoup(html, "lxml")
    title = " ".join(soup.title.get_text(" ").split()) if soup.title else ""
    headings = [" ".join(h.get_text(" ").split()) for h in soup.find_all(["h1", "h2", "h3"])]
    links = sorted({a["href"].strip() for a in soup.find_all("a", href=True) if a["href"].strip()})
    return {"main_text": text, "text_chars": len(text), "title": title, "headings": headings, "links": links,
            "extract_seconds": extract_seconds}


def failure_reason(status, text_chars, error=""):
    """'' when the load counts as good (DECISION.md, Step 2)."""
    if error:
        return error
    if status >= 400:
        return f"http {status}"
    if text_chars < MIN_TEXT:
        return f"only {text_chars} characters of text"
    return ""


class Sampler(threading.Thread):
    """Samples the whole process tree (this process, chromedriver, every Chrome child) every `interval` seconds."""

    def __init__(self, interval=0.2):
        super().__init__(daemon=True)
        self.interval, self.stop_flag = interval, threading.Event()
        self.rss, self.cpu = [], []

    def run(self):
        root, known = psutil.Process(), {}
        while not self.stop_flag.is_set():
            rss = cpu = 0.0
            try:
                family = [root] + root.children(recursive=True)
            except psutil.Error:
                family = [root]
            for p in family:
                try:
                    if p.pid not in known:
                        known[p.pid] = p
                        p.cpu_percent(None)            # the first reading is a primer
                    else:
                        cpu += known[p.pid].cpu_percent(None)
                    rss += p.memory_info().rss
                except psutil.Error:
                    continue
            self.rss.append(rss)
            self.cpu.append(cpu)
            self.stop_flag.wait(self.interval)

    def result(self):
        self.stop_flag.set()
        self.join(timeout=2)
        return {"peak_rss_mb": round(max(self.rss, default=0) / 1e6, 1),
                "avg_cpu_percent": round(sum(self.cpu) / len(self.cpu), 1) if self.cpu else 0.0,
                "samples": len(self.rss)}


def write_run(scraper, run, record):
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{scraper}_run{run}.json"
    path.write_text(json.dumps(record, ensure_ascii=False))
    return path


def host_of(url):
    return urlsplit(url).netloc


def count_loc(path):
    """Non-blank lines that hold code: comments and docstrings do not count."""
    import io
    import tokenize

    lines, text = set(), Path(path).read_text()
    line_start = (None, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.NL, tokenize.COMMENT)
    prev = None
    for tok in tokenize.generate_tokens(io.StringIO(text).readline):
        if tok.type == tokenize.ENDMARKER:
            continue
        if tok.type == tokenize.STRING and prev in line_start:
            prev = tok.type                            # a string that starts a statement: a docstring
            continue
        if tok.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            lines.update(range(tok.start[0], tok.end[0] + 1))
        prev = tok.type
    return len(lines)


SETUP_STEPS = {
    "http": ["pip install httpx protego beautifulsoup4 lxml psutil"],
    "selenium": ["pip install selenium psutil beautifulsoup4 lxml protego httpx",
                 "install Google Chrome",
                 "let Selenium Manager download the matching chromedriver on the first run"],
}
