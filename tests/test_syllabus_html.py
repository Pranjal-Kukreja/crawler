"""Tests for the HTML syllabus parser, on a tiny page shaped like the real one."""
from src.syllabus_html import IDE_LABEL, elective_structure, parse_syllabus_page

ROW = "<tr><td>{n}.</td><td>{code}</td><td class='subject-name'><span>{title} ▼</span></td><td>3</td><td>0</td><td>0</td><td>{c}</td></tr>"
DETAIL = ("<tr class='syllabus-row'><td><div><table>"
          "<tr><th>Course Number</th><td>{code}</td></tr>"
          "<tr><th>Course Description</th><td>{desc}</td></tr></table></div></td></tr>")


def section(label, rows):
    return f"<li><label>{label}</label><div class='content'><table><tbody>{rows}</tbody></table></div></li>"


HTML = "<ul class='accordian'>" + section("Semester I",
    ROW.format(n=1, code="MA1101", title="Calculus", c="4.0") + DETAIL.format(code="MA1101", desc="Limits and  vectors.")
    + ROW.format(n=2, code="IK1201", title="Indian Knowledge System", c="2") + DETAIL.format(code="IK1201", desc="")
    + ROW.format(n=3, code="CB41PQ", title="DE-II", c="3") + DETAIL.format(code="CB41PQ", desc="Copy of a real elective.")
    + ROW.format(n=4, code="XX41PQ", title="IDE-III", c="3") + DETAIL.format(code="XX41PQ", desc="")) \
    + section("Elective - DE-I", ROW.format(n=1, code="MA1101", title="Calculus", c="4.0") + DETAIL.format(code="MA1101", desc="Limits and  vectors.")) \
    + section("IDE Floated by the Department (not applicable for B. Tech. Chemical Engineering students)",
              ROW.format(n=1, code="CB4108", title="Bioprocess", c="3") + DETAIL.format(code="CB4108", desc="Bioreactors.")) \
    + "</ul>"


def parse():
    return parse_syllabus_page(HTML, "chemical-engineering", "B.Tech in Chemical Engineering", "https://x/y.html")


def test_one_record_per_course_with_the_agreed_fields():
    first = parse()[0]
    assert first == {"course_code": "MA1101", "title": "Calculus", "department": "chemical-engineering",
                     "programme": "B.Tech in Chemical Engineering", "semester": "Semester I", "credits": "4.0",
                     "L": "3", "T": "0", "P": "0", "course_type": "", "mode": "", "prerequisites": "", "syllabus_text": "",
                     "learning_objectives": "", "description": "Limits and vectors.",
                     "source_url": "https://x/y.html", "fetched_at": ""}


def test_stated_fields_are_picked_up_and_unstated_ones_stay_empty():
    detail = ("<tr class='syllabus-row'><td><table>"
              "<tr><th>Learning Mode</th><td>Classroom lectures</td></tr>"
              "<tr><th>Pre-requisites</th><td>MA1101</td></tr>"
              "<tr><th>Learning Objectives:</th><td>Learn limits.</td></tr>"
              "<tr><th>Course Outline</th><td>Unit 1. Limits</td></tr></table></td></tr>")
    html = "<ul class='accordian'>" + section("Elective - DE-I", ROW.format(n=1, code="X1", title="T", c="3") + detail) + "</ul>"
    r = parse_syllabus_page(html, "d", "p", "u", "2026-01-01")[0]
    assert (r["mode"], r["prerequisites"], r["learning_objectives"], r["syllabus_text"], r["course_type"]) == (
        "Classroom lectures", "MA1101", "Learn limits.", "Unit 1. Limits", "department_elective")
    assert r["description"] == "" and r["fetched_at"] == "2026-01-01"


def test_elective_slot_placeholders_are_dropped_but_real_courses_without_description_stay():
    codes = [r["course_code"] for r in parse()]
    assert "CB41PQ" not in codes and "XX41PQ" not in codes   # with or without a description
    iks = next(r for r in parse() if r["course_code"] == "IK1201")
    assert iks["description"] == ""


def test_same_course_in_semester_and_elective_group_is_kept_twice():
    ma = [r["semester"] for r in parse() if r["course_code"] == "MA1101"]
    assert ma == ["Semester I", "Elective - DE-I"]


def test_ide_group_is_relabelled():
    assert next(r for r in parse() if r["course_code"] == "CB4108")["semester"] == IDE_LABEL


def test_course_type_uses_only_what_the_page_says():
    types = {r["course_code"]: r["course_type"] for r in parse()}
    assert types["IK1201"] == ""                               # plain semester table: not called core
    assert types["CB4108"] == "interdisciplinary_elective"     # "IDE Floated by the Department"


TOTAL = "<tr><td>TOTAL</td><td>9</td><td>0</td><td>2</td><td>{t}</td></tr>"
SLOTS = ("<ul class='accordian'>" + section("Semester VII",
    ROW.format(n=1, code="CB41PQ", title="DE-II", c="3") + DETAIL.format(code="CB41PQ", desc="")
    + ROW.format(n=2, code="XX41PQ", title="IDE-III", c="3") + DETAIL.format(code="XX41PQ", desc="")
    + ROW.format(n=3, code="HS31XX", title="HSS Elective-II", c="3")
    + ROW.format(n=4, code="CB4199", title="Project - I", c="6") + TOTAL.format(t="15"))
    + section("Elective - DE-II", ROW.format(n=1, code="CB4101", title="A", c="3")
              + ROW.format(n=2, code="CB4102", title="B", c="3"))
    + "</ul><p>DE-II - Department Elective-II Options. IDE-III (Interdisciplinary Elective-III)</p>")


def test_elective_slots_with_credits_meaning_and_option_counts():
    slots = elective_structure(SLOTS, "d", "p", "u")
    assert [(s["slot"], s["credits"], s["slot_means"], s["options_listed"]) for s in slots] == [
        ("DE-II", 3.0, "Department Elective", 2),
        ("IDE-III", 3.0, "Interdisciplinary Elective", None),
        ("HSS Elective-II", 3.0, "HSS Elective", None)]
    assert slots[0]["semester_total_credits_printed"] == slots[0]["semester_total_credits_summed"] == 15


def test_slot_meaning_stays_empty_when_the_page_does_not_say():
    html = SLOTS.replace("(Interdisciplinary Elective-III)", "")
    assert next(s for s in elective_structure(html, "d", "p", "u") if s["slot"] == "IDE-III")["slot_means"] == ""
