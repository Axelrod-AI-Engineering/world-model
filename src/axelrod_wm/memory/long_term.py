"""Long-term memory (§6.13, D15): Figure 1's four parts plus prior states.

| Figure 1                  | Field                       |
|---------------------------|-----------------------------|
| Object generalizations    | object_generalizations      | the object taxonomy and the superentity patterns it classifies
| Interaction generalizations | interaction_generalizations | the interaction taxonomy
| Entity memories           | entity_memories             | one EntityMemory per entity
| Correlation frontier      | correlation_frontier        | co-movements and blocked pairs
| Box title: prior states   | prior_states                | daily episodes and stored explanations

The attribute vocabulary is designer-provided and belongs to the construction spec, and exact past
states are snapshots in the SnapshotStore (§9), so neither is in here.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.graph import CausalGraph
from axelrod_wm.core.serialization import StrSet
from axelrod_wm.core.superentity import (
    SuperentityPattern,
    SuperentityStatus,
    SuperInteraction,
    SuperLinkKind,
)
from axelrod_wm.core.taxonomy import Taxonomy, TaxonomyKind
from axelrod_wm.engine.explain_records import Explanation
from axelrod_wm.memory.entity_memory import EntityMemory
from axelrod_wm.memory.frontier import CorrelationFrontier

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn


class Episode(BaseModel):
    """One consolidated day with applied events (§8.12)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    day: date
    trigger_event_ids: list[str]
    routine: bool                               # True if every event that day was a routine data release
    event_types: list[str] = []
    tags: list[str] = []                        # e.g. ["energy-shock-like"]
    signature: StrSet                           # generalization ids involved (objects and interactions)
    key_signature: StrSet                       # the same, from non-routine events only (all events if none)
    deltas: dict[str, tuple[float, float]]      # subentity -> (z at start of day, z at end of day)
    edge_effects: dict[str, tuple[float, float]]       # interaction id -> (implied effect, weight) that day
    response_effects: dict[str, tuple[float, float]] = {}   # non-routine only: pooled over the following
                                                            # episodes.analog_span_days (filled in by consolidation)
    response_deltas: dict[str, float] = {}      # non-routine only: change in z over the same span
    active_interaction_ids: list[str]
    active_pattern_ids: list[str]
    explanation_ids: list[str] = []
    day_index: int | None = None                # the day's index on the daily grid


class ObjectGeneralizations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taxonomy: Taxonomy                                   # kind OBJECT; instances are entities and patterns
    patterns: dict[str, SuperentityPattern] = {}        # superentity definitions (§6.8)
    super_interaction_labels: dict[str, str] = {}       # "S2->S1" -> label (seed file)
    palettes: dict[str, dict[str, str]] = {}            # palette key -> {"fill": ..., "line": ...}

    def admitted(self) -> list[SuperentityPattern]:
        return [p for _, p in sorted(self.patterns.items()) if p.status == SuperentityStatus.ADMITTED]

    def candidates(self) -> list[SuperentityPattern]:
        return [p for _, p in sorted(self.patterns.items()) if p.status == SuperentityStatus.CANDIDATE]


class InteractionGeneralizations(BaseModel):
    model_config = ConfigDict(extra="forbid")

    taxonomy: Taxonomy                                   # kind INTERACTION


class PriorStates(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episodes: dict[str, Episode] = {}
    explanations: dict[str, Explanation] = {}

    def by_generalization(self, gen_id: str) -> list[str]:
        return [eid for eid, ep in sorted(self.episodes.items()) if gen_id in ep.signature]

    def analog_candidates(self) -> list[Episode]:
        """Non-routine episodes."""
        return [ep for _, ep in sorted(self.episodes.items()) if not ep.routine]

    def by_index_key(self, key: str) -> list[str]:
        """Explanation ids."""
        return [eid for eid, ex in sorted(self.explanations.items()) if key in ex.index_keys]

    def by_tag(self, tag: str) -> list[str]:
        return [eid for eid, ep in sorted(self.episodes.items()) if tag in ep.tags]

    def index_keys_of(self, explanation_ids: list[str]) -> set[str]:
        out: set[str] = set()
        for eid in explanation_ids:
            ex = self.explanations.get(eid)
            if ex is not None:
                out |= set(ex.index_keys)
        return out


class LongTermMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_generalizations: ObjectGeneralizations
    interaction_generalizations: InteractionGeneralizations
    entity_memories: dict[str, EntityMemory] = {}
    correlation_frontier: CorrelationFrontier          # §8.7
    prior_states: PriorStates = PriorStates()

    def taxonomy(self, kind: Any) -> Taxonomy:
        return (self.object_generalizations.taxonomy if str(kind) == TaxonomyKind.OBJECT.value
                else self.interaction_generalizations.taxonomy)


# ---------------------------------------------------------------------------------------------
# Super-interactions (§6.8)
# ---------------------------------------------------------------------------------------------

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

    def compute(self, graph: CausalGraph, objects: ObjectGeneralizations) -> list[dict[str, Any]]:
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
                    label = objects.super_interaction_labels.get(f"{a.pattern_id}->{b.pattern_id}", best.label)
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

    def rebuild(self, graph: CausalGraph, objects: ObjectGeneralizations, txn: MutationTxn) -> list[str]:
        """Diff the desired super-interactions against the stored ones and write the changes.
        Ids are stable per (source, target, kind). Returns the ids that changed."""
        desired = self.compute(graph, objects)
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
                txn.add("wm.graph.super_interactions", SuperInteraction(id=sid, **spec))
                changed.append(sid)
            else:
                fields = {k: v for k, v in spec.items() if getattr(cur, k) != v}
                if fields:
                    txn.update("wm.graph.super_interactions", cur.id, **fields)
                    changed.append(cur.id)
        for key, cur in existing.items():
            if key not in seen:
                txn.remove("wm.graph.super_interactions", cur.id)
                changed.append(cur.id)
        return changed


__all__ = ["LongTermMemory", "Episode", "ObjectGeneralizations", "InteractionGeneralizations", "PriorStates",
           "SuperInteractionBuilder"]
