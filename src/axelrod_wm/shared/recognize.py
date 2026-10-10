"""Recognition: binding known superentity patterns to an event's entities (§8.8, the bind step).

Part of the shared process, so both learning and inference read events this way. When an event touches
entities that can fill a recalled pattern's roles, the pattern is bound to them: an instance of the
superentity is created (a transient one on a thesis's branch). Instances whose pattern was dissolved, or
whose interactions were retired, are removed. A bound pattern whose relation has no concrete interaction
yet proposes that interaction, which waits for review.

Inputs: the parsed event and what it recalls. Output: an InductionResult (instances bound and dissolved,
proposals). Writes working memory (instances) for a real event; long-term learning's schema induction
(learning/abduction.py) counts support and proposes new patterns separately, once a day.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.registry import register, registry
from axelrod_wm.memory.long_term import SuperInteractionBuilder
from axelrod_wm.model.superentity import PatternRelation, RoleSpec, SuperentityInstance, SuperentityStatus
from axelrod_wm.model.taxonomy import AttributeVocabulary, relation_key
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.engine.interfaces import RecallResult
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.model.graph import CausalGraph
    from axelrod_wm.model.superentity import SuperentityPattern
    from axelrod_wm.repo.mutator import MutationTxn
    from axelrod_wm.shared.process import ParsedEvent

INSTANCES = "wm.graph.instances"


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


registry("binder", PatternBinder)


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


def roles_and_relations(entity_ids: list[str], interaction_ids: list[str], graph: CausalGraph, ltm: LongTermMemory,
                        threshold: float) -> tuple[list[RoleSpec], list[PatternRelation]]:
    """A pattern's roles (one per entity, at its deepest well-supported kind) and relations (one per
    interaction between them): how a configuration of concrete entities becomes a reusable schema. The
    daily distillation's candidates and a backend user's groups are built this way."""
    og = ltm.object_generalizations
    roles = []
    for e in entity_ids:
        ent = graph.entities[e]
        kinds = sorted({graph.subentities[s].attribute_kind for s in ent.subentity_ids})
        roles.append(RoleSpec(name=e, generalization_id=deepest_supported_up(og.taxonomy, ent.generalization_id,
                                                                             threshold), attribute_kinds=kinds))
    relations = []
    for iid in interaction_ids:
        inter = graph.interactions[iid]
        src, tgt = graph.subentities[inter.source_id], graph.subentities[inter.target_id]
        relations.append(PatternRelation(source_role=src.entity_id, source_attr=src.attribute_kind,
                                         target_role=tgt.entity_id, target_attr=tgt.attribute_kind,
                                         interaction_generalization_id=inter.generalization_id,
                                         polarity=inter.polarity(), label=inter.label))
    return roles, relations


def interactions_among(entity_ids: list[str], graph: CausalGraph) -> list[str]:
    """The active interactions between two different entities of the group."""
    group = set(entity_ids)
    out = []
    for iid, inter in sorted(graph.interactions.items()):
        if not inter.active:
            continue
        a, b = graph.subentities.get(inter.source_id), graph.subentities.get(inter.target_id)
        if a is not None and b is not None and a.entity_id in group and b.entity_id in group \
                and a.entity_id != b.entity_id:
            out.append(iid)
    return out


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


class PatternRecognizer:
    """The per-event bind step, shared by learning (real events) and inference (theses)."""

    def __init__(self, binder: PatternBinder, engine: Any = None) -> None:
        self.binder = binder
        self.engine = engine
        self.builder = SuperInteractionBuilder()

    @property
    def vocab(self) -> AttributeVocabulary:
        return _vocab_of(self.engine)

    def bind(self, parsed: ParsedEvent, recall: RecallResult, wm: WorkingMemory, ltm: LongTermMemory,
             ctx: ProcessContext, txn: MutationTxn | None) -> InductionResult:
        from axelrod_wm.shared.recall import near_instance

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
        from axelrod_wm.events.graph_update import AddInteraction, ConcreteTarget, EventKind, GraphUpdateEvent
        from axelrod_wm.model.distributions import Gaussian
        from axelrod_wm.model.interaction import EdgeDynamics

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
