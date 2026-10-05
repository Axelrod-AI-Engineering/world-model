"""Consolidation: the daily distillation of working memory into long-term memory (§8.12)."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.entity import DecisionProfile, EntityMemory, EntityMemoryEntry, action_of
from axelrod_wm.core.hypothesis import HypothesisStatus
from axelrod_wm.engine.frontier_test import decay_frontier
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.engine.voi import context_bucket
from axelrod_wm.events.ledger import LedgerKind
from axelrod_wm.memory.episodes import Episode
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext


class ConsolidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date
    episode_id: str | None
    patterns_supported: list[str]
    proposals: list[str]
    frontier_decayed: list[str]
    hypotheses_expired: list[str]
    snapshot_version: int
    proposal_events: list[dict] = []
    kernels_updated: list[str] = []
    candidates: list[str] = []


class Consolidator(ABC):
    @abstractmethod
    def run(self, day: date, ctx: ProcessContext) -> ConsolidationReport: ...


registry("consolidator", Consolidator)

LEVEL_NOISE_BOUNDS = (0.02, 1.0)


def build_episode(ep_id: str, wm: Any, cfg: Any) -> Episode:
    buf = wm.episode_buffer
    start = min(e.at for e in buf)
    end = max(e.at for e in buf)
    sig = {k for e in buf for k in e.signature if not k.startswith(("tag:", "etype:"))}
    non_routine = [e for e in buf if not e.routine] or list(buf)
    key_sig = {k for e in non_routine for k in e.signature if not k.startswith(("tag:", "etype:"))}
    z_start: dict[str, float] = {}
    z_end: dict[str, float] = {}
    for e in buf:
        for sid, z in e.z_before.items():
            z_start.setdefault(sid, z)
        for sid, z in e.z_after.items():
            z_end[sid] = z
            z_start.setdefault(sid, e.z_before.get(sid, z))
    deltas = {sid: (z_start[sid], z_end[sid]) for sid in sorted(z_end)
              if abs(z_end[sid] - z_start[sid]) >= float(cfg.consolidation.episode_min_abs_z)}
    active = sorted({r.interaction_id for r in wm.activity_log})
    effects = {}
    for iid, (spy, sp2) in sorted(wm.fold_accumulators.items()):
        if sp2 > 1e-9:
            effects[iid] = (spy / sp2, sp2)
    patterns = sorted({i.pattern_id for i in wm.graph.instances.values() if i.activation > 0 and not i.transient})
    tags = sorted({t for e in buf for t in e.tags} | set(wm.pending_episode_tags))
    return Episode(id=ep_id, start=start, end=end, trigger_event_ids=[e.event_id for e in buf],
                   event_types=sorted({e.event_type for e in buf if e.event_type}), signature=sig,
                   key_signature=key_sig, deltas=deltas, active_interaction_ids=active, edge_effects=effects,
                   active_pattern_ids=patterns, explanation_ids=[e.explanation_id for e in buf if e.explanation_id],
                   tags=tags, step=wm.deviations.step_of(end))


@register("consolidator", "daily")
class DailyConsolidator(Consolidator):
    def __init__(self, config: Any = None, engine: Any = None) -> None:
        self.config = config
        self.engine = engine

    def run(self, day: date, ctx: ProcessContext) -> ConsolidationReport:
        eng = self.engine
        comp = eng.components
        cfg = ctx.config
        wm, ltm = eng.wm, eng.ltm
        report = ConsolidationReport(day=day, episode_id=None, patterns_supported=[], proposals=[],
                                     frontier_decayed=[], hypotheses_expired=[], snapshot_version=eng.version)
        with ctx.mutator.begin(f"consolidation:{day.isoformat()}", now=ctx.now) as txn:
            if ctx.now > wm.clock:
                txn.set("wm.clock", ctx.now)
            episode = None
            touched_today: set[str] = set()
            if wm.episode_buffer:
                episode = build_episode(txn.new_id("EP"), wm, cfg)
                txn.add("episodes", episode)
                report.episode_id = episode.id
                for e in wm.episode_buffer:
                    touched_today.update(e.touched_entity_ids)
            # 2. forecast explanations move into long-term memory
            for tid in sorted(wm.forecast_layer.by_thesis):
                ex = wm.forecast_layer.by_thesis[tid].explanation
                if ex.id not in ltm.explanations.explanations:
                    txn.add("explanations", ex)
            # 3. superentity support
            if episode is not None:
                ind = comp["inducer"].count(episode, wm, ltm, ctx, txn)
                report.patterns_supported = list(ind.supported_pattern_ids)
                report.candidates = list(ind.candidate_pattern_ids)
                report.proposal_events.extend(ind.proposal_events)
            # 4. kernels
            report.kernels_updated = comp["kernel_updater"].update(wm, ltm, ctx, txn)
            # 5. entity memories
            for eid in sorted(touched_today):
                self._entity_memory(eid, episode, ctx, txn)
            # 6. decay
            report.frontier_decayed = decay_frontier(wm, ltm, ctx, txn, wm.last_consolidated)
            for hid in sorted(wm.hypotheses):
                h = wm.hypotheses[hid]
                if h.status != HypothesisStatus.OPEN:
                    continue
                age = (ctx.now - (h.created_at or h.scored_at)).total_seconds() / 86400.0
                if h.current_value(ctx.now) < 0.01 and age > 4 * h.half_life_days and not h.comovement_id:
                    txn.update("hypotheses", hid, status=HypothesisStatus.EXPIRED)
                    report.hypotheses_expired.append(hid)
            for pid in sorted(wm.pending_refinements):
                if wm.pending_refinements[pid].expires_at <= ctx.now:
                    txn.remove("pending_refinements", pid)
            # 7. taxonomy growth on the nodes touched today
            if episode is not None and comp.get("taxonomy_grower") is not None:
                for gid in sorted(episode.signature):
                    for tax in (ltm.object_taxonomy, ltm.interaction_taxonomy):
                        if gid in tax.nodes:
                            comp["taxonomy_grower"].maybe_split(tax, gid, ctx, txn)
            # 8. reset
            if wm.activity_log:
                txn.set("wm.activity_log", [])
            if wm.fold_accumulators:
                txn.set("wm.fold_accumulators", {})
            if wm.episode_buffer:
                txn.set("wm.episode_buffer", [])
            if wm.pending_episode_tags:
                txn.set("wm.pending_episode_tags", [])
            for iid in sorted(wm.graph.instances):
                if wm.graph.instances[iid].activation != 0.0:
                    txn.update("instances", iid, activation=0.0)
            unpinned = [t for t in sorted(wm.forecast_layer.by_thesis) if t not in wm.forecast_layer.pinned]
            for tid in unpinned:
                txn.remove("forecast_layer", tid)
            if unpinned:
                txn.set("forecast_layer.order", [t for t in wm.forecast_layer.order if t not in unpinned])
            txn.set("wm.last_consolidated", day)
        # 9. snapshot
        if eng.snapshot_on_consolidation and not eng.initializing:
            eng.save_snapshot()
        report.snapshot_version = eng.version
        eng.ledger.append(LedgerKind.CONSOLIDATION, report.model_dump(mode="json", exclude={"proposal_events"}),
                          recorded_at=ctx.now)
        ctx.tracer.emit(Phase.CONSOLIDATE, "consolidation.done", refs=[report.episode_id] if report.episode_id else [],
                        report={"day": day.isoformat(), "episode_id": report.episode_id,
                                "patterns_supported": report.patterns_supported,
                                "frontier_decayed": report.frontier_decayed,
                                "hypotheses_expired": report.hypotheses_expired,
                                "kernels_updated": report.kernels_updated, "candidates": report.candidates,
                                "snapshot_version": report.snapshot_version,
                                "episodes": len(ltm.episodes.episodes)})
        return report

    def _entity_memory(self, eid: str, episode: Episode | None, ctx: ProcessContext, txn: Any) -> None:
        eng = self.engine
        wm, ltm = eng.wm, eng.ltm
        ent = wm.graph.entities.get(eid)
        if ent is None:
            return
        dev = wm.deviations
        step = dev.step_of(ctx.now)
        summaries = {}
        zs = {}
        for sid in ent.subentity_ids:
            sub = wm.graph.subentities.get(sid)
            if sub is None:
                continue
            summaries[sid] = sub.posterior.summary()
            z = dev.z_at(sid, step)
            if z is not None:
                zs[sid] = z
        entry = EntityMemoryEntry(at=episode.end if episode is not None else ctx.now, subentity_summaries=summaries,
                                  event_ids=[e for e in (episode.trigger_event_ids if episode else [])][:20], z=zs)
        mem = ltm.entity_memories.get(eid)
        keep = EntityMemory.MAX_ENTRIES
        if mem is None:
            mem_new = EntityMemory(entity_id=eid, entries=[entry])
            txn.add("entity_memories", mem_new)
            decisions = []
        else:
            txn.append_to("entity_memories", eid, "entries", entry, keep_last=keep)
            decisions = list(mem.decisions)
        # fold decision observations into profiles
        if decisions:
            profiles: dict[str, DecisionProfile] = {}
            for d in decisions:
                sub = wm.graph.subentities.get(d.subentity_id)
                scale_native = sub.scale if sub is not None and sub.posterior.link == "identity" else (
                    abs(float(np.exp(sub.anchor + sub.scale) - np.exp(sub.anchor))) if sub is not None else 1.0)
                action = action_of(d.change, scale_native)
                prof = profiles.setdefault(d.subentity_id, DecisionProfile())
                bucket = context_bucket(d.context)
                counts = prof.by_context.setdefault(bucket, [0, 0, 0])
                counts[("raised", "cut", "held").index(action)] += 1
            if mem is None or {k: v.by_context for k, v in mem.profiles.items()} != {k: v.by_context for k, v in profiles.items()}:
                txn.update("entity_memories", eid, profiles=profiles)
        # level noise: the realized volatility of each subentity over its last 52 observations
        # DECISION: computed from the observed standardized values (y), not the filtered z, whose changes
        # understate volatility and feed back into ever-smaller level noise.
        for sid in ent.subentity_ids:
            sub0 = wm.graph.subentities.get(sid)
            if sub0 is None:
                continue
            obs: dict[int, float] = {}
            for ts in sub0.history:
                if "y" in ts.values and "step" in ts.values:
                    obs[int(ts.values["step"])] = float(ts.values["y"])
            steps_sorted = sorted(obs)[-53:]
            pts = [(k, obs[k]) for k in steps_sorted]
            changes = []
            for (s0, z0), (s1, z1) in zip(pts[:-1], pts[1:]):
                if s1 > s0:
                    changes.append((z1 - z0) / math.sqrt(s1 - s0))
            if len(changes) >= 8:
                sd = float(np.std(changes))
                lo = LEVEL_NOISE_BOUNDS[0]
                if sid in wm.decision_variables:
                    # DECISION: decision variables move in discrete jumps; a level noise learned from a run
                    # of holds would make the fold ignore the next real decision.
                    lo = max(lo, float(ctx.config.learning.level_process_noise))
                sd = min(max(sd, lo), LEVEL_NOISE_BOUNDS[1])
                sub = wm.graph.subentities[sid]
                if sub.level_noise is None or abs(sub.level_noise - sd) > 1e-9:
                    txn.update("subentities", sid, level_noise=sd)
