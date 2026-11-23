"""Elective slots per programme and semester, read from the semester tables of the curriculum PDF.

A slot is a table row that stands for a choice (DE-II, IDE - I, HSS Elective II, B. Tech. Elective - I,
Minor - IV ...) instead of a named course. The PDF's own wording is kept: slot_type is the label with its
number removed, slot_labels are the labels as printed. Nothing is inferred about what a slot means.

Fields: programme, department, department_slug, semester, slot_type, slot_labels, number_of_slots,
credits_per_slot (empty if the slots differ), credits_each, source_page, source_pages, semester_total_credits,
printed_below_total, source_url, fetched_at.
"""
import json
from collections import OrderedDict
from pathlib import Path

from src.departments import department_slug
from src.pdf_lines import pdf_lines
from src.semester_tables import parse_tables, slot_of

CURRICULUM_URL = "https://academics.iitp.ac.in/revised_curriculum/Revised_Curriculumn.pdf"
CURRICULUM_PDF = "curated_pdfs/curriculum/revised-nep-2020-compliant-curriculum.pdf"
OUT = "data/out/elective_structure.jsonl"


def fmt(x):
    x = float(x)
    return int(x) if x == int(x) else x


def elective_structure(pages, source_url, fetched_at=""):
    rows, totals = parse_tables(pages)
    printed = {(prog, sem): v for (prog, sem, _), v in totals.items()}
    groups = OrderedDict()
    for r in rows:
        if r["table_index"] != 0:               # later tables under the same header list options, not slots
            continue
        slot = slot_of(r)
        if not slot:
            continue
        label, kind = slot
        g = groups.setdefault((r["programme"], r["semester"], kind, r["below_total"]),
                              {"department": r["department"], "labels": [], "credits": [], "pages": []})
        g["labels"].append(label)
        g["credits"].append(fmt(r["credits"]))
        g["pages"].append(r["page"])
    out = []
    for (programme, semester, kind, below), g in groups.items():
        out.append({
            "record_type": "elective_structure", "programme": programme, "department": g["department"] or "",
            "department_slug": department_slug(g["department"]),
            "semester": semester, "slot_type": kind, "slot_labels": g["labels"],
            "number_of_slots": len(g["labels"]),
            "credits_per_slot": g["credits"][0] if len(set(g["credits"])) == 1 else "",
            "credits_each": g["credits"], "source_page": min(g["pages"]), "source_pages": sorted(set(g["pages"])),
            "semester_total_credits": fmt(printed[(programme, semester)]) if (programme, semester) in printed else "",
            "printed_below_total": below, "source_url": source_url, "fetched_at": fetched_at})
    return out


def main():
    from collections import Counter

    from src.config import load_config
    from src.fetcher import Fetcher

    fetcher = Fetcher(load_config())
    records = elective_structure(pdf_lines(CURRICULUM_PDF), CURRICULUM_URL, fetcher.saved_at(CURRICULUM_URL))
    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    Path(OUT).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    print(f"{len(records)} records -> {OUT}")
    print("slot types as printed:", dict(Counter(r["slot_type"] for r in records)))
    print("network requests:", fetcher.network_requests)


if __name__ == "__main__":
    main()
