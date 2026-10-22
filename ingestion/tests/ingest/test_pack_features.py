"""The pipeline on the packs' problems: pages with no content are excluded with a reason, scans are read by OCR or marked
needs_ocr, dates and periods are kept apart, a bare ¥ is resolved from the document, a manifest types a file. Invented files."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.ocr import Ocr, find_tesseract
from axelrod_ingest.pipeline import Ingestor
from tests.ingest.builders import pdf, scanned_pdf
from tests.ingest.multilingual import world
from tests.ingest.test_ocr import calls, engine

T = "acme"
NOW = datetime(2026, 10, 22, tzinfo=UTC)
G = world()
PROSE = ("<p>Acme EV reported results for the period. Management said the quarter went well across all of its regions and "
         "that margins improved as the mix shifted toward higher value models, while costs were flat.</p>") * 5


def html(body: str, title: str = "Results") -> bytes:
    return f"<html><head><title>{title}</title></head><body>{body}</body></html>".encode()


def make(lake, **kw) -> Ingestor:
    return Ingestor(lake, HashingEmbedder(), clock=lambda: NOW, **kw)


# -- pages with no content -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name,data,reason", [
    ("001_INDEX_ONLY_Quarterly-Archive.html", html(PROSE), "named an index"),
    ("page.html", html("<script>window.x=1</script><p>Please enable JavaScript to continue.</p>"), "gated"),
    ("page.html", html("<ul>" + "<li>Menu item</li>" * 30 + "</ul>"), "a list of links"),
    ("blank.pdf", pdf(["12"]), "no content"),
])
def test_a_page_with_no_content_is_excluded_with_its_reason(lake, name, data, reason):
    res = make(lake, screen=True).ingest_file(T, data, name, G)
    doc = res.document
    assert doc.status == "excluded" and reason in doc.error and res.bundle is None and res.chunks == 0
    assert res.warnings == [f"excluded from extraction: {doc.error}"] and doc.source_type == "other"
    assert doc.meta["doc_type"]["excluded"] is True and lake.get_chunks(T, doc.id) == [] and lake.get_text(T, doc.id) is not None


def test_screening_is_off_by_default_and_never_touches_a_typed_upload_or_a_note(lake):
    index = html(PROSE)
    off = make(lake).ingest_file(T, index, "001_INDEX_ONLY_Archive.html", G)
    assert off.document.status == "extracted" and off.document.meta["doc_type"]["excluded"] is False
    typed = make(lake, screen=True).ingest_file(T, html("<p>Short.</p>"), "short.html", G, source_type="news")
    assert typed.document.status == "extracted" and typed.document.source_type == "news"
    note = make(lake, screen=True).ingest_file(T, b"# Short\n\nA note.", "note.md", G)
    assert note.document.status == "extracted"


def test_a_document_read_again_without_screening_comes_back(lake):
    data = html(PROSE)
    first = make(lake, screen=True).ingest_file(T, data, "001_INDEX_ONLY_Archive.html", G)
    assert first.document.status == "excluded"
    again = make(lake).process(T, first.document.id, G)
    assert again.document.status == "extracted" and again.chunks > 0 and again.document.error == ""
    assert lake.get_chunks(T, first.document.id)


# -- scans ---------------------------------------------------------------------------------------------------------------------
def test_a_scan_without_an_engine_is_marked_needs_ocr_and_nothing_is_extracted(lake):
    res = make(lake).ingest_file(T, scanned_pdf([None, None]), "deck.pdf", G)
    doc = res.document
    assert doc.status == "needs_ocr" and res.bundle is None and res.chunks == 0 and "2 page(s)" in doc.error
    assert doc.meta["needs_ocr"] == [1, 2] and res.warnings == [doc.error] and lake.get_chunks(T, doc.id) == []


def test_a_partly_scanned_pdf_is_read_and_its_missing_pages_are_reported(lake):
    res = make(lake).ingest_file(T, scanned_pdf(["Acme EV net profit: CNY 8.5bn for the year, said the company.", None]),
                                 "mixed.pdf", G)
    assert res.document.status == "extracted" and res.signals == 1 and res.document.meta["needs_ocr"] == [2]
    assert res.warnings == ["page(s) [2] have no text layer and no OCR engine read them: needs_ocr"]


def test_a_scan_is_read_by_the_engine_and_its_version_is_recorded(lake, tmp_path):
    exe = find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path, body='cat >/dev/null; echo "Acme EV net profit: CNY 8.5bn"'))})
    ing = make(lake, ocr=Ocr(exe, tmp_path / "cache"))
    res = ing.ingest_file(T, scanned_pdf([None]), "deck.pdf", G)
    doc = res.document
    assert doc.status == "extracted" and res.signals == 1 and "needs_ocr" not in doc.meta
    assert doc.meta["ocr"] == {"engine": "tesseract", "version": "9.9.9", "config": exe.config, "pages": [1]}
    assert lake.get_text(T, doc.id)[0] == "Acme EV net profit: CNY 8.5bn"
    again = ing.process(T, doc.id, G)                                   # read again: same text, same bundle, no engine run
    assert again.bundle == res.bundle and len(calls(tmp_path)) == 1


def test_a_scan_marked_needs_ocr_is_read_when_an_engine_arrives(lake, tmp_path):
    first = make(lake).ingest_file(T, scanned_pdf([None]), "deck.pdf", G)
    assert first.document.status == "needs_ocr"
    exe = find_tesseract({"AXELROD_TESSERACT": str(engine(tmp_path, body='cat >/dev/null; echo "Acme EV net profit: CNY 8.5bn"'))})
    later = make(lake, ocr=Ocr(exe, tmp_path / "cache")).process(T, first.document.id, G)
    assert later.document.status == "extracted" and later.document.error == "" and later.signals == 1
    assert "needs_ocr" not in later.document.meta and later.document.meta["ocr"]["pages"] == [1]


def test_text_with_no_pages_at_all_is_a_warning_not_a_silence(lake):
    res = make(lake).ingest_file(T, b"", "empty.txt", G)
    assert res.warnings == ["no text could be read from the document", "no claims about the model's values were found"]


# -- dates and periods ------------------------------------------------------------------------------------------------------------
MANIFEST = {"file": "x", "url": "https://www.hkexnews.hk/a/b.pdf", "section": "Business", "rank": 1, "sha256": "ab" * 32}


def test_a_manifest_file_is_dated_by_its_name_and_keeps_its_period(lake):
    text = b"Acme EV net profit: CNY 8.5bn.\nFor the six months ended 30 June 2026 the company reported results on 5 October 2026."
    res = make(lake).ingest_file(T, text, "001_1_28-Aug-2026_interim.txt", G, meta={"manifest": MANIFEST})
    doc, item = res.document, res.bundle.bundle["items"][0]
    assert doc.published_at == datetime(2026, 8, 28, tzinfo=UTC) == doc.event_time
    assert doc.meta["dates"]["published_source"] == "manifest" and doc.meta["dates"]["period_end"] == "2026-06-30"
    assert item["published_at"].startswith("2026-08-28") and item["occurred_at"].startswith("2026-06-30")
    assert "period:2026-H1" in item["tags"] and "doc_type:filing" in item["tags"] and "lang:en" in item["tags"]
    assert doc.source_type == "filing" and item["source_type"] == "filing" and item["kind"] == "filing"
    assert doc.meta["manifest"]["sha256_matches"] is False and doc.meta["manifest"]["url"].endswith("b.pdf")


def test_a_forward_period_gives_no_occurred_at(lake):
    text = b"Acme EV net profit: CNY 8.5bn.\nGuidance for FY2027."
    res = make(lake).ingest_file(T, text, "001_1_29-Jan-2026_guidance.txt", G, meta={"manifest": MANIFEST})
    item = res.bundle.bundle["items"][0]
    assert res.document.meta["dates"]["period_forward"] is True and item["occurred_at"] is None and "period:2027" in item["tags"]


def test_a_name_without_a_date_leaves_the_document_dated_when_it_arrived(lake):
    res = make(lake).ingest_file(T, b"Acme EV net profit: CNY 8.5bn.", "001_2_undated_notes.txt", G, meta={"manifest": MANIFEST})
    assert res.document.published_at is None and res.document.event_time == NOW
    assert res.document.meta["dates"] == {"published_source": "ingested_at"}


def test_a_date_after_arrival_is_not_the_publication(lake):
    res = make(lake).ingest_file(T, b"Acme EV net profit: CNY 8.5bn. Results due 2027-02-01.", "notes.txt", G)
    assert res.document.published_at is None and res.document.event_time == NOW


def test_reading_a_document_again_keeps_its_dates_and_an_uploaded_date(lake):
    ing = make(lake)
    first = ing.ingest_file(T, b"Acme EV net profit: CNY 8.5bn. Note of 2026-09-01.", "a.txt", G)
    again = ing.process(T, first.document.id, G)
    assert again.document == first.document and again.bundle == first.bundle
    up = ing.ingest_file(T, b"Acme EV net profit: CNY 9.5bn. Note of 2026-09-01.", "b.txt", G, published_at=datetime(2026, 9, 3))
    assert up.document.published_at == datetime(2026, 9, 3, tzinfo=UTC) and up.document.meta["dates"]["published_source"] == "upload"
    assert ing.process(T, up.document.id, G).document == up.document


# -- ¥ -----------------------------------------------------------------------------------------------------------------------------
def test_a_bare_yen_sign_is_yuan_in_a_prc_issuers_document_and_yen_otherwise(lake):
    prc = ("Acme EV (A joint stock company incorporated in the People’s Republic of China)\n\n"
           "Acme EV revenue was ¥120bn in the year.").encode()
    other = b"Acme Japan revenue was \xc2\xa541tn in the year."
    a = make(lake).ingest_file(T, prc, "prc.txt", G)
    assert a.signals == 1 and a.bundle.bundle["items"][0]["signals"][0]["value"] == 120.0
    assert a.document.meta["currency"]["yen"] == {"code": "CNY", "basis": "issuer", "signs": 1, "cny_words": 0, "jpy_words": 0,
                                                  "language": "en", "issuer_country": "CN"}
    b = make(lake).ingest_file(T, other, "jp.txt", G)
    assert b.signals == 1 and b.document.meta["currency"]["yen"]["code"] == "JPY"
    c = make(lake).ingest_file(T, "Acme EV revenue was ¥120bn in the year.".encode(), "plain.txt", G)
    assert c.signals == 0 and c.document.meta["currency"]["yen"]["basis"] == "default"      # yen is not the value's yuan


def test_a_chinese_document_is_read_end_to_end(lake):
    text = "艾克米电动股份有限公司\n\n2025年度，艾克米电动营业收入为人民币1,200亿元，净利润为人民币85.6亿元。同比增长。\n".encode()
    res = make(lake).ingest_file(T, text, "zh.txt", G)
    sigs = {s["value_of"]: s["value"] for s in res.bundle.bundle["items"][0]["signals"]}
    assert sigs == {"acme_ev.revenue": 120.0, "acme_ev.net_profit": 8.56}
    assert res.document.meta["language"] == "zh" and "lang:zh" in res.bundle.bundle["items"][0]["tags"]
    assert res.document.meta["dates"]["period"] == "2025"


# -- the manifest and the type -------------------------------------------------------------------------------------------------
def test_the_manifest_types_a_file_and_an_explicit_type_wins(lake):
    ing = make(lake)
    text = b"Acme EV net profit: CNY 8.5bn."
    a = ing.ingest_file(T, text, "x.txt", G, meta={"manifest": {**MANIFEST, "url": "https://www.calls.example.com/q/transcripts/1"}})
    assert a.document.source_type == "expert_call" and a.document.meta["doc_type"]["type"] == "transcript"
    b = ing.ingest_file(T, text + b" ", "y.txt", G, source_type="news", meta={"manifest": MANIFEST})
    assert b.document.source_type == "news" and b.document.meta["doc_type"]["type"] == "filing"


def test_store_file_keeps_the_meta_it_is_given(lake):
    doc, new = make(lake).store_file(T, b"x", "x.txt", meta={"hints": {"issuer_country": "CN"}})
    assert new and doc.meta == {"hints": {"issuer_country": "CN"}}
    res = make(lake).process(T, doc.id, G)
    assert res.document.meta["hints"] == {"issuer_country": "CN"}
    assert res.document.meta["currency"]["yen"]["issuer_country"] == "CN"


def test_a_json_document_that_is_not_text_still_carries_the_derived_meta(lake):
    res = make(lake).ingest_file(T, json.dumps({"a": 1}).encode(), "a.json", G)
    assert res.document.meta["format"] == "json" and res.document.meta["doc_type"]["type"] == "other"
