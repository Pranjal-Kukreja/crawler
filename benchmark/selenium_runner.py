"""Scraper S: the Selenium side of the benchmark. One run over benchmark/urls.txt.

    python -m benchmark.selenium_runner --run 1
    python -m benchmark.selenium_runner --selftest      # starts Chrome on a data: page, no network

Setup (rule C): Selenium 4, headless Chrome, one browser session for the whole run, eager page-load strategy,
WebDriverWait on document.readyState (no fixed sleeps), images and media blocked, the same user-agent.
Live-site protection: every URL pattern that robots.txt disallows is blocked in the browser, every request the
browser makes is logged, and afterwards each logged URL is checked against robots.txt with the pipeline's policy.
Active time = from driver.get() until the page source is in hand. The robots check and the delay are outside it.
"""
import argparse
import json
import time
from collections import Counter
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from benchmark.common import (STOP_AFTER_BLOCKS, TIMEOUT, Pacer, Sampler, cdp_block_patterns, config, crawl_delay,
                              failure_reason, fetch_robots, host_of, load_urls, page_fields, write_run)

MEDIA_PATTERNS = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg", "*.ico", "*.mp4", "*.webm", "*.mp3"]
TIMING_JS = """const nav = performance.getEntriesByType('navigation')[0];
const res = performance.getEntriesByType('resource');
return [nav ? nav.transferSize : 0, res.reduce((a, e) => a + e.transferSize, 0), res.length];"""


def build_driver(user_agent, block_patterns):
    opts = Options()
    opts.add_argument("--headless=new")
    opts.page_load_strategy = "eager"
    opts.add_argument(f"--user-agent={user_agent}")
    opts.add_argument("--window-size=1280,1024")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("--disable-background-networking")      # no update, safe-browsing or sync calls of Chrome's own
    opts.add_argument("--disable-extensions")
    opts.add_argument("--no-first-run")
    opts.add_argument("--mute-audio")
    opts.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2,
                                           "profile.managed_default_content_settings.media_stream": 2})
    opts.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    opts.add_experimental_option("perfLoggingPrefs", {"enableNetwork": True, "enablePage": False})
    driver = webdriver.Chrome(options=opts)                  # Selenium Manager finds or downloads chromedriver
    driver.set_page_load_timeout(TIMEOUT)
    driver.execute_cdp_cmd("Network.enable", {})
    driver.execute_cdp_cmd("Network.setBlockedURLs", {"urls": block_patterns + MEDIA_PATTERNS})
    return driver


def read_log(driver):
    """Drain Chrome's network log: requested URLs, blocked count, bytes on the wire, status of the page itself."""
    requests, blocked, wire, status = [], 0, 0, 0
    for entry in driver.get_log("performance"):
        msg = json.loads(entry["message"])["message"]
        method, params = msg.get("method"), msg.get("params", {})
        if method == "Network.requestWillBeSent":
            requests.append(params["request"]["url"])
        elif method == "Network.loadingFailed" and params.get("blockedReason"):
            blocked += 1
        elif method == "Network.loadingFinished":
            wire += params.get("encodedDataLength", 0)
        elif method == "Network.responseReceived" and params.get("type") == "Document":
            status = params["response"]["status"]
    return requests, blocked, wire, status


def run(run_number):
    cfg, user_agent, delay = config()
    urls = load_urls()
    sampler = Sampler()
    sampler.start()
    wall = time.perf_counter()
    pacer = Pacer(delay)
    hosts = list(dict.fromkeys(host_of(u) for u, _ in urls))
    policies, texts, robots_requests = fetch_robots(hosts, user_agent, pacer, cfg["blocked_query_keys"])
    patterns = sorted({p for text in texts.values() for p in cdp_block_patterns(text, user_agent)})

    t0 = time.perf_counter()
    driver = build_driver(user_agent, patterns)
    startup = time.perf_counter() - t0
    chrome = driver.capabilities.get("browserVersion", "")

    pages, blocks, stopped = [], 0, ""
    try:
        for url, group in urls:
            host = host_of(url)
            record = {"scraper": "selenium", "run": run_number, "url": url, "group": group, "refused": False}
            allowed, why = policies[host].check(url)
            if not allowed:
                pages.append({**record, "refused": True, "failure_reason": why})
                continue
            record["slept_seconds"] = pacer.wait(host, crawl_delay(policies[host], delay))
            driver.get_log("performance")                    # empty the log so it holds this page only
            html, error = "", ""
            t0 = time.perf_counter()
            try:
                driver.get(url)
                WebDriverWait(driver, TIMEOUT).until(
                    lambda d: d.execute_script("return document.readyState") == "complete")
                html = driver.page_source
            except TimeoutException:
                error = "timeout"
            except WebDriverException as e:
                error = f"error: {type(e).__name__}"
            active = time.perf_counter() - t0
            pacer.mark(host)
            requests, blocked, wire, status = read_log(driver)
            try:
                nav, resources, n_resources = driver.execute_script(TIMING_JS)
            except WebDriverException:
                nav = resources = n_resources = 0
            fields = page_fields(html) if html else {"main_text": "", "text_chars": 0, "title": "", "headings": [],
                                                     "links": [], "extract_seconds": 0.0}
            refused = [u for u in requests if urlsplit(u).scheme in ("http", "https") and urlsplit(u).netloc in policies
                       and not policies[urlsplit(u).netloc].check(u)[0]]
            reason = failure_reason(status, fields["text_chars"], error)
            pages.append({**record, "status": status, "failed": bool(reason), "failure_reason": reason,
                          "active_seconds": active, "bytes": nav + resources, "bytes_cdp": wire, **fields,
                          "subrequests": {"count": len(requests), "blocked": blocked, "resource_entries": n_resources,
                                          "by_host": dict(Counter(urlsplit(u).netloc for u in requests)),
                                          "robots_refused": refused, "urls": requests}})
            blocks = blocks + 1 if status in (403, 429) else 0
            if blocks >= STOP_AFTER_BLOCKS:
                stopped = f"{blocks} blocks (403/429) in a row"
                break
    finally:
        driver.quit()
    result = sampler.result()
    return write_run("selenium", run_number, {
        "scraper": "selenium", "run": run_number, "startup_seconds": startup, "robots_requests": robots_requests,
        "wall_seconds": time.perf_counter() - wall, "stopped": stopped, "chrome": chrome,
        "blocked_patterns": patterns, "pages": pages, **result})


def selftest():
    """Start the browser on a data: page (no network) and check the blocking and the log work."""
    cfg, user_agent, _ = config()
    patterns = cdp_block_patterns(open("robots.txt").read(), user_agent)
    t0 = time.perf_counter()
    driver = build_driver(user_agent, patterns)
    print("start-up seconds:", round(time.perf_counter() - t0, 2), "| chrome", driver.capabilities["browserVersion"],
          "| driver", driver.capabilities["chrome"]["chromedriverVersion"].split()[0])
    driver.get("data:text/html,<html><title>t</title><body><p>hello self test</p></body></html>")
    print("page source has text:", "hello self test" in driver.page_source, "| user agent:",
          driver.execute_script("return navigator.userAgent")[:70])
    print("block patterns:", patterns)
    driver.quit()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        print("wrote", run(args.run))
