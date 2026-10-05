"""Superentity abduction at consolidation (§8.8 count): candidates, admission, growth, decay,
evidence of absence, and composition."""

from __future__ import annotations

from datetime import timedelta

from axelrod_wm.core.superentity import SuperentityStatus
from axelrod_wm.memory.episodes import Episode
from axelrod_wm.memory.working import ActivityRecord
from tests.conftest import START, warm_taxonomies

CHAIN = [("e46", "northwind_semis.export_revenue", -0.6, -0.7),
         ("e47", "northwind_semis.share_price", -0.5, -0.6),
         ("e48", "northwind_semis.capex", -0.4, -0.5)]


def _episode(eng, k, day, active, patterns=()):
    return Episode(id=f"EP-t{k}", start=day, end=day, trigger_event_ids=[f"GUE-{k}"], event_types=["regulatory_action"],
                   signature=set(), key_signature=set(), deltas={}, active_interaction_ids=sorted(active),
                   edge_effects={}, active_pattern_ids=list(patterns), step=eng.wm.deviations.step_of(day))


def _count(eng, k, day, records, patterns=()):
    """Write an activity log and run inducer.count for one episode."""
    ctx = eng.context(learn=True, now=day)
    with eng.mutator.begin(f"count-{k}", now=day) as txn:
        txn.set("wm.activity_log", records)
        ep = _episode(eng, k, day, {r.interaction_id for r in records}, patterns)
        txn.add("episodes", ep)
        res = eng.components["inducer"].count(ep, eng.wm, eng.ltm, ctx, txn)
        txn.set("wm.activity_log", [])
        txn.set("wm.last_consolidated", day.date())
    return res


def _records(step, chain=CHAIN, extra=()):
    return [ActivityRecord(step=step, interaction_id=i, contribution=c, target_move=m, target_id=t)
            for i, t, c, m in list(chain) + list(extra)]


def test_planted_configuration_becomes_candidate_then_admission(warm_engine):
    eng = warm_engine
    proposals = []
    cand = None
    for k in range(4):
        day = START + timedelta(days=1100 + k)
        res = _count(eng, k, day, _records(eng.wm.deviations.step_of(day)))
        if k == 0:
            assert len(res.candidate_pattern_ids) == 1
            cand = res.candidate_pattern_ids[0]
            p = eng.ltm.patterns.patterns[cand]
            assert p.status == SuperentityStatus.CANDIDATE and p.origin == "inference"
            assert p.name.startswith("Export controls") or "Northwind" in p.name
            inst = [i for i in eng.wm.graph.instances.values() if i.pattern_id == cand]
            assert inst and sorted(inst[0].interaction_ids) == ["e46", "e47", "e48"]
        else:
            assert cand in res.supported_pattern_ids and not res.candidate_pattern_ids
        proposals += res.proposal_events
    p = eng.ltm.patterns.patterns[cand]
    assert p.support > 3
    kinds = [x["kind"] for x in proposals]
    assert kinds == ["superentity_admission"]
    # a component that grows around the pattern still matches
    day = START + timedelta(days=1105)
    grown = _records(eng.wm.deviations.step_of(day),
                     extra=[("e09", "cross_border_trade.trade_volume", -0.45, -0.5)])
    res = _count(eng, 9, day, grown)
    assert cand in res.supported_pattern_ids and not res.candidate_pattern_ids
    # approval admits and binds it
    from axelrod_wm.events.graph_update import GraphUpdateEvent

    eng.structural.apply(GraphUpdateEvent.model_validate(proposals[0]["event"]), day, "superentity_admission")
    p = eng.ltm.patterns.patterns[cand]
    assert p.status == SuperentityStatus.ADMITTED
    assert eng.ltm.object_taxonomy.is_under(p.generalization_id, "gen:obj:configuration")


def test_pattern_that_stops_occurring_decays_and_gets_a_dissolution_proposal(warm_engine):
    eng = warm_engine
    with eng.mutator.begin("weak", now=START) as txn:
        txn.update("patterns", "S6", support=1.2)
        txn.set("wm.last_consolidated", (START + timedelta(days=1000)).date())
    day = START + timedelta(days=1060)
    res = _count(eng, 1, day, [])
    assert eng.ltm.patterns.patterns["S6"].support < 1.0
    assert any(p["kind"] == "superentity_dissolution" and p["event"]["ops"][0]["pattern_id"] == "S6"
               for p in res.proposal_events)


def test_evidence_of_absence_supports_the_absent_pattern(warm_engine):
    eng = warm_engine
    day = START + timedelta(days=1100)
    step = eng.wm.deviations.step_of(day)
    with eng.mutator.begin("moves", now=day) as txn:
        # headline CPI rose by 1.5 sd before e43's response window (45 + 30 days, 11 steps); over that
        # window the Fed's stance does not move
        txn.merge("wm.deviations", {"z": {"inflation.headline_cpi": {step - 16: 0.0, step - 11: 1.5, step: 1.5},
                                          "federal_reserve.policy_stance": {step - 20: 0.2, step: 0.25}}})
    before = eng.ltm.patterns.patterns["S9"].support
    s8_before = eng.ltm.patterns.patterns["S8"].support
    res = _count(eng, 1, day, [])
    assert "S9" in res.supported_pattern_ids
    assert eng.ltm.patterns.patterns["S9"].support > before
    assert eng.ltm.patterns.patterns["S8"].support <= s8_before


def test_two_patterns_active_together_form_a_composite(warm_engine):
    eng = warm_engine
    base = START + timedelta(days=1100)
    with eng.mutator.begin("history", now=base) as txn:
        for k in range(4):
            txn.add("episodes", _episode(eng, 100 + k, base - timedelta(days=7 * (k + 1)), {"e20", "e08", "e24"},
                                         patterns=("S1", "S2")))
    res = _count(eng, 1, base, [])
    comps = [eng.ltm.patterns.patterns[c] for c in res.candidate_pattern_ids]
    pairs = [sorted(c.sub_pattern_ids) for c in comps if c.sub_pattern_ids]
    assert ["S1", "S2"] in pairs
    comp = next(c for c in comps if sorted(c.sub_pattern_ids) == ["S1", "S2"])
    inst = next(i for i in eng.wm.graph.instances.values() if i.pattern_id == comp.id)
    assert sorted(inst.child_instance_ids) == ["inst-S1", "inst-S2"]
    assert "e20" in inst.interaction_ids


def test_initialization_counts_seed_support_only(warm_engine):
    eng = warm_engine
    eng.initializing = True
    day = START + timedelta(days=50)
    res = _count(eng, 1, day, _records(eng.wm.deviations.step_of(day)))
    assert not res.candidate_pattern_ids and not res.proposal_events
    eng.initializing = False
    warm_taxonomies(eng, rounds=1)
