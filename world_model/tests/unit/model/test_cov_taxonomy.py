"""Taxonomy pieces on hand-built inputs: vocabulary, signatures, running stats, priors, trees, features."""

from __future__ import annotations

import math

import pytest

from axelrod_wm.model.distributions import Gaussian
from axelrod_wm.model.superentity import PatternRelation, RoleSpec, SuperentityPattern
from axelrod_wm.model.taxonomy import (
    DEFAULT_EFFECT_SD,
    AttributeKind,
    AttributeVocabulary,
    Generalization,
    GeneralizationStats,
    RunningStats,
    Signature,
    Taxonomy,
    TaxonomyKind,
    default_obs_noise,
    derive_signature,
    features_of,
    features_of_entity,
    features_of_interaction,
    features_of_pattern,
    label_family,
    relation_key,
)
from tests.unit.model.graphkit import T0, inter, small_graph

VOCAB = AttributeVocabulary(kinds={
    "rate": AttributeKind(name="rate", parent=None, family="gaussian"),
    "policy_rate": AttributeKind(name="policy_rate", parent="rate", family="gaussian"),
    "price": AttributeKind(name="price", parent=None, family="lognormal"),
    "oil_price": AttributeKind(name="oil_price", parent="price", family="lognormal"),
    "sentiment_index": AttributeKind(name="sentiment_index", parent=None, family="gaussian"),
    "orphan": AttributeKind(name="orphan", parent="missing_parent", family="beta"),
    "loop_a": AttributeKind(name="loop_a", parent="loop_b", family="gaussian"),
    "loop_b": AttributeKind(name="loop_b", parent="loop_a", family="gaussian"),
})


# ----- vocabulary -------------------------------------------------------------------------------

def test_ancestors_nearest_first_with_unknown_parent_and_cycles():
    assert VOCAB.ancestors("policy_rate") == ["policy_rate", "rate"]
    assert VOCAB.ancestors("orphan") == ["orphan", "missing_parent"]   # an unknown parent still listed
    assert VOCAB.ancestors("loop_a") == ["loop_a", "loop_b"]            # a cycle stops
    assert VOCAB.ancestors("unknown") == ["unknown"]


def test_is_a_distance_family_root():
    assert VOCAB.is_a("policy_rate", "rate") and not VOCAB.is_a("policy_rate", "price")
    assert VOCAB.is_a("unknown", "unknown") and not VOCAB.is_a("unknown", "rate")
    assert VOCAB.distance("policy_rate", "rate") == 1
    assert VOCAB.distance("policy_rate", "policy_rate") == 0
    assert VOCAB.distance("policy_rate", "oil_price") == 99
    assert VOCAB.family("oil_price") == "lognormal" and VOCAB.family("nope") == "gaussian"
    assert VOCAB.root_of("oil_price") == "price" and VOCAB.root_of("loop_a") == "loop_b"


def test_root_of_with_empty_ancestors():
    class NoAncestors(AttributeVocabulary):
        def ancestors(self, kind):
            return []

    assert NoAncestors(kinds={}).root_of("x") == "x"


# ----- signatures -------------------------------------------------------------------------------

def test_signature_match_and_known_only():
    sig = Signature(required={"kind": ["company"]}, any_of={"attribute_kinds": ["rate"]})
    feats = {"kind": ["company"], "attribute_kinds": ["policy_rate", "price"]}
    assert sig.match(feats, VOCAB) == 1.0                       # policy_rate is_a rate
    assert sig.match({"kind": ["agency"]}, VOCAB) == 0.0
    assert sig.match({"kind": ["company"]}, VOCAB) == 0.5       # any_of key missing
    assert sig.satisfied_by_known({"kind": ["company"]}, VOCAB)
    assert not sig.satisfied_by_known({"kind": ["agency"]}, VOCAB)
    assert not sig.satisfied_by_known({}, VOCAB)                # no known key
    empty = Signature()
    assert empty.is_empty() and empty.match(feats, VOCAB) == 0.0 and not empty.satisfied_by_known(feats, VOCAB)


def test_signature_required_all_values_and_no_vocab():
    sig = Signature(required={"source_attr": ["rate"]})
    assert sig.match({"source_attr": ["policy_rate"]}, VOCAB) == 1.0
    assert sig.match({"source_attr": ["policy_rate", "price"]}, VOCAB) == 0.0   # every value must hold
    assert sig.match({"source_attr": ["policy_rate"]}, None) == 0.0             # without a vocabulary: exact
    assert sig.match({"source_attr": ["rate"]}, None) == 1.0


def test_signature_any_of_only_keys_known_only_path():
    sig = Signature(any_of={"x": ["1"], "y": ["2"]})
    assert sig.satisfied_by_known({"x": ["1", "3"]}, VOCAB)
    assert not sig.satisfied_by_known({"x": ["3"]}, VOCAB)


# ----- running stats ----------------------------------------------------------------------------

def test_running_stats_welford_matches_numpy():
    xs = [1.0, 2.0, 4.0, 7.0]
    rs = RunningStats()
    for x in xs:
        rs.push(x)
    rs.push(float("nan"))
    rs.push(100.0, w=0.0)
    mean = sum(xs) / 4
    assert rs.n == 4 and rs.mean == pytest.approx(mean)
    assert rs.var() == pytest.approx(sum((x - mean) ** 2 for x in xs) / 4)
    assert RunningStats().var() == 0.0


def test_running_stats_weighted_push():
    rs = RunningStats()
    rs.push(0.0, w=1.0)
    rs.push(3.0, w=2.0)
    assert rs.mean == pytest.approx(2.0)
    assert rs.var() == pytest.approx((1 * 4 + 2 * 1) / 3)


def test_running_stats_merge_equals_pooled():
    a, b, both = RunningStats(), RunningStats(), RunningStats()
    for x in (1.0, 2.0, 3.0):
        a.push(x)
        both.push(x)
    for x in (10.0, 12.0):
        b.push(x)
        both.push(x)
    m = a.merged(b)
    assert m.n == both.n and m.mean == pytest.approx(both.mean) and m.var() == pytest.approx(both.var())
    assert a.merged(RunningStats()) == a and a.merged(RunningStats()) is not a
    assert RunningStats().merged(b) == b


def test_generalization_stats_merge():
    s1 = GeneralizationStats(support=2.0, existence_alpha=3.0, existence_beta=2.0, track_hits=1.0,
                             duration_permanent=1.0)
    s1.attribute_level["rate"] = RunningStats(n=1, mean=1.0)
    s2 = GeneralizationStats(support=1.0, existence_alpha=2.0, existence_beta=4.0, track_misses=2.0)
    s2.attribute_level["rate"] = RunningStats(n=1, mean=3.0)
    s2.relation_effects["a>b:1"] = RunningStats(n=2, mean=0.5)
    m = s1.merged(s2)
    assert m.support == 3.0 and m.existence_alpha == 4.0 and m.existence_beta == 5.0
    assert m.track_hits == 1.0 and m.track_misses == 2.0 and m.duration_permanent == 1.0
    assert m.attribute_level["rate"].n == 2 and m.attribute_level["rate"].mean == 2.0
    assert m.relation_effects["a>b:1"].mean == 0.5
    assert s1.attribute_level["rate"].n == 1          # inputs untouched


# ----- generalization priors --------------------------------------------------------------------

def _gen(**stats) -> Generalization:
    return Generalization(id="g", kind=TaxonomyKind.INTERACTION, name="g", parent_id=None,
                          stats=GeneralizationStats(**stats))


def test_prior_for_attribute():
    g = _gen()
    with pytest.raises(KeyError):
        g.prior_for_attribute("rate", "gaussian")
    g.stats.attribute_level["rate"] = RunningStats(n=2, mean=1.0, m2=2.0)        # var 1
    prior, scale = g.prior_for_attribute("rate", "gaussian")
    assert scale == 1.0 and prior.mean() == 1.0 and prior.var() == pytest.approx(2.0)
    g.stats.attribute_scale["rate"] = RunningStats(n=1, mean=0.5)
    prior, scale = g.prior_for_attribute("rate", "gaussian")
    assert scale == 0.5 and prior.var() == pytest.approx(1.25)


def test_prior_dynamics_defaults_and_learned():
    g = _gen()
    assert not g.has_dynamics()
    dyn, ex = g.prior_dynamics()
    assert dyn.effect.mean() == 0.0 and dyn.effect.sd() == pytest.approx(DEFAULT_EFFECT_SD)
    d, l, dur = dyn.kernel.means()
    assert (d, l) == pytest.approx((14.0, 30.0)) and dur is None      # 0 >= 0: permanent
    assert ex.alpha == 1.0 and ex.beta == 1.0

    g2 = _gen(effect=RunningStats(n=2, mean=0.6, m2=0.02), delay_days=RunningStats(n=1, mean=5.0),
              lag_days=RunningStats(n=1, mean=10.0), duration_days=RunningStats(n=3, mean=40.0),
              duration_permanent=1.0, existence_alpha=0.0, existence_beta=3.0)
    assert g2.has_dynamics()
    dyn, ex = g2.prior_dynamics()
    assert dyn.effect.mean() == 0.6 and dyn.effect.sd() == pytest.approx(math.sqrt(0.01 + DEFAULT_EFFECT_SD ** 2))
    assert dyn.kernel.means() == pytest.approx((5.0, 10.0, 40.0))
    assert ex.alpha == 1e-3 and ex.beta == 3.0


def test_prior_for_pattern():
    g = _gen()
    priors, rec = g.prior_for_pattern()
    assert priors == {} and rec.hits == 0.0 and rec.misses == 0.0
    g2 = _gen(track_hits=3.0, track_misses=1.0,
              relation_effects={"a>b:1": RunningStats(n=2, mean=0.4, m2=0.0), "c>d:-1": RunningStats()})
    priors, rec = g2.prior_for_pattern()
    assert list(priors) == ["a>b:1"] and priors["a>b:1"].mean() == 0.4
    rate = 4.0 / 6.0
    assert rec.hits == pytest.approx(2 * rate) and rec.misses == pytest.approx(2 * (1 - rate))


def test_relation_key():
    assert relation_key("rate", "price", 1) == "rate>price:1"
    assert relation_key("rate", "price", 0) == "rate>price:1"
    assert relation_key("rate", "price", -3) == "rate>price:-1"


# ----- taxonomy tree ----------------------------------------------------------------------------

def _tree() -> Taxonomy:
    def node(gid, parent, kids=(), support=0.0, inst=()):
        return Generalization(id=gid, kind=TaxonomyKind.OBJECT, name=gid, parent_id=parent, child_ids=list(kids),
                              stats=GeneralizationStats(support=support), instance_ids=list(inst))
    nodes = {"root": node("root", None, ["a", "b", "ghost"], 10, ["r1"]),
             "a": node("a", "root", ["a1"], 5, ["x1"]),
             "a1": node("a1", "a", [], 1, ["x2", "x3"]),
             "b": node("b", "root", [], 4, ["y1"])}
    return Taxonomy(kind=TaxonomyKind.OBJECT, root_id="root", nodes=nodes)


def test_taxonomy_navigation():
    t = _tree()
    assert [n.id for n in t.children("root")] == ["a", "b"]       # missing child skipped
    assert t.path_to_root("a1") == ["a1", "a", "root"]
    assert t.path_from_root("a1") == ["root", "a", "a1"]
    assert t.depth("a1") == 2 and t.depth("root") == 0
    assert t.is_under("a1", "a") and not t.is_under("b", "a")
    assert t.instances_under("root") == ["r1", "x1", "x2", "x3", "y1"]
    assert t.instances_under("nope") == []
    assert t.node_of_instance("x3") == "a1" and t.node_of_instance("zz") is None


def test_taxonomy_cyclic_parents_stop():
    t = _tree()
    t.nodes["root"].parent_id = "a1"
    assert t.path_to_root("a1") == ["a1", "a", "root"]
    t.nodes["a1"].child_ids = ["a"]
    assert sorted(t.instances_under("a")) == ["x1", "x2", "x3"]


def test_deepest_supported():
    t = _tree()
    assert t.deepest_supported(["root", "a", "a1", "missing"], 2.0) == "a"
    assert t.deepest_supported(["root", "a", "a1"], 0.5) == "a1"
    assert t.deepest_supported(["a", "a1"], 100.0) == "root"


# ----- features ---------------------------------------------------------------------------------

def test_label_family():
    assert label_family("Raises, saving") == "increase"
    assert label_family("cuts margin") == "decrease"
    assert label_family("moves with") == "other"


def test_features_of_entity_and_interaction():
    g = small_graph()
    fa = features_of_entity(g.entities["a"], g)
    assert fa == {"kind": ["company"], "object_type": ["entity"], "region": ["US"], "attribute_kinds": ["policy_rate"]}
    g.entities["c"].subentity_ids = ["c.missing"]
    assert "attribute_kinds" not in features_of_entity(g.entities["c"], g)

    f1 = features_of_interaction(g.interactions["int-1"], g)
    assert f1["polarity"] == ["1"] and f1["label_family"] == ["increase"] and f1["scope"] == ["between"]
    assert f1["source_attr"] == ["policy_rate"] and f1["target_attr"] == ["revenue"]
    assert "source_gen" not in f1 and f1["target_gen"] == ["gen:obj:firm"]
    assert f1["source_features"] == ["region=US"] and f1["target_features"] == ["product=chips"]
    f2 = features_of_interaction(g.interactions["int-2"], g)
    assert f2["scope"] == ["internal"] and f2["polarity"] == ["-1"] and f2["label_family"] == ["decrease"]
    assert "target_features" not in f2


def test_features_of_interaction_with_missing_ends():
    g = small_graph()
    dangling = inter("int-9", "gone.s", "b.y")
    f = features_of_interaction(dangling, g)
    assert "scope" not in f and "source_attr" not in f and f["target_attr"] == ["revenue"]
    del g.entities["b"]
    f = features_of_interaction(g.interactions["int-1"], g)
    assert "target_gen" not in f and f["target_features"] == ["product=chips"]


def _pattern(roles=(), rels=()):
    return SuperentityPattern(id="pat-1", name="p", roles=list(roles), relations=list(rels), created_at=T0)


def test_features_of_pattern_and_dispatch():
    rel = PatternRelation(source_role="a", source_attr="rate", target_role="b", target_attr="price",
                          interaction_generalization_id="gen:int:x", polarity=1, label="raises")
    rel_no_gen = rel.model_copy(update={"interaction_generalization_id": None})
    p = _pattern([RoleSpec(name="a", generalization_id="gen:obj:bank")], [rel, rel_no_gen])
    assert features_of_pattern(p) == {"object_type": ["superentity"], "role_generalizations": ["gen:obj:bank"],
                                      "relation_generalizations": ["gen:int:x"]}
    assert features_of_pattern(_pattern()) == {"object_type": ["superentity"]}
    g = small_graph()
    assert features_of(p, g)["object_type"] == ["superentity"]
    assert features_of(g.entities["a"], g)["object_type"] == ["entity"]
    assert features_of(g.interactions["int-1"], g)["polarity"] == ["1"]
    with pytest.raises(TypeError):
        features_of("text", g)


def test_derive_signature_objects():
    assert derive_signature([], TaxonomyKind.OBJECT) == Signature()
    ents = [{"object_type": ["entity"], "kind": ["company"], "attribute_kinds": ["rate"]},
            {"object_type": ["entity"], "kind": ["agency"]},
            {"object_type": ["superentity"], "role_generalizations": ["r"]}]
    sig = derive_signature(ents, TaxonomyKind.OBJECT)
    assert sig.required == {"kind": ["agency", "company"]} and sig.any_of == {"attribute_kinds": ["rate"]}
    no_kinds = derive_signature([{"object_type": ["entity"], "kind": ["market"]}], TaxonomyKind.OBJECT)
    assert no_kinds.any_of == {}
    pats = derive_signature([{"object_type": ["superentity"], "role_generalizations": ["r1"],
                              "relation_generalizations": ["i1"]}], TaxonomyKind.OBJECT)
    assert pats.required == {"object_type": ["superentity"]}
    assert pats.any_of == {"role_generalizations": ["r1"], "relation_generalizations": ["i1"]}
    bare = derive_signature([{"object_type": ["superentity"]}], TaxonomyKind.OBJECT)
    assert bare.required == {"object_type": ["superentity"]} and bare.any_of == {}


def test_derive_signature_interactions():
    one = derive_signature([{"polarity": ["1"], "source_attr": ["rate"], "target_attr": ["price"]},
                            {"polarity": ["1"], "source_attr": ["oil_price"]}], TaxonomyKind.INTERACTION)
    assert one.required == {"polarity": ["1"]}
    assert one.any_of == {"source_attr": ["oil_price", "rate"], "target_attr": ["price"]}
    mixed = derive_signature([{"polarity": ["1"]}, {"polarity": ["-1"]}], TaxonomyKind.INTERACTION)
    assert mixed.required == {} and mixed.any_of == {}


def test_default_obs_noise():
    assert default_obs_noise("policy_rate", VOCAB) == 0.05
    assert default_obs_noise("oil_price", VOCAB) == 0.05
    assert default_obs_noise("sentiment_index", VOCAB) == 0.25
    assert default_obs_noise("orphan", VOCAB) == 0.15
    assert default_obs_noise("rate", None) == 0.05
    assert default_obs_noise("anything", VOCAB, is_decision=True) == 0.02


def test_satisfied_by_known_skips_unknown_required_keys():
    sig = Signature(required={"kind": ["company"], "region": ["US"]})
    assert sig.satisfied_by_known({"kind": ["company"]}, VOCAB)
    assert sig.match({"kind": ["company"]}, VOCAB) == 0.5


def test_generalization_signature_defaults_are_independent():
    a, b = _gen(), _gen()
    a.stats.effect.push(1.0)
    assert b.stats.effect.n == 0
    assert isinstance(a.prior_dynamics()[0].effect, Gaussian)
