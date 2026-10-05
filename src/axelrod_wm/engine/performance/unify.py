"""Unify network predictions into one forecast (goal 3; §8.9.4, D2): add channels, mix rivals."""

from __future__ import annotations

import itertools
import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.core.distributions import from_link, summarize_samples
from axelrod_wm.core.hypothesis import HypothesisKind, HypothesisStatus
from axelrod_wm.core.interaction import base_interaction_id
from axelrod_wm.engine.performance.records import Forecast, ForecastScenario, NetworkSummary
from axelrod_wm.engine.performance.task import ForecastUnifier
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.engine.regressors import level_noise_of, obs_noise_of
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.performance.records import Network, NetworkPrediction
    from axelrod_wm.engine.propagation import PropagationResult
    from axelrod_wm.events.thesis import Thesis
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


class RivalDetector(ABC):
    @abstractmethod
    def groups(self, networks: list[Network], ltm: LongTermMemory) -> list[list[str]]:
        """Groups of rival network ids."""


class ScenarioWeighter(ABC):
    @abstractmethod
    def weights(self, scenarios: list[ForecastScenario], networks: list[Network], wm: WorkingMemory,
                ltm: LongTermMemory, ctx: ProcessContext) -> list[float]:
        """Unnormalized weights."""


registry("rival_detector", RivalDetector)
registry("scenario_weighter", ScenarioWeighter)


@register("rival_detector", "pattern_and_sign")
class PatternAndSignRivalDetector(RivalDetector):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    def _rivals(self, a: Network, b: Network, ltm: LongTermMemory) -> bool:
        pa = ltm.patterns.patterns.get(a.pattern_id) if a.pattern_id else None
        pb = ltm.patterns.patterns.get(b.pattern_id) if b.pattern_id else None
        if pa is not None and pb is not None and (pb.id in pa.rival_ids or pa.id in pb.rival_ids):
            return True
        sign_a = {(c.source_id, c.target_id): np.sign(c.dynamics.effect.mean()) for c in a.channels}
        for c in b.channels:
            k = (c.source_id, c.target_id)
            if k in sign_a and sign_a[k] * np.sign(c.dynamics.effect.mean()) < 0:
                return True
        if set(a.forced_present) & set(b.forced_absent) or set(b.forced_present) & set(a.forced_absent):
            return True
        return False

    def groups(self, networks: list[Network], ltm: LongTermMemory) -> list[list[str]]:
        parent = {n.id: n.id for n in networks}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i, a in enumerate(networks):
            for b in networks[i + 1:]:
                if self._rivals(a, b, ltm):
                    ra, rb = find(a.id), find(b.id)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
        groups: dict[str, list[str]] = {}
        for n in networks:
            groups.setdefault(find(n.id), []).append(n.id)
        return [sorted(g) for _, g in sorted(groups.items()) if len(g) >= 2]


def network_log_fit(net: Network, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> float:
    """-0.5 * sum e^2 over standardized one-step errors of the network's channel targets in the last
    fit_window_steps, recomputed with the network's dynamics and forced edges."""
    from axelrod_wm.engine.kernel_update import target_fit_sse
    from axelrod_wm.engine.regressors import regressor_cache

    dev = wm.deviations
    now_step = dev.step_of(ctx.now)
    window = int(ctx.config.unify.fit_window_steps)
    overrides: dict[str, tuple[float, bool]] = {}
    absent = set(net.forced_absent)
    for ch in net.channels:
        overrides[ch.channel_key] = (ch.dynamics.effect.mean(), ch.interaction_id not in absent)
    cache = regressor_cache(wm, ctx)
    total = 0.0
    for tgt in sorted({ch.target_id for ch in net.channels}):
        sub = wm.graph.subentities.get(tgt)
        if sub is None:
            continue
        steps = [s for s in sorted(dev.z.get(tgt, {})) if now_step - window < s <= now_step]
        sse, n = target_fit_sse(wm, ctx, tgt, steps, None, cache, overrides)
        if n == 0:
            continue
        sigma2 = level_noise_of(sub, ctx) ** 2 + 2 * obs_noise_of(sub, wm, ltm) ** 2
        total += -0.5 * sse / max(sigma2, 1e-9)
    return total


@register("scenario_weighter", "support_fit_reliability")
class SupportFitReliabilityWeighter(ScenarioWeighter):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    def weights(self, scenarios: list[ForecastScenario], networks: list[Network], wm: WorkingMemory,
                ltm: LongTermMemory, ctx: ProcessContext) -> list[float]:
        by_id = {n.id: n for n in networks}
        groups: dict[str, list[str]] = ctx.notes.get("rival_groups", {})
        prior, fit, rel = {}, {}, {}
        for gkey, members in groups.items():
            sup = {}
            logf = {}
            for nid in members:
                n = by_id[nid]
                p = ltm.patterns.patterns.get(n.pattern_id) if n.pattern_id else None
                sup[nid] = (p.support if p is not None else 0.0) + 1.0
                logf[nid] = network_log_fit(n, wm, ltm, ctx)
                rel[nid] = ltm.reliability.mean(n.pattern_id) if n.pattern_id else 0.5
            tot = sum(sup.values())
            mx = max(logf.values())
            lse = mx + math.log(sum(math.exp(v - mx) for v in logf.values()))
            for nid in members:
                prior[nid] = sup[nid] / tot
                fit[nid] = math.exp(logf[nid] - lse)
        ctx.notes["weight_terms"] = {nid: {"prior": prior[nid], "fit": fit[nid], "reliability": rel[nid]}
                                     for nid in prior}
        out = []
        for s in scenarios:
            w = 1.0
            for _gkey, nid in s.rival_choices.items():
                w *= prior.get(nid, 1.0) * fit.get(nid, 1.0) * rel.get(nid, 0.5)
            for hid, on in s.branched_hypothesis_ids.items():
                h = wm.hypotheses.get(hid)
                p = h.probability if h is not None else 0.5
                w *= p if on else (1.0 - p)
            out.append(w)
        return out


@register("scenario_weighter", "uniform")
class UniformWeighter(ScenarioWeighter):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    def weights(self, scenarios, networks, wm, ltm, ctx) -> list[float]:  # type: ignore[override]
        return [1.0 for _ in scenarios]


def largest_remainder(total: int, weights: list[float]) -> list[int]:
    raw = [total * w for w in weights]
    counts = [int(math.floor(r)) for r in raw]
    for i, w in enumerate(weights):
        if w >= 0.01 and counts[i] == 0:
            counts[i] = 1
    rest = total - sum(counts)
    order = sorted(range(len(weights)), key=lambda i: (-(raw[i] - math.floor(raw[i])), i))
    k = 0
    while rest > 0 and order:
        counts[order[k % len(order)]] += 1
        rest -= 1
        k += 1
    while rest < 0:
        i = max(range(len(counts)), key=lambda j: (counts[j], -j))
        counts[i] -= 1
        rest += 1
    return counts


@register("unifier", "channels_and_rivals")
class ChannelsAndRivalsUnifier(ForecastUnifier):
    def __init__(self, config: Any = None, rival_detector: RivalDetector | None = None,
                 scenario_weighter: ScenarioWeighter | None = None) -> None:
        self.config = config
        self.detector = rival_detector or PatternAndSignRivalDetector(config)
        self.weighter = scenario_weighter or SupportFitReliabilityWeighter(config)

    def _branches(self, networks: list[Network], wm: WorkingMemory, ctx: ProcessContext) -> list[tuple[str, str]]:
        cfg = ctx.config.unify
        lo, hi = cfg.branch_probability_range
        inside = {c.interaction_id for n in networks for c in n.channels}
        out = []
        for hid in sorted(wm.hypotheses):
            h = wm.hypotheses[hid]
            if h.status != HypothesisStatus.OPEN or h.kind == HypothesisKind.ENTITY_DECISION:
                continue
            iid = h.interaction_id
            if iid is None and h.source_id and h.target_id:
                ids = wm.graph.interaction_between(h.source_id, h.target_id)
                iid = ids[0] if ids else None
            if iid is None or iid not in inside:
                continue
            if h.current_value(ctx.now) >= float(cfg.branch_hypothesis_min_voi) and lo <= h.probability <= hi:
                out.append((hid, iid))
        return out

    def plan(self, networks: list[Network], wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext) -> list[ForecastScenario]:
        cfg = ctx.config.unify
        by_id = {n.id: n for n in networks}
        groups = self.detector.groups(networks, ltm)
        gmap = {f"G{k + 1}": g for k, g in enumerate(groups)}
        ctx.notes["rival_groups"] = gmap
        in_group = {nid for g in groups for nid in g}
        common = [n.id for n in networks if n.id not in in_group]
        branches = self._branches(networks, wm, ctx)
        axes: list[list[tuple[str, str, Any]]] = []
        for gkey, g in gmap.items():
            axes.append([("rival", gkey, nid) for nid in g])
        for hid, iid in branches:
            axes.append([("branch", hid, (iid, True)), ("branch", hid, (iid, False))])
        scenarios: list[ForecastScenario] = []
        for k, combo in enumerate(itertools.product(*axes) if axes else [()], start=1):
            nets = list(common)
            forced: dict[str, bool] = {}
            choices: dict[str, str] = {}
            branched: dict[str, bool] = {}
            names = []
            for kind, key, val in combo:
                if kind == "rival":
                    n = by_id[val]
                    nets.append(val)
                    choices[key] = val
                    for iid in n.forced_present:
                        forced[iid] = True
                    for iid in n.forced_absent:
                        forced[iid] = False
                    names.append(n.name or n.id)
                else:
                    iid, on = val
                    forced[iid] = on
                    branched[key] = on
                    names.append(f"{key} {'present' if on else 'absent'}")
            scenarios.append(ForecastScenario(id=f"SC-{ctx.scope}-{k}", name=" + ".join(names) or "All networks",
                                              weight=0.0, network_ids=[n.id for n in networks if n.id in set(nets)],
                                              forced_existence=forced, branched_hypothesis_ids=branched,
                                              rival_choices=choices))
        raw = self.weighter.weights(scenarios, networks, wm, ltm, ctx)
        total = sum(raw)
        weights = [w / total for w in raw] if total > 0 else [1.0 / len(raw)] * len(raw)
        order = sorted(range(len(scenarios)), key=lambda i: (-weights[i], scenarios[i].id))
        keep = order[: int(cfg.max_scenarios)]
        kept_mass = sum(weights[i] for i in keep)
        out = []
        for i in sorted(keep):
            out.append(scenarios[i].model_copy(update={"weight": weights[i] / kept_mass if kept_mass > 0 else 0.0}))
        ctx.notes["dropped_mass"] = 1.0 - kept_mass
        ctx.tracer.emit(Phase.UNIFY, "unify.scenarios", refs=[s.id for s in out],
                        scenarios=[{"id": s.id, "name": s.name, "weight": round(s.weight, 6),
                                    "networks": s.network_ids, "forced": s.forced_existence} for s in out],
                        dropped_mass=round(ctx.notes["dropped_mass"], 6), weight_terms=ctx.notes.get("weight_terms", {}))
        return out

    # -- combine ---------------------------------------------------------------------------
    def combine(self, thesis: Thesis, scenarios: list[ForecastScenario], coupled: dict[str, PropagationResult],
                baseline: dict[str, PropagationResult], local: dict[str, NetworkPrediction], networks: list[Network],
                ctx: ProcessContext) -> Forecast:
        wm = ctx.wm
        graph = wm.graph
        S = int(ctx.config.propagation.samples)
        H = int(ctx.notes.get("horizon_steps", ctx.config.time.horizon_steps))
        dev = wm.deviations
        step_now = dev.step_of(ctx.now)
        weights = [s.weight for s in scenarios]
        counts = largest_remainder(S, weights) if scenarios else []

        def levels(res: PropagationResult | None, sid: str, n: int) -> np.ndarray:
            if res is not None and res.has(sid):
                z = res.z_of(sid)[:n]
                if z.shape[1] < H + 1:
                    z = np.pad(z, ((0, 0), (0, H + 1 - z.shape[1])), mode="edge")
                return z[:, : H + 1]
            z0 = dev.z_at(sid, step_now) or 0.0
            return np.full((n, H + 1), z0)

        def mixture(sid: str) -> tuple[np.ndarray, np.ndarray]:
            lv, ef = [], []
            for s, n in zip(scenarios, counts):
                if n <= 0:
                    continue
                n = min(n, coupled[s.id].n_samples)
                lvl = levels(coupled[s.id], sid, n)
                base = levels(baseline[s.id], sid, n)
                lv.append(lvl)
                ef.append(lvl - base)
            if not lv:
                z0 = dev.z_at(sid, step_now) or 0.0
                return np.full((1, H + 1), z0), np.zeros((1, H + 1))
            return np.concatenate(lv, axis=0), np.concatenate(ef, axis=0)

        candidates = sorted({sid for r in coupled.values() for sid in r.subentity_index})
        effects_at_h: dict[str, float] = {}
        cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for sid in candidates:
            lv, ef = mixture(sid)
            cache[sid] = (lv, ef)
            effects_at_h[sid] = float(np.median(ef[:, H]))
        if thesis.targets:
            targets = [t for t in thesis.targets if t in graph.subentities]
        else:
            targets = [sid for sid in candidates if abs(effects_at_h.get(sid, 0.0)) >= 0.1]
            for sid in sorted(ctx.config.hypotheses.watch_list):
                if sid in graph.subentities and sid not in targets:
                    targets.append(sid)
        summary, effect_summary, z_summary = {}, {}, {}
        for sid in targets:
            lv, ef = cache.get(sid) or mixture(sid)
            sub = graph.subentities[sid]
            native = np.asarray(from_link(sub.anchor + sub.scale * lv, sub.posterior.link), dtype=float)
            summary[sid] = [summarize_samples(native[:, t]) for t in range(H + 1)]
            effect_summary[sid] = [summarize_samples(ef[:, t]) for t in range(H + 1)]
            z_summary[sid] = [summarize_samples(lv[:, t]) for t in range(H + 1)]
        new_scen = []
        for s in scenarios:
            ssum, esum = {}, {}
            for sid in targets:
                sub = graph.subentities[sid]
                lvl = levels(coupled[s.id], sid, coupled[s.id].n_samples)
                base = levels(baseline[s.id], sid, baseline[s.id].n_samples)
                native = np.asarray(from_link(sub.anchor + sub.scale * lvl, sub.posterior.link), dtype=float)
                ssum[sid] = [summarize_samples(native[:, t]) for t in range(H + 1)]
                esum[sid] = [summarize_samples((lvl - base)[:, t]) for t in range(H + 1)]
            new_scen.append(s.model_copy(update={"summary": ssum, "effect_summary": esum}))
        # decomposition in the top-weighted scenario
        isolated: dict[str, dict[str, Any]] = {}
        decomposition: dict[str, dict[str, float]] = {}
        top = max(scenarios, key=lambda s: (s.weight, s.id)) if scenarios else None
        for n in networks:
            pred = local.get(n.id)
            if pred is None:
                continue
            isolated[n.id] = {sid: summarize_samples(pred.result.z_of(sid)[:, min(H, pred.result.horizon_steps)])
                              for sid in targets if pred.result.has(sid)}
        if top is not None:
            eff_top = coupled[top.id].minus(baseline[top.id])
            for sid in targets:
                parts = {}
                for nid in top.network_ids:
                    pred = local.get(nid)
                    v = 0.0
                    if pred is not None and pred.result.has(sid):
                        v = float(np.median(pred.result.z_of(sid)[:, min(H, pred.result.horizon_steps)]))
                    parts[nid] = v
                coupled_med = eff_top.median_z(sid, H) if eff_top.has(sid) else 0.0
                parts["coupling"] = coupled_med - sum(parts.values())
                decomposition[sid] = parts
        net_summaries = [NetworkSummary(id=n.id, kind=n.kind, name=n.name or n.id, relevance=n.relevance,
                                        pattern_id=n.pattern_id, subentity_ids=list(n.subentity_ids),
                                        instance_id=n.instance_id,
                                        entity_ids=sorted({graph.subentities[s].entity_id for s in n.subentity_ids
                                                           if s in graph.subentities}),
                                        channel_ids=sorted({base_interaction_id(c.channel_key) for c in n.channels}))
                         for n in networks]
        is_baseline = bool(ctx.notes.get("is_baseline", False))
        return Forecast(id=ctx.notes.get("forecast_id", f"FC-{thesis.id}-1"), thesis_id=thesis.id,
                        based_on_version=ctx.state_version, config_hash=ctx.config.config_hash(), seed=int(ctx.config.seed),
                        created_at=ctx.now, step_days=ctx.step_days, horizon_steps=H, targets=targets, summary=summary,
                        effect_summary=effect_summary, scenarios=new_scen, isolated=isolated, decomposition=decomposition,
                        networks=net_summaries, dropped_mass=float(ctx.notes.get("dropped_mass", 0.0)),
                        z_summary=z_summary, question=thesis.question, is_baseline=is_baseline)


@register("unifier", "weighted_mixture")
class WeightedMixtureUnifier(ChannelsAndRivalsUnifier):
    """Baseline for D2: every network is a rival, weighted by relevance."""

    def plan(self, networks: list[Network], wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext) -> list[ForecastScenario]:
        rel = [max(n.relevance, 1e-6) for n in networks]
        tot = sum(rel)
        out = []
        for k, (n, r) in enumerate(zip(networks, rel), start=1):
            forced = {iid: True for iid in n.forced_present}
            forced.update({iid: False for iid in n.forced_absent})
            out.append(ForecastScenario(id=f"SC-{ctx.scope}-{k}", name=n.name or n.id, weight=r / tot,
                                        network_ids=[n.id], forced_existence=forced))
        ctx.notes["dropped_mass"] = 0.0
        ctx.tracer.emit(Phase.UNIFY, "unify.scenarios", refs=[s.id for s in out],
                        scenarios=[{"id": s.id, "name": s.name, "weight": round(s.weight, 6), "networks": s.network_ids}
                                   for s in out], dropped_mass=0.0)
        return out
