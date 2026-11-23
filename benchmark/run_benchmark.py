"""Run the benchmark: 3 runs of each scraper on benchmark/urls.txt, then compare.

    python -m benchmark.run_benchmark

Each run is a fresh process (and, for Selenium, a fresh browser with an empty cache); the HTTP side never reads
data/raw/. The order alternates (H S, S H, H S) so that time of day does not favour one scraper. The runs go one
after another, never in parallel, so the site never sees both scrapers at once.
"""
import subprocess
import sys
import time

ORDER = [("http", 1), ("selenium", 1), ("selenium", 2), ("http", 2), ("http", 3), ("selenium", 3)]


def main():
    for scraper, n in ORDER:
        t0 = time.time()
        print(f"[{time.strftime('%H:%M:%S')}] {scraper} run {n} ...", flush=True)
        subprocess.run([sys.executable, "-m", f"benchmark.{scraper if scraper == 'selenium' else 'http'}_runner", "--run", str(n)],
                       check=True)
        print(f"    done in {time.time() - t0:.0f} s", flush=True)
    subprocess.run([sys.executable, "-m", "benchmark.compare"], check=True)


if __name__ == "__main__":
    main()
