# Benchmark conclusion

Written from `results.csv`, `pages.csv`, `SUMMARY.md` and the rule in `DECISION.md`. Run on 27 HTML pages, 3 runs of each scraper, one after another, on one machine on one day. 0 failed loads and 0 robots refusals on either side.

## Result

**HTTP, decided at Step 3 (cost per page), under the rule with Amendment 1.** Step 1 is a tie: neither scraper misses text on any of the 27 pages (word coverage is 1.00 in both directions everywhere). Step 2 is a tie: 0 failed loads each. At Step 3 HTTP is lower: median active seconds per page 0.347 (range over the runs 0.341 to 0.352) against 0.693 (0.629 to 0.727); the ranges do not overlap.

## How the rule was amended, and what it said before

As first written, the rule gave **Selenium, at Step 1**: HTTP missed text on 13 pages, the 10 department `/courses` pages, the CSE and Mechanical faculty lists and the CSE directory (coverage 0.79 to 0.97). Inspected by hand, the only difference on all 13 pages, in all 3 runs, was one identical 182-character passage: the site's footer link list ("Home About Visit News ... Contact Us").

- The browser builds that list after the page loads; words such as "Innovation Hub" and "Amenities" are not in the raw HTML.
- On these 13 pages there is no `<main>` element, so the extractor falls back to the whole body, and the list is not wrapped in a `<footer>` tag. The 14 other pages (10 department main pages, both Chemical syllabus pages, Downloads, the calendar) have a `<main>` and were identical in both scrapers.
- No course, programme, faculty or directory text differed, and neither did titles, headings or links. The Chemical B.Tech syllabus page (84 collapse/expand elements) is identical in both: its collapsed text is already in the raw HTML. So did the CSE faculty page, the stress test.

The user approved excluding that list because it is menu labels and `docs/PS.md` needs course, rules and resource data. This was decided after the numbers were seen (DECISION.md, Amendment 1). Nothing was re-run: every figure is recomputed offline from the stored texts of the same 6 runs. The first-written result stays in `decision.json` and `SUMMARY.md`.

## Every metric (medians of 3 runs)

| Metric | HTTP | Selenium | Better |
| --- | --- | --- | --- |
| Pages where it misses text (of 27) | 0 | 0 | tie (13 vs 0 before Amendment 1, footer list only) |
| Failed page loads (of 81) | 0 | 0 | tie |
| Fields that differ (title, headings, links) | 0 pages | 0 pages | tie |
| Active seconds per page | 0.347 | 0.693 | HTTP (about 2.0 times lower) |
| Bytes per page | 174,988 | 744,362 | HTTP (about 4.3 times lower) |
| Peak memory (MB) | 290 | 1,615 | HTTP (about 5.6 times lower) |
| Average CPU (% of one core) | 7.0 | 37.8 | HTTP (about 5.4 times lower) |
| Start-up seconds | 0.071 | 0.535 | HTTP (about 7.5 times lower) |
| Lines of code in the runner | 58 | 134 | HTTP |
| Setup steps | 1 | 3 | HTTP |
| Requests per page to the site | 1 | 39 | HTTP |

Per-page active seconds are in `pages.csv` and `active_seconds_per_page.png`: Selenium is slower on every one of the 27 pages, by a small margin on some course pages and by about three times on the Downloads page.

## Live-site notes

- The browser made 39 requests per page (median; 83 on the first department page): scripts, styles and fonts, plus about 767 requests per run that my image and robots patterns blocked (mostly images). Third-party hosts seen: Google Translate and Google Fonts.
- It attempted 14 requests over the 3 runs to `/search?_rsc=...` (a Next.js link prefetch), which `robots.txt` disallows. A test on a non-resolving host showed that this block pattern stops such requests in the browser, and likewise `/api/` and `?page=`; I did not observe those 14 live requests being blocked directly.
- No 403 or 429 answers. Wall time per run was 47 s (HTTP) and 51 s (Selenium), mostly the 1.5 s delay.

## Limits

- One site, 27 pages, one machine, one day. About 12 of the pages are 3.4 MB each, which dominate the HTTP times.
- HTTP bytes are body bytes on the wire plus header bytes; Selenium bytes are the browser's `transferSize` totals. They are close in kind, not identical.
- Average CPU and peak memory are sampled over the whole run, including the delays, and include the Python process that runs the harness.
- Selenium's text is the DOM after the page has loaded; HTTP's is the raw HTML. The comparison shows what each delivers, not what a person sees.

## What this does not decide

Per rule G, nothing was added to the pipeline. The result concerns HTML pages only; PDF extraction was not compared. It says nothing about pages that need real interaction (logins, forms, content loaded after a click), because none of the 27 pages needed it.
