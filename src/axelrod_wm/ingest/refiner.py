"""The refiner: from broad to concrete, as far as evidence allows (§7.5, D3, D10)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.ids import TEMP_PREFIX, slugify, strip_temp
from axelrod_wm.core.taxonomy import Signature, label_family
from axelrod_wm.engine.classify import node_signature
from axelrod_wm.engine.registry import register, registry
from axelrod_wm.events.graph_update import (
    AbstractTarget,
    AddEntity,
    AddInteraction,
    AddSubentity,
    ChangeValue,
    ConcreteTarget,
    EventKind,
    GraphUpdateEvent,
    ObserveValue,
    Specificity,
    op_ends,
)
from axelrod_wm.ingest.resolver import AliasFuzzyResolver, EntityResolver, text_similarity
from axelrod_wm.memory.working import PendingRefinement
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.core.graph import CausalGraph
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


class RefinementStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op_index: int
    end: str                               # "source", "target", "subject", or "relation"
    from_level: Specificity
    to_level: Specificity
    node_id: str                           # generalization, entity, or subentity id reached
    candidates: list[tuple[str, float]]    # (id, score) considered at this level
    created: bool = False                  # True if the refiner added an AddSubentity op
    reason: str


class RefinementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: GraphUpdateEvent                # concrete ops only, plus any AddSubentity ops added
    steps: list[RefinementStep]
    pending: list[PendingRefinement]       # ops that stayed fuzzy
    soft_support: dict[str, float] = {}    # interaction generalization id -> support to add


class Refiner(ABC):
    """Pure: refine() and retry_pending() never write to memory. Their results travel inside
    a Proposal and are applied when the proposal is approved (§7.6)."""

    @abstractmethod
    def refine(self, event: GraphUpdateEvent, wm: WorkingMemory, ltm: LongTermMemory,
               ctx: ProcessContext) -> RefinementResult: ...

    @abstractmethod
    def retry_pending(self, applied: GraphUpdateEvent, wm: WorkingMemory, ltm: LongTermMemory,
                      ctx: ProcessContext) -> list[GraphUpdateEvent]:
        """Called after each applied real event. Returns refined events ready for review."""


registry("refiner", Refiner)


class _VirtualSub:
    """A subentity created earlier in the same event (an AddSubentity op), usable as a candidate."""

    def __init__(self, sid: str, entity_id: str, name: str, attribute_kind: str, features: dict[str, str],
                 aliases: list[str]) -> None:
        self.id = sid
        self.entity_id = entity_id
        self.name = name
        self.attribute_kind = attribute_kind
        self.features = features
        self.aliases = aliases


def _attr_ok(kind: str, allowed: list[str], vocab: Any) -> bool:
    return not allowed or any(vocab.is_a(kind, a) for a in allowed)


def _feats_ok(features: dict[str, str], constraints: dict[str, str]) -> bool:
    return all(features.get(k) == v for k, v in constraints.items())


def _signature_attrs(sig: Signature, key: str) -> list[str]:
    return list(sig.required.get(key, [])) + [v for v in sig.any_of.get(key, []) if v not in sig.required.get(key, [])]


@register("refiner", "taxonomy")
class TaxonomyRefiner(Refiner):
    def __init__(self, config: Any = None, entity_resolver: EntityResolver | None = None) -> None:
        self.config = config
        self.resolver = entity_resolver or AliasFuzzyResolver(config)

    # -- helpers ---------------------------------------------------------------------------
    def _entity_subs(self, eid: str, graph: CausalGraph, virtual: list[_VirtualSub]) -> list[Any]:
        ent = graph.entities.get(eid)
        subs = [graph.subentities[s] for s in (ent.subentity_ids if ent else []) if s in graph.subentities]
        return subs + [v for v in virtual if v.entity_id == eid]

    def _can_satisfy(self, eid: str, allowed: list[str], graph: CausalGraph, virtual: list[_VirtualSub],
                     vocab: Any) -> bool:
        if not allowed:
            return True
        return any(_attr_ok(s.attribute_kind, allowed, vocab) for s in self._entity_subs(eid, graph, virtual))

    def _entity_instances(self, gen_id: str, ltm: LongTermMemory, graph: CausalGraph) -> list[str]:
        return [i for i in ltm.object_taxonomy.instances_under(gen_id) if i in graph.entities]

    def _signature_fit(self, gen_id: str, allowed: list[str], constraints: dict[str, str], ltm: LongTermMemory,
                       graph: CausalGraph, virtual: list[_VirtualSub]) -> float:
        reqs = (1 if allowed else 0) + len(constraints)
        if reqs == 0:
            return 0.0
        ents = self._entity_instances(gen_id, ltm, graph)
        met = 0
        if allowed and any(self._can_satisfy(e, allowed, graph, virtual, ltm.attributes) for e in ents):
            met += 1
        for k, v in constraints.items():
            if any(graph.entities[e].features.get(k) == v
                   or any(s.features.get(k) == v for s in self._entity_subs(e, graph, virtual)) for e in ents):
                met += 1
        return met / reqs

    def _gen_mention(self, gen_id: str, mention: str | None, ltm: LongTermMemory, graph: CausalGraph,
                     virtual: list[_VirtualSub]) -> float:
        if not mention:
            return 0.0
        strings = [ltm.object_taxonomy.nodes[gen_id].name]
        for e in self._entity_instances(gen_id, ltm, graph):
            ent = graph.entities[e]
            strings += [ent.name, *ent.aliases]
            for s in self._entity_subs(e, graph, virtual):
                strings += [s.name, *getattr(s, "aliases", [])]
        return text_similarity(mention, strings)

    # -- relation (step 0) -----------------------------------------------------------------
    def _relation(self, idx: int, op: AddInteraction, graph: CausalGraph, ltm: LongTermMemory,
                  ctx: ProcessContext, steps: list[RefinementStep]) -> tuple[str, dict[str, list[str]]]:
        tax = ltm.interaction_taxonomy
        thr = ctx.recall_threshold
        feats: dict[str, list[str]] = {"polarity": [str(op.polarity)], "label_family": [label_family(op.label)]}
        for end, t in (("source", op.source), ("target", op.target)):
            if isinstance(t, ConcreteTarget):
                sid = strip_temp(t.subentity_id)
                sub = graph.subentities.get(sid)
                if sub is not None:
                    feats[f"{end}_attr"] = [sub.attribute_kind]
                    ent = graph.entities.get(sub.entity_id)
                    if ent is not None and ent.generalization_id:
                        feats[f"{end}_gen"] = [ent.generalization_id]
                    kv = sorted({f"{k}={v}" for k, v in {**(ent.features if ent else {}), **sub.features}.items()})
                    if kv:
                        feats[f"{end}_features"] = kv
            else:
                if t.attribute_kind:
                    feats[f"{end}_attr"] = [t.attribute_kind]
                if t.generalization_id:
                    feats[f"{end}_gen"] = [t.generalization_id]
                if t.constraints:
                    feats[f"{end}_features"] = sorted(f"{k}={v}" for k, v in t.constraints.items())
        node = op.interaction_generalization_id if op.interaction_generalization_id in tax.nodes else tax.root_id
        while True:
            nxt = None
            for child in sorted(tax.children(node), key=lambda c: (-c.stats.support, c.id)):
                sig = node_signature(tax, child.id, graph, ltm)
                if child.stats.support > thr and sig.satisfied_by_known(feats, ltm.attributes):
                    nxt = child.id
                    break
            if nxt is None:
                break
            steps.append(RefinementStep(op_index=idx, end="relation", from_level=Specificity.GENERALIZATION,
                                        to_level=Specificity.GENERALIZATION, node_id=nxt, candidates=[],
                                        reason=f"relation narrows to {tax.nodes[nxt].name}"))
            node = nxt
        sig = node_signature(tax, node, graph, ltm)
        return node, {"source": _signature_attrs(sig, "source_attr"), "target": _signature_attrs(sig, "target_attr")}

    # -- one end ---------------------------------------------------------------------------
    def _refine_end(self, idx: int, end: str, t: AbstractTarget, allowed: list[str], explicit_attr: bool,
                    temp_map: dict[str, str], graph: CausalGraph, ltm: LongTermMemory, ctx: ProcessContext,
                    virtual: list[_VirtualSub], new_ops: list[Any], steps: list[RefinementStep],
                    pattern_bonus: set[str]) -> dict[str, Any]:
        cfg = ctx.config.refinement
        thr = ctx.recall_threshold
        tax = ltm.object_taxonomy
        vocab = ltm.attributes
        self.resolver.extra_subs = virtual  # type: ignore[attr-defined]
        entity = None
        node = t.generalization_id if t.generalization_id in tax.nodes else tax.root_id
        candidates: list[tuple[str, float]] = []
        if t.entity_id:
            entity = temp_map.get(t.entity_id, strip_temp(t.entity_id))
            if entity not in graph.entities:
                entity = None
        if entity is None and t.candidate_entity_ids:
            cands = [e for e in t.candidate_entity_ids if e in graph.entities
                     and self._can_satisfy(e, allowed, graph, virtual, vocab)]
            ranked = self.resolver.resolve(t.mention, t.constraints, cands, graph)
            ranked = sorted(((e, min(1.0, s + (0.2 if e in pattern_bonus else 0.0))) for e, s in ranked),
                            key=lambda x: (-x[1], x[0]))
            candidates = ranked
            if ranked and ranked[0][1] >= float(cfg.bind_score) and \
                    ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0.0) >= float(cfg.bind_margin):
                entity = ranked[0][0]
                steps.append(RefinementStep(op_index=idx, end=end, from_level=Specificity.GENERALIZATION,
                                            to_level=Specificity.ENTITY, node_id=entity, candidates=ranked[:5],
                                            reason=f"{graph.entities[entity].name} ranks first among the candidates"))
        elif entity is None:
            # step 1: walk down the object taxonomy
            while True:
                best = None
                for child in tax.children(node):
                    fit = self._signature_fit(child.id, allowed, t.constraints, ltm, graph, virtual)
                    ment = self._gen_mention(child.id, t.mention, ltm, graph, virtual)
                    score = 0.6 * fit + 0.4 * ment
                    key = (score, child.stats.support, child.id)
                    if best is None or key[0] > best[0] or (key[0] == best[0] and (key[1] > best[1] or (
                            key[1] == best[1] and key[2] < best[2]))):
                        best = key
                if best is None or best[0] < float(cfg.min_generalization_score) or \
                        tax.nodes[best[2]].stats.support <= thr:
                    break
                steps.append(RefinementStep(op_index=idx, end=end, from_level=Specificity.GENERALIZATION,
                                            to_level=Specificity.GENERALIZATION, node_id=best[2],
                                            candidates=[(best[2], round(best[0], 4))],
                                            reason=f"{tax.nodes[best[2]].name} fits (score {best[0]:.2f})"))
                node = best[2]
            # step 2: bind the entity
            cands = [e for e in self._entity_instances(node, ltm, graph)
                     if self._can_satisfy(e, allowed, graph, virtual, vocab)]
            ranked = self.resolver.resolve(t.mention, t.constraints, cands, graph)
            ranked = sorted(((e, min(1.0, s + (0.2 if e in pattern_bonus else 0.0))) for e, s in ranked),
                            key=lambda x: (-x[1], x[0]))
            candidates = [(e, round(s, 4)) for e, s in ranked]
            if ranked and ranked[0][1] >= float(cfg.bind_score) and \
                    ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0.0) >= float(cfg.bind_margin):
                entity = ranked[0][0]
                steps.append(RefinementStep(op_index=idx, end=end, from_level=Specificity.GENERALIZATION,
                                            to_level=Specificity.ENTITY, node_id=entity, candidates=candidates[:5],
                                            reason=f"{graph.entities[entity].name} binds (score {ranked[0][1]:.2f})"))
        if entity is None:
            return {"level": Specificity.GENERALIZATION, "ref": node, "candidates": candidates}
        # step 3: bind the subentity
        subs = [s for s in self._entity_subs(entity, graph, virtual)
                if _attr_ok(s.attribute_kind, allowed, vocab) and _feats_ok(s.features, t.constraints)]
        chosen = None
        sub_cands: list[tuple[str, float]] = []
        if len(subs) == 1:
            chosen = subs[0].id
            sub_cands = [(chosen, 1.0)]
        elif len(subs) > 1:
            scored = sorted(((s.id, text_similarity(t.mention, [s.name, *getattr(s, "aliases", [])])) for s in subs),
                            key=lambda x: (-x[1], x[0]))
            sub_cands = [(i, round(v, 4)) for i, v in scored]
            if scored[0][1] - scored[1][1] >= float(cfg.bind_margin):
                chosen = scored[0][0]
        created = False
        if chosen is None and not subs and explicit_attr and t.attribute_kind:
            slug = slugify(t.mention or t.attribute_kind)
            final = f"{entity}.{slug}"
            k = 2
            while final in graph.subentities or any(v.id == final for v in virtual):
                final = f"{entity}.{slug}_{k}"
                k += 1
            temp = f"{TEMP_PREFIX}{final}"
            name = (t.mention or t.attribute_kind.replace("_", " ")).strip()
            name = name[:1].upper() + name[1:]
            new_ops.append(AddSubentity(entity=entity, temp_id=temp, name=name, attribute_kind=t.attribute_kind,
                                        unit="index", features=dict(t.constraints),
                                        aliases=[t.mention] if t.mention else [],
                                        family=vocab.family(t.attribute_kind)))
            virtual.append(_VirtualSub(final, entity, name, t.attribute_kind, dict(t.constraints),
                                       [t.mention] if t.mention else []))
            chosen = temp
            created = True
            sub_cands = [(final, 1.0)]
        if chosen is None:
            return {"level": Specificity.ENTITY, "ref": entity, "candidates": sub_cands or [(entity, 1.0)]}
        ref = chosen if chosen.startswith(TEMP_PREFIX) else chosen
        steps.append(RefinementStep(op_index=idx, end=end, from_level=Specificity.ENTITY, to_level=Specificity.SUBENTITY,
                                    node_id=strip_temp(ref), candidates=sub_cands[:5], created=created,
                                    reason=("creates " if created else "binds ") + strip_temp(ref)))
        return {"level": Specificity.SUBENTITY, "ref": ref, "candidates": sub_cands}

    # -- refine ----------------------------------------------------------------------------
    def refine(self, event: GraphUpdateEvent, wm: WorkingMemory, ltm: LongTermMemory,
               ctx: ProcessContext) -> RefinementResult:
        cfg = ctx.config.refinement
        graph = wm.graph
        steps: list[RefinementStep] = []
        pending: list[PendingRefinement] = []
        soft: dict[str, float] = {}
        out_ops: list[Any] = []
        virtual: list[_VirtualSub] = []
        temp_map: dict[str, str] = {}
        strength = event.evidence[0].strength if event.evidence else min(1.0, event.confidence)
        for idx, op in enumerate(event.ops):
            if isinstance(op, AddEntity):
                temp_map[op.temp_id] = strip_temp(op.temp_id)
            if isinstance(op, AddSubentity):
                eid = temp_map.get(op.entity, strip_temp(op.entity))
                virtual.append(_VirtualSub(strip_temp(op.temp_id), eid, op.name, op.attribute_kind, op.features,
                                           op.aliases))
            ends = op_ends(op)
            if not ends or all(isinstance(t, ConcreteTarget) for _, t in ends):
                out_ops.append(op)
                continue
            allowed_map: dict[str, list[str]] = {}
            rel_node = None
            pattern_bonus: set[str] = set()
            if isinstance(op, AddInteraction):
                rel_node, rel_attrs = self._relation(idx, op, graph, ltm, ctx, steps)
                for end, t in ends:
                    if isinstance(t, AbstractTarget) and not t.attribute_kind:
                        allowed_map[end] = rel_attrs.get(end, [])
                if op.pattern_relation is not None:
                    pattern_bonus = self._pattern_bonus(op, wm, ltm)
            resolved: dict[str, dict[str, Any]] = {}
            new_ops: list[Any] = []
            for end, t in ends:
                if isinstance(t, ConcreteTarget):
                    resolved[end] = {"level": Specificity.SUBENTITY, "ref": t.subentity_id, "candidates": []}
                    continue
                allowed = [t.attribute_kind] if t.attribute_kind else allowed_map.get(end, [])
                resolved[end] = self._refine_end(idx, end, t, allowed, bool(t.attribute_kind), temp_map, graph, ltm,
                                                 ctx, virtual, new_ops, steps, pattern_bonus)
                resolved[end]["allowed"] = allowed
                resolved[end]["explicit"] = bool(t.attribute_kind)
            out_ops.extend(new_ops)
            if all(r["level"] == Specificity.SUBENTITY for r in resolved.values()):
                out_ops.append(self._concrete_op(op, {e: r["ref"] for e, r in resolved.items()}))
                continue
            partial = self._partial_op(op, resolved)
            out_ops_pending_end = min(resolved.items(), key=lambda kv: (int(kv[1]["level"]), kv[0]))
            end_name, info = out_ops_pending_end
            pend = PendingRefinement(
                id=f"pending:{event.id}:{idx}", op=partial, end=end_name, reached=info["level"], node_id=info["ref"],
                candidates={c: float(s) for c, s in info["candidates"]}, evidence=list(event.evidence),
                source_event_id=event.id, created_at=ctx.now,
                expires_at=ctx.now + timedelta(days=float(cfg.pending_ttl_days)), relation_node_id=rel_node,
                attribute_filter=list(info.get("allowed", [])), explicit_attribute=bool(info.get("explicit")),
                label=getattr(op, "label", None), polarity=getattr(op, "polarity", None),
                market_event_id=event.market_event_id)
            pending.append(pend)
            if isinstance(op, AddInteraction) and rel_node:
                soft[rel_node] = soft.get(rel_node, 0.0) + float(strength)
            ctx.tracer.emit(Phase.REFINE, "refine.pending", refs=[pend.id, info["ref"]], pending_id=pend.id,
                            op_index=idx, end=end_name, level=int(info["level"]), node_id=info["ref"],
                            candidates=[[c, round(float(s), 4)] for c, s in info["candidates"][:5]],
                            relation=rel_node)
        for st in steps:
            ctx.tracer.emit(Phase.REFINE, "refine.step", refs=[event.id, st.node_id], event_id=event.id,
                            op_index=st.op_index, end=st.end, from_level=int(st.from_level), to_level=int(st.to_level),
                            node_id=st.node_id, candidates=[[c, s] for c, s in st.candidates], created=st.created,
                            reason=st.reason)
        refined = event.model_copy(update={"ops": out_ops})
        return RefinementResult(event=refined, steps=steps, pending=pending, soft_support=soft)

    def _pattern_bonus(self, op: AddInteraction, wm: WorkingMemory, ltm: LongTermMemory) -> set[str]:
        ref = op.pattern_relation
        p = ltm.patterns.patterns.get(ref.pattern_id) if ref else None
        if p is None or ref.relation_index >= len(p.relations):
            return set()
        rel = p.relations[ref.relation_index]
        out: set[str] = set()
        for role_name in (rel.source_role, rel.target_role):
            role = p.role(role_name)
            if role is not None and role.generalization_id in ltm.object_taxonomy.nodes:
                out |= set(ltm.object_taxonomy.instances_under(role.generalization_id))
        for inst in wm.graph.instances.values():
            if inst.pattern_id == p.id:
                out |= set(inst.bindings.values())
        return out

    @staticmethod
    def _concrete_op(op: Any, refs: dict[str, str]) -> Any:
        if isinstance(op, (ObserveValue, ChangeValue)):
            return op.model_copy(update={"target": ConcreteTarget(subentity_id=refs["subject"])})
        return op.model_copy(update={"source": ConcreteTarget(subentity_id=refs["source"]),
                                     "target": ConcreteTarget(subentity_id=refs["target"])})

    @staticmethod
    def _partial_op(op: Any, resolved: dict[str, dict[str, Any]]) -> Any:
        """The op as specific as it got: concrete ends become ConcreteTargets, entity-level ends
        get their entity_id."""
        updates: dict[str, Any] = {}
        for end, info in resolved.items():
            field = "target" if end == "subject" else end
            cur = getattr(op, field)
            if info["level"] == Specificity.SUBENTITY:
                # stored pending ops outlive the event, so temp ids become the final ids they map to
                updates[field] = ConcreteTarget(subentity_id=strip_temp(info["ref"]))
            elif info["level"] == Specificity.ENTITY and isinstance(cur, AbstractTarget):
                updates[field] = cur.model_copy(update={"entity_id": info["ref"]})
            elif isinstance(cur, AbstractTarget):
                updates[field] = cur.model_copy(update={"generalization_id": info["ref"]})
        return op.model_copy(update=updates)

    # -- retry -----------------------------------------------------------------------------
    def retry_pending(self, applied: GraphUpdateEvent, wm: WorkingMemory, ltm: LongTermMemory,
                      ctx: ProcessContext) -> list[GraphUpdateEvent]:
        cfg = ctx.config.refinement
        graph = wm.graph
        vocab = ltm.attributes
        dev = wm.deviations
        w = int(ctx.config.frontier.window_steps)
        step = dev.step_of(ctx.now)
        touched: dict[str, list[tuple[str, float]]] = {}       # entity -> [(subentity, signed move)]
        for op in applied.ops:
            if isinstance(op, (ChangeValue, ObserveValue)) and isinstance(op.target, ConcreteTarget):
                sid = op.target.subentity_id
                sub = graph.subentities.get(sid)
                if sub is None:
                    continue
                move = op.delta if isinstance(op, ChangeValue) else dev.window_change(sid, step, w)
                touched.setdefault(sub.entity_id, []).append((sid, float(move)))
        out: list[GraphUpdateEvent] = []
        self.resolver.extra_subs = []  # type: ignore[attr-defined]
        for pid in sorted(wm.pending_refinements):
            pend = wm.pending_refinements[pid]
            if pend.expires_at <= ctx.now:
                continue
            op = pend.op
            t = getattr(op, "target" if pend.end in ("target", "subject") else "source")
            mention_scores: dict[str, float] = {}
            if applied.mentions and pend.candidates:
                for c in pend.candidates:
                    cand_entity = c.split(".")[0] if c not in graph.entities else c
                    if cand_entity in graph.entities:
                        s = max(self.resolver.resolve(m, getattr(t, "constraints", {}), [cand_entity], graph)[0][1]
                                for m in applied.mentions)
                        mention_scores[c] = s
            scores: dict[str, float] = {}
            for c, old in pend.candidates.items():
                s = max(old, mention_scores.get(c, 0.0))
                cand_entity = c if c in graph.entities else c.split(".")[0]
                if cand_entity in touched and self._agrees(pend, touched[cand_entity], wm, step, w):
                    s += float(cfg.evidence_bonus)
                scores[c] = s
            ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
            if not ranked:
                continue
            top, top_s = ranked[0]
            runner = ranked[1][1] if len(ranked) > 1 else 0.0
            if top_s < float(cfg.bind_score) or top_s - runner < float(cfg.bind_margin):
                continue
            entity = top if top in graph.entities else top.split(".")[0]
            sid = None
            if top in graph.subentities:
                sid = top
            elif not pend.explicit_attribute and entity in touched:
                for s_id, _mv in touched[entity]:
                    if _attr_ok(graph.subentities[s_id].attribute_kind, pend.attribute_filter, vocab):
                        sid = s_id
                        break
            if sid is None:
                subs = [s for s in self._entity_subs(entity, graph, [])
                        if _attr_ok(s.attribute_kind, pend.attribute_filter, vocab)
                        and _feats_ok(s.features, getattr(t, "constraints", {}))]
                if len(subs) == 1:
                    sid = subs[0].id
            if sid is None:
                continue
            refs = {}
            for end, tt in op_ends(op):
                if end == pend.end:
                    refs[end] = sid
                elif isinstance(tt, ConcreteTarget):
                    refs[end] = tt.subentity_id
            if len(refs) != len(op_ends(op)):
                continue
            new_op = self._concrete_op(op, refs)
            ev = GraphUpdateEvent(id=f"GUE-REF-{pend.id}", kind=EventKind.REAL, event_type="refinement",
                                  occurred_at=ctx.now, recorded_at=ctx.now, ops=[new_op],
                                  evidence=list(pend.evidence) + list(applied.evidence),
                                  market_event_id=applied.market_event_id or pend.market_event_id, produced_by="engine",
                                  confidence=min(1.0, top_s), mentions=list(applied.mentions))
            ctx.tracer.emit(Phase.REFINE, "refine.step", refs=[pend.id, sid], event_id=ev.id, pending_id=pend.id,
                            op_index=0, end=pend.end, from_level=int(pend.reached), to_level=int(Specificity.SUBENTITY),
                            node_id=sid, candidates=[[c, round(s, 4)] for c, s in ranked[:5]], created=False,
                            reason=f"new evidence from {applied.id} binds {sid}")
            out.append(ev)
        return out

    def _agrees(self, pend: PendingRefinement, moves: list[tuple[str, float]], wm: WorkingMemory, step: int,
                w: int) -> bool:
        """For an add_interaction: the target candidate moved the way the relation predicts given the
        source's recent move. For a value op: any move counts."""
        op = pend.op
        if not isinstance(op, AddInteraction):
            return True
        pol = pend.polarity or 1
        other = op.source if pend.end == "target" else op.target
        if not isinstance(other, ConcreteTarget):
            return False
        other_move = wm.deviations.window_change(strip_temp(other.subentity_id), step, w)
        for _sid, mv in moves:
            if mv == 0 or other_move == 0:
                continue
            if pend.end == "target" and (pol * other_move) * mv > 0:
                return True
            if pend.end == "source" and (pol * mv) * other_move > 0:
                return True
        return False
