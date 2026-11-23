"""Page-by-page text lines of a PDF, with their vertical position, cached on disk.

Reading a 200-page PDF takes about 15 seconds, and several steps need the same lines, so the result
is stored under data/pdf_lines/<sha256 of the file>.json. Nothing here touches the network.
"""
import hashlib
import json
from pathlib import Path

import pdfplumber

CACHE_DIR = Path("data/pdf_lines")


def pdf_lines(path):
    """[page][line] -> {"text", "top", "bottom", "x0"}; page 1 is index 0."""
    data = Path(path).read_bytes()
    cache = CACHE_DIR / f"{hashlib.sha256(data).hexdigest()}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append([{"text": " ".join(l["text"].split()), "top": round(l["top"], 1),
                           "bottom": round(l["bottom"], 1), "x0": round(l["x0"], 1)}
                          for l in page.extract_text_lines() if l["text"].strip()])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(pages))
    return pages


if __name__ == "__main__":
    import sys
    for p in sorted(Path("curated_pdfs").glob("**/*.pdf")):
        n = len(pdf_lines(p))
        print(f"{n:>4} pages  {p}", flush=True)
