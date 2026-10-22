"""The inference task (§8.9, D1, D2, D5), in the seven stages of flows/inference.py, each answering one question:

1. Pose a thesis (ThesisService, before this task): what is asked?
2. Isolate: what can the shock reach? (isolator, plus the context network)
3. Isolated prediction: how does each network respond alone? (network_predictor)
4. Distributed prediction: how do the networks move together? Scenarios are formed and weighed once
   (unifier.plan: rival_detector, scenario_weighter), then each is coupled (coupler).
5. Unify: one forecast, the scenarios mixed by those weights (unifier.combine).
6. Read out: what moves, when, by which path, and why (groups, constraints, transmission, explainer).
7. Evaluate (evaluation/, after the horizon): did it come true?
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.dynamics.propagation import PropagationResult, ShockInput
from axelrod_wm.engine.registry import registry
from axelrod_wm.inference.records import (
    Forecast,
    ForecastScenario,
    Network,
    NetworkInputs,
    NetworkKind,
    NetworkPrediction,
    NetworkSummary,
)
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import PrefilledModel
    from axelrod_wm.events.thesis import Thesis
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.shared.process import SharedResult

__all__ = ["NetworkKind", "Network", "NetworkInputs", "NetworkPrediction", "ForecastScenario", "NetworkSummary",
           "Forecast", "NetworkIsolator", "NetworkPredictor", "NetworkCoupler", "ForecastUnifier", "InferenceTask",
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


class InferenceTask:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    @property
    def shared(self) -> Any:
        return self.engine.shared

    def run(self, thesis: Thesis, now: datetime, watch: list[str] | None = None) -> Forecast:
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
        # 2 · Isolate: what can the shock reach?
        networks = comp["isolator"].isolate(shared, wm, ltm, ctx)
        if shocks:                                                                      # the context layer
            from axelrod_wm.inference.isolate import watch_network

            extra = watch_network(shared, networks, list(watch or []), wm, ctx, k=len(networks) + 1,
                                  targets=list(thesis.targets))
            if extra is not None and extra.id not in {n.id for n in networks}:
                networks = [*networks, extra]
        # 3 · Isolated prediction: how does each network respond alone?
        local = {n.id: comp["network_predictor"].predict(n, NetworkInputs(shocks=shocks_in(shared, n)),
                                                          shared.model, ctx)
                 for n in networks}
        # 4 · Distributed prediction: scenarios formed and weighed once, then each coupled (± the shock, same draws)
        scenarios = comp["unifier"].plan(networks, wm, ltm, ctx)
        members = {s.id: [n for n in networks if n.id in s.network_ids] for s in scenarios}
        coupler = comp["coupler"]
        coupled = {s.id: coupler.couple(members[s.id], s.forced_existence, shocks, shared.model, ctx)
                   for s in scenarios}
        baseline = {s.id: coupler.couple(members[s.id], s.forced_existence, [], shared.model, ctx)
                    for s in scenarios}                                                 # same rng keys
        for s in scenarios:
            ctx.tracer.emit(Phase.COUPLE, "couple.done", refs=[s.id] + s.network_ids, scenario_id=s.id, name=s.name,
                            weight=round(s.weight, 6))
        # 5 · Unify: one forecast, the scenarios mixed by their weights
        forecast = comp["unifier"].combine(thesis, scenarios, coupled, baseline, local, networks, ctx)
        # 6 · Read out: groups, binding constraints, transmission paths, and the explanation
        # coarser targets (entities, superentities, sectors, categories) from the same scenario mixture
        from axelrod_wm.inference.groups import EffectMixture, group_forecasts, movers

        mix = EffectMixture(scenarios, coupled, baseline, int(ctx.config.propagation.samples),
                            int(ctx.notes["horizon_days"]))
        groups, densities, splits = group_forecasts(thesis, list(forecast.targets), mix, wm, ltm)
        shocked = {op.target.subentity_id for op in thesis.event.ops
                   if getattr(op, "op", "") == "change_value" and getattr(op.target, "kind", "") == "concrete"}
        # economic constraints (addition): how often a soft bound bent a value, weighted by scenario
        # DECISION: only what the question adds counts. A value that already sits near its bound bends in
        # the baseline too, so a binding is reported for a value the shock reaches, net of the baseline's.
        hits: dict[str, float] = {}
        for s in scenarios:
            off = baseline[s.id].bound_hits
            for sid, share in coupled[s.id].bound_hits.items():
                hits[sid] = hits.get(sid, 0.0) + s.weight * max(0.0, share - off.get(sid, 0.0))
        # transmission (addition): every value the shock reaches, its order, and its main path
        from axelrod_wm.inference.transmission import transmission_map

        chans = []
        if scenarios:
            top_s = max(scenarios, key=lambda s: (s.weight, s.id))
            chans = list(coupled[top_s.id].channels)
        trans = transmission_map(sorted({s.subentity_id for s in shocks}), chans, mix.effect,
                                 int(ctx.notes["horizon_days"]), int(ctx.config.propagation.min_delay_days))
        from axelrod_wm.inference.paths import source_of

        grid_src = source_of(sorted({s.subentity_id for s in shocks}), chans, mix.effect, int(ctx.notes["horizon_days"]),
                             trans, int(ctx.config.propagation.min_delay_days),
                             asked=frozenset(forecast.targets)) if chans else None
        reached = {e.subentity_id for e in trans} | {s.subentity_id for s in shocks}
        contrib, live, absent = channel_contributions(scenarios, coupled, baseline)
        coverage = forecast_coverage(wm.graph, sorted({s.subentity_id for s in shocks}), reached, list(forecast.targets),
                                     contrib, live, absent)
        binding ={sid: round(v, 4) for sid, v in sorted(hits.items()) if v >= 0.05 and sid in reached}
        # the scenario table (Oct 15): bull, base, and bear bands of the draws, read for the book (the watchlist, else
        # the names the thesis asks about)
        from axelrod_wm.inference.scenario_table import build_scenario_table

        book = [e for e in (watch or []) if e in wm.graph.entities] or sorted(
            {wm.graph.subentities[t].entity_id for t in forecast.targets if t in wm.graph.subentities})
        table = build_scenario_table(mix, scenarios, book, wm.graph, wm.hypotheses, int(ctx.notes["horizon_days"]))
        forecast = forecast.model_copy(update={"groups": groups, "effect_density": densities, "split": splits,
                                               "movers": movers(mix, coupled, shocked), "transmission": trans,
                                               "shocked": sorted({s.subentity_id for s in shocks}),
                                               "constraints_binding": binding, "paths": grid_src,
                                               "scenario_table": table,
                                               "unquantified": unquantified_links(wm.graph, reached, trans),
                                               "coverage": coverage})
        if scenarios:
            from axelrod_wm.dynamics.regressors import emit_frames

            top = max(scenarios, key=lambda s: (s.weight, s.id))
            emit_frames(ctx, Phase.COUPLE, f"couple:{thesis.id}", coupled[top.id].minus(baseline[top.id]),
                        refs=[top.id])
        ctx.notes["coupled"] = coupled

        def ablate(scenario: ForecastScenario, key: str | None) -> dict[str, float]:
            n = max(1, int(ctx.config.propagation.samples) // 4)
            forced = dict(scenario.forced_existence)
            if key is not None:
                from axelrod_wm.model.interaction import base_interaction_id

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


def unquantified_links(graph: Any, reached: set[str], trans: list[Any]) -> list[dict]:
    """The uncalibrated links a forecast's shock reaches (Oct 17): each one's source moves, but its size is unknown,
    so it adds nothing here, and what lies downstream of it (by any link) is incomplete in that direction."""
    peak = {t.subentity_id: float(t.peak) for t in trans}
    out_of: dict[str, list[str]] = {}
    for i in graph.active_interactions():
        out_of.setdefault(i.source_id, []).append(i.target_id)
    rows = []
    for i in graph.active_interactions():
        if i.quantified or i.source_id not in reached:
            continue
        down, stack = set(), [i.target_id]
        while stack:
            v = stack.pop()
            if v not in down:
                down.add(v)
                stack.extend(out_of.get(v, []))
        rows.append({"interaction_id": i.id, "source": i.source_id, "target": i.target_id,
                     "sign": i.transition.sign if i.transition is not None else None,
                     "mechanism": i.transition.mechanism if i.transition is not None else i.label,
                     "source_peak": round(peak.get(i.source_id, 0.0), 4), "downstream": sorted(down)})
    return rows


def channel_contributions(scenarios: list[Any], coupled: dict[str, Any],
                          baseline: dict[str, Any]) -> tuple[dict[str, float], set[str], set[str]]:
    """Per link (interaction id, both channels of a two-way link together): its contribution to its target at the
    horizon, in target sd (the median over draws of what the channel added with the shock minus without it, weighted
    by scenario); the links that ran in at least one scenario; and the links every scenario that held them forced off."""
    from axelrod_wm.model.interaction import base_interaction_id

    contrib: dict[str, float] = {}
    live: set[str] = set()
    held: set[str] = set()
    for s in scenarios:
        on, off = coupled[s.id], baseline[s.id]
        H = on.horizon_days
        for ch in on.channels:
            iid = base_interaction_id(ch.channel_key)
            held.add(iid)
            if ch.forced is False:
                continue
            live.add(iid)
            d = on.contrib_of(ch.channel_key)[:, H] - off.contrib_of(ch.channel_key)[:, H]
            contrib[iid] = contrib.get(iid, 0.0) + s.weight * float(np.median(d))
    return contrib, live, held - live


ROUTE_DEPTH = 6          # routes from a shock to a target are counted up to this many links (transmission's max order)
ROUTE_BUDGET = 20000     # links walked in all; a denser graph reports its route counts as truncated


def _entity(graph: Any, sid: str) -> str | None:
    sub = graph.subentities.get(sid)
    return sub.entity_id if sub is not None else None


def forecast_coverage(graph: Any, shocked: list[str], reached: set[str], targets: list[str], contrib: dict[str, float],
                      live: set[str], absent: set[str], max_depth: int = ROUTE_DEPTH,
                      budget: int = ROUTE_BUDGET) -> dict:
    """A forecast's calculation coverage (Oct 18): what its numbers are made of, and what they leave out.

    - `contributed`: the quantified links out of a reached value that ran in the forecast, each with its contribution
      at the horizon (target sd, `channel_contributions`), largest first.
    - `excluded`: the links out of a reached value that carry no size here, with why: `uncalibrated` (represented, sign
      and mechanism known, size unknown), `absent_in_every_scenario` (every scenario forced it off), or
      `outside_the_forecast_networks` (quantified, but no network the forecast isolated holds it).
    - `blocking_inputs`: the unresolved inputs of the excluded links' transitions, with their status.
    - `targets`: per target, the routes from a shocked value to it (simple paths of at most `max_depth` active links,
      calibrated or not), how many are fully quantified (every link contributed), and that share (None with no route).
      Oct 18: and the company's own construction apart from the routes (a high share must not hide a path whose own steps
      are all unsized): `own_steps` (the distinct links inside the target's company on any route), how many contributed,
      and that share; and the fully quantified routes split into those through at least one own step
      (`quantified_routes_through_own_steps`) and those quantified only through macro or summary links
      (`quantified_routes_through_summary_links_only`).
    """
    from axelrod_wm.context.construction import input_needs

    active = sorted(graph.active_interactions(), key=lambda i: i.id)
    contributed, excluded = [], []
    for i in active:
        if i.source_id not in reached:
            continue
        if i.quantified and i.id in live:
            contributed.append({"interaction_id": i.id, "source": i.source_id, "target": i.target_id,
                                "edge_type": str(i.edge_type), "contribution_sd": round(contrib.get(i.id, 0.0), 4)})
            continue
        tr = i.transition
        reason = ("uncalibrated" if not i.quantified else "absent_in_every_scenario" if i.id in absent
                  else "outside_the_forecast_networks")
        signed = i.quantified or (tr is not None and tr.sign is not None)
        excluded.append({"interaction_id": i.id, "source": i.source_id, "target": i.target_id, "reason": reason,
                         "sign": ("+" if i.polarity() > 0 else "-") if signed else None,
                         "mechanism": tr.mechanism if tr is not None else i.label,
                         "unresolved": [u.input for u in tr.unresolved] if tr is not None else []})
    contributed.sort(key=lambda r: (-abs(r["contribution_sd"]), r["interaction_id"]))
    blocking = input_needs([(r["interaction_id"], graph.interactions[r["interaction_id"]].transition) for r in excluded])

    ok = {r["interaction_id"] for r in contributed}
    out_of: dict[str, list[Any]] = {}
    for i in active:
        out_of.setdefault(i.source_id, []).append(i)
    counts = {t: [0, 0, 0] for t in targets}           # routes, fully quantified, fully quantified through own steps
    owner = {t: graph.subentities[t].entity_id if t in graph.subentities else None for t in targets}
    own_steps: dict[str, set[str]] = {t: set() for t in targets}
    walked = 0
    truncated = False

    def walk(v: str, seen: frozenset[str], quantified: bool, depth: int, route: tuple[Any, ...]) -> None:
        nonlocal walked, truncated
        for i in out_of.get(v, []):
            if i.target_id in seen:
                continue
            if walked >= budget:
                truncated = True
                return
            walked += 1
            q = quantified and i.id in ok
            here = route + (i,)
            t = i.target_id
            if t in counts:
                own = [x.id for x in here if _entity(graph, x.source_id) == owner[t] == _entity(graph, x.target_id)]
                own_steps[t].update(own)
                counts[t][0] += 1
                counts[t][1] += int(q)
                counts[t][2] += int(q and bool(own))
            if depth + 1 < max_depth:
                walk(t, seen | {t}, q, depth + 1, here)

    for s in shocked:
        walk(s, frozenset({s}), True, 0, ())
    rows = []
    for t, (n, q, qo) in counts.items():
        own = own_steps[t]
        own_q = len(own & ok)
        rows.append({"target": t, "routes": n, "quantified_routes": q, "share_quantified": round(q / n, 4) if n else None,
                     "quantified_routes_through_own_steps": qo, "quantified_routes_through_summary_links_only": q - qo,
                     "own_steps": len(own), "own_steps_quantified": own_q,
                     "share_own_steps_quantified": round(own_q / len(own), 4) if own else None,
                     "own_steps_unquantified": sorted(own - ok), "truncated": truncated})
    reasons = sorted({r["reason"] for r in excluded})
    return {"contributed": contributed, "excluded": excluded, "blocking_inputs": blocking, "targets": rows,
            "summary": {"contributed": len(contributed), "excluded": len(excluded),
                        "excluded_by_reason": {k: sum(1 for r in excluded if r["reason"] == k) for k in reasons},
                        "blocking_inputs": len(blocking)},
            "max_route_depth": max_depth}
