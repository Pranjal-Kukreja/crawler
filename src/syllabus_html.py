"""Parser for the HTML syllabus pages on the academics site (page type "syllabus_html").

Page layout (checked on the Chemical Engineering B.Tech page):
  ul.accordian > li                one li per semester
    label                          "Semester I"
    div.content > table(s)         a semester table, plus tables for elective options
      tr  (7 cells)                Sl. No. | Subject Code | Title | L | T | P | C
      tr.syllabus-row              hidden detail block for the course above it:
        a small table of label/value pairs: Course Number, Course Credit, Course Title,
        Learning Mode, Learning Objectives, Course Description, ...

One record per course. Fields: course_code, title, department, programme, semester, credits, L, T, P,
course_type, mode, prerequisites, syllabus_text, learning_objectives, description, source_url,
fetched_at. A field is left empty when the page does not state it; nothing is guessed.
"""
import re

from bs4 import BeautifulSoup

PAGE_TYPE = "syllabus_html"


# Rows titled "DE-II", "IDE-III" or "HSS Elective-II" are elective slots, not courses. Where a slot
# row has a description it is a copy of one real elective, which is recorded in its own right.
SLOT_TITLE = re.compile(r"^(DE|IDE|HSS|OE|PE)\b")
IDE_LABEL = "IDE (floated by the department; not for this programme's students)"


def clean(text):
    return " ".join(text.split())


def detail_fields(syllabus_row):
    """Read the label/value pairs of a detail block into a dict."""
    fields = {}
    for tr in syllabus_row.find_all("tr"):
        cells = tr.find_all(["th", "td"], recursive=False)
        if len(cells) == 2:
            fields[clean(cells[0].get_text(" "))] = clean(cells[1].get_text(" "))
    return fields


def pick(fields, *names):
    """First non-empty value among the label variants, ignoring case and a trailing colon."""
    wanted = {n.lower() for n in names}
    for label, value in fields.items():
        if label.lower().rstrip(": ") in wanted and value:
            return value
    return ""


def course_type(group, ide_floated=False):
    """The kind of course, only as far as the page's own group heading says it. The pages never use
    the words core, programme/open/free elective, so those are never assigned; plain semester
    tables say nothing about core vs elective, so they stay empty."""
    if ide_floated:
        return "interdisciplinary_elective"      # the page defines IDE as Interdisciplinary Elective
    g = group.lower()
    if "department elective" in g or re.match(r"elective\s*-\s*de\b", g):
        return "department_elective"             # "Elective - DE-I" / "Department Elective - I"
    return ""


def parse_syllabus_page(html, department, programme, source_url, fetched_at=""):
    soup = BeautifulSoup(html, "lxml")
    records = []
    for li in soup.select("ul.accordian > li"):
        label = li.find("label")
        semester = clean(label.get_text(" ")) if label else ""
        for tr in li.select("div.content tr"):
            if "syllabus-row" in (tr.get("class") or []):
                continue
            cells = [clean(td.get_text(" ")) for td in tr.find_all("td", recursive=False)]
            if len(cells) != 7 or not re.fullmatch(r"\d+\.?", cells[0]):
                continue                           # header rows, totals, elective headings
            _, code, title, l, t, p, credits = cells
            title = title.replace("▼", "").strip()
            detail_row = tr.find_next_sibling("tr")
            fields = detail_fields(detail_row) if detail_row and "syllabus-row" in (
                detail_row.get("class") or []) else {}
            description = fields.get("Course Description", "")
            if SLOT_TITLE.match(title):
                continue                           # rule 1: drop elective-slot placeholders
            ide_floated = semester.startswith("IDE Floated")
            group = semester
            if ide_floated:
                semester = IDE_LABEL               # rule 3: say clearly it is not for this programme
            records.append({
                "course_code": code,
                "title": title,
                "department": department,
                "programme": programme,
                "semester": semester,
                "credits": credits,
                "L": l, "T": t, "P": p,
                "course_type": course_type(group, ide_floated),   # only if the page says so
                "mode": pick(fields, "Learning Mode"),
                "prerequisites": pick(fields, "Pre-requisite", "Prerequisite", "Pre-requisites"),
                "syllabus_text": pick(fields, "Course Content", "Course Outline"),
                "learning_objectives": pick(fields, "Learning Objectives"),
                "description": description,
                "source_url": source_url,
                "fetched_at": fetched_at,
            })
    return records


ROMAN = r"(?:I{1,3}|IV|V|VI{0,3})"


def _slot_kind(slot, page_text):
    """What the page says the slot abbreviation stands for ('' when it does not say)."""
    if slot.startswith("HSS"):
        return "HSS Elective"                       # the slot title says so itself
    if slot.startswith("IDE"):
        return "Interdisciplinary Elective" if re.search(
            r"IDE-?\s?\w*\s*\(Interdisciplinary Elective", page_text, re.I) else ""
    if slot.startswith("DE"):
        return "Department Elective" if re.search(r"Department Elective", page_text) else ""
    return ""


def elective_structure(html, department, programme, source_url, fetched_at=""):
    """One record per elective slot in the semester tables (DE-I, IDE-III, HSS Elective-II ...):
    semester, slot name, credits, what the page says the slot is, and how many option courses the
    page lists for it. Also the semester's total credits as printed, checked against the sum."""
    soup = BeautifulSoup(html, "lxml")
    page_text = clean(soup.get_text(" "))
    # option lists: heading "Elective - DE-II" or "Department Elective - II" -> {"DE-II": n courses}
    options = {}
    for li in soup.select("ul.accordian > li"):
        label = li.find("label")
        name = clean(label.get_text(" ")) if label else ""
        m = re.match(rf"(?:Department )?Elective\s*-\s*(?:DE-)?({ROMAN})$", name)
        if m:
            n = sum(1 for tr in li.select("div.content tr")
                    if "syllabus-row" not in (tr.get("class") or [])
                    and len(tr.find_all("td", recursive=False)) == 7
                    and re.fullmatch(r"\d+\.?", clean(tr.find_all("td", recursive=False)[0].get_text(" "))))
            options[f"DE-{m.group(1)}"] = n
    records = []
    for li in soup.select("ul.accordian > li"):
        label = li.find("label")
        semester = clean(label.get_text(" ")) if label else ""
        if not re.match(r"semester\s", semester, re.I):
            continue
        slots, total_sum, printed_total = [], 0.0, None
        for tr in li.select("div.content tr"):
            if "syllabus-row" in (tr.get("class") or []) or tr.find_parent("tr", class_="syllabus-row"):
                continue                           # the hidden detail block and its nested tables
            cells = [clean(td.get_text(" ")) for td in tr.find_all("td", recursive=False)]
            if cells and cells[0] == "TOTAL":
                printed_total = float(cells[-1])   # the last cell is the credit total
                continue
            if len(cells) != 7 or not re.fullmatch(r"\d+\.?", cells[0]):
                continue
            title = cells[2].replace("▼", "").strip()
            credits = float(cells[6])
            total_sum += credits
            if SLOT_TITLE.match(title):
                slots.append((title, cells[1], credits))
        for title, code, credits in slots:
            norm = re.sub(r"\s+", "", title)
            records.append({
                "department": department, "programme": programme, "semester": semester,
                "slot": title, "slot_code": code, "credits": credits,
                "slot_means": _slot_kind(norm, page_text),
                "options_listed": options.get(norm) if norm.startswith("DE") else None,
                "semester_total_credits_printed": printed_total,
                "semester_total_credits_summed": total_sum,
                "source_url": source_url, "fetched_at": fetched_at,
            })
    return records


# The two Chemical Engineering pages the user approved. Programme names are the ones the
# department's /courses page gives them.
PAGES = [
    ("chemical-engineering", "B.Tech in Chemical Engineering",
     "https://academics.iitp.ac.in/revised_syllabus/B.TECH-CSE/sem-1/chemicalengineering.html"),
    ("chemical-engineering", "M.Tech in Chemical Engineering",
     "https://academics.iitp.ac.in/revised_syllabus/B.TECH-CSE/M.TECH/mtech-chem.html"),
]


def main():
    """Parse the saved pages (no network) into data/out/<department>/<programme>.jsonl."""
    import json
    from pathlib import Path

    from src.config import load_config
    from src.fetcher import Fetcher
    from src.syllabus_pdfs import slug

    fetcher = Fetcher(load_config())
    for department, programme, url in PAGES:
        page = fetcher.cached(url)
        if page is None:
            raise SystemExit(f"not in the raw cache, fetch it first: {url}")
        records = parse_syllabus_page(page.text, department, programme, url, fetcher.saved_at(url))
        path = Path("data/out") / department / f"{slug(programme)}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
        print(f"{len(records):>3} records -> {path}")
        slots = elective_structure(page.text, department, programme, url, fetcher.saved_at(url))
        slot_path = Path("data/out") / department / f"{slug(programme)}.elective_slots.jsonl"
        slot_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in slots))
        print(f"{len(slots):>3} elective slots -> {slot_path}")
    print("network requests:", fetcher.network_requests)


if __name__ == "__main__":
    main()
