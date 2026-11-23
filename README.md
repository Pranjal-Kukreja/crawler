# IIT Patna knowledge-base pipeline

The data-collection and knowledge-base layer for the IIT Patna **Personalised Learning Buddy** (Adobe problem statement).

- Buddy Zero, the assistant: https://github.com/ps-submision-pdev/main-submission
- Research principles and implementations: https://github.com/ps-submision-pdev/Research-principles-and-implementations

The buddy makes no web calls at runtime; it only calls the configured LLM provider. This pipeline runs before it. This repository holds the **process**: the code, its tests and the benchmark. The collected data is not included (see [Data](#data)).

## What was done

- Crawled the 10 department sites on `www.iitp.ac.in`: 353 URLs seen, 246 pages accepted (`data/url_inventory.csv`).
- Downloaded and processed 51 PDFs from `academics.iitp.ac.in`: 43 syllabus PDFs (2,997 pages), plus the calendar, six ordinance and regulation PDFs and the revised curriculum PDF (`curated_pdfs/MANIFEST.csv`).
- Built the knowledge base from them. In our run it held 1,131 courses, 2,029 programme-course records, 156 rules, 198 elective-structure records, 68 minor-programme course records and 45 programme overviews, each with `source_url` and `fetched_at`.
- Benchmarked plain HTTP against Selenium on 27 pages (below).

## How it works

The fetcher is the only code that touches the network: allowlisted host only, robots.txt checked first, at least 1.5 s between requests, every response cached in `data/raw/`. PDFs are fetched only from URLs listed in `data/academics_*`, checked for a `%PDF` header and recorded in the manifest with their sha256. Parsers read the saved pages and PDFs, and `python -m src.build_kb` merges the results into `data/out/`. A value is left empty when the documents do not state it; when documents disagree (366 courses in our run) all versions are kept and flagged. `python -m src.validate` checks the output.

Gaps found while building it (see `docs/build_log.md`): the sources state no eligibility rules for minors, and the ordinances have no NPTEL/SWAYAM credit rules; Chemical Engineering has HTML syllabi only; rule extraction is keyword-based and can miss a rule.

## Benchmark: plain HTTP against Selenium

Does the pipeline need a real browser? `benchmark/DECISION.md` has the rule, `benchmark/CONCLUSION.md` the full write-up with every metric, and `benchmark/out/` the six raw runs the results are computed from.

**Setup.** 27 HTML pages, HTTP (httpx) against Selenium 4 with headless Chrome, same user-agent, robots check and 1.5 s delay, 3 runs each in alternating order. **Rule**, in order: completeness (the scraper that misses text on fewer pages wins), then fewer failed loads, then lower median active seconds per page, then tie-breaks on bytes, memory, CPU, start-up, lines of code and setup steps.

**Amendment 1.** The rule was written before any run. After the first run's numbers were seen, it was amended to exclude the site's footer link list from the compared text (the browser builds it after load; it is only menu labels). As first written, the rule gave Selenium at Step 1; with the amendment it gives HTTP at Step 3. Nothing was re-run: the figures were recomputed offline from the same 6 runs, and the first-written result is kept in `benchmark/decision.json` and `benchmark/SUMMARY.md`.

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

**Decision rule applied (benchmark/DECISION.md, with Amendment 1: footer link list excluded)**

- Step 1: tie. Neither scraper misses text on any page.
- Step 2: tie. Failed page loads HTTP 0, Selenium 0.
- Step 3: active seconds per page, ranges over 3 runs HTTP 0.341 to 0.352, Selenium 0.629 to 0.727. http is lower.

Official result: http (Step 3, cost per page).

**As first written, before Amendment 1 (kept on record)**

- Step 1: HTTP misses text on 13 page(s), Selenium on none. Selenium preferred.

Result before the amendment: selenium (Step 1, completeness).

**Limits** (from `benchmark/CONCLUSION.md`)

- One site, 27 pages, one machine, one day. About 12 of the pages are 3.4 MB each, which dominate the HTTP times.
- HTTP bytes are body bytes on the wire plus header bytes; Selenium bytes are the browser's `transferSize` totals. They are close in kind, not identical.
- Average CPU and peak memory are sampled over the whole run, including the delays, and include the Python process that runs the harness.
- Selenium's text is the DOM after the page has loaded; HTTP's is the raw HTML. The comparison shows what each delivers, not what a person sees.

In short: one site, 27 HTML pages, one machine, one day; HTML only, PDFs were not compared.

## Tests

```bash
pip install -r requirements.txt
python -m pytest        # 92 tests, none reaches the network
```

## Reproduce the crawl

Everything below sends real requests to `iitp.ac.in` and `academics.iitp.ac.in` (about 250 pages and 51 PDFs, 1.5 s apart), so use it politely.

```bash
cp config.local.yaml.example config.local.yaml   # put your own contact email in it (git-ignored)
python -m src.crawler                            # fetches the pages into data/raw/
python -m src.syllabus_pdfs list                 # then head, download, manifest
python -m src.department_overview                # the parsers read the saved pages and PDFs
python -m src.syllabus_html
python -m src.rules_extract
python -m src.minors_extract
python -m src.elective_structure
python -m src.build_kb && python -m src.validate # writes and checks data/out/
```

The benchmark results can be recomputed from the stored runs without touching the site: `python -m benchmark.compare`.

## Data

All of it comes from public IIT Patna pages, and it is **not** in this repository: the PDFs, the cached pages (`data/raw/`), the text extracted from the PDFs (`data/pdf_lines/`, `data/pdf_blocks/`) and the knowledge base (`data/out/`) are git-ignored and are rebuilt by the commands above. Kept here: the URL lists, `curated_pdfs/MANIFEST.csv` (url and sha256 of every PDF, so the files can be re-downloaded and checked), the crawl inventory and logs, and the benchmark runs and results.

## Repository history

Developed locally in November 2026 (`docs/build_log.md`, one dated entry: 9 November 2026). Published to GitHub on 24 November 2026 as a sequence of commits grouped by step; the commit dates are the publication date, not the original timeline.
