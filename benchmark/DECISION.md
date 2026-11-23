# Benchmark decision rule

Written before any benchmark run. Nothing has been run on the live site. Points 1 to 4 below were agreed with the user; the URL list (`benchmark/urls.proposed.txt`) still waits for the user's OK.

## Scope

- HTML pages only. PDF extraction is not compared; it is not a like-for-like test.
- 27 pages (about 30): department and course/programme pages, two HTML syllabus pages, two academics pages, three faculty or directory pages.
- Pages the user listed but that have under 200 characters of main text were swapped out before the run (`/revised_curriculum/` 125, `/revised_syllabus/` 102, Disciplinary Ordinance article 111 characters).
- Allowed on the academics host for the benchmark: only the four listed academics URLs (two syllabus pages, Downloads id=78, calendar id=59). Same fetch layer, delay and robots rules. No other academics URL is requested.

## What is compared

- Scraper H: our HTTP pipeline (httpx, connection reuse, 20 s timeout).
- Scraper S: Selenium 4, headless Chrome, one browser session per run, eager page-load strategy, `WebDriverWait` (no fixed sleeps), images and media blocked.
- The same 30 pages (`benchmark/urls.txt`), the same user-agent, the same robots check (`src/robots_policy.py`) before every request or `driver.get()`, the same 1.5 s delay between requests.
- 3 runs each, a fresh process and a fresh browser per run. H does not read `data/raw/`.
- Selenium stays in `benchmark/`. If it wins on some pages, that is reported to you; it is not added to the pipeline.

## What "better" means, in this order

**Step 1, completeness (the first thing that matters).** Prefer the scraper that extracts all the text the other extracts.
- Text of a page = main-content text, taken from each scraper's final HTML with the same function (`benchmark/extract.py`): scripts, styles, navigation, header, footer, side bars and forms removed, whitespace collapsed, same normalisation for both. Text inside collapsed panels stays in, because it is part of the page.
- Every page whose coverage falls under the threshold is inspected by hand and shown to the user.
- `coverage(Y in X)` = the share of Y's words (counted with repeats) that also appear in X's text. A run's number is computed per page; a page's number is the median of its 3 runs.
- X **misses text** on a page when `coverage(other in X) < 0.98` (agreed). The 2% slack covers things like dates or counters that change between loads.
- Scraper A is preferred at Step 1 if A misses text on no page and B misses text on at least one page.
- If neither misses text, Step 1 is a tie. If each misses text on some page, Step 1 is "mixed": no preference, we go on to Step 2, and the report lists every page where each side loses text.
- A page that a scraper fails to load in all 3 runs counts as text missed by that scraper.

**Step 2, fewer failed pages.** Count failed page loads out of 81 (27 pages x 3 runs) for each scraper. Fewer wins; equal counts (including 0 and 0) is a tie. A load fails when it raises an error, times out (20 s), returns HTTP 400 or higher, or yields fewer than 200 characters of text (agreed; a page that legitimately has less is swapped out before the run, not counted as a failure). A page refused by robots.txt is not a failure and is removed from both lists before the run.

**Step 3, lower cost per page.** Cost per page = median active seconds per page (below). Per run take the median over the 30 pages; then take the median of the 3 runs. Lower wins, unless the two scrapers' min-to-max ranges over the 3 runs overlap, which is a tie (the difference is inside run-to-run noise).

## How ties are broken

If Step 3 is a tie, go down this list and stop at the first metric with a clear difference. For metrics 3 to 6 a difference counts only if the medians differ by more than 10% of the larger one (agreed).

1. Bytes downloaded per page (lower wins)
2. Peak memory (lower wins)
3. Average CPU (lower wins)
4. Start-up time (lower wins)
5. Lines of code (lower wins; exact count)
6. Setup steps (fewer wins; exact count)

If every metric is tied, the result is "no difference found". The pipeline stays as it is, because nothing in the numbers asks for a change. No tie is settled by preference.

## How each metric is measured

| Metric | H (HTTP) | S (Selenium) |
| --- | --- | --- |
| Active seconds per page | from sending the request to having the full body, excluding the 1.5 s sleep and the robots check | from `driver.get()` until `body` is present and `page_source` is read, excluding the sleep and the robots check |
| Start-up time | creating the HTTP client | launching headless Chrome until the driver is ready |
| Bytes per page | bytes on the wire for the body plus the header bytes | sum of `transferSize` from the browser's navigation and resource timing for that page |
| Peak memory, average CPU | `psutil`, sampled every 0.2 s over the runner's process | same, summed over Python, chromedriver and every Chrome child process |
| Completeness | Step 1 above, plus which fields differ (title, headings, text, link set) | same |
| Failed pages | Step 2 above | same |
| Lines of code, setup steps | non-blank, non-comment lines of the runner file; setup steps counted from the install instructions | same |

Text extraction time is the same function for both, is recorded separately and is not part of active time.

## Rules for the live site

- At most these 27 pages. Each scraper loads each page 3 times, so 81 page loads each, plus one `robots.txt` per host per run.
- S's browser also asks for scripts and styles, which H does not. To keep it inside robots.txt, the browser blocks every URL pattern that robots.txt disallows (`/api/`, `/.next/`, `/admin/`, `/dev/`, `/private/`, `/search?`) and the runner counts each blocked request. If a page needs one of those to show its text, that shows up as missing text in Step 1, and we report it.
- The runner logs every sub-request the browser makes. After each run, any logged URL that robots.txt would refuse is listed in the report.
- Both runners stop at once after 5 consecutive 403 or 429 answers (the pipeline's rule).
- Four pages are on `academics.iitp.ac.in`. They are allowed only because they are on our URL allowlist; no other URL on that host is requested.
- Several pages (the 10 department main pages and 2 faculty lists) are about 3.4 MB of HTML each, so the load on the institute's server is mostly those: 12 pages x 3 runs x 2 scrapers = 72 large loads.

## What will be reported

- Every metric, including the ones where S wins or ties, in the same table, and all of them in `results.csv` whether or not they decide anything.
- Any page where S finds text that H misses, shown to you with the missing text.
- A conclusion written only from the numbers and the rule above. No word such as "slow" or "brittle" unless a metric in the table shows it.

## Agreed points

1. Coverage threshold 0.98, on main-content text, same normalisation for both; pages under it are inspected by hand.
2. A page needs at least 200 characters of text. Fixed.
3. 10% margin for the tie-break metrics.
4. Active seconds alone decides the cost step. Bytes, memory and CPU are tie-breaks only.

## Amendment 1 (made after the first run, with the user's approval)

- **What changed:** the site's footer link list ("Home About Visit News Academics Admissions Students Campus Life Alumni Administration Research Departments Services & Amenities Innovation Hub Opportunities Miscellaneous Contact Us") is excluded from the text that is compared. `benchmark/extract.py` does it by name (`strip_site_footer`) when the two texts are compared.
- **Why:** the first run found that HTTP "missed" this passage on 13 pages. The browser builds it after the page loads, and on pages without a `<main>` element it is not inside a `<footer>` tag, so the tag-based exclusion did not remove it. It is menu labels. `docs/PS.md` asks for the course catalogue, academic rules and learning resources, and does not mention site navigation, so it carries nothing the problem needs.
- **When and how:** decided after the numbers were seen. No scraper was re-run; every figure is recomputed offline from the stored texts of the same 6 runs. The result as first written (Selenium, at Step 1) is kept in `decision.json` under `as_first_written_before_amendment_1` and in `SUMMARY.md`, and `inspect.md` still lists the 13 pages and the passage.
- Nothing else in this file changed.
