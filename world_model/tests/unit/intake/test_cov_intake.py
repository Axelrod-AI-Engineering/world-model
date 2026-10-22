"""Intake around the refiner: sources, scrapers, the resolver, translators, bundles, and the pipeline's op summaries."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from axelrod_ingest.contract.bundle import ImportItem, Link, Move, Observe, Support
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.market import MarketEvent
from axelrod_wm.intake import scrapers
from axelrod_wm.intake.pipeline import op_summary
from axelrod_wm.intake.resolver import (
    AliasFuzzyResolver,
    EntityResolver,
    constraint_fraction,
    entity_strings,
    text_similarity,
)
from axelrod_wm.intake.scrapers import MockWebScraper
from axelrod_wm.intake.sources import HistoryReplaySource, JsonlReplaySource, load_market_events
from axelrod_wm.intake.structured import StructuredTranslator, market_event_of, signal_ops, translate_item
from axelrod_wm.intake.translators import (
    DataFeedTranslator,
    LLMNotConfigured,
    LLMTranslator,
    TemplateTranslator,
    TranslationContext,
    fill_event,
)
from axelrod_wm.model.taxonomy import TaxonomyKind
from tests.conftest import constructed_engine

AT = datetime(2026, 2, 9, 14, 0, tzinfo=UTC)


def me(eid="ME-X", **kw) -> MarketEvent:
    base = {"id": eid, "kind": "news", "channel": "scraper", "source": "Wire", "headline": "h",
            "published_at": AT, "occurred_at": AT}
    return MarketEvent.model_validate({**base, **kw})


@pytest.fixture(scope="module")
def eng():
    return constructed_engine()


@pytest.fixture
def tctx(eng):
    emitted = []
    ctx = TranslationContext(eng.wm, eng.ltm, eng.vocab, AT, emit=lambda kind, **p: emitted.append((kind, p)))
    ctx.emitted = emitted
    return ctx


# -- sources and scrapers ------------------------------------------------------------------------
def _jsonl(tmp_path, events):
    p = tmp_path / "market_events.jsonl"
    p.write_text("\n\n".join(json.dumps(e.model_dump(mode="json")) for e in events) + "\n\n")
    return p


def test_sources_read_jsonl_skip_blank_lines_and_find_by_id(tmp_path):
    assert load_market_events(tmp_path / "missing.jsonl") == ([], {})
    a, b = me("ME-B", published_at=AT + timedelta(days=1)), me("ME-A", channel="data_feed")
    p = _jsonl(tmp_path, [a, b])
    src = JsonlReplaySource(p, channel="scraper")
    assert [e.id for e in src.events] == ["ME-A", "ME-B"]        # published_at order
    assert src.get("ME-B").id == "ME-B" and src.get("ME-none") is None
    assert [e.id for e in src.poll(None, AT + timedelta(days=2))] == ["ME-B"]   # the scraper channel only
    hist = HistoryReplaySource(path=p)
    assert [e.id for e in hist.poll(AT, AT + timedelta(days=2))] == ["ME-B"]     # since is exclusive
    assert HistoryReplaySource().events == []


def test_mock_scraper_waits_its_latency(tmp_path, monkeypatch):
    slept = []
    monkeypatch.setattr(scrapers.time, "sleep", slept.append)
    s = MockWebScraper(scenario_dir=tmp_path, latency_s=0.25)
    assert s.path == tmp_path / "market_events.jsonl" and s.events == []
    assert s.poll(None, AT) == [] and slept == [0.25]


# -- the resolver ----------------------------------------------------------------------------------
def _graph():
    ent = SimpleNamespace(name="Delta Air Lines", aliases=["DAL"], subentity_ids=["delta.fuel", "delta.gone"],
                          features={"region": "US"})
    sub = SimpleNamespace(name="jet fuel cost", aliases=[], features={"product": "fuel"})
    return SimpleNamespace(entities={"delta": ent}, subentities={"delta.fuel": sub})


def test_resolver_edges():
    g = _graph()
    assert text_similarity(None, ["x"]) == 0.0 and text_similarity("", ["x"]) == 0.0
    assert text_similarity("delta", ["", "delta"]) == 1.0          # empty strings are skipped
    assert entity_strings("nobody", g) == []
    assert entity_strings("delta", g) == ["Delta Air Lines", "DAL", "jet fuel cost"]   # a missing value is skipped
    assert constraint_fraction("nobody", {"region": "US"}, g) == 0.0
    assert constraint_fraction("delta", {"region": "US", "product": "fuel"}, g) == 1.0
    r = AliasFuzzyResolver()
    # no mention: only the constraints count
    assert r.score("delta", None, {"region": "US"}, g) == pytest.approx(0.2)
    assert r.resolve(None, {}, ["delta", "nobody"], g) == [("delta", 0.0)]
    with pytest.raises(TypeError):
        EntityResolver()                       # abstract
    assert EntityResolver.resolve(r, None, {}, [], g) is None      # the abstract body


# -- translators -----------------------------------------------------------------------------------
def test_translation_context_reads_the_model(eng, tctx):
    eid = sorted(eng.wm.graph.entities)[0]
    hits = tctx.search_entities(eng.wm.graph.entities[eid].name, limit=2)
    assert len(hits) == 2 and hits[0][0] == eid
    subs = tctx.subentities_of(eid)
    assert subs and all(s.entity_id == eid for s in subs)
    assert tctx.subentities_of("no_such_entity") == []
    assert tctx.attribute_vocabulary() is eng.vocab
    rows = tctx.taxonomy_outline(TaxonomyKind.OBJECT, 1)
    assert rows[0][2] == 0 and {d for _, _, d in rows} == {0, 1}
    assert tctx.admitted_patterns() == eng.ltm.object_generalizations.admitted()
    assert tctx.recent_events() == []
    ctx2 = TranslationContext(eng.wm, eng.ltm, eng.vocab, AT, recent=lambda n: ["e"] * n)
    assert ctx2.recent_events(3) == ["e", "e", "e"]
    ctx2.emit("anything", x=1)                 # the default emit does nothing
    # a taxonomy without its root has no outline
    empty = SimpleNamespace(taxonomy=lambda kind: SimpleNamespace(root_id="r", nodes={}))
    assert TranslationContext(eng.wm, empty, eng.vocab, AT).taxonomy_outline(TaxonomyKind.OBJECT) == []


def test_fill_event_without_a_market_event():
    assert fill_event({"ops": []}, None, "human") == {"ops": [], "produced_by": "human", "kind": "real"}


def test_data_feed_with_a_given_map_and_nothing_known(eng, tctx):
    sid = next(iter(eng.wm.graph.subentities))
    t = DataFeedTranslator(series_map={"SERIES": sid})
    out = t.translate(me(kind="data", channel="data_feed", data={"SERIES": 1.0}), tctx)
    assert out.events[0].ops[0].target.subentity_id == sid
    none = t.translate(me("ME-N", kind="data", channel="data_feed", data={"UNKNOWN": 1.0}), tctx)
    assert none.events == [] and none.rationale == "no known series"
    assert ("translate.missing", {"market_event_id": "ME-N", "key": "UNKNOWN"}) in tctx.emitted


RULES = """
subjects:
  - {pattern: "oil", subentity: resources_energy.oil_price}
  - {pattern: "euro", subentity: fx.dollar_index, invert: true}
  - {pattern: "gas", subentity: resources_energy.gas_price}
verbs:
  - {pattern: "wobbled"}
  - {pattern: "moved by (?P<num>[0-9.]+) ?(?P<unit>bp|sd|%|points)?", sign: -1.0}
  - {pattern: "doubled", delta: 1.0, mode: relative}
timeframes:
  - {pattern: "next week", days: 7}
"""


@pytest.fixture
def template(tmp_path):
    p = tmp_path / "templates.yaml"
    p.write_text(RULES)
    return TemplateTranslator(templates=p)


@pytest.mark.parametrize("text, delta, mode", [
    ("oil moved by 25 bp", -0.25, "absolute"),
    ("oil moved by 2 sd", -2.0, "standardized"),
    ("oil moved by 3 points", -3.0, "absolute"),
    ("oil moved by 10%", -0.1, "relative"),
    ("the euro doubled", 1.0 / 2.0 - 1.0, "relative"),
    ("the euro moved by 2 sd", 2.0, "standardized"),
])
def test_template_units_and_inverted_subjects(template, text, delta, mode):
    ops, spans = template.parse(text, AT)
    assert len(ops) == 1 and ops[0]["delta"] == pytest.approx(delta) and ops[0]["mode"] == mode
    assert text[spans[0][0]:spans[0][1]].startswith(("oil", "euro"))


def test_template_skips_verbs_without_a_size_and_unmatched_subjects(template):
    # "wobbled" names no size: skipped; gas matches no verb at all; the timeframe moves the change a week out
    ops, spans = template.parse("oil wobbled, gas fell, oil doubled next week", AT)
    assert [(o["target"]["subentity_id"], o["delta"]) for o in ops] == [("resources_energy.oil_price", 1.0)]
    assert ops[0]["at"] == (AT + timedelta(days=7)).isoformat()


def test_template_without_a_match_returns_nothing(template, tctx):
    out = template.translate(me("ME-T", headline="nothing here"), tctx)
    assert out.events == [] and out.rationale == "no template matched"
    assert ("translate.missing", {"market_event_id": "ME-T"}) in tctx.emitted
    assert TemplateTranslator(templates="/no/such/file.yaml").rules.subjects == []


class FakeLLM:
    def __init__(self):
        self.prompts = []

    def complete(self, prompt, schema):
        self.prompts.append(prompt)
        return json.dumps({"market_event_id": "ignored", "rationale": "llm",
                           "events": [{"occurred_at": AT.isoformat(), "ops": []}]})


def test_llm_translator_needs_a_client_and_fills_its_events(eng, tctx):
    with pytest.raises(LLMNotConfigured):
        LLMTranslator().translate(me(), tctx)
    llm = FakeLLM()
    out = LLMTranslator(client=llm).translate(me("ME-L", mentions=["oil"]), tctx)
    assert out.market_event_id == "ME-L" and out.rationale == "llm"
    ev = out.events[0]
    assert ev.id == "GUE-ME-L" and ev.produced_by == "llm" and ev.mentions == ["oil"]
    prompt = llm.prompts[0]
    assert prompt.startswith("Translate the market event") and "Entities:" in prompt
    some = next(iter(eng.wm.graph.entities.values()))
    assert json.dumps(some.name)[1:-1] in prompt


# -- bundles ---------------------------------------------------------------------------------------
class Graph:
    subentities = {"a.x": 1, "b.y": 1}

    def active_interactions(self):
        return []


def test_signal_with_a_missing_end_and_unfound_quote():
    item = ImportItem(id="I1", published_at=AT, source="s", headline="Head", summary="Body", category="rates",
                      signals=[Link(type="link", source="a.x", target="nowhere.z", label="l", effect=1.0),
                               Observe(type="observe", value_of="a.x", value=2.0, quote="not in the text", note="n1")])
    ev = market_event_of(item, "IM-I1", synthetic=True)
    res, dropped = translate_item(item, ev, Graph())
    assert dropped == ["link (no value nowhere.z)"] and res.spans == []
    assert res.rationale == "s (news), categorized as rates: n1"
    item2 = item.model_copy(update={"signals": [Link(type="link", source="nowhere.q", target="a.x", label="l",
                                                     effect=1.0)]})
    res2, dropped2 = translate_item(item2, ev, Graph())
    assert res2.events == [] and dropped2 == ["link (no value nowhere.q)"]
    res3, _ = translate_item(item.model_copy(update={"signals": []}), ev, Graph())
    assert res3.rationale == "nothing to change: no signals"
    assert signal_ops(Move(type="move", value_of="nowhere.z", delta=0.1), Graph(), AT) == ([], "no value nowhere.z")
    assert signal_ops(Support(type="support", source="a.x", target="b.y"), Graph(), AT) == ([], "no link a.x -> b.y")


def test_structured_translator_ignores_items_it_did_not_import(tctx):
    out = StructuredTranslator(runner=SimpleNamespace(imported={})).translate(me(), tctx)
    assert out.events == [] and out.rationale == "not an imported item"
    item = ImportItem(id="I2", published_at=AT, source="s", headline="h",
                      signals=[Observe(type="observe", value_of="resources_energy.oil_price", value=80.0)])
    got = StructuredTranslator(runner=SimpleNamespace(imported={"IM-I2": item})).translate(me("IM-I2"), tctx)
    assert got.events[0].ops[0].op == "observe_value"


# -- the pipeline's op summaries -------------------------------------------------------------------
def test_op_summaries_for_the_rarer_ops():
    ev = GraphUpdateEvent.model_validate({
        "id": "E", "kind": "real", "occurred_at": AT, "recorded_at": AT, "produced_by": "human", "ops": [
            {"op": "retire_entity", "entity_id": "delta", "reason": "gone"},
            {"op": "propose_hypothesis", "hypothesis": {
                "id": "H1", "kind": "interaction_present", "statement": "oil drives fares", "probability": 0.5,
                "scored_at": AT.isoformat(), "origin": "human"}}]})
    assert op_summary(ev.ops[0]) == "retire delta and its interactions"
    assert op_summary(ev.ops[1]) == "hypothesis: oil drives fares"
    assert op_summary(SimpleNamespace(op="something_new")) == "something_new"
