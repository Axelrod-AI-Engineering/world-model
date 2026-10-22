"""Isolate the relevant networks (goal 1; §8.9.1, D1)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.dynamics.propagation import Channel
from axelrod_wm.dynamics.regressors import graph_channels
from axelrod_wm.engine.registry import register
from axelrod_wm.inference.records import Network, NetworkKind
from axelrod_wm.inference.task import NetworkIsolator
from axelrod_wm.model.interaction import base_interaction_id
from axelrod_wm.model.superentity import SuperentityInstance, SuperentityStatus
from axelrod_wm.shared.recognize import PatternBinder
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import PrefilledModel
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.shared.process import SharedResult


def network_seeds(shared: SharedResult, wm: WorkingMemory, ctx: ProcessContext) -> list[str]:
    shocks = [s.subentity_id for s in shared.parsed.shocks]
    if shocks:
        seeds = list(dict.fromkeys(shocks + sorted(shared.analysis.expected_moves)))
    else:
        today = ctx.today
        w = int(ctx.config.frontier.window_days)
        seeds = [s for s in sorted(wm.graph.subentities) if abs(wm.deviations.window_change(s, today, w)) >= 0.5]
    return [s for s in seeds if s in wm.graph.subentities]


def channel_for(key: str, wm: WorkingMemory, model: PrefilledModel, episodes: set[str],
                forced: bool | None = None) -> Channel | None:
    if key in model.channels:
        return model.channel_with(key, episodes, forced)
    ch = graph_channels(wm, {key}).get(key)
    if ch is None:
        return None
    return ch.model_copy(update={"forced": forced}) if forced is not None else ch


def instance_channels(inst: SuperentityInstance, wm: WorkingMemory, model: PrefilledModel,
                      episodes: set[str]) -> list[Channel]:
    out: list[Channel] = []
    absent = set(inst.absent_interaction_ids)
    for iid in list(inst.interaction_ids) + list(inst.absent_interaction_ids):
        inter = wm.graph.interactions.get(iid)
        if inter is None or inter.retired_at is not None:
            continue
        for key, *_ in inter.channel_items():
            if any(c.channel_key == key for c in out):
                continue
            ch = channel_for(key, wm, model, episodes, False if iid in absent else None)
            if ch is not None:
                out.append(ch)
    return out


def endpoints(channels: list[Channel]) -> list[str]:
    out: list[str] = []
    for ch in channels:
        for s in (ch.source_id, ch.target_id):
            if s not in out:
                out.append(s)
    return out


def add_boundaries(networks: list[Network], wm: WorkingMemory) -> None:
    subs = {n.id: set(n.subentity_ids) for n in networks}
    own = {n.id: {c.channel_key for c in n.channels} for n in networks}
    for n in networks:
        bin_, bout = set(), set()
        for key, inter, s, t, _ in wm.graph.channel_items():
            for m in networks:
                if m.id == n.id:
                    continue
                if s in subs[m.id] and t in subs[n.id] and key not in own[n.id]:
                    bin_.add(inter.id)
                if s in subs[n.id] and t in subs[m.id] and key not in own[n.id]:
                    bout.add(inter.id)
        n.boundary_in = sorted(bin_)
        n.boundary_out = sorted(bout)


def residual_network(shared: SharedResult, kept: list[Network], seeds: list[str], wm: WorkingMemory,
                     ctx: ProcessContext, k: int) -> Network | None:
    cfg = ctx.config.isolation
    covered = {c.channel_key for n in kept for c in n.channels}
    model = shared.model
    keys: list[str] = []
    res = shared.analysis.result
    if res is not None and res.channel_contrib is not None:
        med = np.median(res.channel_contrib, axis=0)                   # [channels, days]
        for key, c in sorted(res.channel_index.items()):
            if key not in covered and float(np.max(np.abs(med[c]))) >= float(cfg.residual_min_significance):
                keys.append(key)
    else:
        near = wm.graph.neighborhood(seeds, int(cfg.residual_hops), float(cfg.residual_min_significance))
        for key, inter, s, t, _ in wm.graph.channel_items():
            if key in covered or s not in near or t not in near:
                continue
            if inter.significance_mean() >= float(cfg.residual_min_significance):
                keys.append(key)
    if not keys:
        return None
    eps = set(model.recalled_episode_ids)
    chans = [c for c in (channel_for(key, wm, model, eps) for key in keys) if c is not None]
    return Network(id=f"NW-{ctx.scope}-{k}", kind=NetworkKind.RESIDUAL, instance_id=None, pattern_id=None,
                   subentity_ids=endpoints(chans), channels=chans, relevance=0.0, episode_ids=sorted(eps),
                   name="Residual")


def watch_network(shared: SharedResult, kept: list[Network], watch: list[str], wm: WorkingMemory,
                  ctx: ProcessContext, k: int, max_hops: int = 4, targets: list[str] | None = None) -> Network | None:
    """The context layer (addition): the most significant shortest path from the shock to every value of every
    watched entity, and to every target, within `max_hops` interactions, so no tracked name is left out of the
    simulation because its paths looked too faint to isolate.
    DECISION: the paths are kept whole even where another network holds a channel. That network may be one of
    a pair of rival schemas (S8 | S9), present in only some scenarios; the coupler de-duplicates channels."""
    if not watch and not targets:
        return None
    shocked = [s.subentity_id for s in shared.parsed.shocks]
    out: dict[str, list[tuple[str, str, float]]] = {}
    for key, inter, s, t, _d in wm.graph.channel_items():
        out.setdefault(s, []).append((key, t, inter.significance_mean()))
    dist = {s: 0 for s in shocked}
    parent: dict[str, tuple[str, str, float]] = {}
    layer = list(shocked)
    for hop in range(1, max_hops + 1):
        nxt: list[str] = []
        for u in layer:
            for key, v, sig in sorted(out.get(u, [])):
                if v in dist and dist[v] < hop:
                    continue
                if v not in dist:
                    dist[v] = hop
                    nxt.append(v)
                if v not in parent or sig > parent[v][2]:
                    parent[v] = (key, u, sig)
        layer = nxt
    wanted = {sid for sid, sub in wm.graph.subentities.items() if sub.entity_id in set(watch)} | set(targets or [])
    keys: list[str] = []
    for sid in sorted(wanted & set(parent)):
        cur = sid
        while cur in parent and dist.get(cur, 0) > 0:
            key, prev, _sig = parent[cur]
            if key not in keys:
                keys.append(key)
            cur = prev
    if not keys:
        return None
    model = shared.model
    eps = set(model.recalled_episode_ids)
    chans = [c for c in (channel_for(key, wm, model, eps) for key in keys) if c is not None]
    return Network(id=f"NW-{ctx.scope}-{k}", kind=NetworkKind.RESIDUAL, instance_id=None, pattern_id=None,
                   subentity_ids=endpoints(chans), channels=chans, relevance=0.0, episode_ids=sorted(eps),
                   name="Context paths")


@register("isolator", "bound_superentity")
class BoundSuperentityIsolator(NetworkIsolator):
    def __init__(self, config: Any = None, binder: PatternBinder | None = None) -> None:
        self.config = config
        self.binder = binder

    def _candidate(self, pattern_id: str, attention: float, seeds: list[str], seed_entities: set[str],
                   dist: dict[str, float], wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext,
                   model: PrefilledModel, prefer_members: set[str] | None = None) -> dict | None:
        p = ltm.object_generalizations.patterns.get(pattern_id)
        # DECISION: a composite is not a network of its own; its parts are, and the coupler joins them
        # across the boundary edges, so isolating the composite too would count its parts twice
        if p is None or p.status != SuperentityStatus.ADMITTED or p.sub_pattern_ids:
            return None
        graph = wm.graph
        inst = None
        # the instance with the largest overlap with the seeds (or with a kept rival's members)
        target = prefer_members or seed_entities
        best = (0, "")
        for iid in sorted(graph.instances):
            i = graph.instances[iid]
            if i.pattern_id != p.id:
                continue
            overlap = len(graph.members(iid) & target)
            if overlap > best[0]:
                best = (overlap, iid)
        if best[0] > 0:
            inst = graph.instances[best[1]]
        if inst is None and self.binder is not None and not p.sub_pattern_ids:
            b = self.binder.bind(p, sorted(seed_entities), graph, ltm)
            if b is not None:
                inst = SuperentityInstance(id=ctx.overlay.next_id("inst") if ctx.overlay else f"inst-{ctx.scope}-x",
                                           pattern_id=p.id, bindings=b.bindings, interaction_ids=b.interaction_ids,
                                           absent_interaction_ids=b.absent_interaction_ids, transient=True)
                if ctx.overlay is not None:
                    ctx.overlay.put("instances", inst)
                ctx.tracer.emit(Phase.PREFILL, "induce.bound", refs=[inst.id, p.id], instance_id=inst.id,
                                pattern_id=p.id, members=sorted(set(b.bindings.values())), transient=True)
        if inst is None:
            for iid in sorted(graph.instances):
                if graph.instances[iid].pattern_id == p.id:
                    inst = graph.instances[iid]
                    break
        if inst is None:
            return None
        subs = graph.member_subentities(inst.id) if inst.id in graph.instances else set()
        if not subs:
            for e in inst.bindings.values():
                if e in graph.entities:
                    subs |= set(graph.entities[e].subentity_ids)
        reach = max((math.exp(-dist[s]) for s in subs if s in dist), default=0.0)
        eps = set(model.network_episodes.get(inst.id, []))
        if not eps:
            episodes = ltm.prior_states.episodes
            eps = {e for e in model.recalled_episode_ids if e in episodes and p.id in episodes[e].active_pattern_ids}
        return {"pattern": p, "instance": inst, "attention": attention, "reach": reach,
                "relevance": 0.5 * attention + 0.5 * reach, "episodes": eps}

    def isolate(self, shared: SharedResult, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> list[Network]:
        cfg = ctx.config.isolation
        model = shared.model
        seeds = network_seeds(shared, wm, ctx)
        seed_entities = {wm.graph.subentities[s].entity_id for s in seeds}
        dist = wm.graph.directed_costs(seeds)
        cands: dict[str, dict] = {}
        for s in shared.recall.superentities:
            if s.pattern_id in cands:
                continue
            c = self._candidate(s.pattern_id, s.attention, seeds, seed_entities, dist, wm, ltm, ctx, model)
            if c is not None:
                cands[s.pattern_id] = c
        ranked = sorted(cands.values(), key=lambda c: (-c["relevance"], c["pattern"].id))
        kept = [c for c in ranked if c["relevance"] >= float(cfg.min_relevance)][: int(cfg.max_networks)]
        kept_ids = {c["pattern"].id for c in kept}
        # DECISION: rivals are compared on the same entities, so a rival is bound to the instance that
        # shares the most members with the higher-ranked network it rivals (anchored once, in rank order)
        anchored: set[str] = set()
        for i in range(len(kept)):
            c = kept[i]
            anchored.add(c["pattern"].id)
            inst_id = c["instance"].id
            members = wm.graph.members(inst_id) if inst_id in wm.graph.instances else set(c["instance"].bindings.values())
            for rid in sorted(c["pattern"].rival_ids):
                if rid in anchored:
                    continue
                anchored.add(rid)
                rc = self._candidate(rid, cands[rid]["attention"] if rid in cands else 0.0, seeds, seed_entities, dist,
                                     wm, ltm, ctx, model, prefer_members=members or None)
                if rid in kept_ids:
                    # a kept rival was a candidate, so it is admitted, not composite, and has an instance (or binds
                    # again the same way): rc is not None here
                    kept = [rc if k["pattern"].id == rid else k for k in kept]
                    continue
                if rc is not None and rc["relevance"] >= float(cfg.min_relevance) / 2.0:
                    kept.append(rc)
                    kept_ids.add(rid)
        networks: list[Network] = []
        for k, c in enumerate(kept, start=1):
            inst = c["instance"]
            chans = instance_channels(inst, wm, model, c["episodes"])
            networks.append(Network(
                id=f"NW-{ctx.scope}-{k}", kind=NetworkKind.SUPERENTITY, instance_id=inst.id, pattern_id=c["pattern"].id,
                subentity_ids=endpoints(chans), channels=chans, forced_present=list(inst.interaction_ids),
                forced_absent=list(inst.absent_interaction_ids), relevance=round(c["relevance"], 9),
                episode_ids=sorted(c["episodes"]), name=f"{c['pattern'].id} · {c['pattern'].name}",
                attention=c["attention"], reach=c["reach"], transient=inst.transient))
        r = residual_network(shared, networks, seeds, wm, ctx, len(networks) + 1)
        if r is not None:
            networks.append(r)
        add_boundaries(networks, wm)
        ctx.tracer.emit(Phase.ISOLATE, "isolate.networks", refs=[n.id for n in networks] + [n.instance_id for n in networks if n.instance_id],
                        networks=[{"id": n.id, "kind": str(n.kind), "name": n.name, "pattern_id": n.pattern_id,
                                   "instance_id": n.instance_id, "relevance": round(n.relevance, 4),
                                   "members": sorted({s.split(".")[0] for s in n.subentity_ids}),
                                   "channels": [base_interaction_id(c.channel_key) for c in n.channels]}
                                  for n in networks])
        return networks


@register("isolator", "k_hop")
class KHopIsolator(NetworkIsolator):
    """Baseline: only the residual rule, no superentities."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def isolate(self, shared: SharedResult, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext) -> list[Network]:
        seeds = network_seeds(shared, wm, ctx)
        r = residual_network(shared, [], seeds, wm, ctx, 1)
        if r is None:
            near = wm.graph.neighborhood(seeds, int(ctx.config.isolation.reach_hops), 0.0)
            keys = [k for k, _i, s, t, _d in wm.graph.channel_items() if s in near and t in near]
            eps = set(shared.model.recalled_episode_ids)
            chans = [c for c in (channel_for(k, wm, shared.model, eps) for k in keys) if c is not None]
            if not chans:
                return []
            r = Network(id=f"NW-{ctx.scope}-1", kind=NetworkKind.RESIDUAL, instance_id=None, pattern_id=None,
                        subentity_ids=endpoints(chans), channels=chans, relevance=1.0, name="Residual")
        r.relevance = 1.0
        ctx.tracer.emit(Phase.ISOLATE, "isolate.networks", refs=[r.id],
                        networks=[{"id": r.id, "kind": "residual", "name": r.name, "relevance": 1.0,
                                   "members": sorted({s.split(".")[0] for s in r.subentity_ids}),
                                   "channels": [base_interaction_id(c.channel_key) for c in r.channels]}])
        return [r]
