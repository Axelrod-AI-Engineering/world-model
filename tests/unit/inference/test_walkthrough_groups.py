"""Additions: trace scopes (the walkthrough replays one scope), small distribution pictures, forecasts for
coarser targets, the two-children split, weekly VOI sensitivity, and the world's keyed randomness."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pytest

from axelrod_wm.engine.initialize import ConstructionSpec
from axelrod_wm.events.thesis import TargetGroup
from axelrod_wm.model.distributions import Gaussian, density_of_samples
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind
from axelrod_wm.shared.classify import SplitOnSharedFeatureGrower
from axelrod_wm.sim.world import SyntheticWorld, TruthSpec
from axelrod_wm.trace import Phase, RecordingTracer
from tests.conftest import START, VOCAB, constructed_engine, oil_thesis, warm_taxonomies

NOW = START + timedelta(days=30)
OIL = "resources_energy.oil_price"


# -- trace scopes ------------------------------------------------------------------------------------
def test_tracer_scopes_nest_and_restore():
    tr = RecordingTracer()
    tr.emit(Phase.INGEST, "a")
    with tr.scoped("ME-01"):
        tr.emit(Phase.INGEST, "b")
        with tr.scoped("day:2026-01-28"):
            tr.emit(Phase.FOLD, "c")
        with tr.scoped(None):           # None keeps the enclosing scope
            tr.emit(Phase.FOLD, "d")
    tr.emit(Phase.FOLD, "e")
    assert [(e.kind, e.scope) for e in tr.events] == [("a", None), ("b", "ME-01"), ("c", "day:2026-01-28"),
                                                       ("d", "ME-01"), ("e", None)]


def test_a_failing_step_still_restores_the_scope():
    tr = RecordingTracer()
    with pytest.raises(RuntimeError), tr.scoped("T-01"):
        raise RuntimeError("boom")
    tr.emit(Phase.FOLD, "after")
    assert tr.events[-1].scope is None


# -- distribution pictures ---------------------------------------------------------------------------------
def test_density_points_cover_the_central_99_percent_and_peak_at_the_mode():
    pts = Gaussian(mu=2.0, sigma=0.5).density_points(41)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    assert len(pts) == 41 and max(ys) == pytest.approx(1.0)
    assert xs[0] == pytest.approx(2.0 - 2.5758 * 0.5, abs=1e-3)
    assert xs[-1] == pytest.approx(2.0 + 2.5758 * 0.5, abs=1e-3)
    assert xs[ys.index(max(ys))] == pytest.approx(2.0, abs=0.05)


def test_density_of_samples_is_peak_normalized_and_empty_when_degenerate():
    s = density_of_samples(np.random.default_rng(0).normal(1.0, 0.2, 4000), n=24)
    assert len(s) == 24 and max(p[1] for p in s) == pytest.approx(1.0)
    peak = max(s, key=lambda p: p[1])[0]
    assert peak == pytest.approx(1.0, abs=0.1)
    assert density_of_samples(np.zeros(10)) == []
    assert density_of_samples(np.array([1.0])) == []


# -- forecasts for coarser targets ------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def grouped():
    eng = constructed_engine(build=True)
    warm_taxonomies(eng)
    th = oil_thesis(NOW).model_copy(update={"target_groups": [
        TargetGroup(kind="entity", ref="exxonmobil"), TargetGroup(kind="sector", ref="airlines"),
        TargetGroup(kind="superentity", ref="S2"), TargetGroup(kind="category", ref="SD"),
        TargetGroup(kind="entity", ref="no_such_actor")]})
    return eng, th, eng.inference.run(th, NOW)


def test_groups_resolve_and_unknown_references_are_dropped(grouped):
    _eng, th, fc = grouped
    assert [g.id for g in fc.groups] == ["entity:exxonmobil", "sector:airlines", "superentity:S2", "category:SD"]
    for g in fc.groups:
        assert g.members and len(g.effect_summary) == th.horizon_days + 1
        assert g.top and all(sid in g.members for sid, _ in g.top)
    airlines = next(g for g in fc.groups if g.kind == "sector")
    assert {m.split(".")[0] for m in airlines.members} == {"delta", "united_airlines"}


def test_a_group_forecast_is_its_response_so_the_shocked_value_is_left_out(grouped):
    _eng, _th, fc = grouped
    s2 = next(g for g in fc.groups if g.kind == "superentity")
    assert OIL not in s2.members and "inflation.headline_cpi" in s2.members
    exxon = next(g for g in fc.groups if g.ref == "exxonmobil")
    assert exxon.effect_summary[-1].q50 > 0          # dearer oil lifts Exxon's earnings (e73)


def test_every_target_gets_a_small_density_of_its_effect(grouped):
    _eng, _th, fc = grouped
    assert set(fc.effect_density) == set(fc.targets)
    cpi = fc.effect_density["inflation.headline_cpi"]
    assert cpi and max(p[1] for p in cpi) == pytest.approx(1.0)


def test_group_forecasts_leave_the_state_alone(grouped):
    eng, th, fc = grouped
    again = eng.inference.run(th, NOW)
    assert [g.effect_summary[-1].q50 for g in again.groups] == [g.effect_summary[-1].q50 for g in fc.groups]


# -- the taxonomy keeps 0 or >= 2 children ------------------------------------------------------------------------
def _fill_leaf(eng, regions: list[str], node: str = "gen:obj:airline") -> list[str]:
    from axelrod_wm.model.entity import Entity

    at = eng.wm.clock
    ids = []
    with eng.mutator.begin("fill", at=at) as txn:
        for k, region in enumerate(regions):
            eid = f"carrier{k}"
            ids.append(eid)
            txn.add("entities", Entity(id=eid, name=f"Carrier {k}", kind="company", category_tags={"SD"},
                                       features={"region": region}, origin="human", created_at=at,
                                       generalization_id=node))
        txn.update("generalizations.object", node, instance_ids=ids)
    return ids


def test_a_leaf_splits_only_into_two_children_at_once():
    eng = constructed_engine()
    _fill_leaf(eng, ["EU"] * 4 + ["US"] * 4 + ["JP"], node="gen:obj:bank")
    tax = eng.ltm.object_generalizations.taxonomy
    ctx = eng.context(learn=True, now=eng.wm.clock)
    with eng.mutator.begin("grow", at=eng.wm.clock) as txn:
        created = SplitOnSharedFeatureGrower().maybe_split(tax, "gen:obj:bank", ctx, txn)
    assert len(created) == 2
    req = sorted(tax.nodes[c].signature.required["region"][0] for c in created)
    assert req == ["EU", "US"]
    assert tax.nodes["gen:obj:bank"].instance_ids == ["carrier8"]


def test_a_leaf_with_one_shared_group_does_not_split():
    eng = constructed_engine()
    _fill_leaf(eng, ["EU"] * 4 + ["US", "JP"], node="gen:obj:bank")
    tax = eng.ltm.object_generalizations.taxonomy
    ctx = eng.context(learn=True, now=eng.wm.clock)
    with eng.mutator.begin("grow", at=eng.wm.clock) as txn:
        assert SplitOnSharedFeatureGrower().maybe_split(tax, "gen:obj:bank", ctx, txn) == []
    assert not tax.nodes["gen:obj:bank"].child_ids


# -- VOI: the sensitivity is kept for a week, zero included ----------------------------------------------------------
def test_sensitivity_is_recomputed_weekly_even_when_it_is_zero():
    eng = constructed_engine(build=True)
    scorer = eng.components["hypothesis_scorer"]
    calls = []

    def fake(h, wm, ltm, ctx):
        calls.append(ctx.now)
        return 0.0

    scorer.sensitivity = fake
    h = Hypothesis(id="H-z", kind=HypothesisKind.INTERACTION_PRESENT, statement="e43 holds", interaction_id="e43",
                   source_id="inflation.headline_cpi", target_id="federal_reserve.policy_stance", probability=0.5,
                   scored_at=NOW, origin="human", half_life_days=14)
    for days in (0, 3, 6, 8, 9):
        h = scorer.rescore(h, eng.wm, eng.ltm, eng.context(learn=False, now=NOW + timedelta(days=days)), None)
    assert calls == [NOW, NOW + timedelta(days=8)]
    assert h.sensitivity_at == NOW + timedelta(days=8) and h.scored_at == NOW + timedelta(days=9)


def test_the_frozen_history_reads_the_same_values():
    from axelrod_wm.inference.voi import _FrozenHistory

    eng = constructed_engine(build=True)
    dev = eng.wm.deviations
    frozen = _FrozenHistory(dev)
    a = frozen.array(OIL, 0, 30)
    assert a == dev.array(OIL, 0, 30) and frozen.array(OIL, 0, 30) is a
    assert frozen.first_kept_day == getattr(dev, "first_kept_day", frozen.first_kept_day)


# -- the world's randomness is keyed --------------------------------------------------------------------------------
def test_adding_an_actor_does_not_redeal_the_other_series():
    spec = ConstructionSpec.load("data/worlds/economy")
    truth = TruthSpec.load("data/scenarios/oil_shock_demo/truth.yaml")
    drop = "united_airlines"
    fewer = spec.model_copy(update={
        "entities": [e for e in spec.entities if e.id != drop],
        "interactions": [i for i in spec.interactions
                         if not (i.source.startswith(f"{drop}.") or i.target.startswith(f"{drop}."))]})
    end = datetime(2023, 4, 1, tzinfo=timezone.utc)
    worlds = []
    for sp in (spec, fewer):
        w = SyntheticWorld(sp, truth, 7, origin=date(2023, 1, 2), vocab=VOCAB)
        w.advance(end)
        worlds.append(w)
    for sid in (OIL, "inflation.headline_cpi", "confidence.consumer_confidence"):
        assert [worlds[0].z_at(sid, d) for d in range(80)] == pytest.approx([worlds[1].z_at(sid, d) for d in range(80)])
