"""View models for the API (§12.2). The front end renders these and never computes model results."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import DistSummary, from_link
from axelrod_wm.core.hypothesis import Hypothesis
from axelrod_wm.events.graph_update import SPECIFICITY_NAMES

if TYPE_CHECKING:
    from axelrod_wm.control.controller import WorldModelController
    from axelrod_wm.memory.long_term import LongTermMemory
    from axelrod_wm.memory.working import WorkingMemory


class _V(BaseModel):
    model_config = ConfigDict(extra="allow")


class Deviation(_V):
    z: float
    direction: str


class EntityNode(_V):
    id: str
    name: str
    kind: str
    category_tags: list[str]
    instance_ids: list[str]
    loose: bool
    origin: str
    generalization_id: str | None
    deviation: Deviation
    aliases: list[str] = []
    features: dict[str, str] = {}
    subentity_ids: list[str] = []
    demo_addition: bool = False


class SubentityNode(_V):
    id: str
    entity_id: str
    name: str
    family: str
    unit: str
    z: float
    origin: str
    summary: DistSummary
    attribute_kind: str = ""
    decision_variable: bool = False


class LinkView(_V):
    id: str
    source: str
    target: str
    label: str
    direction: str
    edge_type: str
    polarity: int
    significance: float
    existence: float
    confidence: float
    internal: bool
    origin: str
    tags: list[str]
    generalization_id: str | None = None
    reverse_effect: float | None = None
    effect: float = 0.0


class EntityLinkView(_V):
    source: str
    target: str
    label: str
    interaction_ids: list[str]
    significance: float


class HullView(_V):
    id: str
    pattern_id: str
    label: str
    members: list[str]
    status: str
    transient: bool
    palette: str | None
    child_instance_ids: list[str] = []
    rival_ids: list[str] = []
    support: float = 0.0
    activation: float = 0.0
    interaction_ids: list[str] = []
    origin: str = ""


class SuperLinkView(_V):
    id: str
    source: str
    target: str
    kind: str
    label: str
    interaction_ids: list[str]
    shared_entity_ids: list[str] = []
    significance: float = 0.0


class FrontierLineView(_V):
    id: str
    earlier: str
    later: str
    support: float
    lag_steps: int
    sign: int
    status: str
    consistent: int = 0
    inconsistent: int = 0
    corr: float = 0.0
    hypothesis_id: str | None = None
    ambiguous_direction: bool = False
    seeded: bool = False


class FuzzyEnd(_V):
    level: str
    ref: str | None
    candidates: list[list[Any]] = []


class FuzzyView(_V):
    pending_id: str
    op: str
    label: str | None
    relation: str | None
    source: FuzzyEnd | None = None
    target: FuzzyEnd | None = None
    subject: FuzzyEnd | None = None
    status: str = "pending"
    proposal_id: str | None = None
    kind: str = "real"


class GraphView(_V):
    version: int
    sim_time: datetime
    entities: list[EntityNode]
    subentities: list[SubentityNode]
    links: list[LinkView]
    entity_links: list[EntityLinkView]
    hulls: list[HullView]
    super_links: list[SuperLinkView]
    frontier: list[FrontierLineView]
    fuzzy: list[FuzzyView]
    proposals_pending: int
    palettes: dict[str, dict[str, str]] = {}
    read_only: bool = False


def _z(wm: WorkingMemory, sid: str) -> float:
    dev = wm.deviations
    z = dev.z_at(sid, dev.step_of(wm.clock))
    return float(z) if z is not None else 0.0


def _pattern_label(p: Any) -> str:
    return f"{p.id} · {p.name}"


def _end_view(t: Any, info: dict | None = None) -> FuzzyEnd:
    if getattr(t, "kind", "") == "concrete":
        return FuzzyEnd(level="subentity", ref=t.subentity_id, candidates=[])
    level = "entity" if t.entity_id else "generalization"
    ref = t.entity_id or t.generalization_id
    cands = [[c, round(s, 4)] for c, s in (info or {}).items()]
    return FuzzyEnd(level=level, ref=ref, candidates=sorted(cands, key=lambda x: -x[1])[:6])


def fuzzy_from_pending(pend: Any, status: str = "pending", proposal_id: str | None = None) -> FuzzyView:
    op = pend.op
    ends: dict[str, FuzzyEnd] = {}
    for name in ("source", "target"):
        if hasattr(op, name) and op.op == "add_interaction":
            ends[name] = _end_view(getattr(op, name), pend.candidates if pend.end == name else None)
    if op.op in ("change_value", "observe_value"):
        ends["subject"] = _end_view(op.target, pend.candidates)
    if pend.end in ends and pend.reached is not None:
        ends[pend.end].level = SPECIFICITY_NAMES[int(pend.reached)]
        if pend.node_id:
            ends[pend.end].ref = pend.node_id
    return FuzzyView(pending_id=pend.id, op=op.op, label=getattr(op, "label", None) or pend.label,
                     relation=pend.relation_node_id or getattr(op, "interaction_generalization_id", None),
                     status=status, proposal_id=proposal_id, **ends)


def build_graph_view(wm: WorkingMemory, ltm: LongTermMemory, controller: WorldModelController | None,
                     version: int) -> GraphView:
    g = wm.graph
    instance_members = {iid: g.members(iid) for iid in g.instances}
    entities = []
    for eid, e in sorted(g.entities.items()):
        insts = sorted(i for i, m in instance_members.items() if eid in m and not g.instances[i].transient)
        zs = [(abs(_z(wm, s)), _z(wm, s)) for s in e.subentity_ids if s in g.subentities]
        zmax = max(zs)[1] if zs else 0.0
        entities.append(EntityNode(id=eid, name=e.name, kind=str(e.kind), category_tags=sorted(str(t) for t in e.category_tags),
                                   instance_ids=insts, loose=not insts, origin=str(e.origin),
                                   generalization_id=e.generalization_id,
                                   deviation=Deviation(z=round(zmax, 4), direction="up" if zmax > 0.25 else (
                                       "down" if zmax < -0.25 else "flat")),
                                   aliases=list(e.aliases), features=dict(e.features), subentity_ids=list(e.subentity_ids),
                                   demo_addition=eid in ("federal_reserve", "ecb", "northwind_semis", "fed_chair")))
    subs = []
    for sid, s in sorted(g.subentities.items()):
        subs.append(SubentityNode(id=sid, entity_id=s.entity_id, name=s.name, family=s.posterior.family, unit=s.unit,
                                  z=round(_z(wm, sid), 4), origin=str(s.origin), summary=s.posterior.summary(),
                                  attribute_kind=s.attribute_kind, decision_variable=sid in wm.decision_variables))
    links = []
    for inter in g.active_interactions():
        links.append(LinkView(id=inter.id, source=inter.source_id, target=inter.target_id, label=inter.label,
                              direction=str(inter.direction), edge_type=str(inter.edge_type), polarity=inter.polarity(),
                              significance=round(inter.significance_mean(), 4),
                              existence=round(inter.existence.mean(), 4), confidence=round(inter.confidence(), 4),
                              internal=inter.internal, origin=str(inter.origin), tags=list(inter.tags),
                              generalization_id=inter.generalization_id,
                              reverse_effect=inter.reverse.effect.mean() if inter.reverse is not None else None,
                              effect=round(inter.forward.effect.mean(), 4)))
    ent_links = [EntityLinkView(source=el.source_entity_id, target=el.target_entity_id, label=el.label,
                                interaction_ids=el.interaction_ids, significance=round(el.significance, 4))
                 for el in g.entity_links()]
    hulls = []
    for iid, inst in sorted(g.instances.items()):
        p = ltm.patterns.patterns.get(inst.pattern_id)
        if p is None:
            continue
        hulls.append(HullView(id=iid, pattern_id=p.id, label=_pattern_label(p), members=sorted(instance_members[iid]),
                              status=str(p.status), transient=inst.transient, palette=p.palette,
                              child_instance_ids=list(inst.child_instance_ids), rival_ids=sorted(p.rival_ids),
                              support=round(p.support, 3), activation=round(inst.activation, 3),
                              interaction_ids=list(inst.interaction_ids), origin=str(p.origin)))
    sups = [SuperLinkView(id=s.id, source=s.source_instance_id, target=s.target_instance_id, kind=str(s.kind),
                          label=s.label, interaction_ids=list(s.underlying_interaction_ids),
                          shared_entity_ids=list(s.shared_entity_ids), significance=round(s.significance, 4))
            for _, s in sorted(g.super_interactions.items())]
    frontier = [FrontierLineView(id=co.id, earlier=co.earlier_id, later=co.later_id, support=round(co.support, 3),
                                 lag_steps=co.lag_steps, sign=co.sign, status=str(co.status), consistent=co.consistent,
                                 inconsistent=co.inconsistent, corr=round(co.corr.corr(), 3),
                                 hypothesis_id=co.hypothesis_id, ambiguous_direction=co.ambiguous_direction,
                                 seeded=co.seeded)
                for _, co in sorted(ltm.frontier.entries.items()) if str(co.status) != "decayed"]
    fuzzy = [fuzzy_from_pending(p) for _, p in sorted(wm.pending_refinements.items())]
    pending = 0
    if controller is not None:
        for p in controller.proposals.values():
            if str(p.status) == "pending":
                pending += 1
                for k, pend in enumerate(p.pending):
                    fuzzy.append(fuzzy_from_pending(pend, status="proposed", proposal_id=p.id))
    return GraphView(version=version, sim_time=wm.clock, entities=entities, subentities=subs, links=links,
                     entity_links=ent_links, hulls=hulls, super_links=sups, frontier=frontier, fuzzy=fuzzy,
                     proposals_pending=pending, palettes=dict(ltm.patterns.palettes),
                     read_only=controller is not None and version != controller.engine.version)


# ---------------------------------------------------------------------------------------------
# Detail views
# ---------------------------------------------------------------------------------------------

def native_summary_points(sub: Any, wm: WorkingMemory, n: int = 60) -> list[dict]:
    pts = []
    for ts in sub.history[-n:]:
        if "mean" in ts.values:
            pts.append({"t": ts.at.valid_at.isoformat(), "mean": ts.values["mean"], "sd": ts.values.get("sd", 0.0),
                        "z": ts.values.get("z"), "event": ts.source_event_id})
    return pts


def entity_view(eid: str, wm: WorkingMemory, ltm: LongTermMemory) -> dict:
    g = wm.graph
    e = g.entities[eid]
    subs = []
    for sid in e.subentity_ids:
        s = g.subentities.get(sid)
        if s is None:
            continue
        subs.append({"id": sid, "name": s.name, "unit": s.unit, "family": s.posterior.family,
                     "attribute_kind": s.attribute_kind, "summary": s.posterior.summary().model_dump(),
                     "prior": s.prior.summary().model_dump(), "z": _z(wm, sid), "scale": s.scale,
                     "level_noise": s.level_noise, "prior_source_id": s.prior_source_id, "origin": str(s.origin),
                     "aliases": s.aliases, "features": s.features, "decision_variable": sid in wm.decision_variables,
                     "history": native_summary_points(s, wm)})
    path = ltm.object_taxonomy.path_from_root(e.generalization_id) if e.generalization_id in ltm.object_taxonomy.nodes else []
    mem = ltm.entity_memories.get(eid)
    memory = None
    if mem is not None:
        memory = {"entries": len(mem.entries), "decisions": [d.model_dump(mode="json") for d in mem.decisions[-20:]],
                  "profiles": {k: v.by_context for k, v in mem.profiles.items()}}
    return {"entity": e.model_dump(mode="json"), "subentities": subs,
            "generalization_path": [{"id": gid, "name": ltm.object_taxonomy.nodes[gid].name} for gid in path],
            "instance_ids": g.instances_of_entity(eid), "entity_memory": memory,
            "in_links": [i.id for i in g.active_interactions() if g.subentities.get(i.target_id) is not None
                         and g.subentities[i.target_id].entity_id == eid and not i.internal],
            "out_links": [i.id for i in g.active_interactions() if g.subentities.get(i.source_id) is not None
                          and g.subentities[i.source_id].entity_id == eid and not i.internal]}


def interaction_view(iid: str, wm: WorkingMemory, ltm: LongTermMemory) -> dict:
    """The Figure 2 record."""
    i = wm.graph.interactions[iid]
    k = i.forward.kernel
    weight_points = [{"t": ts.at.valid_at.isoformat(), "significance": ts.values.get("significance"),
                      "effect_mean": ts.values.get("effect_mean"), "effect_sd": ts.values.get("effect_sd"),
                      "existence_mean": ts.values.get("existence_mean")}
                     for ts in i.time_states if "significance" in ts.values][-80:]
    sig = i.significance()
    path = ltm.interaction_taxonomy.path_from_root(i.generalization_id) if i.generalization_id in ltm.interaction_taxonomy.nodes else []
    return {"id": i.id, "label": i.label, "direction": str(i.direction), "origin": str(i.origin),
            "edge_type": str(i.edge_type), "source": i.source_id, "target": i.target_id, "internal": i.internal,
            "weight": {"now": sig.model_dump(), "history": weight_points},
            "time_states": [ts.model_dump(mode="json") for ts in i.time_states[-30:]],
            "parameters": [p.model_dump(mode="json") for p in i.parameters],
            "delay": k.delay.summary().model_dump(), "lag": k.lag.summary().model_dump(),
            "duration": k.duration.summary().model_dump() if k.duration is not None else None,
            "kernel_means": k.shorthand(), "existence": i.existence.summary().model_dump(),
            "existence_params": {"alpha": i.existence.alpha, "beta": i.existence.beta},
            "effect": i.forward.effect.summary().model_dump(),
            "reverse_effect": i.reverse.effect.summary().model_dump() if i.reverse is not None else None,
            "confidence": i.confidence(), "evidence": [e.model_dump(mode="json") for e in i.evidence[-20:]],
            "evidence_count": len(i.evidence) + i.evidence_dropped,
            "generalization_path": [{"id": gid, "name": ltm.interaction_taxonomy.nodes[gid].name} for gid in path],
            "prior_source_id": i.prior_source_id, "tags": i.tags, "created_at": i.created_at.isoformat()}


def pattern_view(pid: str, wm: WorkingMemory, ltm: LongTermMemory) -> dict:
    p = ltm.patterns.patterns[pid]
    g = wm.graph
    insts = [inst for inst in g.instances.values() if inst.pattern_id == pid]
    inst_ids = {i.id for i in insts}
    sups = [s.model_dump(mode="json") for s in g.super_interactions.values()
            if s.source_instance_id in inst_ids or s.target_instance_id in inst_ids]
    return {"pattern": p.model_dump(mode="json"),
            "support_history": [{"t": ts.at.valid_at.isoformat(), "support": ts.values.get("support")} for ts in p.history],
            "instances": [i.model_dump(mode="json") for i in insts], "super_interactions": sups,
            "generalization_path": ltm.object_taxonomy.path_from_root(p.generalization_id)
            if p.generalization_id in ltm.object_taxonomy.nodes else []}


def taxonomy_view(kind: str, ltm: LongTermMemory) -> dict:
    tax = ltm.object_taxonomy if kind == "object" else ltm.interaction_taxonomy
    return {"kind": kind, "root_id": tax.root_id,
            "nodes": [{"id": n.id, "name": n.name, "parent": n.parent_id, "children": list(n.child_ids),
                       "support": round(n.stats.support, 3), "instance_ids": list(n.instance_ids),
                       "signature": n.signature.model_dump(), "origin": str(n.origin)}
                      for _, n in sorted(tax.nodes.items())]}


def memory_summary(wm: WorkingMemory, ltm: LongTermMemory) -> dict:
    eps = sorted(ltm.episodes.episodes.values(), key=lambda e: (e.end, e.id))
    return {"episodes": len(eps), "patterns": len(ltm.patterns.patterns),
            "generalizations": len(ltm.object_taxonomy.nodes) + len(ltm.interaction_taxonomy.nodes),
            "frontier_entries": len(ltm.frontier.entries), "explanations": len(ltm.explanations.explanations),
            "entity_memories": len(ltm.entity_memories),
            "recent_episodes": [{"id": e.id, "start": e.start.isoformat(), "end": e.end.isoformat(), "tags": e.tags,
                                 "event_types": e.event_types, "signature": sorted(e.signature)[:20],
                                 "active_patterns": e.active_pattern_ids, "deltas": len(e.deltas)}
                                for e in eps[-25:][::-1]],
            "explanations_recent": [{"id": x.id, "subject": x.subject_id, "kind": x.subject_kind, "text": x.text}
                                    for x in list(ltm.explanations.explanations.values())[-15:][::-1]],
            "entity_memory_ids": sorted(ltm.entity_memories)}


def hypothesis_view(h: Hypothesis, now: datetime) -> dict:
    pts = []
    for k in range(0, 9):
        t = now + timedelta(days=7 * k)
        pts.append({"t": t.isoformat(), "value": h.current_value(t)})
    return {"hypothesis": h.model_dump(mode="json"), "current_value": h.current_value(now), "decay_points": pts}


def proposal_view(p: Any, wm: WorkingMemory, ltm: LongTermMemory) -> dict:
    from axelrod_wm.ingest.pipeline import op_ends_view, op_summary

    ops = []
    preview: list[dict] = []
    g = wm.graph
    for idx, op in enumerate(p.event.ops):
        ops.append({"index": idx, "op": op.op, "summary": op_summary(op), "ends": op_ends_view(op)})
        if op.op == "observe_value" and getattr(op.target, "kind", "") == "concrete":
            s = g.subentities.get(op.target.subentity_id)
            if s is not None:
                preview.append({"kind": "change", "ref": s.id, "before": s.posterior.summary().q50, "after": op.value,
                                "unit": s.unit})
        elif op.op == "change_value" and getattr(op.target, "kind", "") == "concrete":
            s = g.subentities.get(op.target.subentity_id)
            if s is not None:
                from axelrod_wm.engine.parse import change_size

                size, _ = change_size(s, op.mode, op.delta)
                x = float(from_link(s.posterior.link_moments()[0] + size * s.scale, s.posterior.link))
                preview.append({"kind": "change", "ref": s.id, "before": s.posterior.summary().q50, "after": x,
                                "unit": s.unit})
        elif op.op in ("add_entity", "add_subentity"):
            preview.append({"kind": "create", "ref": op.temp_id, "name": op.name})
        elif op.op == "add_interaction":
            preview.append({"kind": "create", "ref": f"{getattr(op.source, 'subentity_id', '?')} -> "
                                                     f"{getattr(op.target, 'subentity_id', '?')}", "name": op.label})
        elif op.op == "reweight_interaction":
            i = g.interactions.get(op.interaction_id)
            if i is not None:
                a, b = i.existence.alpha, i.existence.beta
                after = (a + op.strength) / (a + b + op.strength) if op.supports else a / (a + b + op.strength)
                preview.append({"kind": "change", "ref": i.id, "before": i.existence.mean(), "after": after,
                                "unit": "existence"})
        elif op.op == "propose_superentity":
            preview.append({"kind": "create", "ref": op.pattern.id, "name": op.pattern.name,
                            "members": sorted(set(op.bindings.values()))})
        elif op.op == "dissolve_superentity":
            preview.append({"kind": "remove", "ref": op.pattern_id, "name": op.reason})
    breadcrumb = []
    for st in p.refinement_steps:
        name = st.node_id
        if st.node_id in ltm.object_taxonomy.nodes:
            name = ltm.object_taxonomy.nodes[st.node_id].name
        elif st.node_id in ltm.interaction_taxonomy.nodes:
            name = ltm.interaction_taxonomy.nodes[st.node_id].name
        elif st.node_id in g.entities:
            name = g.entities[st.node_id].name
        breadcrumb.append({"op_index": st.op_index, "end": st.end, "name": name, "node_id": st.node_id,
                           "to_level": SPECIFICITY_NAMES[int(st.to_level)], "created": st.created, "reason": st.reason})
    return {"proposal": p.model_dump(mode="json"), "ops": ops, "refinement_steps": breadcrumb,
            "review_reasons": p.review_reasons, "preview": preview,
            "fuzzy": [fuzzy_from_pending(x, status="proposed", proposal_id=p.id).model_dump() for x in p.pending]}


def forecast_view(fc: Any, explanation: Any, wm: WorkingMemory) -> dict:
    g = wm.graph
    dates = [(fc.created_at + timedelta(days=fc.step_days * k)).date().isoformat() for k in range(fc.horizon_steps + 1)]
    targets = []
    for sid in fc.targets:
        s = g.subentities.get(sid)
        targets.append({"id": sid, "name": s.name if s else sid, "unit": s.unit if s else "",
                        "levels": [x.model_dump() for x in fc.summary.get(sid, [])],
                        "effects": [x.model_dump() for x in fc.effect_summary.get(sid, [])],
                        "z_levels": [x.model_dump() for x in fc.z_summary.get(sid, [])],
                        "decomposition": fc.decomposition.get(sid, {})})
    return {"forecast": fc.model_dump(mode="json", exclude={"summary", "effect_summary", "z_summary"}),
            "dates": dates, "targets": targets,
            "scenarios": [{"id": s.id, "name": s.name, "weight": s.weight, "network_ids": s.network_ids,
                           "forced_existence": s.forced_existence, "branched": s.branched_hypothesis_ids,
                           "effects_at_horizon": {k: v[-1].q50 for k, v in s.effect_summary.items()},
                           "levels": {k: [x.model_dump() for x in v] for k, v in s.summary.items()}}
                          for s in fc.scenarios],
            "networks": [n.model_dump(mode="json") for n in fc.networks],
            "isolated": {nid: {t: d.model_dump() for t, d in v.items()} for nid, v in fc.isolated.items()},
            "explanation": explanation.model_dump(mode="json") if explanation is not None else None}

