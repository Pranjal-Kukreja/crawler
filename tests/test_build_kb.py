"""Tests for the Step 5 builder helpers and the Step 6 validator."""
import json

import pytest

from src import validate
from src.build_kb import build_courses, conflicts_of, merged, programme_courses, split_codes, stem, version

DOC = {"programme": "B.Tech X", "department": "physics", "url": "https://x/a.pdf", "fetched_at": "2026-01-01"}
DOC2 = {"programme": "M.Sc Y", "department": "chemistry", "url": "https://x/b.pdf", "fetched_at": "2026-01-02"}


def test_codes_alternates_split_and_placeholders_dropped():
    assert split_codes("PH1101/PH1201") == ["PH1101", "PH1201"]
    assert split_codes("XX41PQ") == [] and split_codes("HS21XX") == [] and split_codes("") == []


def test_merged_returns_empty_instead_of_picking_when_values_differ():
    assert merged(["3", "", "3"]) == ("3", [])
    assert merged(["3", "4"]) == ("", ["3", "4"])


def test_stem_keeps_the_pdfs_wording():
    assert stem("Departmental Elective – I") == "departmental_elective"
    assert stem("Interdisciplinary Elective (IDE)") == "interdisciplinary_elective_ide"


def test_same_text_in_two_documents_is_one_version_and_no_conflict():
    a = version("detail_block", DOC, "PH1101", 5, title="Physics", credits="5.5", syllabus_text="Waves and optics.")
    b = version("detail_block", DOC2, "PH1101", 9, title="PHYSICS", credits="5.5", syllabus_text="Waves  and optics")
    (course,) = build_courses([a, b])
    assert course["n_versions"] == 1 and not course["conflict"] and len(course["versions"][0]["sources"]) == 2
    assert course["departments"] == ["chemistry", "physics"] and course["department"] == ""
    assert course["title"] == "Physics" and course["credits"] == "5.5"


def test_different_credits_keep_both_versions_and_leave_the_field_empty():
    a = version("semester_table", DOC, "CE4299", 3, title="Project II", credits="6", L="0", T="0", P="12")
    b = version("semester_table", DOC2, "CE4299", 4, title="Project II", credits="8.0", L="0", T="0", P="16")
    (course,) = build_courses([a, b])
    assert course["conflict"] and set(course["conflict_fields"]) == {"credits", "ltp"}
    assert course["credits"] == "" and course["L"] == "" and course["title"] == "Project II"
    assert {s["source_url"] for v in course["versions"] for s in v["sources"]} == {"https://x/a.pdf", "https://x/b.pdf"}


def test_a_missing_description_in_one_version_is_not_a_conflict():
    a = version("detail_block", DOC, "PH2", 5, title="T", syllabus_text="Real text.")
    b = version("semester_table", DOC, "PH2", 2, title="T")
    assert conflicts_of([a, b]) == []


def test_nil_and_none_prerequisites_agree():
    a = version("detail_block", DOC, "PH3", 5, prerequisites="Nil")
    b = version("detail_block", DOC2, "PH3", 5, prerequisites="None")
    assert conflicts_of([a, b]) == []


def entry(kind, **kw):
    base = {"programme": "P", "department": "d", "code": "AB1234", "kind": kind, "semester": "", "group": "",
            "credits": "3", "L": "3", "T": "0", "P": "0", "page": 4, "source_url": "u", "fetched_at": "t",
            "listed_as": ""}
    return {**base, **kw}


def test_programme_course_takes_semester_from_the_table_and_type_from_the_elective_list():
    recs = programme_courses([entry("semester_table", semester="VI", page=3),
                              entry("option_list", group="Departmental Elective – I", page=9),
                              entry("detail_block", page=20)])
    (r,) = recs
    assert (r["semester"], r["course_type"], r["elective_group"], r["source_page"]) == (
        "VI", "departmental_elective", "Departmental Elective – I", 3)
    assert r["evidence"] == ["semester_table", "option_list", "detail_block"]


def test_programme_course_without_a_stated_type_stays_empty_and_two_semesters_are_not_picked():
    (r,) = programme_courses([entry("semester_table", semester="III"), entry("semester_table", semester="IV")])
    assert r["course_type"] == "" and r["semester"] == "" and r["semesters_listed"] == ["III", "IV"]


def write_out(tmp_path, monkeypatch, **overrides):
    monkeypatch.setattr(validate, "OUT", tmp_path)
    rec = {"source_url": "u", "fetched_at": "t"}
    data = {"courses.jsonl": [{"course_code": "AB1", **rec, "conflict": False, "conflict_fields": [], "versions": []}],
            "programme_courses.jsonl": [{"programme": "P", "department": "d", "course_code": "AB1", **rec}],
            "rules.jsonl": [{"rule_type": "other", **rec}], "elective_structure.jsonl": [{"slot_type": "DE", **rec}],
            "minor_lists.jsonl": [{"minor": "m", **rec}]}
    data.update(overrides)
    for name, rs in data.items():
        (tmp_path / name).write_text("".join(json.dumps(r) + "\n" for r in rs))


def test_validator_passes_good_files(tmp_path, monkeypatch, capsys):
    write_out(tmp_path, monkeypatch)
    validate.main()
    assert "VALIDATION PASSED" in capsys.readouterr().out


def test_validator_fails_on_missing_fetched_at(tmp_path, monkeypatch):
    write_out(tmp_path, monkeypatch, **{"rules.jsonl": [{"rule_type": "other", "source_url": "u", "fetched_at": ""}]})
    with pytest.raises(SystemExit) as e:
        validate.main()
    assert e.value.code == 1


def test_validator_fails_on_duplicate_and_empty_course_codes(tmp_path, monkeypatch):
    good = {"source_url": "u", "fetched_at": "t", "conflict": False, "conflict_fields": [], "versions": []}
    write_out(tmp_path, monkeypatch, **{"courses.jsonl": [{"course_code": "AB1", **good}, {"course_code": "AB1", **good}]})
    with pytest.raises(SystemExit):
        validate.main()
    write_out(tmp_path, monkeypatch, **{"courses.jsonl": [{"course_code": "", **good}]})
    with pytest.raises(SystemExit):
        validate.main()
