"""Parsing: every format into the same normalized text, built byte for byte in the test; bad files raise ParseError."""

from __future__ import annotations

import json

import pytest

from axelrod_ingest.parse import Parsed, ParseError, Segment, _cell, mime_of, normalize, parse, supported
from tests.ingest.builders import docx, para, pdf, pptx, xlsx, zip_of


def _spans_exact(p: Parsed) -> None:
    text = p.text
    for a, b, seg in p.spans():
        assert text[a:b] == seg.text


# -- normalize ------------------------------------------------------------------------------------------------------
def test_normalize_collapses_spaces_and_blank_runs_and_unifies_newlines():
    raw = "  Rates\u00a0 rose\t\u2009 sharply \r\nnext\rline\fpage\n\n\n\n\nlast \u3000 word  "
    assert normalize(raw) == "Rates rose sharply\nnext\nline\npage\n\nlast word"


def test_normalize_composes_unicode_and_keeps_curly_quotes_and_dashes():
    assert normalize("Cafe\u0301 “dollar” — up") == "Café “dollar” — up"


def test_normalize_is_idempotent():
    once = normalize("a  b\n\n\n\nc\r\nd ")
    assert normalize(once) == once


# -- Parsed -------------------------------------------------------------------------------------------------------
def test_parsed_text_joins_non_empty_segments_and_spans_index_it_exactly():
    p = Parsed("x", (Segment("one", 1), Segment("", 2), Segment("two\nlines", 3), Segment("", 4), Segment("3", 5)))
    assert p.text == "one\n\ntwo\nlines\n\n3"
    assert [(a, b, s.page) for a, b, s in p.spans()] == [(0, 3, 1), (5, 14, 3), (16, 17, 5)]
    _spans_exact(p)


# -- PDF ------------------------------------------------------------------------------------------------------------
def test_pdf_pages_become_segments_with_title_from_metadata():
    data = pdf(["The bank raised its policy rate to 4.25% (a 25bp hike).", "Bond yields rose."], title="Policy note")
    p = parse(data, "note.pdf")
    assert p.format == "pdf" and p.title == "Policy note" and p.meta == {"pages": 2}
    assert [s.page for s in p.segments] == [1, 2]
    assert "bank raised its policy rate to 4.25% (a 25bp hike)." in p.segments[0].text
    assert p.segments[1].text == "Bond yields rose."
    _spans_exact(p)


def test_pdf_without_metadata_has_empty_title():
    p = parse(pdf(["Crude rose."]), "x.PDF")
    assert p.title == "" and p.text == "Crude rose."


@pytest.mark.parametrize("data", [b"", b"not a pdf at all", b"%PDF-1.4\n garbage without a trailer"])
def test_corrupted_pdf_raises_parse_error(data):
    with pytest.raises(ParseError, match="not a readable PDF"):
        parse(data, "bad.pdf")


# -- DOCX -----------------------------------------------------------------------------------------------------------
def test_docx_paragraphs_tabs_and_breaks():
    body = (para() + para("Rates", "\t", "note") + "<w:p><w:r><w:t/></w:r></w:p>"
            + para("The Bank ", "raised rates.", "\n", "Bond yields rose."))
    p = parse(docx(body), "memo.docx")
    assert p.format == "docx"
    assert p.text == "Rates note\n\nThe Bank raised rates.\nBond yields rose."
    assert p.title == "Rates note"
    assert [s.page for s in p.segments] == [None]


def test_docx_title_is_truncated_and_empty_document_parses_empty():
    p = parse(docx(para("x" * 300)), "long.docx")
    assert p.title == "x" * 160
    empty = parse(docx(""), "empty.docx")
    assert empty.text == "" and empty.title == "" and empty.spans() == []


@pytest.mark.parametrize("data,why", [
    (b"PK not really a zip", "not a valid Office file"),
    (zip_of({"other.xml": "<x/>"}), "not a valid DOCX"),
    (zip_of({"word/document.xml": "<w:document"}), "not a valid DOCX"),
])
def test_corrupted_docx_raises_parse_error(data, why):
    with pytest.raises(ParseError, match=why):
        parse(data, "bad.docx")


# -- PPTX -----------------------------------------------------------------------------------------------------------
def test_pptx_slides_in_number_order_with_pages_and_title():
    data = pptx({10: ["Slide ten"], 2: ["Dollar outlook", "Dollar index fell to 104."], 1: []},
                extra={"ppt/slides/_rels/slide1.xml.rels": "<r/>", "ppt/slideLayouts/slideLayout1.xml": "<l/>"})
    p = parse(data, "deck.pptx")
    assert p.format == "pptx" and p.meta == {"slides": 3}
    assert [(s.page, s.text) for s in p.segments] == [(1, ""), (2, "Dollar outlook\nDollar index fell to 104."),
                                                       (3, "Slide ten")]
    assert p.title == "Dollar outlook"
    assert p.text == "Dollar outlook\nDollar index fell to 104.\n\nSlide ten"
    _spans_exact(p)


def test_pptx_with_no_text_has_empty_title():
    assert parse(pptx({1: []}), "blank.pptx").title == ""


@pytest.mark.parametrize("data,why", [
    (b"garbage", "not a valid Office file"),
    (zip_of({"ppt/presentation.xml": "<p/>"}), "no slides"),
    (zip_of({"ppt/slides/slide1.xml": "<p:sld"}), "not a valid PPTX: ppt/slides/slide1.xml"),
])
def test_corrupted_pptx_raises_parse_error(data, why):
    with pytest.raises(ParseError, match=why):
        parse(data, "bad.pptx")


# -- XLSX -----------------------------------------------------------------------------------------------------------
def test_xlsx_sheets_rows_and_cell_values():
    data = xlsx({"Rates": [["Name", "Value", None, None], ["Bank", 4.25, None, None], [None, None],
                           ["Board", 2.0, 7, "pct"], [3e-10]],
                 "Empty": []})
    p = parse(data, "book.xlsx")
    assert p.format == "xlsx" and p.meta == {"sheets": ["Rates", "Empty"]} and p.title == ""
    assert p.segments[0] == Segment("Sheet: Rates\nName | Value\nBank | 4.25\nBoard | 2 | 7 | pct\n3e-10", page=1,
                                    label="Rates")
    assert p.segments[1] == Segment("", page=2, label="Empty")
    assert p.text == p.segments[0].text
    _spans_exact(p)


def test_xlsm_uses_the_xlsx_parser():
    assert parse(xlsx({"S": [["a"]]}), "macro.xlsm").text == "Sheet: S\na"


@pytest.mark.parametrize("value,text", [(None, ""), (2.0, "2"), (4.25, "4.25"), (2.00000000001, "2"),
                                        (0.1 + 0.2, "0.3"), (3e-10, "3e-10"), (7, "7"), ("x", "x"), (True, "True"),
                                        ("FY26\nCurrent", "FY26 Current"), ("a\r\nb", "a  b")])
def test_cell_renders_values_deterministically(value, text):
    assert _cell(value) == text


@pytest.mark.parametrize("data", [b"garbage", zip_of({"a.txt": "x"}), zip_of({"[Content_Types].xml": "<Types/>"})])
def test_corrupted_xlsx_raises_parse_error(data):
    with pytest.raises(ParseError, match="not a valid XLSX"):
        parse(data, "bad.xlsx")


# -- HTML -----------------------------------------------------------------------------------------------------------
def test_html_skips_scripts_and_styles_keeps_title_blocks_and_tables():
    html = b"""<!doctype html><html><head><title>Bank &amp; the dollar</title><style>p{color:red}</style>
    <script>var x = "Crude rose";</script></head><body><noscript>enable js</noscript>
    <h1>Rates</h1><p>The Bank <b>raised</b> rates.</p></script><span>inline</span></span>
    <table><tr><th>Name</th><th>Rate</th></tr><tr><td>Bank</td><td>4.25%</td></tr></table>
    <ul><li>one</li><li>two</li></ul><template>hidden</template>tail<br>end</body></html>"""
    p = parse(html, "page.html")
    assert p.format == "html" and p.title == "Bank & the dollar"
    assert p.text == "Rates\n\nThe Bank raised rates.\ninline\n\nName | Rate\n\nBank | 4.25%\n\none\n\ntwo\n\ntail\nend"
    for hidden in ("color", "Crude", "enable js", "hidden"):
        assert hidden not in p.text


def test_htm_extension_and_html_mime_fallback():
    assert parse(b"<p>x</p>", "a.htm").text == "x"
    assert parse(b"<p>x</p>", "upload.bin", "text/html").format == "html"


# -- CSV, Markdown, text ----------------------------------------------------------------------------------------------
def test_csv_rows_joined_with_bars_and_empty_rows_dropped():
    p = parse(b'name,rate\r\n"Bank, Home",4.25\r\n,\r\n\r\nBoard,2.25\r\n', "rates.csv")
    assert p.format == "csv" and p.text == "name | rate\nBank, Home | 4.25\nBoard | 2.25" and p.title == ""


def test_markdown_title_is_first_heading_without_hashes():
    p = parse(b"\n\n## Bank hikes\n\nThe Bank raised rates.\n", "note.md")
    assert p.format == "markdown" and p.title == "Bank hikes" and p.text == "## Bank hikes\n\nThe Bank raised rates."
    assert parse(b"# x", "n.markdown").format == "markdown"


@pytest.mark.parametrize("data", [
    "Dollar — café".encode(),
    b"\xef\xbb\xbf" + "Dollar — café".encode(),
    "Dollar — café".encode("utf-16"),
    "Dollar — café".encode("utf-16-be").join([b"\xfe\xff", b""]),
])
def test_text_decodes_utf8_bom_and_utf16(data):
    p = parse(data, "a.txt")
    assert p.format == "text" and p.text == "Dollar — café" and p.title == "Dollar — café"


def test_text_falls_back_to_latin1_when_not_utf8():
    assert parse("café ±".encode("latin-1"), "a.text").text == "café ±"


def test_empty_text_file_parses_empty():
    p = parse(b"", "a.txt")
    assert p.text == "" and p.title == "" and p.spans() == []


# -- JSON -------------------------------------------------------------------------------------------------------------
def test_plain_json_is_pretty_printed_with_sorted_keys():
    p = parse(json.dumps({"b": [1, "€"], "a": {"c": None}}).encode(), "data.json")
    assert p.format == "json" and p.meta == {}
    assert p.text == '{\n"a": {\n"c": null\n},\n"b": [\n1,\n"€"\n]\n}'  # lines stripped


def test_import_bundle_json_is_passed_through_whole():
    bundle = {"format": "axelrod.import/v1", "title": "Desk notes", "items": [
        {"id": "A", "headline": "Bank hikes", "summary": "The Bank raised rates."}, "not an item",
        {"id": "B", "headline": "Dollar up"}]}
    p = parse(json.dumps(bundle).encode(), "bundle.json")
    assert p.format == "bundle" and p.title == "Desk notes" and p.meta == {"bundle": bundle}
    assert p.text == "Bank hikes\nThe Bank raised rates.\n\nDollar up"


def test_import_bundle_without_items_or_title():
    p = parse(b'{"format": "axelrod.import/v1", "items": null}', "b.json")
    assert p.format == "bundle" and p.text == "" and p.title == ""


@pytest.mark.parametrize("data", [b"{not json", b""])
def test_invalid_json_raises_parse_error(data):
    with pytest.raises(ParseError, match="not valid JSON"):
        parse(data, "bad.json")


# -- dispatch ---------------------------------------------------------------------------------------------------------
def test_extension_wins_over_mime_and_is_case_insensitive():
    assert parse(b"# t", "NOTE.MD", "application/json").format == "markdown"


@pytest.mark.parametrize("mime,fmt", [("text/plain", "text"), ("text/csv", "csv"), ("text/markdown", "markdown"),
                                      ("application/json", "json")])
def test_mime_fallback_when_extension_unknown(mime, fmt):
    assert parse(b"[1]", "upload", mime).format == fmt


@pytest.mark.parametrize("name,mime,why", [("a.exe", "", r"\.exe"), ("upload", "image/png", "image/png"),
                                           ("upload", "", "unknown")])
def test_unsupported_type_raises_parse_error(name, mime, why):
    with pytest.raises(ParseError, match=f"unsupported file type: {why}"):
        parse(b"x", name, mime)


def test_mime_of_and_supported():
    assert mime_of("a.PDF") == "application/pdf"
    assert mime_of("a.docx").endswith("wordprocessingml.document")
    assert mime_of("a.md") == "text/markdown"
    assert mime_of("a.xlsm") == "application/octet-stream"     # parsed, but no MIME of its own
    assert mime_of("noext") == "application/octet-stream"
    assert supported("a.xlsm") and supported("x", "text/csv") and supported("A.HTM")
    assert not supported("a.exe") and not supported("x", "image/png")


def test_parse_is_deterministic():
    data = docx(para("The Bank raised rates.") + para("Bond yields rose 10bp."))
    assert parse(data, "a.docx") == parse(data, "a.docx")
