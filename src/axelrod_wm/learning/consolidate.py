"""The daily distillation of working memory into long-term memory (§8.12): long-term learning's daily step.

One commit ("distill:<date>"), after the day is recorded and before it closes: the day becomes an episode,
analog responses are pooled into past episodes, forecast explanations are kept, superentity support is
counted (proposing candidates, admissions, and dissolutions for review), entity memories gain their weekly
entry, the correlation frontier decays, and the kinds touched today may grow. Working memory's own end of
day (kernels, hypotheses, pruning, the clock) is in learning/working_memory.py.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.registry import register, registry
from axelrod_wm.learning.frontier_test import decay_frontier
from axelrod_wm.memory.entity_memory import EntityMemory, EntityMemoryEntry
from axelrod_wm.memory.long_term import Episode
from axelrod_wm.memory.working import split_point_key
from axelrod_wm.model.interaction import base_interaction_id

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.repo.mutator import MutationTxn


class ConsolidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    episode_id: str | None
    patterns_supported: list[str]
    proposals: list[str]
    frontier_decayed: list[str]
    hypotheses_expired: list[str]
    version: int                       # state version after this consolidation
    proposal_events: list[dict] = []
    kernels_updated: list[str] = []
    candidates: list[str] = []
    pruned_points: int = 0


class Consolidator(ABC):
    @abstractmethod
    def run(self, day: int, ctx: ProcessContext) -> ConsolidationReport: ...


registry("consolidator", Consolidator)

LEVEL_NOISE_BOUNDS = (0.02, 1.0)
WEEKS = 52
MIN_WEEKS = 8


def build_episode(ep_id: str, day: int, wm: WorkingMemory, cfg: Any) -> Episode:
    """Today's Episode from the episode buffer (§8.12 step 1)."""
    buf = wm.episode_buffer
    dev = wm.deviations
    sig = {k for e in buf for k in e.signature if not k.startswith(("tag:", "etype:"))}
    non_routine = [e for e in buf if not e.routine] or list(buf)
    key_sig = {k for e in non_routine for k in e.signature if not k.startswith(("tag:", "etype:"))}
    min_z = float(cfg.episodes.min_abs_z)
    deltas = {}
    for sid in sorted(wm.graph.subentities):
        z0, z1 = dev.z(sid, day - 1), dev.z(sid, day)
        if abs(z1 - z0) >= min_z:
            deltas[sid] = (z0, z1)
    active = sorted({base_interaction_id(r.channel_id) for r in wm.activity_log.values() if r.day == day})
    effects = {}
    for key, (spy, sp2) in sorted(wm.fold_accumulators.items()):
        if sp2 > 1e-9:
            effects[key] = (spy / sp2, sp2)
    patterns = sorted({i.pattern_id for i in wm.graph.instances.values() if i.activation > 0 and not i.transient})
    tags = sorted({t for e in buf for t in e.tags} | set(wm.pending_episode_tags))
    return Episode(id=ep_id, day=dev.date_of(day), day_index=day, trigger_event_ids=[e.event_id for e in buf],
                   routine=all(e.routine for e in buf),
                   event_types=sorted({e.event_type for e in buf if e.event_type}), signature=sig,
                   key_signature=key_sig, deltas=deltas, active_interaction_ids=active, edge_effects=effects,
                   active_pattern_ids=patterns, explanation_ids=[e.explanation_id for e in buf if e.explanation_id],
                   tags=tags)


def pool(stored: tuple[float, float] | None, today: tuple[float, float]) -> tuple[float, float]:
    """Precision pooling of (implied effect, weight) pairs (§8.12 step 2)."""
    if stored is None:
        return today
    b, w = stored
    b_d, w_d = today
    w2 = w + w_d
    return ((b * w + b_d * w_d) / w2 if w2 > 0 else b, w2)


@register("consolidator", "daily")
class DailyConsolidator(Consolidator):
    def __init__(self, config: Any = None, engine: Any = None) -> None:
        self.config = config
        self.engine = engine

    def run(self, day: int, ctx: ProcessContext) -> ConsolidationReport:
        eng = self.engine
        comp = eng.components
        cfg = ctx.config
        wm, ltm = eng.wm, eng.ltm
        dev = wm.deviations
        d_date = dev.date_of(day)
        report = ConsolidationReport(day=d_date, episode_id=None, patterns_supported=[], proposals=[],
                                     frontier_decayed=[], hypotheses_expired=[], version=eng.version)
        with ctx.mutator.begin(f"distill:{d_date.isoformat()}", at=ctx.now, process="day.distill",
                               message=f"Daily distillation · {d_date.isoformat()}") as txn:
            # 1. episode
            episode = None
            non_routine_touched: set[str] = set()
            if wm.episode_buffer:
                episode = build_episode(txn.new_id("EP"), day, wm, cfg)
                txn.add("ltm.prior_states.episodes", episode)
                report.episode_id = episode.id
                ctx.notes["episode_id"] = episode.id
                for e in wm.episode_buffer:
                    if not e.routine:
                        non_routine_touched.update(e.touched_entity_ids)
            # working memory's end of day rescores the hypotheses these entities touch
            ctx.notes["non_routine_touched"] = non_routine_touched
            # 2. analog responses
            self._analog_responses(day, episode, ctx, txn)
            # 3. forecast explanations move into long-term memory
            stored = ltm.prior_states.explanations
            for tid in sorted(wm.forecast_layer.by_thesis):
                ex = wm.forecast_layer.by_thesis[tid].explanation
                if ex.id not in stored:
                    txn.add("ltm.prior_states.explanations", ex)
            # 4. superentity support
            ind = comp["inducer"].count(day, wm, ltm, ctx, txn)
            report.patterns_supported = list(ind.supported_pattern_ids)
            report.candidates = list(ind.candidate_pattern_ids)
            report.proposal_events.extend(ind.proposal_events)
            # 5. entity memories
            every_em = max(1, int(cfg.entity_memory.entry_every_days))
            if (day + 1) % every_em == 0:
                self._entity_memories(day, episode, ctx, txn)
            # 6. the correlation frontier decays (pattern supports decay in inducer.count)
            report.frontier_decayed = decay_frontier(day, wm, ltm, ctx, txn)
            # 7. taxonomy growth on the nodes touched today
            if episode is not None and comp.get("taxonomy_grower") is not None:
                for gid in sorted(episode.signature):
                    for tax in (ltm.object_generalizations.taxonomy, ltm.interaction_generalizations.taxonomy):
                        if gid in tax.nodes:
                            comp["taxonomy_grower"].maybe_split(tax, gid, ctx, txn)
        report.version = eng.version
        return report

    # -- step 2 ------------------------------------------------------------------------------
    def _analog_responses(self, day: int, episode: Episode | None, ctx: ProcessContext, txn: MutationTxn) -> None:
        """Pool today's edge effects into the response of every non-routine episode from the last
        episodes.analog_span_days days, including today's, and update its response deltas."""
        wm, ltm = self.engine.wm, self.engine.ltm
        dev = wm.deviations
        span = int(ctx.config.episodes.analog_span_days)
        min_z = float(ctx.config.episodes.min_abs_z)
        today_effects = {}
        for key, (spy, sp2) in sorted(wm.fold_accumulators.items()):
            if sp2 > 1e-9:
                today_effects[key] = (spy / sp2, sp2)
        for eid, ep in sorted(ltm.prior_states.episodes.items()):
            if ep.routine:
                continue
            ep_day = ep.day_index if ep.day_index is not None else dev.day_of_date(ep.day)
            if not (day - span < ep_day <= day):
                continue
            fields: dict[str, Any] = {}
            if today_effects:
                re = dict(ep.response_effects)
                for key, val in today_effects.items():
                    re[key] = pool(re.get(key), val)
                fields["response_effects"] = re
            # the change in z since the trigger day began, for subentities that moved by at least
            # episodes.min_abs_z over the span so far
            rd = dict(ep.response_deltas)
            keys = set(ep.deltas) | set(rd)
            for sid in sorted(wm.graph.subentities):
                change = dev.z(sid, day) - dev.z(sid, ep_day - 1)
                if sid in keys or abs(change) >= min_z:
                    rd[sid] = round(change, 6)
            if rd != ep.response_deltas:
                fields["response_deltas"] = rd
            if fields:
                txn.update("ltm.prior_states.episodes", eid, **fields)

    # -- step 6 ------------------------------------------------------------------------------
    def _entity_memories(self, day: int, episode: Episode | None, ctx: ProcessContext, txn: MutationTxn) -> None:
        """A weekly EntityMemoryEntry for every entity, and each subentity's level noise from the
        weekly changes in its local level over the last 52 weeks (§8.12 step 6)."""
        eng = self.engine
        wm, ltm = eng.wm, eng.ltm
        dev = wm.deviations
        every = max(1, int(ctx.config.entity_memory.entry_every_days))
        floor_decision = float(ctx.config.learning.level_process_noise)
        triggers = list(episode.trigger_event_ids)[:20] if episode is not None else []
        end = dev.day_end(day)
        for eid in sorted(wm.graph.entities):
            ent = wm.graph.entities[eid]
            summaries, zs = {}, {}
            for sid in ent.subentity_ids:
                sub = wm.graph.subentities.get(sid)
                if sub is None:
                    continue
                summaries[sid] = sub.posterior.summary()
                zs[sid] = round(dev.z(sid, day), 6)
            touched = [t for t in triggers]
            entry = EntityMemoryEntry(at=end, subentity_summaries=summaries, event_ids=touched, z=zs)
            if eid in ltm.entity_memories:
                txn.append_to("ltm.entity_memories", eid, "entries", entry, keep_last=EntityMemory.MAX_ENTRIES)
            else:
                txn.add("ltm.entity_memories", EntityMemory(entity_id=eid, entries=[entry]))
            for sid in ent.subentity_ids:
                sub = wm.graph.subentities.get(sid)
                if sub is None:
                    continue
                changes = []
                for k in range(WEEKS):
                    a, b = dev.point(sid, day - every * (k + 1)), dev.point(sid, day - every * k)
                    if a is None or b is None:
                        break
                    changes.append(b.level - a.level)
                if len(changes) < MIN_WEEKS:
                    continue
                sd = float(np.std(changes)) / math.sqrt(every)
                lo = LEVEL_NOISE_BOUNDS[0]
                if sid in wm.decision_variables:
                    # DECISION: decision variables move in discrete jumps; a level noise learned from a run
                    # of holds would make the fold ignore the next real decision.
                    lo = max(lo, floor_decision)
                sd = min(max(sd, lo), LEVEL_NOISE_BOUNDS[1])
                if sub.level_noise is None or abs(sub.level_noise - sd) > 1e-9:
                    txn.update("wm.graph.subentities", sid, level_noise=sd)


__all__ = ["ConsolidationReport", "Consolidator", "DailyConsolidator", "build_episode", "split_point_key"]
