"""The performance task: isolate, predict, couple, unify, explain (§8.9, D1, D2, D5)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

from axelrod_wm.engine.performance.records import (
    Forecast,
    ForecastScenario,
    Network,
    NetworkInputs,
    NetworkKind,
    NetworkPrediction,
    NetworkSummary,
)
from axelrod_wm.engine.propagation import PropagationResult, ShockInput
from axelrod_wm.engine.registry import registry
from axelrod_wm.events.ledger import LedgerKind
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import PrefilledModel
    from axelrod_wm.engine.shared import SharedResult
    from axelrod_wm.events.thesis import Thesis
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory

__all__ = ["NetworkKind", "Network", "NetworkInputs", "NetworkPrediction", "ForecastScenario", "NetworkSummary",
           "Forecast", "NetworkIsolator", "NetworkPredictor", "NetworkCoupler", "ForecastUnifier", "PerformanceTask",
           "UnboundThesis"]


class NetworkIsolator(ABC):
    @abstractmethod
    def isolate(self, shared: SharedResult, wm: WorkingMemory, ltm: LongTermMemory,
                ctx: ProcessContext) -> list[Network]: ...


class NetworkPredictor(ABC):
    @abstractmethod
    def predict(self, network: Network, inputs: NetworkInputs, model: PrefilledModel,
                ctx: ProcessContext) -> NetworkPrediction: ...


class NetworkCoupler(ABC):
    @abstractmethod
    def couple(self, networks: list[Network], forced_existence: dict[str, bool],
               shocks: list[ShockInput], model: PrefilledModel, ctx: ProcessContext,
               n_samples: int | None = None) -> PropagationResult: ...


class ForecastUnifier(ABC):
    @abstractmethod
    def plan(self, networks: list[Network], wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext) -> list[ForecastScenario]: ...

    @abstractmethod
    def combine(self, thesis: Thesis, scenarios: list[ForecastScenario],
                coupled: dict[str, PropagationResult], baseline: dict[str, PropagationResult],
                local: dict[str, NetworkPrediction], networks: list[Network],
                ctx: ProcessContext) -> Forecast: ...


registry("isolator", NetworkIsolator)
registry("network_predictor", NetworkPredictor)
registry("coupler", NetworkCoupler)
registry("unifier", ForecastUnifier)


class UnboundThesis(Exception):
    """A shocked end stayed fuzzy; the person must pick a candidate (HTTP 422)."""

    def __init__(self, unbound: list[dict]) -> None:
        super().__init__(f"thesis has unbound ends: {unbound}")
        self.unbound = unbound


def shocks_in(shared: SharedResult, network: Network) -> list[ShockInput]:
    subs = set(network.subentity_ids)
    return [s for s in shared.parsed.shocks if s.subentity_id in subs]


class PerformanceTask:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    @property
    def shared(self) -> Any:
        return self.engine.shared

    def run(self, thesis: Thesis, now: datetime) -> Forecast:
        from axelrod_wm.engine.context import GraphOverlay

        eng = self.engine
        comp = eng.components
        ctx = eng.context(learn=False, now=now)
        ctx.scope = thesis.id
        ctx.overlay = GraphOverlay(eng.wm, scope=thesis.id)
        ctx.notes["horizon_days"] = max(1, int(math.ceil(thesis.horizon_days - 1e-9)))
        ctx.notes["targets"] = list(thesis.targets)
        n_posed = eng.wm.forecast_layer.pose_counts.get(thesis.id, 0) + 1
        ctx.notes["forecast_id"] = f"FC-{thesis.id}-{n_posed}"
        wm, ltm = ctx.wm, eng.ltm
        shared = self.shared.run(thesis.event, ctx, txn=None)                           # includes the analysis
        shocks = shared.parsed.shocks
        ctx.notes["is_baseline"] = not shocks
        networks = comp["isolator"].isolate(shared, wm, ltm, ctx)                       # goal 1
        local = {n.id: comp["network_predictor"].predict(n, NetworkInputs(shocks=shocks_in(shared, n)),
                                                          shared.model, ctx)
                 for n in networks}                                                     # goal 2, isolated
        scenarios = comp["unifier"].plan(networks, wm, ltm, ctx)
        members = {s.id: [n for n in networks if n.id in s.network_ids] for s in scenarios}
        coupler = comp["coupler"]
        coupled = {s.id: coupler.couple(members[s.id], s.forced_existence, shocks, shared.model, ctx)
                   for s in scenarios}                                                  # goal 2, distributed
        baseline = {s.id: coupler.couple(members[s.id], s.forced_existence, [], shared.model, ctx)
                    for s in scenarios}                                                 # same rng keys
        for s in scenarios:
            ctx.tracer.emit(Phase.COUPLE, "couple.done", refs=[s.id] + s.network_ids, scenario_id=s.id, name=s.name,
                            weight=round(s.weight, 6))
        forecast = comp["unifier"].combine(thesis, scenarios, coupled, baseline, local, networks, ctx)  # goal 3
        # coarser targets (entities, superentities, sectors, categories) from the same scenario mixture
        from axelrod_wm.engine.performance.groups import EffectMixture, group_forecasts, movers

        mix = EffectMixture(scenarios, coupled, baseline, int(ctx.config.propagation.samples),
                            int(ctx.notes["horizon_days"]))
        groups, densities = group_forecasts(thesis, list(forecast.targets), mix, wm, ltm)
        shocked = {op.target.subentity_id for op in thesis.event.ops
                   if getattr(op, "op", "") == "change_value" and getattr(op.target, "kind", "") == "concrete"}
        forecast = forecast.model_copy(update={"groups": groups, "effect_density": densities,
                                               "movers": movers(mix, coupled, shocked)})
        if scenarios:
            from axelrod_wm.engine.regressors import emit_frames

            top = max(scenarios, key=lambda s: (s.weight, s.id))
            emit_frames(ctx, Phase.COUPLE, f"couple:{thesis.id}", coupled[top.id].minus(baseline[top.id]),
                        refs=[top.id])
        ctx.notes["coupled"] = coupled

        def ablate(scenario: ForecastScenario, key: str | None) -> dict[str, float]:
            n = max(1, int(ctx.config.propagation.samples) // 4)
            forced = dict(scenario.forced_existence)
            if key is not None:
                from axelrod_wm.core.interaction import base_interaction_id

                forced[base_interaction_id(key)] = False
            mem = members[scenario.id]
            on = coupler.couple(mem, forced, shocks, shared.model, ctx, n_samples=n)
            off = coupler.couple(mem, forced, [], shared.model, ctx, n_samples=n)
            eff = on.minus(off)
            H = eff.horizon_days
            return {t: eff.median_z(t, H) for t in forecast.targets if eff.has(t)}

        ctx.notes["ablate"] = ablate
        explanation = comp["explainer"].explain_forecast(forecast, networks, scenarios, shared, ctx)
        forecast = forecast.model_copy(update={"explanation_id": explanation.id})
        ctx.tracer.emit(Phase.EXPLAIN, "explain.stored", refs=[explanation.id, forecast.id], explanation_id=explanation.id,
                        top_paths=[p.model_dump(mode="json") for p in explanation.top_paths[:10]], text=explanation.text)
        self.update_state(thesis, forecast, explanation, ctx)      # Figure 1 "perturbs": write the forecast layer
        return self.read_out(thesis.id, ctx)                       # Figure 1 "read out": read it back

    def update_state(self, thesis: Thesis, forecast: Forecast, explanation: Any, ctx: ProcessContext) -> None:
        """Write the forecast layer through a transaction that touches only the layer (no version bump)."""
        from axelrod_wm.memory.working import ForecastStateView

        eng = self.engine
        layer = eng.wm.forecast_layer
        view = ForecastStateView(thesis_id=thesis.id, forecast=forecast, explanation=explanation,
                                 thesis=thesis.model_dump(mode="json"))
        with eng.mutator.begin(f"pose:{thesis.id}", at=ctx.now) as txn:
            if thesis.id in layer.by_thesis:
                txn.remove("forecast_layer", thesis.id)
            txn.add("forecast_layer", view)
            counts = dict(layer.pose_counts)
            counts[thesis.id] = counts.get(thesis.id, 0) + 1
            txn.set("forecast_layer.pose_counts", counts)
            txn.set("forecast_layer.order", [t for t in layer.order if t != thesis.id] + [thesis.id])
            if thesis.pinned and thesis.id not in layer.pinned:
                txn.set("forecast_layer.pinned", set(layer.pinned) | {thesis.id})

    def read_out(self, thesis_id: str, ctx: ProcessContext | None = None) -> Forecast:
        eng = self.engine
        view = eng.wm.forecast_layer.by_thesis[thesis_id]
        now = ctx.now if ctx is not None else eng.wm.clock
        if view.thesis is not None:
            eng.ledger.append(LedgerKind.THESIS, view.thesis, recorded_at=now)
        eng.ledger.append(LedgerKind.FORECAST, {"forecast": view.forecast.model_dump(mode="json"),
                                                "explanation": view.explanation.model_dump(mode="json")},
                          recorded_at=now)
        eng.tracer.emit(Phase.READ_OUT, "forecast.ready", refs=[view.forecast.id, thesis_id],
                        forecast_id=view.forecast.id, thesis_id=thesis_id)
        return view.forecast

