"""Generalization updates: long-term learning's statistics on the kinds (§8.6.2).

Every node on an item's classification path gains support, plus the statistics its prior is built from
(attribute levels and scales for entities, effects and kernels for interactions, relation effects for
superentity patterns). Input: classifications. Writes long-term memory (the taxonomies) only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from axelrod_wm.engine.interfaces import Classification
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.model.taxonomy import RunningStats, TaxonomyKind, relation_key
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.repo.mutator import MutationTxn

OBJECT_NODES = "ltm.object_generalizations.taxonomy.nodes"
INTERACTION_NODES = "ltm.interaction_generalizations.taxonomy.nodes"


class GeneralizationUpdater(ABC):
    @abstractmethod
    def update(self, classifications: list[Classification], ltm: LongTermMemory,
               ctx: ProcessContext, txn: MutationTxn) -> None: ...


registry("generalization_updater", GeneralizationUpdater)


def pattern_relation_effects(pattern_id: str, wm: WorkingMemory) -> list[tuple[str, float]]:
    """(relation key, effect mean) for the realized relations of a pattern's bound instances."""
    graph = wm.graph
    out = []
    for iid in sorted(graph.instances):
        inst = graph.instances[iid]
        if inst.pattern_id != pattern_id or inst.transient:
            continue
        for int_id in inst.interaction_ids:
            inter = graph.interactions.get(int_id)
            if inter is None or inter.retired_at is not None:
                continue
            s, t = graph.subentities.get(inter.source_id), graph.subentities.get(inter.target_id)
            if s is None or t is None:
                continue
            out.append((relation_key(s.attribute_kind, t.attribute_kind, inter.polarity()),
                        inter.forward.effect.mean()))
    return out


@register("generalization_updater", "path_stats")
class PathStatsUpdater(GeneralizationUpdater):
    """For every node on each classification path: support += 1, plus attribute, edge, or pattern
    statistics (§8.6.2)."""

    def __init__(self, config: Any = None) -> None:
        self.config = config

    def update(self, classifications: list[Classification], ltm: LongTermMemory,
               ctx: ProcessContext, txn: MutationTxn) -> None:
        if not ctx.learn:
            return
        graph = ctx.wm.graph
        patterns = ltm.object_generalizations.patterns
        pending: dict[tuple[str, str], Any] = {}
        for c in classifications:
            tax = ltm.taxonomy(c.taxonomy)
            coll = OBJECT_NODES if c.taxonomy == TaxonomyKind.OBJECT else INTERACTION_NODES
            for gid in c.path:
                if gid not in tax.nodes:
                    continue
                key = (coll, gid)
                st = pending.get(key)
                if st is None:
                    st = pending[key] = tax.nodes[gid].stats.model_copy(deep=True)
                st.support += 1.0
                if c.taxonomy == TaxonomyKind.OBJECT and c.item_id in graph.entities:
                    for sid in graph.entities[c.item_id].subentity_ids:
                        sub = graph.subentities.get(sid)
                        if sub is None:
                            continue
                        m, _ = sub.posterior.link_moments()
                        st.attribute_level.setdefault(sub.attribute_kind, RunningStats()).push(m)
                        st.attribute_scale.setdefault(sub.attribute_kind, RunningStats()).push(sub.scale)
                elif c.taxonomy == TaxonomyKind.OBJECT and c.item_id in patterns:
                    for rkey, eff in pattern_relation_effects(c.item_id, ctx.wm):
                        st.relation_effects.setdefault(rkey, RunningStats()).push(eff)
                elif c.taxonomy == TaxonomyKind.INTERACTION and c.item_id in graph.interactions:
                    inter = graph.interactions[c.item_id]
                    st.effect.push(inter.forward.effect.mean())
                    d, l, dur = inter.forward.kernel.means()
                    st.delay_days.push(d)
                    st.lag_days.push(l)
                    if dur is None:
                        st.duration_permanent += 1.0
                    else:
                        st.duration_days.push(dur)
                    p = inter.existence.mean()
                    st.existence_alpha += 0.1 * p
                    st.existence_beta += 0.1 * (1 - p)
        self._write(pending, ctx, txn)

    def update_pattern(self, pattern_id: str, ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn, *,
                       count_support: bool = True, hits: float = 0.0, misses: float = 0.0) -> None:
        """The path update for a superentity pattern at a counted support increment (support += 1 and
        its realized relations' effects) or a track-record change (hits and misses only).
        # DECISION: a track-record change alone does not add support to the path's nodes."""
        pat = ltm.object_generalizations.patterns.get(pattern_id)
        tax = ltm.object_generalizations.taxonomy
        if pat is None or not pat.generalization_id or pat.generalization_id not in tax.nodes:
            return
        effects = pattern_relation_effects(pattern_id, ctx.wm) if count_support else []
        pending: dict[tuple[str, str], Any] = {}
        for gid in tax.path_from_root(pat.generalization_id):
            st = tax.nodes[gid].stats.model_copy(deep=True)
            if count_support:
                st.support += 1.0
                for rkey, eff in effects:
                    st.relation_effects.setdefault(rkey, RunningStats()).push(eff)
            st.track_hits += hits
            st.track_misses += misses
            pending[(OBJECT_NODES, gid)] = st
        self._write(pending, ctx, txn)

    @staticmethod
    def _write(pending: dict[tuple[str, str], Any], ctx: ProcessContext, txn: MutationTxn) -> None:
        for (coll, gid), st in sorted(pending.items()):
            txn.update(coll, gid, stats=st)
        if pending:
            ctx.tracer.emit(Phase.GENERALIZE, "generalize.updated", refs=[g for _, g in sorted(pending)],
                            supports={g: round(st.support, 3) for (_, g), st in sorted(pending.items())})
