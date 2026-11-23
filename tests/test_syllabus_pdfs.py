"""Tests for the academics-host PDF allowlist, header-only requests and PDF collection."""
import httpx
import pytest

from src.fetcher import Fetcher, Refused
from src.syllabus_pdfs import download_all, head_all, split_programme
from tests.test_fetcher import CFG, FakeClock

PDF_URL = "https://academics.iitp.ac.in/revised_syllabus/a.pdf"


def make(tmp_path, handler):
    urls = tmp_path / "pdf_urls.txt"
    urls.write_text(PDF_URL + "\n")
    cfg = {**CFG, "pdf_downloads": {"host": "academics.iitp.ac.in", "urls_file": str(urls)},
           "fetch": {**CFG["fetch"], "raw_dir": str(tmp_path / "raw")}}
    seen = []

    def wrapped(request):
        seen.append((request.method, request.url.host, request.url.path))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return handler(request)

    clock = FakeClock()
    f = Fetcher(cfg, client=httpx.Client(transport=httpx.MockTransport(wrapped)),
                sleep=clock.sleep, clock=clock.now)
    return f, seen


def test_listed_pdf_is_allowed_but_nothing_else_on_that_host(tmp_path):
    f, seen = make(tmp_path, lambda r: httpx.Response(200, content=b"%PDF-1.4"))
    assert f.fetch(PDF_URL).content == b"%PDF-1.4"
    for other in ["https://academics.iitp.ac.in/", "https://academics.iitp.ac.in/sitemap.xml",
                  "https://academics.iitp.ac.in/revised_syllabus/b.pdf"]:
        with pytest.raises(Refused):
            f.fetch(other)
    assert all(path in ("/robots.txt", "/revised_syllabus/a.pdf") for _, _, path in seen)


def test_head_sends_head_and_reads_size(tmp_path):
    f, seen = make(tmp_path, lambda r: httpx.Response(200, headers={"content-length": "1234"}))
    sizes = head_all([{"url": PDF_URL}], f)
    assert sizes == {PDF_URL: 1234}
    assert ("HEAD", "academics.iitp.ac.in", "/revised_syllabus/a.pdf") in seen


@pytest.mark.parametrize("status,headers", [(405, {}), (200, {})])
def test_head_not_answered_properly_stops(tmp_path, status, headers):
    f, _ = make(tmp_path, lambda r: httpx.Response(status, headers=headers))
    with pytest.raises(RuntimeError):
        head_all([{"url": PDF_URL}], f)


def test_download_saves_by_programme_name_and_checks_pdf(tmp_path):
    f, _ = make(tmp_path, lambda r: httpx.Response(200, content=b"%PDF-1.4 data"))
    rows = [{"department": "physics", "programme": "B.Tech. in Eng. Physics & Maths", "url": PDF_URL}]
    saved = download_all(rows, f, tmp_path / "out")
    assert saved[0][0] == tmp_path / "out" / "physics" / "btech-in-eng-physics-maths.pdf"
    assert saved[0][0].read_bytes() == b"%PDF-1.4 data"


def test_download_rejects_a_non_pdf(tmp_path):
    f, _ = make(tmp_path, lambda r: httpx.Response(200, content=b"<html>error</html>"))
    with pytest.raises(RuntimeError):
        download_all([{"department": "x", "programme": "p", "url": PDF_URL}], f, tmp_path / "out")


def test_programme_name_comes_from_the_card_text():
    assert split_programme("B.Tech. in Artificial Intelligence Duration : 4 years", "x.pdf") == (
        "B.Tech. in Artificial Intelligence", "4 years")
    assert split_programme("", "x.pdf") == ("x.pdf", "")


def test_extra_urls_file_is_also_allowed_and_nothing_beyond_it(tmp_path):
    extra = tmp_path / "extra.txt"
    extra.write_text("https://academics.iitp.ac.in/index.php?option=com_content&view=article&id=46\n")
    f, seen = make(tmp_path, lambda r: httpx.Response(200, text="<html>ok</html>"))
    f.extra_urls |= {u for u in extra.read_text().split()}   # what the config key does at start-up
    assert f.fetch("https://academics.iitp.ac.in/index.php?option=com_content&view=article&id=46").status == 200
    with pytest.raises(Refused):
        f.fetch("https://academics.iitp.ac.in/index.php?option=com_content&view=article&id=47")
