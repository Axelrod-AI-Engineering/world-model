"""Parse: resolve temp ids and handle every op (§8.4.1)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from axelrod_wm.core.distributions import Beta, Gaussian, from_link, from_link_moments, to_link
from axelrod_wm.core.entity import Entity, Subentity
from axelrod_wm.core.evidence import Evidence, Origin, SourceType
from axelrod_wm.core.hypothesis import HypothesisStatus
from axelrod_wm.core.ids import TEMP_PREFIX, entity_of, strip_temp
from axelrod_wm.core.interaction import Direction, EdgeDynamics, Interaction
from axelrod_wm.core.temporal import Bitemporal, KernelSpec, TimeState, gamma_from_mean
from axelrod_wm.engine.interfaces import EventParser
from axelrod_wm.engine.propagation import ShockInput
from axelrod_wm.engine.registry import register
from axelrod_wm.engine.regressors import obs_noise_of, regressor_cache, steps_until
from axelrod_wm.engine.shared import ParsedEvent
from axelrod_wm.events.graph_update import (
    AbstractTarget,
    AddEntity,
    AddInteraction,
    AddSubentity,
    AnnotateInteraction,
    ChangeMode,
    ChangeValue,
    DissolveSuperentity,
    EventKind,
    EventValidationError,
    ObserveValue,
    ProposeHypothesis,
    ProposeSuperentity,
    ReweightInteraction,
    validate_event,
)
from axelrod_wm.trace import Phase

if TYPE_CHECKING:
    from axelrod_wm.control.mutator import MutationTxn
    from axelrod_wm.engine.context import ProcessContext
    from axelrod_wm.events.graph_update import GraphUpdateEvent
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory

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

    @property
    def real(self) -> bool:
        return self.txn is not None

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
        if self.txn is not None:
            self.txn.append_to(collection, obj_id, field, *items, keep_last=keep_last)
            return
        overlay = self.ctx.overlay
        target = {"entities": overlay.graph.entities, "subentities": overlay.graph.subentities,
                  "interactions": overlay.graph.interactions}[collection]
        cur = list(getattr(target[obj_id], field)) + list(items)
        if keep_last is not None:
            cur = cur[-keep_last:]
        target[obj_id] = target[obj_id].model_copy(update={field: cur})


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
            if ref not in temp_map:
                raise EventValidationError(f"temp id {ref!r} used before it is defined")
            return temp_map[ref]
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
        step = dev.step_of(event.occurred_at)
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

        for idx, op in enumerate(event.ops):
            if isinstance(op, AddEntity):
                final = self._final_id(strip_temp(op.temp_id), taken)
                taken.add(final)
                temp_map[op.temp_id] = final
                ent = Entity(id=final, name=op.name, kind=op.kind, aliases=op.aliases,
                             category_tags=set(op.category_tags), features=op.features,
                             origin=Origin.HUMAN if human else Origin.EVENT_PARSING, created_at=ctx.now)
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
                family = op.family or ltm.attributes.family(op.attribute_kind)
                if op.prior is not None:
                    prior = op.prior
                    if op.prior.family != family:
                        family = op.prior.family
                else:
                    prior = from_link_moments(family, 0.0, PROVISIONAL_LINK_VAR)
                m, _ = prior.link_moments()
                sub = Subentity(id=final, entity_id=eid, name=op.name, attribute_kind=op.attribute_kind, unit=op.unit,
                                aliases=op.aliases, features=op.features, scale=op.scale or 1.0, prior=prior,
                                posterior=prior, anchor=m, origin=Origin.HUMAN if human else Origin.EVENT_PARSING)
                w.add("subentities", sub)
                ent = graph.entities[eid]
                w.update("entities", eid, subentity_ids=list(ent.subentity_ids) + [final])
                new_subs.append(final)
                provided_subs[final] = [k for k, v in (("prior", op.prior), ("scale", op.scale),
                                                       ("family", op.family)) if v is not None]
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
                dyn = op.dynamics or placeholder
                reverse = op.reverse
                if op.direction == Direction.BIDIRECTIONAL and reverse is None:
                    reverse = dyn
                evid = Evidence(id=w.new_id("EV"), source_type=ev_source, excerpt=excerpt or op.label,
                                observed_at=event.occurred_at, strength=min(1.0, max(ev_strength, 0.0)),
                                market_event_id=event.market_event_id)
                inter = Interaction(id=iid, source_id=src, target_id=tgt, label=op.label, direction=op.direction,
                                    edge_type=op.edge_type, origin=origin,
                                    existence=op.existence or Beta(alpha=1.0, beta=1.0), forward=dyn,
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
                    a += op.strength
                else:
                    b += op.strength
                w.update("interactions", inter.id, existence=Beta(alpha=a, beta=b))
                if real:
                    ts = TimeState(at=Bitemporal(valid_at=event.occurred_at, recorded_at=ctx.now),
                                   values={"existence_mean": a / (a + b), "strength": op.strength,
                                           "supports": 1.0 if op.supports else 0.0},
                                   source_event_id=event.id, note="reweight")
                    w.append_to("interactions", inter.id, "time_states", ts)
                    evid = Evidence(id=w.new_id("EV"), source_type=ev_source, excerpt=excerpt or event.id,
                                    observed_at=event.occurred_at, strength=min(1.0, op.strength),
                                    market_event_id=event.market_event_id)
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
                                observed_at=event.occurred_at, strength=min(1.0, ev_strength),
                                market_event_id=event.market_event_id)
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
                noise = op.noise_sd if op.noise_sd is not None else obs_noise_of(sub, ctx.wm, ltm)
                observations.append((sid, op.value, float(noise), op.observed_at))
            elif isinstance(op, ChangeValue):
                sid = self._concrete(op.target, temp_map, ctx.wm.graph, f"op {idx}")
                sub = ctx.wm.graph.subentities[sid]
                size, size_sd = change_size(sub, op.mode, op.delta, op.delta_sd)
                if real:
                    start = 1
                    hold = None
                else:
                    start = steps_until(ctx, op.at, 1)
                    hold = (int(math.ceil(op.window_days / ctx.step_days)) if op.window_days else None)
                shocks.append(ShockInput(subentity_id=sid, size=size, size_sd=size_sd, start_step=start,
                                         persistence=op.persistence, intervention=bool(op.intervention and not real),
                                         hold_steps=hold))
                if real:
                    r_sd = max(size_sd, float(cfg.learning.min_change_noise))
                    change_obs.append((sid, size, r_sd, op.at))
                max_move = max(max_move, abs(size))
            elif isinstance(op, (ProposeSuperentity, DissolveSuperentity)):
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
            cache = regressor_cache(ctx.wm, ctx)
            min_reg = float(cfg.learning.min_regressor)
            for sid, *_ in observations + change_obs:
                for key, inter, s, _t, dyn in graph.in_channel_items(sid):
                    phi, _ = cache.phi(key, s, dyn, inter.parameters if key == inter.id else [], step)
                    if abs(phi) >= min_reg and inter.id not in touched_ints and inter.id not in new_ints:
                        touched_ints.append(inter.id)
                z = dev.z_at(sid, step)
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
            event_id=event.id, kind=event.kind, event_type=event.event_type, step=step, shocks=shocks,
            observations=observations, touched_subentity_ids=touched_subs, touched_entity_ids=touched_entities,
            new_entity_ids=new_entities, new_interaction_ids=new_ints, touched_interaction_ids=touched_ints,
            tags=list(event.tags), mentions=list(event.mentions), new_subentity_ids=new_subs,
            change_observations=change_obs, occurred_at=event.occurred_at, market_event_id=event.market_event_id,
            produced_by=event.produced_by, temp_map=temp_map, z_before=z_before, max_abs_move=max_move,
            annotated_interaction_ids=annotated, origin_hint=proposal_kind)
        if new_entities or new_subs or new_ints:
            ctx.tracer.emit(Phase.PARSE, "parse.created", refs=[event.id] + new_entities + new_subs + new_ints,
                            event_id=event.id, entities=new_entities, subentities=new_subs, interactions=new_ints,
                            transient=not real)
        return parsed

    def _close_frontier(self, src: str, tgt: str, ctx: ProcessContext, txn: MutationTxn | None) -> None:
        """An interaction created between a frontier pair closes the entry (§8.7 step 7)."""
        if txn is None:
            return
        for co in ctx.ltm.frontier.for_pair(src, tgt):
            if co.hypothesis_id and co.hypothesis_id in ctx.wm.hypotheses:
                txn.update("hypotheses", co.hypothesis_id, status=HypothesisStatus.SUPPORTED)
            txn.remove("frontier", co.id)
            ctx.tracer.emit(Phase.FRONTIER, "frontier.closed", refs=[co.id], comovement_id=co.id,
                            earlier=co.earlier_id, later=co.later_id)


def _append_evidence(w: _Writer, inter: Interaction, evid: Evidence) -> None:
    """Keep the 50 most recent records and count older ones (§6.7)."""
    cur = inter.evidence
    if len(cur) + 1 > MAX_EVIDENCE:
        w.update("interactions", inter.id, evidence=(list(cur) + [evid])[-MAX_EVIDENCE:],
                 evidence_dropped=inter.evidence_dropped + len(cur) + 1 - MAX_EVIDENCE)
    else:
        w.append_to("interactions", inter.id, "evidence", evid)


append_evidence = _append_evidence
Writer = _Writer
