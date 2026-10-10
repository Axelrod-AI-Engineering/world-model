"""Prefill a model with the recalled superentities' and analogs' trends (§8.4.4)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from axelrod_wm.dynamics.regressors import graph_channels, obs_noise_of
from axelrod_wm.engine.interfaces import AnalogEvidence, PrefilledModel, Prefiller
from axelrod_wm.engine.registry import register
from axelrod_wm.events.graph_update import EventKind
from axelrod_wm.model.interaction import base_interaction_id
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import RecallResult
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.shared.process import ParsedEvent
    from axelrod_wm.shared.recognize import InductionResult


def level_drift(wm: WorkingMemory, sid: str, today: int, window_days: int, clip: float) -> float:
    """Mean daily change of the local level (DeviationPoint.level) over the last `window_days`,
    clipped to +-clip (0 if fewer days exist)."""
    dev = wm.deviations
    a, b = dev.point(sid, today - window_days), dev.point(sid, today)
    if a is None or b is None or window_days <= 0:
        return 0.0
    drift = (b.level - a.level) / window_days
    return max(-clip, min(clip, drift))


def focus_of(parsed: ParsedEvent, wm: WorkingMemory, ctx: ProcessContext) -> list[str]:
    focus = list(parsed.touched_subentity_ids)
    if parsed.kind == EventKind.HYPOTHETICAL:
        for sid in list(ctx.notes.get("targets", [])) + sorted(ctx.config.hypotheses.watch_list):
            if sid in wm.graph.subentities and sid not in focus:
                focus.append(sid)
    if not parsed.shocks:
        today = ctx.today
        w = int(ctx.config.frontier.window_days)
        for sid in sorted(wm.graph.subentities):
            if sid not in focus and abs(wm.deviations.window_change(sid, today, w)) >= 0.5:
                focus.append(sid)
    return focus


@register("prefiller", "analog_empirical_bayes")
class AnalogEmpiricalBayesPrefiller(Prefiller):
    use_analogs = True
    use_trends = True

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def prefill(self, parsed: ParsedEvent, recall: RecallResult, induction: InductionResult,
                wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> PrefilledModel:
        graph = wm.graph
        # DECISION: a real event with no shocks needs no analysis, so it gets an empty model.
        if parsed.kind == EventKind.REAL and not parsed.shocks:
            return PrefilledModel(channels={}, analog_evidence={}, network_episodes={}, drifts={},
                                  instance_ids=list(induction.bound_instance_ids), notes=[])
        focus = focus_of(parsed, wm, ctx)
        hops = int(ctx.config.isolation.residual_hops) + 2
        near = graph.neighborhood(focus, hops, 0.0)
        keys: set[str] = set()
        for key, _inter, s, t, _d in graph.channel_items():
            if s in near or t in near:
                keys.add(key)
        instance_ids = sorted(set(induction.bound_instance_ids)
                              | {s.instance_id for s in recall.superentities if s.instance_id})
        for iid in instance_ids:
            inst = graph.instances.get(iid)
            if inst is None:
                continue
            for i in inst.interaction_ids + inst.absent_interaction_ids:
                inter = graph.interactions.get(i)
                if inter is not None and inter.retired_at is None:
                    for key, *_ in inter.channel_items():
                        keys.add(key)
        channels = graph_channels(wm, keys)
        recalled = {a.episode_id: a.attention for a in recall.analogs}
        evidence: dict[str, list[AnalogEvidence]] = {}
        notes: list[str] = []
        target_noise: dict[str, float] = {}
        tax = ltm.interaction_generalizations.taxonomy
        episodes = ltm.prior_states.episodes
        for key, ch in sorted(channels.items()):
            tgt = graph.subentities[ch.target_id]
            target_noise[key] = obs_noise_of(tgt, wm, ctx.vocab)
            if not self.use_analogs:
                continue
            inter = graph.interactions[base_interaction_id(key)]
            gen = inter.generalization_id
            siblings = set(tax.instances_under(gen)) if gen and gen in tax.nodes else set()
            # DECISION (restructure): a sibling's response pools only when its effect has this channel's
            # sign. A kind can hold links of both signs (oil raises a fuel bill; the bill squeezes a
            # margin), and pooling across them flipped the sign of an airline's fuel-to-margin effect.
            sign = 1.0 if ch.dynamics.effect.mean() >= 0 else -1.0
            siblings = {o for o in siblings if o in graph.interactions
                        and (1.0 if graph.interactions[o].forward.effect.mean() >= 0 else -1.0) == sign}
            # an analog carries the response that followed its trigger (§8.12 step 2)
            items: list[AnalogEvidence] = []
            for eid, att in sorted(recalled.items()):
                ep = episodes.get(eid)
                if ep is None:
                    continue
                resp = ep.response_effects or ep.edge_effects
                if key in resp:
                    b, wgt = resp[key]
                else:
                    pairs = [resp[o] for o in sorted(siblings) if o in resp]
                    if not pairs:
                        continue
                    wsum = sum(p[1] for p in pairs)
                    if wsum <= 0:
                        continue
                    b, wgt = sum(p[0] * p[1] for p in pairs) / wsum, wsum
                if wgt > 0:
                    items.append(AnalogEvidence(episode_id=eid, implied_effect=float(b), weight=float(wgt),
                                                attention=float(att)))
            if items:
                evidence[key] = items
        network_episodes: dict[str, list[str]] = {}
        for iid in instance_ids:
            inst = graph.instances.get(iid)
            if inst is None:
                continue
            network_episodes[iid] = [eid for eid in sorted(recalled)
                                     if eid in episodes and inst.pattern_id in episodes[eid].active_pattern_ids]
        drifts: dict[str, float] = {}
        if self.use_trends:
            pf = ctx.config.prefill
            endpoints = {ch.source_id for ch in channels.values()} | {ch.target_id for ch in channels.values()}
            for sid in sorted(endpoints | set(focus)):
                if sid in graph.subentities:
                    d = level_drift(wm, sid, ctx.today, int(pf.trend_window_days), float(pf.max_drift_per_day))
                    if d:
                        drifts[sid] = d
        model = PrefilledModel(channels=channels, analog_evidence=evidence, network_episodes=network_episodes,
                               drifts=drifts, instance_ids=instance_ids, notes=notes, target_noise=target_noise,
                               focus=focus, recalled_episode_ids=sorted(recalled))
        all_eps = set(recalled)
        for key in sorted(evidence):
            before = channels[key].dynamics.effect.mean()
            after = model.dynamics_for(key, all_eps).effect.mean()
            if abs(after - before) >= 0.01:
                eps = [e.episode_id for e in evidence[key]]
                tags = sorted({t for e in eps for t in episodes[e].tags})
                label = f"{tags[0]} " if tags else ""
                notes.append(f"{key} effect {before:.2f} -> {after:.2f} from {len(eps)} {label}analogs")
                ctx.tracer.emit(Phase.PREFILL, "prefill.adjusted", refs=[base_interaction_id(key)] + eps,
                                interaction_id=base_interaction_id(key), channel=key, effect_before=round(before, 4),
                                effect_after=round(after, 4), analog_ids=eps)
        return model


@register("prefiller", "none")
class NonePrefiller(AnalogEmpiricalBayesPrefiller):
    """Base posteriors, no analogs and no trends."""

    use_analogs = False
    use_trends = False
