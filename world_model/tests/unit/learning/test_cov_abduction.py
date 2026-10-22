"""Superentity abduction (§8.8) at its edges: evidence spacing, the latest and strongest activity per
interaction, dissolved and edge-less patterns, initialization, the candidate palette, and rivals."""

from __future__ import annotations

from axelrod_wm.learning.abduction import spaced_count
from axelrod_wm.memory.working import ActivityRecord, activity_key
from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.superentity import SuperentityInstance, SuperentityStatus

PATTERNS = "ltm.object_generalizations.patterns"
INSTANCES = "wm.graph.instances"
CHAIN = [("e46", "nvidia.china_revenue", -0.6, -0.7),
         ("e47", "nvidia.share_price", -0.5, -0.6),
         ("e48", "nvidia.capex", -0.4, -0.5)]


def _count(eng, day, records=()):
    dev = eng.wm.deviations
    ctx = eng.context(learn=True, now=dev.day_end(day), processing_day=day)
    with eng.mutator.begin(f"count-{day}", at=ctx.now) as txn:
        txn.clear("wm.activity_log")
        for r in records:
            txn.add("wm.activity_log", r, key=activity_key(r.day, r.channel_id))
        return eng.components["inducer"].count(day, eng.wm, eng.ltm, ctx, txn)


def _records(day):
    return [ActivityRecord(day=day, channel_id=i, contribution_change=c, target_move=m, target_id=t)
            for i, t, c, m in CHAIN]


def test_spaced_count_skips_days_inside_the_spacing():
    assert spaced_count([20, 1, 2, 15], 14) == 2        # 1 and 15 count; 2 and 20 are too close
    assert spaced_count([], 14) == 0


def test_the_inducer_reads_the_engines_vocabulary(warm_engine):
    assert warm_engine.components["inducer"].vocab is warm_engine.vocab


def test_active_edges_keep_the_latest_record_and_the_strongest_channel(warm_engine):
    eng = warm_engine
    recs = [ActivityRecord(day=1100, channel_id="e46", contribution_change=-0.6, target_move=-0.7),
            ActivityRecord(day=1099, channel_id="e46", contribution_change=-0.9, target_move=-0.9),
            ActivityRecord(day=1100, channel_id="e47", contribution_change=0.6, target_move=0.5),
            ActivityRecord(day=1100, channel_id="e47:rev", contribution_change=0.3, target_move=0.5)]
    with eng.mutator.begin("log", at=eng.wm.clock) as txn:
        for r in recs:
            txn.add("wm.activity_log", r, key=activity_key(r.day, r.channel_id))
    active = eng.components["inducer"]._active_edges(1100, eng.wm, 28)
    assert set(active) == {"e46", "e47"}
    assert active["e46"].day == 1100 and active["e46"].contribution_change == -0.6
    assert active["e47"].channel_id == "e47" and active["e47"].contribution_change == 0.6


def test_dissolved_patterns_do_not_decay_and_unknown_absent_edges_are_ignored(warm_engine):
    eng = warm_engine
    pats = eng.ltm.object_generalizations.patterns
    with eng.mutator.begin("setup", at=eng.wm.clock) as txn:
        txn.update(PATTERNS, "S6", status=SuperentityStatus.DISSOLVED)
        txn.update(INSTANCES, "inst-S9", absent_interaction_ids=["e43", "no-such-edge"])
    s6, s7 = pats["S6"].support, pats["S7"].support
    res = _count(eng, 1060)
    assert pats["S6"].support == s6 and pats["S7"].support < s7
    assert "S9" not in res.supported_pattern_ids


def test_a_pattern_with_no_present_relation_matches_nothing(warm_engine):
    eng = warm_engine
    pats = eng.ltm.object_generalizations.patterns
    rels = [r.model_copy(update={"present": False}) for r in pats["S12"].relations]
    with eng.mutator.begin("setup", at=eng.wm.clock) as txn:
        txn.update(PATTERNS, "S12", relations=rels)
    res = _count(eng, 1100, _records(1100))
    assert "S12" not in res.supported_pattern_ids
    assert len(res.candidate_pattern_ids) == 1


def test_during_initialization_a_learned_pattern_is_not_matched(warm_engine):
    eng = warm_engine
    pats = eng.ltm.object_generalizations.patterns
    cand = _count(eng, 1100, _records(1100)).candidate_pattern_ids[0]
    assert pats[cand].origin == Origin.INFERENCE
    eng.initializing = True
    try:
        res = _count(eng, 1120, _records(1120))
    finally:
        eng.initializing = False
    assert cand not in res.supported_pattern_ids and not res.candidate_pattern_ids
    assert pats[cand].last_counted_day == 1100


def test_a_candidate_reuses_a_palette_that_already_exists(warm_engine):
    eng = warm_engine
    og = eng.ltm.object_generalizations
    mine = {"fill": "#123456", "line": "#654321"}
    with eng.mutator.begin("setup", at=eng.wm.clock) as txn:
        txn.set("ltm.object_generalizations.palettes", {**og.palettes, "x1": mine})
    cand = _count(eng, 1100, _records(1100)).candidate_pattern_ids[0]
    assert og.patterns[cand].palette == "x1" and og.palettes["x1"] == mine
    assert og.patterns[cand].name.endswith("more relations")


def test_patterns_on_the_same_members_that_disagree_become_rivals(warm_engine):
    eng = warm_engine
    pats = eng.ltm.object_generalizations.patterns
    s6 = pats["S6"]
    flipped = [s6.relations[0].model_copy(update={"polarity": -s6.relations[0].polarity})] + list(s6.relations[1:])
    bindings = dict(eng.wm.graph.instances["inst-S6"].bindings)
    with eng.mutator.begin("setup", at=eng.wm.clock) as txn:
        for pid in ("S6b", "S6c"):
            txn.add(PATTERNS, s6.model_copy(update={"id": pid, "relations": flipped, "origin": Origin.INFERENCE,
                                                    "rival_ids": set()}))
        txn.add(INSTANCES, SuperentityInstance(id="inst-S6b", pattern_id="S6b", bindings=bindings,
                                               interaction_ids=list(eng.wm.graph.instances["inst-S6"].interaction_ids)))
        # a binding made for a hypothetical is transient: it says nothing about rivals
        txn.add(INSTANCES, SuperentityInstance(id="inst-S6c", pattern_id="S6c", bindings=bindings,
                                               interaction_ids=[], transient=True))
    _count(eng, 1060)
    assert "S6b" in pats["S6"].rival_ids and "S6" in pats["S6b"].rival_ids
    assert "S6c" not in pats["S6"].rival_ids and not pats["S6c"].rival_ids
