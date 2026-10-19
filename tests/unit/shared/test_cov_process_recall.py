"""The shared process's helpers and recall's pattern helpers, on the warm economy."""

from __future__ import annotations

from datetime import datetime, timezone

from axelrod_wm.engine.interfaces import Classification
from axelrod_wm.model.superentity import PatternRelation, RoleSpec, SuperentityPattern
from axelrod_wm.model.taxonomy import TaxonomyKind
from axelrod_wm.shared.process import build_new_channels, signature_of
from axelrod_wm.shared.recall import can_fill, pattern_signature

AT = datetime(2023, 1, 1, 23, 59, 59, tzinfo=timezone.utc)


def test_signature_of_without_a_parsed_event(warm_engine):
    eng = warm_engine
    ctx = eng.context(learn=True, now=AT)
    otax = eng.ltm.object_generalizations.taxonomy
    path = otax.path_from_root(eng.wm.graph.entities["federal_reserve"].generalization_id)
    c = Classification(item_id="federal_reserve", taxonomy=TaxonomyKind.OBJECT, path=path + ["gen:obj:ghost"],
                       prior_source_id=path[0])
    sig = signature_of([c], eng.ltm, ctx)
    assert sig and sig <= set(path) and not any(k.startswith(("etype:", "tag:")) for k in sig)
    assert all(otax.nodes[g].stats.support > ctx.recall_threshold for g in sig)


def test_build_new_channels_skips_missing_interactions(warm_engine):
    eng = warm_engine
    ctx = eng.context(learn=True, now=AT)
    eng.wm.channels.pop("e01")
    with eng.mutator.begin("ch", at=AT) as txn:
        build_new_channels(["ghost", "e01"], ctx, txn)
    assert "e01" in eng.wm.channels and "ghost" not in eng.wm.channels


def test_pattern_signature_and_can_fill(warm_engine):
    eng = warm_engine
    ltm = eng.ltm
    p = SuperentityPattern(id="p", name="p", created_at=AT,
                           roles=[RoleSpec(name="cb", generalization_id="gen:obj:central_bank"),
                                  RoleSpec(name="x", generalization_id="gen:obj:not_a_node")],
                           relations=[PatternRelation(source_role="cb", source_attr="a", target_role="x",
                                                      target_attr="b", polarity=1, label="l",
                                                      interaction_generalization_id="gen:int:ghost"),
                                      PatternRelation(source_role="cb", source_attr="a", target_role="x",
                                                      target_attr="b", polarity=1, label="l")])
    sig = pattern_signature(p, ltm)
    assert sig == set(ltm.object_generalizations.taxonomy.path_to_root("gen:obj:central_bank"))
    assert can_fill("gen:obj:central_bank", p, ltm)
    assert not can_fill(None, p, ltm) and not can_fill("gen:obj:ghost", p, ltm)
    assert not can_fill("gen:obj:airline", p, ltm)
