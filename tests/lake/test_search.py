"""Search over the lakehouse and Sally's world model (Oct 17): keyword, prefix (names from the graph and word prefixes),
semantic (cosine over hashing embeddings), graph (named entities and values, their neighbours, and the chunks that
mention them), and hybrid (reciprocal-rank fusion). Every mode is tenant-scoped and returns the same results in the
same order for the same data, including on a second lake built from the same inputs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from axelrod_wm.lake.embed import HashingEmbedder
from axelrod_wm.lake.search import MODES, RRF_K, Searcher
from axelrod_wm.lake.sqlite import SQLiteLake
from axelrod_wm.lake.store import Mention
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.runner import build_runner
from tests.lake.conftest import T0, add_doc

EMB = HashingEmbedder()

DOCS = [
    (b"jpm", "acme", "JPMorgan results", [
        "JPMorgan net interest income rose as rates stayed high",
        "JPMorgan shares rallied after the results",
    ], [(0, "jpmorgan", "jpmorgan.net_interest_income", "JPMorgan net interest income"),
        (0, "jpmorgan", None, "JPMorgan"),
        (1, "jpmorgan", "jpmorgan.share_price", "JPMorgan shares"),
        (1, "jpmorgan", None, "JPMorgan")]),
    (b"boj", "acme", "BoJ watch", [
        "The Bank of Japan raised its policy rate",
        "The yen strengthened and Toyota shares fell",
    ], [(0, "boj", "boj.policy_rate", "Bank of Japan policy rate"),
        (1, "toyota", "toyota.share_price", "Toyota shares"),
        (1, "dollar_yen", None, "yen")]),
    (b"toy", "acme", "Toyota outlook", [
        "Toyota Motor raised its operating profit forecast",
    ], [(0, "toyota", "toyota.operating_profit", "Toyota Motor operating profit")]),
    (b"other", "bravo", "Bravo note", [
        "JPMorgan net interest income in the other tenant",
    ], [(0, "jpmorgan", "jpmorgan.net_interest_income", "JPMorgan net interest income")]),
]


@pytest.fixture(scope="module")
def graph():
    r = build_runner("sally_demo", interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    return r.controller.engine.wm.graph


def populate(lake: SQLiteLake) -> dict[str, str]:
    ids = {}
    for data, tenant, title, texts, mentions in DOCS:
        doc = add_doc(lake, data, texts, tenant=tenant, title=title)
        lake.put_mentions(tenant, doc.id, [Mention(tenant=tenant, doc_id=doc.id, ord=o, entity_id=e, subentity_id=s,
                                                   surface=sf) for o, e, s, sf in mentions])
        lake.put_embeddings(tenant, doc.id, EMB.name, EMB.embed(texts))
        ids[data.decode()] = doc.id
    return ids


@pytest.fixture
def ids(lake):
    return populate(lake)


@pytest.fixture
def s(lake, graph, ids):
    return Searcher(lake, EMB, graph)


def keys(hits):
    return [(h.kind, h.doc_id, h.ord, h.ref) for h in hits]


# -- keyword and prefix ---------------------------------------------------------------------------------------------

def test_keyword_delegates_to_the_store(s, lake, ids):
    hits = s.keyword("acme", "net interest income")
    assert hits == lake.keyword_search("acme", "net interest income")
    assert [(h.doc_id, h.ord) for h in hits] == [(ids["jpm"], 0)]


def test_names_match_entity_and_attribute_name_prefixes(s):
    hits = s.names("Toyo", limit=500)
    assert len(s.names("Toyo")) == 20                                       # the default limit
    assert (hits[0].kind, hits[0].ref, hits[0].score) == ("entity", "toyota", 1.0)
    vals = hits[1:]                     # Toyota's attributes, however many its construction gives it
    assert vals and all(h.kind == "attribute" and h.score == 0.9 and h.ref.startswith("toyota.") for h in vals)
    assert hits[0].entity_id == "toyota" and all(h.entity_id == "toyota" for h in vals)
    assert {"toyota.operating_profit", "toyota.share_price", "toyota.vehicle_sales"} <= {h.ref for h in vals}
    assert hits[0].text == "Toyota Motor" and hits[0].why == ["name prefix"]
    assert [h.ref for h in s.names("jp") if h.kind == "entity"] == ["jpmorgan", "jpy_eur", "jpy_usd"]  # JPM: an alias


def test_names_include_attributes_after_entities(s, graph):
    sid, sub = next((k, v) for k, v in sorted(graph.subentities.items()))
    hits = s.names(sub.name[:6])
    vals = [h for h in hits if h.kind == "attribute"]
    assert sid in [h.ref for h in vals] and all(h.score == 0.9 for h in vals)
    assert [h.kind for h in hits] == sorted((h.kind for h in hits), key=lambda k: k != "entity")


def test_names_respect_limit_and_empty_query(s, lake):
    assert len(s.names("j", limit=2)) == 2
    assert s.names("   ") == [] and s.names("zzzz") == []
    assert Searcher(lake, EMB).names("Toyo") == []


def test_prefix_puts_model_names_before_document_prefixes(s, ids):
    hits = s.prefix("acme", "Toyo", limit=500)
    names = s.names("Toyo", limit=500)
    n = len(names)
    assert keys(hits)[:n] == [(h.kind, None, None, h.ref) for h in names]
    assert {(h.doc_id, h.ord) for h in hits[n:]} == {(ids["toy"], 0), (ids["boj"], 1)}
    assert all(h.why == ["prefix"] for h in hits if h.kind == "chunk")
    assert len(s.prefix("acme", "Toyo", limit=1)) == 1


def test_prefix_without_a_graph_or_query(lake, ids):
    bare = Searcher(lake, EMB)
    assert {h.kind for h in bare.prefix("acme", "Toyo")} == {"chunk"}
    assert bare.prefix("acme", "  ") == []


# -- semantic -------------------------------------------------------------------------------------------------------

def test_semantic_ranks_the_closest_chunk_first(s, ids):
    hits = s.semantic("acme", "JPMorgan net interest income rose")
    assert (hits[0].doc_id, hits[0].ord) == (ids["jpm"], 0)
    assert hits[0].title == "JPMorgan results" and hits[0].event_time == T0 and hits[0].why == ["semantic"]
    assert len(hits) == 5                                              # every acme chunk, none of bravo's
    order = [(-h.score, h.doc_id, h.ord) for h in hits]
    assert order == sorted(order)


def test_semantic_breaks_score_ties_by_document_and_position(s):
    hits = s.semantic("acme", "zzz qqq")                                # orthogonal to everything: ties at 0
    assert [(h.doc_id, h.ord) for h in hits] == sorted((h.doc_id, h.ord) for h in hits)


def test_semantic_empty_query_and_limit(s):
    assert s.semantic("acme", "  ") == []
    assert len(s.semantic("acme", "rates", limit=2)) == 2
    assert s.semantic("nobody", "rates") == []


def test_a_chunk_hit_without_its_document_or_chunk_is_blank(s, lake):
    lake.put_embeddings("acme", "zz-orphan", EMB.name, EMB.embed(["orphan vector"]))
    hit = next(h for h in s.semantic("acme", "orphan vector") if h.doc_id == "zz-orphan")
    assert (hit.text, hit.title, hit.filename, hit.event_time) == ("", "", "", None)
    gone = s._chunk_hit("acme", s.store.list_documents("acme")[0].id, 99, 0.5, ["x"])
    assert gone.text == "" and gone.title != ""


# -- graph ----------------------------------------------------------------------------------------------------------

def test_graph_finds_a_named_attribute_its_neighbours_and_mentioning_chunks(s, ids):
    hits = s.graph_search("acme", "JPMorgan net interest income")
    assert keys(hits) == [
        ("entity", None, None, "jpmorgan"),
        ("attribute", None, None, "jpmorgan.net_interest_income"),
        ("attribute", None, None, "federal_reserve.policy_rate"),          # the policy rate drives NII
        ("attribute", None, None, "jpmorgan.interest_expense"),            # Oct 18 (JPMorgan construction): NII's parts
        ("attribute", None, None, "jpmorgan.interest_income"),
        ("attribute", None, None, "jpmorgan.nii_ex_markets"),              # ... and the identity it is a term of
        ("attribute", None, None, "jpmorgan.share_price"),                 # NII drives the share price
        ("attribute", None, None, "us_treasuries.yield_10y"),              # the long end drives NII
        ("chunk", ids["jpm"], 0, None),                                # the value and the entity, twice
        ("chunk", ids["jpm"], 1, None),                                # only the entity: the share price is excluded
    ]
    assert [h.entity_id for h in hits[:3]] == ["jpmorgan", "jpmorgan", "federal_reserve"] and hits[8].entity_id is None
    assert hits[2].why == ["neighbour", "drives JPMorgan net interest income"]
    assert hits[6].why == ["neighbour", "JPMorgan net interest income drives"] and hits[6].score == 0.5
    assert [h.score for h in hits[8:]] == [1.0, 0.5] and hits[8].why == ["mentions"]


def test_graph_neighbours_include_what_drives_a_named_value(s):
    hits = s.graph_search("acme", "JPMorgan share price")
    near = {h.ref: h.why for h in hits if "neighbour" in h.why}
    assert near["jpmorgan.net_interest_income"] == ["neighbour", "drives JPMorgan share price"]


def test_graph_named_entity_counts_every_mention(s, ids, graph):
    hits = s.graph_search("acme", "Toyota")
    assert keys(hits)[0] == ("entity", None, None, "toyota")
    vals = set(graph.entities["toyota"].subentity_ids)
    assert not any(h.ref in vals for h in hits if "neighbour" in h.why)   # links inside the seeds are not neighbours
    assert [(h.doc_id, h.ord) for h in hits if h.kind == "chunk"] == sorted([(ids["boj"], 1), (ids["toy"], 0)])


def test_graph_falls_back_to_shared_name_words(s, ids):
    hits = s.graph_search("acme", "morgan")                             # no full name: Morgan Stanley shares a word
    assert [h.ref for h in hits if h.kind == "entity"] == ["morgan_stanley"]
    assert all(h.kind != "chunk" for h in hits)                         # nothing mentions Morgan Stanley


def test_graph_without_matches_or_graph_is_empty(s, lake):
    assert s.graph_search("acme", "zebra quantum") == []
    assert s.graph_search("acme", "") == []
    assert Searcher(lake, EMB).graph_search("acme", "Toyota") == []


def test_graph_is_tenant_scoped_and_limited(s, ids):
    assert all(h.doc_id != ids["other"] for h in s.graph_search("acme", "JPMorgan net interest income"))
    bravo = s.graph_search("bravo", "JPMorgan net interest income")
    assert [(h.doc_id, h.ord) for h in bravo if h.kind == "chunk"] == [(ids["other"], 0)]
    assert len(s.graph_search("acme", "JPMorgan net interest income", limit=2)) == 2


# -- hybrid and dispatch --------------------------------------------------------------------------------------------

def test_hybrid_fuses_by_reciprocal_rank(s, ids):
    q = "JPMorgan net interest income"
    hits = s.hybrid("acme", q)
    assert all(h.kind == "chunk" for h in hits)
    top = hits[0]
    assert (top.doc_id, top.ord) == (ids["jpm"], 0)
    assert top.why == ["keyword", "semantic", "mentions"]               # merged, each once
    lists = [s.keyword("acme", q, 50), s.semantic("acme", q, 50),
             [h for h in s.graph_search("acme", q, 50) if h.kind == "chunk"]]
    expected = {}
    for hl in lists:
        for rank, h in enumerate(hl):
            expected[(h.doc_id, h.ord)] = expected.get((h.doc_id, h.ord), 0.0) + 1.0 / (RRF_K + rank + 1)
    assert {(h.doc_id, h.ord): h.score for h in hits} == {k: round(v, 6) for k, v in expected.items()}
    order = [(-h.score, h.doc_id, h.ord) for h in hits]
    assert order == sorted(order)


def test_hybrid_keeps_the_first_text_and_respects_limit(s, ids):
    hits = s.hybrid("acme", "Toyota", limit=2)
    assert len(hits) == 2 and all(h.text for h in hits)


def test_hybrid_ties_resolve_by_document_and_position(s):
    hits = s.hybrid("acme", "zzz qqq")                                  # semantic only, all at rank-derived scores
    assert [(-h.score, h.doc_id, h.ord) for h in hits] == sorted((-h.score, h.doc_id, h.ord) for h in hits)


class StubHit(SimpleNamespace):
    def model_copy(self, update):
        return StubHit(**{**vars(self), **update})


def test_hybrid_merges_why_without_duplicates():
    def hit(d, o, why):
        return StubHit(doc_id=d, ord=o, why=why, kind="chunk")

    class Stub(Searcher):
        def keyword(self, tenant, q, limit=20):
            return [hit("a", 0, ["keyword"]), hit("b", 0, ["keyword", "any word"])]

        def semantic(self, tenant, q, limit=20):
            return [hit("b", 0, ["semantic"]), hit("a", 0, ["semantic"])]

        def graph_search(self, tenant, q, limit=20):
            return [hit("b", 0, ["keyword"]), StubHit(kind="entity")]

    out = Stub(None, EMB).hybrid("t", "q")
    assert [(h.doc_id, h.why) for h in out] == [("b", ["keyword", "any word", "semantic"]),
                                                 ("a", ["keyword", "semantic"])]
    assert out[0].score == round(1 / 62 + 1 / 61 + 1 / 61, 6)


@pytest.mark.parametrize("mode", MODES)
def test_search_dispatches_each_mode(s, mode):
    expected = {"keyword": s.keyword, "prefix": s.prefix, "semantic": s.semantic, "graph": s.graph_search,
                "hybrid": s.hybrid}[mode]("acme", "Toyota", 3)
    assert s.search("acme", "Toyota", mode=mode, limit=3) == expected


def test_search_defaults_to_hybrid_and_rejects_unknown_modes(s):
    assert s.search("acme", "Toyota") == s.hybrid("acme", "Toyota")
    with pytest.raises(ValueError, match="mode must be one of"):
        s.search("acme", "Toyota", mode="fuzzy")


# -- the gazetteer cache and determinism ----------------------------------------------------------------------------

def test_gazetteer_is_cached_and_rebuilt_when_the_graph_changes(s, graph):
    gz = s.gazetteer()
    assert gz is s.gazetteer()
    other = SimpleNamespace(entities={}, subentities={})
    s.graph = other
    assert s.gazetteer() is not gz and s.gazetteer() is s.gazetteer()
    s.graph = graph
    assert s.gazetteer() is not gz and s.gazetteer().digest == gz.digest


@pytest.mark.parametrize("q", ["JPMorgan net interest income", "Toyota", "yen", "morgan", "rates rose", "Toyo"])
@pytest.mark.parametrize("mode", MODES)
def test_the_same_query_returns_the_same_results(s, lake, graph, tmp_path, mode, q):
    first = s.search("acme", q, mode=mode)
    assert s.search("acme", q, mode=mode) == first
    twin = SQLiteLake(tmp_path / "twin")
    try:
        populate(twin)
        assert Searcher(twin, HashingEmbedder(), graph).search("acme", q, mode=mode) == first
    finally:
        twin.close()
