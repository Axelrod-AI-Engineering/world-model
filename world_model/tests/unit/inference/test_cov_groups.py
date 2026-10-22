"""Coarser forecast targets (groups.py): how each kind of group resolves to members, and the effect mixture's edge
cases (short runs, no scenarios)."""

from __future__ import annotations

import numpy as np
import pytest

from axelrod_wm.dynamics.propagation import PropagationResult
from axelrod_wm.events.thesis import TargetGroup
from axelrod_wm.inference.groups import EffectMixture, resolve_group, split_at_horizon
from axelrod_wm.inference.records import ForecastScenario
from axelrod_wm.model.superentity import SuperentityInstance
from tests.conftest import constructed_engine


@pytest.fixture(scope="module")
def eng():
    return constructed_engine(build=True)


def _resolve(eng, kind, ref):
    return resolve_group(TargetGroup(kind=kind, ref=ref), eng.wm, eng.ltm)


def test_unknown_references_resolve_to_none(eng):
    assert _resolve(eng, "entity", "no_such_actor") is None
    assert _resolve(eng, "superentity", "S999") is None
    assert _resolve(eng, "sector", "no_such_sector") is None
    assert _resolve(eng, "category", "ZZ") is None


def test_a_pattern_with_no_bound_instance_has_no_members(eng):
    # HP1 (bank run) is admitted but the construction binds no instance of it
    assert not any(i.pattern_id == "HP1" for i in eng.wm.graph.instances.values())
    name, members = _resolve(eng, "superentity", "HP1")
    assert name.startswith("HP1 · ") and members == []


def test_an_instance_without_live_relations_falls_back_to_its_bound_entities():
    e = constructed_engine(build=True)
    inst = SuperentityInstance(id="inst-HP1", pattern_id="HP1", bindings={"a": "delta", "b": "ghost_actor"},
                               interaction_ids=["no_such_edge"])
    with e.mutator.begin("test", at=e.wm.clock) as txn:
        txn.add("instances", inst)
    name, members = _resolve(e, "superentity", "HP1")
    delta = sorted(s for s in e.wm.graph.entities["delta"].subentity_ids if s in e.wm.graph.subentities)
    assert members == delta and delta                      # the unknown entity is skipped


def test_a_category_resolves_to_its_tagged_entities(eng):
    name, members = _resolve(eng, "category", "sd")
    assert name and members
    tagged = {e.id for e in eng.wm.graph.entities.values() if "SD" in {str(t) for t in e.category_tags}}
    assert {m.split(".")[0] for m in members} <= tagged


def _result(sids, z):
    return PropagationResult({s: i for i, s in enumerate(sids)}, {}, z, None)


def test_the_mixture_reads_each_runs_effect_and_zero_outside_it():
    # 2 samples, 1 subentity, horizon 2
    on = _result(["a"], np.array([[[0.0, 1.0, 2.0]], [[0.0, 1.0, 4.0]]]))
    off = _result(["a"], np.zeros((2, 1, 3)))
    sc = [ForecastScenario(id="SC-1", name="one", weight=1.0, network_ids=[])]
    mix = EffectMixture(sc, {"SC-1": on}, {"SC-1": off}, samples=2, horizon=2)
    ef = mix.effect("a")
    assert ef.shape == (2, 3) and ef[:, 2].tolist() == [2.0, 4.0]
    lv_on, lv_off = mix.levels("a")
    assert lv_on[:, -1].tolist() == [2.0, 4.0] and not lv_off.any()
    # a subentity outside the run sits at zero in both
    z_on, z_off = mix.levels("b")
    assert z_on.shape == (2, 3) and not z_on.any() and not z_off.any()
    assert not mix.effect("b").any()


def test_a_mixture_with_no_scenarios_is_flat_zero():
    mix = EffectMixture([], {}, {}, samples=10, horizon=3)
    on, off = mix.levels("a")
    assert on.shape == off.shape == (1, 4) and not on.any()
    assert mix.effect("a").shape == (1, 4)


def test_split_needs_two_draws_on_each_side():
    assert split_at_horizon(np.array([1.0]), np.array([0.0, 1.0])) == {}
    out = split_at_horizon(np.array([1.0, 2.0, 3.0]), np.array([0.0, 0.0, 0.0]))
    assert out["shift"] == pytest.approx(2.0) and out["domain"][0] == 0.0
