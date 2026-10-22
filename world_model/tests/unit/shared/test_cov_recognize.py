"""Recognition on a hand-built chain a -> b -> c -> d: role filling over several passes, coverage,
dissolution on a routine event, a thesis's transient instance, and the missing-relation proposal."""

from __future__ import annotations

from datetime import timedelta

import pytest

from axelrod_wm.engine.context import GraphOverlay
from axelrod_wm.engine.interfaces import RecallResult, ScoredSuperentity
from axelrod_wm.events.graph_update import EventKind
from axelrod_wm.model.distributions import Gaussian
from axelrod_wm.model.graph import CausalGraph
from axelrod_wm.model.superentity import (
    PatternRelation,
    RoleSpec,
    SuperentityInstance,
    SuperentityPattern,
    SuperentityStatus,
)
from axelrod_wm.model.taxonomy import (
    AttributeVocabulary,
    Generalization,
    GeneralizationStats,
    RunningStats,
    Taxonomy,
    TaxonomyKind,
)
from axelrod_wm.shared.process import ParsedEvent
from axelrod_wm.shared.recognize import (
    BfsRoleFillingBinder,
    PatternBinder,
    PatternRecognizer,
    _subs_of_kind,
    entity_path,
)
from tests.unit.dynamics.kit import NOW, tiny_engine
from tests.unit.model.graphkit import T0, entity, inter, sub

VOCAB = AttributeVocabulary(kinds={})


def chain_graph(missing_ac=True) -> CausalGraph:
    ents = {e: entity(e, subs=[f"{e}.k"], generalization_id="g:obj") for e in "abcd"}
    subs = {f"{e}.k": sub(f"{e}.k", "k") for e in "abcd"}
    ints = {"i-ab": inter("i-ab", "a.k", "b.k", 0.5), "i-bc": inter("i-bc", "b.k", "c.k", 0.5),
            "i-cd": inter("i-cd", "c.k", "d.k", 0.5), "i-neg": inter("i-neg", "a.k", "d.k", -0.5)}
    if not missing_ac:
        ints["i-ac"] = inter("i-ac", "a.k", "c.k", 0.5)
    return CausalGraph(entities=ents, subentities=subs, interactions=ints)


def rel(s, t, gid=None, present=True, polarity=1):
    return PatternRelation(source_role=s, source_attr="k", target_role=t, target_attr="k", polarity=polarity,
                           label=f"{s} lifts {t}", interaction_generalization_id=gid, present=present)


def pattern(relations, roles="ABCD", pid="pat-1", gen=None, **kw):
    return SuperentityPattern(id=pid, name="chain", roles=[RoleSpec(name=r, generalization_id="g:obj") for r in roles],
                              relations=relations, created_at=T0, status=SuperentityStatus.ADMITTED,
                              generalization_id=gen, **kw)


def engine_with_taxonomies(graph=None, patterns=(), support=10.0, **config):
    eng = tiny_engine(graph if graph is not None else chain_graph(), **config)
    eng.vocab = VOCAB
    og = eng.ltm.object_generalizations
    og.taxonomy = Taxonomy(kind=TaxonomyKind.OBJECT, root_id="g:obj", nodes={
        "g:obj": Generalization(id="g:obj", kind=TaxonomyKind.OBJECT, name="obj", parent_id=None,
                                stats=GeneralizationStats(support=support)),
        "g:cfg": Generalization(id="g:cfg", kind=TaxonomyKind.OBJECT, name="cfg", parent_id=None,
                                stats=GeneralizationStats(relation_effects={"k>k:1": RunningStats(n=3, mean=0.7)}))})
    eng.ltm.interaction_generalizations.taxonomy = Taxonomy(kind=TaxonomyKind.INTERACTION, root_id="g:int", nodes={
        "g:int": Generalization(id="g:int", kind=TaxonomyKind.INTERACTION, name="int", parent_id=None,
                                stats=GeneralizationStats(support=support, effect=RunningStats(n=2, mean=0.03))),
        "g:weak": Generalization(id="g:weak", kind=TaxonomyKind.INTERACTION, name="weak", parent_id=None,
                                 stats=GeneralizationStats(support=0.0))})
    for p in patterns:
        og.patterns[p.id] = p
    return eng


def parsed(touched, event_type=None, move=2.0):
    return ParsedEvent(event_id="GUE-1", kind=EventKind.REAL, event_type=event_type, day=20, processing_day=20,
                       shocks=[], observations=[], touched_subentity_ids=[], touched_entity_ids=touched,
                       new_entity_ids=[], new_interaction_ids=[], touched_interaction_ids=[], max_abs_move=move)


def recall_of(*pids):
    return RecallResult(superentities=[ScoredSuperentity(pattern_id=p, instance_id=None, score=1.0, attention=1.0)
                                       for p in pids], analogs=[])


# ----- helpers ----------------------------------------------------------------------------------

def test_entity_path_and_subs_of_kind():
    eng = tiny_engine(chain_graph())
    assert entity_path("a", eng.wm.graph, eng.ltm) == []                 # no taxonomy at all
    eng2 = engine_with_taxonomies()
    assert entity_path("a", eng2.wm.graph, eng2.ltm) == ["g:obj"]
    assert entity_path("ghost", eng2.wm.graph, eng2.ltm) == ["g:obj"]
    assert _subs_of_kind("ghost", "k", eng2.wm.graph, VOCAB) == []
    assert _subs_of_kind("a", "k", eng2.wm.graph, VOCAB) == ["a.k"]
    assert PatternBinder.bind(BfsRoleFillingBinder(vocab=VOCAB), None, [], None, None) is None


# ----- binding ----------------------------------------------------------------------------------

def test_role_filling_takes_several_passes():
    # listed against the chain's order, each pass can bind only one more role
    p = pattern([rel("C", "D"), rel("B", "C"), rel("A", "B")])
    eng = engine_with_taxonomies(patterns=[p])
    b = BfsRoleFillingBinder(vocab=VOCAB).bind(p, ["a", "ghost"], eng.wm.graph, eng.ltm)
    assert b.bindings == {"A": "a", "B": "b", "C": "c", "D": "d"}
    assert b.coverage == 1.0 and b.interaction_ids == ["i-cd", "i-bc", "i-ab"] and b.missing_relations == []
    assert b.significance == pytest.approx(3 * eng.wm.graph.interactions["i-ab"].significance_mean())


def test_absent_relations_and_low_coverage():
    p = pattern([rel("A", "B"), rel("A", "D", present=False, polarity=1)], roles="ABD")
    eng = engine_with_taxonomies(patterns=[p])
    binder = BfsRoleFillingBinder(eng.config, engine=eng)
    assert binder.min_cov == 0.6 and binder.vocab is VOCAB
    b = binder.evaluate(p, {"A": "a", "B": "b", "D": "d"}, eng.wm.graph, eng.ltm)
    assert b.absent_interaction_ids == ["i-neg"] and b.coverage == 1.0
    lonely = pattern([rel("A", "B"), rel("B", "C"), rel("C", "D")])
    assert BfsRoleFillingBinder(vocab=VOCAB, min_binding_coverage=0.9).bind(lonely, ["d"], eng.wm.graph, eng.ltm) \
        .bindings["A"] == "a"
    assert BfsRoleFillingBinder(vocab=VOCAB, min_binding_coverage=1.0).bind(
        pattern([rel("A", "B"), rel("B", "C", gid="g:int", polarity=-1)], roles="ABC"), ["a"], eng.wm.graph,
        eng.ltm) is None


# ----- the recognizer ---------------------------------------------------------------------------

def test_routine_event_dissolves_stale_instances_and_binds_nothing():
    p = pattern([rel("A", "B"), rel("B", "C"), rel("C", "D")])
    g = chain_graph()
    g.instances["inst-old"] = SuperentityInstance(id="inst-old", pattern_id="pat-gone", bindings={"A": "a"},
                                                  interaction_ids=["i-ab"])
    g.instances["inst-ok"] = SuperentityInstance(id="inst-ok", pattern_id="pat-1", bindings={"A": "a"},
                                                 interaction_ids=["i-ab"])
    eng = engine_with_taxonomies(g, patterns=[p])
    rec = PatternRecognizer(BfsRoleFillingBinder(vocab=VOCAB), engine=eng)
    ctx = eng.context(learn=True, now=NOW)
    with eng.mutator.begin("bind", at=NOW) as txn:
        res = rec.bind(parsed(["a"], event_type="data_release", move=0.2), recall_of("pat-1"), eng.wm, eng.ltm,
                       ctx, txn)
    assert res.dissolved_instance_ids == ["inst-old"] and res.bound_instance_ids == []
    assert sorted(eng.wm.graph.instances) == ["inst-ok"]
    with eng.mutator.begin("bind2", at=NOW) as txn:      # routine, nothing to dissolve
        res = rec.bind(parsed(["a"], event_type="data_release", move=0.2), recall_of(), eng.wm, eng.ltm, ctx, txn)
    assert res.dissolved_instance_ids == []


def test_initializing_binds_nothing():
    eng = engine_with_taxonomies()
    ctx = eng.context(learn=True, now=NOW)
    ctx.initializing = True
    assert PatternRecognizer(BfsRoleFillingBinder(vocab=VOCAB)).bind(parsed(["a"]), recall_of(), eng.wm, eng.ltm,
                                                                      ctx, None).bound_instance_ids == []


def test_thesis_binds_a_transient_instance():
    p = pattern([rel("A", "B"), rel("B", "C"), rel("C", "D")])
    eng = engine_with_taxonomies(patterns=[p])
    ctx = eng.context(learn=False, now=NOW)
    ctx.overlay = GraphOverlay(eng.wm, scope="T-1")
    rec = PatternRecognizer(BfsRoleFillingBinder(vocab=VOCAB), engine=eng)
    res = rec.bind(parsed(["a"]), recall_of("pat-1", "pat-missing"), ctx.wm, eng.ltm, ctx, None)
    assert res.bound_instance_ids == ["inst-T-1-1"]
    inst = ctx.overlay.graph.instances["inst-T-1-1"]
    assert inst.transient and inst.bindings == {"A": "a", "B": "b", "C": "c", "D": "d"}
    assert eng.wm.graph.instances == {} and rec.vocab is VOCAB


def test_missing_relations_become_proposals_with_a_cooldown():
    rels = [rel("A", "B"), rel("B", "C"), rel("A", "C", gid="g:int"), rel("C", "A", gid="g:weak"),
            rel("A", "C", gid=None, polarity=-1), rel("C", "A", gid="g:int", polarity=-1)]
    p = pattern(rels, roles="ABC", gen="g:cfg")
    plain = pattern([rel("A", "B"), rel("B", "C"), rel("C", "A", gid="g:int", polarity=1)], roles="ABC", pid="pat-2")
    eng = engine_with_taxonomies(patterns=[p, plain], abduction={"min_binding_coverage": 0.3})
    rec = PatternRecognizer(BfsRoleFillingBinder(eng.config, engine=eng), engine=eng)
    ctx = eng.context(learn=True, now=NOW)
    with eng.mutator.begin("bind", at=NOW) as txn:
        res = rec.bind(parsed(["a"]), recall_of("pat-1"), eng.wm, eng.ltm, ctx, txn)
    (iid,) = res.bound_instance_ids
    inst = eng.wm.graph.instances[iid]
    assert inst.bindings == {"A": "a", "B": "b", "C": "c"} and inst.interaction_ids == ["i-ab", "i-bc"]
    # only the relations with a well-supported broad kind propose (gid None and g:weak do not)
    kinds = [(pe["event"]["ops"][0]["source"]["subentity_id"], pe["event"]["ops"][0]["target"]["subentity_id"],
              pe["event"]["ops"][0]["polarity"]) for pe in res.proposal_events]
    assert kinds == [("a.k", "c.k", 1), ("c.k", "a.k", -1)]
    first = res.proposal_events[0]["event"]["ops"][0]
    assert first["dynamics"]["effect"]["mu"] == 0.7                     # the configuration's prior for k>k:1
    second = res.proposal_events[1]["event"]["ops"][0]
    assert second["dynamics"]["effect"]["mu"] == -0.1                   # polarity times at least 0.1
    assert sorted(eng.wm.missing_relation_log) == ["pat-1#2", "pat-1#5"]
    assert "(chain) predicts A lifts C" in res.proposal_events[0]["reason"]
    # a second bind inside the cooldown proposes nothing again
    with eng.mutator.begin("drop", at=NOW) as txn:
        txn.remove("wm.graph.instances", iid)
    ctx2 = eng.context(learn=True, now=NOW + timedelta(days=3))
    with eng.mutator.begin("bind2", at=NOW) as txn:
        res2 = rec.bind(parsed(["a"]), recall_of("pat-1"), eng.wm, eng.ltm, ctx2, txn)
    assert res2.bound_instance_ids and res2.proposal_events == []
    assert isinstance(Gaussian(mu=0, sigma=1), Gaussian)


def test_missing_relation_without_matching_subentities_is_skipped():
    g = chain_graph()
    g.subentities["c.k"] = g.subentities["c.k"].model_copy(update={"attribute_kind": "other"})
    g.interactions["i-bc"] = inter("i-bc", "b.k", "c.k", 0.5)
    p = SuperentityPattern(id="pat-1", name="p", created_at=T0, status=SuperentityStatus.ADMITTED,
                           roles=[RoleSpec(name=r, generalization_id="g:obj") for r in "ABC"],
                           relations=[rel("A", "B"),
                                      PatternRelation(source_role="B", source_attr="k", target_role="C",
                                                      target_attr="other", polarity=1, label="b to c"),
                                      rel("A", "C", gid="g:int")])
    eng = engine_with_taxonomies(g, patterns=[p])
    rec = PatternRecognizer(BfsRoleFillingBinder(vocab=VOCAB), engine=eng)
    with eng.mutator.begin("bind", at=NOW) as txn:
        res = rec.bind(parsed(["a"]), recall_of("pat-1"), eng.wm, eng.ltm, eng.context(learn=True, now=NOW), txn)
    assert res.bound_instance_ids and res.proposal_events == []          # C has no subentity of kind k
