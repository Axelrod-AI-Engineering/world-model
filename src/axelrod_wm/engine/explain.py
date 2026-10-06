"""Explanation: the edges, paths, analogs, and scenarios responsible for a result (§8.10)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import networkx as nx
import numpy as np

from axelrod_wm.core.distributions import from_link
from axelrod_wm.core.interaction import base_interaction_id
from axelrod_wm.engine.explain_records import Explanation, PathContribution
from axelrod_wm.engine.kernels import mean_kernel_days
from axelrod_wm.engine.registry import register, registry

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.learning import FoldResult
    from axelrod_wm.engine.performance.records import Forecast, ForecastScenario, Network
    from axelrod_wm.engine.propagation import Channel
    from axelrod_wm.engine.shared import SharedResult
    from axelrod_wm.memory.frontier import FrontierResult

__all__ = ["Explanation", "PathContribution", "Explainer", "PathAttributionExplainer", "top_paths"]


class Explainer(ABC):
    @abstractmethod
    def explain_forecast(self, forecast: Forecast, networks: list[Network],
                         scenarios: list[ForecastScenario], shared: SharedResult,
                         ctx: ProcessContext) -> Explanation: ...

    @abstractmethod
    def explain_learning(self, shared: SharedResult, fold: FoldResult, frontier: FrontierResult,
                         ctx: ProcessContext) -> Explanation: ...


registry("explainer", Explainer)


def _sig(ch: Channel) -> float:
    from axelrod_wm.core.interaction import abs_mean

    return ch.existence.mean() * abs_mean(ch.dynamics.effect)


def kernel_value(ch: Channel, day: int, min_delay: int = 1) -> float:
    """The channel's step response g(day) at its mean kernel (§6.4)."""
    d, l, lam = mean_kernel_days(ch.dynamics.kernel, min_delay)
    if day < d:
        return 0.0
    if day <= d + l - 1:
        return (day - d + 1) / l
    return float(lam ** (day - (d + l - 1)))


def top_paths(channels: list[Channel], shocks: list[tuple[str, float]], targets: list[str], horizon: int,
              min_delay: int = 1, k: int = 3, max_edges: int = 5) -> list[PathContribution]:
    """For each shock and target, the k best simple paths by cost -log(significance). A path's gain is
    the product of mean effects times the kernels' values at the horizon (in days)."""
    g = nx.DiGraph()
    best_edge: dict[tuple[str, str], Channel] = {}
    for ch in channels:
        key = (ch.source_id, ch.target_id)
        if ch.forced is False:
            continue
        if key not in best_edge or _sig(ch) > _sig(best_edge[key]):
            best_edge[key] = ch
    for (s, t), ch in best_edge.items():
        g.add_edge(s, t, weight=-math.log(max(_sig(ch), 1e-6)), channel=ch)
    out: list[PathContribution] = []
    for shock_id, size in shocks:
        for tgt in targets:
            if shock_id == tgt or shock_id not in g or tgt not in g:
                continue
            found: list[PathContribution] = []
            try:
                gen = nx.shortest_simple_paths(g, shock_id, tgt, weight="weight")
                for path in gen:
                    if len(path) - 1 > max_edges:
                        break
                    gain = size
                    ids = []
                    for a, b in zip(path[:-1], path[1:]):
                        ch = g.edges[a, b]["channel"]
                        gain *= ch.dynamics.effect.mean() * kernel_value(ch, horizon, min_delay)
                        ids.append(ch.channel_key)
                    found.append(PathContribution(interaction_ids=ids, shock_id=shock_id, target_id=tgt, gain=gain,
                                                  share=0.0))
                    if len(found) >= k:
                        break
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            total = sum(abs(p.gain) for p in found)
            for p in found:
                p.share = abs(p.gain) / total if total > 0 else 0.0
            out.extend(found)
    return out


def _fmt_date(dt: Any) -> str:
    return dt.strftime("%b %Y")


@register("explainer", "path_attribution")
class PathAttributionExplainer(Explainer):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    # -- learning --------------------------------------------------------------------------
    def explain_learning(self, shared: SharedResult, fold: FoldResult, frontier: FrontierResult,
                         ctx: ProcessContext) -> Explanation:
        txn = ctx.mutator.active
        eid = txn.new_id("EX") if txn is not None else f"EX-{shared.parsed.event_id}"
        graph = ctx.wm.graph
        ranked = sorted(set(fold.effect_changes) | set(fold.existence_changes),
                        key=lambda i: (-(fold.effect_changes.get(i, 0.0) + fold.existence_changes.get(i, 0.0)), i))
        key_ints = [(i, round(fold.effect_changes.get(i, 0.0) + fold.existence_changes.get(i, 0.0), 6))
                    for i in ranked[:10]]
        parsed = shared.parsed
        paths: list[PathContribution] = []
        res = shared.analysis.result
        if res is not None and shared.analysis.expected_moves:
            targets = sorted(shared.analysis.expected_moves, key=lambda s: -abs(shared.analysis.expected_moves[s].q50))[:5]
            chans = [shared.model.channels[k] for k in sorted(shared.model.channels)]
            paths = top_paths(chans, [(s.subentity_id, s.size) for s in parsed.shocks], targets,
                              shared.analysis.horizon_days, int(ctx.config.propagation.min_delay_days))
        index: set[str] = set()
        for iid, _ in key_ints:
            inter = graph.interactions.get(iid)
            if inter is None:
                continue
            if inter.generalization_id:
                index.add(inter.generalization_id)
            for sid in (inter.source_id, inter.target_id):
                sub = graph.subentities.get(sid)
                if sub is not None and graph.entities[sub.entity_id].generalization_id:
                    index.add(graph.entities[sub.entity_id].generalization_id)
        for e in parsed.touched_entity_ids:
            ent = graph.entities.get(e)
            if ent is not None and ent.generalization_id:
                index.add(ent.generalization_id)
        for s in shared.recall.superentities:
            index.add(s.pattern_id)
        parts = [f"{parsed.event_id}"]
        if parsed.event_type:
            parts[0] += f" ({parsed.event_type})"
        if parsed.shocks:
            parts.append("shocks " + ", ".join(f"{s.subentity_id} {s.size:+.2f} sd" for s in parsed.shocks[:3]))
        if parsed.observations:
            parts.append(f"{len(parsed.observations)} observations")
        if shared.analysis.expected_moves:
            top = sorted(shared.analysis.expected_moves.items(), key=lambda kv: -abs(kv[1].q50))[:3]
            parts.append("expected " + ", ".join(f"{k} {v.q50:+.2f} sd" for k, v in top))
        if key_ints:
            parts.append("largest updates: " + ", ".join(i for i, _ in key_ints[:3]))
        if frontier.logged or frontier.proposals:
            parts.append(f"frontier: {len(frontier.logged)} logged, {len(frontier.proposals)} proposed")
        touched = set(parsed.touched_entity_ids)
        pending = [pid for pid, p in sorted(ctx.wm.pending_refinements.items())
                   if touched & {c.split(".")[0] for c in p.candidates}]
        return Explanation(
            id=eid, subject_kind="learning", subject_id=parsed.event_id, state_version=ctx.state_version,
            created_at=ctx.now, key_interactions=key_ints, top_paths=paths,
            analogs=[(a.episode_id, round(a.attention, 6)) for a in shared.recall.analogs], networks=[], scenarios=[],
            assumptions=[], notes=list(shared.model.notes), text="; ".join(parts) + ".", index_keys=index,
            frontier_changes=list(frontier.logged) + list(frontier.tested) + list(frontier.proposals),
            pending_touched=pending)

    # -- forecasts -------------------------------------------------------------------------
    def explain_forecast(self, forecast: Forecast, networks: list[Network], scenarios: list[ForecastScenario],
                         shared: SharedResult, ctx: ProcessContext) -> Explanation:
        graph = ctx.wm.graph
        H = forecast.horizon_days
        top = max(scenarios, key=lambda s: (s.weight, s.id)) if scenarios else None
        coupled = ctx.notes.get("coupled", {})
        targets = [t for t in forecast.targets if t in forecast.effect_summary]
        ranked_targets = sorted(targets, key=lambda t: -abs(forecast.effect_summary[t][-1].q50))
        key_ints: list[tuple[str, float]] = []
        if top is not None and top.id in coupled and coupled[top.id].channel_contrib is not None:
            res = coupled[top.id]
            means = {k: float(np.mean(np.abs(res.channel_contrib[:, c, H]))) for k, c in res.channel_index.items()}
            cands = sorted(means, key=lambda k: (-means[k], k))[:15]
            ablate = ctx.notes.get("ablate")
            if ablate is not None and cands and ranked_targets:
                base_med = ablate(top, None)
                effects = []
                for key in cands:
                    med = ablate(top, key)
                    delta = sum(abs(abs(base_med.get(t, 0.0)) - abs(med.get(t, 0.0))) for t in ranked_targets)
                    effects.append((base_interaction_id(key), key, delta))
                effects.sort(key=lambda x: (-x[2], x[1]))
                seen: set[str] = set()
                for iid, _key, d in effects:
                    if iid not in seen:
                        seen.add(iid)
                        key_ints.append((iid, round(d, 6)))
            else:
                key_ints = [(base_interaction_id(k), round(means[k], 6)) for k in cands]
        chans = []
        seen_keys: set[str] = set()
        member_ids = set(top.network_ids) if top is not None else {n.id for n in networks}
        for n in networks:
            if n.id not in member_ids:
                continue
            for ch in n.channels:
                if ch.channel_key not in seen_keys:
                    seen_keys.add(ch.channel_key)
                    forced = top.forced_existence.get(base_interaction_id(ch.channel_key)) if top else None
                    chans.append(ch.model_copy(update={"forced": forced if forced is not None else ch.forced}))
        shocks = [(s.subentity_id, s.size) for s in shared.parsed.shocks if not s.intervention]
        paths = top_paths(chans, shocks, ranked_targets[:5], H, int(ctx.config.propagation.min_delay_days))
        nets_share: list[tuple[str, float]] = []
        if ranked_targets and ranked_targets[0] in forecast.decomposition:
            dec = {k: v for k, v in forecast.decomposition[ranked_targets[0]].items() if k != "coupling"}
            tot = sum(abs(v) for v in dec.values())
            nets_share = [(k, round(abs(v) / tot, 6) if tot > 0 else 0.0) for k, v in sorted(dec.items())]
        assumptions = []
        for s in scenarios:
            for hid, on in sorted(s.branched_hypothesis_ids.items()):
                assumptions.append(f"{s.name}: {hid} {'holds' if on else 'does not hold'}")
        for n in networks:
            for aid in n.forced_absent:
                assumptions.append(f"{n.name or n.id} says {aid} is absent")
        index: set[str] = set()
        for iid, _ in key_ints:
            inter = graph.interactions.get(iid)
            if inter is None:
                continue
            if inter.generalization_id:
                index.add(inter.generalization_id)
            for sid in (inter.source_id, inter.target_id):
                sub = graph.subentities.get(sid)
                if sub is not None and graph.entities[sub.entity_id].generalization_id:
                    index.add(graph.entities[sub.entity_id].generalization_id)
        for n in networks:
            if n.pattern_id:
                index.add(n.pattern_id)
        text = self._forecast_text(forecast, shared, ranked_targets, paths, scenarios, key_ints, ctx)
        return Explanation(
            id=f"EX-{forecast.id}", subject_kind="forecast", subject_id=forecast.id, state_version=forecast.based_on_version,
            created_at=ctx.now, key_interactions=key_ints, top_paths=paths,
            analogs=[(a.episode_id, round(a.attention, 6)) for a in shared.recall.analogs], networks=nets_share,
            scenarios=[(s.name, round(s.weight, 6)) for s in scenarios], assumptions=assumptions,
            notes=list(shared.model.notes), text=text, index_keys=index)

    def _forecast_text(self, forecast: Forecast, shared: SharedResult, targets: list[str],
                       paths: list[PathContribution], scenarios: list[ForecastScenario],
                       key_ints: list[tuple[str, float]], ctx: ProcessContext) -> str:
        graph = ctx.wm.graph
        if not targets:
            return "No subentity moves by 0.1 standard units or more at the horizon."
        shocks = [s for s in shared.parsed.shocks if not s.intervention]
        # DECISION: the lead sentence describes the largest move the shocks cause elsewhere; a shocked
        # subentity's own move restates the thesis
        shocked = {s.subentity_id for s in shocks}
        t = next((x for x in targets if x not in shocked), targets[0])
        sub = graph.subentities.get(t)
        eff = forecast.effect_summary[t][-1]
        end = forecast.created_at
        from datetime import timedelta

        end = end + timedelta(days=forecast.horizon_days)
        if sub is not None:
            base = sub.anchor + sub.scale * (forecast.z_summary[t][-1].q50 - eff.q50) if t in forecast.z_summary else sub.anchor
            native = lambda dz: float(from_link(base + sub.scale * dz, sub.posterior.link) - from_link(base, sub.posterior.link))  # noqa: E731
            move = f"{native(eff.q50):+.2f} {sub.unit} ({native(eff.q10):+.2f} to {native(eff.q90):+.2f})"
            name = sub.name
        else:
            move = f"{eff.q50:+.2f} sd"
            name = t
        lead = "The baseline" if not shocks else ", ".join(
            f"{graph.subentities[s.subentity_id].name if s.subentity_id in graph.subentities else s.subentity_id} "
            f"{s.size:+.1f} sd" for s in shocks[:2])
        text = f"{lead} moves {name} by {move} by {_fmt_date(end)}"
        tp = [p for p in paths if p.target_id == t]
        if tp:
            best = max(tp, key=lambda p: p.share)
            text += f", mostly through {' → '.join(base_interaction_id(i) for i in best.interaction_ids)} ({best.share:.0%})"
        elif key_ints:
            text += f", mostly through {key_ints[0][0]}"
        text += "."
        if len(scenarios) > 1:
            s = max(scenarios, key=lambda x: x.weight)
            text += f" The leading scenario, {s.name} ({s.weight:.0%}), is one of {len(scenarios)}."
        return text
