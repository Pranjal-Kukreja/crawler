"""Tests for the pure parts of the minors extractor (row parsing and the heading patterns)."""
from src.minors_extract import HEADING, LINE_ROW, SPLIT_CODE, SPLIT_NUMS, row_to_record


def test_table_row_with_semester_column():
    r = row_to_record(["1.", "Sem III", "CB2103", "Heat Transfer", "3", "0", "3", "4.5"])
    assert (r["semester"], r["course_code"], r["title"], r["L"], r["T"], r["P"], r["credits"]) == (
        "Sem III", "CB2103", "Heat Transfer", "3", "0", "3", "4.5")


def test_wrapped_title_cell_is_joined():
    r = row_to_record(["4.", "CE3202", "Minor IV: Infrastructure Drawing and\nEstimation", "1", "2", "0", "3"])
    assert r["title"] == "Minor IV: Infrastructure Drawing and Estimation" and r["credits"] == "3"


def test_any_one_option_row_keeps_its_option_marker():
    r = row_to_record(["ii.", "PH3206", "Laser Physics", None, None, "3", "0", "0", "3"])
    assert (r["option"], r["course_code"], r["title"]) == ("ii", "PH3206", "Laser Physics")


def test_row_without_a_course_code_is_not_a_course():
    assert row_to_record(["TOTAL", None, None, "14", "0", "6", "17"]) is None
    assert row_to_record(["4. Minor-IV (Any One)", None, None]) is None


def test_headings_and_notes():
    assert HEADING.match("Minor in Thermal Engineering").group(1) == "Minor in Thermal Engineering"
    m = HEADING.match("Minor in Business Studies: (Only open to B. Tech. / BS-MBA Dual Degree)")
    assert m.group(1) == "Minor in Business Studies" and "Only open" in m.group(2)
    assert HEADING.match("B. Tech. in Civil Engineering and Minor in Infrastructure Engineering") is None


def test_borderless_line_and_page_break_rows():
    assert LINE_ROW.match("Minor-I CS2101 Algorithm 3 0 3 4.5").groups() == (
        "Minor-I", "CS2101", "Algorithm", "3", "0", "3", "4.5")
    assert SPLIT_CODE.match("ME3201 Applied Thermodynamics and").group(1) == "ME3201"
    assert SPLIT_NUMS.match("4. 3 1 2 5").groups() == ("3", "1", "2", "5")
