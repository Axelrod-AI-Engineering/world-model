"""Retrieval (Oct 26, the public `GET /v1/world-models/{id}/chunks`): the channels fused in the store in one call, the
document filter, the per-document cap, paging, neighbours, and the same page for the same spec, on the local lake and
behind the data service alike."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from axelrod_ingest.lake.search import Searcher
from axelrod_ingest.lake.store import MAX_DEPTH, RRF_K, RetrievalFilter, RetrievalSpec
from tests.conftest import acme_graph
from tests.lake.conftest import T0, add_doc
from tests.lake.test_search import EMB, populate


@pytest.fixture(scope="module")
def graph():
    return acme_graph()


@pytest.fixture
def ids(lake):
    return populate(lake)


@pytest.fixture
def s(lake, graph, ids):
    return Searcher(lake, EMB, graph)


def keys(r):
    return [(p.chunk.doc_id, p.chunk.ord) for p in r.passages]


def test_the_channels_are_fused_by_reciprocal_rank(s, ids):
    r = s.retrieve("acme", "Acme Bank net interest income")
    top = r.passages[0]
    assert (top.chunk.doc_id, top.chunk.ord) == (ids["jpm"], 0)
    assert top.why == ["keyword", "semantic", "graph"] and set(top.scores) == {"keyword", "semantic", "graph"}
    assert top.score == round(3 / (RRF_K + 1), 6) and top.scores["graph"] == 1.0
    assert top.document.title == "Acme Bank results" and top.chunk.text.startswith("Acme Bank net interest income")
    assert {m.entity_id for m in top.mentions} == {"acme_bank"}
    assert len(r.passages) == 5 and not r.more                       # every acme chunk the embedding reaches; no bravo
    order = [(-p.score, p.chunk.doc_id, p.chunk.ord) for p in r.passages]
    assert order == sorted(order)


def test_the_same_spec_returns_the_same_page(s):
    a = s.retrieve("acme", "shares rallied", context=1)
    assert a == s.retrieve("acme", "shares rallied", context=1)


def test_one_channel_alone(s, ids):
    kw = s.retrieve("acme", "rallied", channels=["keyword"])
    assert keys(kw) == [(ids["jpm"], 1)] and kw.passages[0].why == ["keyword"]
    anyword = s.retrieve("acme", "rallied zebra", channels=["keyword"])
    assert keys(anyword) == [(ids["jpm"], 1)] and anyword.passages[0].why == ["keyword", "any word"]
    assert s.retrieve("acme", "zebra", channels=["keyword"]).passages == []
    assert s.retrieve("acme", "!!!", channels=["keyword"]).passages == []
    graph = s.retrieve("acme", "Acme Motors", channels=["graph"])
    assert sorted(keys(graph)) == sorted([(ids["rates"], 1), (ids["toy"], 0)])
    assert all(p.why == ["graph"] for p in graph.passages)


def test_a_named_attribute_counts_its_own_mentions_and_its_entitys(s, ids):
    r = s.retrieve("acme", "Acme Bank net interest income", channels=["graph"])
    assert keys(r) == [(ids["jpm"], 0), (ids["jpm"], 1)]             # the share price mention is not counted
    assert [p.scores["graph"] for p in r.passages] == [1.0, 0.5]


def test_channels_with_nothing_to_go_on_add_nothing(s, lake):
    assert s.retrieve("acme", "  ", channels=["semantic"]).passages == []          # no text: no embedding
    assert s.retrieve("acme", "zebra quantum", channels=["graph"]).passages == []  # no names
    assert Searcher(lake, EMB).retrieve("acme", "Acme Motors", channels=["graph"]).passages == []  # no model
    assert s.retrieve("nobody", "Acme Motors").passages == []
    spec = RetrievalSpec(query="rates", channels=["semantic"], vector=[1.0, 0.0], model="another-embedder")
    assert lake.retrieve("acme", spec).passages == []


def test_bad_specs_are_value_errors(lake):
    with pytest.raises(ValueError, match="channels"):
        lake.retrieve("acme", RetrievalSpec(query="x", channels=["telepathy"]))
    with pytest.raises(ValueError, match="channels"):
        lake.retrieve("acme", RetrievalSpec(query="x", channels=[]))
    with pytest.raises(ValueError, match=str(MAX_DEPTH)):
        lake.retrieve("acme", RetrievalSpec(query="x", offset=MAX_DEPTH, limit=1))


# -- the filter -----------------------------------------------------------------------------------------------------------

def test_filter_by_document(s, ids):
    r = s.retrieve("acme", "Acme", filter=RetrievalFilter(document_ids=[ids["toy"]]))
    assert keys(r) == [(ids["toy"], 0)]


def test_filter_by_entity_keeps_documents_that_name_it(s, ids):
    r = s.retrieve("acme", "Acme Bank", filter=RetrievalFilter(entity_ids=["acme_motors"]))
    assert {d for d, _o in keys(r)} == {ids["rates"], ids["toy"]}


def test_filter_by_source_and_type(s, lake):
    add_doc(lake, b"brk", ["Acme Bank margins widened"], tenant="acme", source="Big Broker",
            source_type="broker_research")
    f = RetrievalFilter(sources=["big broker"], source_types=["broker_research"])
    r = s.retrieve("acme", "Acme Bank", filter=f)
    assert [p.document.source for p in r.passages] == ["Big Broker"]
    assert s.retrieve("acme", "Acme Bank", filter=RetrievalFilter(source_types=["news"])).passages == []


def test_filter_by_date_in_any_zone(s, lake):
    late = add_doc(lake, b"late", ["Acme Bank later note"], tenant="acme", event_time=T0 + timedelta(days=30))
    tokyo = timezone(timedelta(hours=9))
    after = RetrievalFilter(published_from=(T0 + timedelta(days=1)).astimezone(tokyo))
    assert {p.chunk.doc_id for p in s.retrieve("acme", "Acme Bank", filter=after).passages} == {late.id}
    before = RetrievalFilter(published_to=(T0 + timedelta(days=1)).replace(tzinfo=None))     # naive: UTC
    assert late.id not in {p.chunk.doc_id for p in s.retrieve("acme", "Acme Bank", filter=before).passages}
    assert s.retrieve("acme", "Acme Bank", filter=RetrievalFilter(published_to=datetime(2020, 1, 1, tzinfo=UTC))).passages == []


# -- the page ---------------------------------------------------------------------------------------------------------------

def test_pages_follow_one_another(s):
    whole = keys(s.retrieve("acme", "Acme", limit=5))
    first, second = s.retrieve("acme", "Acme", limit=2), s.retrieve("acme", "Acme", offset=2, limit=2)
    assert first.more and second.more and keys(first) + keys(second) == whole[:4]
    last = s.retrieve("acme", "Acme", offset=4, limit=2)
    assert keys(last) == whole[4:] and not last.more
    assert s.retrieve("acme", "Acme", offset=10, limit=2).passages == []


def test_per_document_caps_each_document(s):
    r = s.retrieve("acme", "Acme shares", per_document=1)
    docs = [d for d, _o in keys(r)]
    assert len(docs) == len(set(docs)) == 3


def test_context_brings_the_neighbours(s, ids):
    r = s.retrieve("acme", "rallied", channels=["keyword"], context=2)
    p = r.passages[0]
    assert [c.ord for c in p.before] == [0] and p.after == []
    r = s.retrieve("acme", "net interest income rose", channels=["keyword"], context=1)
    assert r.passages[0].before == [] and [c.ord for c in r.passages[0].after] == [1]


def test_a_chunk_that_is_gone_is_left_out(s, lake):
    lake.put_embeddings("acme", "zz-orphan", EMB.name, EMB.embed(["orphan vector"]))    # no document: never admitted
    doc = lake.list_documents("acme")[0]
    lake.put_embeddings("acme", doc.id, EMB.name, EMB.embed(["one", "two", "three", "four", "a chunk not stored"]))
    r = s.retrieve("acme", "a chunk not stored", channels=["semantic"], limit=10)
    assert "zz-orphan" not in {p.chunk.doc_id for p in r.passages}
    assert all(p.chunk.ord < 2 for p in r.passages if p.chunk.doc_id == doc.id)
