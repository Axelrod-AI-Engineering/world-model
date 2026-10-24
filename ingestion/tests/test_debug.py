"""The stage debugger's dry run (Oct 24): it answers what `Ingestor.process` stores, in the same order with the same
functions, and it writes nothing. Every document is invented."""

from __future__ import annotations

from array import array
from datetime import UTC, datetime

import pytest

import axelrod_ingest.debug as debug
from axelrod_ingest.debug import dry_run
from axelrod_ingest.dedupe import link_duplicates
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.sqlite import SQLiteLake
from axelrod_ingest.pack import lake_digest
from axelrod_ingest.parse import Parsed, Segment
from axelrod_ingest.pipeline import Ingestor
from tests.conftest import acme_graph
from tests.ingest.test_dedupe import FIGURES, report

NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)
T = "desk"
EMB = HashingEmbedder()
NOTE = (b"# Policy watch\n\nThe central bank raised its policy rate by 25bp to 4.25%. Government bonds 10Y yield rose "
        b"10bp, and the dollar index rose 2%.\n\nHigher government bonds 10Y yield lifts Acme Re domestic P&C profit.\n")
LONG = ("Quarterly results for the quarter ended 30 September 2026. " + "A sentence with several words in it " * 60
        + ". Revenue 1,234,567.\n\n" + "Short one. Another short one.").encode()
ZH = "截至2025年12月31日止年度的合并业绩。营业收入为人民币777,102百万元。净利润为人民币8,102百万元。".encode()
MENU = b"<html><body><ul><li>Home</li><li>About</li><li>Login</li></ul></body></html>"


def ingestor(store, **kw):
    return Ingestor(store, EMB, clock=lambda: NOW, timer=lambda: 0.0, **kw)


def stage(res, key):
    return next(s for s in res["stages"] if s["id"] == key)


def run(data, name, **kw):
    return dry_run(data, name, embedder=EMB, clock=lambda: NOW, **kw)


def test_a_dry_run_equals_what_the_pipeline_stores(tmp_path):
    store = SQLiteLake(tmp_path / "a")
    pub = datetime(2026, 9, 1, tzinfo=UTC)
    for data, name in ((NOTE, "policy_2026-10-05.md"), (LONG, "results.txt"), (ZH, "zh.txt")):
        res = run(data, name, published_at=pub, vectors=True)
        real = ingestor(store).ingest_file(T, data, name, acme_graph(), published_at=pub)
        doc = store.get_document(T, real.document.id)
        assert [s["status"] for s in res["stages"][:5]] == ["ok"] * 5 and res["stopped"] is None
        t = stage(res, "type")["data"]
        assert t["doc_type"] == doc.meta["doc_type"] and t["dates"] == doc.meta["dates"]
        assert t["language"] == doc.meta["language"] and t["yen"] == doc.meta["currency"]["yen"]
        assert t["source_type"] == doc.source_type and t["published_at"] == doc.published_at.isoformat()
        shown = stage(res, "chunk")["data"]["chunks"]
        assert [(c["ord"], c["start"], c["end"], c["page"], c["section"], c["text"]) for c in shown] == [
            (c.ord, c.start, c.end, c.page, c.section, c.text) for c in store.get_chunks(T, doc.id)]
        # the store keeps float32: the same vectors, as that type holds them
        assert [array("f", v).tolist() for v in stage(res, "index")["data"]["embedding"]["vectors"]] == [
            v for d, _o, v in store.embeddings(T, EMB.name) if d == doc.id]
        assert stage(res, "parse")["data"]["text"] == store.get_text(T, doc.id)[0]
        assert stage(res, "store")["data"]["doc_id"] == doc.id


def test_a_stored_document_dry_runs_as_it_was_stored_and_nothing_is_written(tmp_path):
    store = SQLiteLake(tmp_path / "b")
    real = ingestor(store).ingest_file(T, NOTE, "policy_2026-10-05.md", acme_graph())
    before = lake_digest(store, T)
    res = run(NOTE, "policy_2026-10-05.md", store=store, tenant=T, ingested_at=real.document.ingested_at)
    new = run(LONG, "fresh.txt", store=store, tenant=T)
    assert lake_digest(store, T) == before and store.stats(T)["documents"] == 1
    assert stage(res, "store")["data"]["stored"]["status"] == "extracted"
    assert stage(res, "store")["decision"] == "already in the lake"
    assert stage(new, "store")["data"]["stored"] is None and "not in the lake" in stage(new, "store")["decision"]
    # the nearest stored passages leave the document's own chunks out; a new file finds the stored ones
    assert all(h["doc_id"] != real.document.id for n in stage(res, "index")["data"]["nearest"] for h in n["hits"])
    nearest = stage(new, "index")["data"]["nearest"]
    assert nearest and nearest[0]["hits"][0]["doc_id"] == real.document.id and nearest[0]["hits"][0]["text"]


def test_a_parse_error_is_a_failed_card_and_the_rest_are_skipped():
    res = run(b"not a pdf", "broken.pdf")
    assert res["stopped"]["stage"] == "parse" and stage(res, "parse")["status"] == "failed"
    assert stage(res, "parse")["data"]["error"] == res["stopped"]["reason"]
    assert [s["status"] for s in res["stages"]] == ["ok", "failed", "skipped", "skipped", "skipped", "skipped"]
    assert "not reached" in stage(res, "chunk")["decision"]


def test_an_excluded_page_stops_at_the_type_stage():
    res = run(MENU, "menu.html", screen=True)
    t = stage(res, "type")
    assert t["status"] == "stopped" and t["data"]["doc_type"]["excluded"] and res["stopped"]["stage"] == "type"
    assert t["decision"].startswith("excluded from extraction") and stage(res, "chunk")["status"] == "skipped"
    assert "excluded" in stage(res, "index")["decision"]


def test_a_scan_with_no_ocr_engine_stops_as_needs_ocr(monkeypatch):
    monkeypatch.setattr(debug, "parse", lambda *a, **k: Parsed("pdf", (Segment("", page=1),), meta={"needs_ocr": [1]}))
    res = run(b"%PDF", "scan.pdf")
    assert stage(res, "type")["status"] == "stopped" and "needs_ocr" in res["stopped"]["reason"]
    seg = stage(res, "parse")["data"]["segments"][0]
    assert seg["chars"] == 0 and seg["start"] is None and stage(res, "parse")["data"]["needs_ocr"] == [1]


def test_chunks_show_their_sentences_weights_and_the_long_sentence_cut():
    res = run(LONG, "results.txt")
    c = stage(res, "chunk")["data"]
    assert any(x["cut"] for x in c["chunks"]) and not all(x["cut"] for x in c["chunks"])
    assert all(len(x["sentences"]) >= 1 and x["weight"] <= c["limit"] for x in c["chunks"])
    h = c["histogram"]
    assert sum(b["count"] for b in h["bins"]) + h["over"] == len(c["chunks"]) and h["over"] == 0
    assert "cut from a long sentence" in stage(res, "chunk")["decision"]


def test_a_table_row_over_the_limit_is_counted_over_and_never_cut():
    row = (" | ".join(f"c{k}" for k in range(400)) + "\n").encode()
    res = run(row, "wide.csv")
    d = stage(res, "chunk")["data"]
    assert d["histogram"]["over"] == 1 and not any(c["cut"] for c in d["chunks"])


def test_the_index_card_has_terms_norms_and_vectors():
    d = stage(run(NOTE, "n.md"), "index")["data"]
    terms = {t["term"]: t["norm"] for c in d["keyword"]["chunks"] for t in c["terms"]}
    assert terms["bonds"] == "bond" and terms["10y"] == "10y" and "Porter" in d["keyword"]["note"]
    e = d["embedding"]
    assert e["name"] == EMB.name and e["dim"] == EMB.dim and e["vectors"] is None
    assert all(abs(c["norm"] - 1.0) < 1e-3 and len(c["head"]) == 8 and "vector" not in c for c in e["chunks"])
    assert d["nearest"] is None                                             # no lake: nothing to search


def test_the_detail_is_capped_on_a_long_document(monkeypatch, tmp_path):
    monkeypatch.setattr(debug, "DETAIL_CHUNKS", 2)
    monkeypatch.setattr(debug, "NEAREST_CHUNKS", 1)
    store = SQLiteLake(tmp_path / "cap")
    text = "\n\n".join(f"Paragraph {k} says that the policy rate rose." for k in range(5)).encode()
    d = stage(run(text, "p.txt", store=store, tenant=T), "index")["data"]
    assert len(d["embedding"]["chunks"]) == 2 and len(d["keyword"]["chunks"]) == 2 and len(d["nearest"]) == 1


def seeded(tmp_path):
    store = SQLiteLake(tmp_path / "dup")
    ing = ingestor(store)
    ids = {k: ing.ingest_file(T, report(line, figs), f"{k}.txt", acme_graph()).document.id for k, line, figs in (
        ("en", "Consolidated results for the year ended 31 December 2025 under IFRS.", FIGURES),
        ("sum", "Annual report summary for the year ended 31 December 2025.", FIGURES[:45]),
        ("later", "Results for the year ended 31 December 2026.", FIGURES))}
    return store, ids


def test_duplicates_are_compared_against_the_stored_documents_of_the_same_period(tmp_path):
    store, ids = seeded(tmp_path)
    # a new Chinese copy of the same year: it would join the English filing's group, which stays primary
    zh = report("截至2025年12月31日止年度的合并业绩。", FIGURES[:70])
    d = stage(run(zh, "zh.txt", store=store, tenant=T), "duplicates")
    assert d["data"]["period_end"] == "2025-12-31" and d["data"]["figures"] > 40
    assert {c["doc_id"] for c in d["data"]["compared"]} == {ids["en"], ids["sum"]}      # not the other year
    assert d["data"]["group"]["primary"] == ids["en"] and d["data"]["group"]["role"] == "duplicate"
    assert "would join" in d["decision"]
    # the same answer the batch linker gives once it is stored
    zid = ingestor(store).ingest_file(T, zh, "zh.txt", acme_graph()).document.id
    (g,) = link_duplicates(store, T)
    assert g.primary == ids["en"] and zid in g.members and set(d["data"]["group"]["members"]) == set(g.members)
    # a stored document run again does not compare itself with itself
    again = stage(run(zh, "zh.txt", store=store, tenant=T), "duplicates")
    assert zid not in {c["doc_id"] for c in again["data"]["compared"]}


def test_a_distinct_document_and_a_document_without_a_period(tmp_path):
    store, _ids = seeded(tmp_path)
    other = report("For the year ended 31 December 2025, other group.", [f"{900000 + k}" for k in range(60)])
    d = stage(run(other, "o.txt", store=store, tenant=T), "duplicates")
    assert d["data"]["group"] is None and "none is the same disclosure" in d["decision"]
    d = stage(run(NOTE, "n.md", store=store, tenant=T), "duplicates")
    assert "never matched" in d["decision"] and d["data"]["compared"] is None
    assert stage(run(NOTE, "n.md"), "duplicates")["decision"] == "no lake to compare against"


def test_a_stored_document_that_has_lost_its_text_still_compares(tmp_path):
    store, ids = seeded(tmp_path)
    store.put_text(T, ids["sum"], "", "x")
    data = report("Year ended 31 December 2025.", FIGURES)
    assert {c["doc_id"] for c in stage(run(data, "x.txt", store=store, tenant=T), "duplicates")["data"]["compared"]} == {
        ids["en"], ids["sum"]}
    store.delete_document(T, ids["sum"])
    assert {c["doc_id"] for c in stage(run(data, "x.txt", store=store, tenant=T), "duplicates")["data"]["compared"]} == {
        ids["en"]}


def test_every_stage_has_its_timing_and_the_stages_come_in_order():
    ticks = iter(range(0, 1000))
    res = run(NOTE, "n.md", timer=lambda: next(ticks) / 10)
    assert [s["id"] for s in res["stages"]] == ["store", "parse", "type", "chunk", "index", "duplicates"]
    assert all(s["seconds"] > 0 for s in res["stages"]) and pytest.approx(stage(res, "parse")["seconds"]) == 0.1
