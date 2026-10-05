"""The pattern store and the super-interaction builder (§6.8, §6.13)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.graph import CausalGraph
from axelrod_wm.core.superentity import (
    SuperentityPattern,
    SuperentityStatus,
    SuperInteraction,
    SuperLinkKind,
)

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn


class PatternStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patterns: dict[str, SuperentityPattern] = {}
    super_interaction_labels: dict[str, str] = {}   # "S2->S1" -> label (seed file)
    palettes: dict[str, dict[str, str]] = {}        # palette key -> {"fill": ..., "line": ...}

    def admitted(self) -> list[SuperentityPattern]:
        return [p for _, p in sorted(self.patterns.items()) if p.status == SuperentityStatus.ADMITTED]

    def candidates(self) -> list[SuperentityPattern]:
        return [p for _, p in sorted(self.patterns.items()) if p.status == SuperentityStatus.CANDIDATE]


def _descendants(graph: CausalGraph, instance_id: str) -> set[str]:
    out: set[str] = set()
    stack = list(graph.instances[instance_id].child_instance_ids) if instance_id in graph.instances else []
    while stack:
        iid = stack.pop()
        if iid in out or iid not in graph.instances:
            continue
        out.add(iid)
        stack.extend(graph.instances[iid].child_instance_ids)
    return out


class SuperInteractionBuilder:
    """Recomputes super-interactions after every change to instance bindings (§6.8).

    An interaction is a boundary edge from instance A to instance B when its source entity is in
    A but not in B, and its target entity is in B but not in A. One CAUSAL super-interaction per
    ordered pair with boundary edges, one SHARES_MEMBERS per pair that shares entities.
    """

    def compute(self, graph: CausalGraph, patterns: PatternStore) -> list[dict[str, Any]]:
        insts = [i for _, i in sorted(graph.instances.items()) if not i.transient]
        members = {i.id: graph.members(i.id) for i in insts}
        related = {i.id: _descendants(graph, i.id) for i in insts}
        out: list[dict[str, Any]] = []
        channels = []
        for inter in graph.active_interactions():
            for _, s, t, _ in inter.channel_items():
                ss, tt = graph.subentities.get(s), graph.subentities.get(t)
                if ss is None or tt is None:
                    continue
                channels.append((inter, ss.entity_id, tt.entity_id))
        for a in insts:
            for b in insts:
                if a.id == b.id or b.id in related[a.id] or a.id in related[b.id]:
                    continue
                ma, mb = members[a.id], members[b.id]
                under = []
                for inter, se, te in channels:
                    if se in ma and se not in mb and te in mb and te not in ma:
                        under.append(inter)
                if under:
                    under_ids = sorted({i.id for i in under})
                    best = max(under, key=lambda i: (i.significance_mean(), i.id))
                    label = patterns.super_interaction_labels.get(f"{a.pattern_id}->{b.pattern_id}", best.label)
                    out.append({"source_instance_id": a.id, "target_instance_id": b.id,
                                "kind": SuperLinkKind.CAUSAL, "label": label,
                                "underlying_interaction_ids": under_ids, "shared_entity_ids": [],
                                "significance": max(i.significance_mean() for i in under)})
                if a.id < b.id:
                    shared = sorted(ma & mb)
                    if shared:
                        out.append({"source_instance_id": a.id, "target_instance_id": b.id,
                                    "kind": SuperLinkKind.SHARES_MEMBERS, "label": "share members",
                                    "underlying_interaction_ids": [], "shared_entity_ids": shared,
                                    "significance": 0.0})
        return out

    def rebuild(self, graph: CausalGraph, patterns: PatternStore, txn: MutationTxn) -> list[str]:
        """Diff the desired super-interactions against the stored ones and write the changes.
        Ids are stable per (source, target, kind). Returns the ids that changed."""
        desired = self.compute(graph, patterns)
        existing = {(s.source_instance_id, s.target_instance_id, str(s.kind)): s
                    for _, s in sorted(graph.super_interactions.items())}
        changed: list[str] = []
        seen: set[tuple[str, str, str]] = set()
        for spec in desired:
            key = (spec["source_instance_id"], spec["target_instance_id"], str(spec["kind"]))
            seen.add(key)
            cur = existing.get(key)
            if cur is None:
                sid = txn.new_id("sup")
                txn.add("super_interactions", SuperInteraction(id=sid, **spec))
                changed.append(sid)
            else:
                fields = {k: v for k, v in spec.items() if getattr(cur, k) != v}
                if fields:
                    txn.update("super_interactions", cur.id, **fields)
                    changed.append(cur.id)
        for key, cur in existing.items():
            if key not in seen:
                txn.remove("super_interactions", cur.id)
                changed.append(cur.id)
        return changed
