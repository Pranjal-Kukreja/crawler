"""Minor-programme course lists from the revised curriculum PDF (and the B.Tech syllabus PDFs).

The PDF states a minor only as a heading ("Minor in Thermal Engineering") followed by a course table.
It states no eligibility, CPI or credit-requirement text for a minor, so none is recorded here.

One record per course row. Fields: programme_context, minor, note, slot, option, semester, course_code, title,
L, T, P, credits, source_url, page_number, fetched_at. A field is empty when the PDF does not state it.
"""
import json
import re
from pathlib import Path

import pdfplumber

CODE = re.compile(r"^[A-Z]{2}\d{4}$")
HEADING = re.compile(r"^(?:\d+\.\s*)?(Minor in [^:(]+?)\s*(?::|\(|$)(.*)$", re.I)
# A programme heading ends the minor above it: "(i) B. Tech. in ...", "(7.) B. Tech. Programme from ...".
PROGRAMME = re.compile(r"^(?:\(\w+\.?\)\s*)?((?:B|M)\.\s?(?:Tech|S|Sc)\.?\b.*|Common curriculum.+|Ph\.?\s?D.*|Dual Degree.*)$", re.I)
# Borderless tables (AI&DS, CSE) come out of the PDF as plain lines: "Minor-I CS2101 Algorithm 3 0 3 4.5".
LINE_ROW = re.compile(r"^(Minor[\s-]*(?:[IVX]+|\d))\s+([A-Z]{2}\d{4})\s+(.+?)\s+(\d)\s+(\d)\s+(\d)\s+(\d+(?:\.\d+)?)$")
SLOT = re.compile(r"^(?:\d+\.\s*)?(Minor[\s-]*(?:[IVX]+|\d)\b[^:]*)$", re.I)
NUMBER = re.compile(r"^\d+(\.\d+)?$")
# A table row cut by a page break: "ME3201 Applied Thermodynamics and" / "4. 3 1 2 5" / "Turbomachinery".
SPLIT_CODE = re.compile(r"^([A-Z]{2}\d{4})\s+(.+)$")
SPLIT_NUMS = re.compile(r"^\d+\.\s+(\d)\s+(\d)\s+(\d)\s+(\d+(?:\.\d+)?)$")


def clean(text):
    return " ".join((text or "").split())


def row_to_record(cells):
    """A table row -> dict with slot/option/semester/code/title/LTPC, or None if it has no course code."""
    cells = [clean(c) for c in cells if c is not None and clean(c)]
    code_i = next((i for i, c in enumerate(cells) if CODE.match(c)), None)
    if code_i is None:
        return None
    nums = [c for c in cells if NUMBER.match(c)]
    if len(nums) < 4:
        return None
    l, t, p, credits = nums[-4:]
    before = cells[:code_i]
    semester = next((c for c in before if re.fullmatch(r"Sem [IVX]+", c)), "")
    label = next((c for c in before if SLOT.match(c)), "")
    option = next((c for c in before if re.fullmatch(r"[ivx]+\.", c)), "")
    rest = [c for c in cells[code_i + 1:] if not NUMBER.match(c)]
    return {"slot": clean(re.sub(r"^\d+\.\s*", "", label)), "option": option.rstrip("."),
            "semester": semester, "course_code": cells[code_i],
            "title": clean(" ".join(rest)), "L": l, "T": t, "P": p, "credits": credits}


def extract(pdf_path, source_url, fetched_at=""):
    records = []
    minor = context = slot = None
    note = ""
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            events = []                                  # (y, kind, payload) in reading order
            if minor:                                    # a minor table that carries over from the last page
                top = [clean(l["text"]) for l in page.extract_text_lines()[:3]]
                a, b = SPLIT_CODE.match(top[0]) if top else None, SPLIT_NUMS.match(top[1]) if len(top) > 1 else None
                if a and b:
                    tail = top[2] if len(top) > 2 and not PROGRAMME.match(top[2]) and "(" not in top[2][:2] else ""
                    records.append({"programme_context": context or "", "minor": minor, "note": note, "slot": slot or "",
                                    "option": "", "semester": "", "course_code": a.group(1),
                                    "title": clean(f"{a.group(2)} {tail}"), "L": b.group(1), "T": b.group(2),
                                    "P": b.group(3), "credits": b.group(4), "source_url": source_url,
                                    "page_number": number, "fetched_at": fetched_at})
            for line in page.extract_text_lines():
                text = clean(line["text"])
                if m := HEADING.match(text):
                    events.append((line["top"], "minor", (clean(m.group(1)), clean(m.group(2)).strip("() "))))
                elif PROGRAMME.match(text) and "Program Learning" not in text:
                    events.append((line["top"], "programme", text))
                elif re.search(r"\bSEMESTER\b", text):          # a regular semester table: the minor is over
                    events.append((line["top"], "end", text))
                elif m := LINE_ROW.match(text):
                    events.append((line["top"], "line", m.groups()))
            for table in page.find_tables():
                events.append((table.bbox[1], "table", table.extract()))
            for _, kind, payload in sorted(events, key=lambda e: e[0]):
                if kind == "programme":
                    minor = None
                    if not re.fullmatch(r"B\.\s?Tech\.\s*programmes?\.?", payload, re.I):   # that line alone is not a name
                        context = payload
                elif kind == "line" and minor:
                    slot_, code, title, l, t, p_, c = payload
                    key = (minor, code)
                    if key not in {(r["minor"], r["course_code"]) for r in records}:
                        records.append({"programme_context": context or "", "minor": minor, "note": note,
                                        "slot": clean(slot_), "option": "", "semester": "",
                                        "course_code": code, "title": clean(title), "L": l, "T": t,
                                        "P": p_, "credits": c, "source_url": source_url,
                                        "page_number": number, "fetched_at": fetched_at})
                elif kind == "minor":
                    (minor, note), slot = payload, ""
                elif kind == "end":
                    minor = None
                elif kind == "table" and minor:
                    for cells in payload:
                        first = clean(cells[0]) if cells and cells[0] else ""
                        if not any(CODE.match(clean(c)) for c in cells if c):
                            if SLOT.match(first):
                                slot = clean(re.sub(r"^\d+\.\s*", "", first))     # "Minor-IV (Any One)"
                            elif first.lower().startswith("total"):
                                pass
                            else:                       # a title that wrapped onto its own row: "Mumbai)"
                                texts = [clean(c) for c in cells if c and clean(c)]
                                last = records[-1] if records else None
                                if (len(texts) == 1 and last and last["minor"] == minor
                                        and last["page_number"] == number and texts[0] != "Minor"
                                        and not HEADING.match(texts[0])):
                                    last["title"] = clean(f"{last['title']} {texts[0]}")
                            continue
                        rec = row_to_record(cells)
                        if rec and (minor, rec["course_code"]) not in {(r["minor"], r["course_code"]) for r in records}:
                            rec["slot"] = rec["slot"] or slot or ""
                            records.append({"programme_context": context or "", "minor": minor, "note": note, **rec,
                                            "source_url": source_url, "page_number": number,
                                            "fetched_at": fetched_at})
    return records


def main():
    from src.config import load_config
    from src.fetcher import Fetcher
    from collections import Counter

    fetcher = Fetcher(load_config())
    url = "https://academics.iitp.ac.in/revised_curriculum/Revised_Curriculumn.pdf"
    path = "curated_pdfs/curriculum/revised-nep-2020-compliant-curriculum.pdf"
    records = extract(path, url, fetcher.saved_at(url))
    out = Path("data/out/minors/minors.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    print(len(records), "records ->", out)
    for (minor, page), n in sorted(Counter((r["minor"], r["page_number"]) for r in records).items(),
                                   key=lambda x: x[0][1]):
        print(f"  p{page:<4} {n:>2}  {minor}")
    print("network requests:", fetcher.network_requests)


if __name__ == "__main__":
    main()
