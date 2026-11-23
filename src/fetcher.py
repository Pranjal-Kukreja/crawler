"""The polite fetch layer. This is the ONLY code that talks to the network.

Order of events for fetch(url):
  1. clean the URL, check the host is allowed
  2. check robots.txt (and our blocked query keys)
  3. if we already saved this URL, return the saved copy (no network, no waiting)
  4. wait until at least min_delay_seconds have passed since our last request to the host
  5. send the request; retry with backoff on errors; stop the run after too many 403/429
  6. save the raw response under data/raw/<sha256 of the URL>
"""
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from src.robots_policy import RobotsPolicy
from src.urls import normalise


class Refused(Exception):
    """We chose not to fetch this URL (wrong host, or robots.txt says no)."""


class TooManyBlocks(Exception):
    """The site answered 403/429 too many times in a row. Stop the whole run."""


@dataclass
class Page:
    url: str
    status: int
    text: str
    from_cache: bool
    content: bytes = b""   # the raw bytes, for files like PDFs


class Fetcher:
    def __init__(self, cfg, client=None, sleep=time.sleep, clock=time.monotonic):
        self.cfg = cfg
        self.fc = cfg["fetch"]
        # One client for the whole run so connections are reused.
        self.client = client or httpx.Client(
            headers={"User-Agent": cfg["user_agent"]},
            timeout=self.fc["timeout_seconds"],
            follow_redirects=True,
        )
        # sleep and clock are swappable so tests can run instantly.
        self.sleep = sleep
        self.clock = clock
        self.raw_dir = Path(self.fc["raw_dir"])
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = {}   # host -> time of our last request
        self._robots = {}         # host -> RobotsPolicy (parsed once per run)
        self.robots_text = {}     # host -> the raw robots.txt we read this run
        self.network_requests = 0  # every request actually sent (cache hits don't count)
        self._blocks_in_a_row = 0
        # A short, explicit list of URLs on one extra host (the syllabus PDFs). Nothing else there.
        self.extra_urls = set()
        pdf = cfg.get("pdf_downloads")
        for key in ("urls_file", "extra_urls_file", "candidate_urls_file"):
            if pdf and key in pdf and Path(pdf[key]).exists():
                self.extra_urls |= {normalise(u) for u in Path(pdf[key]).read_text().split()}

    # ---- public ----
    def fetch(self, url):
        url = self._check(url)
        host = urlsplit(url).netloc
        cached = self._read_cache(url)
        if cached:
            return cached

        resp = self._polite_get(url, host)
        self._save(url, resp)
        return Page(url, resp.status_code, resp.text, from_cache=False, content=resp.content)

    def head(self, url):
        """Header-only request: returns the response (status and headers, no body). Not cached."""
        url = self._check(url)
        return self._polite_get(url, urlsplit(url).netloc, method="HEAD")

    def cached(self, url):
        """The saved copy of a URL, or None. Never touches the network."""
        return self._read_cache(normalise(url))

    def saved_at(self, url):
        """When we saved this URL (ISO time), or None."""
        _, meta = self._paths(normalise(url))
        return json.loads(meta.read_text())["fetched_at"] if meta.exists() else None

    def _check(self, url):
        """Clean the URL and raise Refused unless host and robots.txt both allow it."""
        url = normalise(url)
        host = urlsplit(url).netloc
        if host not in self.cfg["allowed_hosts"] and url not in self.extra_urls:
            raise Refused(f"host not allowed: {host}")
        allowed, reason = self._policy(host).check(url)
        if not allowed:
            raise Refused(f"{url}: {reason}")
        return url

    # ---- robots ----
    def _policy(self, host):
        if host not in self._robots:
            # robots.txt is fetched with the same politeness, but is re-read every run.
            resp = self._polite_get(f"https://{host}/robots.txt", host)
            if resp.status_code >= 500:
                raise Refused("robots.txt unavailable (server error), so we do not crawl")
            text = resp.text if resp.status_code == 200 else ""  # 404 = no rules
            self._save(f"https://{host}/robots.txt", resp)
            self.robots_text[host] = text
            self._robots[host] = RobotsPolicy(
                text, self.cfg["user_agent"], self.cfg["blocked_query_keys"]
            )
        return self._robots[host]

    # ---- network ----
    def _wait_turn(self, host):
        """Sleep so that requests to one host are at least the minimum delay apart."""
        delay = self.fc["min_delay_seconds"]
        policy = self._robots.get(host)
        if policy and policy.crawl_delay():
            delay = max(delay, policy.crawl_delay())  # never faster than robots asks
        if host in self._last_request:
            wait = delay - (self.clock() - self._last_request[host])
            if wait > 0:
                self.sleep(wait)

    def _polite_get(self, url, host, method="GET"):
        resp = None
        for attempt in range(self.fc["max_retries"] + 1):
            self._wait_turn(host)
            self.network_requests += 1
            try:
                resp = self.client.request(
                    method, url, headers={"User-Agent": self.cfg["user_agent"]}
                )
            except httpx.HTTPError:
                self._last_request[host] = self.clock()
                self._backoff(attempt)
                continue
            self._last_request[host] = self.clock()

            if resp.status_code in (403, 429):
                self._blocks_in_a_row += 1
                if self._blocks_in_a_row >= self.fc["max_consecutive_blocks"]:
                    self._save(url, resp)
                    raise TooManyBlocks(
                        f"{self._blocks_in_a_row} blocks (403/429) in a row, stopping"
                    )
            else:
                self._blocks_in_a_row = 0

            if resp.status_code == 429 or resp.status_code >= 500:
                self._backoff(attempt)   # temporary trouble: wait longer and try again
                continue
            return resp                  # includes 403 and 404: we report them, not retry
        # Out of retries: hand back the last answer if we have one, else give up.
        if resp is not None:
            return resp
        raise httpx.ConnectError(f"could not reach {url} after retries")

    def _backoff(self, attempt):
        self.sleep(self.fc["backoff_base_seconds"] * (2 ** attempt))

    # ---- raw cache ----
    def _paths(self, url):
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.raw_dir / f"{key}.body", self.raw_dir / f"{key}.json"

    def _save(self, url, resp):
        body, meta = self._paths(url)
        body.write_bytes(resp.content)
        meta.write_text(json.dumps({
            "url": url,
            "status": resp.status_code,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "content_type": resp.headers.get("content-type", ""),
        }))

    def _read_cache(self, url):
        body, meta = self._paths(url)
        if not (body.exists() and meta.exists()):
            return None
        info = json.loads(meta.read_text())
        # Blocks and server errors are not worth keeping: try those again next time.
        if info["status"] in (403, 429) or info["status"] >= 500:
            return None
        data = body.read_bytes()
        return Page(url, info["status"], data.decode("utf-8", "replace"), True, content=data)
