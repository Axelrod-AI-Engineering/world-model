"""Superentities: binding and abduction (§8.8, D9).

Records and interfaces. The default binder and inducer live in ``engine.abduction_impl`` and
are registered when the engine loads its defaults.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.superentity import PatternRelation
from axelrod_wm.engine.registry import registry

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.core.graph import CausalGraph
    from axelrod_wm.core.superentity import SuperentityPattern
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import RecallResult
    from axelrod_wm.engine.shared import ParsedEvent
    from axelrod_wm.memory.episodes import Episode
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bindings: dict[str, str]                  # role -> entity id
    interaction_ids: list[str]
    absent_interaction_ids: list[str]         # concrete edges a present=False relation says are absent
    missing_relations: list[PatternRelation]  # present relations with no concrete edge yet
    coverage: float                           # realized present relations / present relations
    significance: float = 0.0


class PatternBinder(ABC):
    @abstractmethod
    def bind(self, pattern: SuperentityPattern, seed_entity_ids: list[str], graph: CausalGraph,
             ltm: LongTermMemory) -> Binding | None: ...


class InductionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bound_instance_ids: list[str] = []
    candidate_pattern_ids: list[str] = []
    proposals: list[str] = []
    dissolved_instance_ids: list[str] = []
    supported_pattern_ids: list[str] = []
    proposal_events: list[dict] = []          # proposals to queue: {"kind", "event", "reason"}


class SuperentityInducer(ABC):
    @abstractmethod
    def bind(self, parsed: ParsedEvent, recall: RecallResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn | None) -> InductionResult:
        """During prefill: bind recalled admitted patterns to the event's entities, refresh
        activations, and dissolve instances whose pattern was dissolved or whose edges were
        retired. Bindings made for hypothetical events are transient."""

    @abstractmethod
    def count(self, episode: Episode, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn) -> InductionResult:
        """At consolidation: count support from the episode's activity, form candidates,
        propose admissions and dissolutions, and find compositions."""


registry("binder", PatternBinder)
registry("inducer", SuperentityInducer)


# =============================================================================================
# Default implementations
# =============================================================================================

import math  # noqa: E402
from typing import Any  # noqa: E402

import networkx as nx  # noqa: E402

from axelrod_wm.core.evidence import Origin  # noqa: E402
from axelrod_wm.core.superentity import (  # noqa: E402
    RoleSpec,
    SuperentityInstance,
    SuperentityPattern,
    SuperentityStatus,
)
from axelrod_wm.core.temporal import Bitemporal, TimeState  # noqa: E402
from axelrod_wm.engine.registry import register  # noqa: E402
from axelrod_wm.memory.patterns import SuperInteractionBuilder  # noqa: E402
from axelrod_wm.trace import Phase  # noqa: E402

EXTRA_PALETTE = ["#E9DDB5", "#D8E2C8", "#F0D9C4", "#D4DFEA", "#E8D5DF", "#D5E8E4", "#EDE3CC", "#DCD9E6"]


def entity_path(entity_id: str, graph: CausalGraph, ltm: LongTermMemory) -> list[str]:
    ent = graph.entities.get(entity_id)
    if ent is None or not ent.generalization_id or ent.generalization_id not in ltm.object_taxonomy.nodes:
        return [ltm.object_taxonomy.root_id] if ltm.object_taxonomy.root_id else []
    return ltm.object_taxonomy.path_from_root(ent.generalization_id)


def deepest_supported_up(tax: Any, gen_id: str | None, threshold: float) -> str:
    """The deepest node at or above `gen_id` whose support exceeds the threshold (the root if none)."""
    if not gen_id or gen_id not in tax.nodes:
        return tax.root_id
    return tax.deepest_supported(tax.path_from_root(gen_id), threshold)


def _subs_of_kind(entity_id: str, attr: str, graph: CausalGraph, vocab: Any) -> list[str]:
    ent = graph.entities.get(entity_id)
    if ent is None:
        return []
    return [s for s in ent.subentity_ids if s in graph.subentities
            and vocab.is_a(graph.subentities[s].attribute_kind, attr)]


def realizations(rel: PatternRelation, src_entity: str, tgt_entity: str, graph: CausalGraph, vocab: Any) -> list[str]:
    """Concrete interactions realizing a relation between two bound entities."""
    srcs = set(_subs_of_kind(src_entity, rel.source_attr, graph, vocab))
    tgts = set(_subs_of_kind(tgt_entity, rel.target_attr, graph, vocab))
    out = []
    for inter in graph.active_interactions():
        if inter.source_id in srcs and inter.target_id in tgts:
            if rel.present and inter.polarity() != rel.polarity:
                continue
            out.append(inter.id)
    return out


@register("binder", "bfs_role_filling")
class BfsRoleFillingBinder(PatternBinder):
    def __init__(self, config: Any = None, min_binding_coverage: float | None = None) -> None:
        ab = getattr(config, "abduction", None)
        self.min_cov = float(min_binding_coverage if min_binding_coverage is not None
                             else getattr(ab, "min_binding_coverage", 0.6))

    def _partner(self, entity: str, rel: PatternRelation, outward: bool, role: RoleSpec, used: set[str],
                 graph: CausalGraph, ltm: LongTermMemory) -> str | None:
        vocab = ltm.attributes
        best: tuple[float, str] | None = None
        mine = set(_subs_of_kind(entity, rel.source_attr if outward else rel.target_attr, graph, vocab))
        for inter in graph.active_interactions():
            if rel.present and inter.polarity() != rel.polarity:
                continue
            here, there = (inter.source_id, inter.target_id) if outward else (inter.target_id, inter.source_id)
            if here not in mine:
                continue
            other = graph.subentities.get(there)
            if other is None or other.entity_id in used:
                continue
            want_attr = rel.target_attr if outward else rel.source_attr
            if not vocab.is_a(other.attribute_kind, want_attr):
                continue
            if role.generalization_id not in entity_path(other.entity_id, graph, ltm):
                continue
            key = (inter.significance_mean(), other.entity_id)
            if best is None or key[0] > best[0] or (key[0] == best[0] and key[1] < best[1]):
                best = key
        return best[1] if best else None

    def bind(self, pattern: SuperentityPattern, seed_entity_ids: list[str], graph: CausalGraph,
             ltm: LongTermMemory) -> Binding | None:
        roles = {r.name: r for r in pattern.roles}
        best: Binding | None = None
        for seed in sorted(set(seed_entity_ids)):
            if seed not in graph.entities:
                continue
            path = entity_path(seed, graph, ltm)
            for role in pattern.roles:
                if role.generalization_id not in path:
                    continue
                bindings = {role.name: seed}
                for _ in range(3):
                    progress = False
                    for rel in pattern.relations:
                        for bound, other, outward in ((rel.source_role, rel.target_role, True),
                                                      (rel.target_role, rel.source_role, False)):
                            if bound in bindings and other not in bindings and other in roles:
                                cand = self._partner(bindings[bound], rel, outward, roles[other],
                                                     set(bindings.values()), graph, ltm)
                                if cand is not None:
                                    bindings[other] = cand
                                    progress = True
                    if not progress:
                        break
                b = self.evaluate(pattern, bindings, graph, ltm)
                if b.coverage + 1e-12 < self.min_cov:
                    continue
                if best is None or (b.coverage, b.significance) > (best.coverage, best.significance):
                    best = b
        return best

    def evaluate(self, pattern: SuperentityPattern, bindings: dict[str, str], graph: CausalGraph,
                 ltm: LongTermMemory) -> Binding:
        present = [r for r in pattern.relations if r.present]
        realized: list[str] = []
        absent: list[str] = []
        missing: list[PatternRelation] = []
        n_ok = 0
        for rel in pattern.relations:
            if rel.source_role not in bindings or rel.target_role not in bindings:
                continue
            ids = realizations(rel, bindings[rel.source_role], bindings[rel.target_role], graph, ltm.attributes)
            if rel.present:
                if ids:
                    n_ok += 1
                    realized.extend(i for i in ids if i not in realized)
                else:
                    missing.append(rel)
            else:
                absent.extend(i for i in ids if i not in absent)
        coverage = n_ok / len(present) if present else 1.0
        sig = sum(graph.interactions[i].significance_mean() for i in realized)
        return Binding(bindings=dict(sorted(bindings.items())), interaction_ids=realized, absent_interaction_ids=absent,
                       missing_relations=missing, coverage=coverage, significance=sig)


def relation_tuple(rel: PatternRelation, roles: dict[str, RoleSpec], ltm: LongTermMemory, thr: float) -> tuple:
    src_gen = deepest_supported_up(ltm.object_taxonomy, roles[rel.source_role].generalization_id
                                   if rel.source_role in roles else None, thr)
    tgt_gen = deepest_supported_up(ltm.object_taxonomy, roles[rel.target_role].generalization_id
                                   if rel.target_role in roles else None, thr)
    int_gen = deepest_supported_up(ltm.interaction_taxonomy, rel.interaction_generalization_id, thr)
    return (src_gen, rel.source_attr, int_gen, tgt_gen, rel.target_attr, str(rel.polarity))


def pattern_tuples(p: SuperentityPattern, ltm: LongTermMemory, thr: float) -> set[tuple]:
    roles = {r.name: r for r in p.roles}
    return {relation_tuple(r, roles, ltm, thr) for r in p.relations if r.present}


def absent_tuples(p: SuperentityPattern, ltm: LongTermMemory, thr: float) -> set[tuple]:
    roles = {r.name: r for r in p.roles}
    return {relation_tuple(r, roles, ltm, thr) for r in p.relations if not r.present}


def interaction_tuple(iid: str, graph: CausalGraph, ltm: LongTermMemory, thr: float) -> tuple:
    inter = graph.interactions[iid]
    src = graph.subentities[inter.source_id]
    tgt = graph.subentities[inter.target_id]
    src_gen = deepest_supported_up(ltm.object_taxonomy, graph.entities[src.entity_id].generalization_id, thr)
    tgt_gen = deepest_supported_up(ltm.object_taxonomy, graph.entities[tgt.entity_id].generalization_id, thr)
    int_gen = deepest_supported_up(ltm.interaction_taxonomy, inter.generalization_id, thr)
    return (src_gen, src.attribute_kind, int_gen, tgt_gen, tgt.attribute_kind, str(inter.polarity()))


def _jac(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def _boundary_edges(graph: CausalGraph, a: str, b: str) -> set[str]:
    ma, mb = graph.members(a), graph.members(b)
    out = set()
    for inter in graph.active_interactions():
        for _, s, t, _ in inter.channel_items():
            se, te = graph.subentities[s].entity_id, graph.subentities[t].entity_id
            if (se in ma and se not in mb and te in mb and te not in ma) or (
                    se in mb and se not in ma and te in ma and te not in mb):
                out.add(inter.id)
    return out


@register("inducer", "co_activation")
class CoActivationInducer(SuperentityInducer):
    def __init__(self, config: Any = None, binder: PatternBinder | None = None) -> None:
        self.config = config
        self.binder = binder or BfsRoleFillingBinder(config)
        self.builder = SuperInteractionBuilder()

    # -- bind (during prefill) ---------------------------------------------------------------
    def bind(self, parsed: ParsedEvent, recall: RecallResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn | None) -> InductionResult:
        from axelrod_wm.engine.recall import near_instance

        res = InductionResult()
        if ctx.initializing:
            return res
        real = txn is not None
        graph = wm.graph
        changed = False
        if real:
            for iid in sorted(graph.instances):
                inst = graph.instances[iid]
                pat = ltm.patterns.patterns.get(inst.pattern_id)
                retired = any(graph.interactions.get(i) is None or graph.interactions[i].retired_at is not None
                              for i in inst.interaction_ids)
                if pat is None or pat.status == SuperentityStatus.DISSOLVED or retired:
                    txn.remove("instances", iid)
                    res.dissolved_instance_ids.append(iid)
                    changed = True
                    ctx.tracer.emit(Phase.PREFILL, "induce.dissolved", refs=[iid, inst.pattern_id], instance_id=iid,
                                    pattern_id=inst.pattern_id, transient=False)
        if real and parsed.is_routine():
            if changed:
                self.builder.rebuild(graph, ltm.patterns, txn)
            return res
        touched = set(parsed.touched_entity_ids)
        thr = ctx.recall_threshold
        for s in recall.superentities:
            p = ltm.patterns.patterns.get(s.pattern_id)
            if p is None or p.status != SuperentityStatus.ADMITTED or p.sub_pattern_ids:
                continue
            if near_instance(p.id, wm, touched):
                continue
            b = self.binder.bind(p, sorted(touched), graph, ltm)
            if b is None:
                continue
            if real:
                iid = txn.new_id("inst")
                inst = SuperentityInstance(id=iid, pattern_id=p.id, bindings=b.bindings, interaction_ids=b.interaction_ids,
                                           absent_interaction_ids=b.absent_interaction_ids)
                txn.add("instances", inst)
                changed = True
                self._missing_relations(p, b, wm, ltm, ctx, txn, res, thr)
            else:
                iid = ctx.overlay.next_id("inst")  # type: ignore[union-attr]
                inst = SuperentityInstance(id=iid, pattern_id=p.id, bindings=b.bindings, interaction_ids=b.interaction_ids,
                                           absent_interaction_ids=b.absent_interaction_ids, transient=True)
                ctx.overlay.put("instances", inst)  # type: ignore[union-attr]
            res.bound_instance_ids.append(iid)
            ctx.tracer.emit(Phase.PREFILL, "induce.bound", refs=[iid, p.id] + sorted(set(b.bindings.values())),
                            instance_id=iid, pattern_id=p.id, members=sorted(set(b.bindings.values())),
                            coverage=round(b.coverage, 3), transient=not real)
        if real and changed:
            self.builder.rebuild(graph, ltm.patterns, txn)
        return res

    def _missing_relations(self, p: SuperentityPattern, b: Binding, wm: WorkingMemory, ltm: LongTermMemory,
                           ctx: ProcessContext, txn: MutationTxn, res: InductionResult, thr: float) -> None:
        from axelrod_wm.events.graph_update import AddInteraction, ConcreteTarget, EventKind, GraphUpdateEvent

        cool = float(ctx.config.abduction.missing_relation_cooldown_days)
        graph = wm.graph
        for rel in b.missing_relations:
            gid = rel.interaction_generalization_id
            node = ltm.interaction_taxonomy.nodes.get(gid) if gid else None
            if node is None or node.stats.support <= thr:
                continue
            idx = p.relations.index(rel)
            key = f"{p.id}#{idx}"
            last = wm.missing_relation_log.get(key)
            if last is not None and (ctx.now - last).total_seconds() < cool * 86400:
                continue
            srcs = _subs_of_kind(b.bindings[rel.source_role], rel.source_attr, graph, ltm.attributes)
            tgts = _subs_of_kind(b.bindings[rel.target_role], rel.target_attr, graph, ltm.attributes)
            if not srcs or not tgts:
                continue
            dyn, existence = node.prior_dynamics()
            from axelrod_wm.core.distributions import Gaussian
            from axelrod_wm.core.interaction import EdgeDynamics

            mu = float(rel.polarity) * max(abs(dyn.effect.mean()), 0.1)
            dyn = EdgeDynamics(effect=Gaussian(mu=mu, sigma=dyn.effect.sd()), kernel=dyn.kernel)
            ev = GraphUpdateEvent(
                id=f"GUE-MR-{p.id}-{idx}-{ctx.now.strftime('%Y%m%d')}", kind=EventKind.REAL, event_type="missing_relation",
                occurred_at=ctx.now, recorded_at=ctx.now, produced_by="engine", confidence=0.5,
                ops=[AddInteraction(source=ConcreteTarget(subentity_id=srcs[0]), target=ConcreteTarget(subentity_id=tgts[0]),
                                    label=rel.label, polarity=rel.polarity, interaction_generalization_id=gid,
                                    dynamics=dyn, existence=existence)])
            txn.merge("wm.missing_relation_log", {key: ctx.now})
            res.proposal_events.append({"kind": "missing_relation", "event": ev.model_dump(mode="json"),
                                        "reason": f"pattern {p.id} ({p.name}) predicts {rel.label}"})

    # -- count (at consolidation) ------------------------------------------------------------
    def count(self, episode: Episode, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn) -> InductionResult:
        res = InductionResult()
        cfg = ctx.config.abduction
        rec = ctx.recognition
        thr = ctx.recall_threshold
        init = ctx.initializing
        graph = wm.graph
        now = ctx.now
        instances_changed = False

        # 1-2. active edges and their components
        active: dict[str, list[Any]] = {}
        for r in wm.activity_log:
            inter = graph.interactions.get(r.interaction_id)
            if inter is None or inter.retired_at is not None:
                continue
            if r.target_move is None or r.contribution * r.target_move > 0:   # unobserved counts as agreeing
                active.setdefault(r.interaction_id, []).append(r)
        g = nx.Graph()
        for iid in sorted(active):
            inter = graph.interactions[iid]
            g.add_edge(inter.source_id, inter.target_id)
        comps = []
        for nodes in sorted((sorted(c) for c in nx.connected_components(g)), key=lambda c: c[0]):
            node_set = set(nodes)
            edges = sorted(i for i in active if graph.interactions[i].source_id in node_set)
            if len(edges) < 2:
                continue
            contrib = sum(abs(r.contribution) for i in edges for r in active[i])
            moves: dict[tuple[str, int], float] = {}
            for i in edges:
                for r in active[i]:
                    if r.target_move is not None:
                        moves[(r.target_id or graph.interactions[i].target_id, r.step)] = abs(r.target_move)
            total_move = sum(moves.values())
            explained = min(1.0, contrib / total_move) if total_move > 1e-9 else 0.5
            score = explained - float(cfg.mdl_lambda) * len(edges)
            if score > 0:
                comps.append({"edges": edges, "explained": explained,
                              "entities": sorted({graph.subentities[s].entity_id for s in node_set}),
                              "tuples": {interaction_tuple(i, graph, ltm, thr) for i in edges}})

        # 8 (first). decay supports by the time since the last consolidation
        days = 1.0
        if wm.last_consolidated is not None:
            days = max((episode.end.date() - wm.last_consolidated).days, 0)
        half = float(cfg.support_half_life_days)
        supports: dict[str, float] = {}
        for pid, p in sorted(ltm.patterns.patterns.items()):
            if p.status == SuperentityStatus.DISSOLVED:
                continue
            s = p.support
            if not (init and p.origin == Origin.SEED) and days > 0:
                s = s * 0.5 ** (days / half)
            supports[pid] = s

        # 6. evidence of absence (computed before matching so a rival can be suppressed)
        suppressed: set[tuple[str, str]] = set()
        absence_hits: set[str] = set()
        dev = wm.deviations
        step = episode.step if episode.step is not None else dev.step_of(episode.end)
        w = int(ctx.config.frontier.window_steps)
        for iid, inst in sorted(graph.instances.items()):
            p = ltm.patterns.patterns.get(inst.pattern_id)
            if p is None or p.status == SuperentityStatus.DISSOLVED or not inst.absent_interaction_ids:
                continue
            for aid in inst.absent_interaction_ids:
                inter = graph.interactions.get(aid)
                if inter is None:
                    continue
                d, l, _ = inter.forward.kernel.means()
                kw = max(1, int(math.ceil((d + l) / ctx.step_days)))
                # DECISION: judge the target over the kernel window *after* the source moved, so a slow
                # channel is not counted as absent during its own delay.
                if abs(dev.window_change(inter.source_id, step - kw, w)) >= 1.0 and \
                        abs(dev.window_change(inter.target_id, step, kw)) < 0.25:
                    absence_hits.add(p.id)
                    for rid in sorted(p.rival_ids):
                        suppressed.add((rid, aid))
        # DECISION: the symmetric counterpart of evidence of absence, for rival pairs that disagree on
        # a relation's presence: the pattern that asserts the relation gains support in an episode
        # where the source moved by at least 1 standard unit and the target then moved the predicted
        # way by at least 0.25 within the kernel window. That is the evidence that separates them.
        rival_absent: dict[str, set[str]] = {}
        for iid, inst in sorted(graph.instances.items()):
            for aid in inst.absent_interaction_ids:
                rival_absent.setdefault(aid, set()).add(inst.pattern_id)
        for iid, inst in sorted(graph.instances.items()):
            p = ltm.patterns.patterns.get(inst.pattern_id)
            if p is None or p.status == SuperentityStatus.DISSOLVED or p.id in absence_hits:
                continue
            for pid_iid in inst.interaction_ids:
                rivals = rival_absent.get(pid_iid, set()) & set(p.rival_ids)
                inter = graph.interactions.get(pid_iid)
                if not rivals or inter is None:
                    continue
                d, l, _ = inter.forward.kernel.means()
                kw = max(1, int(math.ceil((d + l) / ctx.step_days)))
                sc = dev.window_change(inter.source_id, step - kw, w)
                tc = dev.window_change(inter.target_id, step, kw)
                if abs(sc) >= 1.0 and abs(tc) >= 0.25 and sc * tc * inter.polarity() > 0:
                    absence_hits.add(p.id)
                    break
        for pid in sorted(absence_hits):
            supports[pid] = supports.get(pid, 0.0) + 1.0
            res.supported_pattern_ids.append(pid)

        # 5. match or create
        living = [p for _, p in sorted(ltm.patterns.patterns.items())
                  if p.status != SuperentityStatus.DISSOLVED and not p.sub_pattern_ids]
        tuples_of = {p.id: pattern_tuples(p, ltm, thr) for p in living}
        absent_of = {p.id: absent_tuples(p, ltm, thr) for p in living}
        new_candidates: list[str] = []
        for comp in comps:
            matched = []
            for p in living:
                pt = tuples_of[p.id]
                if not pt:
                    continue
                # DECISION: a component that realizes a relation the pattern says is absent contradicts
                # it; and the subset rule needs at least two relations, or a one-relation pattern would
                # match every component that happens to contain that edge.
                if absent_of[p.id] & comp["tuples"]:
                    continue
                if _jac(pt, comp["tuples"]) >= float(cfg.match_jaccard) or (len(pt) >= 2 and pt <= comp["tuples"]):
                    if init and p.origin != Origin.SEED:
                        continue
                    if any((p.id, e) in suppressed for e in comp["edges"]):
                        continue
                    matched.append(p)
            for p in matched:
                if p.id in res.supported_pattern_ids:
                    continue
                supports[p.id] = supports.get(p.id, 0.0) + 1.0
                res.supported_pattern_ids.append(p.id)
                txn.update("patterns", p.id, last_seen=now,
                           episode_ids=(list(p.episode_ids) + [episode.id])[-50:])
                if not init and not any(set(comp["entities"]) <= graph.members(i)
                                        for i in graph.instances if graph.instances[i].pattern_id == p.id):
                    b = self.binder.bind(p, comp["entities"], graph, ltm)
                    if b is not None:
                        iid = txn.new_id("inst")
                        txn.add("instances", SuperentityInstance(
                            id=iid, pattern_id=p.id, bindings=b.bindings, interaction_ids=b.interaction_ids,
                            absent_interaction_ids=b.absent_interaction_ids))
                        instances_changed = True
                ctx.tracer.emit(Phase.ABDUCE, "abduce.support", refs=[p.id] + comp["entities"], pattern_id=p.id,
                                support=round(supports[p.id], 3), members=comp["entities"])
            if not matched and not init:
                pid = self._create_candidate(comp, episode, wm, ltm, ctx, txn)
                new_candidates.append(pid)
                supports[pid] = 1.0
                instances_changed = True

        # composites: once per episode in which both parts are active across a boundary edge
        if not init:
            active_now = set(episode.active_pattern_ids)
            active_edges = set(episode.active_interaction_ids)
            for pid, p in sorted(ltm.patterns.patterns.items()):
                if not p.sub_pattern_ids or p.status == SuperentityStatus.DISSOLVED:
                    continue
                if not set(p.sub_pattern_ids) <= active_now:
                    continue
                inst = next((i for i in graph.instances.values() if i.pattern_id == pid), None)
                if inst is None or len(inst.child_instance_ids) < 2:
                    continue
                a, b = inst.child_instance_ids[:2]
                if a in graph.instances and b in graph.instances and _boundary_edges(graph, a, b) & active_edges:
                    supports[pid] = supports.get(pid, p.support) + 1.0
                    res.supported_pattern_ids.append(pid)
        # write supports and history
        for pid, s in sorted(supports.items()):
            p = ltm.patterns.patterns[pid]
            ts = TimeState(at=Bitemporal(valid_at=episode.end, recorded_at=now), values={"support": round(s, 6)},
                           source_event_id=episode.id)
            if abs(p.support - s) > 1e-12:
                txn.update("patterns", pid, support=s)
            txn.append_to("patterns", pid, "history", ts, keep_last=156)

        if not init:
            # 7. admission
            for pid, p in sorted(ltm.patterns.patterns.items()):
                if p.status == SuperentityStatus.CANDIDATE and p.support > rec and p.proposed_at is None:
                    self._propose_admission(p, wm, ctx, txn, res)
                # 8. dissolution
                elif p.status == SuperentityStatus.ADMITTED and p.support < float(cfg.dissolve_below) \
                        and p.proposed_at is None:
                    self._propose_dissolution(p, ctx, txn, res)
            # 9. composition
            instances_changed |= self._compose(episode, wm, ltm, ctx, txn, res)
            # 10. rivals
            self._rivals(wm, ltm, txn)
        res.candidate_pattern_ids = new_candidates + [c for c in res.candidate_pattern_ids if c not in new_candidates]
        if instances_changed:
            self.builder.rebuild(graph, ltm.patterns, txn)
        return res

    def _create_candidate(self, comp: dict, episode: Episode, wm: WorkingMemory, ltm: LongTermMemory,
                          ctx: ProcessContext, txn: MutationTxn) -> str:
        graph = wm.graph
        thr = ctx.recall_threshold
        roles = []
        for e in comp["entities"]:
            ent = graph.entities[e]
            kinds = sorted({graph.subentities[s].attribute_kind for s in ent.subentity_ids})
            roles.append(RoleSpec(name=e, generalization_id=deepest_supported_up(ltm.object_taxonomy, ent.generalization_id, thr),
                                  attribute_kinds=kinds))
        relations = []
        for iid in comp["edges"]:
            inter = graph.interactions[iid]
            src, tgt = graph.subentities[inter.source_id], graph.subentities[inter.target_id]
            relations.append(PatternRelation(source_role=src.entity_id, source_attr=src.attribute_kind,
                                             target_role=tgt.entity_id, target_attr=tgt.attribute_kind,
                                             interaction_generalization_id=inter.generalization_id,
                                             polarity=inter.polarity(), label=inter.label))
        top = max(comp["edges"], key=lambda i: (graph.interactions[i].significance_mean(), i))
        ti = graph.interactions[top]
        name = f"{graph.subentities[ti.source_id].name} → {graph.subentities[ti.target_id].name}"
        pid = txn.new_id("pat")
        n_pat = sum(1 for p in ltm.patterns.patterns.values() if p.origin != Origin.SEED)
        palette_key = f"x{n_pat % len(EXTRA_PALETTE) + 1}"
        if palette_key not in ltm.patterns.palettes:
            color = EXTRA_PALETTE[n_pat % len(EXTRA_PALETTE)]
            txn.merge("ltm.patterns.palettes", {palette_key: {"fill": color, "line": "#8A7F70"}})
        pattern = SuperentityPattern(id=pid, name=name, roles=roles, relations=relations, support=1.0,
                                     status=SuperentityStatus.CANDIDATE, episode_ids=[episode.id],
                                     origin=Origin.INFERENCE, palette=palette_key, created_at=ctx.now,
                                     last_seen=ctx.now)
        txn.add("patterns", pattern)
        iid = txn.new_id("inst")
        bindings = {e: e for e in comp["entities"]}
        realized = self.binder.evaluate(pattern, bindings, graph, ltm).interaction_ids \
            if hasattr(self.binder, "evaluate") else list(comp["edges"])
        txn.add("instances", SuperentityInstance(id=iid, pattern_id=pid, bindings=bindings,
                                                 interaction_ids=sorted(set(realized) | set(comp["edges"]))))
        ctx.tracer.emit(Phase.ABDUCE, "abduce.candidate", refs=[pid, iid] + comp["entities"], pattern_id=pid,
                        instance_id=iid, name=name, support=1.0, members=comp["entities"], edges=comp["edges"])
        return pid

    def _propose_admission(self, p: SuperentityPattern, wm: WorkingMemory, ctx: ProcessContext,
                           txn: MutationTxn, res: InductionResult) -> None:
        from axelrod_wm.events.graph_update import EventKind, GraphUpdateEvent, ProposeSuperentity

        inst = next((i for _, i in sorted(wm.graph.instances.items()) if i.pattern_id == p.id), None)
        bindings = dict(inst.bindings) if inst is not None else {}
        ev = GraphUpdateEvent(id=f"GUE-ADMIT-{p.id}", kind=EventKind.REAL, event_type="superentity_admission",
                              occurred_at=ctx.now, recorded_at=ctx.now, produced_by="engine", confidence=0.6,
                              ops=[ProposeSuperentity(pattern=p, bindings=bindings)])
        txn.update("patterns", p.id, proposed_at=ctx.now)
        res.proposal_events.append({"kind": "superentity_admission", "event": ev.model_dump(mode="json"),
                                    "reason": f"support {p.support:.2f} exceeds the recognition threshold"})
        ctx.tracer.emit(Phase.ABDUCE, "abduce.admission_proposed", refs=[p.id] + sorted(set(bindings.values())),
                        pattern_id=p.id, support=round(p.support, 3), members=sorted(set(bindings.values())))

    def _propose_dissolution(self, p: SuperentityPattern, ctx: ProcessContext, txn: MutationTxn,
                             res: InductionResult) -> None:
        from axelrod_wm.events.graph_update import DissolveSuperentity, EventKind, GraphUpdateEvent

        ev = GraphUpdateEvent(id=f"GUE-DISSOLVE-{p.id}-{ctx.now.strftime('%Y%m%d')}", kind=EventKind.REAL,
                              event_type="superentity_dissolution", occurred_at=ctx.now, recorded_at=ctx.now,
                              produced_by="engine", confidence=0.6,
                              ops=[DissolveSuperentity(pattern_id=p.id, reason=f"support fell to {p.support:.2f}")])
        txn.update("patterns", p.id, proposed_at=ctx.now)
        res.proposal_events.append({"kind": "superentity_dissolution", "event": ev.model_dump(mode="json"),
                                    "reason": f"support {p.support:.2f} below the dissolve threshold"})
        ctx.tracer.emit(Phase.ABDUCE, "abduce.dissolution_proposed", refs=[p.id], pattern_id=p.id,
                        support=round(p.support, 3), members=[])

    def _compose(self, episode: Episode, wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext,
                 txn: MutationTxn, res: InductionResult) -> bool:
        graph = wm.graph
        rec = ctx.recognition
        admitted = [p for p in ltm.patterns.admitted() if not p.sub_pattern_ids]
        inst_of = {}
        for p in admitted:
            for iid in sorted(graph.instances):
                if graph.instances[iid].pattern_id == p.id and not graph.instances[iid].transient:
                    inst_of[p.id] = iid
                    break
        existing = {tuple(sorted(p.sub_pattern_ids)) for p in ltm.patterns.patterns.values() if p.sub_pattern_ids}
        changed = False
        eps = sorted(ltm.episodes.episodes.values(), key=lambda e: e.id)
        for i, p in enumerate(admitted):
            for q in admitted[i + 1:]:
                if p.id not in inst_of or q.id not in inst_of:
                    continue
                pair = tuple(sorted((p.id, q.id)))
                if pair in existing or p.id in q.rival_ids:
                    continue
                boundary = _boundary_edges(graph, inst_of[p.id], inst_of[q.id])
                if not boundary:
                    continue
                n = sum(1 for e in eps if p.id in e.active_pattern_ids and q.id in e.active_pattern_ids
                        and boundary & set(e.active_interaction_ids))
                if n <= rec:
                    continue
                # DECISION: a composite starts like any candidate (support 1) and earns support once per
                # later episode in which both are active across a boundary edge (see _composite_support).
                pid = txn.new_id("pat")
                roles = list({r.name: r for r in p.roles + q.roles}.values())
                relations = p.relations + [r for r in q.relations if r not in p.relations]
                comp = SuperentityPattern(id=pid, name=f"{p.name} + {q.name}", roles=roles, relations=relations,
                                          sub_pattern_ids=[p.id, q.id], support=1.0,
                                          status=SuperentityStatus.CANDIDATE, origin=Origin.INFERENCE,
                                          created_at=ctx.now, last_seen=ctx.now, episode_ids=[episode.id])
                txn.add("patterns", comp)
                ip, iq = graph.instances[inst_of[p.id]], graph.instances[inst_of[q.id]]
                iid = txn.new_id("inst")
                txn.add("instances", SuperentityInstance(
                    id=iid, pattern_id=pid, bindings={**ip.bindings, **iq.bindings},
                    interaction_ids=sorted(set(ip.interaction_ids) | set(iq.interaction_ids) | boundary),
                    absent_interaction_ids=sorted(set(ip.absent_interaction_ids) | set(iq.absent_interaction_ids)),
                    child_instance_ids=[ip.id, iq.id]))
                existing.add(pair)
                changed = True
                res.candidate_pattern_ids.append(pid)
                ctx.tracer.emit(Phase.ABDUCE, "abduce.candidate", refs=[pid, iid, p.id, q.id], pattern_id=pid,
                                instance_id=iid, name=comp.name, support=1.0, composite=True,
                                members=sorted(graph.members(ip.id) | graph.members(iq.id)))
        return changed

    def _rivals(self, wm: WorkingMemory, ltm: LongTermMemory, txn: MutationTxn) -> None:
        graph = wm.graph
        by_members: dict[tuple[str, ...], list[str]] = {}
        for iid in sorted(graph.instances):
            inst = graph.instances[iid]
            if inst.transient:
                continue
            by_members.setdefault(tuple(sorted(graph.members(iid))), []).append(inst.pattern_id)
        for _, pids in sorted(by_members.items()):
            pids = sorted(set(pids))
            for i, a in enumerate(pids):
                for b in pids[i + 1:]:
                    pa, pb = ltm.patterns.patterns.get(a), ltm.patterns.patterns.get(b)
                    if pa is None or pb is None or b in pa.rival_ids:
                        continue
                    ra = {(r.source_role, r.source_attr, r.target_role, r.target_attr): (r.present, r.polarity)
                          for r in pa.relations}
                    rb = {(r.source_role, r.source_attr, r.target_role, r.target_attr): (r.present, r.polarity)
                          for r in pb.relations}
                    if any(k in rb and rb[k] != v for k, v in ra.items()):
                        txn.update("patterns", a, rival_ids=set(pa.rival_ids) | {b})
                        txn.update("patterns", b, rival_ids=set(pb.rival_ids) | {a})

