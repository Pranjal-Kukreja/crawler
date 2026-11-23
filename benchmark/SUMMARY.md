# Benchmark summary

| Metric | HTTP | Selenium |
| --- | --- | --- |
| Completeness: pages where it misses text (of 27) | 0 | 0 |
| Failed page loads (of 81) | 0 | 0 |
| Active seconds per page (median of 3 runs) | 0.347 | 0.693 |
|   range over the 3 runs | 0.341 to 0.352 | 0.629 to 0.727 |
| Bytes per page | 174,988 | 744,362 |
| Peak memory (MB) | 290 | 1,615 |
| Average CPU (% of one core) | 7.0 | 37.8 |
| Start-up seconds | 0.071 | 0.535 |
| Lines of code (runner file) | 58 | 134 |
| Setup steps | 1 | 3 |
| Requests per page to the site | 1 | 39 (median) |

## Decision rule applied (benchmark/DECISION.md, with Amendment 1: footer link list excluded)

- Step 1: tie. Neither scraper misses text on any page.
- Step 2: tie. Failed page loads HTTP 0, Selenium 0.
- Step 3: active seconds per page, ranges over 3 runs HTTP 0.341 to 0.352, Selenium 0.629 to 0.727. http is lower.

Official result: http (Step 3, cost per page).

## As first written, before Amendment 1 (kept on record)

- Step 1: HTTP misses text on 13 page(s), Selenium on none. Selenium preferred.

Result before the amendment: selenium (Step 1, completeness).
