from src.department_overview import parse_courses_page

HTML = """<html><head><title>Courses - Department of Physics | IIT Patna</title></head><body>
<div><div>B.Tech in Engineering Physics</div><div>Duration : 4 years</div><p>Four-year programme.</p>
<a href="/files/ph.pdf">Click here for detailed Syllabus and Curriculum</a></div>
<div><div>PhD</div><div>Duration : 3 years</div><p></p><a href="https://x.org/y.html">Click here for detailed Syllabus</a></div>
</body></html>"""


def test_one_record_per_programme_card():
    recs = parse_courses_page(HTML, "https://www.iitp.ac.in/departments/physics/courses", "2026-01-01")
    assert [(r["programme"], r["duration"], r["description"]) for r in recs] == [
        ("B.Tech in Engineering Physics", "4 years", "Four-year programme."), ("PhD", "3 years", "")]
    assert recs[0]["department"] == "physics" and recs[0]["department_name"] == "Department of Physics"
    assert recs[0]["syllabus_url"] == "https://www.iitp.ac.in/files/ph.pdf" and recs[0]["fetched_at"] == "2026-01-01"
