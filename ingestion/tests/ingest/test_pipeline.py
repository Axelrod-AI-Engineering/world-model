"""The pipeline: a file stored once by content, parsed, chunked, indexed, read against the model, and turned into a
validated import bundle; failures are recorded on the document, never raised past it."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from axelrod_ingest import EXTRACTOR_VERSION
from axelrod_ingest.gazetteer import Gazetteer
from axelrod_ingest.lake.embed import HashingEmbedder
from axelrod_ingest.lake.store import content_id
from axelrod_ingest.pipeline import KIND_OF, SOURCE_TYPES, Ingestor, _utc, bundle_id
from axelrod_wm.intake.bundle import ImportBundle
from tests.ingest.conftest import NOW

T = "acme"
NOTE = (b"# Central bank watch\n\nPublished 2026-10-05.\n\nThe central bank raised its policy rate by 25bp to 4.25%. "
        b"Government bonds 10Y yield rose.\n\nAcme Re said overseas profit should benefit.\n\nNothing about the model here.")
OVERSEAS = "Acme Re said overseas profit should benefit."


def quotes_hold(bundle: dict) -> None:
    ImportBundle.model_validate(bundle)
    for item in bundle["items"]:
        text = f"{item['headline']}\n{item['summary']}"
        for s in item["signals"]:
            assert s["quote"] and s["quote"] in text


class FakeProvider:
    name, model = "fake", "fake-1"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append(user.split("Passage:\n", 1)[1])
        return json.dumps({"signals": [
            {"type": "support", "source": "dollar.index", "target": "acme_re.international_profit",
             "quote": OVERSEAS}]})


# -- storing --------------------------------------------------------------------------------------------------------------
def test_utc():
    naive = datetime(2026, 10, 5, 9)
    assert _utc(naive) == datetime(2026, 10, 5, 9, tzinfo=UTC)
    offset = datetime(2026, 10, 5, 9, tzinfo=timezone(timedelta(hours=9)))
    assert _utc(offset) is offset


def test_store_file_stores_once_by_content(ingestor):
    doc, new = ingestor.store_file(T, NOTE, "note.md", source="Desk", source_type="broker_research", uploaded_by="u")
    assert new and doc.id == content_id(NOTE) and doc.size == len(NOTE) and doc.mime == "text/markdown"
    assert doc.ingested_at == doc.event_time == NOW and doc.published_at is None and doc.status == "stored"
    again, new2 = ingestor.store_file(T, NOTE, "renamed.md", source="Other")
    assert not new2 and again == doc


def test_store_file_validates_source_type_and_normalizes_times(ingestor):
    with pytest.raises(ValueError, match="source_type must be one of"):
        ingestor.store_file(T, b"x", "a.txt", source_type="blog")
    doc, _ = ingestor.store_file(T, b"x", "a.txt", mime="text/x-custom", published_at=datetime(2026, 9, 1, 8))
    assert doc.published_at == doc.event_time == datetime(2026, 9, 1, 8, tzinfo=UTC) and doc.mime == "text/x-custom"


def test_clock_without_a_timezone_is_read_as_utc(lake):
    ing = Ingestor(lake, HashingEmbedder(), clock=lambda: datetime(2026, 10, 17, 9, 30))
    doc, _ = ing.store_file(T, b"x", "a.txt")
    assert doc.ingested_at == NOW.replace(minute=30)


def test_default_clock_is_now(lake):
    doc, _ = Ingestor(lake, HashingEmbedder()).store_file(T, b"x", "a.txt")
    assert abs(doc.ingested_at - datetime.now(UTC)) < timedelta(minutes=1)


# -- processing ---------------------------------------------------------------------------------------------------------------
def test_process_unknown_document_raises(ingestor, graph):
    with pytest.raises(KeyError):
        ingestor.process(T, "nope", graph)


def test_parse_failure_marks_the_document_failed(ingestor, lake, graph):
    res = ingestor.ingest_file(T, b"%PDF-1.4 broken", "bad.pdf", graph)
    assert res.new and res.bundle is None and res.document.status == "failed"
    assert res.document.error.startswith("not a readable PDF") and res.warnings == [res.document.error]
    assert lake.get_document(T, res.document.id).status == "failed" and lake.get_text(T, res.document.id) is None


def test_missing_raw_bytes_parse_as_empty(ingestor, lake, graph, tmp_path):
    doc, _ = ingestor.store_file(T, b"Crude oil price rose.", "a.txt")
    for p in (tmp_path / "lake").rglob(f"{doc.id}*"):
        p.unlink()
    res = ingestor.process(T, doc.id, graph)
    assert res.chunks == 0 and res.bundle.items == 0 and res.warnings


def test_ingest_markdown_end_to_end(ingestor, lake, graph):
    res = ingestor.ingest_file(T, NOTE, "note.md", graph, source="Desk", source_type="broker_research")
    doc = res.document
    assert res.new and doc.status == "extracted" and doc.title == "Central bank watch"
    assert doc.published_at == doc.event_time == datetime(2026, 10, 5, tzinfo=UTC) and doc.ingested_at == NOW
    assert doc.meta == {"format": "markdown"}
    text, parser = lake.get_text(T, doc.id)
    assert parser == "markdown/parse-1.0" and text == NOTE.decode()
    chunks = lake.get_chunks(T, doc.id)
    assert res.chunks == len(chunks) == 5 and [c.ord for c in chunks] == list(range(5))
    assert all(text[c.start:c.end] == c.text for c in chunks)
    assert len(lake.embeddings(T, "hashing-256")) == 5
    ms = lake.mentions_of(T, doc_id=doc.id)
    assert res.mentions == len(ms) and {m.entity_id for m in ms} == {"central_bank", "gov_bonds", "acme_re"}
    rec = res.bundle
    assert rec.id == bundle_id(rec.bundle) and rec.doc_ids == [doc.id] and rec.created_at == NOW
    assert rec.extractor_version == EXTRACTOR_VERSION and lake.get_bundle(T, rec.id) == rec
    b = rec.bundle
    assert b["title"] == "Central bank watch" and b["collected_by"] == f"axelrod ingest {EXTRACTOR_VERSION}"
    assert b["synthetic"] is False and b["collected_at"] == NOW.isoformat().replace("+00:00", "Z")
    (item,) = b["items"]
    assert item["id"] == f"D{doc.id[:10]}-0002" and item["kind"] == "analyst" and item["source"] == "Desk"
    # "raised its policy rate by 25bp to 4.25%": a level and a move, both claimed
    assert [(s["type"], s["value_of"]) for s in item["signals"]] == [("observe", "central_bank.policy_rate"),
                                                                     ("move", "central_bank.policy_rate")]
    assert res.signals == rec.signals == 2 and rec.items == 1 and res.llm_signals == 0 and res.warnings == []
    assert b["description"] == (f"Extracted from note.md ({doc.id}) against the world model's names (gazetteer "
                                f"{Gazetteer(graph).digest}): 2 signal(s) in 1 item(s).")
    quotes_hold(b)


def test_a_document_with_nothing_for_the_model_warns(ingestor, graph):
    res = ingestor.ingest_file(T, b"Weather was fine.", "w.txt", graph)
    assert res.bundle.items == 0 and res.signals == 0
    assert res.warnings == ["no claims about the model's values were found"]
    assert res.document.status == "extracted"


@pytest.mark.parametrize("source_type,kind", [("data", "data"), ("filing", "filing"), ("expert_call", "analyst"),
                                              ("news", "news"), ("other", "news")])
def test_item_kind_follows_the_source_type(ingestor, graph, source_type, kind):
    res = ingestor.ingest_file(T, b"Crude oil price rose 3%.", f"{source_type}.txt", graph, source_type=source_type)
    assert res.bundle.bundle["items"][0]["kind"] == kind == KIND_OF.get(source_type, "news")
    assert source_type in SOURCE_TYPES


# -- event time and title ----------------------------------------------------------------------------------------------
def test_event_time_prefers_the_given_date(ingestor, graph):
    given = datetime(2026, 9, 1, tzinfo=UTC)
    res = ingestor.ingest_file(T, NOTE, "note_2026-08-01.md", graph, published_at=given)
    assert res.document.published_at == res.document.event_time == given
    assert res.bundle.bundle["items"][0]["published_at"] == "2026-09-01T00:00:00Z"


def test_event_time_from_text_then_file_name_then_ingestion(ingestor, graph):
    a = ingestor.ingest_file(T, b"Dated 2026-10-05: Crude oil price rose.", "x_2026-08-01.txt", graph).document
    b = ingestor.ingest_file(T, b"Crude oil price rose.", "x_2026-08-01.txt", graph).document
    c = ingestor.ingest_file(T, b"Crude oil price fell.", "x.txt", graph).document
    assert a.event_time == datetime(2026, 10, 5, tzinfo=UTC)
    assert b.event_time == b.published_at == datetime(2026, 8, 1, tzinfo=UTC)
    assert c.event_time == NOW and c.published_at is None


def test_title_falls_back_to_the_file_name(ingestor, graph):
    res = ingestor.ingest_file(T, b"name,rate\nCentral bank,4.25\n", "rates.csv", graph)
    assert res.document.title == "rates.csv" and res.bundle.bundle["title"] == "rates.csv"


def test_reprocessing_keeps_the_title_and_date(ingestor, graph):
    first = ingestor.ingest_file(T, NOTE, "note.md", graph)
    again = ingestor.process(T, first.document.id, graph)
    assert again.document.title == first.document.title and again.document.event_time == first.document.event_time
    assert again.bundle == first.bundle and not again.new


# -- import bundles uploaded as files -------------------------------------------------------------------------------------
def test_an_import_bundle_is_passed_through(ingestor, lake, graph):
    bundle = {"format": "axelrod.import/v1", "title": "Agent bundle", "items": [
        {"id": "EM-1", "published_at": "2026-10-01T06:00:00Z", "source": "Agent", "headline": "Central bank hikes",
         "summary": "The central bank raised rates to 4.25%.", "entities": ["central_bank"],
         "signals": [{"type": "observe", "value_of": "central_bank.policy_rate", "value": 4.25,
                      "quote": "The central bank raised rates to 4.25%."}]}]}
    res = ingestor.ingest_file(T, json.dumps(bundle).encode(), "bundle.json", graph)
    assert res.new and res.document.status == "extracted" and res.document.title == "Agent bundle"
    assert res.document.meta == {"format": "bundle"} and res.chunks == 1 and res.signals == 1 and res.mentions == 0
    assert res.bundle.bundle == ImportBundle.model_validate(bundle).model_dump(mode="json")
    assert res.bundle.items == 1 and res.bundle.id == bundle_id(res.bundle.bundle)
    assert res.document.event_time == NOW                         # no date in its text
    quotes_hold(res.bundle.bundle)


def test_a_file_that_claims_to_be_a_bundle_and_is_not_fails(ingestor, graph):
    bad = {"format": "axelrod.import/v1", "title": "Broken", "items": [{"id": "X-1"}]}
    res = ingestor.ingest_file(T, json.dumps(bad).encode(), "broken.json", graph)
    assert res.bundle is None and res.document.status == "failed"
    assert res.document.error.startswith("not a valid axelrod.import/v1 bundle") and res.warnings == [res.document.error]


# -- the LLM step --------------------------------------------------------------------------------------------------------
def test_llm_step_reads_only_chunks_with_entities_and_no_rule_signals(lake, inverted, graph):
    p = FakeProvider()
    ing = Ingestor(lake, HashingEmbedder(), provider=p, clock=lambda: NOW, inverted=inverted)
    res = ing.ingest_file(T, NOTE, "note.md", graph, source_type="news")
    # the heading names the central bank (nothing for the rules) and the Acme Re line names a value (nothing either);
    # the rules' paragraph and the line naming nothing are never sent
    assert p.calls == ["# Central bank watch", OVERSEAS]
    items = res.bundle.bundle["items"]
    assert [i["tags"] for i in items] == [["extracted"], ["extracted", "llm"]]
    llm_item = items[1]
    assert llm_item["signals"] == [{"type": "support", "source": "dollar.index",
                                    "target": "acme_re.international_profit", "strength": 0.5, "quote": OVERSEAS,
                                    "note": "llm:fake-1"}]
    assert llm_item["confidence"] == 0.5 and llm_item["category"] == "earnings"
    assert res.llm_signals == 1 and res.signals == 3
    quotes_hold(res.bundle.bundle)
    # a second run replays the cache: no new calls, the same bundle
    again = ing.process(T, res.document.id, graph)
    assert len(p.calls) == 2 and again.bundle.id == res.bundle.id


# -- many files ---------------------------------------------------------------------------------------------------------
def test_ingest_many_returns_event_time_order_then_id(ingestor, graph):
    files = [(b"Crude rose. 2026-10-09", "c.txt"), (b"Crude fell. 2026-10-01", "a.txt"),
             (b"Crude rose 3%.", "b_2026-10-01.txt"), (b"Crude fell 2%.", "d.txt")]
    out = ingestor.ingest_many(T, files, graph, source_type="news")
    keys = [(r.document.event_time, r.document.id) for r in out]
    assert keys == sorted(keys)
    assert [r.document.event_time.date().isoformat() for r in out] == ["2026-10-01", "2026-10-01", "2026-10-09",
                                                                        "2026-10-17"]
    assert all(r.new for r in out)
    assert [r.new for r in ingestor.ingest_many(T, files, graph)] == [False] * 4
