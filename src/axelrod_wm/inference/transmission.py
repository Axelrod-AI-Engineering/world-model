"""Transmission (addition): how a thesis's shock travels through the graph, value by value.

Every value the forecast reaches gets
- its order: the fewest interactions between a shocked value and it. A first-order effect is direct; a
  second-order effect passes through one intermediate value; a third-order effect through two; and so on;
- its transmission path: the most significant path of that length (significance is the product, over the
  path's interactions, of the belief that the interaction exists times the size of its mean effect);
- when the effect arrives (the sum of the path's delays) and when it peaks, from the simulated effect;
- its size at the horizon and at its peak, as medians over the forecast's scenario mixture."""
from __future__ import annotations

from collections import deque
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.dynamics.kernels import mean_kernel_days

MATERIAL_SD = 0.05      # an effect at least this large (at its peak or at the horizon) is reported as material


class TransmissionHop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_id: str          # the channel key ("<interaction id>:rev" for a reverse channel)
    source_id: str
    target_id: str
    effect: float                # mean effect, sd of the target per sd of the source
    delay_days: int


class TransmissionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subentity_id: str
    order: int
    shock_id: str
    effect: float                # median effect at the horizon (sd)
    peak: float                  # median effect at its largest (sd)
    peak_day: int
    arrives_day: int             # the sum of the delays along the path
    path: list[TransmissionHop]
    material: bool


def _sig(ch: Any) -> float:
    from axelrod_wm.model.interaction import abs_mean

    return float(ch.existence.mean()) * float(abs_mean(ch.dynamics.effect))


def transmission_map(shocked: list[str], channels: list[Any], effect_of: Any, horizon: int,
                     min_delay: int = 1, max_order: int = 6, limit: int = 240) -> list[TransmissionEntry]:
    """`effect_of(sid)` returns the effect paths [samples, horizon + 1] of one subentity."""
    best_edge: dict[tuple[str, str], Any] = {}
    for ch in channels:
        if ch.forced is False:
            continue
        key = (ch.source_id, ch.target_id)
        if key not in best_edge or _sig(ch) > _sig(best_edge[key]):
            best_edge[key] = ch
    out_edges: dict[str, list[Any]] = {}
    for (s, _t), ch in sorted(best_edge.items()):
        out_edges.setdefault(s, []).append(ch)
    # order: breadth-first distance from the nearest shocked value
    dist = {s: 0 for s in shocked}
    q = deque(shocked)
    while q:
        u = q.popleft()
        if dist[u] >= max_order:
            continue
        for ch in out_edges.get(u, []):
            if ch.target_id not in dist:
                dist[ch.target_id] = dist[u] + 1
                q.append(ch.target_id)
    # the most significant path among the shortest ones: one pass over the layers
    best: dict[str, tuple[float, Any | None, str]] = {s: (1.0, None, s) for s in shocked}
    for u in sorted(dist, key=lambda x: (dist[x], x)):      # each value at order d was reached from one at d - 1
        score, _prev, origin = best[u]
        for ch in out_edges.get(u, []):
            v = ch.target_id
            if dist.get(v) != dist[u] + 1:
                continue
            cand = score * _sig(ch)
            if v not in best or cand > best[v][0]:
                best[v] = (cand, ch, origin)
    shocked_set = set(shocked)
    entries: list[TransmissionEntry] = []
    for sid, order in dist.items():
        if sid in shocked_set or sid not in best:
            continue
        hops: list[TransmissionHop] = []
        cur = sid
        while best[cur][1] is not None:
            ch = best[cur][1]
            d, _l, _lam = mean_kernel_days(ch.dynamics.kernel, min_delay)
            hops.append(TransmissionHop(interaction_id=ch.channel_key, source_id=ch.source_id, target_id=ch.target_id,
                                        effect=round(float(ch.dynamics.effect.mean()), 4), delay_days=int(d)))
            cur = ch.source_id
        hops.reverse()
        paths = effect_of(sid)
        med = np.median(paths, axis=0) if paths.size else np.zeros(horizon + 1)
        k = int(np.argmax(np.abs(med))) if med.size else 0
        peak = float(med[k]) if med.size else 0.0
        at_h = float(med[min(horizon, med.size - 1)]) if med.size else 0.0
        entries.append(TransmissionEntry(
            subentity_id=sid, order=order, shock_id=best[sid][2], effect=round(at_h, 4), peak=round(peak, 4),
            peak_day=k, arrives_day=int(sum(h.delay_days for h in hops)), path=hops,
            material=max(abs(peak), abs(at_h)) >= MATERIAL_SD))
    entries.sort(key=lambda e: (e.order, -abs(e.peak), e.subentity_id))
    return entries[:limit]
