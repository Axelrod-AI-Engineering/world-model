"""Forecasts at several granularities (addition). A thesis can ask about an entity (NVIDIA), a
superentity (S2), a sector (airlines), or a category (spending and demand) as well as single
subentities. A group's forecast is the average standardized effect of its subentities, computed sample
by sample from the same scenario mixture as the targets, so its uncertainty is honest: members that
move together widen it, members that offset narrow it."""

from __future__ import annotations

from typing import Any

import numpy as np

from axelrod_wm.core.categories import CATEGORY_NAMES
from axelrod_wm.core.distributions import density_of_samples, summarize_columns
from axelrod_wm.engine.performance.records import ForecastGroup, ForecastScenario
from axelrod_wm.engine.performance.unify import largest_remainder
from axelrod_wm.engine.propagation import PropagationResult
from axelrod_wm.events.thesis import TargetGroup


def resolve_group(group: TargetGroup, wm: Any, ltm: Any) -> tuple[str, list[str]] | None:
    """A group's display name and member subentities, or None if the reference is unknown."""
    g = wm.graph
    if group.kind == "entity":
        e = g.entities.get(group.ref)
        if e is None:
            return None
        return e.name, [s for s in e.subentity_ids if s in g.subentities]
    if group.kind == "superentity":
        p = ltm.object_generalizations.patterns.get(group.ref)
        if p is None:
            return None
        insts = [i for _, i in sorted(g.instances.items()) if i.pattern_id == p.id and not i.transient]
        # DECISION: the instance the seeds bound, else the most active one (as the demo draws it); its
        # members are the subentities its relations run through, which is what the pattern is about
        inst = next((i for i in insts if i.id == f"inst-{p.id}"), None) or \
            max(insts, key=lambda i: (i.activation, i.id), default=None)
        subs: set[str] = set()
        if inst is not None:
            for iid in inst.interaction_ids:
                inter = g.interactions.get(iid)
                if inter is not None:
                    subs |= {inter.source_id, inter.target_id}
            if not subs:
                for e in set(inst.bindings.values()):
                    if e in g.entities:
                        subs |= set(g.entities[e].subentity_ids)
        return f"{p.id} · {p.name}", sorted(s for s in subs if s in g.subentities)
    if group.kind == "sector":
        ents = [e for _, e in sorted(g.entities.items()) if e.features.get("sector", "").lower() == group.ref.lower()]
        if not ents:
            return None
        return group.ref.replace("_", " ").capitalize(), [s for e in ents for s in e.subentity_ids if s in g.subentities]
    if group.kind == "category":
        code = group.ref.upper()
        if code not in CATEGORY_NAMES:
            return None
        ents = [e for _, e in sorted(g.entities.items()) if code in {str(t) for t in e.category_tags}]
        return CATEGORY_NAMES[code].capitalize(), [s for e in ents for s in e.subentity_ids if s in g.subentities]
    return None


class EffectMixture:
    """Each subentity's effect paths [samples, H + 1], drawn from the scenarios in proportion to their
    weights with the unifier's sample counts, so groups and targets mix alike."""

    def __init__(self, scenarios: list[ForecastScenario], coupled: dict[str, PropagationResult],
                 baseline: dict[str, PropagationResult], samples: int, horizon: int) -> None:
        self.H = horizon
        weights = [s.weight for s in scenarios]
        counts = largest_remainder(samples, weights) if scenarios else []
        self.parts = [(coupled[s.id], baseline[s.id], min(n, coupled[s.id].n_samples))
                      for s, n in zip(scenarios, counts) if n > 0]

    def _paths(self, res: PropagationResult, sid: str, n: int) -> np.ndarray | None:
        if not res.has(sid):
            return None
        z = res.z_of(sid)[:n]
        if z.shape[1] < self.H + 1:
            z = np.pad(z, ((0, 0), (0, self.H + 1 - z.shape[1])), mode="edge")
        return z[:, : self.H + 1]

    def effect(self, sid: str) -> np.ndarray:
        out = []
        for on, off, n in self.parts:
            a = self._paths(on, sid, n)
            b = self._paths(off, sid, n)
            if a is None or b is None:
                out.append(np.zeros((n, self.H + 1)))      # not in the scenario's networks: no effect
            else:
                out.append(a - b)
        return np.concatenate(out, axis=0) if out else np.zeros((1, self.H + 1))


def group_forecasts(thesis: Any, targets: list[str], mix: EffectMixture, wm: Any,
                    ltm: Any) -> tuple[list[ForecastGroup], dict[str, list[list[float]]]]:
    """The thesis's coarser targets, and a small density of each target's effect at the horizon."""
    H = mix.H
    densities = {sid: density_of_samples(mix.effect(sid)[:, H]) for sid in targets}
    # DECISION: a group's forecast is its response, so the subentities the thesis itself shocks are left
    # out of the average (a doubled oil price would otherwise dominate any group that holds it)
    shocked = {op.target.subentity_id for op in thesis.event.ops
               if getattr(op, "op", "") == "change_value" and getattr(op.target, "kind", "") == "concrete"}
    groups = []
    for grp in getattr(thesis, "target_groups", []) or []:
        resolved = resolve_group(grp, wm, ltm)
        if resolved is None or not resolved[1]:
            continue
        name, members = resolved
        members = [m for m in members if m not in shocked] or members
        total = None
        at_h = []
        for sid in members:
            ef = mix.effect(sid)
            total = ef if total is None else total + ef
            at_h.append((sid, float(np.median(ef[:, H]))))
        mean = total / len(members)
        top = sorted(at_h, key=lambda x: (-abs(x[1]), x[0]))[:5]
        groups.append(ForecastGroup(id=grp.id, kind=grp.kind, ref=grp.ref, name=name, members=members,
                                    effect_summary=summarize_columns(mean), effect_density=density_of_samples(mean[:, H]),
                                    top=[[sid, round(v, 4)] for sid, v in top]))
    return groups, densities


def movers(mix: EffectMixture, coupled: dict[str, PropagationResult], shocked: set[str],
           top_n: int = 24, floor: float = 0.02) -> dict[str, float]:
    """The subentities the forecast moves most: the median effect at the horizon of every subentity in
    the coupled runs, from the same mixture as the targets (the shocked ones left out)."""
    sids = sorted({s for r in coupled.values() for s in r.subentity_index} - set(shocked))
    H = mix.H
    out = {sid: float(np.median(mix.effect(sid)[:, H])) for sid in sids}
    ranked = sorted(((k, v) for k, v in out.items() if abs(v) >= floor), key=lambda kv: (-abs(kv[1]), kv[0]))[:top_n]
    return {k: round(v, 4) for k, v in ranked}
