"""Admissions and dissolutions after review (§7.6, §8.8) at their edges: a re-admission picks up its
configuration node's track record, a binding that fails leaves no instance, a part takes its composites
with it, and an unknown pattern is a no-op."""

from __future__ import annotations

import pytest

from axelrod_wm.engine.interfaces import Classification
from axelrod_wm.events.graph_update import ProposeSuperentity
from axelrod_wm.model.superentity import SuperentityStatus
from tests.conftest import real_event

NODES = "ltm.object_generalizations.taxonomy.nodes"


def _admit(eng, pattern, bindings, eid):
    op = ProposeSuperentity(pattern=pattern, bindings=bindings).model_dump(mode="json")
    return eng.structural.apply(real_event([op], eid, produced_by="engine"), eng.wm.clock, "superentity_admission")


def test_a_readmitted_pattern_starts_from_its_nodes_track_record(warm_engine):
    eng = warm_engine
    og = eng.ltm.object_generalizations
    p = og.patterns["S6"]
    assert p.track_record.hits + p.track_record.misses == 0
    with eng.mutator.begin("track", at=eng.wm.clock) as txn:
        for gid in og.taxonomy.path_from_root(p.generalization_id):
            st = og.taxonomy.nodes[gid].stats.model_copy(update={"track_hits": 3.0, "track_misses": 1.0})
            txn.update(NODES, gid, stats=st)
    cls = _admit(eng, p, dict(eng.wm.graph.instances["inst-S6"].bindings), "GUE-RE-S6")
    assert cls[0].item_id == "S6"
    rec = og.patterns["S6"].track_record
    assert (rec.hits, rec.misses) == pytest.approx((2.0 * 4.0 / 6.0, 2.0 * 2.0 / 6.0))   # (3 + 1) / (4 + 2), two pseudo-trials


def test_a_prior_source_outside_the_taxonomy_leaves_the_track_record(warm_engine):
    eng = warm_engine
    og = eng.ltm.object_generalizations
    real = eng.components["classifier"]

    class Elsewhere:
        def classify(self, kind, item_id, is_new, ctx, txn, **kw):
            c = real.classify(kind, item_id, is_new, ctx, txn, **kw)
            return c.model_copy(update={"prior_source_id": "gen:obj:elsewhere"})

    p = og.patterns["S6"]
    with eng.mutator.begin("track", at=eng.wm.clock) as txn:
        for gid in og.taxonomy.path_from_root(p.generalization_id):
            st = og.taxonomy.nodes[gid].stats.model_copy(update={"track_hits": 3.0})
            txn.update(NODES, gid, stats=st)
    eng.components["classifier"] = Elsewhere()
    try:
        cls = _admit(eng, p, dict(eng.wm.graph.instances["inst-S6"].bindings), "GUE-RE-S6B")
    finally:
        eng.components["classifier"] = real
    assert isinstance(cls[0], Classification) and cls[0].prior_source_id == "gen:obj:elsewhere"
    assert og.patterns["S6"].status == SuperentityStatus.ADMITTED
    assert og.patterns["S6"].track_record.hits == 0.0


def test_an_admission_whose_binding_fails_has_no_instance(warm_engine):
    eng = warm_engine
    og = eng.ltm.object_generalizations
    p = og.patterns["S6"].model_copy(update={"id": "PX", "status": SuperentityStatus.CANDIDATE,
                                             "generalization_id": None})

    class NoBinding:
        def bind(self, pattern, entities, graph, ltm):
            assert pattern.id == "PX" and entities == ["inflation"]
            return None

    real = eng.components["binder"]
    eng.components["binder"] = NoBinding()
    try:
        _admit(eng, p, {"r": "inflation"}, "GUE-PX")
    finally:
        eng.components["binder"] = real
    assert og.patterns["PX"].status == SuperentityStatus.ADMITTED
    assert not any(i.pattern_id == "PX" for i in eng.wm.graph.instances.values())


def test_dissolving_a_part_dissolves_its_composite(warm_engine):
    eng = warm_engine
    og = eng.ltm.object_generalizations
    assert "S1" in og.patterns["S10"].sub_pattern_ids
    eng.structural.apply(real_event([{"op": "dissolve_superentity", "pattern_id": "S1", "reason": "x"}], "GUE-D1",
                                    produced_by="engine"), eng.wm.clock)
    assert og.patterns["S1"].status == SuperentityStatus.DISSOLVED
    assert og.patterns["S10"].status == SuperentityStatus.DISSOLVED
    assert og.patterns["S2"].status == SuperentityStatus.ADMITTED
    assert not any(i.pattern_id in ("S1", "S10") for i in eng.wm.graph.instances.values())
    assert "inst-S2" in eng.wm.graph.instances


def test_dissolving_an_unknown_pattern_changes_nothing(warm_engine):
    eng = warm_engine
    og = eng.ltm.object_generalizations
    before = {pid: p.status for pid, p in og.patterns.items()}
    insts = set(eng.wm.graph.instances)
    eng.structural.apply(real_event([{"op": "dissolve_superentity", "pattern_id": "NOPE", "reason": "x"}], "GUE-D0",
                                    produced_by="engine"), eng.wm.clock)
    assert {pid: p.status for pid, p in og.patterns.items()} == before
    assert set(eng.wm.graph.instances) == insts
