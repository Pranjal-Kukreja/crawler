"""Tests for the semester-table parser and the elective-slot finder, on lines shaped like the real PDFs."""
from src.elective_structure import elective_structure
from src.semester_tables import parse_tables, slot_of


def page(*items):
    """Lines 12 points apart, like a table. An item can be (text, top) to place a wrapped title line
    close to its own row, as in the real PDFs."""
    out, top = [], 100
    for item in items:
        text, at = item if isinstance(item, tuple) else (item, top)
        out.append({"text": text, "top": at, "bottom": at + 10, "x0": 50})
        top = at + 12
    return out


PAGE = page(
    "(2.) B. Tech. Programme from the Department of Computer Science and Engineering",
    "(ii) B. Tech. in Computer Science and Engineering (CSE)",
    "Sl.",
    "Subject Code SEMESTER VI L T P C",
    "No.",
    "1. CS3201 Cyber Security 3 0 2 4",
    ("Probability Theory and Ordinary", 176),
    ("2. MA1201 3 1 0 4", 183),
    ("Differential Equations", 190),
    ("3. CS32XX DE-I (CS ELECTIVES LIST) 3 0 0 3", 208),
    "4. CS3299 Capstone Project 0 0 6 3",
    "TOTAL 9 1 8 14",
    "Minor - IV 3 0 2 4",
    "Semester-VII",
    "1. XX41PQ IDE-III 3 0 0 3",
    "2. HS41XX HSS Elective II X X X 3*",
    "Total 6",
    "3",
)


def test_rows_wrapped_titles_and_totals():
    rows, totals = parse_tables([PAGE])
    sem6 = [r for r in rows if r["semester"] == "VI" and not r["below_total"]]
    assert [(r["code"], r["title"], r["credits"]) for r in sem6] == [
        ("CS3201", "Cyber Security", "4"),
        ("MA1201", "Probability Theory and Ordinary Differential Equations", "4"),
        ("CS32XX", "DE-I (CS ELECTIVES LIST)", "3"),
        ("CS3299", "Capstone Project", "3")]
    assert sum(float(r["credits"]) for r in sem6) == float(totals[("B. Tech. in Computer Science and Engineering (CSE)", "VI", 1)])
    assert rows[0]["department"] == "Computer Science and Engineering"


def test_x_in_ltp_is_left_empty_and_star_is_dropped():
    rows, _ = parse_tables([PAGE])
    hss = next(r for r in rows if r["code"] == "HS41XX")
    assert (hss["L"], hss["T"], hss["P"], hss["credits"]) == ("", "", "", "3")


def test_minor_row_under_the_total_is_kept_but_flagged():
    rows, _ = parse_tables([PAGE])
    minor = next(r for r in rows if r["title"].startswith("Minor"))
    assert minor["below_total"] and minor["semester"] == "VI" and minor["credits"] == "4"


def test_slot_rows_use_the_pdfs_own_words():
    assert slot_of({"title": "DE-I (CS ELECTIVES LIST)", "code": "CS32XX"}) == ("DE-I", "DE")
    assert slot_of({"title": "IDE - III", "code": "XX41PQ"}) == ("IDE - III", "IDE")
    assert slot_of({"title": "HSS Elective II", "code": "HS41XX"}) == ("HSS Elective II", "HSS Elective")
    assert slot_of({"title": "Department Elective - II", "code": "PH51XX"})[1] == "Department Elective"
    assert slot_of({"title": "Minor Project", "code": "ME4190"}) is None        # a real course
    assert slot_of({"title": "Cyber Security", "code": "CS3201"}) is None


def test_elective_structure_counts_slots_and_credits():
    recs = elective_structure([PAGE], "https://x/c.pdf", "2026-01-01")
    by = {(r["semester"], r["slot_type"]): r for r in recs}
    assert by[("VI", "DE")]["number_of_slots"] == 1 and by[("VI", "DE")]["credits_per_slot"] == 3
    assert by[("VI", "Minor")]["printed_below_total"] is True
    assert by[("VII", "IDE")]["source_page"] == 1 and by[("VII", "HSS Elective")]["credits_per_slot"] == 3
    assert all(r["source_url"] and r["fetched_at"] for r in recs)


def test_second_table_with_same_header_is_an_option_list_not_slots():
    two = PAGE + page("SEMESTER VI", "1. CS3301 Option A 3 0 0 3", "2. XX41PQ IDE-IX 3 0 0 3")
    rows, _ = parse_tables([two])
    assert [r["table_index"] for r in rows if r["code"] in ("CS3301", "CS3201")] == [0, 1]
    assert not any(r["slot_labels"] == ["IDE-IX"] for r in elective_structure([two], "u"))
