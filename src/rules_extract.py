"""Pull academic rules out of the ordinance and regulation PDFs in curated_pdfs/rules/.

Each page is cut into clause-sized chunks, and a chunk is kept when it matches one rule type:
  credit_limit, minor_eligibility, prerequisite, online_credit, other
Matching is keyword-based, so it can miss a rule or keep a near-miss: every record keeps its
page number so a person can check it against the PDF. Nothing is rewritten; text is as printed.
"""
import csv
import json
import re
from pathlib import Path

import pdfplumber

OUT = "data/out/rules/rules.jsonl"

# Which programme each document is about, from the document's own title.
APPLIES_TO = {
    "btech-ordinances-and-regulations-2019-onwards": "B.Tech",
    "mtech-ordinances-and-regulations-2022": "M.Tech",
    "mtech-by-research-ordinances-and-regulations-2020": "M.Tech by Research",
    "msc-and-ma-ordinances-and-regulations-2020": "M.Sc. / M.A.",
    "phd-ordinances-and-regulations-2019": "PhD",
    "integrated-dual-degree-detailed-information": "Integrated Dual Degree (IIT Patna with NITIE Mumbai)",
}

# Checked in this order; the first match wins. "other" is a short list of common academic rules.
RULES = [
    ("minor_eligibility", r"\bminors?\b"),
    ("online_credit", r"\b(NPTEL|SWAYAM|MOOCs?|online (course|credit|learning))"),
    ("prerequisite", r"\bpre-?requisites?\b(?!\s*:?\s*(none|nil|-)\b)|must pass .{0,60}before (registering|registration)|before registering for"),
    ("credit_limit", r"credit requirements?|\b(earn|complete|completing)\b.{0,60}\bcredits\b|total (number of )?credits|"
                     r"\bcredits?\b.{0,120}\b(not (be )?(less|more) than|should not exceed|shall not exceed|maximum|minimum|at least|at most|overload)|"
                     r"\b(maximum|minimum|at least|overload\w*)\b.{0,120}\bcredits?\b"),
    ("other", r"\battendance\b|\b(CPI|CGPA)\b.{0,60}\b(at least|lower than|below|less than|minimum|not less)|"
              r"\bdebarred\b|\bterminat\w+|\bwithdraw\w*|\brepeat\b|\beligible\b|\bbacklog"),
]
NUMBER_ONLY = re.compile(r"^\d{1,2}(\.\d{1,2}){0,2}\.?$")          # the clause numbers in the left column
NEW_ITEM = re.compile(r"^\(([a-z]|[ivx]+|\d+)\)\s?")                # (a)  (ii)  (3)
# A clause number or heading that runs on inside a paragraph: "... session 11.2 In order to ..."
INLINE_CLAUSE = re.compile(r"\s+(?=\d{1,2}\.\d{1,2}(?:\.\d{1,2})?\s?[A-Z(])|\s+(?=\d{1,2}\.\s?[A-Z][A-Z ]{6,})")


def chunks_of(page_text):
    """Cut one page's text into paragraphs: a new one starts at '(a)'-style items or after a full stop."""
    chunks, current = [], ""
    for line in page_text.splitlines():
        line = line.strip()
        if not line or NUMBER_ONLY.match(line):
            continue
        starts_new = bool(NEW_ITEM.match(line)) or (current.endswith(".") and line[:1].isupper())
        if starts_new and current:
            chunks.append(current)
            current = ""
        current = f"{current} {line}".strip()
    if current:
        chunks.append(current)
    return [part.strip() for c in chunks for part in INLINE_CLAUSE.split(c) if part.strip()]


def classify(text):
    for rule_type, pattern in RULES:
        if re.search(pattern, text, flags=re.I):
            return rule_type
    return None


def extract(pdf_path, source_url, fetched_at):
    applies_to = APPLIES_TO.get(Path(pdf_path).stem, "")
    records, seen = [], set()
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            for text in chunks_of(page.extract_text() or ""):
                text = " ".join(text.split())
                rule_type = classify(text)
                if not rule_type or not 40 <= len(text) <= 1500 or text in seen:
                    continue
                seen.add(text)
                records.append({"rule_type": rule_type, "text": text, "applies_to": applies_to,
                                "source_url": source_url, "page_number": number, "fetched_at": fetched_at})
    return records


def main():
    from src.config import load_config
    from src.fetcher import Fetcher
    fetcher = Fetcher(load_config())
    records = []
    for row in csv.DictReader(open("curated_pdfs/MANIFEST.csv")):
        if row["department"] == "rules":
            records += extract(row["file"], row["url"], row["fetched_at"])
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    Path(OUT).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    print(f"{len(records)} rule records -> {OUT}; network requests: {fetcher.network_requests}")


if __name__ == "__main__":
    main()
