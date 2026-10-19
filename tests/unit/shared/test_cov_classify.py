"""Classification on the warm economy: incorporation, re-listing, the thesis overlay, inherited
interaction priors, and taxonomy growth."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from axelrod_wm.engine.context import GraphOverlay
from axelrod_wm.engine.interfaces import Classification
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.model.entity import Entity
from axelrod_wm.model.taxonomy import Generalization, TaxonomyKind
from axelrod_wm.shared.classify import (
    NoGrower,
    SplitOnSharedFeatureGrower,
    TaxonomyDescentClassifier,
    item_features,
)
from tests.conftest import real_event

AT = datetime(2023, 1, 1, 23, 59, 59, tzinfo=timezone.utc)
RATE, FUND = "interest_rates.us_policy_rate", "credit_availability.us_bank_funding_cost"


def conc(sid):
    return {"kind": "concrete", "subentity_id": sid}


def test_item_features_of_a_missing_item_is_empty(warm_engine):
    eng = warm_engine
    assert item_features(TaxonomyKind.OBJECT, "nope", eng.wm.graph, eng.ltm) == {}
    assert item_features(TaxonomyKind.INTERACTION, "nope", eng.wm.graph, eng.ltm) == {}
    assert item_features(TaxonomyKind.OBJECT, "S1", eng.wm.graph, eng.ltm)["object_type"] == ["superentity"]


def test_incorporate_guards_and_relisting(warm_engine):
    eng = warm_engine
    clf = TaxonomyDescentClassifier(taxonomy_grower=NoGrower())
    ctx = eng.context(learn=True, now=AT)
    tax = eng.ltm.object_generalizations.taxonomy
    with eng.mutator.begin("inc", at=AT) as txn:
        assert clf.incorporate(Classification(item_id="ecb", taxonomy=TaxonomyKind.OBJECT, path=[],
                                              prior_source_id="gen:obj:root"), ctx, txn) == []
        assert clf.incorporate(Classification(item_id="ecb", taxonomy=TaxonomyKind.OBJECT, path=["gen:obj:ghost"],
                                              prior_source_id="gen:obj:root"), ctx, txn) == []
        c = Classification(item_id="ecb", taxonomy=TaxonomyKind.OBJECT, path=["gen:obj:root", "gen:obj:currency_board"],
                           prior_source_id="gen:obj:root", is_new=True)
        assert clf.incorporate(c, ctx, txn) == []
    assert "ecb" not in tax.nodes["gen:obj:central_bank"].instance_ids
    assert tax.nodes["gen:obj:currency_board"].instance_ids == ["ecb"]
    assert NoGrower(config=None).maybe_split(tax, "gen:obj:root", ctx, None) == []


def _thesis(eng, ops):
    ev = GraphUpdateEvent.model_validate({"id": "GUE-H", "kind": "hypothetical", "occurred_at": AT, "recorded_at": AT,
                                          "produced_by": "human", "ops": ops})
    ctx = eng.context(learn=False, now=AT)
    ctx.overlay = GraphOverlay(eng.wm, scope="T-1")
    parsed = eng.components["parser"].parse(ev, ctx.wm, eng.ltm, ctx, None)
    return parsed, ctx


def test_thesis_items_classify_into_the_overlay(warm_engine):
    eng = warm_engine
    ops = [{"op": "add_entity", "temp_id": "new:rbi", "name": "RBI", "kind": "agency",
            "features": {"function": "monetary_policy"}},
           {"op": "add_subentity", "entity": "new:rbi", "temp_id": "new:rbi.rate", "name": "Repo", "attribute_kind":
            "policy_rate", "unit": "pct"},
           {"op": "add_interaction", "source": conc("new:rbi.rate"), "target": conc(FUND), "label": "lifts",
            "polarity": -1, "direction": "bidirectional"}]
    parsed, ctx = _thesis(eng, ops)
    clf = eng.components["classifier"]
    c = clf.classify(TaxonomyKind.OBJECT, "rbi", True, ctx, None)
    ov = ctx.overlay.graph
    assert ov.entities["rbi"].generalization_id == c.path[-1] and "rbi" not in eng.wm.graph.entities
    sub = ov.subentities["rbi.rate"]
    assert sub.prior_source_id is not None and sub.anchor == sub.posterior.link_moments()[0]
    iid = parsed.new_interaction_ids[0]
    ci = clf.classify(TaxonomyKind.INTERACTION, iid, True, ctx, None)
    inter = ov.interactions[iid]
    assert inter.generalization_id == ci.path[-1] and inter.prior_source_id == ci.prior_source_id
    assert inter.forward.effect.mean() <= -0.1 and inter.reverse == inter.forward    # the op's sign, both ways


def test_thesis_classification_of_a_pattern_without_a_transaction(warm_engine):
    eng = warm_engine
    ctx = eng.context(learn=False, now=AT)
    ctx.overlay = GraphOverlay(eng.wm, scope="T-2")
    before = eng.ltm.object_generalizations.patterns["S1"].generalization_id
    c = eng.components["classifier"].classify(TaxonomyKind.OBJECT, "S1", True, ctx, None)
    assert c.path and eng.ltm.object_generalizations.patterns["S1"].generalization_id == before
    ctx_plain = eng.context(learn=False, now=AT)                   # no overlay and no transaction: nothing written
    c2 = eng.components["classifier"].classify(TaxonomyKind.OBJECT, "ecb", True, ctx_plain, None)
    assert c2.path[-1] == eng.wm.graph.entities["ecb"].generalization_id


def test_dry_run_classification_fills_nothing(warm_engine):
    eng = warm_engine
    ctx = eng.context(learn=False, now=AT)                          # no overlay and no transaction
    sid = eng.wm.graph.entities["ecb"].subentity_ids[0]
    ctx.notes["new_subentities"] = {sid: []}
    sub_before = eng.wm.graph.subentities[sid]
    int_before = eng.wm.graph.interactions["e01"]
    clf = eng.components["classifier"]
    clf.classify(TaxonomyKind.OBJECT, "ecb", True, ctx, None)
    ci = clf.classify(TaxonomyKind.INTERACTION, "e01", True, ctx, None)
    assert sid in ctx.notes["filled_subentities"] and ci.prior_source_id
    assert eng.wm.graph.subentities[sid] is sub_before and eng.wm.graph.interactions["e01"] is int_before


def test_new_interaction_without_a_declared_polarity_keeps_the_inherited_effect(warm_engine):
    eng = warm_engine
    ev = real_event([{"op": "add_interaction", "source": conc(RATE), "target": conc(FUND), "label": "moves",
                      "polarity": 1}], at=AT)
    ctx = eng.context(learn=True, now=AT)
    with eng.mutator.begin("p", at=AT) as txn:
        parsed = eng.components["parser"].parse(ev, eng.wm, eng.ltm, ctx, txn)
        iid = parsed.new_interaction_ids[0]
        ctx.notes["polarity"] = {}
        c = eng.components["classifier"].classify(TaxonomyKind.INTERACTION, iid, True, ctx, txn)
    node = eng.ltm.interaction_generalizations.taxonomy.nodes[c.prior_source_id]
    dyn, _ = node.prior_dynamics()
    assert eng.wm.graph.interactions[iid].forward.effect.mean() == pytest.approx(dyn.effect.mean())


def _agencies(eng, regions):
    with eng.mutator.begin("seed", at=AT) as txn:
        ids = []
        for k, region in enumerate(regions):
            eid = f"board{k}"
            ids.append(eid)
            txn.add("entities", Entity(id=eid, name=f"Board {k}", kind="agency", category_tags=set(),
                                       features={"region": region}, origin="human", created_at=AT,
                                       generalization_id="gen:obj:currency_board"))
        txn.update("generalizations.object", "gen:obj:currency_board", instance_ids=ids)
        # a node elsewhere already holds the first child's natural id
        txn.add("generalizations.object", Generalization(id="gen:obj:currency_board__region_eu",
                                                         kind=TaxonomyKind.OBJECT, name="taken", parent_id=None))
    return ids


def test_first_split_of_a_leaf_creates_two_children_with_fresh_ids(warm_engine):
    eng = warm_engine
    _agencies(eng, ["EU"] * 4 + ["US"] * 4 + ["JP"])
    tax = eng.ltm.object_generalizations.taxonomy
    ctx = eng.context(learn=True, now=AT)
    with eng.mutator.begin("grow", at=AT) as txn:
        created = SplitOnSharedFeatureGrower().maybe_split(tax, "gen:obj:currency_board", ctx, txn)
    assert created == ["gen:obj:currency_board__region_eu_2", "gen:obj:currency_board__region_us"]
    assert tax.nodes["gen:obj:currency_board"].child_ids == created
    assert tax.nodes["gen:obj:currency_board"].instance_ids == ["board8"]
    assert eng.wm.graph.entities["board0"].generalization_id == created[0]
    assert eng.wm.graph.entities["board5"].generalization_id == created[1]


def test_first_split_waits_for_a_second_group(warm_engine):
    eng = warm_engine
    _agencies(eng, ["EU"] * 4 + ["US"] * 2 + ["JP"] * 2)
    tax = eng.ltm.object_generalizations.taxonomy
    with eng.mutator.begin("grow", at=AT) as txn:
        assert SplitOnSharedFeatureGrower().maybe_split(tax, "gen:obj:currency_board",
                                                        eng.context(learn=True, now=AT), txn) == []
