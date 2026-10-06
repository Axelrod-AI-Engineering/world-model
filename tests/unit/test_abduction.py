"""Superentity abduction at the daily consolidation (§8.8 count): candidates, admission, growth,
evidence spacing, activity from changes only, decay, evidence of absence, and composition."""

from __future__ import annotations

from axelrod_wm.core.superentity import SuperentityStatus
from axelrod_wm.memory.working import ActivityRecord, DeviationPoint, activity_key, point_key
from tests.conftest import close_day, predict_day, warm_taxonomies

CHAIN = [("e46", "nvidia.china_revenue", -0.6, -0.7),
         ("e47", "nvidia.share_price", -0.5, -0.6),
         ("e48", "nvidia.capex", -0.4, -0.5)]


def _count(eng, day: int, records=(), patterns_active=()):
    """Write the day's activity log and run inducer.count(day)."""
    dev = eng.wm.deviations
    ctx = eng.context(learn=True, now=dev.day_end(day), processing_day=day)
    with eng.mutator.begin(f"count-{day}", at=ctx.now) as txn:
        txn.clear("wm.activity_log")
        for r in records:
            txn.add("wm.activity_log", r, key=activity_key(r.day, r.channel_id))
        res = eng.components["inducer"].count(day, eng.wm, eng.ltm, ctx, txn)
    return res


def _records(day, chain=CHAIN, extra=()):
    return [ActivityRecord(day=day, channel_id=i, contribution_change=c, target_move=m, target_id=t)
            for i, t, c, m in list(chain) + list(extra)]


def test_planted_configuration_becomes_candidate_then_admission(warm_engine):
    eng = warm_engine
    proposals = []
    cand = None
    for k in range(4):
        day = 1100 + 20 * k                     # triggered four times, 20 days apart
        res = _count(eng, day, _records(day))
        if k == 0:
            assert len(res.candidate_pattern_ids) == 1
            cand = res.candidate_pattern_ids[0]
            p = eng.ltm.object_generalizations.patterns[cand]
            assert p.status == SuperentityStatus.CANDIDATE and p.origin == "inference"
            assert p.last_counted_day == day
            inst = [i for i in eng.wm.graph.instances.values() if i.pattern_id == cand]
            # the planted links, plus any link of the same kind among the bound entities (NVIDIA's other
            # revenue line drives its share price too)
            assert inst and {"e46", "e47", "e48"} <= set(inst[0].interaction_ids)
        else:
            assert cand in res.supported_pattern_ids and not res.candidate_pattern_ids
        proposals += res.proposal_events
    p = eng.ltm.object_generalizations.patterns[cand]
    assert p.support > 3
    assert [x["kind"] for x in proposals] == ["superentity_admission"]
    # a component that grows around the pattern still matches
    day = 1100 + 20 * 4
    grown = _records(day, extra=[("e09", "cross_border_trade.trade_volume", -0.45, -0.5)])
    res = _count(eng, day, grown)
    assert cand in res.supported_pattern_ids and not res.candidate_pattern_ids
    # approval admits it under the configuration node, binds it, and pools its relation effects
    from axelrod_wm.events.graph_update import GraphUpdateEvent

    eng.structural.apply(GraphUpdateEvent.model_validate(proposals[0]["event"]), eng.wm.clock, "superentity_admission")
    p = eng.ltm.object_generalizations.patterns[cand]
    tax = eng.ltm.object_generalizations.taxonomy
    assert p.status == SuperentityStatus.ADMITTED
    assert tax.is_under(p.generalization_id, "gen:obj:configuration")
    assert tax.nodes["gen:obj:configuration"].stats.relation_effects


def test_one_long_shock_counts_once_per_spacing(warm_engine):
    eng = warm_engine
    first = _count(eng, 1100, _records(1100))
    cand = first.candidate_pattern_ids[0]
    supports = []
    for day in range(1101, 1130):               # the same configuration stays active for four weeks
        res = _count(eng, day, _records(day))
        supports.append(cand in res.supported_pattern_ids)
    spacing = eng.config.abduction.evidence_spacing_days
    counted = [1101 + i for i, s in enumerate(supports) if s]
    assert counted == [1100 + spacing, 1100 + 2 * spacing]
    assert eng.ltm.object_generalizations.patterns[cand].support < 3.2


def test_a_permanent_old_effect_does_not_keep_a_configuration_active(warm_engine):
    """Activity measures transmitted change: once a step's ramp has passed, its permanent effect
    leaves no activity records."""
    from axelrod_wm.engine.daily import ensure_channel_states

    eng = warm_engine
    dev = eng.wm.deviations
    src = "legal_regulatory.export_controls"
    # a step of 2 sd in export controls on day 0 that has stayed since (days 0..399)
    with eng.mutator.begin("history", at=eng.wm.clock) as txn:
        for d in range(400):
            for sid in eng.wm.graph.subentities:
                z = 2.0 if sid == src else 0.0
                txn.add("wm.deviations.points", DeviationPoint(z=z, var=0.01, level=z), key=point_key(sid, d))
        txn.set("wm.last_processed_day", 399)
        txn.set("wm.clock", dev.day_end(399))
        ctx = eng.context(learn=True, now=dev.day_end(399))
        for iid in sorted(eng.wm.graph.interactions):
            ensure_channel_states(eng.wm.graph.interactions[iid], eng.wm, ctx, txn, day=400)
    predict_day(eng, 400)
    close_day(eng, 400)
    assert not any(r.channel_id in ("e46", "e09") for r in eng.wm.activity_log.values())


def test_pattern_that_stops_occurring_decays_and_gets_a_dissolution_proposal(warm_engine):
    eng = warm_engine
    with eng.mutator.begin("weak", at=eng.wm.clock) as txn:
        txn.update("ltm.object_generalizations.patterns", "S6", support=1.005)
    res = _count(eng, 1060)
    assert eng.ltm.object_generalizations.patterns["S6"].support < 1.0
    assert any(p["kind"] == "superentity_dissolution" and p["event"]["ops"][0]["pattern_id"] == "S6"
               for p in res.proposal_events)


def test_evidence_of_absence_supports_the_absent_pattern(warm_engine):
    eng = warm_engine
    day = 1100
    cpi, stance = "inflation.headline_cpi", "federal_reserve.policy_stance"
    with eng.mutator.begin("moves", at=eng.wm.clock) as txn:
        # headline CPI rose by 1.5 sd before e43's span (45 + 30 days); over that span the Fed's stance
        # barely moved
        for d, z in ((day - 75 - 28, 0.0), (day - 75, 1.5)):
            txn.add("wm.deviations.points", DeviationPoint(z=z, var=0.01, level=z), key=point_key(cpi, d))
        for d, z in ((day - 75, 0.2), (day, 0.25)):
            txn.add("wm.deviations.points", DeviationPoint(z=z, var=0.01, level=z), key=point_key(stance, d))
    pats = eng.ltm.object_generalizations.patterns
    before, s8_before = pats["S9"].support, pats["S8"].support
    res = _count(eng, day)
    assert "S9" in res.supported_pattern_ids
    assert pats["S9"].support > before
    assert pats["S8"].support <= s8_before


def test_two_patterns_counted_together_form_a_composite(warm_engine):
    eng = warm_engine
    pats = eng.ltm.object_generalizations.patterns
    with eng.mutator.begin("history", at=eng.wm.clock) as txn:
        days = [1000, 1020, 1040, 1060]          # counted together four times, at least 14 days apart
        for pid in ("S1", "S2", "S3"):
            txn.update("ltm.object_generalizations.patterns", pid, counted_days=days)
    res = _count(eng, 1100)
    comps = [pats[c] for c in res.candidate_pattern_ids]
    pairs = [sorted(c.sub_pattern_ids) for c in comps if c.sub_pattern_ids]
    # S1 and S3 meet across "sparks crises"; S1 and S2 already form the seeded composite S10
    assert ["S1", "S3"] in pairs and ["S1", "S2"] not in pairs
    comp = next(c for c in comps if sorted(c.sub_pattern_ids) == ["S1", "S3"])
    inst = next(i for i in eng.wm.graph.instances.values() if i.pattern_id == comp.id)
    assert sorted(inst.child_instance_ids) == ["inst-S1", "inst-S3"]


def test_initialization_counts_seed_support_only(warm_engine):
    eng = warm_engine
    eng.initializing = True
    try:
        res = _count(eng, 50, _records(50))
        assert not res.candidate_pattern_ids and not res.proposal_events
    finally:
        eng.initializing = False
    warm_taxonomies(eng, rounds=1)
