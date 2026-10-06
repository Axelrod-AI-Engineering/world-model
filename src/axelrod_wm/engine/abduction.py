"""Superentities: binding and abduction (§8.8, D9)."""

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
    def count(self, day: int, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn) -> InductionResult:
        """At the daily consolidation: count support from the activity of the last
        abduction.window_days, form candidates, propose admissions and dissolutions, and find
        compositions."""


registry("binder", PatternBinder)
registry("inducer", SuperentityInducer)


# =============================================================================================
# Default implementations
# =============================================================================================

import math  # noqa: E402
from typing import Any  # noqa: E402

import networkx as nx  # noqa: E402

from axelrod_wm.core.evidence import Origin  # noqa: E402
from axelrod_wm.core.interaction import base_interaction_id  # noqa: E402
from axelrod_wm.core.superentity import (  # noqa: E402
    RoleSpec,
    SuperentityInstance,
    SuperentityPattern,
    SuperentityStatus,
)
from axelrod_wm.core.taxonomy import AttributeVocabulary, relation_key  # noqa: E402
from axelrod_wm.core.temporal import Bitemporal, TimeState  # noqa: E402
from axelrod_wm.engine.registry import register  # noqa: E402
from axelrod_wm.memory.long_term import SuperInteractionBuilder  # noqa: E402
from axelrod_wm.trace import Phase  # noqa: E402

EXTRA_PALETTE = ["#E9DDB5", "#D8E2C8", "#F0D9C4", "#D4DFEA", "#E8D5DF", "#D5E8E4", "#EDE3CC", "#DCD9E6"]
PATTERNS = "ltm.object_generalizations.patterns"
INSTANCES = "wm.graph.instances"
MAX_PATTERN_HISTORY = 260


def entity_path(entity_id: str, graph: CausalGraph, ltm: LongTermMemory) -> list[str]:
    tax = ltm.object_generalizations.taxonomy
    ent = graph.entities.get(entity_id)
    if ent is None or not ent.generalization_id or ent.generalization_id not in tax.nodes:
        return [tax.root_id] if tax.root_id else []
    return tax.path_from_root(ent.generalization_id)


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


def _vocab_of(engine: Any) -> AttributeVocabulary:
    vocab = getattr(engine, "vocab", None)
    return vocab if vocab is not None else AttributeVocabulary(kinds={})


@register("binder", "bfs_role_filling")
class BfsRoleFillingBinder(PatternBinder):
    def __init__(self, config: Any = None, engine: Any = None, min_binding_coverage: float | None = None,
                 vocab: AttributeVocabulary | None = None) -> None:
        ab = getattr(config, "abduction", None)
        self.engine = engine
        self._vocab = vocab
        self.min_cov = float(min_binding_coverage if min_binding_coverage is not None
                             else getattr(ab, "min_binding_coverage", 0.6))

    @property
    def vocab(self) -> AttributeVocabulary:
        return self._vocab if self._vocab is not None else _vocab_of(self.engine)

    def _partner(self, entity: str, rel: PatternRelation, outward: bool, role: RoleSpec, used: set[str],
                 graph: CausalGraph, ltm: LongTermMemory) -> str | None:
        vocab = self.vocab
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
        vocab = self.vocab
        for rel in pattern.relations:
            if rel.source_role not in bindings or rel.target_role not in bindings:
                continue
            ids = realizations(rel, bindings[rel.source_role], bindings[rel.target_role], graph, vocab)
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
    otax = ltm.object_generalizations.taxonomy
    itax = ltm.interaction_generalizations.taxonomy
    src_gen = deepest_supported_up(otax, roles[rel.source_role].generalization_id
                                   if rel.source_role in roles else None, thr)
    tgt_gen = deepest_supported_up(otax, roles[rel.target_role].generalization_id
                                   if rel.target_role in roles else None, thr)
    int_gen = deepest_supported_up(itax, rel.interaction_generalization_id, thr)
    return (src_gen, rel.source_attr, int_gen, tgt_gen, rel.target_attr, str(rel.polarity))


def pattern_tuples(p: SuperentityPattern, ltm: LongTermMemory, thr: float) -> set[tuple]:
    roles = {r.name: r for r in p.roles}
    return {relation_tuple(r, roles, ltm, thr) for r in p.relations if r.present}


def absent_tuples(p: SuperentityPattern, ltm: LongTermMemory, thr: float) -> set[tuple]:
    roles = {r.name: r for r in p.roles}
    return {relation_tuple(r, roles, ltm, thr) for r in p.relations if not r.present}


def interaction_tuple(iid: str, graph: CausalGraph, ltm: LongTermMemory, thr: float) -> tuple:
    otax = ltm.object_generalizations.taxonomy
    itax = ltm.interaction_generalizations.taxonomy
    inter = graph.interactions[iid]
    src = graph.subentities[inter.source_id]
    tgt = graph.subentities[inter.target_id]
    src_gen = deepest_supported_up(otax, graph.entities[src.entity_id].generalization_id, thr)
    tgt_gen = deepest_supported_up(otax, graph.entities[tgt.entity_id].generalization_id, thr)
    int_gen = deepest_supported_up(itax, inter.generalization_id, thr)
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


def _kernel_span(inter: Any) -> int:
    d, l, _ = inter.forward.kernel.means()
    return max(1, int(math.ceil(d + l)))


def spaced_count(days: list[int], spacing: int) -> int:
    """How many of the (sorted) days count under the evidence-spacing rule."""
    n, last = 0, None
    for d in sorted(days):
        if last is None or d - last >= spacing:
            n += 1
            last = d
    return n


@register("inducer", "co_activation")
class CoActivationInducer(SuperentityInducer):
    def __init__(self, config: Any = None, binder: PatternBinder | None = None, engine: Any = None) -> None:
        self.config = config
        self.engine = engine
        self.binder = binder or BfsRoleFillingBinder(config, engine)
        self.builder = SuperInteractionBuilder()

    @property
    def vocab(self) -> AttributeVocabulary:
        return _vocab_of(self.engine)

    # -- bind (during prefill) ---------------------------------------------------------------
    def bind(self, parsed: ParsedEvent, recall: RecallResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn | None) -> InductionResult:
        from axelrod_wm.engine.recall import near_instance

        res = InductionResult()
        if ctx.initializing:
            return res
        real = txn is not None
        graph = wm.graph
        og = ltm.object_generalizations
        changed = False
        if real:
            for iid in sorted(graph.instances):
                inst = graph.instances[iid]
                pat = og.patterns.get(inst.pattern_id)
                retired = any(graph.interactions.get(i) is None or graph.interactions[i].retired_at is not None
                              for i in inst.interaction_ids)
                if pat is None or pat.status == SuperentityStatus.DISSOLVED or retired:
                    txn.remove(INSTANCES, iid)
                    res.dissolved_instance_ids.append(iid)
                    changed = True
                    ctx.tracer.emit(Phase.PREFILL, "induce.dissolved", refs=[iid, inst.pattern_id], instance_id=iid,
                                    pattern_id=inst.pattern_id, transient=False)
        if real and parsed.is_routine():
            if changed:
                self.builder.rebuild(graph, og, txn)
            return res
        touched = set(parsed.touched_entity_ids)
        thr = ctx.recall_threshold
        for s in recall.superentities:
            p = og.patterns.get(s.pattern_id)
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
                txn.add(INSTANCES, inst)
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
            self.builder.rebuild(graph, og, txn)
        return res

    def _missing_relations(self, p: SuperentityPattern, b: Binding, wm: WorkingMemory, ltm: LongTermMemory,
                           ctx: ProcessContext, txn: MutationTxn, res: InductionResult, thr: float) -> None:
        from axelrod_wm.core.distributions import Gaussian
        from axelrod_wm.core.interaction import EdgeDynamics
        from axelrod_wm.events.graph_update import AddInteraction, ConcreteTarget, EventKind, GraphUpdateEvent

        cool = float(ctx.config.abduction.missing_relation_cooldown_days)
        graph = wm.graph
        vocab = self.vocab
        itax = ltm.interaction_generalizations.taxonomy
        otax = ltm.object_generalizations.taxonomy
        pattern_node = otax.nodes.get(p.generalization_id) if p.generalization_id else None
        pattern_priors = pattern_node.prior_for_pattern()[0] if pattern_node is not None else {}
        for rel in b.missing_relations:
            gid = rel.interaction_generalization_id
            node = itax.nodes.get(gid) if gid else None
            if node is None or node.stats.support <= thr:
                continue
            idx = p.relations.index(rel)
            key = f"{p.id}#{idx}"
            last = wm.missing_relation_log.get(key)
            if last is not None and (ctx.now - last).total_seconds() < cool * 86400:
                continue
            srcs = _subs_of_kind(b.bindings[rel.source_role], rel.source_attr, graph, vocab)
            tgts = _subs_of_kind(b.bindings[rel.target_role], rel.target_attr, graph, vocab)
            if not srcs or not tgts:
                continue
            dyn, existence = node.prior_dynamics()
            prior = pattern_priors.get(relation_key(rel.source_attr, rel.target_attr, rel.polarity))
            if prior is not None:
                # the pattern's configuration node supplies priors for relations without concrete edges (§8.8)
                effect = prior
            else:
                mu = float(rel.polarity) * max(abs(dyn.effect.mean()), 0.1)
                effect = Gaussian(mu=mu, sigma=dyn.effect.sd())
            dyn = EdgeDynamics(effect=effect, kernel=dyn.kernel)
            ev = GraphUpdateEvent(
                id=f"GUE-MR-{p.id}-{idx}-{ctx.now.strftime('%Y%m%d')}", kind=EventKind.REAL, event_type="missing_relation",
                occurred_at=ctx.now, recorded_at=ctx.now, produced_by="engine", confidence=0.5,
                ops=[AddInteraction(source=ConcreteTarget(subentity_id=srcs[0]), target=ConcreteTarget(subentity_id=tgts[0]),
                                    label=rel.label, polarity=rel.polarity, interaction_generalization_id=gid,
                                    dynamics=dyn, existence=existence)])
            txn.put("wm.missing_relation_log", key, ctx.now)
            res.proposal_events.append({"kind": "missing_relation", "event": ev.model_dump(mode="json"),
                                        "reason": f"pattern {p.id} ({p.name}) predicts {rel.label}"})

    # -- count (at the daily consolidation) --------------------------------------------------
    def _active_edges(self, day: int, wm: WorkingMemory, width: int) -> dict[str, Any]:
        """Interaction id -> its latest activity record in the window, for channels whose contribution
        change has the same sign as the target's move over the same window (§8.8 step 1)."""
        graph = wm.graph
        latest: dict[str, Any] = {}
        for r in wm.activity_log.values():
            if r.day <= day - width or r.day > day:
                continue
            cur = latest.get(r.channel_id)
            if cur is None or r.day > cur.day:
                latest[r.channel_id] = r
        active: dict[str, Any] = {}
        for key in sorted(latest):
            r = latest[key]
            iid = base_interaction_id(key)
            inter = graph.interactions.get(iid)
            if inter is None or inter.retired_at is not None:
                continue
            if r.contribution_change * r.target_move > 0:
                prev = active.get(iid)
                if prev is None or abs(r.contribution_change) > abs(prev.contribution_change):
                    active[iid] = r
        return active

    def _components(self, active: dict[str, Any], wm: WorkingMemory, ltm: LongTermMemory, ctx: ProcessContext,
                    ) -> list[dict]:
        """Steps 2-3: components of the active edges, scored, then the greedy best explanation."""
        graph = wm.graph
        thr = ctx.recall_threshold
        mdl = float(ctx.config.abduction.mdl_lambda)
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
            contrib = sum(abs(active[i].contribution_change) for i in edges)
            moves: dict[str, float] = {}
            for i in edges:
                r = active[i]
                moves[r.target_id or graph.interactions[i].target_id] = abs(r.target_move)
            total = sum(moves.values())
            explained = min(1.0, contrib / total) if total > 1e-9 else 0.0
            comps.append({"edges": edges, "explained": explained, "score": explained - mdl * len(edges),
                          "entities": sorted({graph.subentities[s].entity_id for s in node_set}),
                          "tuples": {interaction_tuple(i, graph, ltm, thr) for i in edges}})
        kept, used = [], set()
        for c in sorted(comps, key=lambda c: (-c["score"], c["edges"])):
            if c["score"] <= 0 or set(c["entities"]) & used:
                continue
            kept.append(c)
            used |= set(c["entities"])
        return kept

    def count(self, day: int, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn) -> InductionResult:
        res = InductionResult()
        cfg = ctx.config.abduction
        rec = ctx.recognition
        thr = ctx.recall_threshold
        init = ctx.initializing
        graph = wm.graph
        og = ltm.object_generalizations
        patterns = og.patterns
        dev = wm.deviations
        now = ctx.now
        width = int(cfg.window_days)
        spacing = int(cfg.evidence_spacing_days)
        episode_id = ctx.notes.get("episode_id")
        instances_changed = False
        updater = self.engine.components.get("generalization_updater") if self.engine is not None else None

        active = self._active_edges(day, wm, width)
        comps = self._components(active, wm, ltm, ctx)

        # 8 (first). every pattern's support decays by one day; seeds do not decay during initialization
        factor = 0.5 ** (1.0 / float(cfg.support_half_life_days))
        supports: dict[str, float] = {}
        for pid, p in sorted(patterns.items()):
            if p.status == SuperentityStatus.DISSOLVED:
                continue
            supports[pid] = p.support if (init and p.origin == Origin.SEED) else p.support * factor
        counted: set[str] = set()

        def count_once(pid: str) -> bool:
            """support += 1, at most once per evidence_spacing_days (§8.8 step 5)."""
            p = patterns[pid]
            if pid in counted or (p.last_counted_day is not None and day - p.last_counted_day < spacing):
                return False
            counted.add(pid)
            supports[pid] = supports.get(pid, p.support) + 1.0
            if init:
                txn.update(PATTERNS, pid, last_counted_day=day)
            else:
                txn.update(PATTERNS, pid, last_counted_day=day, counted_days=(list(p.counted_days) + [day])[-52:])
            res.supported_pattern_ids.append(pid)
            if updater is not None and p.generalization_id and hasattr(updater, "update_pattern"):
                updater.update_pattern(pid, ltm, ctx, txn, count_support=True)
            return True

        # 6. evidence of absence (before matching, so that a rival can be suppressed)
        suppressed: set[tuple[str, str]] = set()
        absence_hits: set[str] = set()
        for iid, inst in sorted(graph.instances.items()):
            p = patterns.get(inst.pattern_id)
            if p is None or p.status == SuperentityStatus.DISSOLVED or not inst.absent_interaction_ids:
                continue
            for aid in inst.absent_interaction_ids:
                inter = graph.interactions.get(aid)
                if inter is None:
                    continue
                kw = _kernel_span(inter)
                # DECISION: judge the target over the kernel's span *after* the source moved, so a slow
                # channel is not counted as absent during its own delay.
                if abs(dev.window_change(inter.source_id, day - kw, width)) >= 1.0 and \
                        abs(dev.window_change(inter.target_id, day, kw)) < 0.25:
                    absence_hits.add(p.id)
                    for rid in sorted(p.rival_ids):
                        suppressed.add((rid, aid))
        # DECISION: the symmetric counterpart of evidence of absence, for rival pairs that disagree on
        # a relation's presence: the pattern that asserts the relation gains support when the source
        # moved by at least 1 standard unit and the target then moved the predicted way by at least
        # 0.25 within the kernel's span. That is the evidence that separates them.
        rival_absent: dict[str, set[str]] = {}
        for iid, inst in sorted(graph.instances.items()):
            for aid in inst.absent_interaction_ids:
                rival_absent.setdefault(aid, set()).add(inst.pattern_id)
        for iid, inst in sorted(graph.instances.items()):
            p = patterns.get(inst.pattern_id)
            if p is None or p.status == SuperentityStatus.DISSOLVED or p.id in absence_hits:
                continue
            for pid_iid in inst.interaction_ids:
                rivals = rival_absent.get(pid_iid, set()) & set(p.rival_ids)
                inter = graph.interactions.get(pid_iid)
                if not rivals or inter is None:
                    continue
                kw = _kernel_span(inter)
                sc = dev.window_change(inter.source_id, day - kw, width)
                tc = dev.window_change(inter.target_id, day, kw)
                if abs(sc) >= 1.0 and abs(tc) >= 0.25 and sc * tc * inter.polarity() > 0:
                    absence_hits.add(p.id)
                    break
        for pid in sorted(absence_hits):
            count_once(pid)

        # 5. match or create
        living = [p for _, p in sorted(patterns.items())
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
                fields: dict[str, Any] = {"last_seen": now}
                if episode_id and episode_id not in p.episode_ids:
                    fields["episode_ids"] = (list(p.episode_ids) + [episode_id])[-50:]
                txn.update(PATTERNS, p.id, **fields)
                own = [graph.instances[i] for i in sorted(graph.instances)
                       if graph.instances[i].pattern_id == p.id and not graph.instances[i].transient]
                if not init and not any(set(comp["entities"]) <= graph.members(i.id) for i in own):
                    b = self.binder.bind(p, comp["entities"], graph, ltm)
                    # DECISION: a binding that an instance of the pattern already holds is that instance
                    # recurring, not a new one; otherwise a component with one extra entity re-binds the
                    # same roles every day and identical instances pile up.
                    if b is not None and not any(dict(i.bindings) == dict(b.bindings) for i in own):
                        iid = txn.new_id("inst")
                        txn.add(INSTANCES, SuperentityInstance(
                            id=iid, pattern_id=p.id, bindings=b.bindings, interaction_ids=b.interaction_ids,
                            absent_interaction_ids=b.absent_interaction_ids))
                        instances_changed = True
                if count_once(p.id):
                    ctx.tracer.emit(Phase.ABDUCE, "abduce.support", refs=[p.id] + comp["entities"], pattern_id=p.id,
                                    support=round(supports[p.id], 3), members=comp["entities"])
            if not matched and not init:
                pid = self._create_candidate(comp, day, episode_id, wm, ltm, ctx, txn)
                new_candidates.append(pid)
                supports[pid] = 1.0
                counted.add(pid)
                instances_changed = True
                # DECISION: later components on the same day can match the new candidate, so one
                # configuration realized twice in a day makes one candidate rather than two
                if pid in patterns:
                    living.append(patterns[pid])
                    tuples_of[pid] = pattern_tuples(patterns[pid], ltm, thr)
                    absent_of[pid] = absent_tuples(patterns[pid], ltm, thr)

        # composites earn support when both parts are active across a boundary edge (same spacing)
        if not init:
            active_patterns = {i.pattern_id for i in graph.instances.values() if i.activation > 0 and not i.transient}
            for pid, p in sorted(patterns.items()):
                if not p.sub_pattern_ids or p.status == SuperentityStatus.DISSOLVED:
                    continue
                if not set(p.sub_pattern_ids) <= active_patterns:
                    continue
                inst = next((i for i in graph.instances.values() if i.pattern_id == pid), None)
                if inst is None or len(inst.child_instance_ids) < 2:
                    continue
                a, b = inst.child_instance_ids[:2]
                if a in graph.instances and b in graph.instances and _boundary_edges(graph, a, b) & set(active):
                    count_once(pid)

        # write supports, and a weekly time state with the support
        from axelrod_wm.engine.daily import time_state_due

        for pid, s in sorted(supports.items()):
            p = patterns[pid]
            if abs(p.support - s) > 1e-12:
                txn.update(PATTERNS, pid, support=s)
            if time_state_due(p.history, wm, day):
                ts = TimeState(at=Bitemporal(valid_at=dev.day_end(day), recorded_at=now),
                               values={"support": round(s, 6)}, source_event_id=episode_id)
                txn.append_to(PATTERNS, pid, "history", ts, keep_last=MAX_PATTERN_HISTORY)

        if not init:
            for pid, p in sorted(patterns.items()):
                # 7. admission
                if p.status == SuperentityStatus.CANDIDATE and p.support > rec and p.proposed_at is None:
                    self._propose_admission(p, wm, ctx, txn, res)
                # 8. dissolution
                elif p.status == SuperentityStatus.ADMITTED and p.support < float(cfg.dissolve_below) \
                        and p.proposed_at is None:
                    self._propose_dissolution(p, ctx, txn, res)
            # 9. composition
            instances_changed |= self._compose(day, episode_id, active, wm, ltm, ctx, txn, res)
            # 10. rivals
            self._rivals(wm, ltm, txn)
        res.candidate_pattern_ids = new_candidates + [c for c in res.candidate_pattern_ids if c not in new_candidates]
        if instances_changed:
            self.builder.rebuild(graph, og, txn)
        return res

    def _create_candidate(self, comp: dict, day: int, episode_id: str | None, wm: WorkingMemory,
                          ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn) -> str:
        graph = wm.graph
        thr = ctx.recall_threshold
        og = ltm.object_generalizations
        roles = []
        for e in comp["entities"]:
            ent = graph.entities[e]
            kinds = sorted({graph.subentities[s].attribute_kind for s in ent.subentity_ids})
            roles.append(RoleSpec(name=e, generalization_id=deepest_supported_up(og.taxonomy, ent.generalization_id, thr),
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
        # DECISION: a candidate named after its strongest edge says how many more relations it has, so
        # two configurations that share that edge do not read as duplicates
        if len(relations) > 1:
            more = len(relations) - 1
            name += f" + {more} more relation{'s' if more > 1 else ''}"
        pid = txn.new_id("pat")
        n_pat = sum(1 for p in og.patterns.values() if p.origin != Origin.SEED)
        palette_key = f"x{n_pat % len(EXTRA_PALETTE) + 1}"
        if palette_key not in og.palettes:
            color = EXTRA_PALETTE[n_pat % len(EXTRA_PALETTE)]
            txn.set("ltm.object_generalizations.palettes",
                    {**og.palettes, palette_key: {"fill": color, "line": "#8A7F70"}})
        pattern = SuperentityPattern(id=pid, name=name, roles=roles, relations=relations, support=1.0,
                                     status=SuperentityStatus.CANDIDATE,
                                     episode_ids=[episode_id] if episode_id else [],
                                     origin=Origin.INFERENCE, palette=palette_key, created_at=ctx.now,
                                     last_seen=ctx.now, last_counted_day=day)
        txn.add(PATTERNS, pattern)
        iid = txn.new_id("inst")
        bindings = {e: e for e in comp["entities"]}
        realized = self.binder.evaluate(pattern, bindings, graph, ltm).interaction_ids \
            if hasattr(self.binder, "evaluate") else list(comp["edges"])
        txn.add(INSTANCES, SuperentityInstance(id=iid, pattern_id=pid, bindings=bindings,
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
        txn.update(PATTERNS, p.id, proposed_at=ctx.now)
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
        txn.update(PATTERNS, p.id, proposed_at=ctx.now)
        res.proposal_events.append({"kind": "superentity_dissolution", "event": ev.model_dump(mode="json"),
                                    "reason": f"support {p.support:.2f} below the dissolve threshold"})
        ctx.tracer.emit(Phase.ABDUCE, "abduce.dissolution_proposed", refs=[p.id], pattern_id=p.id,
                        support=round(p.support, 3), members=[])

    def _compose(self, day: int, episode_id: str | None, active: dict[str, Any], wm: WorkingMemory,
                 ltm: LongTermMemory, ctx: ProcessContext, txn: MutationTxn, res: InductionResult) -> bool:
        """Step 9: two admitted patterns whose instances were both counted active, under the spacing
        rule, more than `recognition` times, with a boundary edge between them, form a candidate."""
        graph = wm.graph
        og = ltm.object_generalizations
        rec = ctx.recognition
        spacing = int(ctx.config.abduction.evidence_spacing_days)
        admitted = [p for p in og.admitted() if not p.sub_pattern_ids]
        inst_of = {}
        for p in admitted:
            for iid in sorted(graph.instances):
                if graph.instances[iid].pattern_id == p.id and not graph.instances[iid].transient:
                    inst_of[p.id] = iid
                    break
        existing = {tuple(sorted(p.sub_pattern_ids)) for p in og.patterns.values() if p.sub_pattern_ids}
        changed = False
        for i, p in enumerate(admitted):
            for q in admitted[i + 1:]:
                if p.id not in inst_of or q.id not in inst_of:
                    continue
                pair = tuple(sorted((p.id, q.id)))
                if pair in existing or p.id in q.rival_ids:
                    continue
                # DECISION: "both counted active" means count() added support to both on the same day,
                # and only live counts are kept (counted_days), so composites form on screen from what
                # happens after initialization rather than all at once from three years of history.
                together = sorted(set(p.counted_days) & set(q.counted_days))
                if spaced_count(together, spacing) <= rec:
                    continue
                boundary = _boundary_edges(graph, inst_of[p.id], inst_of[q.id])
                if not boundary:
                    continue
                # DECISION: a composite starts like any candidate (support 1) and earns support under
                # the same spacing rule whenever both parts are active across a boundary edge.
                pid = txn.new_id("pat")
                roles = list({r.name: r for r in p.roles + q.roles}.values())
                relations = p.relations + [r for r in q.relations if r not in p.relations]
                comp = SuperentityPattern(id=pid, name=f"{p.name} + {q.name}", roles=roles, relations=relations,
                                          sub_pattern_ids=[p.id, q.id], support=1.0,
                                          status=SuperentityStatus.CANDIDATE, origin=Origin.INFERENCE,
                                          created_at=ctx.now, last_seen=ctx.now, last_counted_day=day,
                                          episode_ids=[episode_id] if episode_id else [])
                txn.add(PATTERNS, comp)
                ip, iq = graph.instances[inst_of[p.id]], graph.instances[inst_of[q.id]]
                iid = txn.new_id("inst")
                txn.add(INSTANCES, SuperentityInstance(
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
        patterns = ltm.object_generalizations.patterns
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
                    pa, pb = patterns.get(a), patterns.get(b)
                    if pa is None or pb is None or b in pa.rival_ids:
                        continue
                    ra = {(r.source_role, r.source_attr, r.target_role, r.target_attr): (r.present, r.polarity)
                          for r in pa.relations}
                    rb = {(r.source_role, r.source_attr, r.target_role, r.target_attr): (r.present, r.polarity)
                          for r in pb.relations}
                    if any(k in rb and rb[k] != v for k, v in ra.items()):
                        txn.update(PATTERNS, a, rival_ids=set(pa.rival_ids) | {b})
                        txn.update(PATTERNS, b, rival_ids=set(pb.rival_ids) | {a})
