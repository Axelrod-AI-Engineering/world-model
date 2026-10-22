"""OCR for pages that are pictures: found, read by an engine when there is one, cached by content, and reported as
`needs_ocr` when there is not, so a scan never parses to nothing without a word. The engine here is a shell script."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from axelrod_ingest import ocr as ocr_module
from axelrod_ingest.ocr import Ocr, OcrError, Tesseract, find_tesseract, ocr_from_env, pgm_of
from axelrod_ingest.parse import parse
from tests.ingest.builders import scanned_pdf


def engine(tmp_path: Path, *, version: str = "tesseract 9.9.9", body: str | None = None, name: str = "tesseract") -> Path:
    """A fake `tesseract`: prints a version for --version, else saves the page it is given and writes text."""
    script = tmp_path / name
    log = tmp_path / "calls.log"
    body = body if body is not None else f'cat > "{tmp_path}/page.pgm"; echo "Slide text 4.5%"; echo "RMB 3bn"'
    script.write_text(f'#!/bin/sh\nif [ "$1" = "--version" ]; then echo "{version}"; echo " leptonica-1.0"; exit 0; fi\n'
                      f'echo "$@" >> "{log}"\n{body}\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def make(tmp_path: Path, **kw) -> Ocr:
    found = find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path, **kw))})
    assert found is not None
    return Ocr(found, tmp_path / "cache")


def test_the_engine_is_found_with_its_version(tmp_path):
    e = find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path)), "AXELROD_OCR_LANG": "eng+chi_sim"})
    assert e == Tesseract(str(tmp_path / "tesseract"), "9.9.9", "eng+chi_sim")
    assert e.config == "lang=eng+chi_sim psm=3 oem=1 dpi=200 threads=1"


def test_a_missing_or_silent_engine_is_none(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert find_tesseract({}) is None and find_tesseract() is None
    assert find_tesseract({"AXELROD_TESSERACT": str(tmp_path / "nowhere")}) is None
    assert find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path, version="tesseract"))}) is None   # no version number
    bad = engine(tmp_path, name="broken")
    bad.write_text("#!/bin/sh\nexit 3\n")
    assert find_tesseract({"AXELROD_TESSERACT": str(bad)}) is None
    quiet = engine(tmp_path, name="quiet")
    quiet.write_text("#!/bin/sh\nexit 0\n")
    assert find_tesseract({"AXELROD_TESSERACT": str(quiet)}) is None
    old = engine(tmp_path, name="old")
    old.write_text('#!/bin/sh\necho "tesseract 4.1.1" >&2\n')                 # older builds print the version on stderr
    assert find_tesseract({"AXELROD_TESSERACT": str(old)}).version == "4.1.1"


def test_the_engine_is_found_on_the_path(tmp_path, monkeypatch):
    engine(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_tesseract().version == "9.9.9"


def test_ocr_from_env(tmp_path):
    exe = str(engine(tmp_path))
    assert ocr_from_env({"AXELROD_OCR": "off", "AXELROD_TESSERACT": exe}) is None
    assert ocr_from_env({"AXELROD_TESSERACT": str(tmp_path / "nowhere")}) is None
    assert ocr_from_env({"AXELROD_TESSERACT": exe}).cache_dir is None
    assert ocr_from_env({"AXELROD_TESSERACT": exe, "WORLD_MODEL_LAKE_DIR": str(tmp_path / "lake")}).cache_dir == tmp_path / "lake" / "ocr"
    got = ocr_from_env({"AXELROD_TESSERACT": exe, "AXELROD_OCR_CACHE": str(tmp_path / "c"), "WORLD_MODEL_LAKE_DIR": "x"})
    assert got.cache_dir == tmp_path / "c" and got.meta == {"engine": "tesseract", "version": "9.9.9", "config": got.engine.config}


def test_the_engine_runs_with_a_fixed_configuration(tmp_path, monkeypatch):
    monkeypatch.setenv("TESSDATA_PREFIX", "/somewhere/tessdata")
    e = find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path))})
    assert e.read(b"P5\n1 1\n255\n\x00") == "Slide text 4.5%\nRMB 3bn\n"
    assert calls(tmp_path) == ["stdin stdout -l eng --psm 3 --oem 1 --dpi 200"]
    assert (tmp_path / "page.pgm").read_bytes().startswith(b"P5\n1 1\n255\n")


def test_an_engine_that_fails_or_cannot_run_is_an_ocr_error(tmp_path, monkeypatch):
    failing = find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path, body='echo "no data" >&2; exit 2'))})
    with pytest.raises(OcrError, match="failed \\(2\\): no data"):
        failing.read(b"")
    with pytest.raises(OcrError, match="could not run"):
        Tesseract(str(tmp_path / "nowhere"), "1").read(b"")
    monkeypatch.setattr(ocr_module, "TIMEOUT_SECONDS", 0.2)
    slow = find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path, body="sleep 5"))})
    with pytest.raises(OcrError, match="could not run"):
        slow.read(b"")


def test_pages_are_cached_by_content_and_the_image_is_drawn_only_on_a_miss(tmp_path):
    o = make(tmp_path)
    drawn = []

    def image() -> bytes:
        drawn.append(1)
        return b"P5\n1 1\n255\n\x00"

    first = o.page_text("a" * 64, 3, image)
    again = o.page_text("a" * 64, 3, image)
    assert first == again == "Slide text 4.5%\nRMB 3bn\n" and len(drawn) == 1 and len(calls(tmp_path)) == 1
    o.page_text("a" * 64, 4, image)                          # another page, another entry
    o.page_text("b" * 64, 3, image)                          # another document
    assert len(calls(tmp_path)) == 3
    assert len(list((tmp_path / "cache").rglob("*.txt"))) == 3 and not list((tmp_path / "cache").rglob("*.tmp"))
    assert o.key("a" * 64, 3) != o.key("a" * 64, 4)


def test_a_new_engine_version_does_not_reuse_the_cache(tmp_path):
    one, two = make(tmp_path), make(tmp_path, version="tesseract 10.0.0")
    assert one.key("c" * 64, 1) != two.key("c" * 64, 1)


def test_without_a_cache_the_engine_runs_each_time(tmp_path):
    o = Ocr(find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path))}))
    o.page_text("d" * 64, 1, lambda: b"")
    o.page_text("d" * 64, 1, lambda: b"")
    assert len(calls(tmp_path)) == 2


def test_the_pgm_drops_row_padding():
    assert pgm_of(2, 2, 4, bytes([1, 2, 0, 0, 3, 4, 0, 0])) == b"P5\n2 2\n255\n" + bytes([1, 2, 3, 4])


# -- the PDF parser -----------------------------------------------------------------------------------------------------
def test_a_scanned_pdf_is_read_page_by_page_when_an_engine_is_there(tmp_path):
    o = make(tmp_path)
    p = parse(scanned_pdf(["A text page with enough letters to be a text layer", None, "", None]), "deck.pdf", ocr=o)
    assert [s.text for s in p.segments] == ["A text page with enough letters to be a text layer",
                                            "Slide text 4.5%\nRMB 3bn", "", "Slide text 4.5%\nRMB 3bn"]
    assert p.meta == {"pages": 4, "ocr": {"engine": "tesseract", "version": "9.9.9", "config": o.engine.config,
                                          "pages": [2, 4]}}
    # the page the engine was given is the page, drawn at 200 dpi as a gray map: 612x792 points is 1700x2200 pixels
    assert (tmp_path / "page.pgm").read_bytes().startswith(b"P5\n1700 2200\n255\n")
    assert len((tmp_path / "page.pgm").read_bytes()) == len(b"P5\n1700 2200\n255\n") + 1700 * 2200


def test_the_same_scan_read_again_gives_the_same_text_without_the_engine(tmp_path):
    o = make(tmp_path)
    data = scanned_pdf([None])
    one = parse(data, "deck.pdf", ocr=o)
    again = parse(data, "deck.pdf", ocr=o)
    assert one == again and len(calls(tmp_path)) == 1


def test_a_scanned_pdf_without_an_engine_is_marked_needs_ocr():
    p = parse(scanned_pdf(["Text page with plenty of letters on it", None, "~", ""]), "deck.pdf")
    assert p.meta == {"pages": 4, "needs_ocr": [2]} and p.segments[1].text == ""      # a rule or a blank page is not a scan
    assert parse(scanned_pdf([None, None]), "d.pdf").meta == {"pages": 2, "needs_ocr": [1, 2]}


def test_a_page_the_engine_fails_on_is_needs_ocr_not_silent(tmp_path):
    o = make(tmp_path, body="exit 1")
    p = parse(scanned_pdf([None, "Plenty of letters on a text page here"]), "deck.pdf", ocr=o)
    assert p.meta == {"pages": 2, "needs_ocr": [1]} and "ocr" not in p.meta


def test_a_picture_with_only_a_footer_on_it_is_a_scan_and_a_text_page_with_a_picture_is_not(tmp_path):
    o = make(tmp_path)
    p = parse(scanned_pdf(["^12", "^A page of real text with a large logo image behind it"]), "x.pdf", ocr=o)
    assert p.segments[0].text == "Slide text 4.5%\nRMB 3bn" and p.meta["ocr"]["pages"] == [1]
    assert p.segments[1].text.startswith("A page of real text")
