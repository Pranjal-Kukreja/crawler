"""Step 5: normalise everything extracted so far into the knowledge-base files in data/out/.

  courses.jsonl            one record per course_code, with every version found and a conflict flag
  programme_courses.jsonl  one record per (programme, course_code)
  rules.jsonl              the academic-rule records
  elective_structure.jsonl elective slots per programme and semester (written by src.elective_structure)
  minor_lists.jsonl        every minor course list, tagged "minor_list"; no eligibility rules exist to record

Nothing here touches the network. A value is left empty when the documents do not state it. When documents
disagree about a course, every version is kept with its source and the field is flagged instead of picked.
"""
import csv
import json
import re
from collections import OrderedDict, defaultdict
from pathlib import Path

from src.course_details import detail_blocks
from src.departments import department_slug
from src.elective_structure import CURRICULUM_PDF, CURRICULUM_URL
from src.pdf_lines import pdf_lines
from src.semester_tables import PLACEHOLDER_CODE, parse_tables, slot_of

OUT = Path("data/out")
REAL_CODE = re.compile(r"^[A-Z]{2}\d{4}$")
NONE_WORDS = {"", "nil", "none", "na", "notapplicable", "no"}
HTML_FILES = {
    "B.Tech in Chemical Engineering": "data/out/chemical-engineering/btech-in-chemical-engineering.jsonl",
    "M.Tech in Chemical Engineering": "data/out/chemical-engineering/mtech-in-chemical-engineering.jsonl",
}


def nrm(text):
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def as_number(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def split_codes(code):
    """'PH1101/PH1201' -> ['PH1101', 'PH1201']; placeholders such as XX41PQ are not courses."""
    return [c for c in (code or "").split("/") if REAL_CODE.match(c) and not PLACEHOLDER_CODE.match(c)]


def stem(group):
    """'Departmental Elective – I' -> 'departmental_elective' (the PDF's own words, lower case)."""
    s = re.sub(r"[\s\-–]*(?:[IVX]+|\d+)$", "", group.strip(), flags=re.I)
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def semester_token(label):
    """'Semester III' / 'SEMESTER 1' -> 'III' / '1'; anything else (an option-list heading) -> ''."""
    m = re.fullmatch(r"semester\s+([IVX]+|\d+)", label.strip(), re.I)
    return m.group(1).upper() if m else ""


# ---- reading the sources ------------------------------------------------------------------------------

def syllabus_documents():
    rows = list(csv.DictReader(open("curated_pdfs/MANIFEST.csv")))
    return [r for r in rows if r["department"] not in ("rules", "admissions", "curriculum")]


def version(kind, doc, code, page, **fields):
    base = {"code": code, "title": "", "L": "", "T": "", "P": "", "credits": "", "prerequisites": "",
            "learning_objectives": "", "course_description": "", "syllabus_text": "", "learning_outcomes": "",
            "mode": ""}
    base.update(fields)
    base.update({"kind": kind, "programme": doc["programme"], "department": doc["department"],
                 "source_url": doc["url"], "source_page": page, "fetched_at": doc["fetched_at"]})
    return base


def collect_pdf(doc, versions, entries):
    """Table rows and detail blocks of one syllabus PDF -> versions (for courses) and entries (for programme_courses)."""
    rows, _ = parse_tables(pdf_lines(doc["file"]))
    for r in rows:
        if slot_of(r):
            continue
        for code in split_codes(r["code"]):
            kind = "semester_table" if r["table_index"] == 0 and not r["group"] else "option_list"
            versions.append(version(kind, doc, code, r["page"], title=r["title"], L=r["L"], T=r["T"], P=r["P"],
                                    credits=r["credits"]))
            entries.append({"programme": doc["programme"], "department": doc["department"], "code": code,
                            "kind": kind, "semester": r["semester"] if r["table_index"] == 0 and not r["group"] else "",
                            "group": r["group"], "credits": r["credits"], "L": r["L"], "T": r["T"], "P": r["P"],
                            "page": r["page"], "source_url": doc["url"], "fetched_at": doc["fetched_at"],
                            "listed_as": r["code"] if "/" in r["code"] else ""})
    unusable = []
    for b in detail_blocks(doc["file"]):
        codes = split_codes(b["code"])
        if not codes:
            unusable.append({"programme": doc["programme"], "page": b["page"], "title": b["title"],
                             "source_url": doc["url"]})
            continue
        f = b["fields"]
        for code in codes:
            versions.append(version("detail_block", doc, code, b["page"], title=b["title"], L=b["L"], T=b["T"],
                                    P=b["P"], credits=b["credits"], prerequisites=f.get("prerequisites", ""),
                                    learning_objectives=f.get("learning_objectives", ""),
                                    course_description=f.get("course_description", ""),
                                    syllabus_text=f.get("syllabus_text", ""),
                                    learning_outcomes=f.get("learning_outcomes", ""), mode=f.get("mode", "")))
            entries.append({"programme": doc["programme"], "department": doc["department"], "code": code,
                            "kind": "detail_block", "semester": "", "group": "", "credits": b["credits"],
                            "L": b["L"], "T": b["T"], "P": b["P"], "page": b["page"],
                            "source_url": doc["url"], "fetched_at": doc["fetched_at"], "listed_as": ""})
    return unusable


def collect_html(programme, path, versions, entries):
    for rec in map(json.loads, open(path)):
        doc = {"programme": programme, "department": rec["department"], "url": rec["source_url"],
               "fetched_at": rec["fetched_at"]}
        ide_floated = rec["semester"].startswith("IDE (floated")
        for code in split_codes(rec["course_code"]):
            versions.append(version("html_detail", doc, code, "", title=rec["title"], L=rec.get("L", ""),
                                    T=rec.get("T", ""), P=rec.get("P", ""), credits=rec["credits"],
                                    prerequisites=rec["prerequisites"], learning_objectives=rec["learning_objectives"],
                                    course_description=rec["description"], syllabus_text=rec["syllabus_text"],
                                    mode=rec["mode"]))
            if ide_floated:
                continue              # offered to other departments' students, not part of this programme
            sem = semester_token(rec["semester"])
            entries.append({"programme": programme, "department": rec["department"], "code": code,
                            "kind": "html_detail", "semester": sem, "group": "" if sem else rec["semester"],
                            "credits": rec["credits"], "L": rec.get("L", ""), "T": rec.get("T", ""),
                            "P": rec.get("P", ""), "page": "", "source_url": rec["source_url"],
                            "fetched_at": rec["fetched_at"], "listed_as": rec["course_code"] if "/" in rec["course_code"] else "",
                            "html_type": rec["course_type"]})


def collect_curriculum(versions, fetched_at):
    rows, _ = parse_tables(pdf_lines(CURRICULUM_PDF))
    for r in rows:
        if slot_of(r):
            continue
        doc = {"programme": r["programme"] or "", "department": department_slug(r["department"]),
               "url": CURRICULUM_URL, "fetched_at": fetched_at}
        for code in split_codes(r["code"]):
            versions.append(version("curriculum_table", doc, code, r["page"], title=r["title"], L=r["L"], T=r["T"],
                                    P=r["P"], credits=r["credits"]))


# ---- programme_courses --------------------------------------------------------------------------------

def merged(values):
    """(value, listed): the value when all non-empty ones agree, '' when they differ, plus the distinct list."""
    seen = list(OrderedDict.fromkeys(v for v in values if v not in ("", None)))
    return (seen[0] if len(seen) == 1 else ""), (seen if len(seen) > 1 else [])


def programme_courses(entries):
    groups = OrderedDict()
    for e in entries:
        groups.setdefault((e["programme"], e["code"]), []).append(e)
    out = []
    for (programme, code), es in groups.items():
        sem_rows = [e for e in es if e["semester"]]
        semester, semesters = merged([e["semester"] for e in sem_rows])
        types = [e.get("html_type") or stem(e["group"]) for e in es if e["group"] or e.get("html_type")]
        course_type, types_listed = merged(types)
        groups_listed = list(OrderedDict.fromkeys(e["group"] for e in es if e["group"]))
        credits, credits_listed = merged([e["credits"] for e in es if e["kind"] != "detail_block"] or
                                         [e["credits"] for e in es])
        first = (sem_rows or [e for e in es if e["kind"] in ("option_list", "html_detail")] or es)[0]
        rec = {"record_type": "programme_course", "programme": programme, "department": es[0]["department"],
               "course_code": code, "semester": semester, "course_type": course_type,
               "elective_group": groups_listed[0] if len(groups_listed) == 1 else "",
               "credits": credits, "L": merged([e["L"] for e in es])[0], "T": merged([e["T"] for e in es])[0],
               "P": merged([e["P"] for e in es])[0], "listed_as": next((e["listed_as"] for e in es if e["listed_as"]), ""),
               "evidence": list(OrderedDict.fromkeys(e["kind"] for e in es)),
               "source_url": first["source_url"], "source_page": first["page"], "fetched_at": first["fetched_at"]}
        if semesters:
            rec["semesters_listed"] = semesters
        if credits_listed:
            rec["credits_listed"] = credits_listed
        if types_listed:
            rec["course_types_listed"] = types_listed
        if len(groups_listed) > 1:
            rec["elective_groups_listed"] = groups_listed
        out.append(rec)
    return sorted(out, key=lambda r: (r["department"], r["programme"], r["course_code"]))


# ---- courses ------------------------------------------------------------------------------------------

def description_of(v):
    parts = [("Learning objectives", v["learning_objectives"]), ("Course description", v["course_description"]),
             ("Course content", v["syllabus_text"])]
    return "\n\n".join(f"{label}: {text}" for label, text in parts if text)


def conflicts_of(versions):
    def values(fn):
        return {x for x in (fn(v) for v in versions) if x}

    flagged = []
    if len(values(lambda v: nrm(v["title"]))) > 1:
        flagged.append("title")
    if len({as_number(v["credits"]) for v in versions if as_number(v["credits"]) is not None}) > 1:
        flagged.append("credits")
    if len(values(lambda v: (v["L"], v["T"], v["P"]) if v["L"] and v["T"] and v["P"] else None)) > 1:
        flagged.append("ltp")
    if len({nrm(v["prerequisites"]) for v in versions if nrm(v["prerequisites"]) not in NONE_WORDS}) > 1:
        flagged.append("prerequisites")
    if len(values(lambda v: nrm(description_of(v)))) > 1:
        flagged.append("description")
    return flagged


def build_courses(all_versions):
    by_code = OrderedDict()
    for v in all_versions:
        by_code.setdefault(v["code"], []).append(v)
    out = []
    for code, vs in sorted(by_code.items()):
        merged_versions = OrderedDict()
        for v in vs:
            key = (nrm(v["title"]), v["L"], v["T"], v["P"], as_number(v["credits"]), nrm(v["prerequisites"]) if
                   nrm(v["prerequisites"]) not in NONE_WORDS else "", nrm(v["learning_objectives"]),
                   nrm(v["course_description"]), nrm(v["syllabus_text"]), nrm(v["learning_outcomes"]))
            entry = merged_versions.setdefault(key, {
                **{k: v[k] for k in ("title", "L", "T", "P", "credits", "prerequisites", "learning_objectives",
                                     "course_description", "syllabus_text", "learning_outcomes", "mode")},
                "sources": []})
            entry["sources"].append({"kind": v["kind"], "programme": v["programme"], "department": v["department"],
                                     "source_url": v["source_url"], "source_page": v["source_page"],
                                     "fetched_at": v["fetched_at"]})
        versions = list(merged_versions.values())
        order = {"detail_block": 0, "html_detail": 0, "semester_table": 1, "option_list": 2, "curriculum_table": 3}
        versions.sort(key=lambda x: min(order[s["kind"]] for s in x["sources"]))
        flagged = conflicts_of(versions)

        departments = sorted({s["department"] for x in versions for s in x["sources"] if s["department"]})
        detail = next((x for x in versions if x["learning_objectives"] or x["course_description"] or x["syllabus_text"]), None)
        first_source = versions[0]["sources"][0]
        out.append({
            "record_type": "course", "course_code": code,
            "title": "" if "title" in flagged else next((x["title"] for x in versions if x["title"]), ""),
            "department": departments[0] if len(departments) == 1 else "", "departments": departments,
            "credits": "" if "credits" in flagged else next((x["credits"] for x in versions if x["credits"]), ""),
            "L": "" if "ltp" in flagged else next((x["L"] for x in versions if x["L"]), ""),
            "T": "" if "ltp" in flagged else next((x["T"] for x in versions if x["T"]), ""),
            "P": "" if "ltp" in flagged else next((x["P"] for x in versions if x["P"]), ""),
            "prerequisites": "" if "prerequisites" in flagged else next(
                (x["prerequisites"] for x in versions if x["prerequisites"]), ""),
            "description": "" if "description" in flagged or not detail else description_of(detail),
            "conflict": bool(flagged), "conflict_fields": flagged, "n_versions": len(versions),
            "programmes": sorted({s["programme"] for x in versions for s in x["sources"] if s["programme"]}),
            "source_url": first_source["source_url"], "source_page": first_source["source_page"],
            "fetched_at": first_source["fetched_at"], "versions": versions})
    return out


# ---- the other files ---------------------------------------------------------------------------------

def tagged(path, record_type):
    return [{"record_type": record_type, **json.loads(l)} for l in open(path)]


def write(name, records):
    path = OUT / name
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    print(f"{len(records):>5} records -> {path}")


def main():
    from src.config import load_config
    from src.fetcher import Fetcher

    fetcher = Fetcher(load_config())
    versions, entries, unusable = [], [], []
    for doc in syllabus_documents():
        unusable += collect_pdf(doc, versions, entries)
    for programme, path in HTML_FILES.items():
        collect_html(programme, path, versions, entries)
    collect_curriculum(versions, fetcher.saved_at(CURRICULUM_URL))

    OUT.mkdir(parents=True, exist_ok=True)
    pcs = programme_courses(entries)
    courses = build_courses(versions)
    write("courses.jsonl", courses)
    write("programme_courses.jsonl", pcs)
    write("rules.jsonl", tagged("data/out/rules/rules.jsonl", "academic_rule"))
    write("minor_lists.jsonl", tagged("data/out/minors/minors.jsonl", "minor_list"))
    Path("data/out/unusable_detail_blocks.json").write_text(json.dumps(unusable, indent=1))
    print(f"{len(unusable):>5} detail blocks had no readable course code -> data/out/unusable_detail_blocks.json")
    print("network requests:", fetcher.network_requests)


if __name__ == "__main__":
    main()
