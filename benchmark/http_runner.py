"""Scraper H: the HTTP side of the benchmark. One run over benchmark/urls.txt.

    python -m benchmark.http_runner --run 1

Active time = from sending the request to having the whole body. The robots check and the delay are outside it.
It does not read data/raw/: it uses its own httpx client, not the pipeline's cache.
"""
import argparse
import time

import httpx

from benchmark.common import (STOP_AFTER_BLOCKS, TIMEOUT, Pacer, Sampler, config, crawl_delay,
                              failure_reason, fetch_robots, host_of, load_urls, page_fields, write_run)


def header_bytes(resp):
    return sum(len(k) + len(v) + 4 for k, v in resp.headers.raw) + 15       # header lines plus the status line


def run(run_number):
    cfg, user_agent, delay = config()
    urls = load_urls()
    sampler = Sampler()
    sampler.start()
    wall = time.perf_counter()

    t0 = time.perf_counter()
    client = httpx.Client(headers={"User-Agent": user_agent}, timeout=TIMEOUT, follow_redirects=True)
    startup = time.perf_counter() - t0

    pacer = Pacer(delay)
    hosts = list(dict.fromkeys(host_of(u) for u, _ in urls))
    policies, _, robots_requests = fetch_robots(hosts, user_agent, pacer, cfg["blocked_query_keys"])
    pages, blocks, stopped = [], 0, ""
    for url, group in urls:
        host = host_of(url)
        record = {"scraper": "http", "run": run_number, "url": url, "group": group, "refused": False}
        allowed, why = policies[host].check(url)
        if not allowed:
            pages.append({**record, "refused": True, "failure_reason": why})
            continue
        record["slept_seconds"] = pacer.wait(host, crawl_delay(policies[host], delay))
        status, body, error, nbytes = 0, "", "", 0
        t0 = time.perf_counter()
        try:
            resp = client.get(url)
            active = time.perf_counter() - t0
            status, body, nbytes = resp.status_code, resp.text, resp.num_bytes_downloaded + header_bytes(resp)
        except httpx.TimeoutException:
            active, error = time.perf_counter() - t0, "timeout"
        except httpx.HTTPError as e:
            active, error = time.perf_counter() - t0, f"error: {type(e).__name__}"
        pacer.mark(host)
        fields = page_fields(body) if body else {"main_text": "", "text_chars": 0, "title": "", "headings": [],
                                                 "links": [], "extract_seconds": 0.0}
        reason = failure_reason(status, fields["text_chars"], error)
        pages.append({**record, "status": status, "failed": bool(reason), "failure_reason": reason,
                      "active_seconds": active, "bytes": nbytes, **fields})
        blocks = blocks + 1 if status in (403, 429) else 0
        if blocks >= STOP_AFTER_BLOCKS:
            stopped = f"{blocks} blocks (403/429) in a row"
            break
    client.close()
    result = sampler.result()
    return write_run("http", run_number, {
        "scraper": "http", "run": run_number, "startup_seconds": startup, "robots_requests": robots_requests,
        "wall_seconds": time.perf_counter() - wall, "stopped": stopped, "pages": pages, **result})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, required=True)
    path = run(ap.parse_args().run)
    print("wrote", path)
