"""The causal graph: a pure data structure with indexes and no inference (§6.11)."""

from __future__ import annotations

import heapq
import math
from collections import defaultdict

import networkx as nx
from pydantic import BaseModel, ConfigDict

from axelrod_wm.model.entity import Entity, Subentity
from axelrod_wm.model.interaction import EdgeDynamics, Interaction
from axelrod_wm.model.serialization import digest
from axelrod_wm.model.superentity import SuperentityInstance, SuperInteraction


class EntityLink(BaseModel):
    """Entity-to-entity aggregation of subentity edges, for display."""

    model_config = ConfigDict(extra="forbid")

    source_entity_id: str
    target_entity_id: str
    label: str                        # from entity_link_labels (§14.3), else the most significant edge's label
    interaction_ids: list[str]
    significance: float


class CausalGraph(BaseModel):
    """Store and indexes for entities, subentities, interactions, superentity instances,
    and super-interactions. A pure data structure with no inference."""

    model_config = ConfigDict(extra="forbid")

    entities: dict[str, Entity] = {}
    subentities: dict[str, Subentity] = {}
    interactions: dict[str, Interaction] = {}
    instances: dict[str, SuperentityInstance] = {}
    super_interactions: dict[str, SuperInteraction] = {}
    entity_link_labels: dict[str, str] = {}   # "a->b" -> label (Figure 1's arrow labels)

    # ----- interactions --------------------------------------------------------------------
    def active_interactions(self) -> list[Interaction]:
        return [i for _, i in sorted(self.interactions.items()) if i.retired_at is None]

    def in_channels(self, subentity_id: str) -> list[tuple[str, str, EdgeDynamics]]:
        return [(s, t, d) for _, _, s, t, d in self.in_channel_items(subentity_id)]

    def out_channels(self, subentity_id: str) -> list[tuple[str, str, EdgeDynamics]]:
        out = []
        for inter in self.active_interactions():
            for _, s, t, d in inter.channel_items():
                if s == subentity_id:
                    out.append((s, t, d))
        return out

    def in_channel_items(self, subentity_id: str) -> list[tuple[str, Interaction, str, str, EdgeDynamics]]:
        """(channel key, interaction, source, target, dynamics) for channels into a subentity."""
        out = []
        for inter in self.active_interactions():
            for key, s, t, d in inter.channel_items():
                if t == subentity_id:
                    out.append((key, inter, s, t, d))
        return out

    def channel_items(self) -> list[tuple[str, Interaction, str, str, EdgeDynamics]]:
        out = []
        for inter in self.active_interactions():
            for key, s, t, d in inter.channel_items():
                out.append((key, inter, s, t, d))
        return out

    def interaction_between(self, a: str, b: str) -> list[str]:
        """Interaction ids that connect subentities a and b in either direction."""
        return [i.id for i in self.active_interactions()
                if (i.source_id == a and i.target_id == b) or (i.source_id == b and i.target_id == a)]

    def neighborhood(self, seeds: list[str], hops: int, min_significance: float) -> set[str]:
        """Subentities within `hops` undirected steps of the seeds along edges whose
        significance is at least `min_significance`."""
        adj: dict[str, set[str]] = defaultdict(set)
        for inter in self.active_interactions():
            if inter.significance_mean() >= min_significance:
                adj[inter.source_id].add(inter.target_id)
                adj[inter.target_id].add(inter.source_id)
        seen = {s for s in seeds if s in self.subentities}
        frontier = sorted(seen)
        for _ in range(max(hops, 0)):
            nxt = []
            for node in frontier:
                for nb in sorted(adj.get(node, ())):
                    if nb not in seen:
                        seen.add(nb)
                        nxt.append(nb)
            frontier = nxt
        return seen

    def hop_distances(self, seeds: list[str], max_hops: int = 8) -> dict[str, int]:
        """Undirected hop distance from the nearest seed subentity."""
        adj: dict[str, set[str]] = defaultdict(set)
        for inter in self.active_interactions():
            adj[inter.source_id].add(inter.target_id)
            adj[inter.target_id].add(inter.source_id)
        dist = {s: 0 for s in seeds}
        frontier = sorted(dist)
        for h in range(1, max_hops + 1):
            nxt = []
            for node in frontier:
                for nb in sorted(adj.get(node, ())):
                    if nb not in dist:
                        dist[nb] = h
                        nxt.append(nb)
            frontier = nxt
        return dist

    def directed_costs(self, seeds: list[str]) -> dict[str, float]:
        """Shortest directed path cost from any seed, with edge cost -log(max(significance, 1e-6))."""
        out_adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for inter in self.active_interactions():
            cost = -math.log(max(inter.significance_mean(), 1e-6))
            for _, s, t, _ in inter.channel_items():
                out_adj[s].append((t, cost))
        dist: dict[str, float] = {}
        heap = [(0.0, s) for s in sorted(set(seeds))]
        heapq.heapify(heap)
        while heap:
            d, node = heapq.heappop(heap)
            if node in dist:
                continue
            dist[node] = d
            for nb, c in out_adj.get(node, ()):
                if nb not in dist:
                    heapq.heappush(heap, (d + max(c, 0.0), nb))
        return dist

    # ----- superentities -------------------------------------------------------------------
    def members(self, instance_id: str) -> set[str]:
        """Entity ids of an instance, including those of its child instances."""
        out: set[str] = set()
        stack = [instance_id]
        seen: set[str] = set()
        while stack:
            iid = stack.pop()
            if iid in seen or iid not in self.instances:
                continue
            seen.add(iid)
            inst = self.instances[iid]
            out.update(inst.bindings.values())
            stack.extend(inst.child_instance_ids)
        return out

    def instances_of_entity(self, entity_id: str) -> list[str]:
        return [iid for iid in sorted(self.instances) if entity_id in self.members(iid)]

    def member_subentities(self, instance_id: str) -> set[str]:
        out: set[str] = set()
        for eid in self.members(instance_id):
            ent = self.entities.get(eid)
            if ent is not None:
                out.update(ent.subentity_ids)
        return out

    # ----- display -------------------------------------------------------------------------
    def entity_links(self) -> list[EntityLink]:
        groups: dict[tuple[str, str], list[tuple[str, float, str]]] = defaultdict(list)
        for inter in self.active_interactions():
            for _, s, t, _ in inter.channel_items():
                ss, tt = self.subentities.get(s), self.subentities.get(t)
                if ss is None or tt is None or ss.entity_id == tt.entity_id:
                    continue
                groups[(ss.entity_id, tt.entity_id)].append((inter.id, inter.significance_mean(), inter.label))
        links = []
        for (a, b), items in sorted(groups.items()):
            items.sort(key=lambda x: (-x[1], x[0]))
            label = self.entity_link_labels.get(f"{a}->{b}", items[0][2])
            ids = sorted({x[0] for x in items})
            links.append(EntityLink(source_entity_id=a, target_entity_id=b, label=label,
                                    interaction_ids=ids, significance=max(x[1] for x in items)))
        return links

    def to_networkx(self) -> nx.MultiDiGraph:
        g = nx.MultiDiGraph()
        for sid in sorted(self.subentities):
            g.add_node(sid, entity_id=self.subentities[sid].entity_id)
        for key, inter, s, t, d in self.channel_items():
            g.add_edge(s, t, key=key, interaction_id=inter.id, effect=d.effect.mean(),
                       significance=inter.significance_mean(),
                       cost=-math.log(max(inter.significance_mean(), 1e-6)))
        return g

    def content_hash(self) -> str:
        return digest(self)
