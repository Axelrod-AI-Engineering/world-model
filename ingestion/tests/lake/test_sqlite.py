"""The SQLite lakehouse (Oct 17): documents stored once per content hash, partitioned by tenant; text, chunks, the
keyword index, mentions, and embeddings round-trip and are replaced or deleted together; keyword search quotes every
word (no operator in a query is interpreted) and falls back from every word to any word; bundles, imports, and the
LLM cache; and every read comes back in a deterministic order."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest

from axelrod_ingest.lake.sqlite import SQLiteLake, fts_query
from axelrod_ingest.lake.store import BundleRecord, ImportRecord, Mention
from tests.lake.conftest import T0, add_doc, make_chunks, make_doc

DAY = timedelta(days=1)


def mention(doc_id, ord_, entity_id, subentity_id=None, surface="x", tenant="acme"):
    return Mention(tenant=tenant, doc_id=doc_id, ord=ord_, entity_id=entity_id, subentity_id=subentity_id,
                   surface=surface)


def bundle(id_, doc_ids, created_at=T0, tenant="acme"):
    return BundleRecord(tenant=tenant, id=id_, doc_ids=doc_ids, created_at=created_at, extractor_version="v1",
                        items=1, signals=2, bundle={"z": 1, "a": [1, 2]})


# -- documents ------------------------------------------------------------------------------------------------------

def test_put_document_stores_once_per_content(lake):
    data = b"Acme Bank net interest income rose."
    doc = make_doc(data, title="first")
    stored, new = lake.put_document(doc, data)
    assert new and stored == doc
    again, new2 = lake.put_document(make_doc(data, title="second"), b"other bytes")
    assert not new2 and again.title == "first"
    assert lake.raw_bytes("acme", doc.id) == data                    # the raw file was written once
    assert lake.get_document("acme", doc.id) == doc
    assert lake.stats("acme")["documents"] == 1


def test_documents_round_trip_every_field(lake):
    data = b"payload"
    doc = make_doc(data, source="broker", source_type="broker_research", title="T", published_at=T0 - DAY,
                   uploaded_by="eve", meta={"b": 1, "a": [1]}, status="parsed", error="")
    lake.put_document(doc, data)
    assert lake.get_document("acme", doc.id) == doc


def test_missing_document_reads_as_none(lake):
    assert lake.get_document("acme", "nope") is None
    assert lake.raw_bytes("acme", "nope") is None


def test_raw_bytes_is_none_when_the_raw_file_is_gone(lake):
    data = b"bytes"
    doc, _ = lake.put_document(make_doc(data), data)
    lake._raw_path("acme", doc).unlink()
    assert lake.raw_bytes("acme", doc.id) is None


def test_the_same_bytes_in_two_tenants_are_separate(lake):
    data = b"shared"
    a, new_a = lake.put_document(make_doc(data, tenant="acme", title="A"), data)
    b, new_b = lake.put_document(make_doc(data, tenant="bravo", title="B"), data)
    assert new_a and new_b and a.id == b.id
    assert lake.get_document("acme", a.id).title == "A" and lake.get_document("bravo", b.id).title == "B"
    assert lake.delete_document("acme", a.id)
    assert lake.get_document("acme", a.id) is None
    assert lake.raw_bytes("bravo", b.id) == data


def test_tenants_whose_names_sanitize_alike_keep_separate_raw_files(lake):
    data = b"same bytes"
    lake.put_document(make_doc(data, tenant="Acme"), data)
    lake.put_document(make_doc(data, tenant="acme"), data)
    lake.delete_document("Acme", make_doc(data).id)
    assert lake.raw_bytes("acme", make_doc(data).id) == data


def test_raw_path_sanitizes_tenant_and_extension(lake):
    doc = make_doc(b"x", filename="../../Report.Final.P-D-F!!LONGEXTENSION")
    p = lake._raw_path("../Evil Tenant/", doc)
    assert p.parent.parent.parent == lake.root
    assert p.parent.name == "raw" and p.parent.parent.name.startswith("evil_tenant-")
    assert p.name == f"{doc.id}.pdflonge"                              # letters and digits only, eight at most
    assert lake._raw_path("acme", make_doc(b"x", filename="README")).name == doc.id
    assert lake._raw_path("acme", doc).parent.parent.name == "acme"
    assert lake._raw_path("!!!", doc).parent.parent.name.startswith("default-")
    assert lake._raw_path("!!!", doc) != lake._raw_path("default", doc)


def test_list_documents_orders_and_filters(lake):
    # event times run opposite to ingestion times
    docs = [lake.put_document(make_doc(d, event_time=T0 + k * DAY, ingested_at=T0 + (5 - k) * DAY), d)[0]
            for k, d in enumerate([b"d0", b"d1", b"d2", b"d3"])]
    ids = [d.id for d in docs]
    assert [d.id for d in lake.list_documents("acme")] == ids
    assert [d.id for d in lake.list_documents("acme", order="ingested_at")] == ids[::-1]
    assert [d.id for d in lake.list_documents("acme", since=T0 + DAY)] == ids[1:]
    assert [d.id for d in lake.list_documents("acme", until=T0 + 2 * DAY)] == ids[:2]
    assert [d.id for d in lake.list_documents("acme", since=T0 + DAY, until=T0 + 3 * DAY)] == ids[1:3]
    assert [d.id for d in lake.list_documents("acme", order="ingested_at", since=T0 + 4 * DAY)] == ids[:2][::-1]
    assert [d.id for d in lake.list_documents("acme", limit=2, offset=1)] == ids[1:3]
    assert lake.list_documents("bravo") == []


def test_list_documents_breaks_ties_by_id(lake):
    ids = [lake.put_document(make_doc(d), d)[0].id for d in (b"a", b"b", b"c")]
    assert [d.id for d in lake.list_documents("acme")] == sorted(ids)


def test_list_documents_rejects_an_unknown_order(lake):
    with pytest.raises(ValueError, match="order must be"):
        lake.list_documents("acme", order="title")


def test_update_document_changes_the_stored_fields(lake):
    data = b"u"
    doc, _ = lake.put_document(make_doc(data), data)
    new = lake.update_document("acme", doc.id, status="parsed", title="Q3", meta={"pages": 2},
                               published_at=T0 - DAY, event_time=T0 - DAY)
    assert new.status == "parsed" and new.ingested_at == doc.ingested_at
    assert lake.get_document("acme", doc.id) == new
    with pytest.raises(KeyError):
        lake.update_document("acme", "missing", status="failed")
    with pytest.raises(KeyError):
        lake.update_document("bravo", doc.id, status="failed")


def test_delete_document_removes_everything_it_owns(lake):
    doc = add_doc(lake, b"del", ["oil prices rose", "dollar weakened"])
    keep = add_doc(lake, b"keep", ["oil prices fell"])
    lake.put_mentions("acme", doc.id, [mention(doc.id, 0, "oil")])
    lake.put_embeddings("acme", doc.id, "m", [[1.0], [0.5]])
    path = lake._raw_path("acme", doc)
    assert path.exists()
    assert lake.delete_document("acme", doc.id) is True
    assert not path.exists()
    assert lake.get_text("acme", doc.id) is None and lake.get_chunks("acme", doc.id) == []
    assert lake.mentions_of("acme", doc_id=doc.id) == [] and lake.embeddings("acme", "m") == []
    assert [h.doc_id for h in lake.keyword_search("acme", "oil")] == [keep.id]
    assert [h.doc_id for h in lake.keyword_search("acme", "oil", prefix=True)] == [keep.id]
    assert lake.stats("acme") == {"documents": 1, "chunks": 1, "mentions": 0, "embeddings": 0, "bundles": 0,
                                  "imports": 0}
    assert lake.delete_document("acme", doc.id) is False


def test_delete_document_tolerates_a_missing_raw_file(lake):
    data = b"gone"
    doc, _ = lake.put_document(make_doc(data), data)
    lake._raw_path("acme", doc).unlink()
    assert lake.delete_document("acme", doc.id) is True


# -- text, chunks, mentions, embeddings -----------------------------------------------------------------------------

def test_text_round_trips_and_is_replaced(lake):
    assert lake.get_text("acme", "d") is None
    lake.put_text("acme", "d", "first", "plain")
    lake.put_text("acme", "d", "second", "pdf")
    assert lake.get_text("acme", "d") == ("second", "pdf")
    assert lake.get_text("bravo", "d") is None


def test_chunks_come_back_in_order_and_are_replaced_with_their_index(lake):
    doc = add_doc(lake, b"c", ["alpha dollar", "beta oil", "gamma rates"])
    shuffled = make_chunks("acme", doc.id, ["alpha dollar", "beta oil", "gamma rates"])[::-1]
    lake.put_chunks("acme", doc.id, shuffled)
    assert [c.ord for c in lake.get_chunks("acme", doc.id)] == [0, 1, 2]
    lake.put_chunks("acme", doc.id, make_chunks("acme", doc.id, ["delta copper"]))
    chunks = lake.get_chunks("acme", doc.id)
    assert [c.text for c in chunks] == ["delta copper"] and chunks[0].page is None and chunks[0].section == ""
    assert lake.keyword_search("acme", "alpha") == [] == lake.keyword_search("acme", "alph", prefix=True)
    assert [h.text for h in lake.keyword_search("acme", "copper")] == ["delta copper"]
    assert lake.get_chunks("bravo", doc.id) == []


def test_mentions_filter_by_any_combination(lake):
    lake.put_mentions("acme", "d1", [mention("d1", 1, "zenith_motors", "zenith_motors.share_price", "Zenith Motors shares"),
                                     mention("d1", 0, "zenith_motors", None, "Zenith Motors"),
                                     mention("d1", 0, "central_bank", "central_bank.policy_rate", "policy rate")])
    lake.put_mentions("acme", "d2", [mention("d2", 0, "zenith_motors", None, "Zenith Motors")])
    lake.put_mentions("bravo", "d1", [mention("d1", 0, "zenith_motors", tenant="bravo")])
    every = lake.mentions_of("acme")
    assert [(m.doc_id, m.ord, m.entity_id) for m in every] == [("d1", 0, "central_bank"), ("d1", 0, "zenith_motors"),
                                                                ("d1", 1, "zenith_motors"), ("d2", 0, "zenith_motors")]
    assert len(lake.mentions_of("acme", entity_id="zenith_motors")) == 3
    assert [m.surface for m in lake.mentions_of("acme", subentity_id="zenith_motors.share_price")] == ["Zenith Motors shares"]
    assert [m.entity_id for m in lake.mentions_of("acme", doc_id="d1")] == ["central_bank", "zenith_motors", "zenith_motors"]
    assert [m.ord for m in lake.mentions_of("acme", entity_id="zenith_motors", doc_id="d1")] == [0, 1]
    assert lake.mentions_of("acme", entity_id="zenith_motors", subentity_id="central_bank.policy_rate") == []
    assert len(lake.mentions_of("acme", entity_id="zenith_motors", subentity_id="zenith_motors.share_price", doc_id="d1")) == 1
    lake.put_mentions("acme", "d1", [])                                # replaced, not appended
    assert [m.doc_id for m in lake.mentions_of("acme")] == ["d2"]
    assert len(lake.mentions_of("bravo")) == 1


def test_embeddings_round_trip_as_float32_and_are_replaced(lake):
    lake.put_embeddings("acme", "d2", "m", [[0.1, -0.2]])
    lake.put_embeddings("acme", "d1", "m", [[1.0, 0.0], [0.333333, 0.5]])
    lake.put_embeddings("acme", "d1", "other", [[9.0]])
    got = lake.embeddings("acme", "m")
    assert [(d, o) for d, o, _v in got] == [("d1", 0), ("d1", 1), ("d2", 0)]
    assert got[1][2] == pytest.approx([0.333333, 0.5], abs=1e-7)
    assert got[2][2] == pytest.approx([0.1, -0.2], abs=1e-7)
    lake.put_embeddings("acme", "d1", "m", [[0.0, 1.0]])
    assert [(d, o, v) for d, o, v in lake.embeddings("acme", "m")][:1] == [("d1", 0, [0.0, 1.0])]
    assert len(lake.embeddings("acme", "m")) == 2
    assert lake.embeddings("bravo", "m") == []



def python_ranking(lake, tenant, model, q, limit):
    """The ranking the matrix search replaced: cosine in Python over every vector, rounded, ties by doc and position."""
    from axelrod_ingest.lake.embed import cosine
    return sorted(((round(cosine(q, v), 6), d, o) for d, o, v in lake.embeddings(tenant, model)),
                  key=lambda x: (-x[0], x[1], x[2]))[:limit]


def test_nearest_matches_the_python_ranking_exactly(lake):
    import random
    rng = random.Random(7)
    for d in ("d3", "d1", "d2"):
        lake.put_embeddings("acme", d, "m", [[round(rng.uniform(-1, 1), 4) for _ in range(16)] for _ in range(40)])
    lake.put_embeddings("acme", "d4", "m", [[0.0] * 16, [1.0] + [0.0] * 15, [1.0] + [0.0] * 15])  # a zero row and a tie
    for q in ([rng.uniform(-1, 1) for _ in range(16)], [1.0] + [0.0] * 15, [0.0] * 16):
        assert lake.nearest("acme", "m", q, 25) == python_ranking(lake, "acme", "m", q, 25)
    assert lake.nearest("acme", "m", [1.0] + [0.0] * 15, 2)[0][1:] == ("d4", 1)      # equal scores: by doc, then position
    assert lake.nearest("bravo", "m", [1.0], 5) == [] and lake.nearest("acme", "none", [1.0], 5) == []


def test_nearest_sees_its_own_writes_and_deletes(lake):
    doc = add_doc(lake, b"one", ["Acme"])
    lake.put_embeddings("acme", doc.id, "m", [[1.0, 0.0]])
    assert [d for _s, d, _o in lake.nearest("acme", "m", [1.0, 0.0])] == [doc.id]
    lake.put_embeddings("acme", "zz", "m", [[1.0, 0.0]])                 # held vectors are dropped on a write
    assert [d for _s, d, _o in lake.nearest("acme", "m", [1.0, 0.0])] == [doc.id, "zz"]
    lake.put_embeddings("bravo", "d9", "m", [[1.0, 0.0]])                # another tenant's write leaves acme's alone
    assert [d for _s, d, _o in lake.nearest("acme", "m", [1.0, 0.0])] == [doc.id, "zz"]
    assert lake.delete_document("acme", "missing") is False
    assert lake.delete_document("acme", doc.id) is True                  # and on a delete
    assert [d for _s, d, _o in lake.nearest("acme", "m", [1.0, 0.0])] == ["zz"]


def test_nearest_sees_another_connections_commit(tmp_path):
    a, b = SQLiteLake(tmp_path), SQLiteLake(tmp_path)                 # two processes sharing one lake file
    a.put_embeddings("acme", "d1", "m", [[1.0, 0.0]])
    assert len(b.nearest("acme", "m", [1.0, 0.0])) == 1                 # b builds its matrix
    a.put_embeddings("acme", "d2", "m", [[0.0, 1.0]])                   # a commits; b's data_version moves
    assert [d for _s, d, _o in b.nearest("acme", "m", [0.0, 1.0])] == ["d2", "d1"]


# -- keyword search -------------------------------------------------------------------------------------------------

def test_fts_query_quotes_every_word():
    assert fts_query("Bank hikes rates") == '"Bank" "hikes" "rates"'
    assert fts_query("Bank hikes", any_term=True) == '"Bank" OR "hikes"'
    assert fts_query("Toyo", prefix=True) == '"Toyo"*'
    assert fts_query("net inter", prefix=True, any_term=True) == '"net" OR "inter"*'
    assert fts_query("O'Neil's ...U.S. -AT&T- yields.") == '"O\'Neil\'s" "U.S" "AT&T" "yields"'
    assert fts_query('NEAR(oil "dollar") AND -x*') == '"NEAR" "oil" "dollar" "AND" "x"'


@pytest.mark.parametrize("q", ["", "   ", "***", '"', "- . & '", "()"])
def test_fts_query_without_words_is_none(q):
    assert fts_query(q) is None


@pytest.fixture
def corpus(lake):
    a = add_doc(lake, b"a", ["Acme Motors raised its operating profit forecast", "The dollar strengthened against the euro"],
                title="Acme Motors Q3", filename="acme_motors.pdf", event_time=T0 + DAY)
    b = add_doc(lake, b"b", ["Oil prices rose as crude rallied", "Acme Motors shares rose"], title="Oil note")
    add_doc(lake, b"other tenant", ["Acme Motors operating profit"], tenant="bravo")
    return a, b


def test_keyword_search_requires_every_word_first(lake, corpus):
    a, _b = corpus
    hits = lake.keyword_search("acme", "acme_motors profit")
    assert [(h.doc_id, h.ord) for h in hits] == [(a.id, 0)]
    h = hits[0]
    assert (h.kind, h.title, h.filename, h.event_time, h.why) == ("chunk", "Acme Motors Q3", "acme_motors.pdf", T0 + DAY,
                                                                  ["keyword"])
    assert h.score > 0 and h.text == "Acme Motors raised its operating profit forecast"


def test_keyword_search_stems_words(lake, corpus):
    _a, b = corpus
    assert [(h.doc_id, h.ord) for h in lake.keyword_search("acme", "rallies")] == [(b.id, 0)]
    assert lake.keyword_search("acme", "rallies", prefix=True) == []


def test_keyword_search_falls_back_to_any_word(lake, corpus):
    hits = lake.keyword_search("acme", "euro copper")
    assert [h.text for h in hits] == ["The dollar strengthened against the euro"]
    assert hits[0].why == ["keyword", "any word"]


def test_keyword_search_finds_nothing_for_unknown_words(lake, corpus):
    assert lake.keyword_search("acme", "copper zinc") == []


def test_keyword_search_prefix_matches_the_last_word(lake, corpus):
    assert lake.keyword_search("acme", "mot") == []
    hits = lake.keyword_search("acme", "mot", prefix=True)
    assert len(hits) == 2 and all(h.why == ["prefix"] for h in hits)
    assert [h.text for h in lake.keyword_search("acme", "oil pri", prefix=True)] == [
        "Oil prices rose as crude rallied"]


def test_prefix_search_matches_words_not_their_stems(lake, corpus):
    # a stemmed index holds "oper" for "operating" and stems the prefix "mot" to "toi"; the prefix index does neither
    assert [h.text for h in lake.keyword_search("acme", "opera", prefix=True)] == [
        "Acme Motors raised its operating profit forecast"]
    assert [h.text for h in lake.keyword_search("acme", "rall", prefix=True)] == [
        "Oil prices rose as crude rallied"]


def test_keyword_search_ranks_deterministically_and_respects_limit(lake, corpus):
    hits = lake.keyword_search("acme", "rose")
    assert hits == lake.keyword_search("acme", "rose")
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    assert len(lake.keyword_search("acme", "rose", limit=1)) == 1


def test_keyword_search_is_tenant_scoped(lake, corpus):
    assert {h.text for h in lake.keyword_search("bravo", "acme_motors")} == {"Acme Motors operating profit"}
    assert lake.keyword_search("nobody", "acme_motors") == []


@pytest.mark.parametrize("q", ['acme_motors AND', '"acme_motors', 'toy*', 'NEAR(acme_motors profit)', '-acme_motors', 'acme_motors OR NOT',
                               'col:acme_motors', '^acme_motors', '"', '*', '(', ')', 'AND', '{acme_motors}', "acme_motors's"])
@pytest.mark.parametrize("prefix", [False, True])
def test_keyword_search_never_raises_on_operators(lake, corpus, q, prefix):
    hits = lake.keyword_search("acme", q, prefix=prefix)
    assert isinstance(hits, list)


def test_operator_words_are_searched_as_words(lake, corpus):
    assert len(lake.keyword_search("acme", '"acme_motors')) == 2
    assert len(lake.keyword_search("acme", "acme_motors AND profit")) == 2         # AND is a word, not an operator
    assert len(lake.keyword_search("acme", "NEAR(acme_motors profit)")) == 2       # any word: acme_motors or profit


def test_garbage_query_returns_nothing(lake, corpus):
    assert lake.keyword_search("acme", "  ** \" ( ") == []
    assert lake.keyword_search("acme", "") == []


# -- bundles, imports, cache, housekeeping --------------------------------------------------------------------------

def test_bundles_dedupe_by_id_and_round_trip(lake):
    first = bundle("b1", ["d1"])
    assert lake.put_bundle(first) == first
    assert lake.put_bundle(bundle("b1", ["d9"], created_at=T0 + DAY)) == first
    assert lake.get_bundle("acme", "b1") == first
    assert lake.get_bundle("acme", "nope") is None
    assert lake.get_bundle("bravo", "b1") is None


def test_list_bundles_orders_filters_and_limits(lake):
    lake.put_bundle(bundle("b2", ["d1", "d2"], created_at=T0 + DAY))
    lake.put_bundle(bundle("b1", ["d2"], created_at=T0 + DAY))
    lake.put_bundle(bundle("b0", ["d3"], created_at=T0 + 2 * DAY))
    lake.put_bundle(bundle("b3", ["d1"], created_at=T0))
    lake.put_bundle(bundle("bx", ["d1"], tenant="bravo"))
    assert [b.id for b in lake.list_bundles("acme")] == ["b3", "b1", "b2", "b0"]
    assert [b.id for b in lake.list_bundles("acme", doc_id="d1")] == ["b3", "b2"]
    assert [b.id for b in lake.list_bundles("acme", limit=2)] == ["b3", "b1"]
    assert [b.id for b in lake.list_bundles("acme", doc_id="d2", limit=1)] == ["b1"]
    assert lake.list_bundles("acme", doc_id="none") == []


def test_imports_round_trip_in_order_and_filter_by_bundle(lake):
    r2 = ImportRecord(tenant="acme", bundle_id="b2", imported_at=T0 + DAY, update_id=None, item_ids=["i3"])
    r1 = ImportRecord(tenant="acme", bundle_id="b1", imported_at=T0, update_id="U1", item_ids=["i1", "i2"], by="em")
    r3 = ImportRecord(tenant="acme", bundle_id="b1", imported_at=T0 + DAY, update_id="U2", item_ids=[])
    for r in (r2, r1, r3):
        lake.put_import(r)
    lake.put_import(ImportRecord(tenant="bravo", bundle_id="b1", imported_at=T0, update_id=None, item_ids=[]))
    assert lake.list_imports("acme") == [r1, r3, r2]
    assert lake.list_imports("acme", bundle_id="b1") == [r1, r3]
    assert lake.list_imports("acme", bundle_id="zz") == []
    assert len(lake.list_imports("bravo")) == 1


def test_llm_cache_gets_and_replaces(lake):
    assert lake.cache_get("k") is None
    lake.cache_put("k", "anthropic", "m1", {"b": 1, "a": [1]})
    assert lake.cache_get("k") == {"a": [1], "b": 1}
    lake.cache_put("k", "anthropic", "m2", {"v": 2})
    assert lake.cache_get("k") == {"v": 2}


def test_stats_count_each_table_for_the_tenant(lake):
    doc = add_doc(lake, b"s", ["one", "two"])
    lake.put_mentions("acme", doc.id, [mention(doc.id, 0, "oil"), mention(doc.id, 1, "oil")])
    lake.put_embeddings("acme", doc.id, "m", [[1.0], [0.0]])
    lake.put_bundle(bundle("b", [doc.id]))
    lake.put_import(ImportRecord(tenant="acme", bundle_id="b", imported_at=T0, update_id=None, item_ids=[]))
    assert lake.stats("acme") == {"documents": 1, "chunks": 2, "mentions": 2, "embeddings": 2, "bundles": 1,
                                  "imports": 1}
    assert set(lake.stats("bravo").values()) == {0}


def test_a_reopened_lake_reads_what_was_written_and_close_releases_it(tmp_path):
    lake = SQLiteLake(tmp_path / "x")
    doc = add_doc(lake, b"persist", ["Crude oil rallied"])
    lake.close()
    reopened = SQLiteLake(tmp_path / "x")
    try:
        assert reopened.get_document("acme", doc.id) == doc
        assert reopened.raw_bytes("acme", doc.id) == b"persist"
        assert len(reopened.keyword_search("acme", "crude")) == 1
    finally:
        reopened.close()
    with pytest.raises(sqlite3.ProgrammingError):
        reopened.get_document("acme", doc.id)
