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
    description: str = ""


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
    observed_today: bool = False      # today's z came from data, not from daily propagation
    observed: bool = True             # False if no source ever reports it
    density: list[list[float]] = []   # a small picture of the posterior: (native value, density / peak)


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
    description: str = ""
    sub_pattern_ids: list[str] = []


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
    lag_days: int
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
    update: dict | None = None        # the active update run: {"id", "state", "current_day"}
    today: str | None = None          # the last processed day


def _z(wm: WorkingMemory, sid: str) -> float:
    return float(wm.deviations.z(sid, wm.last_processed_day))


def _observed_today(wm: WorkingMemory, sid: str) -> bool:
    p = wm.deviations.point(sid, wm.last_processed_day)
    return bool(p is not None and p.observed)


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
                                   # actors added to Figure 1's ideas: agencies, companies, people, sectors
                                   demo_addition=str(e.kind) in ("agency", "company", "person") or "sector" in e.features,
                                   description=e.description))
    subs = []
    for sid, s in sorted(g.subentities.items()):
        subs.append(SubentityNode(id=sid, entity_id=s.entity_id, name=s.name, family=s.posterior.family, unit=s.unit,
                                  z=round(_z(wm, sid), 4), origin=str(s.origin), summary=s.posterior.summary(),
                                  attribute_kind=s.attribute_kind, decision_variable=sid in wm.decision_variables,
                                  observed_today=_observed_today(wm, sid), observed=bool(s.observed),
                                  density=s.posterior.density_points(20)))
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
    patterns = ltm.object_generalizations.patterns
    for iid, inst in sorted(g.instances.items()):
        p = patterns.get(inst.pattern_id)
        if p is None:
            continue
        hulls.append(HullView(id=iid, pattern_id=p.id, label=_pattern_label(p), members=sorted(instance_members[iid]),
                              status=str(p.status), transient=inst.transient, palette=p.palette,
                              child_instance_ids=list(inst.child_instance_ids), rival_ids=sorted(p.rival_ids),
                              support=round(p.support, 3), activation=round(inst.activation, 3),
                              interaction_ids=list(inst.interaction_ids), origin=str(p.origin),
                              description=p.description, sub_pattern_ids=list(p.sub_pattern_ids)))
    sups = [SuperLinkView(id=s.id, source=s.source_instance_id, target=s.target_instance_id, kind=str(s.kind),
                          label=s.label, interaction_ids=list(s.underlying_interaction_ids),
                          shared_entity_ids=list(s.shared_entity_ids), significance=round(s.significance, 4))
            for _, s in sorted(g.super_interactions.items())]
    frontier = [FrontierLineView(id=co.id, earlier=co.earlier_id, later=co.later_id, support=round(co.support, 3),
                                 lag_days=co.lag_days, sign=co.sign, status=str(co.status), consistent=co.consistent,
                                 inconsistent=co.inconsistent, corr=round(co.corr.corr(), 3),
                                 hypothesis_id=co.hypothesis_id, ambiguous_direction=co.ambiguous_direction,
                                 seeded=co.seeded)
                for _, co in sorted(ltm.correlation_frontier.entries.items()) if str(co.status) != "decayed"]
    fuzzy = [fuzzy_from_pending(p) for _, p in sorted(wm.pending_refinements.items())]
    pending = 0
    update = None
    if controller is not None:
        for p in controller.pending_proposals():
            pending += 1
            for k, pend in enumerate(p.pending):
                fuzzy.append(fuzzy_from_pending(pend, status="proposed", proposal_id=p.id))
        if controller.active_update and controller.active_update in controller.updates:
            run = controller.updates[controller.active_update]
            cur = run.current_day if run.current_day is not None else run.first_day
            update = {"id": run.id, "state": str(run.state),
                      "current_day": wm.deviations.date_of(min(cur, run.last_day)).isoformat()}
    today = wm.deviations.date_of(wm.last_processed_day).isoformat() if wm.last_processed_day >= 0 else None
    return GraphView(version=version, sim_time=wm.clock, entities=entities, subentities=subs, links=links,
                     entity_links=ent_links, hulls=hulls, super_links=sups, frontier=frontier, fuzzy=fuzzy,
                     proposals_pending=pending, palettes=dict(ltm.object_generalizations.palettes),
                     read_only=controller is not None and version != controller.engine.version, update=update,
                     today=today)


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


def daily_points(sid: str, wm: WorkingMemory, n: int = 120) -> list[dict]:
    """The last n days of a subentity's daily state, marking observed days."""
    dev = wm.deviations
    last = int(wm.last_processed_day)
    out = []
    for d in range(max(last - n + 1, dev.first_kept_day), last + 1):
        p = dev.point(sid, d)
        if p is not None:
            out.append({"day": d, "date": dev.date_of(d).isoformat(), "z": round(p.z, 5),
                        "sd": round(p.var ** 0.5, 5), "observed": p.observed})
    return out


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
                     "observed_today": _observed_today(wm, sid), "observed": bool(s.observed),
                     "history": native_summary_points(s, wm), "daily": daily_points(sid, wm),
                     "density": s.posterior.density_points(40), "prior_density": s.prior.density_points(40)})
    otax = ltm.object_generalizations.taxonomy
    path = otax.path_from_root(e.generalization_id) if e.generalization_id in otax.nodes else []
    mem = ltm.entity_memories.get(eid)
    memory = None
    if mem is not None:
        memory = {"entries": len(mem.entries), "decisions": [d.model_dump(mode="json") for d in mem.decisions[-20:]],
                  "profiles": {k: v.by_context for k, v in mem.profiles.items()},
                  # the weekly entries as series, for sparklines (§13.6)
                  "series": {sid: [{"t": en.at.isoformat(), "z": en.z.get(sid)} for en in mem.entries]
                             for sid in e.subentity_ids}}
    return {"entity": e.model_dump(mode="json"), "subentities": subs,
            "generalization_path": [{"id": gid, "name": otax.nodes[gid].name} for gid in path],
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
    itax = ltm.interaction_generalizations.taxonomy
    path = itax.path_from_root(i.generalization_id) if i.generalization_id in itax.nodes else []
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
            "generalization_path": [{"id": gid, "name": itax.nodes[gid].name} for gid in path],
            "prior_source_id": i.prior_source_id, "tags": i.tags, "created_at": i.created_at.isoformat()}


def pattern_view(pid: str, wm: WorkingMemory, ltm: LongTermMemory) -> dict:
    p = ltm.object_generalizations.patterns[pid]
    otax = ltm.object_generalizations.taxonomy
    g = wm.graph
    insts = [inst for inst in g.instances.values() if inst.pattern_id == pid]
    inst_ids = {i.id for i in insts}
    sups = [s.model_dump(mode="json") for s in g.super_interactions.values()
            if s.source_instance_id in inst_ids or s.target_instance_id in inst_ids]
    return {"pattern": p.model_dump(mode="json"),
            "support_history": [{"t": ts.at.valid_at.isoformat(), "support": ts.values.get("support")} for ts in p.history],
            "instances": [i.model_dump(mode="json") for i in insts], "super_interactions": sups,
            "track_record": {"hits": p.track_record.hits, "misses": p.track_record.misses,
                             "mean": p.track_record.mean()},
            "generalization_path": otax.path_from_root(p.generalization_id) if p.generalization_id in otax.nodes else []}


def taxonomy_view(kind: str, ltm: LongTermMemory) -> dict:
    tax = ltm.taxonomy(kind)
    return {"kind": kind, "root_id": tax.root_id,
            "nodes": [{"id": n.id, "name": n.name, "parent": n.parent_id, "children": list(n.child_ids),
                       "support": round(n.stats.support, 3), "instance_ids": list(n.instance_ids),
                       "signature": n.signature.model_dump(), "origin": str(n.origin)}
                      for _, n in sorted(tax.nodes.items())]}


def memory_summary(wm: WorkingMemory, ltm: LongTermMemory) -> dict:
    """One block per part of long-term memory, in Figure 1's order, then prior states (§12.2)."""
    og, ig = ltm.object_generalizations, ltm.interaction_generalizations
    prior = ltm.prior_states
    eps = sorted(prior.episodes.values(), key=lambda e: (e.day, e.id))
    non_routine = [e for e in eps if not e.routine]
    by_status: dict[str, int] = {}
    for co in ltm.correlation_frontier.entries.values():
        by_status[str(co.status)] = by_status.get(str(co.status), 0) + 1
    profiles = {}
    for eid, mem in sorted(ltm.entity_memories.items()):
        if mem.profiles:
            profiles[eid] = {k: v.by_context for k, v in mem.profiles.items()}
    return {
        "object_generalizations": {
            "nodes": len(og.taxonomy.nodes),
            "admitted": [{"id": p.id, "name": p.name, "support": round(p.support, 3),
                          "track_record": round(p.track_record.mean(), 3), "generalization_id": p.generalization_id,
                          "sub_pattern_ids": list(p.sub_pattern_ids), "origin": str(p.origin)} for p in og.admitted()],
            "candidates": [{"id": p.id, "name": p.name, "support": round(p.support, 3),
                            "generalization_id": p.generalization_id} for p in og.candidates()]},
        "interaction_generalizations": {"nodes": len(ig.taxonomy.nodes)},
        "entity_memories": {"entities": sorted(e for e, m in ltm.entity_memories.items() if m.entries),
                            "entries": sum(len(m.entries) for m in ltm.entity_memories.values()),
                            "decision_profiles": profiles},
        "correlation_frontier": {"entries": len(ltm.correlation_frontier.entries), "by_status": by_status,
                                 "live": [{"id": co.id, "earlier": co.earlier_id, "later": co.later_id,
                                           "support": round(co.support, 3), "lag_days": co.lag_days,
                                           "status": str(co.status)} for co in ltm.correlation_frontier.live()]},
        "prior_states": {
            "episodes": len(eps), "non_routine_episodes": len(non_routine),
            "explanations": len(prior.explanations),
            "recent_episodes": [{"id": e.id, "day": e.day.isoformat(), "routine": e.routine, "tags": e.tags,
                                 "event_types": e.event_types, "signature": sorted(e.signature)[:20],
                                 "active_patterns": e.active_pattern_ids, "deltas": len(e.deltas),
                                 "responses": len(e.response_effects)}
                                for e in (non_routine or eps)[-25:][::-1]],
            "explanations_recent": [{"id": x.id, "subject": x.subject_id, "kind": x.subject_kind, "text": x.text}
                                    for x in list(prior.explanations.values())[-15:][::-1]]},
        # flat counts kept for the header badges
        "episodes": len(eps), "patterns": len(og.patterns),
        "generalizations": len(og.taxonomy.nodes) + len(ig.taxonomy.nodes),
        "frontier_entries": len(ltm.correlation_frontier.entries), "explanations": len(prior.explanations),
    }


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
        otax, itax = ltm.object_generalizations.taxonomy, ltm.interaction_generalizations.taxonomy
        if st.node_id in otax.nodes:
            name = otax.nodes[st.node_id].name
        elif st.node_id in itax.nodes:
            name = itax.nodes[st.node_id].name
        elif st.node_id in g.entities:
            name = g.entities[st.node_id].name
        breadcrumb.append({"op_index": st.op_index, "end": st.end, "name": name, "node_id": st.node_id,
                           "to_level": SPECIFICITY_NAMES[int(st.to_level)], "created": st.created, "reason": st.reason})
    return {"proposal": p.model_dump(mode="json"), "ops": ops, "refinement_steps": breadcrumb,
            "review_reasons": p.review_reasons, "preview": preview,
            "fuzzy": [fuzzy_from_pending(x, status="proposed", proposal_id=p.id).model_dump() for x in p.pending]}


def forecast_view(fc: Any, explanation: Any, wm: WorkingMemory) -> dict:
    g = wm.graph
    dev = wm.deviations
    if fc.start_day is not None:
        dates = [dev.date_of(fc.start_day + k).isoformat() for k in range(fc.horizon_days + 1)]
    else:
        dates = [(fc.created_at + timedelta(days=k)).date().isoformat() for k in range(fc.horizon_days + 1)]
    targets = []
    for sid in fc.targets:
        s = g.subentities.get(sid)
        e = g.entities.get(s.entity_id) if s else None
        targets.append({"id": sid, "name": s.name if s else sid, "unit": s.unit if s else "",
                        "entity": e.name if e else None,
                        "levels": [x.model_dump() for x in fc.summary.get(sid, [])],
                        "effects": [x.model_dump() for x in fc.effect_summary.get(sid, [])],
                        "z_levels": [x.model_dump() for x in fc.z_summary.get(sid, [])],
                        "decomposition": fc.decomposition.get(sid, {}),
                        "effect_density": fc.effect_density.get(sid, [])})
    groups = []
    for grp in fc.groups:
        groups.append({"id": grp.id, "kind": grp.kind, "ref": grp.ref, "name": grp.name,
                       "members": len(grp.members), "effects": [x.model_dump() for x in grp.effect_summary],
                       "effect_density": grp.effect_density,
                       "top": [{"id": sid, "name": g.subentities[sid].name if sid in g.subentities else sid, "effect": v}
                               for sid, v in grp.top]})
    movers = [{"id": sid, "name": g.subentities[sid].name if sid in g.subentities else sid,
               "entity": g.entities[g.subentities[sid].entity_id].name if sid in g.subentities else None, "effect": v}
              for sid, v in (fc.movers or {}).items()]
    return {"forecast": fc.model_dump(mode="json", exclude={"summary", "effect_summary", "z_summary", "groups",
                                                            "effect_density", "movers"}),
            "movers": movers,
            "dates": dates, "targets": targets, "groups": groups,
            "scenarios": [{"id": s.id, "name": s.name, "weight": s.weight, "network_ids": s.network_ids,
                           "forced_existence": s.forced_existence, "branched": s.branched_hypothesis_ids,
                           "effects_at_horizon": {k: v[-1].q50 for k, v in s.effect_summary.items()},
                           "days": list(s.summary_days),
                           "levels": {k: [x.model_dump() for x in v] for k, v in s.summary.items()}}
                          for s in fc.scenarios],
            "networks": [n.model_dump(mode="json") for n in fc.networks],
            "isolated": {nid: {t: d.model_dump() for t, d in v.items()} for nid, v in fc.isolated.items()},
            "explanation": explanation.model_dump(mode="json") if explanation is not None else None}



def update_run_view(run: Any, controller: WorldModelController) -> dict:
    """The run, its market events by day with channel and status, what it waits on, and its report."""
    dev = controller.engine.wm.deviations
    cur = run.current_day if run.current_day is not None else run.first_day
    days_done = max(0, min(int(controller.engine.wm.last_processed_day), run.last_day) - run.first_day + 1)
    by_day = []
    for d, ids in sorted(run.queue.items()):
        items = []
        for i in ids:
            me = controller.market_events.get(i)
            if me is None:
                continue
            items.append({"id": i, "channel": str(me.channel), "kind": str(me.kind), "headline": me.headline,
                          "published_at": me.published_at.isoformat(), "status": controller.market_status.get(i, ""),
                          "late_from": dev.date_of(run.late_from[i]).isoformat() if i in run.late_from else None,
                          "synthetic": me.synthetic, "proposal_ids": list(run.walk.get(i, []))})
        by_day.append({"day": d, "date": dev.date_of(d).isoformat(), "events": items})
    return {"id": run.id, "requested_by": run.request.requested_by, "until": run.request.until.isoformat(),
            "state": str(run.state), "first_day": dev.date_of(run.first_day).isoformat(),
            "last_day": dev.date_of(run.last_day).isoformat(),
            "current_day": dev.date_of(min(cur, run.last_day)).isoformat() if run.last_day >= run.first_day else None,
            "days_total": max(0, run.last_day - run.first_day + 1), "days_done": days_done,
            "market_events": by_day, "waiting_on": [run.waiting_on] if run.waiting_on else [],
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "report": run.report.model_dump(mode="json") if run.report is not None else None,
            "error": run.error}
