"""The path update (§8.6.2) at its edges: no learning, unknown nodes and items, missing values, and the
pattern update's two modes (counted support, track record only)."""

from __future__ import annotations

from types import SimpleNamespace

from axelrod_wm.engine.interfaces import Classification
from axelrod_wm.learning.generalize import GeneralizationUpdater, pattern_relation_effects
from axelrod_wm.model.taxonomy import TaxonomyKind
from tests.conftest import START


def _node_stats(eng, gid, kind=TaxonomyKind.OBJECT):
    return eng.ltm.taxonomy(kind).nodes[gid].stats


def test_the_abstract_update_does_nothing(warm_engine):
    class Passthrough(GeneralizationUpdater):
        def update(self, classifications, ltm, ctx, txn):
            return super().update(classifications, ltm, ctx, txn)

    eng = warm_engine
    ctx = eng.context(learn=True, now=START)
    with eng.mutator.begin("abstract", at=START) as txn:
        assert Passthrough().update([], eng.ltm, ctx, txn) is None


def test_no_learning_leaves_the_statistics_alone(warm_engine):
    eng = warm_engine
    ent = eng.wm.graph.entities["inflation"]
    path = eng.ltm.object_generalizations.taxonomy.path_from_root(ent.generalization_id)
    before = {g: _node_stats(eng, g).support for g in path}
    ctx = eng.context(learn=False, now=START)
    with eng.mutator.begin("predict-only", at=START) as txn:
        eng.components["generalization_updater"].update(
            [Classification(item_id="inflation", taxonomy=TaxonomyKind.OBJECT, path=path, prior_source_id=path[0])],
            eng.ltm, ctx, txn)
    assert {g: _node_stats(eng, g).support for g in path} == before


def test_unknown_nodes_and_missing_values_are_skipped(warm_engine):
    eng = warm_engine
    g = eng.wm.graph
    ent = g.entities["inflation"]
    sids = list(ent.subentity_ids)
    path = eng.ltm.object_generalizations.taxonomy.path_from_root(ent.generalization_id)
    leaf = path[-1]
    st0 = _node_stats(eng, leaf)
    kinds = {g.subentities[s].attribute_kind for s in sids}
    counts0 = {k: st0.attribute_level[k].n if k in st0.attribute_level else 0 for k in kinds}
    with eng.mutator.begin("ghost", at=START) as txn:
        txn.update("wm.graph.entities", "inflation", subentity_ids=sids + ["inflation.ghost"])
    ctx = eng.context(learn=True, now=START)
    with eng.mutator.begin("upd", at=START) as txn:
        eng.components["generalization_updater"].update(
            [Classification(item_id="inflation", taxonomy=TaxonomyKind.OBJECT, path=path + ["gen:obj:nowhere"],
                            prior_source_id=path[0])], eng.ltm, ctx, txn)
    st = _node_stats(eng, leaf)
    assert st.support == st0.support + 1.0
    assert "gen:obj:nowhere" not in eng.ltm.object_generalizations.taxonomy.nodes
    # every real value pushed one level; the ghost value pushed nothing
    for k in kinds:
        n_real = sum(1 for s in sids if g.subentities[s].attribute_kind == k)
        assert st.attribute_level[k].n == counts0[k] + n_real


def test_an_interaction_classification_for_an_unknown_item_adds_support_only(warm_engine):
    eng = warm_engine
    itax = eng.ltm.interaction_generalizations.taxonomy
    gid = eng.wm.graph.interactions["e01"].generalization_id
    path = itax.path_from_root(gid)
    st0 = _node_stats(eng, gid, TaxonomyKind.INTERACTION)
    ctx = eng.context(learn=True, now=START)
    with eng.mutator.begin("upd", at=START) as txn:
        eng.components["generalization_updater"].update(
            [Classification(item_id="no-such-edge", taxonomy=TaxonomyKind.INTERACTION, path=path,
                            prior_source_id=path[0])], eng.ltm, ctx, txn)
    st = _node_stats(eng, gid, TaxonomyKind.INTERACTION)
    assert st.support == st0.support + 1.0 and st.effect.n == st0.effect.n


def test_relation_effects_skip_missing_retired_and_dangling_interactions():
    def inter(src, tgt, retired=None, mean=0.5, pol=1):
        return SimpleNamespace(source_id=src, target_id=tgt, retired_at=retired, polarity=lambda: pol,
                               forward=SimpleNamespace(effect=SimpleNamespace(mean=lambda: mean)))

    subs = {"a.x": SimpleNamespace(attribute_kind="price"), "b.y": SimpleNamespace(attribute_kind="output")}
    graph = SimpleNamespace(
        instances={"i1": SimpleNamespace(pattern_id="P", transient=False,
                                         interaction_ids=["ok", "gone", "retired", "dangling"]),
                   "i2": SimpleNamespace(pattern_id="P", transient=True, interaction_ids=["ok"]),
                   "i3": SimpleNamespace(pattern_id="Q", transient=False, interaction_ids=["ok"])},
        interactions={"ok": inter("a.x", "b.y", mean=0.7, pol=-1), "retired": inter("a.x", "b.y", retired=START),
                      "dangling": inter("a.x", "c.z")},
        subentities=subs)
    out = pattern_relation_effects("P", SimpleNamespace(graph=graph))
    assert len(out) == 1 and out[0][1] == 0.7


def test_update_pattern_ignores_unknown_patterns_and_no_classifications_write_nothing(warm_engine):
    eng = warm_engine
    v = eng.version
    ctx = eng.context(learn=True, now=START)
    with eng.mutator.begin("upd", at=START) as txn:
        eng.components["generalization_updater"].update_pattern("NOPE", eng.ltm, ctx, txn)
        eng.components["generalization_updater"].update([], eng.ltm, ctx, txn)
    assert eng.version == v      # nothing to commit


def test_a_pattern_classification_pools_its_relation_effects(warm_engine):
    eng = warm_engine
    og = eng.ltm.object_generalizations
    path = og.taxonomy.path_from_root(og.patterns["S6"].generalization_id)
    effects = pattern_relation_effects("S6", eng.wm)
    assert effects
    leaf = path[-1]
    n0 = {k: v.n for k, v in _node_stats(eng, leaf).relation_effects.items()}
    ctx = eng.context(learn=True, now=START)
    with eng.mutator.begin("upd", at=START) as txn:
        eng.components["generalization_updater"].update(
            [Classification(item_id="S6", taxonomy=TaxonomyKind.OBJECT, path=path, prior_source_id=path[0])],
            eng.ltm, ctx, txn)
        eng.components["generalization_updater"].update_pattern("S6", eng.ltm, ctx, txn)
    st = _node_stats(eng, leaf)
    for rkey in {k for k, _ in effects}:
        pushed = sum(1 for k, _ in effects if k == rkey)
        assert st.relation_effects[rkey].n == n0.get(rkey, 0) + 2 * pushed


def test_a_track_record_change_does_not_add_support(warm_engine):
    eng = warm_engine
    tax = eng.ltm.object_generalizations.taxonomy
    path = tax.path_from_root(eng.ltm.object_generalizations.patterns["S6"].generalization_id)
    before = {g: (_node_stats(eng, g).support, _node_stats(eng, g).track_hits, _node_stats(eng, g).track_misses)
              for g in path}
    ctx = eng.context(learn=True, now=START)
    with eng.mutator.begin("upd", at=START) as txn:
        eng.components["generalization_updater"].update_pattern("S6", eng.ltm, ctx, txn, count_support=False,
                                                                hits=2.0, misses=1.0)
    for g in path:
        s, h, m = before[g]
        st = _node_stats(eng, g)
        assert (st.support, st.track_hits, st.track_misses) == (s, h + 2.0, m + 1.0)
