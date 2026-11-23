"""Answers one question: "may I fetch this URL?", using robots.txt read with protego.

Both the pipeline and the Selenium benchmark runner use this same class, so the
two scrapers follow exactly the same rules (benchmark rule B).
"""
from urllib.parse import parse_qs, urlsplit

from protego import Protego


class RobotsPolicy:
    def __init__(self, robots_text, user_agent, blocked_query_keys=()):
        self.user_agent = user_agent
        self.blocked_query_keys = set(blocked_query_keys)
        self._rules = Protego.parse(robots_text)  # parsed once, then reused

    def crawl_delay(self):
        """Seconds robots.txt asks us to wait, or None."""
        return self._rules.crawl_delay(self.user_agent)

    def check(self, url):
        """Return (allowed, reason)."""
        parts = urlsplit(url)
        # Our own safety net: refuse these query keys even if robots.txt's wording misses them.
        bad_keys = self.blocked_query_keys & set(parse_qs(parts.query))
        if bad_keys:
            return False, f"query key {sorted(bad_keys)} is blocked"
        if not self._rules.can_fetch(url, self.user_agent):
            return False, "disallowed by robots.txt"
        return True, ""
