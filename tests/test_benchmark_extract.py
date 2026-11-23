"""Tests for the main-content text used to compare the two scrapers."""
from benchmark.extract import coverage, main_text, words

PAGE = """<html><head><style>p{}</style><script>var secret=1</script></head><body>
<header>Site header</header><nav>Menu one Menu two</nav>
<main><h1>Programmes</h1><p>B.Tech in  Physics</p>
<div class="collapse" style="display:none">Hidden syllabus text</div></main>
<aside>Side bar</aside><footer>Copyright</footer></body></html>"""


def test_only_main_content_is_kept_and_collapsed_text_stays():
    text = main_text(PAGE)
    assert text == "Programmes B.Tech in Physics Hidden syllabus text"


def test_falls_back_to_body_when_there_is_no_main():
    assert main_text("<body><nav>x</nav><p>Hello  world</p><footer>f</footer></body>") == "Hello world"


def test_coverage_counts_repeated_words_and_is_one_for_empty():
    assert coverage("a b b c", "a b c") == 0.75          # one of the two b's is missing
    assert coverage("", "anything") == 1.0
    assert coverage("Fees: 5,000", "fees 5 000") == 1.0
    assert words("B.Tech-2024") == ["b", "tech", "2024"]


def test_site_footer_list_is_excluded_by_name_and_nothing_else():
    from benchmark.extract import strip_site_footer
    footer = ("Home About Visit News Academics Admissions Students Campus Life Alumni Administration Research "
              "Departments Services & Amenities Innovation Hub Opportunities Miscellaneous Contact Us")
    assert strip_site_footer(f"Courses BTech Physics Privacy Policy {footer}") == "Courses BTech Physics Privacy Policy"
    assert strip_site_footer("Home About Visit News") == "Home About Visit News"      # a partial list is page text
