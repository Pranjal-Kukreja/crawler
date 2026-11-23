"""Tests for the benchmark pieces that need no network: page list, pacing, robots patterns, failure rule, decision rule."""
from benchmark.common import MIN_TEXT, Pacer, cdp_block_patterns, count_loc, failure_reason, load_urls
from benchmark.compare import decide, differs, missing_spans, overlap

UA = "IITP-KB-Student-Project (contact: x@y.z)"


def test_url_list_is_the_approved_27_with_groups():
    urls = load_urls()
    assert len(urls) == 27 and len({u for u, _ in urls}) == 27
    assert {g for _, g in urls} >= {"department main", "courses", "syllabus HTML", "academics", "faculty list", "directory"}
    academics = [u for u, _ in urls if "academics.iitp.ac.in" in u]
    assert len(academics) == 4          # two syllabus pages, Downloads, calendar: nothing else on that host
    assert not any(u.lower().endswith((".pdf", ".docx")) for u, _ in urls)


def test_pacer_waits_the_remaining_time_per_host_only():
    now, slept = [100.0], []
    p = Pacer(1.5, sleep=slept.append, clock=lambda: now[0])
    assert p.wait("a") == 0
    p.mark("a")
    now[0] += 0.5
    assert p.wait("a") == 1.0 and p.wait("b") == 0 and p.wait("a", delay=2.0) == 1.5


ROBOTS = """User-agent: *
Allow: /
Disallow: /api/
Disallow: /*?*page=
Disallow: /search?

User-agent: SemrushBot
Crawl-delay: 10
Disallow: /*.pdf$
"""


def test_browser_block_patterns_come_from_our_group_only():
    assert cdp_block_patterns(ROBOTS, UA) == ["*://*/api/*", "*://*/*?*page=*", "*://*/search?*"]


def test_failure_rule():
    assert failure_reason(200, MIN_TEXT) == "" and failure_reason(200, MIN_TEXT - 1).startswith("only")
    assert failure_reason(404, 5000) == "http 404" and failure_reason(0, 0, "timeout") == "timeout"


def test_loc_ignores_comments_blank_lines_and_docstrings(tmp_path):
    f = tmp_path / "x.py"
    f.write_text('"""doc\nstring"""\n\n# comment\nx = 1\ndef f():\n    """d"""\n    return x\n')
    assert count_loc(f) == 3


def test_overlap_and_margin():
    assert overlap([1, 2, 3], [3, 4]) and not overlap([1, 2], [3, 4])
    assert differs(1.0, 1.2) and not differs(1.0, 1.05)


BASE = dict(miss={"http": [], "selenium": []}, failed={"http": 0, "selenium": 0},
            active={"http": [0.5, 0.6, 0.55], "selenium": [0.5, 0.7, 0.6]},
            tiebreak=[("bytes", {"http": 100, "selenium": 100}), ("memory", {"http": 100, "selenium": 100})],
            loc={"http": 50, "selenium": 50}, setup={"http": 1, "selenium": 1})


def test_decision_completeness_first_even_if_the_slower_one_has_more_text():
    d = decide(**{**BASE, "miss": {"http": ["u1"], "selenium": []}, "active": {"http": [0.1] * 3, "selenium": [9.0] * 3}})
    assert d["winner"] == "selenium" and d["decided_at"].startswith("Step 1")


def test_decision_mixed_completeness_goes_on_to_failures_then_cost():
    d = decide(**{**BASE, "miss": {"http": ["a"], "selenium": ["b"]}, "failed": {"http": 2, "selenium": 0}})
    assert d["winner"] == "selenium" and d["decided_at"].startswith("Step 2")
    d = decide(**{**BASE, "active": {"http": [0.1, 0.12, 0.11], "selenium": [2.0, 2.2, 2.1]}})
    assert d["winner"] == "http" and d["decided_at"].startswith("Step 3")


def test_decision_ties_fall_through_to_the_tie_breaks_and_can_end_in_no_difference():
    d = decide(**{**BASE, "tiebreak": [("bytes", {"http": 100, "selenium": 300}), ("memory", {"http": 1, "selenium": 1})]})
    assert d["winner"] == "http" and "bytes" in d["decided_at"]
    d = decide(**BASE)
    assert d["winner"] is None and d["decided_at"] == "no difference found"


def test_missing_spans_show_what_the_other_scraper_lacks():
    other = "alpha beta gamma delta epsilon zeta eta theta fees are one thousand rupees per term iota"
    own = "alpha beta gamma delta epsilon zeta eta theta iota"
    assert missing_spans(other, own) == ["fees are one thousand rupees per term"]
