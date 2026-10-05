"""Predict across networks (goal 2, distributed; §8.9.3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from axelrod_wm.engine.performance.task import NetworkCoupler
from axelrod_wm.engine.propagation import (
    Channel,
    McImpulsePropagator,
    PropagationResult,
    Propagator,
    ShockInput,
)
from axelrod_wm.engine.registry import register
from axelrod_wm.engine.regressors import build_system, graph_channels, horizon_for

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import PrefilledModel
    from axelrod_wm.engine.performance.records import Network


def union_channels(networks: list[Network], forced_existence: dict[str, bool], model: PrefilledModel,
                   ctx: ProcessContext) -> list[Channel]:
    """The union of the networks' channels (deduplicated by key) plus the boundary channels between
    them, each with dynamics_for(c, E_c) where E_c pools the episodes of the networks containing c."""
    eps: dict[str, set[str]] = {}
    base: dict[str, Channel] = {}
    for n in networks:
        for ch in n.channels:
            key = ch.channel_key
            eps.setdefault(key, set()).update(n.episode_ids)
            if key not in base:
                base[key] = ch
    subs = {n.id: set(n.subentity_ids) for n in networks}
    for key, inter, s, t, _ in ctx.wm.graph.channel_items():
        if key in base:
            continue
        for a in networks:
            for b in networks:
                if a.id != b.id and s in subs[a.id] and t in subs[b.id]:
                    ch = graph_channels(ctx.wm, {key}).get(key)
                    if ch is not None:
                        base[key] = ch
                        eps.setdefault(key, set())
    out = []
    for key in sorted(base):
        ch = base[key]
        if key in model.channels:
            ch = model.channel_with(key, eps.get(key, set()), ch.forced)
        forced = forced_existence.get(ch.interaction_id)
        if forced is not None:
            ch = ch.model_copy(update={"forced": forced})
        out.append(ch)
    return out


@register("coupler", "union_graph")
class UnionGraphCoupler(NetworkCoupler):
    def __init__(self, config: Any = None, propagator: Propagator | None = None) -> None:
        self.config = config
        self.propagator = propagator

    def couple(self, networks: list[Network], forced_existence: dict[str, bool], shocks: list[ShockInput],
               model: PrefilledModel, ctx: ProcessContext, n_samples: int | None = None) -> PropagationResult:
        H = horizon_for(ctx)
        chans = union_channels(networks, forced_existence, model, ctx)
        extra = [s.subentity_id for s in shocks] + list(ctx.notes.get("targets", []))
        system = build_system(chans, ctx.wm, ctx, H, extra_subentities=extra, drifts=model.drifts)
        n = int(n_samples or ctx.config.propagation.samples)
        return self.propagator.propagate(system, shocks, n, ctx.child_rng("couple", ctx.scope),
                                         record_contributions=True)


@register("coupler", "iterative_block")
class IterativeBlockCoupler(NetworkCoupler):
    """Block Gauss-Seidel over networks in order of relevance. Each block propagates its own
    channels with the thesis shocks plus boundary inputs from the latest paths of other blocks,
    until the inputs change by less than 1e-3 (at most 10 rounds)."""

    def __init__(self, config: Any = None, propagator: Propagator | None = None, tol: float = 1e-3,
                 max_rounds: int = 10) -> None:
        self.config = config
        self.propagator = propagator
        self.tol = tol
        self.max_rounds = max_rounds

    def couple(self, networks: list[Network], forced_existence: dict[str, bool], shocks: list[ShockInput],
               model: PrefilledModel, ctx: ProcessContext, n_samples: int | None = None) -> PropagationResult:
        H = horizon_for(ctx)
        n = int(n_samples or ctx.config.propagation.samples)
        chans = union_channels(networks, forced_existence, model, ctx)
        order = sorted(networks, key=lambda x: (-x.relevance, x.id))
        owner: dict[str, int] = {}
        for b, net in enumerate(order):
            for s in net.subentity_ids:
                owner.setdefault(s, b)
        for s in [sh.subentity_id for sh in shocks] + list(ctx.notes.get("targets", [])):
            owner.setdefault(s, 0)
        for ch in chans:
            owner.setdefault(ch.target_id, 0)
            owner.setdefault(ch.source_id, owner[ch.target_id])
        blocks = sorted(set(owner.values()))
        rng = ctx.child_rng("couple", ctx.scope)
        drawer = McImpulsePropagator(ctx.config)
        if isinstance(self.propagator, McImpulsePropagator):
            drawer = self.propagator
        full = build_system(chans, ctx.wm, ctx, H, drifts=model.drifts)
        idx = {s: i for i, s in enumerate(full.subentity_ids)}
        params = drawer._draw(full, idx, 1 if drawer.deterministic else n, rng)
        W = drawer.window
        S = 1 if drawer.deterministic else n
        cross = [c for c, ch in enumerate(chans) if owner[ch.source_id] != owner[ch.target_id]]
        paths: dict[str, np.ndarray] = {}
        results: dict[int, PropagationResult] = {}
        hist: dict[str, np.ndarray] = {}
        for s in full.subentity_ids:
            init = full.initial.get(s)
            past = np.zeros(W)
            if init is not None and init.past_dz:
                arr = np.asarray(init.past_dz[-W:], dtype=float)
                past[W - arr.size:] = arr
            hist[s] = past
        prev_inputs: dict[str, np.ndarray] = {}
        for _round in range(self.max_rounds):
            delta = 0.0
            for b in blocks:
                members = [s for s in full.subentity_ids if owner.get(s) == b]
                own = [ch for ch in chans if owner[ch.target_id] == b and owner[ch.source_id] == b]
                exo: dict[str, np.ndarray] = {}
                for c in cross:
                    ch = chans[c]
                    if owner[ch.target_id] != b:
                        continue
                    src_path = paths.get(ch.source_id)
                    z0 = full.initial[ch.source_id].z_now if ch.source_id in full.initial else 0.0
                    if src_path is None:
                        src_path = np.full((S, H + 1), z0)
                    dz_future = np.diff(src_path, axis=1)                       # [S, H], times 1..H
                    # index i <-> time i - W: a leading zero, the history (times -W+1..0), then the future
                    dz_all = np.concatenate([np.zeros((S, 1)), np.broadcast_to(hist[ch.source_id], (S, W)),
                                             dz_future], axis=1)
                    contrib = np.zeros((S, H + 1))
                    for t in range(H + 1):
                        window = dz_all[:, t: t + W]                             # times t-W..t-1: tau = W..1
                        contrib[:, t] = params.exists[:, c] * params.beta[:, c] * np.sum(window * params.g_rev[:, c, :], axis=1)
                    add = contrib - contrib[:, :1]
                    exo[ch.target_id] = exo.get(ch.target_id, 0.0) + add
                for key, val in exo.items():
                    old = prev_inputs.get(key)
                    if old is not None:
                        delta = max(delta, float(np.max(np.abs(val - old))))
                    else:
                        delta = max(delta, float(np.max(np.abs(val))) if val.size else 0.0)
                    prev_inputs[key] = val
                block_shocks = [s for s in shocks if owner.get(s.subentity_id) == b]
                system = build_system(own, ctx.wm, ctx, H, extra_subentities=members, drifts=model.drifts)
                res = self.propagator.propagate(system, block_shocks, n, rng, record_contributions=True, exogenous=exo)
                results[b] = res
                for s in members:
                    if res.has(s):
                        paths[s] = res.z_of(s)
            if delta < self.tol and _round > 0:
                break
        merged = {}
        for b in blocks:
            res = results[b]
            for s in res.subentity_index:
                if owner.get(s) == b:
                    merged[s] = res.z_of(s)
        sids = sorted(merged)
        z = np.stack([merged[s] for s in sids], axis=1) if sids else np.zeros((S, 0, H + 1))
        keys = sorted({k for r in results.values() for k in r.channel_index})
        contrib = np.zeros((z.shape[0], len(keys), H + 1))
        for j, k in enumerate(keys):
            for r in results.values():
                if k in r.channel_index:
                    contrib[:, j, :] = r.contrib_of(k)
        return PropagationResult({s: i for i, s in enumerate(sids)}, {k: i for i, k in enumerate(keys)}, z, contrib,
                                 chans, ctx.step_days)
