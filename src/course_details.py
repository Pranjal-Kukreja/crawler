"""Course-detail blocks in the syllabus PDFs.

Each course has a two-column table: a label on the left (Course Number, Course Credit (L-T-P-C), Course Title,
Learning Mode, Learning Objectives, Course Description, Course Content / Course Outline, Learning Outcome,
Pre-requisite, Text Books, Reference Books, ...) and its text on the right. A block can continue on the next page.
Every field is returned as the PDF prints it, whitespace collapsed; a label the PDF does not print is simply absent.
Result per block: {"page", "code", "title", "L", "T", "P", "credits", "fields": {name: text}}.
Cached under data/pdf_blocks/ because reading a hundred pages with tables is slow.
"""
import hashlib
import json
import re
from pathlib import Path

import pdfplumber

CACHE_DIR = Path("data/pdf_blocks")
CODE_PIECE = r"[A-Z]{2}\d{4}"

# printed label (lower case, one space) -> field name
LABELS = {
    "course number": "code", "course code": "code", "course": "course",
    "course credit (l-t-p-c)": "credit", "course credit": "credit", "course credit (l-t-p-c) ": "credit",
    "course title": "title",
    "learning mode": "mode", "mode of learning": "mode",
    "learning objectives": "learning_objectives", "learning objective": "learning_objectives",
    "course description": "course_description",
    "course content": "syllabus_text", "course outline": "syllabus_text",
    "learning outcome": "learning_outcomes", "learning outcomes": "learning_outcomes",
    "pre-requisite": "prerequisites", "pre-requisites": "prerequisites", "prerequisite": "prerequisites",
    "prerequisites": "prerequisites", "pre-requisite(s)": "prerequisites",
    "text books": "textbooks", "textbooks": "textbooks", "text book": "textbooks", "textbook": "textbooks",
    "reference books": "references", "reference book": "references", "references": "references",
    "reference": "references", "suggested readings": "references", "books": "textbooks",
    "assessment method": "assessment",
    "(l-t-p-c)": "credit_tail", "l-t-p-c": "credit_tail", "number": "code",     # a label that wrapped onto its own row
    "description": "course_description", "outline": "syllabus_text", "content": "syllabus_text",
    "objectives": "learning_objectives", "mode": "mode", "outcome": "learning_outcomes",
    "outcomes": "learning_outcomes",                  # the second half of a wrapped label
}
LTPC = re.compile(r"(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*-\s*(\d+(?:\.\d+)?)")
LTP_THEN_CREDITS = re.compile(r"(\d+)\s*-\s*(\d+)\s*-\s*(\d+)\s*\(\s*(\d+(?:\.\d+)?)\s*(?:AIU\s*)?Credits?\s*\)", re.I)


def clean(text):
    return " ".join((text or "").split())


def label_of(cell):
    return " ".join((cell or "").lower().split())


def _table_fields(table):
    """[[name, text]] for the rows of one table. The label is the first non-empty cell when it is a known label
    (some PDFs leave the first column empty); a row without a label continues the previous field."""
    out = []
    for row in table:
        cells = [(c or "").strip() for c in row]
        k = next((i for i, c in enumerate(cells) if c), None)
        if k is None:
            continue
        label = label_of(cells[k])
        text = clean(" ".join(c for c in cells[k + 1:] if c))
        if label in LABELS or (k == 0 and label):
            out.append([LABELS.get(label, "other:" + label), text])
        elif out:
            out[-1][1] = clean(out[-1][1] + " " + " ".join(c for c in cells if c))
        elif re.match(rf"^{CODE_PIECE}\b", clean(cells[k])):
            out.append(["course", clean(" ".join(c for c in cells if c))])   # "CE4107 Elementary Soil Behaviour"
    # The first half of a wrapped label ("Course", "Learning") has no text of its own: drop it.
    return [f for f in out if f[1] or not (f[0] == "course" or f[0].startswith("other:"))]


def _blocks_of_pdf(path):
    blocks = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            for table in page.extract_tables():
                fields = _table_fields(table)
                names = [n for n, _ in fields]
                starts = "code" in names or "title" in names or "course" in names or "credit" in names
                if starts:
                    blocks.append({"page": number, "fields": fields})
                elif blocks and blocks[-1]["page"] >= number - 1 and fields and all(
                        not n.startswith("other:") for n, _ in fields):
                    blocks[-1]["fields"].extend(fields)          # the previous block continues on this page
    return blocks


def detail_blocks(path):
    data = Path(path).read_bytes()
    cache = CACHE_DIR / f"{hashlib.sha256(data).hexdigest()}.json"
    if cache.exists():
        raw = json.loads(cache.read_text())
    else:
        raw = _blocks_of_pdf(path)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(raw))
    return [shape(b) for b in raw]


def shape(block):
    f = {}
    for name, text in block["fields"]:
        f[name] = clean(f.get(name, "") + " " + text) if name in f else text
    code = title = ""
    if f.get("code"):
        codes = re.findall(CODE_PIECE, re.sub(r"\s+", "", f["code"]).replace("/", " ").replace(",", " ")) \
            or re.findall(CODE_PIECE, f["code"])
        code = "/".join(dict.fromkeys(codes))
    if f.get("course") and not code:
        m = re.match(rf"^({CODE_PIECE})[\s:\-–.]*(.*)$", f["course"])
        if m:
            code, title = m.group(1), m.group(2)
    if f.get("code") and not title and not f.get("title"):
        title = clean(re.sub(rf"{CODE_PIECE}\s*/?", "", f["code"]))
    title = f.get("title") or title
    L = T = P = credits = ""
    credit = clean(f.get("credit", "") + " " + f.get("credit_tail", ""))
    if m := LTPC.search(credit) or LTP_THEN_CREDITS.search(credit):
        L, T, P, credits = m.groups()
    elif re.fullmatch(r"\d+(?:\.\d+)?", credit):
        credits = credit
    rest = {k: v for k, v in f.items() if k not in ("code", "course", "credit", "credit_tail", "title")}
    return {"page": block["page"], "code": code, "title": title, "L": L, "T": T, "P": P, "credits": credits,
            "fields": rest}
