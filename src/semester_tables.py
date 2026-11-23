"""Semester tables in the curriculum and syllabus PDFs -> one row per table row.

A table looks like this in the PDF text (titles sometimes wrap above and below the row):
    Sl. / Subject Code SEMESTER III L T P C / No.
    1. CS2101 Algorithm 3 0 3 4.5
    ...
    TOTAL 17 0 8 21

Each row has: semester, code, title, L, T, P, credits, page, the row number as printed, and table_index
(0 = the semester's course table, 1 and up = a later table under the same header, i.e. elective options),
and group (the header of an elective option list, empty in a semester table).
The printed TOTAL is kept so every semester can be checked: the credits of its rows must add up to it.
"""
import re

# The header line is "SEMESTER III", "Semester-I", "Semester – VII", with or without column names around it.
SEMESTER = re.compile(r"^(?:(?:Sl\.?|No\.?|Subject|Code|Course)\s+)*Semester\s*[-–]?\s*([IVX]+|\d+)\b"
                      r"(?:\s+L\s+T\s+P\s+C)?\s*$", re.I)
# L T P C at the end of a row. "X" means the PDF leaves it open, and a star after the credits is a footnote mark.
# An option list whose own header names it an elective: "Departmental Elective – I L T P C",
# "Subject Code Department Electives - I L T P C", "Interdisciplinary Elective (IDE) L T P C", "IDE - I L T P C".
ELECTIVE_HEADER = re.compile(
    r"^(?:(?:Sl\.?|No\.?|Subject|Code|Course)\s+)*((?:(?:Departmental|Department|Programme|Program|Open|Free|"
    r"Interdisciplinary|Inter-Disciplinary|Specialization)\s+Electives?|IDE)(?:\s*\(\w+\))?"
    r"(?:\s*[-–]?\s*(?:[IVX]+|\d+))?)\s+L\s+T\s+P\s+C$", re.I)
TAIL = re.compile(r"\s(\d+|X)\s+(\d+|X)\s+(\d+|X)\s+(\d+(?:\.\d+)?)\*?$")
CODE_PIECE = r"[A-Z]{2}\d{2}[A-Z0-9]{2}"
CODE = rf"{CODE_PIECE}(?:/{CODE_PIECE})?"
ROW_START = re.compile(rf"^(?:(\d+)\.?\s+)?(?:({CODE})(?:\s+|$))?(.*)$")
CODE_FIRST = re.compile(rf"^({CODE})(?:\s+(.*))?$")
HEADER_WORDS = {"sl.", "sl", "no.", "no", "subject", "code", "course", "title", "name", "number", "l", "t", "p", "c"}
FOOTER = re.compile(r"^(Page \d+ of \d+|\d+)$")
TOTAL = re.compile(r"^TOT\s?AL(?!\s+Credits)\b", re.I)     # the PDF once prints "TOT AL"
CODE_PART = re.compile(rf"^({CODE_PIECE})/?$")
# "(i) B. Tech. in Chemical Engineering" / "(v.) M. Tech. in Structural Engineering"
PROGRAMME = re.compile(r"^\(\s*[\divx]+\.?\s*\)\s*((?:B|M)\.\s?(?:Tech|S|Sc)\.?(?!\s*Programme).*)$", re.I)
DEPARTMENT = re.compile(r"^\(\d+\.\)\s*(?:B\.|M\.).*?Programme from (?:the )?Department of (.+)$", re.I)
# Slot rows: placeholders for a choice the student makes, not a real course.
SLOT_TITLE = re.compile(
    r"^(?P<label>(?:I?DE|HSS Elective|Specialization Elective|Open Elective|Free Elective|Programme Elective|"
    r"Program Elective|Department Elective|Inter-?Disciplinary Elective|(?:B|M)\. Tech\. Elective|Elective|"
    r"OE|PE|SE|Minor)\b(?:\s*[-–]\s*|\s+)?(?:[IVX]+|\d+)?)\b", re.I)
PLACEHOLDER_CODE = re.compile(r"^[A-Z]{2}\d{2}(XX|PQ)$")


def tidy(title, code):
    """Move course-code fragments ("CE51XX/", "CE62PQ") and stray row numbers ("1.") out of a title."""
    tokens = title.split()
    parts = [t.rstrip("/") for t in tokens if re.fullmatch(rf"{CODE_PIECE}/?", t)]
    tokens = [t for t in tokens if not re.fullmatch(rf"{CODE_PIECE}/?", t) and t != "/"]
    while len(tokens) > 1 and re.fullmatch(r"\d+\.", tokens[-1]):
        tokens.pop()
    title = " ".join(tokens).lstrip("/ ").rstrip(":").strip()
    if parts and not code:
        code = "/".join(parts)
    return title, code


def is_header_line(text):
    words = text.lower().split()
    return bool(words) and all(w in HEADER_WORDS for w in words)


def parse_tables(pages):
    """pages: pdf_lines() output. Returns (rows, totals, programmes) where
    rows     = list of dicts (see module docstring) plus 'programme' and 'department' context,
    totals   = {(programme, semester, page): printed credit total},
    """
    rows, totals = [], {}
    seen_tables = {}                   # (programme, semester) -> how many tables with that header so far
    table_index = 0
    group = ""                         # the header of an elective option list, "" in a semester table
    programme = department = None
    semester = None
    anchors, orphans = [], []          # lines of the table being read
    region_open = False
    last_total_page = None

    def flush(page):
        """Turn the collected anchors and orphans of one table into rows."""
        nonlocal anchors, orphans
        for a in anchors:
            a["pieces"] = [(a["top"], a["title"])] if a["title"] else []
        for o in orphans:
            if not anchors:
                continue
            centre = (o["top"] + o["bottom"]) / 2
            best = min(anchors, key=lambda a: abs((a["top"] + a["bottom"]) / 2 - centre))
            if abs((best["top"] + best["bottom"]) / 2 - centre) > 13:
                continue
            frag = CODE_PART.match(o["text"])
            if frag and not best["code"]:
                best.setdefault("code_parts", []).append((o["top"], frag.group(1)))
                continue
            m = CODE_FIRST.match(o["text"])
            if m and not best["code"]:
                best["code"] = m.group(1)
                if m.group(2):
                    best["pieces"].append((o["top"], m.group(2)))
            else:
                best["pieces"].append((o["top"], o["text"]))
        for a in anchors:
            if a.get("code_parts") and not a["code"]:
                a["code"] = "/".join(c for _, c in sorted(a["code_parts"]))
            title = " ".join(t for _, t in sorted(a["pieces"], key=lambda p: p[0]))
            title, a["code"] = tidy(" ".join(title.split()), a["code"])
            rows.append({"programme": a["programme"], "department": a["department"], "semester": a["semester"],
                         "row_number": a["n"], "code": a["code"], "title": title,
                         "L": a["L"].replace("X", ""), "T": a["T"].replace("X", ""), "P": a["P"].replace("X", ""),
                         "credits": a["credits"], "page": a["page"], "below_total": a["below_total"],
                         "table_index": a["table_index"], "group": a["group"]})
        anchors, orphans = [], []

    for page_no, lines in enumerate(pages, 1):
        for line in lines:
            text = line["text"]
            if FOOTER.match(text):
                continue
            if m := DEPARTMENT.match(text):
                flush(page_no); region_open = False
                department, programme, semester = m.group(1).strip(), None, None
                continue
            if m := PROGRAMME.match(text):
                flush(page_no); region_open = False
                programme, semester = m.group(1).strip(), None
                continue
            if text.startswith("Common curriculum"):
                flush(page_no); region_open = False
                programme, semester = "Common curriculum (first two semesters)", None
                continue
            if m := SEMESTER.match(text):
                flush(page_no)
                semester, region_open, group = m.group(1), True, ""
                # The first table of a semester is its course table; later ones with the same header
                # list the options for the elective slots.
                key = (programme, semester)
                table_index = seen_tables.get(key, 0)
                seen_tables[key] = table_index + 1
                continue
            if m := ELECTIVE_HEADER.match(text):
                flush(page_no)
                region_open, group, table_index = True, m.group(1).strip(), 1
                continue
            if not region_open:
                # The "Minor - IV 3 0 2 4" row is printed under the table's TOTAL line.
                m = re.match(r"^(Minor\s*[-–]?\s*(?:[IVX]+|\d))\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)$", text)
                if m and semester:
                    rows.append({"programme": programme, "department": department, "semester": semester,
                                 "row_number": "", "code": "", "title": m.group(1), "L": m.group(2),
                                 "T": m.group(3), "P": m.group(4), "credits": m.group(5), "page": page_no,
                                 "below_total": True, "table_index": 0, "group": ""})
                continue
            if is_header_line(text):
                if anchors:                    # a second table header: the previous table is over
                    flush(page_no)
                    region_open = False
                continue
            if re.match(r"^Total Credits", text, re.I):
                flush(page_no); region_open = False
                continue
            if TOTAL.match(text):
                nums = re.findall(r"\d+(?:\.\d+)?", text)
                if nums:
                    totals[(programme, semester, page_no)] = nums[-1]
                flush(page_no)
                region_open = False
                continue
            t = TAIL.search(text)
            if t:
                head = text[:t.start()].strip()
                m = ROW_START.match(head)
                n, code, title = m.group(1) or "", m.group(2) or "", (m.group(3) or "").strip()
                anchors.append({"programme": programme, "department": department, "semester": semester,
                                "n": n, "code": code, "title": title, "L": t.group(1), "T": t.group(2),
                                "P": t.group(3), "credits": t.group(4), "page": page_no, "top": line["top"],
                                "bottom": line["bottom"], "below_total": False,
                                "table_index": table_index, "group": group})
            else:
                orphans.append({"text": text, "top": line["top"], "bottom": line["bottom"]})
        # A table cut by the page break stays open; the next page's first lines continue it.
    flush(len(pages))
    return rows, totals


def slot_of(row):
    """(label, type) if the row is a slot placeholder (DE-II, IDE - I, HSS Elective II ...), else None.
    The label is what the PDF prints; the type is the label without its number."""
    title, code = row["title"], row["code"] or ""
    placeholder = bool(PLACEHOLDER_CODE.match(code))
    m = SLOT_TITLE.match(title)
    if m:
        rest = title[m.end():].strip()
        if rest and not rest.startswith("(") and not placeholder:
            return None                      # "Minor Project", "Elective Course ...": a real course
        label = m.group("label").strip()
    elif placeholder:
        label = re.sub(r"\s*\(.*", "", title).strip()
    else:
        return None
    kind = re.sub(r"[\s\-–]*(?:[IVX]+|\d+)$", "", label).strip()
    return label, kind or label
