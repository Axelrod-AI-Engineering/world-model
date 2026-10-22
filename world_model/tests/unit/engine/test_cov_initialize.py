"""Initialization on a tiny hand-written world: spec checks, kind defaults, taxonomies, priors, seeds."""

from __future__ import annotations

import math
from datetime import date

import pytest
import yaml

from axelrod_wm.engine.engine import Engine
from axelrod_wm.engine.initialize import (
    ConstructionError,
    ConstructionSpec,
    FrontierSeed,
    Initializer,
    PatternSeed,
    SeedFile,
    SubentitySpec,
    _native_prior,
    apply_kind_defaults,
    load_taxonomy,
    load_vocabulary,
)
from axelrod_wm.model.distributions import Gaussian, LogNormal
from axelrod_wm.model.taxonomy import AttributeVocabulary, TaxonomyKind
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.trace import NullTracer
from tests.conftest import make_config
from tests.where import TAXONOMY

ATTRS = {"rate": {"parent": None, "family": "gaussian"}, "price": {"parent": None, "family": "lognormal"}}
OBJECTS = {"root": "gen:obj:root", "nodes": [{"id": "gen:obj:root", "name": "Object", "parent": None},
                                              {"id": "gen:obj:firm", "name": "Firm", "parent": "gen:obj:root",
                                               "instances": ["acme"]}]}
INTERACTIONS = {"root": "gen:int:root", "nodes": [{"id": "gen:int:root", "name": "Relation", "parent": None},
                                                   {"id": "gen:int:cost", "name": "Cost push", "parent": "gen:int:root"}]}


def _write(path, data):
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def _taxonomy(tmp_path, attrs=ATTRS, objects=OBJECTS, interactions=INTERACTIONS):
    d = tmp_path / "taxonomy"
    d.mkdir(exist_ok=True)
    _write(d / "attributes.yaml", attrs)
    _write(d / "objects.yaml", objects)
    _write(d / "interactions.yaml", interactions)
    return d


def _ent(eid, subs, **kw):
    return {"id": eid, "name": eid.title(), "kind": "company", "category_tags": ["SD"], "subentities": subs, **kw}


def _sub(sid, kind="rate", **kw):
    base = {"id": sid, "name": sid, "attribute_kind": kind, "unit": "%", "mean": 1.0, "scale": 0.5}
    base.update(kw)
    return base


def _spec(entities, interactions=(), **kw):
    return ConstructionSpec.model_validate({"entities": entities, "interactions": list(interactions), **kw})


def _engine(vocab=None):
    return Engine(make_config(), MemoryBackend(), NullTracer(), vocab=vocab)


# -- ConstructionSpec.load ------------------------------------------------------------------

def test_load_wraps_an_invalid_spec_with_the_folder_name(tmp_path):
    d = tmp_path / "world"
    d.mkdir()
    _write(d / "entities.yaml", {"entities": [{"id": "x"}]})       # no name, kind, ...
    _write(d / "interactions.yaml", {})
    with pytest.raises(ConstructionError, match="invalid construction spec in"):
        ConstructionSpec.load(d, _taxonomy(tmp_path))


# -- validate_spec ----------------------------------------------------------------------------

def _two_entities(**sub_kw):
    return [_ent("a", [_sub("a.x"), _sub("a.y", **sub_kw)]), _ent("b", [_sub("b.z")])]


@pytest.mark.parametrize("spec,msg", [
    (lambda: _spec([_ent("a", []), _ent("a", [])]), "duplicate entity id 'a'"),
    (lambda: _spec([_ent("a", [_sub("b.x")])]), "must start with 'a.'"),
    (lambda: _spec([_ent("a", [_sub("a.x"), _sub("a.x")])]), "duplicate subentity id 'a.x'"),
    (lambda: _spec([_ent("a", [_sub("a.x", kind="mood")])]), "unknown attribute kind 'mood'"),
    (lambda: _spec([_ent("a", [_sub("a.x", family="weird")])]), "unknown family 'weird'"),
    (lambda: _spec([_ent("a", [_sub("a.x", scale=-1.0)])]), "scale must be positive"),
    (lambda: _spec([_ent("a", [_sub("a.x")])], decision_variables=["a.nope"]), "decision variable 'a.nope'"),
    (lambda: _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "b.z", "label": "l"},
                                     {"id": "i1", "source": "a.y", "target": "b.z", "label": "l"}]),
     "duplicate interaction id 'i1'"),
    (lambda: _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "b.z", "label": "  "}]), "has no label"),
    (lambda: _spec(_two_entities(), [{"id": "i1", "source": "a.q", "target": "b.z", "label": "l"}]),
     "source 'a.q' is not a known subentity"),
    (lambda: _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "a.x", "label": "l"}]),
     "source and target are the same"),
    (lambda: _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "b.z", "label": "l"},
                                     {"id": "i2", "source": "a.x", "target": "b.z", "label": "l"}]),
     "duplicates source, target, and label"),
    (lambda: _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "b.z", "label": "l",
                                      "direction": "bidirectional"}]), "bidirectional but has no reverse"),
    (lambda: _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "b.z", "label": "l",
                                      "parameters": [{"name": "p", "moderator": "a.q", "coefficient": {"mu": 1}}]}]),
     "moderator 'a.q' is not a known subentity"),
])
def test_validate_spec_names_the_offending_item(spec, msg):
    vocab = load_vocabulary(TAXONOMY)
    with pytest.raises(ConstructionError, match=msg):
        spec().validate_spec(vocab)


def test_validate_spec_accepts_a_subentity_without_any_prior_fields():
    spec = _spec([_ent("a", [_sub("a.x", mean=None, scale=None)])])
    spec.validate_spec(AttributeVocabulary(kinds={}))      # an empty vocabulary checks no kinds
    assert spec.subentity_ids() == {"a.x"}


# -- apply_kind_defaults ----------------------------------------------------------------------

def test_invalid_kind_defaults_name_the_file(tmp_path):
    objects = {"root": "gen:obj:root", "nodes": [{"id": "gen:obj:root", "name": "Object", "parent": None,
                                                   "defaults": [{"slot": "revenue"}]}]}
    path = _write(tmp_path / "objects.yaml", objects)
    with pytest.raises(ConstructionError, match="invalid defaults in objects.yaml"):
        apply_kind_defaults(_spec([_ent("a", [])]), path)


# -- vocabulary and taxonomies ----------------------------------------------------------------

def test_vocabulary_rejects_an_unknown_parent(tmp_path):
    d = _taxonomy(tmp_path, attrs={"rate": {"parent": "ratio"}})
    with pytest.raises(ConstructionError, match="attribute kind 'rate': unknown parent 'ratio'"):
        load_vocabulary(d)


def test_vocabulary_rejects_an_unknown_family(tmp_path):
    d = _taxonomy(tmp_path, attrs={"rate": {"family": "cauchy"}})
    with pytest.raises(ConstructionError, match="attribute kind 'rate': unknown family 'cauchy'"):
        load_vocabulary(d)


def test_vocabulary_defaults_to_gaussian(tmp_path):
    vocab = load_vocabulary(_taxonomy(tmp_path, attrs={"rate": {}, "policy_rate": {"parent": "rate"}}))
    assert vocab.kinds["policy_rate"].parent == "rate" and vocab.kinds["rate"].family == "gaussian"


@pytest.mark.parametrize("data,msg", [
    ({"root": "r", "nodes": [{"id": "r", "name": "R"}, {"id": "r", "name": "R again"}]}, "duplicate generalization 'r'"),
    ({"root": "missing", "nodes": [{"id": "r", "name": "R"}]}, "root 'missing' is not a node"),
    ({"root": "r", "nodes": [{"id": "r", "name": "R", "parent": "q"}, {"id": "q", "name": "Q", "parent": None}]},
     "the root 'r' must have no parent"),
])
def test_load_taxonomy_rejects_malformed_trees(tmp_path, data, msg):
    path = _write(tmp_path / "t.yaml", data)
    with pytest.raises(ConstructionError, match=msg):
        load_taxonomy(path, TaxonomyKind.OBJECT)


# -- priors -----------------------------------------------------------------------------------

def test_native_prior_without_scale_takes_the_link_sd():
    s = SubentitySpec.model_validate(_sub("a.x", mean=None, scale=None, prior={"mu": 2.0, "sigma": 0.3}))
    prior, scale = _native_prior(s, "gaussian", AttributeVocabulary(kinds={}))
    assert prior == Gaussian(mu=2.0, sigma=0.3)
    assert scale == pytest.approx(0.3)


def test_native_prior_with_scale_keeps_it():
    s = SubentitySpec.model_validate(_sub("a.x", mean=None, scale=2.0, prior={"mu": 2.0, "sigma": 0.3}))
    assert _native_prior(s, "gaussian", AttributeVocabulary(kinds={}))[1] == 2.0


def test_native_prior_requires_a_prior_or_a_mean():
    s = SubentitySpec.model_validate(_sub("a.x", mean=None, scale=None))
    with pytest.raises(ConstructionError, match="subentity 'a.x' has no prior"):
        _native_prior(s, "gaussian", AttributeVocabulary(kinds={}))


# -- construct --------------------------------------------------------------------------------

def _construct(tmp_path, spec, vocab=None):
    tax = _taxonomy(tmp_path)
    eng = _engine()
    Initializer(eng).construct(spec, tax, start=date(2024, 1, 1), vocab=vocab)
    return eng


def test_construct_takes_the_taxonomy_vocabulary_when_the_engine_has_none(tmp_path):
    spec = _spec([_ent("acme", [_sub("acme.cost", kind="price", mean=10.0, scale=0.2)]),
                  _ent("oil", [_sub("oil.price", kind="price", mean=80.0, scale=0.3)])],
                 [{"id": "i1", "source": "oil.price", "target": "acme.cost", "label": "raises",
                   "effect": {"family": "lognormal", "mu": 0.0, "sigma": 0.1},
                   "generalization": "gen:int:cost",
                   "direction": "bidirectional",
                   "reverse": {"effect": {"family": "lognormal", "mu": 0.0, "sigma": 0.2},
                               "kernel": {"delay_days": 3, "lag_days": 5, "duration_days": None}}}])
    eng = _construct(tmp_path, spec)
    assert set(eng.vocab.kinds) == {"rate", "price"}
    inter = eng.wm.graph.interactions["i1"]
    # non-gaussian effects keep their own parameters: no sigma is filled in
    assert inter.forward.effect == LogNormal(mu=0.0, sigma=0.1)
    assert inter.reverse.effect == LogNormal(mu=0.0, sigma=0.2)
    assert inter.generalization_id == "gen:int:cost"
    assert "i1" in eng.ltm.interaction_generalizations.taxonomy.nodes["gen:int:cost"].instance_ids
    assert eng.wm.graph.entities["acme"].generalization_id == "gen:obj:firm"
    sub = eng.wm.graph.subentities["oil.price"]
    assert math.exp(sub.prior.mu) == pytest.approx(80.0)


def test_construct_gaussian_reverse_gets_a_default_sigma(tmp_path):
    spec = _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "b.z", "label": "l",
                                    "direction": "bidirectional",
                                    "reverse": {"effect": {"mu": 0.4},
                                                "kernel": {"delay_days": 3, "lag_days": 5, "duration_days": None}}}])
    eng = _construct(tmp_path, spec)
    inter = eng.wm.graph.interactions["i1"]
    assert inter.reverse.effect == Gaussian(mu=0.4, sigma=0.15)
    assert inter.forward.effect == Gaussian(mu=0.0, sigma=0.15)


def test_construct_rejects_an_unknown_generalization(tmp_path):
    spec = _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "b.z", "label": "l",
                                    "generalization": "gen:int:nowhere"}])
    with pytest.raises(ConstructionError, match="interaction 'i1': unknown generalization 'gen:int:nowhere'"):
        _construct(tmp_path, spec, vocab=load_vocabulary(_taxonomy(tmp_path)))


# -- seeds ------------------------------------------------------------------------------------

@pytest.fixture
def built(tmp_path):
    spec = _spec(_two_entities(), [{"id": "i1", "source": "a.x", "target": "b.z", "label": "l"}])
    return _construct(tmp_path, spec)


def _seeds(*patterns, frontier=()):
    return SeedFile(patterns=[PatternSeed.model_validate(p) for p in patterns],
                    frontier_seeds=[FrontierSeed.model_validate(f) for f in frontier])


@pytest.mark.parametrize("pattern,msg", [
    ({"id": "P", "name": "P", "members": ["a", "ghost"]}, "seed pattern 'P': unknown member 'ghost'"),
    ({"id": "P", "name": "P", "members": ["a", "b"], "interactions": ["i9"]}, "unknown interaction 'i9'"),
    ({"id": "P", "name": "P", "members": ["a", "b"], "sub_patterns": ["Q"]}, "part 'Q' must be a bound seed"),
])
def test_load_seeds_rejects_bad_patterns(built, pattern, msg):
    with pytest.raises(ConstructionError, match=msg):
        Initializer(built).load_seeds(_seeds(pattern), now=built.wm.clock)


def test_load_frontier_seeds_rejects_an_unknown_subentity(built):
    seeds = _seeds(frontier=[{"earlier": "a.x", "later": "b.nope"}])
    with pytest.raises(ConstructionError, match="frontier seed: unknown subentity 'b.nope'"):
        Initializer(built).load_frontier_seeds(seeds, now=built.wm.clock)
