"""The inference task (§8.9): the stage interfaces, the context layer, binding constraints, no scenarios, pinning,
and the read-out."""

from __future__ import annotations

from datetime import timedelta

import pytest

from axelrod_wm.inference.task import (
    ForecastUnifier,
    NetworkCoupler,
    NetworkIsolator,
    NetworkPredictor,
    UnboundThesis,
)
from axelrod_wm.repo.ledger import LedgerKind
from tests.conftest import START, constructed_engine, make_config, oil_thesis

NOW = START + timedelta(days=30)
OIL = "resources_energy.oil_price"
CPI = "inflation.headline_cpi"


def _engine():
    return constructed_engine(build=True, config=make_config(propagation={"samples": 32}))


def _thesis(thesis_id="T-cov", **kw):
    return oil_thesis(NOW, thesis_id=thesis_id, horizon_days=60, **kw)


# -- the stage interfaces -------------------------------------------------------------------------------------------
class _Isolator(NetworkIsolator):
    def isolate(self, shared, wm, ltm, ctx):
        return super().isolate(shared, wm, ltm, ctx)


class _Predictor(NetworkPredictor):
    def predict(self, network, inputs, model, ctx):
        return super().predict(network, inputs, model, ctx)


class _Coupler(NetworkCoupler):
    def couple(self, networks, forced_existence, shocks, model, ctx, n_samples=None):
        return super().couple(networks, forced_existence, shocks, model, ctx, n_samples)


class _Unifier(ForecastUnifier):
    def plan(self, networks, wm, ltm, ctx):
        return super().plan(networks, wm, ltm, ctx)

    def combine(self, thesis, scenarios, coupled, baseline, local, networks, ctx):
        return super().combine(thesis, scenarios, coupled, baseline, local, networks, ctx)


def test_the_stage_interfaces_are_abstract_and_their_bodies_return_nothing():
    for abc in (NetworkIsolator, NetworkPredictor, NetworkCoupler, ForecastUnifier):
        with pytest.raises(TypeError):
            abc()
    assert _Isolator().isolate(None, None, None, None) is None
    assert _Predictor().predict(None, None, None, None) is None
    assert _Coupler().couple([], {}, [], None, None) is None
    assert _Unifier().plan([], None, None, None) is None
    assert _Unifier().combine(None, [], {}, {}, {}, [], None) is None


def test_an_unbound_thesis_names_its_fuzzy_ends():
    unbound = [{"end": "target", "candidates": ["a.x", "b.x"]}]
    err = UnboundThesis(unbound)
    assert err.unbound is unbound and "unbound ends" in str(err) and "a.x" in str(err)


# -- the run --------------------------------------------------------------------------------------------------------
def test_without_a_watchlist_or_targets_no_context_network_is_added(monkeypatch):
    eng = _engine()
    real = eng.components["isolator"]
    seen = []

    class Recording(NetworkIsolator):
        def isolate(self, shared, wm, ltm, ctx):
            seen.extend(real.isolate(shared, wm, ltm, ctx))
            return list(seen)

    monkeypatch.setitem(eng.components, "isolator", Recording())
    fc = eng.inference.run(_thesis(targets=[]), NOW)
    assert seen and [n.id for n in fc.networks] == [n.id for n in seen]
    assert fc.shocked == [OIL]


def test_a_binding_constraint_is_net_of_the_baseline_and_only_where_the_shock_reaches(monkeypatch):
    eng = _engine()
    real = eng.components["coupler"]

    class Bending(NetworkCoupler):
        def couple(self, networks, forced_existence, shocks, model, ctx, n_samples=None):
            res = real.couple(networks, forced_existence, shocks, model, ctx, n_samples)
            res.bound_hits = ({OIL: 0.6, CPI: 0.31, "nowhere.value": 0.9} if shocks else {OIL: 0.1, CPI: 0.3})
            return res

    monkeypatch.setitem(eng.components, "coupler", Bending())
    fc = eng.inference.run(_thesis(), NOW)
    total = sum(s.weight for s in fc.scenarios)
    # oil bends in half the draws beyond the baseline's; CPI's extra 1% is below the 5% floor; the unknown value is
    # never reached by the shock
    assert fc.constraints_binding == {OIL: round(0.5 * total, 4)}


def test_a_forecast_with_no_scenarios_has_no_paths_or_frames(monkeypatch):
    eng = _engine()
    real = eng.components["unifier"]

    class Empty(ForecastUnifier):
        def plan(self, networks, wm, ltm, ctx):
            return []

        def combine(self, thesis, scenarios, coupled, baseline, local, networks, ctx):
            return real.combine(thesis, scenarios, coupled, baseline, local, networks, ctx)

    monkeypatch.setitem(eng.components, "unifier", Empty())
    fc = eng.inference.run(_thesis(), NOW)
    assert fc.scenarios == [] and fc.paths is None and fc.constraints_binding == {}
    assert all(e.path == [] for e in fc.transmission)


def test_a_pinned_thesis_is_pinned_once_and_a_second_pose_replaces_the_first():
    eng = _engine()
    th = _thesis(thesis_id="T-pin").model_copy(update={"pinned": True})
    first = eng.inference.run(th, NOW)
    layer = eng.wm.forecast_layer
    assert "T-pin" in layer.pinned and layer.pose_counts["T-pin"] == 1
    second = eng.inference.run(th, NOW)
    assert layer.pinned == {"T-pin"} and layer.pose_counts["T-pin"] == 2 and layer.order == ["T-pin"]
    assert layer.by_thesis["T-pin"].forecast.id == second.id != first.id


def test_reading_out_a_view_without_its_thesis_logs_only_the_forecast():
    eng = _engine()
    fc = eng.inference.run(_thesis(), NOW)
    layer = eng.wm.forecast_layer
    layer.by_thesis["T-cov"] = layer.by_thesis["T-cov"].model_copy(update={"thesis": None})
    n_thesis = len(eng.ledger.of_kind(LedgerKind.THESIS))
    n_forecast = len(eng.ledger.of_kind(LedgerKind.FORECAST))
    out = eng.inference.read_out("T-cov")
    assert out.id == fc.id
    assert len(eng.ledger.of_kind(LedgerKind.THESIS)) == n_thesis
    forecasts = eng.ledger.of_kind(LedgerKind.FORECAST)
    assert len(forecasts) == n_forecast + 1 and forecasts[-1].recorded_at == eng.wm.clock


def test_a_thesis_without_a_shock_is_a_baseline_with_nothing_transmitted():
    fc = _engine().inference.run(_thesis(thesis_id="T-base", delta=0.0, targets=[]), NOW)
    assert fc.is_baseline and fc.shocked == [] and fc.transmission == [] and fc.constraints_binding == {}
