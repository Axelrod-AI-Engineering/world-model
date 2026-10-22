"""The domain model, projected onto the API model (world_model/docs/design/api.md §1): an attribute is the engine's subentity, a
relationship its interaction, an event its market event, a change its proposal, a simulation its forecast. Each
function reads domain objects and returns an API object from schemas.py; nothing here writes."""

from __future__ import annotations

import hashlib
from typing import Any

from axelrod_wm.api.v1 import schemas as s

# how an object entered the model, as the kind of claim it is (facts kept apart from inferences)
EPISTEMIC_OF_ORIGIN = {"construction": "documented", "event_parsing": "reported", "frontier_promotion": "inferred",
                       "inference": "inferred", "human": "expert_judgment", "seed": "assumption"}
EVIDENCE_TYPE = {"news": "news", "data": "data_release", "filing": "company_filing", "analyst": "broker_research",
                 "human": "reviewer", "model": "model", "history": "historical_data"}
EPISTEMIC_OF_SOURCE = {"news": "reported", "data": "observed", "filing": "documented", "analyst": "broker",
                       "human": "expert_judgment", "model": "model", "history": "observed"}
EVENT_TYPE = {"news": "news", "data": "data_release", "filing": "company_filing", "analyst": "research"}
IDENTIFIER_KEYS = ("ticker", "isin", "figi", "lei", "cik", "sedol")


def owner_of(sid: str) -> str:
    """The entity an attribute id belongs to: the part before its first dot (every attribute id is `entity.key`)."""
    return sid.split(".", 1)[0]


# -- attributes ---------------------------------------------------------------------------------------------------------
def level(sub: Any) -> s.Level:
    d = sub.posterior
    try:
        q05, q95 = round(float(d.quantile(0.05)), 6), round(float(d.quantile(0.95)), 6)
    except (AttributeError, ValueError):
        q05 = q95 = None
    return s.Level(mean=round(float(d.mean()), 6), sd=round(float(d.sd()), 6), q05=q05, q95=q95)


def observations(sub: Any, occurred: dict[str, Any] | None = None) -> list[s.Observation]:
    """The attribute's dated observations, oldest first: each history point a fold of an observed value left, with the
    value in the attribute's unit (valid_at: when it applies; observed_at: when the model recorded it; occurred_at:
    when the fact occurred, from the update that carried it, e.g. a reported figure's period end)."""
    from axelrod_wm.model.distributions import from_link

    out = []
    for ts in sub.history:
        if "y" not in ts.values:
            continue
        value = round(float(from_link(sub.anchor + sub.scale * ts.values["y"], sub.link)), 6)
        oid = hashlib.sha256(f"{sub.id}|{ts.at.valid_at.isoformat()}|{ts.source_event_id}|{value}".encode()).hexdigest()
        out.append(s.Observation(id=f"obs_{oid[:16]}", attribute_id=sub.id, value=value, valid_at=ts.at.valid_at,
                                 observed_at=ts.at.recorded_at, event_id=ts.source_event_id, epistemic_type="observed",
                                 occurred_at=(occurred or {}).get(ts.source_event_id)))
    return out


def states(sub: Any) -> list[s.AttributeState]:
    return [s.AttributeState(valid_at=ts.at.valid_at, recorded_at=ts.at.recorded_at,
                             mean=round(float(ts.values["mean"]), 6), sd=round(float(ts.values.get("sd", 0.0)), 6),
                             z=None if "z" not in ts.values else round(float(ts.values["z"]), 6),
                             event_id=ts.source_event_id, note=ts.note)
            for ts in sub.history if "mean" in ts.values]


def attribute(wm: Any, sid: str, occurred: dict[str, Any] | None = None) -> s.Attribute:
    sub = wm.graph.subentities[sid]
    obs = observations(sub, occurred)
    return s.Attribute(id=sid, key=sid.removeprefix(f"{sub.entity_id}."), entity_id=sub.entity_id, name=sub.name,
                       aliases=list(sub.aliases), unit=sub.unit, concept=sub.attribute_kind,
                       view=sub.features.get("view", ""), basis=sub.features.get("basis", ""),
                       family=str(sub.posterior.family), observed=bool(sub.observed), level=level(sub),
                       latest_observation=obs[-1] if obs else None,
                       epistemic_type="observed" if sub.observed else "inferred")


# -- entities -----------------------------------------------------------------------------------------------------------
def concepts(ltm: Any, gid: str | None) -> list[s.ConceptRef]:
    tax = ltm.object_generalizations.taxonomy
    if not gid or gid not in tax.nodes:
        return []
    return [s.ConceptRef(id=n, name=tax.nodes[n].name) for n in tax.path_from_root(gid) if n != tax.root_id]


def own_attributes(wm: Any, eid: str) -> list[str]:
    return sorted(x for x in wm.graph.entities[eid].subentity_ids if x in wm.graph.subentities)


def entity(wm: Any, ltm: Any, eid: str, attribute_ids: list[str] | None = None,
           relationships: list[s.Relationship] | None = None, occurred: dict[str, Any] | None = None) -> dict:
    """An entity with its attributes nested: all of them, or only `attribute_ids` (those an answer reached or matched)."""
    e = wm.graph.entities[eid]
    own = own_attributes(wm, eid)
    shown = own if attribute_ids is None else sorted(attribute_ids)
    groups = sorted(i.id for i in wm.graph.instances.values() if eid in i.bindings.values())
    out = s.Entity(id=eid, type=str(e.kind), name=e.name, aliases=list(e.aliases),
                   identifiers={k: v for k, v in sorted(e.features.items()) if k in IDENTIFIER_KEYS},
                   description=e.description, concepts=concepts(ltm, e.generalization_id),
                   features=dict(sorted(e.features.items())), group_ids=groups, attribute_count=len(own),
                   attributes=[attribute(wm, x, occurred) for x in shown], relationships=relationships, origin=str(e.origin),
                   created_at=e.created_at)
    return out.model_dump(mode="json", exclude={"relationships"} if relationships is None else set())


# -- relationships and evidence -------------------------------------------------------------------------------------------
def relationship(i: Any, graph: Any = None) -> s.Relationship:
    """An uncalibrated relationship has a sign but no size: its effect and timing are null, never 0. With the graph,
    it carries its retrieval profile (model/construction.transition_profile)."""
    from axelrod_wm.model.construction import transition_profile

    k = i.forward.kernel
    sized = i.quantified
    return s.Relationship(
        id=i.id, source_attribute_id=i.source_id, target_attribute_id=i.target_id,
        source_entity_id=owner_of(i.source_id), target_entity_id=owner_of(i.target_id), type=str(i.edge_type),
        label=i.label, direction=str(i.direction), sign="positive" if i.polarity() > 0 else "negative",
        confidence=round(float(i.existence.mean()), 6),
        effect=round(float(i.forward.effect.mean()), 6) if sized else None, calibration=str(i.calibration),
        kernel=s.Kernel(delay_days=round(float(k.delay.mean()), 3) if sized else None,
                        lag_days=round(float(k.lag.mean()), 3) if sized else None,
                        duration_days=None if k.duration is None or not sized else round(float(k.duration.mean()), 3)),
        transition=i.transition.model_dump(mode="json") if i.transition is not None else None,
        profile=transition_profile(graph, i) if graph is not None and i.transition is not None else None,
        identity_id=i.identity,
        state_dependent=i.state is not None, origin=str(i.origin), epistemic_type=EPISTEMIC_OF_ORIGIN[str(i.origin)],
        status="retired" if i.retired_at is not None else "active", valid_from=i.created_at, valid_to=i.retired_at,
        evidence_count=len(i.evidence) + i.evidence_dropped)


def evidence(e: Any, relationship_id: str) -> s.Evidence:
    src = str(e.source_type)
    return s.Evidence(id=e.id, relationship_id=relationship_id, evidence_type=EVIDENCE_TYPE[src],
                      epistemic_type=EPISTEMIC_OF_SOURCE[src], source_ref=e.source_ref, excerpt=e.excerpt,
                      observed_at=e.observed_at, strength=max(0.0, min(1.0, float(e.strength))),
                      event_id=e.market_event_id)


# -- construction -------------------------------------------------------------------------------------------------------
def composition(graph: Any, c: Any) -> s.Composition:
    from axelrod_wm.model.construction import composition_role

    return s.Composition(id=c.id, entity_id=c.entity_id, view=c.view, basis=c.basis, unit=c.unit, period=c.period,
                         role=composition_role(graph, c.id), additive=c.additive, total_attribute_id=c.total,
                         member_attribute_ids=list(c.members), residual_attribute_id=c.residual,
                         eliminations_attribute_id=c.eliminations, note=c.note)


def path(graph: Any, p: Any) -> s.Path:
    steps = []
    for st in p.steps:
        i = graph.interactions.get(st.interaction_id)
        if i is None:
            continue
        r = relationship(i, graph)
        steps.append(s.PathStep(relationship_id=i.id, branch=st.branch, source_attribute_id=i.source_id,
                                target_attribute_id=i.target_id, type=r.type, calibration=r.calibration,
                                effect=r.effect, sign=r.sign, transition=r.transition))
    return s.Path(id=p.id, entity_id=p.entity_id, name=p.name, trigger=p.trigger, endpoint_attribute_id=p.endpoint,
                  description=p.description, active_when=p.active_when, steps=steps,
                  uncalibrated_steps=sum(1 for x in steps if x.calibration == "uncalibrated"),
                  steps_without_transition=sum(1 for x in steps if x.transition is None))


def construction(graph: Any, entity_id: str) -> dict:
    """The construction view (context/construction.py), with its compositions and paths in the API's shapes."""
    from axelrod_wm.context.construction import construction_view

    view = construction_view(graph, entity_id)
    comps = [composition(graph, c) for c in sorted(graph.compositions.values(), key=lambda c: c.id)
             if c.entity_id == entity_id]
    paths = [path(graph, p) for p in sorted(graph.paths.values(), key=lambda p: p.id) if p.entity_id == entity_id]
    return {"entity_id": view["entity_id"], "name": view["name"], "attributes": view["attributes"],
            "compositions": [c.model_dump(mode="json") for c in comps], "identities": view["identities"],
            "stock_flows": view["stock_flows"], "matrices": view["matrices"],
            "paths": [p.model_dump(mode="json") for p in paths], "links": view["links"], "problems": view["problems"]}


def trace(graph: Any, start: str, entity_id: str, through_totals: bool = False, max_depth: int = 8) -> dict:
    from axelrod_wm.context.construction import trace as walk

    t = walk(graph, start, entity_id, max_depth=max_depth, through_totals=through_totals)
    routes = [{"steps": [{"relationship_id": x["interaction_id"], "source_attribute_id": x["source"],
                          "target_attribute_id": x["target"], "type": x["edge_type"], "calibration": x["calibration"],
                          "has_transition": x["has_transition"]} for x in r["steps"]],
               "ends_at": r["ends_at"], "reaches_endpoint": r["reaches_endpoint"],
               "uncalibrated_steps": r["uncalibrated_steps"], "steps_without_transition": r["steps_without_transition"]}
              for r in t["routes"]]
    return {"from_attribute_id": t["start"], "entity_id": t["entity_id"], "through_totals": t["through_totals"],
            "routes": routes,
            "reaches_endpoint": t["reaches_endpoint"], "stops": t["stops"]}


# -- taxonomy and groups -------------------------------------------------------------------------------------------------
def concept(tax: Any, nid: str) -> s.Concept:
    n = tax.nodes[nid]
    return s.Concept(id=nid, name=n.name, parent_id=None if n.parent_id == tax.root_id else n.parent_id,
                     entity_ids=sorted(n.instance_ids))


def group(ltm: Any, inst: Any) -> s.Group:
    pattern = ltm.object_generalizations.patterns.get(inst.pattern_id)
    return s.Group(id=inst.id, pattern_id=inst.pattern_id, name=pattern.name if pattern is not None else inst.pattern_id,
                   bindings=dict(sorted(inst.bindings.items())), relationship_ids=list(inst.interaction_ids),
                   absent_relationship_ids=list(inst.absent_interaction_ids),
                   child_group_ids=list(inst.child_instance_ids), activation=max(0.0, min(1.0, float(inst.activation))))


# -- events and changes ----------------------------------------------------------------------------------------------------
def event(me: Any, change_ids: list[str]) -> s.Event:
    return s.Event(id=me.id, type=EVENT_TYPE[str(me.kind)], channel=str(me.channel), source=me.source,
                   headline=me.headline, body=me.body, published_at=me.published_at, occurred_at=me.occurred_at,
                   url=me.url, data=dict(me.data), mentions=list(me.mentions), tags=list(me.tags),
                   synthetic=bool(me.synthetic), change_ids=change_ids)


def change(p: Any, org: str, proposed_by: dict | None, decided_by: dict | None) -> s.Change:
    if decided_by is None and p.decided_by:
        # decided inside the engine (a review policy, a replay): the system, named as the engine recorded it
        decided_by = {"kind": "system", "org": org, "sub": p.decided_by}
    ops = getattr(getattr(p, "event", None), "ops", None) or []
    return s.Change(id=p.id, kind=str(p.kind), status=str(p.status), event_id=p.market_event_id,
                    created_at=p.created_at, operation_count=len(ops), proposed_by=proposed_by, decided_by=decided_by,
                    decided_at=p.decided_at, note=p.note, version_after=p.version_after)


def operation(op: Any) -> dict:
    from axelrod_wm.intake.pipeline import op_summary

    d = op.model_dump(mode="json")
    target = d.get("target") or {}
    return {**{k: v for k, v in d.items() if k != "op"}, "op": d["op"],
            "attribute_id": target.get("subentity_id") if isinstance(target, dict) else None,
            "relationship_id": d.get("interaction_id"), "summary": op_summary(op)}


# -- theses and simulations ----------------------------------------------------------------------------------------------
def thesis(t: Any, simulation_ids: list[str]) -> s.Thesis:
    mode = "template" if t.id.startswith("S-") else str(t.mode)
    return s.Thesis(id=t.id, question=t.question, mode=mode, horizon_days=t.horizon_days,
                    target_attribute_ids=list(t.targets), operation_count=len(t.event.ops), posed_by=t.posed_by,
                    posed_at=t.posed_at, simulation_ids=simulation_ids)


def simulation(graph: Any, fc: Any) -> s.Simulation:
    def name(sid: str) -> str:
        return graph.subentities[sid].name if sid in graph.subentities else sid

    targets = []
    for sid in fc.targets:
        es = fc.effect_summary.get(sid) or []
        last = es[-1] if es else None
        targets.append(s.SimulationTarget(attribute_id=sid, entity_id=owner_of(sid), name=name(sid),
                                          effect_sd=None if last is None else s.Effect(
                                              q05=round(last.q05, 4), q50=round(last.q50, 4), q95=round(last.q95, 4))))
    return s.Simulation(id=fc.id, thesis_id=fc.thesis_id, question=fc.question, status="completed",
                        version=fc.based_on_version, seed=fc.seed, config_hash=fc.config_hash,
                        horizon_days=fc.horizon_days, created_at=fc.created_at, targets=targets,
                        scenario_table=fc.scenario_table, unquantified_relationships=list(fc.unquantified))


def transmission(graph: Any, fc: Any) -> list[s.TransmissionStep]:
    rows = sorted(fc.transmission or [], key=lambda t: (t.order, -abs(t.effect), t.subentity_id))
    return [s.TransmissionStep(attribute_id=t.subentity_id, entity_id=owner_of(t.subentity_id),
                               name=graph.subentities[t.subentity_id].name if t.subentity_id in graph.subentities
                               else t.subentity_id, order=t.order, peak_sd=round(t.peak, 4), peak_day=t.peak_day,
                               arrives_day=t.arrives_day, effect_sd=round(t.effect, 4), material=t.material,
                               relationship_ids=[h.interaction_id.split(":", 1)[0] for h in t.path]) for t in rows]
