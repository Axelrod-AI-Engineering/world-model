"""Staged review (Oct 8) beyond the small demo's chain: every kind of item, the reviewer's confidences, staging
with nothing selected or a run that fails, a world event staged outside an update run, fuzzy ends, a frontier
promotion's evidence, recall in words, long-term lessons, and the text form of a review."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace as NS

import pytest

from axelrod_wm.control import stage as st
from axelrod_wm.control.controller import ControllerError
from axelrod_wm.control.stage import (
    Adjustment,
    Learned,
    StagedItem,
    StagedReview,
    StageIO,
    format_review,
    sandbox,
    stage,
    with_confidence,
)
from axelrod_wm.control.updates import UpdateRequest, UpdateState
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.repo.mutator import Change, ChangeSet
from axelrod_wm.repo.review import ProposalKind
from tests.conftest import SEEDS, constructed_engine, make_controller, warm_taxonomies
from tests.unit.control.test_update_loop import ListSource, at, news

CPI, OIL = "inflation.headline_cpi", "resources_energy.oil_price"
T = at(0).isoformat()


@pytest.fixture
def ctl():
    c = make_controller(constructed_engine(build=True))
    warm_taxonomies(c.engine)
    c.auto_resume = False
    c.set_review_policy("review_all")
    return c


def event(ops: list[dict], eid: str = "GUE-S", **kw) -> GraphUpdateEvent:
    return GraphUpdateEvent.model_validate({"id": eid, "kind": "real", "occurred_at": T, "recorded_at": T,
                                            "produced_by": "human", "ops": ops, **kw})


def edge(src: str = "fed_chair.hawkishness", dst: str = "interest_rates.long_term_yields") -> dict:
    return {"op": "add_interaction", "source": {"kind": "concrete", "subentity_id": src},
            "target": {"kind": "concrete", "subentity_id": dst}, "label": "moves", "polarity": 1}


# ---------------------------------------------------------------------------------------------------------------
# items, confidences, and the sandbox
# ---------------------------------------------------------------------------------------------------------------
def test_every_kind_of_item_has_a_label(ctl):
    eng = ctl.engine
    wm, ltm = eng.wm, eng.ltm
    ev = event([
        {"op": "retire_entity", "entity_id": "ecb", "reason": "x"},
        {"op": "retire_entity", "entity_id": "gone", "reason": "x"},
        {"op": "reweight_interaction", "interaction_id": "e01", "supports": True},
        {"op": "reweight_interaction", "interaction_id": "e-gone", "supports": False},
        {"op": "annotate_interaction", "interaction_id": "e01", "note": "watch it", "valid_from": T},
        {"op": "propose_hypothesis", "hypothesis": {
            "id": "H-1", "kind": "interaction_present", "statement": "oil moves CPI", "source_id": OIL,
            "target_id": CPI, "probability": 0.5, "scored_at": T, "origin": "human"}},
        {"op": "add_interaction", "source": {"kind": "abstract", "mention": "chip makers"},
         "target": {"kind": "abstract", "entity_id": "inflation"}, "label": "lifts", "polarity": -1},
        {"op": "add_interaction", "source": {"kind": "abstract", "generalization_id": "gen:obj:actor"},
         "target": {"kind": "abstract"}, "label": "lifts", "polarity": 1},
    ])
    names = st._names(ev, wm)
    labels = [st._item(i, op, names, wm, ltm) for i, op in enumerate(ev.ops)]
    assert [(x.action, x.what) for x in labels[:6]] == [("retire", "entity"), ("retire", "entity"),
                                                        ("reweight", "interaction"), ("reweight", "interaction"),
                                                        ("note", "interaction"), ("hypothesis", "hypothesis")]
    ecb = wm.graph.entities["ecb"].name
    assert labels[0].label == f"Retire {ecb}, with its values and interactions" and labels[0].refs == ["ecb"]
    assert labels[1].label == "Retire gone, with its values and interactions"
    assert labels[2].label.startswith("Strengthen the belief in ") and "(" in labels[2].label
    assert labels[3].label == "Weaken the belief in e-gone"
    assert labels[4].label == "Note on e01: watch it" and labels[5].label == "Hypothesis: oil moves CPI"
    assert labels[6].label == "New interaction: chip makers → inflation (lifts, −)"
    assert labels[7].label == "New interaction: gen:obj:actor → ? (lifts, +)"


def test_the_reviewers_confidences_and_ripple_weights():
    ev = event([edge(), edge(src=OIL, dst=CPI)]).model_copy(update={"ripple": {"a": 0.5, "b": 0.2}})
    out = with_confidence(ev, confidence=1.7, op_confidence={0: 0.4, 1: None, 7: 0.9},
                          ripple={"a": None, "b": 1.0, "c": -0.3, "d": 0.6})
    assert out.ripple == {"c": 0.0, "d": 0.6}        # None or a sure arrival clears; others clip to [0, 1]
    assert out.user_confidence == 1.0
    assert [op.confidence for op in out.ops] == [0.4, None]       # an index past the end is ignored
    assert with_confidence(ev) is ev


def test_the_sandbox_hands_back_the_live_state(ctl):
    eng = ctl.engine
    live = (eng.wm, eng.ltm, eng.version, eng.hasher, eng.ledger)
    with sandbox(eng) as tracer:
        assert eng.hasher.full(eng.wm, eng.ltm) == "staged" == eng.hasher.update()
        assert eng.wm is not live[0] and tracer.run_id == "staged"
    assert (eng.wm, eng.ltm, eng.version, eng.hasher, eng.ledger) == live


# ---------------------------------------------------------------------------------------------------------------
# staging
# ---------------------------------------------------------------------------------------------------------------
def test_staging_an_unknown_proposal_is_refused(ctl):
    with pytest.raises(ControllerError, match="unknown proposal PR-9"):
        stage(ctl, "PR-9")


def test_staging_with_nothing_selected_runs_nothing(ctl):
    p = ctl.submit_graph_update(event([edge()]), by="kim")
    r = stage(ctl, p.id, keep=[], with_graph=False)
    assert r.keep == [] and not r.items[0].selected and r.error is None and r.graph is None
    assert r.stages[1].input == "0 of 1 operation(s) selected"
    assert r.stages[1].output == "no change to working memory" and r.commits == []
    assert r.headline == r.items[0].label                # no article and no reason: the first item says it


def test_a_staged_run_that_fails_is_shown_not_raised(ctl, monkeypatch):
    p = ctl.submit_graph_update(event([edge()]), by="kim")
    v = ctl.engine.version
    monkeypatch.setattr(ctl.engine.structural, "apply", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad edge")))
    r = stage(ctl, p.id, with_graph=False)
    assert r.error == "ValueError: bad edge" and r.stages[1].output == "the staged run failed: ValueError: bad edge"
    assert ctl.engine.version == v and p.id not in ctl._effects_applied
    assert "  staged run failed: ValueError: bad edge" in format_review(r)


def test_a_world_event_staged_after_its_run_opens_the_next_day_on_the_copy(ctl):
    ctl.register_source("feed", ListSource([news("N1", 1, "Oil jumps by 20%")]))
    ctl.engine.config.update.sources = ["feed"]
    run = ctl.request_update(UpdateRequest(requested_by="user", until=at(2).date(), requested_at=at(2, 23)))
    assert run.state == UpdateState.AWAITING_REVIEW
    pid = run.waiting_on
    ctl.cancel_update(run.id)                          # the news is deferred; no run is active any more
    assert ctl.active_update is None
    last = int(ctl.engine.wm.last_processed_day)
    r = stage(ctl, pid, with_graph=False)
    assert r.error is None and r.world_event and r.article["id"] == "N1"
    assert int(ctl.engine.wm.last_processed_day) == last  # the live model did not move
    # values are named with their owner when their own name lacks it ("Resources & energy · Oil price")
    assert r.moves and any(" · " in m.name for m in r.moves + r.ripple)


def test_a_fuzzy_end_shows_as_a_hedge_over_its_candidates(ctl):
    ev = event([{"op": "change_value", "target": {"kind": "abstract", "mention": "energy prices"}, "delta": 0.1,
                 "mode": "relative", "persistence": "step", "at": T}])
    ref = ctl.refine(ev)
    assert ref.pending
    p = ctl.propose(ProposalKind.GRAPH_UPDATE, ref.event, pending=ref.pending, world=True)
    r = stage(ctl, p.id, with_graph=False)
    (pend,) = r.pending
    assert pend["label"] == "“energy prices”" and pend["end"] == "subject"
    names = {c["id"]: c["name"] for c in pend["candidates"]}
    assert names.get("__open__", "one not in the graph yet") == "one not in the graph yet"
    g = ctl.engine.wm.graph
    assert all(names[c] == (g.entities[c].name if c in g.entities else g.subentities[c].name if c in g.subentities
                            else c) for c in names if c != "__open__")
    assert all(c["score"] == c["p"] for c in pend["candidates"])
    assert "  Pending: “energy prices”; candidates " in format_review(r)


def test_hedge_view_names_paths_and_unknown_candidates(ctl):
    g = ctl.engine.wm.graph
    op = NS(source=NS(kind="concrete", subentity_id=OIL), target=NS(kind="concrete", subentity_id="gone.value"),
            label="lifts")
    pend = NS(op=op, ends=[], end="target", id="P1", key="k", soft=True, support=1.0, status="holding",
              posterior=lambda: {f"resources_energy|{CPI}": 0.5, "nope": 0.2, "__open__": 0.3})
    v = st.hedge_view(pend, g)
    assert v["label"] == f"{g.subentities[OIL].name} → gone.value (lifts)" and v["ends"] == ["target"]
    assert [c["name"] for c in v["candidates"]] == [
        f"{g.entities['resources_energy'].name} → {g.subentities[CPI].name}", "nope", "one not in the graph yet"]
    abstract = NS(op=NS(target=NS(kind="abstract", mention=None, attribute_kind=None)), ends=None, end="subject",
                  id="P2", key="k", soft=False, support=0.0, status="holding", posterior=lambda: {})
    assert st.hedge_view(abstract, g)["label"] == "“an end”"


# ---------------------------------------------------------------------------------------------------------------
# a frontier promotion's evidence, and recall in words
# ---------------------------------------------------------------------------------------------------------------
def test_promotion_evidence_lists_the_checks_with_articles_and_none_without_its_pair(ctl):
    from axelrod_wm.engine.initialize import Initializer, SeedFile
    from axelrod_wm.learning.frontier_test import promotion_event

    eng = ctl.engine
    cms = Initializer(eng).load_frontier_seeds(SeedFile.load(SEEDS), now=eng.wm.clock)
    co = eng.ltm.correlation_frontier.entries[cms[0]]
    p = ctl.propose(ProposalKind.FRONTIER_PROMOTION, promotion_event(co, eng.context(learn=False, now=ctl.now)),
                    subject_id=co.id)
    assert st._evidence(ctl, p)["first_seen"] is None    # a seeded pair was never "first seen"
    with eng.mutator.begin("days", at=ctl.now) as txn:
        txn.update("ltm.correlation_frontier.entries", co.id, passed_days=[5, 9], logged_day=2)
    ev = st._evidence(ctl, p)
    assert ev["checks"] == [] and ev["first_seen"] == {"date": eng.wm.deviations.day_start(2).date().isoformat()}
    assert ev["needed"] == int(ctl.config.thresholds.recognition)
    with eng.mutator.begin("drop", at=ctl.now) as txn:
        txn.remove("ltm.correlation_frontier.entries", co.id)
    assert st._evidence(ctl, p) is None


def test_recall_in_words(ctl):
    eps = {"EP-1": NS(id="EP-1", day=date(2023, 3, 13), trigger_event_ids=["GUE-ME-X", "GUE-N1"],
                      event_types=["data_release", "financial_stress"]),
           "EP-2": NS(id="EP-2", day=date(2024, 1, 1), trigger_event_ids=["GUE-ME-Y"], event_types=["data_release"])}
    ltm = NS(prior_states=NS(episodes=eps), object_generalizations=NS(patterns={"S1": NS(id="S1", name="Credit")}))
    g = ctl.engine.wm.graph
    ctl.market_events["N1"] = news("N1", 1, "Banks wobble")
    evs = [NS(kind="recall.result", payload={"episodes": [{"id": "EP-1", "attention": 0.4},
                                                          {"id": "EP-2", "attention": 0.6},
                                                          {"id": "EP-9", "attention": 0.9}],
                                             "patterns": [{"id": "S1", "attention": 0.5}, {"id": "S9", "attention": 1}]}),
           NS(kind="prefill.adjusted", payload={"interaction_id": "e01", "effect_before": 0.1, "effect_after": 0.5,
                                                "analog_ids": ["EP-1", "EP-9"]}),
           NS(kind="prefill.adjusted", payload={"interaction_id": "e-gone", "effect_before": None, "effect_after": 0.2,
                                                "analog_ids": []}),
           NS(kind="other", payload={})]
    recalled, adjusted = st._recall(ctl, evs, NS(graph=g), ltm)
    assert [(x["id"], x["label"]) for x in recalled] == [("EP-2", "a past day: data releases"), ("S1", "Credit"),
                                                         ("EP-1", "Banks wobble")]
    e01 = g.interactions["e01"]
    assert adjusted[0]["name"] == f"{g.subentities[e01.source_id].name} → {g.subentities[e01.target_id].name}"
    assert adjusted[0]["from"] == ["2023-03-13"] and adjusted[1]["name"] == "e-gone"
    eps["EP-1"].trigger_event_ids = ["GUE-ME-X"]
    recalled, _ = st._recall(ctl, evs[:1], NS(graph=g), ltm)
    assert recalled[-1]["label"] == "a past day: financial stress"


# ---------------------------------------------------------------------------------------------------------------
# what long-term memory would learn, and the review's parts
# ---------------------------------------------------------------------------------------------------------------
def cs(*changes: tuple[str, str], process: str = "learning") -> ChangeSet:
    return ChangeSet(id="CS-1", cause="x", version_before=1, version_after=2, id_counters_after={},
                     changes=[Change(action="update", collection=c, id=i) for c, i in changes], recorded_at=at(0),
                     process=process)


def test_lessons_for_patterns_concepts_and_frontier_pairs(ctl):
    eng = ctl.engine
    live_wm, live_ltm = eng.wm, eng.ltm
    ltm = live_ltm.model_copy(deep=True)
    pats = ltm.object_generalizations.patterns
    pats["S1"].support = float(live_ltm.object_generalizations.patterns["S1"].support) + 1.0
    pats["S2"].support = float(live_ltm.object_generalizations.patterns["S2"].support) + 0.1     # daily decay: quiet
    del pats["S3"]
    changes = cs(("ltm.object_generalizations.patterns", "S1"), ("ltm.object_generalizations.patterns", "S2"),
                 ("ltm.object_generalizations.patterns", "S3"),
                 ("ltm.object_generalizations.taxonomy.nodes", "gen:obj:gone"),
                 ("ltm.prior_states.explanations", "EX-1"))
    out = st._lessons([changes, cs(("ltm.entity_memories", "x"), process="day.record")], live_wm, live_ltm,
                      live_wm, ltm, lambda sid: sid)
    s1 = pats["S1"]
    assert out[0] == (f"Superentity “{s1.name}” gains support ({float(s1.support) - 1:.1f} → {float(s1.support):.1f})")
    assert out[-1] == "The explanation of what was learned is stored with the prior states" and len(out) == 2


def _proposal(ctl):
    return ctl.submit_graph_update(event([edge()]), by="kim")


def test_raises_and_value_names_in_a_review(ctl):
    from axelrod_wm.engine.initialize import Initializer, SeedFile

    eng = ctl.engine
    Initializer(eng).load_frontier_seeds(SeedFile.load(SEEDS), now=eng.wm.clock)
    p = _proposal(ctl)
    items = [st._item(0, p.event.ops[0], st._names(p.event, eng.wm), eng.wm, eng.ltm)]
    # a frontier pair whose earlier value has left the graph (its entity retired) keeps its id in words
    ltm = eng.ltm.model_copy(deep=True)
    co = next(iter(ltm.correlation_frontier.entries.values()))
    live_co = eng.ltm.correlation_frontier.entries[co.id]
    co.earlier_id = "gone.value"
    co.consistent = live_co.consistent + 1
    report = NS(proposal_events=[{"kind": "frontier_promotion", "event": {"ops": [1, 2]}, "reason": "passed"},
                                 {"kind": "refinement", "event": event([edge()], eid="GUE-R")},
                                 {"kind": "x", "event": None}])
    r = st._review(ctl, p, [0], items, None, report, [cs(("ltm.correlation_frontier.entries", co.id))], eng.wm,
                   eng.ltm, eng.wm, ltm, set(), None, None, eng.version, None)
    assert r.raises == [{"kind": "frontier_promotion", "reason": "passed", "ops": 2},
                        {"kind": "refinement", "reason": "", "ops": 1}, {"kind": "x", "reason": "", "ops": 0}]
    assert any(x.startswith("The co-movement gone.value → ") for x in r.lessons)
    assert r.stages[2].output.endswith("; raises 3 proposal(s) for later review")
    assert p.reason is None and r.headline == items[0].label and r.source is None


# ---------------------------------------------------------------------------------------------------------------
# the text form
# ---------------------------------------------------------------------------------------------------------------
def test_format_review_writes_every_part():
    def adj(order: int, name: str) -> Adjustment:
        return Adjustment(subentity_id=name, name=name, order=order, effect=0.5, peak=-0.25, peak_day=3,
                          path=["Oil", name])

    r = StagedReview(
        proposal_id="PR-1", kind="graph_update", status="pending", event_id="GUE-1", world_event=True, keep=[0],
        items=[StagedItem(index=0, op="add_entity", action="add", what="entity", label="New entity: X"),
               StagedItem(index=1, op="add_subentity", action="add", what="subentity", label="New value: X · y",
                          requires=[0], selected=False)],
        stages=[StageIO(phase="intake", title="Intake", input="in", output="out"),
                StageIO(phase="x", title="Skipped", input="-", output="-", status="skipped")],
        moves=[Adjustment(subentity_id="o", name="Oil", order=0, effect=1.25, peak=1.25)],
        ripple=[adj(1, "CPI"), adj(5, "Far")],
        learned=[Learned(kind="value", ref="o", name="Oil", before=None, after=80.0, unit="usd"),
                 Learned(kind="effect", ref="e1", name="Oil → CPI", before=0.1, after=0.2),
                 Learned(kind="existence", ref="e1", name="Oil → CPI", before=0.5, after=0.6)],
        lessons=["A lesson"], raises=[{"kind": "refinement", "reason": "a hedge settles"}],
        article={"headline": "Oil jumps", "source": "wire", "rationale": "an oil move"},
        recalled=[{"label": "A day", "day": "2023-03-13", "attention": 0.5}, {"label": "S1", "attention": 0.25}],
        adjusted=[{"name": f"E{i}", "before": 0.1, "after": 0.2} for i in range(7)],
        pending=[{"label": "“energy”", "candidates": [{"name": "Oil", "score": 0.6}]}],
        version=3, error=None)
    text = format_review(r).splitlines()
    assert text[0] == "PR-1 · GUE-1 · pending"
    assert "  Intake: in → out" in text and not any("Skipped" in x for x in text)
    assert "  Article: “Oil jumps” (wire)" in text and "    an oil move" in text
    assert "    [x] New entity: X" in text and "    [ ] New value: X · y  (needs 1)" in text
    assert "  Pending: “energy”; candidates Oil 0.60" in text
    assert "    Oil +1.25 sd" in text
    assert "    first order: CPI -0.25 sd at its peak (day 3) via Oil → CPI" in text
    assert "    5th order: Far -0.25 sd at its peak (day 3) via Oil → Far" in text
    assert "  Recalled: A day (2023-03-13) 0.50; S1 0.25" in text
    assert sum(1 for x in text if x.startswith("  Adjusted from what followed")) == 6
    assert "  … and 1 more effects adjusted" in text
    assert "    Oil: new → 80 usd" in text and "    effect of Oil → CPI: 0.1 → 0.2" in text
    assert "    existence of Oil → CPI: 0.5 → 0.6" in text
    assert "  Long-term memory:" in text and "    A lesson" in text
    assert text[-1] == "  Raises for later review: refinement (a hedge settles)"
    bare = StagedReview(proposal_id="PR-2", kind="k", status="approved", event_id="GUE-2", world_event=False,
                        keep=[], items=[], stages=[], version=1, headline="Edit",
                        article={"headline": "H", "source": "s"})
    assert format_review(bare).splitlines() == ["PR-2 · Edit · approved", "  Article: “H” (s)", "  Items:"]


def test_a_review_of_a_decided_model_edit_says_committed(ctl):
    ctl.set_review_policy("auto_approve_all")
    p = ctl.submit_graph_update(event([edge()]), by="kim")
    r = stage(ctl, p.id, with_graph=False)
    assert r.stages[3].status == "done" and r.stages[4].output == "committed" and r.status == "auto_applied"
    assert r.stages[0].input == "A backend user's edit"
    learned = ctl.propose(ProposalKind.GRAPH_UPDATE, event([edge(OIL, CPI)], eid="GUE-L", produced_by="engine"))
    r2 = stage(ctl, learned.id, with_graph=False)
    assert r2.stages[0].input == "A proposal from learning (graph_update)"
