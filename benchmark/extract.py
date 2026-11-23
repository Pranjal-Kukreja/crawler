"""Main-content text, defined once and used for BOTH scrapers (benchmark/DECISION.md, Step 1).

Main-content text = the page's HTML with scripts, styles, navigation, header, footer, side bars and forms
removed, taken from <main> (else [role=main], else <article>, else <body>), whitespace collapsed. Text inside
collapsed panels (accordions, sliders) stays in: it is part of the page, and whether a scraper gets it is exactly
what the benchmark has to show. Words are lower-case letters/digits runs. The same functions run on the HTTP body and on the
browser's page source, so a difference in the numbers is a difference in what the page delivered.
"""
import re
from collections import Counter

from bs4 import BeautifulSoup

DROP = ["script", "style", "noscript", "template", "svg", "iframe", "nav", "header", "footer", "aside", "form",
        "button", "select"]
WORD = re.compile(r"[a-z0-9]+")


def main_text(html):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(DROP):
        tag.decompose()
    root = soup.select_one("main") or soup.select_one("[role=main]") or soup.select_one("article") or soup.body or soup
    return " ".join(root.get_text(" ", strip=True).split())


# The site's footer link list. The browser builds it after load and, on pages without a <main> element, it is not
# inside a <footer> tag, so the tag-based exclusion misses it. It is menu labels, not course, rules or faculty data,
# so it is excluded by name (DECISION.md, Amendment 1). Applied when the two scrapers' texts are compared.
SITE_FOOTER = re.compile(r"Home About Visit News Academics Admissions Students Campus Life Alumni Administration "
                         r"Research Departments Services & Amenities Innovation Hub Opportunities Miscellaneous Contact Us")


def strip_site_footer(text):
    return " ".join(SITE_FOOTER.sub(" ", text).split())


def words(text):
    return WORD.findall(text.lower())


def coverage(other_text, own_text):
    """Share of the other scraper's words (with repeats) that this scraper's text also has. 1.0 if the other has none."""
    other, own = Counter(words(other_text)), Counter(words(own_text))
    total = sum(other.values())
    return 1.0 if total == 0 else sum((other & own).values()) / total
