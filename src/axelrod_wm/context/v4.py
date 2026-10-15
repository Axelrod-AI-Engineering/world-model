"""The world model as context for a client's agents, in the client's own world-model format (v4.1.4) (Oct 15).

A client's agents (a decision engine, a disruption-propagation agent, an execution and monetization agent) load a
"world model" before they reason: a shared core contract and relationship schema, a registry of domain packs, the
domain pack for the task, and a dated baseline. Their packs name companies, clusters, and qualitative edges (direction
and a high/medium/low confidence); they carry no effect sizes, lags, or forecasts. This module exports Axelrod's world
model as that context, so the agents read our model in the shape they already expect:

- **a domain pack** (the 03x layout): companies, clusters and memberships, metric families, company edge relationships
  with our numbers (effect in standard units per standard unit, existence probability, timing), transmission paths,
  cross-validation assertions, and caveats;
- **a current baseline** (the _19 layer): every value's level and spread as of the committed version, with its evidence
  count and the open questions (the hypothesis frontier);
- **a forecast record** for a thesis: targets with their ranges, the transmission by order and path, the key
  interactions, and the scenario table. It is decision context, kept outside the pack, as the client's contract asks.

The client's own core files (000, 010, 020) are referenced by name in the manifest, never copied. Following the
client's boundary, the context grounds an agent's judgment and never concludes it: no ratings, no sizing.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

SCHEMA = "v4.1.4"
PACK_NO = "036"
BOUNDARY = ("The world model states drivers, exposures, transmission, timing, and how sure it is. It does not conclude "
            "buy, sell, overweight, underweight, sizing, or whether a stock is cheap: those are the agent's judgment.")
TICKER = re.compile(r"^(?:\d{3,6} [A-Z]{2}|[A-Z]{1,5}|[A-Z0-9]{2,5} [A-Z]{2})$")


def _ticker(e: Any) -> str | None:
    return next((a for a in e.aliases if TICKER.match(a)), None)


def _node_id(e: Any) -> str:
    t = _ticker(e)
    return f"N_{re.sub(r'[^A-Z0-9]', '_', t.upper())}" if t else f"N_{e.id.upper()}"


def _confidence(p: float) -> str:
    return "high" if p >= 0.75 else "medium" if p >= 0.5 else "low"


def _horizon(k: Any) -> str:
    """A kernel in words: when the effect starts, how long it builds, how long it lasts."""
    def days(d: Any) -> float | None:
        try:
            return float(d.mean())
        except Exception:
            return None
    delay, lag, dur = days(k.delay), days(k.lag), days(k.duration) if k.duration is not None else None
    parts = [f"starts after ~{delay:.0f}d" if delay is not None else None,
             f"builds over ~{lag:.0f}d" if lag is not None else None,
             f"fades over ~{dur:.0f}d" if dur is not None else "persists"]
    return ", ".join(p for p in parts if p)


def _value(s: Any) -> dict:
    d = s.posterior
    try:
        mean, sd = float(d.mean()), float(d.sd())
    except Exception:
        mean, sd = None, None
    return {"mean": None if mean is None else round(mean, 4), "sd": None if sd is None else round(sd, 4)}


TOP_QUESTIONS = 15


def _cause_first(chain: list[Any]) -> list[Any]:
    """Interactions ordered so that every cause comes before what it moves (ties by id; a cycle is cut by id)."""
    left, out = sorted(chain, key=lambda i: i.id), []
    while left:
        targets = {i.target_id for i in left}
        ready = [i for i in left if i.source_id not in targets] or left[:1]
        out += ready
        left = [i for i in left if i not in ready]
    return out


def domain_pack(wm: Any, ltm: Any, *, scenario_id: str, title: str, book: list[str]) -> dict:
    g = wm.graph
    entities = g.entities
    node = {eid: _node_id(e) for eid, e in entities.items()}
    patterns = getattr(ltm.object_generalizations, "patterns", {})
    live = {pid: p for pid, p in patterns.items() if str(p.status).endswith("admitted")}
    top = [p for p in live.values() if not any(p.id in q.sub_pattern_ids for q in live.values())]

    companies = []
    for eid, e in entities.items():
        if e.kind != "company":
            continue
        packs = [f"PACK_{p.id}" for p in top if any(inst.pattern_id == p.id and eid in inst.bindings.values()
                                                   for inst in g.instances.values())]
        companies.append({"company_id": node[eid], "company_name": e.name, "ticker": _ticker(e),
                          "role_tags": [e.features.get("sector", e.kind), *(["in_book"] if eid in book else [])],
                          "primary_sector_pack_id": packs[0] if packs else None, "axelrod_entity_id": eid,
                          "description": e.description})
    clusters, memberships = [], []
    for inst in g.instances.values():
        p = live.get(inst.pattern_id)
        if p is None:
            continue
        clusters.append({"cluster_id": f"CL_{p.id}", "cluster_name": p.name, "description": p.description,
                         "parent_cluster_ids": [f"CL_{q.id}" for q in live.values() if p.id in q.sub_pattern_ids],
                         "support": p.support, "track_record": {"hits": p.track_record.hits, "misses": p.track_record.misses}})
        for role, eid in sorted(inst.bindings.items()):
            if eid in entities:
                memberships.append({"membership_id": f"CLMEM_{p.id}_{node[eid][2:]}", "cluster_id": f"CL_{p.id}",
                                    "node_id": node[eid], "membership_role": role})
    sector_packs = [{"sector_pack_id": f"PACK_{p.id}", "name": p.name, "description": p.description,
                     "cluster_ids": [f"CL_{c}" for c in p.sub_pattern_ids] or [f"CL_{p.id}"]} for p in top]

    families: dict[str, list[str]] = {}
    for sid, s in g.subentities.items():
        families.setdefault(s.attribute_kind, []).append(sid)
    metric_families = [{"metric_family_id": f"MF_{k.upper()}", "attribute_kind": k, "metrics": sorted(v),
                        "required_baselines": sorted({g.subentities[m].unit for m in v})} for k, v in sorted(families.items())]

    edges = []
    for iid, i in g.interactions.items():
        if i.retired_at is not None:
            continue
        src, tgt = g.subentities.get(i.source_id), g.subentities.get(i.target_id)
        if src is None or tgt is None:
            continue
        eff = float(i.forward.effect.mean())
        p = float(i.existence.mean())
        edges.append({
            "relationship_id": f"REL_{node[src.entity_id][2:]}__{iid.upper()}",
            "company_id": node[src.entity_id], "edge_id": iid.upper(),
            "direction": "positive" if eff > 0 else "negative" if eff < 0 else "neutral",
            "confidence_prior": _confidence(p), "affected_metrics": [i.target_id],
            "affected_node_id": node[tgt.entity_id], "source_metric": i.source_id,
            "mechanism_label": i.label, "time_horizon": _horizon(i.forward.kernel),
            "ontology_relationship_type_hint": (i.generalization_id or "").replace("gen:int:", "") or None,
            # what our model adds to the client's schema: magnitudes, existence, timing, and evidence
            "axelrod": {"effect_sd_per_sd": round(eff, 4), "existence_p": round(p, 4),
                        "delay_days": round(float(i.forward.kernel.delay.mean()), 1),
                        "lag_days": round(float(i.forward.kernel.lag.mean()), 1),
                        "duration_days": None if i.forward.kernel.duration is None else round(float(i.forward.kernel.duration.mean()), 1),
                        "evidence_count": len(i.evidence), "origin": str(i.origin)}})

    # cross-validation: two names moved by the same driver should move together (or apart, if the signs differ)
    by_source: dict[str, list[Any]] = {}
    for i in g.interactions.values():
        if i.retired_at is None and i.source_id in g.subentities and i.target_id in g.subentities:
            by_source.setdefault(i.source_id, []).append(i)
    cross = []
    for src, outs in sorted(by_source.items()):
        firms = [i for i in outs if entities[g.subentities[i.target_id].entity_id].kind == "company"
                 and g.subentities[i.target_id].entity_id != g.subentities[src].entity_id]
        for a_i, b_i in zip(firms, firms[1:]):
            a, b = g.subentities[a_i.target_id], g.subentities[b_i.target_id]
            same = (float(a_i.forward.effect.mean()) > 0) == (float(b_i.forward.effect.mean()) > 0)
            cross.append({"source_company": node[a.entity_id], "target_company": node[b.entity_id],
                          "edge": f"shared driver {src}", "validation_direction": "co-move" if same else "diverge",
                          "mechanism": f"{a_i.label} / {b_i.label}"})

    # transmission paths: each configuration's chain, cause before effect
    paths = []
    for p in live.values():
        if p.sub_pattern_ids:
            continue
        inst = next((x for x in g.instances.values() if x.pattern_id == p.id), None)
        if inst is None:
            continue
        chain = [g.interactions[i] for i in inst.interaction_ids if i in g.interactions]
        chain = _cause_first(chain)
        steps = [f"{g.subentities[i.source_id].name} → {g.subentities[i.target_id].name} ({i.label})" for i in chain
                 if i.source_id in g.subentities and i.target_id in g.subentities]
        if steps:
            names = sorted({node[g.subentities[i.target_id].entity_id] for i in chain if i.target_id in g.subentities
                            and entities[g.subentities[i.target_id].entity_id].kind == "company"})
            paths.append({"path_id": f"PATH_{p.id}", "primary_company_id": names[0] if names else None,
                          "trigger": steps[0], "ordered_steps": steps, "edge_ids": [i.id.upper() for i in chain],
                          "company_ids": names})

    caveats, impacts = [], []
    for s in g.subentities.values():
        c = getattr(s, "constraint", None)
        if c is not None:
            caveats.append({"caveat_id": f"CV_{s.id.upper().replace('.', '_')}", "definition": c.reason or "soft bound",
                            "bounds": {"min": c.min, "max": c.max}, "metric": s.id})
    frontier = sorted((h for h in wm.hypotheses.values() if str(h.status).endswith("open")),
                      key=lambda h: (-(h.informational_value or 0.0), -h.probability))[:TOP_QUESTIONS]
    for h in frontier:
        caveats.append({"caveat_id": f"CV_{h.id}", "definition": h.statement, "probability": round(h.probability, 3)})
        for eid in h.subject_entity_ids:
            if eid in node:
                impacts.append({"caveat_impact_id": f"CAVIMPACT_{h.id}_{node[eid][2:]}", "caveat_id": f"CV_{h.id}",
                                "node_id": node[eid], "severity_prior": round(h.informational_value or 0.0, 4)})

    terms = sorted({a for eid in entities for a in entities[eid].aliases if len(a) > 2})[:60]
    return {
        "schema_version": SCHEMA, "domain_pack_id": f"{PACK_NO}_axelrod_{scenario_id}",
        "domain_pack_name": f"Axelrod world model: {title}", "file_role": "domain_pack",
        "important_boundary": BOUNDARY, "activation_terms": terms,
        "sector_pack_ids": [s["sector_pack_id"] for s in sector_packs],
        "companies": companies, "clusters": clusters, "cluster_memberships": memberships, "sector_packs": sector_packs,
        "metric_families": metric_families, "company_edge_relationships": edges,
        "cross_validation_assertions": cross, "industry_caveat_definitions": caveats,
        "caveat_impact_assertions": impacts, "transmission_paths": paths,
    }


def baseline(wm: Any, *, version: int, state_hash: str | None) -> dict:
    g = wm.graph
    values = []
    for sid, s in sorted(g.subentities.items()):
        ent = g.entities.get(s.entity_id)
        values.append({"metric_id": sid, "node": ent.name if ent else s.entity_id, "name": s.name, "unit": s.unit,
                       **_value(s), "observed": s.observed,
                       "evidence_count": sum(len(i.evidence) for i in g.interactions.values() if i.target_id == sid)})
    questions = [{"id": h.id, "question": h.statement, "probability": round(h.probability, 3),
                  "informational_value": round(h.informational_value or 0.0, 4)}
                 for h in wm.hypotheses.values() if str(h.status).endswith("open")]
    questions.sort(key=lambda q: -q["informational_value"])
    return {"schema_version": SCHEMA, "file_role": "current_baseline", "as_of": wm.clock.isoformat(),
            "state_version": version, "state_hash": state_hash, "values": values, "unresolved_questions": questions[:TOP_QUESTIONS]}


def forecast_record(fc: Any, explanation: Any, wm: Any) -> dict:
    g = wm.graph

    def nm(sid: str) -> str:
        s = g.subentities.get(sid)
        return s.name if s else sid

    targets = []
    for sid in fc.targets:
        eff = fc.effect_summary.get(sid, [])
        last = eff[-1] if eff else None
        targets.append({"metric_id": sid, "name": nm(sid),
                        "effect_at_horizon_sd": None if last is None else {"q05": round(last.q05, 3), "q50": round(last.q50, 3),
                                                                            "q95": round(last.q95, 3)}})
    trans = []
    for t in sorted(fc.transmission or [], key=lambda t: (t.order, -abs(t.effect)))[:40]:
        trans.append({"metric_id": t.subentity_id, "name": nm(t.subentity_id), "order": t.order,
                      "path": [nm(t.path[0].source_id)] + [nm(h.target_id) for h in t.path] if t.path else [nm(t.subentity_id)],
                      "edge_ids": [h.interaction_id.split(":")[0].upper() for h in t.path],
                      "arrives_day": t.arrives_day, "peak_day": t.peak_day, "peak_sd": round(t.peak, 3),
                      "effect_at_horizon_sd": round(t.effect, 3), "material": t.material})
    key = []
    if explanation is not None:
        for iid, contrib in explanation.key_interactions[:10]:
            i = g.interactions.get(iid)
            key.append({"edge_id": iid.upper(), "contribution": round(float(contrib), 4),
                        "mechanism": f"{nm(i.source_id)} {i.label} {nm(i.target_id)}" if i else iid})
    return {"file_role": "decision_context", "forecast_id": fc.id, "thesis_id": fc.thesis_id, "question": fc.question,
            "based_on_version": fc.based_on_version, "seed": fc.seed, "config_hash": fc.config_hash,
            "horizon_days": fc.horizon_days, "targets": targets, "transmission": trans, "key_interactions": key,
            "constraints_binding": fc.constraints_binding, "scenario_table": fc.scenario_table,
            "scenarios": [{"id": s.id, "name": s.name, "weight": round(s.weight, 4)} for s in fc.scenarios]}


# which part of the context each of the client's agent cards reads
FEEDS = [
    {"agent": "Decision Engine", "card": "2 · Regime & thesis status", "reads": ["baseline.values", "domain_pack.clusters"]},
    {"agent": "Decision Engine", "card": "3 · What doesn't confirm", "reads": ["baseline.unresolved_questions",
                                                                               "domain_pack.industry_caveat_definitions"]},
    {"agent": "Decision Engine", "card": "4 · Causal transmission", "reads": ["domain_pack.company_edge_relationships",
                                                                              "domain_pack.transmission_paths",
                                                                              "forecast.transmission"]},
    {"agent": "Decision Engine", "card": "5 · Scenarios & conviction", "reads": ["forecast.scenario_table"]},
    {"agent": "Disruption Propagation", "card": "Cluster transmission", "reads": ["domain_pack.clusters",
                                                                                 "domain_pack.cross_validation_assertions",
                                                                                 "forecast.transmission"]},
    {"agent": "Execution & Monetization", "card": "1-3 year scenarios", "reads": ["forecast.scenario_table"]},
]


def context_pack(wm: Any, ltm: Any, *, scenario_id: str, title: str, book: list[str], version: int,
                 state_hash: str | None, forecast: Any = None, explanation: Any = None) -> dict:
    pack = domain_pack(wm, ltm, scenario_id=scenario_id, title=title, book=book)
    pack_file = f"{PACK_NO}_world_model_domain_pack_axelrod_{scenario_id}_{SCHEMA}.json"
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "generated_by": "Axelrod world model",
        "schema_version": SCHEMA, "boundary": BOUNDARY,
        "load_order": [
            {"file": f"000_core_world_model_common_contract_{SCHEMA}.json", "source": "yours, unchanged"},
            {"file": f"010_core_world_model_relationship_schema_{SCHEMA}", "source": "yours, unchanged"},
            {"file": f"020_world_model_domain_pack_registry_{SCHEMA}.json", "source": "yours, plus the registry row below"},
            {"file": pack_file, "source": "this export: domain_pack"},
            {"file": f"{PACK_NO}_19_current_baseline.json", "source": "this export: baseline"},
            *([{"file": f"{forecast.id}.decision_context.json", "source": "this export: forecast"}] if forecast else []),
        ],
        "registry_row": {"domain_pack_id": pack["domain_pack_id"], "file_name": pack_file,
                         "activation_terms": pack["activation_terms"][:20], "never_merge_into_base": True},
        "feeds": FEEDS,
    }
    out = {"manifest": manifest, "domain_pack": pack, "baseline": baseline(wm, version=version, state_hash=state_hash)}
    if forecast is not None:
        out["forecast"] = forecast_record(forecast, explanation, wm)
    return out
