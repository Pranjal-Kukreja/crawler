"""Completeness, the decision rule and the result tables (DECISION.md, Steps 1 to 3 and the tie-breaks).

    python -m benchmark.compare            # reads benchmark/out/*.json, writes results.csv, pages.csv,
                                           # inspect.md and decision.json

Nothing here decides by feel: decide() applies the order written in DECISION.md to the numbers.
"""
import csv
import json
import re
import statistics
from collections import Counter
from pathlib import Path

from benchmark.common import BENCH, OUT, SETUP_STEPS, count_loc, load_urls
from benchmark.extract import coverage, strip_site_footer, words

THRESHOLD = 0.98          # DECISION.md, Step 1
MARGIN = 0.10             # DECISION.md, tie-breaks
SCRAPERS = ("http", "selenium")
RUNNER_FILES = {"http": BENCH / "http_runner.py", "selenium": BENCH / "selenium_runner.py"}


def med(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def load_runs():
    runs = {}
    for s in SCRAPERS:
        runs[s] = [json.loads(p.read_text()) for p in sorted(OUT.glob(f"{s}_run*.json"))]
    return runs


def pages_by_url(runs):
    """{scraper: {url: [page record per run]}}; refused pages are left out (they are not failures)."""
    return {s: {u: [p for r in rs for p in r["pages"] if p["url"] == u and not p.get("refused")]
                for u in {p["url"] for r in rs for p in r["pages"]}} for s, rs in runs.items()}


def text_of(records, i, clean=lambda t: t):
    return clean(records[i]["main_text"]) if i < len(records) else ""


def page_completeness(by_url, urls, clean=lambda t: t):
    """Per page: median over the runs of the word coverage in each direction, and which fields differ."""
    out = {}
    for url in urls:
        h, s = by_url["http"].get(url, []), by_url["selenium"].get(url, [])
        n = max(len(h), len(s))
        s_in_h = [coverage(text_of(s, i, clean), text_of(h, i, clean)) for i in range(n)]      # S's words found by H
        h_in_s = [coverage(text_of(h, i, clean), text_of(s, i, clean)) for i in range(n)]
        differ = Counter()
        for i in range(min(len(h), len(s))):
            if h[i]["title"] != s[i]["title"]:
                differ["title"] += 1
            if h[i]["headings"] != s[i]["headings"]:
                differ["headings"] += 1
            if h[i]["links"] != s[i]["links"]:
                differ["links"] += 1
        out[url] = {"cov_selenium_in_http": med(s_in_h), "cov_http_in_selenium": med(h_in_s),
                    "fields_differ": sorted(f for f, c in differ.items() if c >= 2)}
    return out


def run_metrics(runs):
    """{metric: {scraper: [value per run]}} for the metrics measured once per run."""
    m = {}

    def add(name, scraper, values):
        m.setdefault(name, {})[scraper] = values

    for s, rs in runs.items():
        ok = lambda r: [p for p in r["pages"] if not p.get("refused")]
        add("startup_seconds", s, [r["startup_seconds"] for r in rs])
        add("active_seconds_per_page", s, [med([p["active_seconds"] for p in ok(r)]) for r in rs])
        add("bytes_per_page", s, [med([p["bytes"] for p in ok(r)]) for r in rs])
        add("peak_memory_mb", s, [r["peak_rss_mb"] for r in rs])
        add("avg_cpu_percent", s, [r["avg_cpu_percent"] for r in rs])
        add("failed_pages", s, [sum(1 for p in ok(r) if p.get("failed")) for r in rs])
        add("pages_loaded", s, [len(ok(r)) for r in rs])
        add("refused_by_robots", s, [sum(1 for p in r["pages"] if p.get("refused")) for r in rs])
        add("wall_seconds", s, [r["wall_seconds"] for r in rs])
        add("extract_seconds_per_page", s, [med([p["extract_seconds"] for p in ok(r)]) for r in rs])
        add("robots_requests", s, [r["robots_requests"] for r in rs])
    sel = runs.get("selenium", [])
    if sel:
        add("subrequests_per_page", "selenium", [med([p["subrequests"]["count"] for p in r["pages"] if "subrequests" in p]) for r in sel])
        add("blocked_subrequests", "selenium", [sum(p["subrequests"]["blocked"] for p in r["pages"] if "subrequests" in p) for r in sel])
        add("subrequests_robots_would_refuse", "selenium", [sum(len(p["subrequests"]["robots_refused"]) for p in r["pages"] if "subrequests" in p) for r in sel])
        add("bytes_per_page_cdp", "selenium", [med([p["bytes_cdp"] for p in r["pages"] if "bytes_cdp" in p]) for r in sel])
    return m


def overlap(a, b):
    return min(a) <= max(b) and min(b) <= max(a)


def differs(a, b):
    """True when a and b differ by more than MARGIN of the larger one."""
    big = max(abs(a), abs(b))
    return big > 0 and abs(a - b) / big > MARGIN


def decide(miss, failed, active, tiebreak, loc, setup):
    """Apply DECISION.md in order. Returns {"winner": scraper|None, "decided_at": str, "trace": [str]}.
    miss: {scraper: [urls where it misses text]}; failed: {scraper: total failed}; active: {scraper: [per-run medians]};
    tiebreak: ordered [(name, {scraper: median})]; loc/setup: {scraper: int}."""
    h, s = "http", "selenium"
    trace = []
    # Step 1
    mh, ms = miss[h], miss[s]
    if mh and not ms:
        trace.append(f"Step 1: HTTP misses text on {len(mh)} page(s), Selenium on none. Selenium preferred.")
        return {"winner": s, "decided_at": "Step 1, completeness", "trace": trace}
    if ms and not mh:
        trace.append(f"Step 1: Selenium misses text on {len(ms)} page(s), HTTP on none. HTTP preferred.")
        return {"winner": h, "decided_at": "Step 1, completeness", "trace": trace}
    if mh and ms:
        trace.append(f"Step 1: mixed. HTTP misses text on {len(mh)} page(s) and Selenium on {len(ms)}. No preference.")
    else:
        trace.append("Step 1: tie. Neither scraper misses text on any page.")
    # Step 2
    if failed[h] != failed[s]:
        win = h if failed[h] < failed[s] else s
        trace.append(f"Step 2: failed page loads HTTP {failed[h]}, Selenium {failed[s]}. {win} has fewer.")
        return {"winner": win, "decided_at": "Step 2, failed pages", "trace": trace}
    trace.append(f"Step 2: tie. Failed page loads HTTP {failed[h]}, Selenium {failed[s]}.")
    # Step 3
    if not overlap(active[h], active[s]):
        win = h if max(active[h]) < min(active[s]) else s
        trace.append(f"Step 3: active seconds per page, ranges over 3 runs HTTP {min(active[h]):.3f} to {max(active[h]):.3f}, "
                     f"Selenium {min(active[s]):.3f} to {max(active[s]):.3f}. {win} is lower.")
        return {"winner": win, "decided_at": "Step 3, cost per page", "trace": trace}
    trace.append(f"Step 3: tie. Active seconds per page, ranges over 3 runs HTTP {min(active[h]):.3f} to {max(active[h]):.3f}, "
                 f"Selenium {min(active[s]):.3f} to {max(active[s]):.3f}; they overlap.")
    # Tie-breaks
    for name, v in tiebreak:
        if differs(v[h], v[s]):
            win = h if v[h] < v[s] else s
            trace.append(f"Tie-break {name}: HTTP {v[h]:.4g}, Selenium {v[s]:.4g}. {win} is lower by more than 10%.")
            return {"winner": win, "decided_at": f"tie-break, {name}", "trace": trace}
        trace.append(f"Tie-break {name}: HTTP {v[h]:.4g}, Selenium {v[s]:.4g}. Within 10%, tied.")
    for name, v in (("lines of code", loc), ("setup steps", setup)):
        if v[h] != v[s]:
            win = h if v[h] < v[s] else s
            trace.append(f"Tie-break {name}: HTTP {v[h]}, Selenium {v[s]}. {win} is lower.")
            return {"winner": win, "decided_at": f"tie-break, {name}", "trace": trace}
        trace.append(f"Tie-break {name}: HTTP {v[h]}, Selenium {v[s]}. Tied.")
    trace.append("Every metric is tied: no difference found.")
    return {"winner": None, "decided_at": "no difference found", "trace": trace}


def missing_spans(other_text, own_text, min_words=5, gap=3):
    """Runs of the other scraper's words that this scraper's text does not have, longest first (for inspecting by hand)."""
    own = Counter(words(own_text))
    flags = []
    for w in words(other_text):
        if own[w] > 0:
            own[w] -= 1
            flags.append(False)
        else:
            flags.append(True)
    toks, spans, start, last = words(other_text), [], None, None
    for i, miss in enumerate(flags):
        if miss:
            if start is None:
                start = i
            last = i
        elif start is not None and i - last > gap:
            spans.append((start, last))
            start = None
    if start is not None:
        spans.append((start, last))
    spans = [(a, b) for a, b in spans if b - a + 1 >= min_words]
    return sorted((" ".join(toks[a:b + 1]) for a, b in spans), key=len, reverse=True)


def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def main():
    runs = load_runs()
    if any(len(runs[s]) != 3 for s in SCRAPERS):
        raise SystemExit(f"need 3 runs of each scraper, found { {s: len(r) for s, r in runs.items()} }")
    entries = load_urls()
    urls = [u for u, _ in entries]
    groups = dict(entries)
    by_url = pages_by_url(runs)
    comp = page_completeness(by_url, urls, strip_site_footer)          # official: footer list excluded (Amendment 1)
    comp_before = page_completeness(by_url, urls)                      # as first written, kept on record
    metrics = run_metrics(runs)

    def misses(c):
        return {"http": [u for u in urls if c[u]["cov_selenium_in_http"] is not None and c[u]["cov_selenium_in_http"] < THRESHOLD],
                "selenium": [u for u in urls if c[u]["cov_http_in_selenium"] is not None and c[u]["cov_http_in_selenium"] < THRESHOLD]}

    miss, miss_before = misses(comp), misses(comp_before)
    loc = {s: count_loc(RUNNER_FILES[s]) for s in SCRAPERS}
    setup = {s: len(SETUP_STEPS[s]) for s in SCRAPERS}
    total = lambda name: {s: sum(metrics[name][s]) for s in SCRAPERS}
    mid = lambda name: {s: med(metrics[name][s]) for s in SCRAPERS}
    tiebreak = [("bytes per page", mid("bytes_per_page")), ("peak memory (MB)", mid("peak_memory_mb")),
                ("average CPU (%)", mid("avg_cpu_percent")), ("start-up seconds", mid("startup_seconds"))]
    decision = decide(miss, total("failed_pages"), metrics["active_seconds_per_page"], tiebreak, loc, setup)
    decision["pages_where_http_misses_text"] = miss["http"]
    decision["pages_where_selenium_misses_text"] = miss["selenium"]
    before = decide(miss_before, total("failed_pages"), metrics["active_seconds_per_page"], tiebreak, loc, setup)
    before["pages_where_http_misses_text"] = miss_before["http"]
    before["pages_where_selenium_misses_text"] = miss_before["selenium"]
    decision["as_first_written_before_amendment_1"] = before
    (BENCH / "decision.json").write_text(json.dumps(decision, indent=1))

    # results.csv: every metric of rule E, one row per metric and scraper
    rows = []
    units = {"startup_seconds": "s", "active_seconds_per_page": "s", "bytes_per_page": "bytes", "bytes_per_page_cdp": "bytes",
             "peak_memory_mb": "MB", "avg_cpu_percent": "% of one core", "failed_pages": "pages per run",
             "pages_loaded": "pages per run", "refused_by_robots": "pages per run", "wall_seconds": "s",
             "extract_seconds_per_page": "s", "robots_requests": "requests per run", "subrequests_per_page": "requests",
             "blocked_subrequests": "requests per run", "subrequests_robots_would_refuse": "requests per run"}
    for name, per in metrics.items():
        for s, vals in per.items():
            rows.append([name, units.get(name, ""), s, *[("" if v is None else round(v, 4)) for v in vals],
                         round(med(vals), 4), round(sum(vals), 4) if name in ("failed_pages", "blocked_subrequests", "subrequests_robots_would_refuse") else ""])
    for s, other in (("http", "selenium"), ("selenium", "http")):
        key = "cov_selenium_in_http" if s == "http" else "cov_http_in_selenium"
        covs = [comp[u][key] for u in urls if comp[u][key] is not None]
        rows.append(["pages_where_scraper_misses_text", "pages of %d" % len(urls), s, "", "", "", len(miss[s]), ""])
        rows.append(["mean_word_coverage_of_other_scraper", "share", s, "", "", "", round(statistics.mean(covs), 4), ""])
        rows.append(["min_word_coverage_of_other_scraper", "share", s, "", "", "", round(min(covs), 4), ""])
    differing = Counter(f for u in urls for f in comp[u]["fields_differ"])
    rows.append(["pages_with_differing_fields", "pages", "both", "", "", "", sum(1 for u in urls if comp[u]["fields_differ"]), ""])
    for f in ("title", "headings", "links"):
        rows.append([f"pages_where_{f}_differ", "pages", "both", "", "", "", differing.get(f, 0), ""])
    for s in SCRAPERS:
        rows.append(["lines_of_code", "lines", s, "", "", "", loc[s], ""])
        rows.append(["setup_steps", "steps", s, "", "", "", setup[s], ""])
    write_csv(BENCH / "results.csv", ["metric", "unit", "scraper", "run1", "run2", "run3", "median", "total"], rows)

    # pages.csv: one row per page
    prow = []
    for u in urls:
        h, s = by_url["http"].get(u, []), by_url["selenium"].get(u, [])
        pm = lambda recs, k: med([r[k] for r in recs if k in r])
        prow.append([groups[u], u, round(pm(h, "active_seconds") or 0, 4), round(pm(s, "active_seconds") or 0, 4),
                     pm(h, "bytes"), pm(s, "bytes"), pm(h, "text_chars"), pm(s, "text_chars"),
                     round(comp[u]["cov_selenium_in_http"], 4), round(comp[u]["cov_http_in_selenium"], 4),
                     "http" if u in miss["http"] else "", "selenium" if u in miss["selenium"] else "",
                     "|".join(comp[u]["fields_differ"]),
                     med([r["subrequests"]["count"] for r in s if "subrequests" in r])])
    write_csv(BENCH / "pages.csv", ["group", "url", "http_active_s", "selenium_active_s", "http_bytes", "selenium_bytes",
                                    "http_text_chars", "selenium_text_chars", "coverage_of_selenium_text_in_http",
                                    "coverage_of_http_text_in_selenium", "http_misses_text", "selenium_misses_text",
                                    "fields_differ", "selenium_subrequests"], prow)

    # inspect.md: every page under the threshold, with the text that is missing, for reading by hand
    lines = [f"# Pages under the {THRESHOLD} word-coverage threshold, before the footer list was excluded\n",
             f"After Amendment 1 (the site footer link list is excluded) {len(miss['http']) + len(miss['selenium'])} pages are under the threshold. "
             "The pages below are those flagged before it, kept for the record.\n"]
    flagged = [(u, "http") for u in miss_before["http"]] + [(u, "selenium") for u in miss_before["selenium"]]
    if not flagged:
        lines.append("None. Every page is at or above the threshold in both directions.\n")
    for u, who in flagged:
        h, s = by_url["http"][u], by_url["selenium"][u]
        other, own = (s, h) if who == "http" else (h, s)
        spans = missing_spans(text_of(other, 0), text_of(own, 0))
        key = "cov_selenium_in_http" if who == "http" else "cov_http_in_selenium"
        lines.append(f"## {who} misses text: {u}\n\ncoverage {comp_before[u][key]:.4f} (median of 3 runs); {len(spans)} missing passage(s) of 5 or more words in run 1:\n")
        for sp in spans[:8]:
            lines.append(f"- {sp[:400]}")
        lines.append("")
    (BENCH / "inspect.md").write_text("\n".join(lines))
    def cell(name, s_, fmt="{:.3f}"):
        return fmt.format(med(metrics[name][s_])) if name in metrics and s_ in metrics[name] else "n/a"

    table = [
        ("Completeness: pages where it misses text (of 27)", str(len(miss["http"])), str(len(miss["selenium"]))),
        ("Failed page loads (of 81)", str(int(sum(metrics["failed_pages"]["http"]))), str(int(sum(metrics["failed_pages"]["selenium"])))),
        ("Active seconds per page (median of 3 runs)", cell("active_seconds_per_page", "http"), cell("active_seconds_per_page", "selenium")),
        ("  range over the 3 runs", "%.3f to %.3f" % (min(metrics["active_seconds_per_page"]["http"]), max(metrics["active_seconds_per_page"]["http"])),
         "%.3f to %.3f" % (min(metrics["active_seconds_per_page"]["selenium"]), max(metrics["active_seconds_per_page"]["selenium"]))),
        ("Bytes per page", cell("bytes_per_page", "http", "{:,.0f}"), cell("bytes_per_page", "selenium", "{:,.0f}")),
        ("Peak memory (MB)", cell("peak_memory_mb", "http", "{:,.0f}"), cell("peak_memory_mb", "selenium", "{:,.0f}")),
        ("Average CPU (% of one core)", cell("avg_cpu_percent", "http", "{:.1f}"), cell("avg_cpu_percent", "selenium", "{:.1f}")),
        ("Start-up seconds", cell("startup_seconds", "http"), cell("startup_seconds", "selenium")),
        ("Lines of code (runner file)", str(loc["http"]), str(loc["selenium"])),
        ("Setup steps", str(setup["http"]), str(setup["selenium"])),
        ("Requests per page to the site", "1", cell("subrequests_per_page", "selenium", "{:.0f}") + " (median)"),
    ]
    md = ["# Benchmark summary\n", "| Metric | HTTP | Selenium |", "| --- | --- | --- |"]
    md += [f"| {a} | {b} | {c} |" for a, b, c in table]
    md += ["", "## Decision rule applied (benchmark/DECISION.md, with Amendment 1: footer link list excluded)", ""]
    md += [f"- {t}" for t in decision["trace"]]
    md += ["", f"Official result: {decision['winner'] or 'no difference found'} ({decision['decided_at']}).", "",
           "## As first written, before Amendment 1 (kept on record)", ""]
    md += [f"- {t}" for t in before["trace"]]
    md += ["", f"Result before the amendment: {before['winner'] or 'no difference found'} ({before['decided_at']}).", ""]
    (BENCH / "SUMMARY.md").write_text("\n".join(md))
    print(json.dumps(decision, indent=1))
    print(f"wrote results.csv, pages.csv, inspect.md, decision.json in {BENCH}")


if __name__ == "__main__":
    main()
