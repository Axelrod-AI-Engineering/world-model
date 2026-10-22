"""The refiner: from broad to concrete, as far as evidence allows (§7.5, D3, D10).

DECISION (Oct 8): a mention binds outright only when it names one candidate (it contains the candidate's name or an
alias; see `_names`). Otherwise the end is hedged: a Dirichlet posterior over the candidates the taxonomy
allows, plus an open-world reserve for one not in the graph yet (Ferguson, 1973). Deferring the choice and
weighing every live candidate follows multiple-hypothesis tracking (Reid, 1979) and probabilistic data association
(Bar-Shalom, Daum, & Huang, 2009); a hedge resolves only when later evidence carries one candidate past a bound,
as in a sequential test (Wald, 1945). `weigh_hedges` runs inside each event's staged learning, so a person sees
every change to a hedge before it is committed."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

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
    RetireInteraction,
    ReweightInteraction,
    Specificity,
    op_confidence,
    op_ends,
)
from axelrod_wm.intake.resolver import AliasFuzzyResolver, EntityResolver, text_similarity
from axelrod_wm.memory.working import HedgeCheck, PendingRefinement
from axelrod_wm.model.distributions import Beta
from axelrod_wm.model.ids import TEMP_PREFIX, slugify, strip_temp
from axelrod_wm.model.taxonomy import Signature, label_family
from axelrod_wm.shared.classify import node_signature
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.model.graph import CausalGraph


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
    """refine() is pure: its result travels inside a Proposal and is applied when the proposal is approved (§7.6).
    weigh_hedges() runs inside an event's (staged) learning and writes only through the transaction it is given."""

    @abstractmethod
    def refine(self, event: GraphUpdateEvent, wm: WorkingMemory, ltm: LongTermMemory,
               ctx: ProcessContext) -> RefinementResult: ...

    def weigh_hedges(self, event: GraphUpdateEvent, parsed: Any, fold: Any, wm: WorkingMemory, ctx: ProcessContext,
                     txn: Any) -> list[dict]:
        """Weigh one learned event's evidence for every hedged fuzzy end; return the resolution proposals it raises."""
        return []


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


def _norm(text: str) -> str:
    """Lowercase words only: possessives and punctuation go ("airlines' jet fuel" -> "airlines jet fuel")."""
    return " " + re.sub(r"[^a-z0-9]+", " ", re.sub(r"['’]s?\b", "", (text or "").lower())).strip() + " "


def _signature_attrs(sig: Signature, key: str) -> list[str]:
    return list(sig.required.get(key, [])) + [v for v in sig.any_of.get(key, []) if v not in sig.required.get(key, [])]


@register("refiner", "taxonomy")
class TaxonomyRefiner(Refiner):
    def __init__(self, config: Any = None, entity_resolver: EntityResolver | None = None, engine: Any = None,
                 vocab: Any = None) -> None:
        self.config = config
        self.engine = engine
        self._vocab = vocab
        self.resolver = entity_resolver or AliasFuzzyResolver(config)

    @property
    def vocab(self) -> Any:
        """The attribute vocabulary (from the construction spec, through the engine)."""
        if self._vocab is not None:
            return self._vocab
        from axelrod_wm.model.taxonomy import AttributeVocabulary

        return getattr(self.engine, "vocab", None) or AttributeVocabulary(kinds={})

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

    def _names(self, mention: str | None, eid: str, graph: CausalGraph, virtual: list[_VirtualSub]) -> bool:
        """DECISION (Oct 8): an article names a candidate when its mention contains the entity's name or an alias, or
        the name or an alias of one of its values ("export controls on advanced chips" names the export controls).
        Resolver similarity alone cannot tell naming from describing: "airlines' jet fuel costs" resembles Delta
        without naming it, so it stays a hedge."""
        if not mention or eid not in graph.entities:
            return False
        m = _norm(mention)
        e = graph.entities[eid]
        phrases = [e.name, *e.aliases]
        for sub in self._entity_subs(eid, graph, virtual):
            phrases += [sub.name, *getattr(sub, "aliases", [])]
        for ph in phrases:
            n = _norm(ph)
            if len(n.strip()) >= 3 and n in m:
                return True
        return False

    def _named_value(self, mention: str | None, eid: str, graph: CausalGraph, allowed: list[str]) -> str | None:
        """The one value of `eid` (of an allowed attribute kind) whose name or alias the mention contains, if exactly one."""
        if not mention or eid not in graph.entities:
            return None
        m = _norm(mention)
        hits = []
        for sub in self._entity_subs(eid, graph, []):
            if not _attr_ok(sub.attribute_kind, allowed, self.vocab):
                continue
            if any(len(_norm(ph).strip()) >= 3 and _norm(ph) in m for ph in [sub.name, *getattr(sub, "aliases", [])]):
                hits.append(sub.id)
        return hits[0] if len(hits) == 1 else None

    def _entity_instances(self, gen_id: str, ltm: LongTermMemory, graph: CausalGraph) -> list[str]:
        return [i for i in ltm.object_generalizations.taxonomy.instances_under(gen_id) if i in graph.entities]

    def _signature_fit(self, gen_id: str, allowed: list[str], constraints: dict[str, str], ltm: LongTermMemory,
                       graph: CausalGraph, virtual: list[_VirtualSub]) -> float:
        reqs = (1 if allowed else 0) + len(constraints)
        if reqs == 0:
            return 0.0
        ents = self._entity_instances(gen_id, ltm, graph)
        met = 0
        if allowed and any(self._can_satisfy(e, allowed, graph, virtual, self.vocab) for e in ents):
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
        strings = [ltm.object_generalizations.taxonomy.nodes[gen_id].name]
        for e in self._entity_instances(gen_id, ltm, graph):
            ent = graph.entities[e]
            strings += [ent.name, *ent.aliases]
            for s in self._entity_subs(e, graph, virtual):
                strings += [s.name, *getattr(s, "aliases", [])]
        return text_similarity(mention, strings)

    # -- relation (step 0) -----------------------------------------------------------------
    def _relation(self, idx: int, op: AddInteraction, graph: CausalGraph, ltm: LongTermMemory,
                  ctx: ProcessContext, steps: list[RefinementStep]) -> tuple[str, dict[str, list[str]]]:
        tax = ltm.interaction_generalizations.taxonomy
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
                if child.stats.support > thr and sig.satisfied_by_known(feats, self.vocab):
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
        tax = ltm.object_generalizations.taxonomy
        vocab = self.vocab
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
            named = [e for e, _ in ranked if self._names(t.mention, e, graph, virtual)]
            if len(named) == 1:
                entity = named[0]
                steps.append(RefinementStep(op_index=idx, end=end, from_level=Specificity.GENERALIZATION,
                                            to_level=Specificity.ENTITY, node_id=entity, candidates=ranked[:5],
                                            reason=f"the article names {graph.entities[entity].name}"))
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
            named = [e for e, _ in ranked if self._names(t.mention, e, graph, virtual)]
            if len(named) == 1:
                entity = named[0]
                steps.append(RefinementStep(op_index=idx, end=end, from_level=Specificity.GENERALIZATION,
                                            to_level=Specificity.ENTITY, node_id=entity, candidates=candidates[:5],
                                            reason=f"the article names {graph.entities[entity].name}"))
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
            hedge = self._hedge(event, idx, op, partial, resolved, ends, rel_node, graph, virtual, ctx)
            pending.append(hedge["pending"])
            out_ops.extend(hedge["soft_ops"])
            if isinstance(op, AddInteraction) and rel_node:
                soft[rel_node] = soft.get(rel_node, 0.0) + float(strength) * op_confidence(event, op)
            pend = hedge["pending"]
            post = pend.posterior()
            named = [(c, round(v, 4)) for c, v in sorted(post.items(), key=lambda kv: -kv[1])][:5]
            steps.append(RefinementStep(op_index=idx, end=pend.end, from_level=pend.reached, to_level=pend.reached,
                                        node_id=pend.node_id, candidates=named,
                                        reason=f"the article names none of {len(pend.alpha)} candidate(s): the end is "
                                               "hedged across them, with a share for one not in the graph yet"))
            ctx.tracer.emit(Phase.REFINE, "refine.pending", refs=[pend.id, pend.node_id], pending_id=pend.id,
                            op_index=idx, end=pend.end, ends=list(pend.ends), level=int(pend.reached),
                            node_id=pend.node_id, soft=pend.soft,
                            candidates=[[c, round(float(v), 4)] for c, v in sorted(post.items(), key=lambda kv: -kv[1])[:6]],
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
        p = ltm.object_generalizations.patterns.get(ref.pattern_id) if ref else None
        if p is None or ref.relation_index >= len(p.relations):
            return set()
        rel = p.relations[ref.relation_index]
        out: set[str] = set()
        for role_name in (rel.source_role, rel.target_role):
            role = p.role(role_name)
            if role is not None and role.generalization_id in ltm.object_generalizations.taxonomy.nodes:
                out |= set(ltm.object_generalizations.taxonomy.instances_under(role.generalization_id))
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

    # -- hedges ----------------------------------------------------------------------------
    def _hedge_candidates(self, t: Any, info: dict[str, Any], graph: CausalGraph, virtual: list[_VirtualSub],
                          max_n: int) -> list[tuple[str, float]]:
        """A fuzzy end's candidates: values where each candidate entity has exactly one value the end can take,
        else entities. Scores are the resolver's (or the subentity match's)."""
        vocab = self.vocab
        allowed = info.get("allowed", [])
        constraints = getattr(t, "constraints", {}) or {}
        out: list[tuple[str, float]] = []
        for cid, score in info.get("candidates", []):
            if cid in graph.subentities or any(v.id == cid for v in virtual) or str(cid).startswith(TEMP_PREFIX):
                out.append((strip_temp(cid), float(score)))
                continue
            if cid in graph.entities:
                subs = [x for x in self._entity_subs(cid, graph, virtual)
                        if _attr_ok(x.attribute_kind, allowed, vocab) and _feats_ok(x.features, constraints)]
                out.append((subs[0].id if len(subs) == 1 else cid, float(score)))
        seen: dict[str, float] = {}
        for cid, sc in out:
            seen[cid] = max(sc, seen.get(cid, 0.0))
        return sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))[:max_n]

    def _hedge(self, event: GraphUpdateEvent, idx: int, op: Any, partial: Any, resolved: dict[str, dict[str, Any]],
               ends: list[tuple[str, Any]], rel_node: str | None, graph: CausalGraph, virtual: list[_VirtualSub],
               ctx: ProcessContext) -> dict[str, Any]:
        """Hedge an op whose ends did not all become values: the posterior over its candidates (jointly, when
        both ends are fuzzy), and, for an interaction whose candidates are values, one soft interaction each."""
        cfg = ctx.config.refinement
        fuzzy = [e for e, r in resolved.items() if r["level"] != Specificity.SUBENTITY]
        tmap = dict(ends)
        per_end = {e: self._hedge_candidates(tmap[e], resolved[e], graph, virtual, int(cfg.hedge_max_candidates))
                   for e in fuzzy}
        keys: list[tuple[list[str], float]] = [([], 1.0)]
        for e in fuzzy:
            cands = per_end[e]
            tot = sum(max(sc, 1e-3) for _, sc in cands) or 1.0
            keys = [(k + [cid], w * max(sc, 1e-3) / tot) for k, w in keys for cid, sc in cands]
        keys = [(k, w) for k, w in keys if len(k) == len(fuzzy)]
        conf = op_confidence(event, op)
        alpha = {"|".join(k): float(cfg.hedge_prior) * w for k, w in keys}
        open_alpha = float(cfg.hedge_open_mass)
        least = min(fuzzy, key=lambda e: (int(resolved[e]["level"]), e))
        key = f"pending:{event.id}:{idx}"
        is_value = lambda c: c in graph.subentities or any(v.id == c for v in virtual)  # noqa: E731
        soft = isinstance(op, AddInteraction) and bool(alpha) and all(is_value(c) for e in fuzzy for c, _ in per_end[e])
        tot = sum(alpha.values()) + open_alpha
        post = {k: a / tot for k, a in alpha.items()}
        pend = PendingRefinement(
            id=key, key=key, op=partial, end=least, ends=fuzzy, reached=resolved[least]["level"],
            node_id=strip_temp(resolved[least]["ref"]), candidates=post, alpha=alpha, open_alpha=open_alpha,
            evidence=list(event.evidence), source_event_id=event.id, created_at=ctx.now,
            expires_at=ctx.now + timedelta(days=float(cfg.pending_ttl_days)), relation_node_id=rel_node,
            attribute_filter=list(resolved[least].get("allowed", [])), explicit_attribute=bool(resolved[least].get("explicit")),
            label=getattr(op, "label", None), polarity=getattr(op, "polarity", None),
            market_event_id=event.market_event_id, soft=soft, user_confidence=conf,
            checks=[HedgeCheck(at=ctx.now, event_id=event.id, market_event_id=event.market_event_id, kind="intake",
                               confidence=conf, posterior={**post, "__open__": open_alpha / tot})])
        soft_ops = []
        if soft:
            kappa = float(cfg.soft_edge_concentration)
            concrete = {e: strip_temp(r["ref"]) for e, r in resolved.items() if r["level"] == Specificity.SUBENTITY}
            for k, a in alpha.items():
                refs = dict(concrete)
                refs.update(dict(zip(fuzzy, k.split("|"))))
                # a candidate the article introduced keeps its temp id until parsing gives it its final one
                refs = {e: (r if r in graph.subentities else next((f"{TEMP_PREFIX}{v.id}" for v in virtual if v.id == r), r))
                        for e, r in refs.items()}
                pk = a / tot * conf
                soft_ops.append(self._concrete_op(op, refs).model_copy(update={
                    "existence": Beta(alpha=max(0.05, kappa * pk), beta=max(0.05, kappa * (1.0 - pk))), "hedge": key}))
        return {"pending": pend, "soft_ops": soft_ops}

    def weigh_hedges(self, event: GraphUpdateEvent, parsed: Any, fold: Any, wm: WorkingMemory, ctx: ProcessContext,
                     txn: Any) -> list[dict]:
        """Each hedge weighs the event as evidence (Oct 8). A candidate the article names gains `mention_weight` times
        the resolver's score; a candidate value that moved the way the interaction predicts gains `move_weight`, and
        one that moved against it passes that weight to its rivals and the open reserve. Every gain is times the
        reviewer's confidence. A soft interaction's existence follows its candidate's probability. A candidate past
        `commit_posterior` with recognition-many checks raises a refinement proposal: keep it, retire its rivals."""
        if ctx.initializing or not wm.pending_refinements or event.kind != EventKind.REAL:
            return []
        cfg = ctx.config.refinement
        graph = wm.graph
        dev = wm.deviations
        w = int(ctx.config.abduction.window_days)
        spacing = int(ctx.config.frontier.evidence_spacing_days)
        day = int(getattr(fold, "day", ctx.today))
        conf = float(min(1.0, max(0.0, event.user_confidence)))
        headline = ctx.notes.get("headline")
        moved: dict[str, float] = {}
        for sh in getattr(parsed, "shocks", []):
            moved[sh.subentity_id] = float(sh.size)
        for sid, innov in (getattr(fold, "innovations", {}) or {}).items():
            if abs(innov) >= 0.5:
                moved.setdefault(sid, float(innov))
        mentions = list(event.mentions)
        out: list[dict] = []
        self.resolver.extra_subs = []  # type: ignore[attr-defined]
        for pid in sorted(wm.pending_refinements):
            pend = wm.pending_refinements[pid]
            if pend.source_event_id == event.id or (pend.expires_at <= ctx.now and not pend.soft) or pend.status != "holding":
                continue
            alpha = dict(pend.alpha) or {c: float(cfg.hedge_prior) * v for c, v in pend.candidates.items()}
            open_alpha = pend.open_alpha
            ends = pend.ends or [pend.end]
            checks: list[HedgeCheck] = []

            # 0. narrowing: a candidate that is a whole entity becomes one of its values when the article names that
            # value ("chip capex" names Productivity & technology's tech capex); its weight goes with it
            if mentions and len(ends) == 1:
                for c in sorted(alpha):
                    if c in graph.entities:
                        sid = next((v for v in (self._named_value(m, c, graph, pend.attribute_filter) for m in mentions) if v), None)
                        if sid and sid not in alpha:
                            alpha[sid] = alpha.pop(c)
                            checks.append(HedgeCheck(at=ctx.now, event_id=event.id, market_event_id=event.market_event_id,
                                                     headline=headline, kind="narrowed", candidate=sid, confidence=conf,
                                                     posterior={}))
            # 1. mentions: the article names a candidate (its entity, or one of its values)
            if mentions:
                for c in sorted(alpha):
                    ents = {cid if cid in graph.entities else cid.split(".")[0] for cid in c.split("|")}
                    if any(self._names(m, ent, graph, []) for ent in ents for m in mentions):
                        gain = float(cfg.mention_weight) * conf
                        alpha[c] += gain
                        checks.append(HedgeCheck(at=ctx.now, event_id=event.id, market_event_id=event.market_event_id,
                                                 headline=headline, kind="mention", candidate=c, weight=round(gain, 4),
                                                 confidence=conf, posterior={}))
            # 2. moves: a candidate value moved the way the interaction predicts (at most once per spacing)
            if moved and isinstance(pend.op, AddInteraction):
                pol = pend.polarity or 1
                for c in sorted(alpha):
                    refs = dict(zip(ends, c.split("|")))
                    for end, tt in op_ends(pend.op):
                        if end not in refs and isinstance(tt, ConcreteTarget):
                            refs[end] = strip_temp(tt.subentity_id)
                    src, tgt = refs.get("source"), refs.get("target")
                    if not src or not tgt:
                        continue
                    # only a move of the candidate's own value tells the candidates apart; a move of the end
                    # the article named (oil) is the same evidence for every candidate
                    own = [refs[e] for e in ends if refs.get(e) in moved and refs[e] in graph.subentities]
                    if not own:
                        continue
                    hit = own[0]
                    last = max((dev.day_of(ck.at) for ck in pend.checks if ck.candidate == c and ck.kind in ("move", "against")),
                               default=None)
                    if last is not None and day - last < spacing:
                        continue
                    other = dev.window_change(src if hit == tgt else tgt, day, w)
                    mv = moved[hit]
                    if other == 0 or mv == 0:
                        continue
                    gain = float(cfg.move_weight) * conf
                    if pol * other * mv > 0:
                        alpha[c] += gain
                        checks.append(HedgeCheck(at=ctx.now, event_id=event.id, market_event_id=event.market_event_id,
                                                 headline=headline, kind="move", candidate=c, weight=round(gain, 4),
                                                 confidence=conf, posterior={}))
                    else:
                        rivals = [k for k in alpha if k != c]
                        share = gain / (len(rivals) + 1)
                        for k in rivals:
                            alpha[k] += share
                        open_alpha += share
                        checks.append(HedgeCheck(at=ctx.now, event_id=event.id, market_event_id=event.market_event_id,
                                                 headline=headline, kind="against", candidate=c, weight=round(gain, 4),
                                                 confidence=conf, posterior={}))
            if not checks:
                continue
            tot = sum(alpha.values()) + open_alpha
            post = {**{c: a / tot for c, a in alpha.items()}, "__open__": open_alpha / tot}
            checks = [ck.model_copy(update={"posterior": {k: round(v, 4) for k, v in post.items()}}) for ck in checks]
            # DECISION (Oct 9): support counts articles, not check records: one article that names two candidates, or
            # names one and moves it, is one piece of evidence. Narrowing is not evidence.
            support = pend.support + (1 if any(ck.kind != "narrowed" for ck in checks) else 0)
            # a hedge that is still gathering evidence lives on: its time runs from the latest check
            ttl = timedelta(days=float(cfg.pending_ttl_days))
            txn.update("wm.pending_refinements", pid, alpha=alpha, open_alpha=open_alpha, support=support,
                       expires_at=max(pend.expires_at, ctx.now + ttl),
                       candidates={k: v for k, v in post.items() if k != "__open__"},
                       checks=(list(pend.checks) + checks)[-20:])
            ctx.tracer.emit(Phase.REFINE, "refine.weighed", refs=[pid, *[ck.candidate for ck in checks if ck.candidate]],
                            pending_id=pid, key=pend.key, posterior={k: round(v, 4) for k, v in post.items()},
                            checks=[{"kind": ck.kind, "candidate": ck.candidate, "weight": ck.weight} for ck in checks])
            # the soft interactions follow the posterior
            soft_ids = self._soft_interactions(pend, graph)
            if soft_ids:
                kappa = float(cfg.soft_edge_concentration) + support
                for c, iid in soft_ids.items():
                    pk = post.get(c, 0.0) * pend.user_confidence
                    txn.update("wm.graph.interactions", iid,
                               existence=Beta(alpha=max(0.05, kappa * pk), beta=max(0.05, kappa * (1.0 - pk))))
            # resolution: one candidate past the bound, with enough checks
            top = max(((k, v) for k, v in post.items() if k != "__open__"), key=lambda kv: kv[1], default=None)
            if top and top[1] >= float(cfg.commit_posterior) and support >= ctx.recognition:
                ev = self._resolution(pend, top[0], soft_ids, event, ctx)
                if ev is not None:
                    txn.update("wm.pending_refinements", pid, status="resolution_proposed")
                    ctx.tracer.emit(Phase.REFINE, "refine.resolution_proposed", refs=[pid, top[0]], pending_id=pid,
                                    candidate=top[0], posterior=round(top[1], 4), support=support)
                    out.append({"kind": "refinement", "event": ev.model_dump(mode="json"), "subject_id": pid,
                                "retires_pending_id": pid,
                                "reason": f"{top[0]} at {top[1]:.0%} after {support:.0f} checks"})
        return out

    @staticmethod
    def _soft_interactions(pend: PendingRefinement, graph: CausalGraph) -> dict[str, str]:
        """A soft hedge's interactions, by candidate key."""
        if not pend.soft or not pend.key:
            return {}
        ends = pend.ends or [pend.end]
        out: dict[str, str] = {}
        for iid, it in graph.interactions.items():
            if not it.active or f"hedge:{pend.key}" not in it.tags:
                continue
            refs = {"source": it.source_id, "target": it.target_id}
            out["|".join(refs[e] for e in ends)] = iid
        return out

    def _resolution(self, pend: PendingRefinement, winner: str, soft_ids: dict[str, str], event: GraphUpdateEvent,
                    ctx: ProcessContext) -> GraphUpdateEvent | None:
        """The proposal that settles a hedge: keep the winner (its soft interaction becomes firm), retire the rivals'
        soft interactions; or, with no soft interactions, the op with the winner's ends."""
        ends = pend.ends or [pend.end]
        ops: list[Any] = []
        if soft_ids:
            if winner not in soft_ids:
                return None
            ops.append(ReweightInteraction(interaction_id=soft_ids[winner], supports=True, strength=2.0))
            for c, iid in sorted(soft_ids.items()):
                if c != winner:
                    ops.append(RetireInteraction(interaction_id=iid, reason=f"the fuzzy end resolved to {winner}"))
        else:
            refs = dict(zip(ends, winner.split("|")))
            if any(r not in ctx.wm.graph.subentities for r in refs.values()):
                return None                    # an entity-level winner still needs its value: keep hedging
            for end, tt in op_ends(pend.op):
                if end not in refs:
                    if not isinstance(tt, ConcreteTarget):
                        return None
                    refs[end] = strip_temp(tt.subentity_id)
            ops.append(self._concrete_op(pend.op, refs))
        return GraphUpdateEvent(id=f"GUE-REF-{pend.id}", kind=EventKind.REAL, event_type="refinement",
                                occurred_at=ctx.now, recorded_at=ctx.now, ops=ops, evidence=list(pend.evidence),
                                market_event_id=event.market_event_id or pend.market_event_id, produced_by="engine",
                                confidence=1.0, mentions=list(event.mentions))
