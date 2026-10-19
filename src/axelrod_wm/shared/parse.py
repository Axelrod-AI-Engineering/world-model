"""Parse: resolve temp ids and handle every op (§8.4.1)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from axelrod_wm.dynamics.propagation import ShockInput
from axelrod_wm.dynamics.regressors import clip_of, days_until, moderator_terms, obs_noise_of
from axelrod_wm.engine.interfaces import EventParser
from axelrod_wm.engine.registry import register
from axelrod_wm.events.graph_update import (
    AbstractTarget,
    AddEntity,
    AddInteraction,
    AddSubentity,
    AnnotateInteraction,
    ChangeMode,
    ChangeValue,
    EventKind,
    EventValidationError,
    ObserveValue,
    ProposeHypothesis,
    RetireEntity,
    RetireInteraction,
    ReweightInteraction,
    op_confidence,
    validate_event,
)
from axelrod_wm.model.distributions import Beta, Gaussian, from_link, from_link_moments, to_link
from axelrod_wm.model.entity import Entity, Subentity
from axelrod_wm.model.evidence import Evidence, Origin, SourceType
from axelrod_wm.model.hypothesis import HypothesisStatus
from axelrod_wm.model.ids import TEMP_PREFIX, entity_of, strip_temp
from axelrod_wm.model.interaction import Direction, EdgeDynamics, Interaction
from axelrod_wm.model.temporal import Bitemporal, KernelSpec, TimeState, gamma_from_mean
from axelrod_wm.shared.process import ParsedEvent
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory
    from axelrod_wm.repo.mutator import MutationTxn

PROVISIONAL_LINK_VAR = 100.0
MAX_EVIDENCE = 50


def source_type_for(produced_by: str) -> SourceType:
    return {"data_feed": SourceType.DATA, "human": SourceType.HUMAN, "hand_drawn": SourceType.NEWS,
            "template": SourceType.HUMAN, "llm": SourceType.NEWS, "engine": SourceType.MODEL}.get(
        produced_by, SourceType.MODEL if produced_by.startswith("engine") else SourceType.NEWS)


def change_size(sub: Subentity, mode: ChangeMode, delta: float, delta_sd: float = 0.0) -> tuple[float, float]:
    """Convert a change_value to a standardized (size, size_sd) at the subentity's posterior (§8.4.1)."""
    link = sub.posterior.link
    eta, _ = sub.posterior.link_moments()
    x = float(from_link(eta, link))

    def d_eta(d: float) -> float:
        if mode == ChangeMode.ABSOLUTE:
            return float(to_link(x + d, link)) - eta
        if mode == ChangeMode.RELATIVE:
            return float(to_link(x * (1.0 + d), link)) - eta
        return d * sub.scale

    size = d_eta(delta) / sub.scale
    if delta_sd <= 0:
        return size, 0.0
    if mode == ChangeMode.STANDARDIZED:
        return size, float(delta_sd)
    hi = d_eta(delta + delta_sd) / sub.scale
    lo = d_eta(delta - delta_sd) / sub.scale
    return size, abs(hi - lo) / 2.0


class _Writer:
    """Routes writes to the transaction (real events) or the overlay (hypothetical events)."""

    def __init__(self, ctx: ProcessContext, txn: MutationTxn | None) -> None:
        self.ctx = ctx
        self.txn = txn

    def new_id(self, prefix: str) -> str:
        if self.txn is not None:
            return self.txn.new_id(prefix)
        return self.ctx.overlay.next_id(prefix)  # type: ignore[union-attr]

    def add(self, collection: str, obj: Any) -> None:
        if self.txn is not None:
            self.txn.add(collection, obj)
        else:
            self.ctx.overlay.put(collection, obj)  # type: ignore[union-attr]

    def update(self, collection: str, obj_id: str, **fields: Any) -> None:
        if self.txn is not None:
            self.txn.update(collection, obj_id, **fields)
            return
        overlay = self.ctx.overlay
        target = {"entities": overlay.graph.entities, "subentities": overlay.graph.subentities,
                  "interactions": overlay.graph.interactions, "hypotheses": overlay.wm.hypotheses}[collection]
        target[obj_id] = target[obj_id].model_copy(update=fields)

    def append_to(self, collection: str, obj_id: str, field: str, *items: Any, keep_last: int | None = None) -> None:
        """Only real events append (a thesis never annotates an interaction or keeps its evidence)."""
        self.txn.append_to(collection, obj_id, field, *items, keep_last=keep_last)  # type: ignore[union-attr]


@register("parser", "default")
class DefaultParser(EventParser):
    def __init__(self, config: Any = None) -> None:
        self.config = config

    # -- helpers ---------------------------------------------------------------------------
    @staticmethod
    def _final_id(wanted: str, taken: set[str]) -> str:
        if wanted not in taken:
            return wanted
        k = 2
        while f"{wanted}_{k}" in taken:
            k += 1
        return f"{wanted}_{k}"

    def _resolve(self, ref: str, temp_map: dict[str, str]) -> str:
        if ref.startswith(TEMP_PREFIX):
            return temp_map[ref]          # validate_event has checked that every temp id is defined before use
        return ref

    def _concrete(self, target: Any, temp_map: dict[str, str], graph: Any, what: str) -> str:
        if isinstance(target, AbstractTarget):
            raise EventValidationError(f"{what}: fuzzy ends never reach parse (D10); refine the event first")
        sid = self._resolve(target.subentity_id, temp_map)
        if sid not in graph.subentities:
            raise EventValidationError(f"{what}: unknown subentity {sid!r}")
        return sid

    # -- parse -----------------------------------------------------------------------------
    def parse(self, event: GraphUpdateEvent, wm: WorkingMemory, ltm: LongTermMemory,
              ctx: ProcessContext, txn: MutationTxn | None) -> ParsedEvent:
        validate_event(event)
        cfg = ctx.config
        w = _Writer(ctx, txn)
        graph = wm.graph
        dev = wm.deviations
        real = event.kind == EventKind.REAL
        if real and txn is None:
            raise ValueError("a real event needs a transaction")
        day = dev.day_of(event.occurred_at)
        processing_day = ctx.day
        temp_map: dict[str, str] = {}
        taken = set(graph.entities) | set(graph.subentities)
        new_entities: list[str] = []
        new_subs: list[str] = []
        new_ints: list[str] = []
        named_ints: list[str] = []
        annotated: list[str] = []
        shocks: list[ShockInput] = []
        observations: list[tuple[str, float, float, Any]] = []
        change_obs: list[tuple[str, float, float, Any]] = []
        provided_subs: dict[str, list[str]] = dict(ctx.notes.get("new_subentities", {}))
        provided_ints: dict[str, list[str]] = dict(ctx.notes.get("new_interactions", {}))
        human = event.produced_by == "human"
        proposal_kind = ctx.notes.get("proposal_kind")
        max_move = 0.0
        ev_source = source_type_for(event.produced_by)
        excerpt = event.evidence[0].excerpt if event.evidence else None
        ev_strength = event.evidence[0].strength if event.evidence else min(1.0, event.confidence)
        retired_ints: list[str] = []
        retired_ents: list[str] = []
        retired_subs: list[str] = []

        # DECISION (Oct 8): the reviewer's confidence (the article's slider, or one change's) goes into the data it
        # writes, as Jeffrey conditioning on uncertain evidence (Jeffrey, 1965; Pearl, 1988): an interaction's
        # existence prior and evidence strength shrink toward "no information"; an observation's noise grows by
        # 1/sqrt(c); a reported move happens with probability c (its mean is c times the move, its variance gains
        # c(1-c) times its square). New entities and values record it. At c = 1 nothing changes.
        for idx, op in enumerate(event.ops):
            c = op_confidence(event, op)
            if isinstance(op, AddEntity):
                final = self._final_id(strip_temp(op.temp_id), taken)
                taken.add(final)
                temp_map[op.temp_id] = final
                ent = Entity(id=final, name=op.name, kind=op.kind, aliases=op.aliases,
                             category_tags=set(op.category_tags), features=op.features,
                             origin=Origin.HUMAN if human else Origin.EVENT_PARSING, created_at=ctx.now,
                             user_confidence=round(c, 4))
                w.add("entities", ent)
                new_entities.append(final)
            elif isinstance(op, AddSubentity):
                eid = self._resolve(op.entity, temp_map)
                if eid not in graph.entities:
                    raise EventValidationError(f"op {idx}: unknown entity {eid!r}")
                slug = strip_temp(op.temp_id).split(".", 1)[-1]
                final = self._final_id(f"{eid}.{slug}", taken)
                taken.add(final)
                temp_map[op.temp_id] = final
                family = op.family or ctx.vocab.family(op.attribute_kind)
                if op.prior is not None:
                    prior = op.prior
                    if op.prior.family != family:
                        family = op.prior.family
                else:
                    prior = from_link_moments(family, 0.0, PROVISIONAL_LINK_VAR)
                m, _ = prior.link_moments()
                sub = Subentity(id=final, entity_id=eid, name=op.name, attribute_kind=op.attribute_kind, unit=op.unit,
                                aliases=op.aliases, features=op.features, scale=op.scale or 1.0, prior=prior,
                                posterior=prior, anchor=m, origin=Origin.HUMAN if human else Origin.EVENT_PARSING,
                                user_confidence=round(c, 4))
                w.add("subentities", sub)
                ent = graph.entities[eid]
                w.update("entities", eid, subentity_ids=list(ent.subentity_ids) + [final])
                new_subs.append(final)
                provided_subs[final] = [k for k, v in (("prior", op.prior), ("scale", op.scale),
                                                       ("family", op.family)) if v is not None]
                # DECISION (Oct 8): a value an actor sets (a policy rate) may arrive by event; the feature
                # decision_variable=true makes it a decision variable, so its moves go to the actor's memory
                if real and op.features.get("decision_variable") == "true" and final not in wm.decision_variables:
                    txn.set("wm.decision_variables", list(wm.decision_variables) + [final])
            elif isinstance(op, AddInteraction):
                src = self._concrete(op.source, temp_map, graph, f"op {idx} source")
                tgt = self._concrete(op.target, temp_map, graph, f"op {idx} target")
                iid = w.new_id("int")
                if human:
                    origin = Origin.HUMAN
                elif proposal_kind == "frontier_promotion":
                    origin = Origin.FRONTIER_PROMOTION
                elif proposal_kind == "missing_relation":
                    origin = Origin.INFERENCE
                else:
                    origin = Origin.EVENT_PARSING
                placeholder = EdgeDynamics(effect=Gaussian(mu=0.0, sigma=1.0),
                                           kernel=KernelSpec(delay=gamma_from_mean(14), lag=gamma_from_mean(30)))
                # copies: the interaction's dynamics are learned in place, and must not change the op (a proposal's
                # event, or a hedge's stored op) they came from
                dyn = op.dynamics.model_copy(deep=True) if op.dynamics is not None else placeholder
                reverse = op.reverse.model_copy(deep=True) if op.reverse is not None else None
                if op.direction == Direction.BIDIRECTIONAL and reverse is None:
                    reverse = dyn.model_copy(deep=True)   # its own copy, or refitting one direction moves both
                evid = Evidence(id=w.new_id("EV"), source_type=ev_source, excerpt=excerpt or op.label,
                                observed_at=event.occurred_at, strength=min(1.0, max(ev_strength * c, 0.0)),
                                market_event_id=event.market_event_id, user_confidence=round(c, 4))
                existence = op.existence or Beta(alpha=1.0, beta=1.0)
                if c < 1.0 and not op.hedge:        # a hedge's soft interactions already carry it
                    existence = Beta(alpha=1.0 + c * (existence.alpha - 1.0), beta=1.0 + c * (existence.beta - 1.0))
                inter = Interaction(id=iid, source_id=src, target_id=tgt, label=op.label, direction=op.direction,
                                    edge_type=op.edge_type, origin=origin,
                                    tags=[f"hedge:{op.hedge}"] if op.hedge else [],
                                    existence=existence, forward=dyn,
                                    reverse=reverse if op.direction == Direction.BIDIRECTIONAL else None,
                                    parameters=op.parameters, evidence=[evid],
                                    internal=entity_of(src) == entity_of(tgt), created_at=ctx.now,
                                    generalization_id=None)
                w.add("interactions", inter)
                new_ints.append(iid)
                provided_ints[iid] = [k for k, v in (("dynamics", op.dynamics), ("existence", op.existence),
                                                     ("reverse", op.reverse)) if v is not None]
                ctx.notes.setdefault("polarity", {})[iid] = op.polarity
                ctx.notes.setdefault("relation_gen", {})[iid] = op.interaction_generalization_id
                if inter.internal:
                    ent = (ctx.wm.graph.entities[entity_of(src)])
                    w.update("entities", ent.id, internal_interaction_ids=list(ent.internal_interaction_ids) + [iid])
                if real:
                    self._close_frontier(src, tgt, ctx, txn)
            elif isinstance(op, ReweightInteraction):
                inter = graph.interactions.get(op.interaction_id)
                if inter is None:
                    raise EventValidationError(f"op {idx}: unknown interaction {op.interaction_id!r}")
                a, b = inter.existence.alpha, inter.existence.beta
                if op.supports:
                    a += op.strength * c
                else:
                    b += op.strength * c
                w.update("interactions", inter.id, existence=Beta(alpha=a, beta=b))
                if real:
                    ts = TimeState(at=Bitemporal(valid_at=event.occurred_at, recorded_at=ctx.now),
                                   values={"existence_mean": a / (a + b), "strength": op.strength,
                                           "supports": 1.0 if op.supports else 0.0},
                                   source_event_id=event.id, note="reweight")
                    w.append_to("interactions", inter.id, "time_states", ts)
                    evid = Evidence(id=w.new_id("EV"), source_type=ev_source, excerpt=excerpt or event.id,
                                    observed_at=event.occurred_at, strength=min(1.0, op.strength * c),
                                    market_event_id=event.market_event_id, user_confidence=round(c, 4))
                    _append_evidence(w, inter, evid)
                named_ints.append(inter.id)
            elif isinstance(op, AnnotateInteraction):
                if not real:
                    continue
                inter = graph.interactions.get(op.interaction_id)
                if inter is None:
                    raise EventValidationError(f"op {idx}: unknown interaction {op.interaction_id!r}")
                note = op.note if op.valid_to is None else f"{op.note} (until {op.valid_to.date().isoformat()})"
                ts = TimeState(at=Bitemporal(valid_at=op.valid_from, recorded_at=ctx.now), values={},
                               source_event_id=event.id, note=note)
                w.append_to("interactions", inter.id, "time_states", ts)
                evid = Evidence(id=w.new_id("EV"), source_type=ev_source, excerpt=excerpt or op.note,
                                observed_at=event.occurred_at, strength=min(1.0, ev_strength * c),
                                market_event_id=event.market_event_id, user_confidence=round(c, 4))
                _append_evidence(w, inter, evid)
                named_ints.append(inter.id)
                annotated.append(inter.id)
            elif isinstance(op, ProposeHypothesis):
                h = op.hypothesis
                hid = h.id
                if hid in ctx.wm.hypotheses or not hid:
                    hid = w.new_id("H")
                update: dict[str, Any] = {"id": hid}
                if not real:
                    update["from_thesis"] = ctx.scope or event.id
                w.add("hypotheses", h.model_copy(update=update))
            elif isinstance(op, ObserveValue):
                sid = self._concrete(op.target, temp_map, ctx.wm.graph, f"op {idx}")
                sub = ctx.wm.graph.subentities[sid]
                noise = op.noise_sd if op.noise_sd is not None else obs_noise_of(sub, ctx.wm, ctx.vocab)
                noise = float(noise) / math.sqrt(max(c, 0.02))
                observations.append((sid, op.value, float(noise), op.observed_at))
            elif isinstance(op, ChangeValue):
                sid = self._concrete(op.target, temp_map, ctx.wm.graph, f"op {idx}")
                sub = ctx.wm.graph.subentities[sid]
                size, size_sd = change_size(sub, op.mode, op.delta, op.delta_sd)
                if c < 1.0:
                    size_sd = math.sqrt(c * size_sd ** 2 + c * (1.0 - c) * size ** 2)
                    size = c * size
                # a shock at or before now starts on day 1, because day 0 is the current state
                if real:
                    start = 1
                    hold = None
                else:
                    start = days_until(ctx, op.at, 1)
                    hold = int(math.ceil(op.window_days)) if op.window_days else None
                shocks.append(ShockInput(subentity_id=sid, size=size, size_sd=size_sd, start_day=start,
                                         persistence=op.persistence, intervention=bool(op.intervention and not real),
                                         hold_days=hold))
                if real:
                    r_sd = max(size_sd, float(cfg.learning.min_change_noise))
                    change_obs.append((sid, size, r_sd, op.at))
                max_move = max(max_move, abs(size))
            elif isinstance(op, RetireInteraction):
                inter = graph.interactions.get(op.interaction_id)
                if inter is None:
                    raise EventValidationError(f"op {idx}: unknown interaction {op.interaction_id!r}")
                if inter.retired_at is None:
                    retire_interaction(inter, op.reason, event.id, ctx, txn)
                    retired_ints.append(inter.id)
            elif isinstance(op, RetireEntity):
                ent = graph.entities.get(op.entity_id)
                if ent is None:
                    raise EventValidationError(f"op {idx}: unknown entity {op.entity_id!r}")
                subs, ints = retire_entity(ent, op.reason, event.id, ctx, txn)
                retired_ents.append(ent.id)
                retired_subs.extend(subs)
                retired_ints.extend(i for i in ints if i not in retired_ints)
            else:                              # ProposeSuperentity or DissolveSuperentity
                raise EventValidationError(f"op {idx} ({op.op}) is applied only by the StructuralApplier after review")

        graph = ctx.wm.graph
        ctx.notes["new_subentities"] = provided_subs
        ctx.notes["new_interactions"] = provided_ints
        touched_subs: list[str] = []

        def touch(sid: str) -> None:
            if sid and sid not in touched_subs:
                touched_subs.append(sid)

        for sid, *_ in observations + change_obs:
            touch(sid)
        for s in shocks:
            touch(s.subentity_id)
        for sid in new_subs:
            touch(sid)
        for iid in new_ints + named_ints:
            inter = graph.interactions[iid]
            touch(inter.source_id)
            touch(inter.target_id)

        # in-channels of observed subentities with |phi| >= min_regressor
        touched_ints: list[str] = list(dict.fromkeys(named_ints))
        z_before: dict[str, float] = {}
        if observations or change_obs:
            from axelrod_wm.dynamics.daily import channel_phi_today

            min_reg = float(cfg.learning.min_regressor)
            clip = clip_of(ctx)
            for sid, *_ in observations + change_obs:
                for key, inter, s, _t, dyn in graph.in_channel_items(sid):
                    params = inter.parameters if key == inter.id else []
                    mult = moderator_terms(params, dev, processing_day, clip)[0] if params else 1.0
                    phi = mult * channel_phi_today(ctx.wm, key, processing_day)
                    if abs(phi) >= min_reg and inter.id not in touched_ints and inter.id not in new_ints:
                        touched_ints.append(inter.id)
                z = dev.z_at(sid, processing_day)
                if z is not None:
                    z_before[sid] = z
        for sid, value, _noise, _at in observations:
            sub = graph.subentities[sid]
            if sid in z_before:
                y = (float(to_link(value, sub.posterior.link)) - sub.anchor) / sub.scale
                max_move = max(max_move, abs(y - z_before[sid]))

        touched_entities: list[str] = []
        for sid in touched_subs:
            e = graph.subentities[sid].entity_id if sid in graph.subentities else entity_of(sid)
            if e not in touched_entities:
                touched_entities.append(e)
        for e in new_entities:
            if e not in touched_entities:
                touched_entities.append(e)

        parsed = ParsedEvent(
            event_id=event.id, kind=event.kind, event_type=event.event_type, day=day,
            processing_day=processing_day, shocks=shocks,
            observations=observations, touched_subentity_ids=touched_subs, touched_entity_ids=touched_entities,
            new_entity_ids=new_entities, new_interaction_ids=new_ints, touched_interaction_ids=touched_ints,
            tags=list(event.tags), mentions=list(event.mentions), new_subentity_ids=new_subs,
            change_observations=change_obs, occurred_at=event.occurred_at, market_event_id=event.market_event_id,
            produced_by=event.produced_by, temp_map=temp_map, z_before=z_before, max_abs_move=max_move,
            annotated_interaction_ids=annotated, origin_hint=proposal_kind,
            retired_interaction_ids=retired_ints, retired_entity_ids=retired_ents, retired_subentity_ids=retired_subs)
        if retired_ints or retired_ents:
            ctx.tracer.emit(Phase.PARSE, "parse.retired", refs=[event.id] + retired_ents + retired_subs + retired_ints,
                            event_id=event.id, entities=retired_ents, subentities=retired_subs,
                            interactions=retired_ints)
        if new_entities or new_subs or new_ints:
            ctx.tracer.emit(Phase.PARSE, "parse.created", refs=[event.id] + new_entities + new_subs + new_ints,
                            event_id=event.id, entities=new_entities, subentities=new_subs, interactions=new_ints,
                            transient=not real)
        return parsed

    def _close_frontier(self, src: str, tgt: str, ctx: ProcessContext, txn: MutationTxn) -> None:
        """An interaction created between a frontier pair closes the entry (§8.7 step 7). Real events only."""
        for co in ctx.ltm.correlation_frontier.for_pair(src, tgt):
            if co.hypothesis_id and co.hypothesis_id in ctx.wm.hypotheses:
                txn.update("hypotheses", co.hypothesis_id, status=HypothesisStatus.SUPPORTED)
            txn.remove("ltm.correlation_frontier.entries", co.id)
            ctx.tracer.emit(Phase.FRONTIER, "frontier.closed", refs=[co.id], comovement_id=co.id,
                            earlier=co.earlier_id, later=co.later_id)


def retire_interaction(inter: Interaction, reason: str, event_id: str, ctx: ProcessContext, txn: MutationTxn) -> None:
    """An interaction leaves the current graph; a note on its history says why (restructure)."""
    ts = TimeState(at=Bitemporal(valid_at=ctx.now, recorded_at=ctx.now), values={}, source_event_id=event_id,
                   note=f"retired: {reason}")
    txn.append_to("wm.graph.interactions", inter.id, "time_states", ts)
    txn.update("wm.graph.interactions", inter.id, retired_at=ctx.now)


def retire_entity(ent: Entity, reason: str, event_id: str, ctx: ProcessContext,
                  txn: MutationTxn) -> tuple[list[str], list[str]]:
    """An entity leaves the current graph with its subentities; the interactions that touch them are
    retired, the superentity instances that bound it dissolve, and hypotheses about it close. Its entity
    memory (long-term) stays. Returns the subentity and interaction ids retired (restructure)."""
    from axelrod_wm.memory.long_term import SuperInteractionBuilder

    wm = ctx.wm
    graph = wm.graph
    subs = [sid for sid in ent.subentity_ids if sid in graph.subentities]
    gone = set(subs)
    ints: list[str] = []
    for inter in graph.active_interactions():
        if inter.source_id in gone or inter.target_id in gone:
            retire_interaction(inter, f"{ent.name} was retired: {reason}", event_id, ctx, txn)
            ints.append(inter.id)
    dissolved = False
    for iid in sorted(graph.instances):
        inst = graph.instances[iid]
        if ent.id in inst.bindings.values() or set(inst.interaction_ids) & set(ints):
            txn.remove("wm.graph.instances", iid)
            dissolved = True
            ctx.tracer.emit(Phase.PREFILL, "induce.dissolved", refs=[iid, inst.pattern_id], instance_id=iid,
                            pattern_id=inst.pattern_id, transient=False)
    for hid in sorted(wm.hypotheses):
        h = wm.hypotheses[hid]
        if h.status != HypothesisStatus.OPEN:
            continue
        if ({h.source_id, h.target_id, h.decision_subentity_id} & gone or ent.id in h.subject_entity_ids
                or (h.interaction_id and h.interaction_id in ints)):
            txn.update("wm.hypotheses", hid, status=HypothesisStatus.EXPIRED)
    for pid in sorted(wm.pending_refinements):
        pend = wm.pending_refinements[pid]
        if pend.node_id == ent.id or ent.id in pend.candidates:
            txn.remove("wm.pending_refinements", pid)
    if gone & set(wm.decision_variables):
        txn.set("wm.decision_variables", [s for s in wm.decision_variables if s not in gone])
    for sid in subs:
        txn.remove("wm.graph.subentities", sid)
    txn.remove("wm.graph.entities", ent.id)
    if dissolved:
        SuperInteractionBuilder().rebuild(graph, ctx.ltm.object_generalizations, txn)
    return subs, ints


def _append_evidence(w: _Writer, inter: Interaction, evid: Evidence) -> None:
    """Keep the 50 most recent records and count older ones (§6.7)."""
    over = len(inter.evidence) + 1 - MAX_EVIDENCE
    w.append_to("interactions", inter.id, "evidence", evid, keep_last=MAX_EVIDENCE)
    if over > 0:
        w.update("interactions", inter.id, evidence_dropped=inter.evidence_dropped + over)


append_evidence = _append_evidence
Writer = _Writer
