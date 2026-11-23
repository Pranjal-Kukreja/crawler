"""Step 6 (light): check the knowledge-base files in data/out/ and stop loudly when a hard rule is broken.

Hard rules (exit code 1 on the first break):
  1. every record has a non-empty source_url and fetched_at (all five files, and every version's sources)
  2. course_code is non-empty and unique in courses.jsonl
Reported, not failed:
  - record counts per file and per programme
  - courses in programme_courses.jsonl that have no record in courses.jsonl
  - courses whose versions disagree (conflict flag), and detail blocks that had no readable code
"""
import json
import sys
from collections import Counter
from pathlib import Path

OUT = Path("data/out")
FILES = ["courses.jsonl", "programme_courses.jsonl", "rules.jsonl", "elective_structure.jsonl", "minor_lists.jsonl"]


class Invalid(Exception):
    pass


def load(name):
    path = OUT / name
    if not path.exists():
        raise Invalid(f"{path} is missing")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check_provenance(name, records):
    for i, r in enumerate(records, 1):
        for key in ("source_url", "fetched_at"):
            if not str(r.get(key) or "").strip():
                raise Invalid(f"{name} line {i}: empty {key} in {{{summary(r)}}}")
        for v in r.get("versions", []):
            for s in v["sources"]:
                for key in ("source_url", "fetched_at"):
                    if not str(s.get(key) or "").strip():
                        raise Invalid(f"{name} line {i} ({r.get('course_code')}): a version has an empty {key} "
                                      f"in its source {s}")


def summary(r):
    return ", ".join(f"{k}={str(r[k])[:40]!r}" for k in ("course_code", "programme", "rule_type", "slot_type", "minor")
                     if k in r)


def check_course_codes(courses):
    seen = Counter(c.get("course_code", "") for c in courses)
    empty = [i for i, c in enumerate(courses, 1) if not str(c.get("course_code") or "").strip()]
    if empty:
        raise Invalid(f"courses.jsonl: empty course_code on lines {empty[:10]}")
    dupes = [code for code, n in seen.items() if n > 1]
    if dupes:
        raise Invalid(f"courses.jsonl: {len(dupes)} duplicate course_code values, first: {dupes[:10]}")


def report(data):
    courses, pcs = data["courses.jsonl"], data["programme_courses.jsonl"]
    print("records per file:", {name: len(rs) for name, rs in data.items()})
    print("\ncourses per programme (programme_courses.jsonl):")
    per = Counter((r["department"], r["programme"]) for r in pcs)
    for (dep, prog), n in sorted(per.items()):
        print(f"  {n:>4}  {prog}  [{dep}]")
    codes = {c["course_code"] for c in courses}
    missing = sorted({(r["programme"], r["course_code"]) for r in pcs if r["course_code"] not in codes})
    print(f"\nprogramme_courses without a matching course in courses.jsonl: {len(missing)}")
    for prog, code in missing:
        print(f"  {code}  ({prog})")
    conflicts = [c for c in courses if c["conflict"]]
    print(f"\ncourses with disagreeing versions (kept, flagged): {len(conflicts)} of {len(courses)}; by field:",
          dict(Counter(f for c in conflicts for f in c["conflict_fields"])))
    unusable = OUT / "unusable_detail_blocks.json"
    if unusable.exists():
        print("detail blocks with no readable course code:", len(json.loads(unusable.read_text())))


def main():
    try:
        data = {name: load(name) for name in FILES}
        for name, records in data.items():
            check_provenance(name, records)
        check_course_codes(data["courses.jsonl"])
    except Invalid as e:
        print("VALIDATION FAILED:", e, file=sys.stderr)
        raise SystemExit(1)
    print("VALIDATION PASSED: every record has source_url and fetched_at; course_code is non-empty and unique.\n")
    report(data)


if __name__ == "__main__":
    main()
