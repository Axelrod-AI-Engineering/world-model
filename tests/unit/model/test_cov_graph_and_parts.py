"""The causal graph's indexes, interactions' significance, kernels, ids, serialization, superentities."""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from scipy import special

from axelrod_wm.model.distributions import Beta, Gamma, Gaussian
from axelrod_wm.model.entity import EntityKind
from axelrod_wm.model.ids import IdFactory, entity_of, is_temp_id, slugify, strip_temp
from axelrod_wm.model.interaction import abs_mean, base_interaction_id
from axelrod_wm.model.serialization import canonical_json, digest, round12, sha256_text, to_jsonable
from axelrod_wm.model.superentity import (
    PatternRelation,
    RoleSpec,
    SuperentityInstance,
    SuperentityPattern,
    TrackRecord,
)
from axelrod_wm.model.temporal import (
    KernelSpec,
    gamma_from_mean,
    kernel_days,
    parse_kernel,
    step_response,
)
from tests.unit.model.graphkit import T0, dyn, entity, inter, small_graph, sub

# ----- graph ------------------------------------------------------------------------------------


def test_channels_in_and_out():
    g = small_graph()
    assert [i.id for i in g.active_interactions()] == ["int-1", "int-2"]
    assert [(s, t) for s, t, _ in g.in_channels("b.y")] == [("a.x", "b.y"), ("b.z", "b.y")]
    assert [(s, t) for s, t, _ in g.out_channels("b.y")] == [("b.y", "b.z")]
    keys = [k for k, *_ in g.channel_items()]
    assert keys == ["int-1", "int-2", "int-2:rev"]
    assert g.interaction_between("b.z", "b.y") == ["int-2"] and g.interaction_between("a.x", "c.w") == []
    g.interactions["int-1"].retired_at = T0
    assert [i.id for i in g.active_interactions()] == ["int-2"]


def test_neighborhood_and_hops():
    g = small_graph()
    assert g.neighborhood(["a.x", "unknown"], 1, 0.0) == {"a.x", "b.y"}
    assert g.neighborhood(["a.x"], 2, 0.0) == {"a.x", "b.y", "b.z"}
    assert g.neighborhood(["a.x"], 2, 10.0) == {"a.x"}
    assert g.neighborhood(["a.x"], -1, 0.0) == {"a.x"}
    assert g.hop_distances(["a.x"]) == {"a.x": 0, "b.y": 1, "b.z": 2}
    assert g.hop_distances(["a.x"], max_hops=1) == {"a.x": 0, "b.y": 1}


def test_directed_costs_are_shortest_paths():
    g = small_graph()
    c = g.directed_costs(["a.x"])
    w1 = -math.log(g.interactions["int-1"].significance_mean())
    w2 = -math.log(g.interactions["int-2"].significance_mean())
    assert c["a.x"] == 0.0 and c["b.y"] == pytest.approx(w1) and c["b.z"] == pytest.approx(w1 + w2)
    assert "c.w" not in c
    # the reverse channel reaches back with the same cost; a cheaper later entry never re-enters
    assert g.directed_costs(["b.z"]) == {"b.z": 0.0, "b.y": pytest.approx(w2)}


def test_directed_costs_with_a_strong_edge_stay_nonnegative():
    g = small_graph()
    g.interactions["int-1"].existence = Beta(alpha=1e6, beta=1.0)
    g.interactions["int-1"].forward.effect = Gaussian(mu=5.0, sigma=0.0)      # significance > 1: cost < 0
    assert g.directed_costs(["a.x"])["b.y"] == 0.0


def test_members_instances_and_member_subentities():
    g = small_graph()
    g.instances["inst-1"] = SuperentityInstance(id="inst-1", pattern_id="p", bindings={"r": "a"}, interaction_ids=[],
                                                child_instance_ids=["inst-2", "missing", "inst-1"])
    g.instances["inst-2"] = SuperentityInstance(id="inst-2", pattern_id="p", bindings={"r": "b", "q": "ghost"},
                                                interaction_ids=[])
    assert g.members("inst-1") == {"a", "b", "ghost"}
    assert g.instances_of_entity("b") == ["inst-1", "inst-2"]
    assert g.member_subentities("inst-2") == {"b.y", "b.z"}
    assert g.instances["inst-2"].entity_ids() == ["b", "ghost"]


def test_entity_links_and_networkx():
    g = small_graph()
    g.subentities["d.v"] = sub("d.v")
    g.entities["d"] = entity("d", subs=["d.v"])
    g.interactions["int-3"] = inter("int-3", "a.x", "b.z", 0.1, label="weak")
    g.interactions["int-4"] = inter("int-4", "c.w", "nowhere.q", 0.1)
    links = g.entity_links()
    assert len(links) == 1
    ln = links[0]
    assert (ln.source_entity_id, ln.target_entity_id) == ("a", "b")
    assert ln.label == "raises" and ln.interaction_ids == ["int-1", "int-3"]
    assert ln.significance == pytest.approx(g.interactions["int-1"].significance_mean())
    g.entity_link_labels["a->b"] = "sets rates for"
    assert g.entity_links()[0].label == "sets rates for"
    nxg = g.to_networkx()
    assert nxg.number_of_nodes() == 6        # 5 subentities plus the dangling target
    assert nxg.has_edge("b.z", "b.y") and nxg["a.x"]["b.y"]["int-1"]["effect"] == 0.8
    assert len(g.content_hash()) == 64


def test_content_hash_is_stable_and_sensitive():
    a, b = small_graph(), small_graph()
    assert a.content_hash() == b.content_hash()
    b.interactions["int-1"].label = "lifts"
    assert a.content_hash() != b.content_hash()


# ----- interactions -----------------------------------------------------------------------------

def test_abs_mean_is_the_folded_normal_mean():
    mu, sd = 0.3, 0.5
    expected = sd * math.sqrt(2 / math.pi) * math.exp(-mu * mu / (2 * sd * sd)) + mu * (1 - 2 * special.ndtr(-mu / sd))
    assert abs_mean(Gaussian(mu=mu, sigma=sd)) == pytest.approx(expected)
    assert abs_mean(Gaussian(mu=0.0, sigma=1.0)) == pytest.approx(math.sqrt(2 / math.pi))
    assert abs_mean(Gaussian(mu=-0.7, sigma=0.0)) == 0.7
    rng = np.random.default_rng(0)
    assert abs_mean(Gaussian(mu=mu, sigma=sd)) == pytest.approx(np.abs(rng.normal(mu, sd, 400_000)).mean(), rel=5e-3)


def test_interaction_channels_polarity_confidence_and_significance():
    g = small_graph()
    i1, i2 = g.interactions["int-1"], g.interactions["int-2"]
    assert len(i1.channels()) == 1 and [c[:2] for c in i2.channels()] == [("b.y", "b.z"), ("b.z", "b.y")]
    assert i1.polarity() == 1 and i2.polarity() == -1
    assert i1.confidence() == pytest.approx(0.9)                   # sd 0: the sign is certain
    noisy = inter("int-5", "a.x", "b.y", 0.5)
    noisy.forward.effect = Gaussian(mu=0.5, sigma=0.5)
    assert noisy.confidence() == pytest.approx(0.9 * special.ndtr(1.0))
    s = i1.significance()
    assert s.mean == pytest.approx(0.9 * 0.8) and s.q05 <= s.q50 <= s.q95
    assert i1.active and base_interaction_id("int-2:rev") == "int-2" and base_interaction_id("int-2") == "int-2"


# ----- kernels ----------------------------------------------------------------------------------

def test_gamma_from_mean_and_kernel_shorthand():
    g = gamma_from_mean(20.0, cv=0.5)
    assert g.mean() == pytest.approx(20.0) and g.sd() / g.mean() == pytest.approx(0.5)
    assert gamma_from_mean(0.0).theta == 1e-9
    k = KernelSpec.model_validate({"delay_days": 7, "lag_days": 21, "duration_days": 60, "shape": "ramp_decay"})
    assert k.means() == pytest.approx((7.0, 21.0, 60.0))
    assert k.shorthand() == pytest.approx({"delay_days": 7.0, "lag_days": 21.0, "duration_days": 60.0})
    perm = KernelSpec.model_validate({"delay_days": None, "lag_days": 5})
    assert perm.means()[0] == pytest.approx(0.0, abs=1e-6) and perm.duration is None
    assert parse_kernel(k) is k and parse_kernel({"delay_days": 1, "lag_days": 1}).means()[2] is None
    full = KernelSpec(delay=gamma_from_mean(3), lag=gamma_from_mean(4))
    assert KernelSpec.model_validate(full.model_dump()) == full


def test_kernel_cv_and_rescale():
    k = KernelSpec.model_validate({"delay_days": 10, "lag_days": 20, "duration_days": 30})
    assert k.cv() == pytest.approx(0.3)
    r = k.rescaled(2.0)
    assert r.means() == pytest.approx((20.0, 40.0, 60.0)) and r.cv() == pytest.approx(0.3)
    r2 = KernelSpec.model_validate({"delay_days": 10, "lag_days": 20}).rescaled(0.5, cv=0.1)
    assert r2.means()[:2] == pytest.approx((5.0, 10.0)) and r2.means()[2] is None and r2.cv() == pytest.approx(0.1)
    gk = KernelSpec(delay=Gaussian(mu=5.0, sigma=1.0), lag=Gaussian(mu=5.0, sigma=1.0))
    assert gk.cv() == pytest.approx(0.3)


def test_kernel_days_rounding_and_lambda():
    assert kernel_days(0.2, 0.2, None) == (1, 1, 1.0)
    assert kernel_days(6.6, 2.4, 30.0, min_delay=3) == (7, 2, pytest.approx(math.exp(-0.1)))
    assert kernel_days(1, 1, float("inf"))[2] == 1.0


def test_step_response_matches_its_definition():
    g = step_response(2, 3, 10.0, 8)
    lam = math.exp(-0.3)
    assert g[:2].tolist() == [0.0, 0.0]
    assert g[2:5] == pytest.approx([1 / 3, 2 / 3, 1.0])
    assert g[5] == pytest.approx(lam) and g[8] == pytest.approx(lam ** 4)
    assert step_response(0, 0, None, 3).tolist() == [0.0, 1.0, 1.0, 1.0]


# ----- ids --------------------------------------------------------------------------------------

def test_id_factory_and_helpers():
    f = IdFactory()
    assert f.peek("int") == "int-000001"
    assert f.next("int") == "int-000001" and f.next("int") == "int-000002" and f.peek("int") == "int-000003"
    assert f.next("H") == "H-000001"
    assert is_temp_id("new:x") and not is_temp_id("x") and not is_temp_id(None) and not is_temp_id("")
    assert strip_temp("new:rbi.policy") == "rbi.policy" and strip_temp("rbi") == "rbi"
    assert slugify("Chip exports (US)") == "chip_exports_us" and slugify("!!!") == "item"
    assert entity_of("a.b.c") == "a" and entity_of("solo") == "solo"


# ----- serialization ----------------------------------------------------------------------------

def test_round12_and_canonical_json():
    assert round12(0.0) == 0.0 and round12(1 / 3) == float("0.333333333333")
    assert math.isinf(round12(float("inf"))) and math.isnan(round12(float("nan")))
    assert canonical_json({"b": 1, "a": 0.1 + 0.2}) == '{"a":0.3,"b":1.0}'
    assert canonical_json({"s": {"y", "x"}, "t": T0}) == '{"s":["x","y"],"t":"2026-01-01T00:00:00+00:00"}'
    assert canonical_json({"a": np.array([1.0, 2.0])}) == '{"a":[1.0,2.0]}'
    with pytest.raises(TypeError):
        canonical_json({"a": object()})
    assert digest({"a": 0}) == digest({"a": 0.0})
    assert sha256_text("x") == digest.__globals__["hashlib"].sha256(b"x").hexdigest()


def test_to_jsonable_models_and_plain_values():
    g = Gaussian(mu=1.0, sigma=2.0)
    assert to_jsonable(g) == {"family": "gaussian", "mu": 1.0, "sigma": 2.0}
    assert to_jsonable([g, frozenset({"b", "a"})]) == [{"family": "gaussian", "mu": 1.0, "sigma": 2.0}, ["a", "b"]]
    assert canonical_json(g) == json.dumps(to_jsonable(g), sort_keys=True, separators=(",", ":"))


def test_strset_serializes_sorted():
    p = SuperentityPattern(id="p", name="p", roles=[], relations=[], created_at=T0, rival_ids={"z", "a", "m"})
    assert json.loads(p.model_dump_json())["rival_ids"] == ["a", "m", "z"]


# ----- superentities ----------------------------------------------------------------------------

def test_pattern_roles_relations_and_track_record():
    rel = PatternRelation(source_role="a", source_attr="rate", target_role="b", target_attr="price", polarity=1,
                          label="raises")
    absent = rel.model_copy(update={"present": False, "polarity": -1})
    p = SuperentityPattern(id="p", name="p", roles=[RoleSpec(name="a", generalization_id="g")],
                           relations=[rel, absent], created_at=T0)
    assert p.role("a").generalization_id == "g" and p.role("zz") is None
    assert p.present_relations() == [rel]
    assert rel.key() == ("a", "rate", "b", "price", "", 1, True)
    tr = TrackRecord()
    assert tr.mean() == 0.5
    tr2 = tr.plus(hits=3.0).plus(misses=1.0)
    assert (tr2.hits, tr2.misses) == (3.0, 1.0) and tr2.mean() == pytest.approx(4 / 6) and tr.hits == 0.0


# ----- entities ---------------------------------------------------------------------------------

def test_subentity_family_and_link():
    s = sub("a.p")
    assert s.family == "gaussian" and str(s.link) == "identity"
    g = Gamma(k=2.0, theta=1.0)
    s2 = s.model_copy(update={"posterior": g})
    assert s2.family == "gamma" and str(s2.link) == "log"
    assert entity("m", kind=EntityKind.MARKET).kind == "market"
    assert dyn(0.1).effect.mean() == 0.1


def test_directed_costs_skip_a_node_reached_twice():
    from axelrod_wm.model.graph import CausalGraph

    subs = {s: sub(s) for s in ("a.s", "b.s", "c.s", "d.s")}
    ints = {"i1": inter("i1", "a.s", "b.s", 0.9), "i2": inter("i2", "a.s", "c.s", 0.8),
            "i3": inter("i3", "b.s", "d.s", 0.9), "i4": inter("i4", "c.s", "d.s", 0.9)}
    g = CausalGraph(subentities=subs, interactions=ints)
    c = g.directed_costs(["a.s"])
    w = {k: -math.log(v.significance_mean()) for k, v in ints.items()}
    assert c["d.s"] == pytest.approx(w["i1"] + w["i3"])          # d is pushed twice, settled once
    assert c["c.s"] == pytest.approx(w["i2"])


def test_hypothesis_fills_subjects_and_decays():
    from datetime import timedelta

    from axelrod_wm.model.evidence import Origin
    from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind

    h = Hypothesis(id="H-1", kind=HypothesisKind.INTERACTION_PRESENT, statement="s", source_id="b.y",
                   target_id="a.x", probability=0.5, informational_value=2.0, scored_at=T0, half_life_days=7.0,
                   origin=Origin.INFERENCE)
    assert h.subject_entity_ids == ["a", "b"] and h.created_at == T0
    assert h.current_value(T0 + timedelta(days=7)) == pytest.approx(1.0)
    assert h.current_value(T0 - timedelta(days=3)) == pytest.approx(2.0)
    kept = Hypothesis(id="H-2", kind=HypothesisKind.ENTITY_DECISION, statement="s", probability=0.5, scored_at=T0,
                      origin=Origin.INFERENCE, subject_entity_ids=["z"], created_at=T0 - timedelta(days=1))
    assert kept.subject_entity_ids == ["z"] and kept.created_at == T0 - timedelta(days=1)
