"""The world model as context for a client's agents, in the client's own world-model format (v4.1.4) (Oct 15).

A client's agents load a numbered world model before they reason: 000 (the core contract), 010 (the relationship
schema), 020 (the registry of domain packs), one activated 03x domain pack, and then the run's evidence. Their packs
name companies, clusters, and qualitative edges; they carry no effect sizes, lags, or forecasts, and live state reaches
the agents as evidence, never as part of a pack. This module exports Axelrod's world model in that layout, following the
contract's ID rules, field names, and value styles:

- **a domain pack** (the 03x file): companies, clusters and memberships, sector packs, metric families, required search
  scopes, company edge relationships (each an instance of an edge in the pack's own E## vocabulary), cross-validation
  assertions, caveats and their impacts, transmission paths, financial-model semantic fields, and support objects that
  hold what the client's schema has no place for (the edge vocabulary, macro factors and the links among them, and our
  numbers: effect sizes, existence probabilities, timing, evidence);
- **a registry entry** to append to 020, so the harness can activate the pack by its id and file index;
- **an evidence pack**: every value's level and spread at the committed version, with what has been observed, and the
  open questions (the hypothesis frontier);
- **a forecast evidence pack** for a thesis: targets with their ranges, the transmission by order and path, the key
  interactions, the scenario table, and the forecast's calculation coverage;
- **a source catalogue** (Oct 18, `attach_sources`, when the client's local sources are given): each cited source id's
  document, and `evidence_refs` (document, location, passage) on the relationships and values that cite them.

The client's core files (000, 010, 020) are named in the manifest's load order, never copied. Following the contract's
decision boundary, the context grounds an agent's judgment and never concludes it: no ratings, no sizing, no funding
sources. Raw ids are retrieval keys; every id carries a name beside it so cards can render names.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from axelrod_wm.context.construction import state_text

SCHEMA = "v4.1.4"
PACK_SCHEMA = "v4.1.4_modular_domain_pack"
EDGE_START = 60          # the client's packs use E03-E35; ours starts clear of them, configurable per scenario
TOP_QUESTIONS = 15
BOUNDARY = ("This file is a domain partition exported from the Axelrod world model. It is not the base ontology and does "
            "not decide investment conclusions: it states drivers, exposures, transmission, timing, and how sure the model "
            "is. Load it after 000, 010, and 020, only when activated by its domain pack id or file index.")
DO_NOT_INFER = [
    "Do not infer buy/add/overweight or sell/trim/underweight from a favorable or adverse forecast alone.",
    "Do not read an effect in standard deviations as a price target or a level without its unit and scale.",
    "Do not treat a relationship's existence probability as evidence that the effect is material.",
    "Do not identify a funding source or funding candidate from this pack.",
]
REQUIRED_BASELINES = ["prior_quarter", "prior_year", "consensus", "axelrod_baseline_forecast"]
TICKER = re.compile(r"^(?:\d{3,6} [A-Z]{2}|[A-Z]{1,5}|[A-Z0-9]{2,5} [A-Z]{2})$")


def _snake(s: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]+", "_", str(s).upper())).strip("_")


def _ticker(e: Any) -> str | None:
    return next((a for a in e.aliases if TICKER.match(a)), None)


def _node_id(e: Any) -> str:
    """N_<TICKER_OR_COMPANY>: a plain ticker where there is one, else the name."""
    t = _ticker(e)
    if t and re.fullmatch(r"[A-Z]{1,5}", t):
        return f"N_{t}"
    return f"N_{_snake(getattr(e, 'short', None) or e.name)}"


def _confidence(p: float) -> str:
    return "high" if p >= 0.85 else "medium_high" if p >= 0.7 else "medium" if p >= 0.5 else "context_only"


def _mean(d: Any) -> float | None:
    try:
        return float(d.mean())
    except Exception:
        return None


def _q(d: Any, q: float) -> float | None:
    try:
        return float(d.quantile(q))
    except Exception:
        return None


def _direction(i: Any) -> str:
    """positive / negative when the effect's 90% range keeps its sign, mixed when it straddles zero; for an
    uncalibrated link, the sign its transition states."""
    if not getattr(i, "quantified", True):
        return "positive" if i.polarity() > 0 else "negative"
    lo, hi, m = _q(i.forward.effect, 0.05), _q(i.forward.effect, 0.95), _mean(i.forward.effect) or 0.0
    if lo is not None and hi is not None and lo < 0 < hi:
        return "mixed_lean_positive" if m > 0 else "mixed_lean_negative"
    return "positive" if m > 0 else "negative" if m < 0 else "mixed"


def _sign_of(rel: dict) -> bool:
    """Whether an exported relationship raises its target (from its effect, or its stated sign when uncalibrated)."""
    ax = rel["axelrod"]
    return (ax["effect_sd_per_sd"] > 0) if ax["effect_sd_per_sd"] is not None else ax.get("sign") == "+"


def _horizon(k: Any) -> str:
    """A kernel in words: when the effect starts, how long it builds, how long it lasts."""
    delay, lag = _mean(k.delay), _mean(k.lag)
    dur = _mean(k.duration) if k.duration is not None else None
    parts = [f"starts after ~{delay:.0f}d" if delay is not None else None,
             f"builds over ~{lag:.0f}d" if lag is not None else None,
             f"fades over ~{dur:.0f}d" if dur is not None else "persists"]
    return ", ".join(p for p in parts if p)


def _provenance(origin: Any) -> str:
    o = str(origin)
    return {"construction": "client_seeded_structure", "import": "imported_research_reviewed",
            "learned": "learned_from_data_reviewed", "manual": "analyst_added_reviewed"}.get(o.split(".")[-1], o)


def _cause_first(chain: list[Any]) -> list[Any]:
    """Interactions ordered so that every cause comes before what it moves (ties by id; a cycle is cut by id)."""
    left, out = sorted(chain, key=lambda i: i.id), []
    while left:
        targets = {i.target_id for i in left}
        ready = [i for i in left if i.source_id not in targets] or left[:1]
        out += ready
        left = [i for i in left if i not in ready]
    return out


# Oct 17: what the business construction carries that the v4.1.4 schema has no field for, and where it is instead
SCHEMA_GAPS = [
    {"concept": "transition timing by part (onset, build-up, persistence, reporting recognition)",
     "carried_in": "company_edge_relationships[].axelrod.transition.timing", "canonical_nearest": "time_horizon"},
    {"concept": "the observable's definition, units, frequency, and proof limits",
     "carried_in": "company_edge_relationships[].axelrod.transition.observable", "canonical_nearest": "evidence_required"},
    {"concept": "evidence kept apart for existence, direction, magnitude, and timing",
     "carried_in": "company_edge_relationships[].axelrod.transition.evidence",
     "canonical_nearest": "evidence_source_type, evidence_reliability"},
    {"concept": "calibration status (a represented link whose size is unknown)",
     "carried_in": "company_edge_relationships[].qualification_status and .axelrod.magnitude", "canonical_nearest": "status"},
    {"concept": "business composition views with residuals and eliminations",
     "carried_in": "domain_specific_support_objects.financial_bridge", "canonical_nearest": "financial_model_semantic_fields"},
    {"concept": "parallel branches within a path",
     "carried_in": "transmission_paths[].axelrod.steps[].branch", "canonical_nearest": "ordered_steps"},
    {"concept": "identities that are not sums (products, ratios, differences) and stock-flow roll-forwards, with their "
                "formulas and derived weights",
     "carried_in": "company_edge_relationships[].axelrod.identity and domain_specific_support_objects."
                   "financial_identities", "canonical_nearest": "dependency_type"},
    {"concept": "state-dependent responses (rises versus falls, thresholds, sign flips)",
     "carried_in": "company_edge_relationships[].axelrod.state", "canonical_nearest": "invalidator"},
]

# Oct 18: how a stock-flow link computes, stated wherever it is exported
STOCK_FLOW_NOTE = ("The stock integrates the flow's deviation from its construction level: a flow held one sd above its "
                   "level adds the weight to the stock every period, linearized at the construction levels. The baseline "
                   "accumulation (the flow at its level) is part of the stock's own path, not added by the link.")


def identity_ref(g: Any, i: Any) -> dict:
    """The identity or stock-flow a link is a term of, with its formula and how its weight was set (Oct 18)."""
    names = {k: v.name for k, v in g.subentities.items()}
    if str(i.edge_type) == "stock_flow":
        x = g.stock_flows.get(i.identity)
        if x is None:
            return {"identity_id": i.identity, "form": "stock_flow", "formula": None}
        return {"identity_id": x.id, "form": "stock_flow", "formula": x.formula(names), "period_days": x.period_days,
                "role": "inflow" if i.source_id in x.inflows else "outflow", "computation": STOCK_FLOW_NOTE}
    x = g.identities.get(i.identity)
    if x is None:
        return {"identity_id": i.identity, "form": None, "formula": None}
    return {"identity_id": x.id, "form": x.form, "formula": x.formula(names), "role": x.role(i.source_id),
            "computation": "weight derived at the construction levels and scales, fixed (never refit)"}


def pack_config(scenario_id: str, title: str, cfg: dict | None = None) -> dict:
    """The pack's identity: its PACK_ id, name, file slug, file index, and the first number of its edge vocabulary."""
    cfg = dict(cfg or {})
    slug = cfg.get("slug") or re.sub(r"[^a-z0-9]+", "_", scenario_id.lower()).strip("_")
    return {"domain_pack_id": cfg.get("domain_pack_id") or f"PACK_{_snake(scenario_id)}",
            "domain_pack_name": cfg.get("name") or title, "slug": slug,
            "file_index": str(cfg.get("file_index") or "036"), "edge_start": int(cfg.get("edge_id_start") or EDGE_START)}


def pack_file_name(pc: dict) -> str:
    return f"{pc['file_index']}_world_model_domain_pack_{pc['slug']}_{SCHEMA}.json"


def domain_pack(wm: Any, ltm: Any, *, pc: dict, book: list[str], version: int, state_hash: str | None) -> dict:
    g = wm.graph
    ents = g.entities
    subs = g.subentities
    otax = ltm.object_generalizations.taxonomy
    itax = ltm.interaction_generalizations.taxonomy
    stamp = f"axelrod_world_model_v{version}"
    node = {eid: _node_id(e) for eid, e in ents.items()}
    is_co = {eid: str(e.kind) == "company" for eid, e in ents.items()}
    ent_of = {sid: s.entity_id for sid, s in subs.items()}
    # a value's metric name is its id's suffix unless it states one (Oct 17: Tokio Marine's "operating_profit" is
    # adjusted net income by definition, so it says so instead of passing for an operating-profit measure)
    slot = {sid: (getattr(s, "features", None) or {}).get("metric") or sid.split(".", 1)[-1] for sid, s in subs.items()}

    def concepts(gid: str | None) -> list[str]:
        if not gid or gid not in otax.nodes:
            return []
        return [otax.nodes[n].name for n in otax.path_from_root(gid) if n != otax.root_id]

    # the pack's edge vocabulary: one E## per interaction concept in long-term memory (unclassified links share one)
    live = [i for i in g.interactions.values() if i.retired_at is None and i.source_id in subs and i.target_id in subs]
    gens = sorted({i.generalization_id or "" for i in live})
    vocab: dict[str, dict] = {}
    for k, gid in enumerate(gens):
        name = itax.nodes[gid].name if gid in itax.nodes else ("Unclassified link" if not gid else gid.split(":")[-1])
        eid = f"E{pc['edge_start'] + k:02d}"
        # the id keeps the concept's base name, short as the client's are; refinements stay in the label
        short = "_".join(_snake(re.split(r"[(\[]", name)[0]).split("_")[:4])
        vocab[gid] = {"edge_id": eid, "edge_name": short, "edge_label": name, "axelrod_concept_id": gid or None,
                      "definition": f"{name}: a causal link the model holds, with an effect size, a lag, and an existence "
                                    "probability learned from data and reviewed research.",
                      "relationship_verb": "exposed_to"}
    ev = {i.id: vocab[i.generalization_id or ""] for i in live}

    # patterns (superentities): leaves become clusters with search scopes; the top level becomes sector packs
    patterns = getattr(ltm.object_generalizations, "patterns", {})
    adm = {pid: p for pid, p in patterns.items() if str(p.status).endswith("admitted")}
    top = [p for p in adm.values() if not any(p.id in q.sub_pattern_ids for q in adm.values())]
    insts = {p: [x for x in g.instances.values() if x.pattern_id == p] for p in adm}
    cl_id = {pid: f"CL_{_snake(p.name)}" for pid, p in adm.items()}
    members = {pid: sorted({e for x in insts[pid] for e in x.bindings.values() if e in ents}) for pid in adm}

    def all_members(pid: str) -> list[str]:
        out = set(members[pid])
        for c in adm[pid].sub_pattern_ids:
            if c in adm:
                out |= set(all_members(c))
        return sorted(out)

    sp_id = {p.id: f"PACK_{_snake(p.name)}" for p in top}
    sp_of: dict[str, list[str]] = {}
    for p in top:
        for e in all_members(p.id):
            sp_of.setdefault(e, []).append(sp_id[p.id])

    # metric families: one per value concept (attribute kind), with the metrics (value slots) under it
    fam: dict[str, set[str]] = {}
    for sid, s in subs.items():
        fam.setdefault(s.attribute_kind, set()).add(slot[sid])
    mf_id = {k: f"MF_{_snake(k)}" for k in fam}

    companies, macro_nodes = [], []
    for eid, e in sorted(ents.items()):
        cpath = concepts(e.generalization_id)
        region = e.features.get("region")
        # a company's concept path reads institutions > companies > sector > industry (GICS-like); other nodes read
        # branch > class > subclass (markets and asset classes > fixed income > sovereign bonds)
        depth = 2 if is_co[eid] and len(cpath) >= 3 else 1 if len(cpath) >= 2 else 0
        sector = cpath[depth] if cpath else (e.features.get("sector") or "").replace("_", " ").title()
        tax = {"sector": sector, "subsectors": cpath[depth + 1:] or ([cpath[-1]] if cpath else []),
               "geographies": [region] if region else [], "geographic_scope": region or "global", "supply_chain_layer": None}
        packs = sorted(set(sp_of.get(eid, [])))
        if is_co[eid]:
            t = _ticker(e)
            companies.append({
                "company_id": node[eid], "descriptive_node_id": f"COMPANY_{node[eid][2:]}_{_snake(e.name)}",
                "company_name": e.name, "ticker": t, "role_tags": sorted({_snake(c).lower() for c in cpath[depth:]}
                                                                         | ({e.features["sector"]} if e.features.get("sector") else set())),
                "primary_sector_pack_id": packs[0] if packs else None, "secondary_sector_pack_ids": packs[1:],
                "node_group": "watchlist" if eid in book else "context", "source_packs_present": [stamp],
                "ontology_entity_type": "Company", "taxonomy": tax, "aliases": [a for a in e.aliases if a != t][:6],
                "description": e.description, "axelrod_entity_id": eid})
        else:
            macro_nodes.append({"node_id": node[eid], "descriptive_node_id": f"MACRO_{_snake(e.name)}", "node_name": e.name,
                                "ontology_entity_type": "MacroFactor", "taxonomy": tax, "description": e.description,
                                "sector_pack_ids": packs, "axelrod_entity_id": eid})

    def link(i: Any, owner: str | None) -> dict:
        src, tgt = subs[i.source_id], subs[i.target_id]
        v = ev[i.id]
        p = _mean(i.existence) or 0.0
        k = i.forward.kernel
        reach = (_mean(k.delay) or 0) + (_mean(k.lag) or 0)
        last = max((x.observed_at for x in i.evidence), default=None)
        sign = "rises" if i.polarity() > 0 else "falls"
        out = {
            "edge_id": v["edge_id"], "direction": _direction(i), "confidence_prior": _confidence(p),
            "affected_metrics": [slot[i.target_id]], "ontology_relationship_type_hint": [_snake(i.label).lower()],
            "mechanism_label": f"{src.name} {i.label} {tgt.name}", "time_horizon": _horizon(k),
            "status": "active" if p >= 0.5 else "candidate",
            "evidence_required": [f"{src.name} moves", f"{tgt.name} responds within ~{reach:.0f} days"],
            "evidence_available": [f"{len(i.evidence) + i.evidence_dropped} reviewed evidence item(s)"] if i.evidence else [],
            "validator": f"{tgt.name} {sign} within ~{reach:.0f} days after {src.name} rises",
            "invalidator": f"{src.name} moves materially and {tgt.name} does not respond within ~{max(30, 2 * reach):.0f} days",
            "last_validated_at": last.isoformat() if last else None, "valid_from": i.created_at.isoformat(),
            "source_provenance": _provenance(i.origin), "source_packs_present": [stamp],
            "axelrod": {"interaction_id": i.id, "source_metric": i.source_id, "target_metric": i.target_id,
                        "source_node_id": node[src.entity_id], "target_node_id": node[tgt.entity_id],
                        "effect_sd_per_sd": round(_mean(i.forward.effect) or 0.0, 4),
                        "effect_q05": None if _q(i.forward.effect, 0.05) is None else round(_q(i.forward.effect, 0.05), 4),
                        "effect_q95": None if _q(i.forward.effect, 0.95) is None else round(_q(i.forward.effect, 0.95), 4),
                        "existence_p": round(p, 4), "delay_days": round(_mean(k.delay) or 0, 1),
                        "lag_days": round(_mean(k.lag) or 0, 1),
                        "duration_days": None if k.duration is None else round(_mean(k.duration) or 0, 1),
                        "evidence_count": len(i.evidence) + i.evidence_dropped}}
        tr = i.transition
        if tr is not None:
            # Oct 17: the link as a business step, in the canonical properties; what has no canonical field (timing
            # by part, the observable's definition and proof limits, evidence by claim) rides under "axelrod"
            out["mechanism_label"] = tr.mechanism
            out["validator"] = "; ".join(x for x in (tr.condition, tr.condition_observable and
                                                    f"observable: {tr.condition_observable}") if x) or out["validator"]
            if tr.breaker:
                out["invalidator"] = tr.breaker + (f" (threshold: {tr.breaker_threshold})" if tr.breaker_threshold else "")
            if tr.timing.onset != "unknown" or tr.timing.build != "unknown":
                out["time_horizon"] = f"onset {tr.timing.onset}; build {tr.timing.build}"
            out["evidence_required"] = [x for x in (tr.condition_observable, tr.observable and tr.observable.name) if x] \
                or out["evidence_required"]
            out["evidence_source_type"] = tr.evidence.existence
            out["evidence_reliability"] = tr.evidence.magnitude
            out["axelrod"]["transition"] = tr.model_dump(mode="json")
        out["dependency_type"] = "accounting_identity" if i.fixed else "causal"
        if i.identity is not None:
            out["axelrod"]["identity"] = identity_ref(g, i)
        if i.note:
            out["axelrod"]["note"] = i.note
        if i.state is not None:
            out["axelrod"]["state"] = {**i.state.model_dump(mode="json", exclude_none=True),
                                       "in_words": state_text(i, {k: v.name for k, v in subs.items()})}
        out["qualification_status"] = str(i.calibration)
        if not i.quantified:
            # no size is known: it is not zero, and nothing numeric is reported for it
            out["status"] = "represented_uncalibrated"
            out["validator"] = out["validator"].replace("rises", "moves") if tr is None else out["validator"]
            out["axelrod"].update(effect_sd_per_sd=None, effect_q05=None, effect_q95=None, delay_days=None, lag_days=None,
                                  duration_days=None, magnitude="unknown (uncalibrated)",
                                  sign=tr.sign if tr is not None else None)
        if owner:
            out = {"relationship_id": "", "company_id": owner, **out}
        return out

    # company edge relationships: owned by the company whose metrics the link moves (or that drives it)
    rels, macro_links, seen = [], [], set()
    for i in sorted(live, key=lambda x: x.id):
        te, se = ent_of[i.target_id], ent_of[i.source_id]
        owner_e = te if is_co[te] else se if is_co[se] else None
        if owner_e is None:
            m = link(i, None)
            macro_links.append({"link_id": f"MLINK_{node[se][2:]}_TO_{node[te][2:]}__{m['edge_id']}_{_snake(slot[i.target_id])}",
                                "source_node_id": node[se], "target_node_id": node[te], **m})
            continue
        r = link(i, node[owner_e])
        rid = f"REL_{node[owner_e][2:]}__{r['edge_id']}_{ev[i.id]['edge_name']}"
        if rid in seen:
            rid = f"{rid}__{_snake(slot[i.target_id])}"
        n = 2
        while rid in seen:
            rid, n = f"{rid}_{n}", n + 1
        seen.add(rid)
        r["relationship_id"] = rid
        rels.append(r)

    # clusters, memberships, and the search scopes that would confirm or break each cluster's links
    clusters, memberships, scopes = [], [], []
    for pid, p in sorted(adm.items(), key=lambda kv: kv[0]):
        mem = all_members(pid)
        cos = [node[e] for e in mem if is_co[e]] + [node[e] for e in mem if not is_co[e]]
        mids = []
        for x in insts[pid]:
            for role, e in sorted(x.bindings.items()):
                if e in ents:
                    mid = f"CLMEM_{cl_id[pid][3:]}__{node[e][2:]}"
                    if mid not in mids:
                        mids.append(mid)
                        memberships.append({"cluster_membership_id": mid, "cluster_id": cl_id[pid], "company_id": node[e],
                                            "membership_role": _snake(role).lower(), "source_packs_present": [stamp]})
        clusters.append({"cluster_id": cl_id[pid], "cluster_name": p.name, "canonical_cluster_name": p.name,
                         "description": p.description, "company_ids": cos, "membership_ids": mids,
                         "subclusters": [adm[c].name for c in p.sub_pattern_ids if c in adm],
                         "activation_terms": [p.name, *[ents[e].name for e in mem]][:12],
                         "purpose": f"A configuration the model holds (support {p.support:.0f}; "
                                    f"track record {p.track_record.hits} hit(s), {p.track_record.misses} miss(es)).",
                         "source_packs_present": [stamp], "axelrod_pattern_id": pid})
        if p.sub_pattern_ids:
            continue
        chain = [g.interactions[i] for x in insts[pid] for i in x.interaction_ids if i in g.interactions and i in ev]
        mf = sorted({mf_id[subs[i.target_id].attribute_kind] for i in chain})
        scopes.append({
            "required_search_scope_id": f"REQ_SEARCH_{cl_id[pid][3:]}", "search_scope_label": f"{p.name} required search scope",
            "sector_pack_ids": sorted({s for e in mem for s in sp_of.get(e, [])}), "cluster_ids": [cl_id[pid]],
            "caveat_ids": [], "metric_family_ids": mf,
            "why_required": f"The links inside {p.name} carry the model's transmission; evidence that they hold or break "
                            "moves the forecast.",
            "member_selector": {"clusters": [cl_id[pid]], "role_tags": sorted({t for c in companies if c["company_id"] in cos
                                                                              for t in c["role_tags"]}),
                                "geographies": sorted({gg for e in mem for gg in ([ents[e].features["region"]] if ents[e].features.get("region") else [])})},
            "seed_search_targets": [ents[e].name for e in mem][:12],
            "mechanisms_to_inspect": sorted({i.label for i in chain})[:12],
            "confirming_evidence": [f"{subs[i.source_id].name} moves and {subs[i.target_id].name} follows" for i in chain][:8],
            "breaking_evidence": [f"{subs[i.source_id].name} moves without {subs[i.target_id].name} responding" for i in chain][:8],
            "search_templates": [f"{{member}} {subs[i.target_id].name.split(' ', 1)[-1]}" for i in chain][:6],
            "search_cost_hint": "medium", "freshness_window_default": "30d",
            "result_states_allowed": ["Qualified signal found", "Quiet / medium-high confidence",
                                      "No qualifying signal / low confidence", "Unavailable"]})

    sector_packs = []
    for p in top:
        mem = all_members(p.id)
        scope_ids = [s["required_search_scope_id"] for s in scopes if set(s["cluster_ids"]) & {cl_id[c] for c in [p.id, *p.sub_pattern_ids] if c in cl_id}]
        mfs = sorted({mf_id[subs[s].attribute_kind] for e in mem for s in ents[e].subentity_ids if s in subs})
        sector_packs.append({"sector_pack_id": sp_id[p.id], "sector_pack_name": p.name,
                             "when_to_activate": [p.name, *[ents[e].name for e in mem]][:14],
                             "company_role_tags_covered": sorted({t for c in companies if c["axelrod_entity_id"] in mem for t in c["role_tags"]}),
                             "metric_family_ids": mfs, "required_baselines": REQUIRED_BASELINES, "do_not_infer": DO_NOT_INFER,
                             "source_packs_present": [stamp], "required_search_scope_ids": scope_ids})

    metric_families = []
    for k, slots in sorted(fam.items()):
        name = k.replace("_", " ").capitalize()
        metric_families.append({"metric_family_id": mf_id[k], "metric_family_name": name, "metrics": sorted(slots),
                                "required_baselines": REQUIRED_BASELINES,
                                "do_not_conclude_without": [f"Do not call a move in {name.lower()} large or small without its "
                                                            "90% interval and the baseline forecast.",
                                                            "Do not read a standardized effect as a level without its unit."],
                                "source_packs_present": [stamp]})

    # cross-validation: two companies moved by the same driver should move together (or apart, if the signs differ)
    by_src: dict[str, list[dict]] = {}
    for r in rels:
        by_src.setdefault(r["axelrod"]["source_metric"], []).append(r)
    cross, seen_cv = [], set()
    for src, rs in sorted(by_src.items()):
        rs = [r for r in rs if r["company_id"] != node[ent_of[src]]]
        for a, b in zip(rs, rs[1:]):
            if a["company_id"] == b["company_id"]:
                continue
            same = _sign_of(a) == _sign_of(b)
            cid = f"CV_{a['company_id'][2:]}_TO_{b['company_id'][2:]}__{a['edge_id']}_{_snake(slot[src])}"
            if cid in seen_cv:
                continue
            seen_cv.add(cid)
            cross.append({"cross_validation_id": cid, "source_company_id": a["company_id"], "target_company_id": b["company_id"],
                          "edge_id": a["edge_id"], "validation_direction": "positive_or_mixed" if same else "negative_or_mixed",
                          "mechanism": f"{subs[src].name} moves both: {subs[a['axelrod']['target_metric']].name} and "
                                       f"{subs[b['axelrod']['target_metric']].name} should move {'together' if same else 'apart'}."})

    # caveats: soft economic bounds, and the open questions the model is testing (the hypothesis frontier)
    caveats, impacts = [], []
    rel_of: dict[str, list[dict]] = {}
    for r in rels:
        rel_of.setdefault(r["company_id"], []).append(r)
    for sid, s in sorted(subs.items()):
        c = getattr(s, "constraint", None)
        if c is None:
            continue
        cav = f"CAV_BOUND_{_snake(sid)}"
        caveats.append({"caveat_id": cav, "caveat_name": f"{s.name}: soft bound", "caveat_type": "soft_economic_bound",
                        "definition": c.reason or f"{s.name} tends to stay within its bound", "bounds": {"min": c.min, "max": c.max},
                        "not_a_conclusion": "A tendency, not a law: the model bends forecasts toward it."})
    # structural caveats the model holds about its own links: seeded but not yet validated by reviewed research, and
    # links whose sign is still uncertain (the effect's 90% range straddles zero)
    for cav, name, ctype, definition, pick in [
        ("CAV_UNVALIDATED_SEEDED_LINKS", "Seeded links not yet validated", "evidence_gap",
         "Relationships seeded from the client's view of the chain that no reviewed research has yet confirmed or broken.",
         lambda r: r["axelrod"]["evidence_count"] == 0),
        ("CAV_SIGN_UNCERTAIN_LINKS", "Links with an uncertain sign", "sign_uncertainty",
         "Relationships whose effect could still run either way: the model's 90% range for the effect includes zero.",
         lambda r: r["direction"].startswith("mixed"))]:
        hit = [r for r in rels if pick(r)]
        if not hit:
            continue
        caveats.append({"caveat_id": cav, "caveat_name": name, "caveat_type": ctype, "definition": definition,
                        "not_a_conclusion": "An exposure-check map: it says where evidence is thin, not that an effect is absent."})
        for r in hit:
            impacts.append({"caveat_impact_id": f"CAVIMPACT_{cav[4:]}__TO_{r['company_id'][2:]}__{r['edge_id']}",
                            "caveat_id": cav, "affected_company_id": r["company_id"], "edge_id": r["edge_id"],
                            "severity_prior": "medium_high" if r["axelrod"]["existence_p"] >= 0.85 else "medium",
                            "exposure_status": "exposure_check_requires_supplied_data", "affected_metrics": r["affected_metrics"],
                            "not_a_materiality_conclusion": True})
    frontier = sorted((h for h in wm.hypotheses.values() if str(h.status).endswith("open")),
                      key=lambda h: (-(h.informational_value or 0.0), -h.probability))[:TOP_QUESTIONS]
    for h in frontier:
        cav = f"CAV_OPEN_{_snake(h.id)}"
        caveats.append({"caveat_id": cav, "caveat_name": h.statement[:80], "caveat_type": "open_hypothesis",
                        "definition": h.statement, "probability": round(h.probability, 3),
                        "not_a_conclusion": "An open question the model is testing; not evidence either way."})
        for e in h.subject_entity_ids:
            if e in node and is_co.get(e):
                r0 = (rel_of.get(node[e]) or [None])[0]
                impacts.append({"caveat_impact_id": f"CAVIMPACT_{cav[4:]}__TO_{node[e][2:]}__{r0['edge_id'] if r0 else 'NA'}",
                                "caveat_id": cav, "affected_company_id": node[e], "edge_id": r0["edge_id"] if r0 else None,
                                "severity_prior": "medium_high" if (h.informational_value or 0) > 0.05 else "medium",
                                "exposure_status": "exposure_check_requires_supplied_data",
                                "affected_metrics": r0["affected_metrics"] if r0 else [],
                                "not_a_materiality_conclusion": True})

    # one impact id per caveat, company, and edge (several links of one company can share an edge)
    uniq: dict[str, dict] = {}
    for imp in impacts:
        if imp["caveat_impact_id"] in uniq:
            prev = uniq[imp["caveat_impact_id"]]
            prev["affected_metrics"] = sorted(set(prev["affected_metrics"]) | set(imp["affected_metrics"]))
        else:
            uniq[imp["caveat_impact_id"]] = imp
    impacts[:] = list(uniq.values())

    # transmission paths: each leaf configuration's chain, cause before effect
    paths = []
    for pid, p in sorted(adm.items()):
        if p.sub_pattern_ids:
            continue
        chain = _cause_first([g.interactions[i] for x in insts[pid] for i in x.interaction_ids if i in g.interactions and i in ev])
        if not chain:
            continue
        cos = [node[ent_of[i.target_id]] for i in chain if is_co[ent_of[i.target_id]]]
        # the company the chain reaches most; on a tie, the one it reaches first (a set's order varies by process,
        # so the same model exported twice named different companies)
        primary = max(dict.fromkeys(cos), key=cos.count) if cos else "EVENT_OR_CONTEXT_DRIVEN"
        paths.append({"path_id": f"PATH_{primary[2:] if cos else 'CONTEXT'}_{cl_id[pid][3:]}", "primary_company_id": primary,
                      "trigger": f"{subs[chain[0].source_id].name} moves",
                      "ordered_steps": [f"{ev[i.id]['edge_id']}: {subs[i.source_id].name} {i.label} {subs[i.target_id].name}"
                                        for i in chain],
                      "edge_ids": list(dict.fromkeys(ev[i.id]["edge_id"] for i in chain)),
                      "company_ids": sorted(set(cos)), "cluster_id": cl_id[pid]})

    # Oct 17: the business paths the construction names (model/construction.py), step by step with their transitions
    for pid, np_ in sorted(g.paths.items()):
        steps = [(st, g.interactions[st.interaction_id]) for st in np_.steps if st.interaction_id in g.interactions]
        steps = [(st, i) for st, i in steps if i.id in ev]
        if not steps:
            continue
        owner = node.get(np_.entity_id, np_.entity_id)
        paths.append({
            "path_id": f"PATH_{owner[2:] if owner.startswith('N_') else _snake(owner)}_{_snake(np_.name)}",
            "primary_company_id": owner, "trigger": np_.trigger,
            "ordered_steps": [f"{ev[i.id]['edge_id']}{f' [{st.branch}]' if st.branch else ''}: "
                              f"{(i.transition.mechanism if i.transition else f'{subs[i.source_id].name} {i.label} {subs[i.target_id].name}')}"
                              f"{'' if i.quantified else ' (uncalibrated)'}" for st, i in steps],
            "edge_ids": list(dict.fromkeys(ev[i.id]["edge_id"] for _st, i in steps)),
            "company_ids": [owner], "path_kind": "business_construction",
            "axelrod": {"path_id": pid, "endpoint": np_.endpoint, "description": np_.description,
                        "active_when": np_.active_when or None,
                        "steps": [{"interaction_id": i.id, "branch": st.branch, "source_metric": i.source_id,
                                   "target_metric": i.target_id, "calibration": str(i.calibration),
                                   "edge_type": str(i.edge_type)} for st, i in steps]}})
    # and the compositions: each view of a business, its parts, and how they reconcile to the total (Oct 18: at the
    # model's levels, each additive view's parts against its total, model/construction.reconcile)
    from axelrod_wm.model.construction import (
        composition_role,
        reconcile,
        reconcile_identities,
        reconcile_matrices,
    )

    rec = {r["composition_id"]: {k: v for k, v in r.items() if k not in ("composition_id", "entity_id", "view", "role")}
           for r in reconcile(g)}
    mrec = {r["matrix_id"]: r for r in reconcile_matrices(g)}
    in_matrix = {cid: mid for mid, m in g.matrices.items() for cid in (m.rows, m.columns)}
    bridge = [{"composition_id": c.id, "company_id": node.get(c.entity_id, c.entity_id), "view": c.view, "basis": c.basis,
               "unit": c.unit, "period": c.period, "total_metric": c.total, "member_metrics": list(c.members),
               "residual_metric": c.residual, "eliminations_metric": c.eliminations, "additive": c.additive,
               "note": c.note, "overlaps_other_views": [o.id for o in g.compositions.values()
                                                        if o.entity_id == c.entity_id and o.id != c.id],
               "role": composition_role(g, c.id), "matrix_id": in_matrix.get(c.id),
               "reconciliation": rec.get(c.id)}
              for c in sorted(g.compositions.values(), key=lambda c: c.id)]
    names = {k: v.name for k, v in subs.items()}
    irec = {r["identity_id"]: r for r in reconcile_identities(g)}
    identities = [{"identity_id": x.id, "company_id": node.get(x.entity_id, x.entity_id), "form": x.form,
                   "target_metric": x.target, "formula": x.formula(names), "formula_ids": x.formula(),
                   "terms": [{"metric": v, "role": x.role(v), "exponent_or_sign": e} for v, e in x.terms()],
                   "coefficient": x.coefficient, "unit_check": x.unit_check, "basis": x.basis, "period": x.period,
                   "note": x.note, "weights": "derived at the construction levels: d ln y = sum e_i d ln x_i (product, "
                   "ratio) or dy = sum s_i dx_i (difference), in sd/sd", "reconciliation": irec.get(x.id)}
                  for _, x in sorted(g.identities.items())]
    identities += [{"identity_id": x.id, "company_id": node.get(x.entity_id, x.entity_id), "form": "stock_flow",
                    "target_metric": x.stock, "formula": x.formula(names), "formula_ids": x.formula(),
                    "terms": [{"metric": v, "role": "inflow" if e > 0 else "outflow", "exponent_or_sign": e}
                              for v, e in x.terms()], "period_days": x.period_days, "basis": x.basis, "note": x.note,
                    "weights": STOCK_FLOW_NOTE, "reconciliation": None}
                   for _, x in sorted(g.stock_flows.items())]
    matrices = [{"matrix_id": m.id, "company_id": node.get(m.entity_id, m.entity_id), "rows": m.rows,
                 "columns": m.columns, "driving": m.driving, "reconciling": m.passive,
                 "cells": [{"row": r, "column": c, "metric": v} for r, c, v in m.cell_list()], "note": m.note,
                 "reconciliation": mrec.get(m.id)} for _, m in sorted(g.matrices.items())]

    fm_fields: dict[str, dict] = {}
    for sid, s in sorted(subs.items()):
        if not is_co[ent_of[sid]]:
            continue
        f = fm_fields.setdefault(slot[sid], {"field_spec_id": f"FMSPEC_{_snake(slot[sid])}", "field_name": slot[sid].replace("_", " "),
                                             "applies_to": [], "required_for": ["transmission sensitivity", "scenario table"],
                                             "ontology_entity_type": "Metric", "source_packs_present": [stamp]})
        f["applies_to"].append(ents[ent_of[sid]].name)

    terms = sorted({a for e in ents.values() for a in e.aliases if len(a) > 2} | {c["company_name"] for c in companies})[:60]
    return {
        "schema_version": PACK_SCHEMA, "file_index": pc["file_index"], "domain_pack_id": pc["domain_pack_id"],
        "domain_pack_name": pc["domain_pack_name"], "file_role": "DOMAIN_PACK__LOAD_AFTER_CORE_WHEN_ACTIVATED",
        "important_boundary": BOUNDARY, "activation_terms": terms, "sector_pack_ids": [s["sector_pack_id"] for s in sector_packs],
        "companies": companies, "clusters": clusters, "cluster_memberships": memberships, "sector_packs": sector_packs,
        "metric_families": metric_families, "required_search_scopes": scopes, "company_edge_relationships": rels,
        "cross_validation_assertions": cross, "industry_caveat_definitions": caveats, "caveat_impact_assertions": impacts,
        "transmission_paths": paths, "financial_model_semantic_fields": list(fm_fields.values()),
        "domain_specific_support_objects": {
            "axelrod_edge_vocabulary": list(vocab.values()), "macro_factor_nodes": macro_nodes,
            "macro_transmission_links": macro_links,
            "financial_bridge": bridge, "financial_identities": identities, "financial_matrices": matrices,
            "schema_gaps": SCHEMA_GAPS if (bridge or g.paths or identities or any(i.transition for i in live)) else [],
            "axelrod_model_state": {"state_version": version, "state_hash": state_hash, "as_of": wm.clock.isoformat(),
                                    "numbers_note": "effect_sd_per_sd is the target's move in its own standard deviations per "
                                                    "standard deviation of the source; existence_p is the probability the link holds."}},
    }


def registry_entry(pc: dict, pack: dict) -> dict:
    """The row to append to the client's 020 registry, so the harness activates the pack by its id or file index."""
    return {"append_to": f"020_world_model_domain_pack_registry_{SCHEMA}.json",
            "domains": [{"domain_pack_id": pc["domain_pack_id"], "domain_pack_name": pc["domain_pack_name"],
                         "file_name": pack_file_name(pc), "activation_terms": pack["activation_terms"][:24],
                         "never_merge_into_base": True, "file_index": pc["file_index"]}]}


def evidence_pack(wm: Any, *, pc: dict, version: int, state_hash: str | None) -> dict:
    """The model's current state, as evidence the agents read after the domain pack (live state never enters a pack)."""
    g = wm.graph
    values = []
    for sid, s in sorted(g.subentities.items()):
        ent = g.entities.get(s.entity_id)
        d = s.posterior
        values.append({"metric_id": sid, "node_id": _node_id(ent) if ent else None, "node_name": ent.name if ent else s.entity_id,
                       "metric": sid.split(".", 1)[-1], "metric_name": s.name, "unit": s.unit,
                       "mean": None if _mean(d) is None else round(_mean(d), 4),
                       "sd": None if _sd(d) is None else round(_sd(d), 4),
                       "q05": None if _q(d, 0.05) is None else round(_q(d, 0.05), 4),
                       "q95": None if _q(d, 0.95) is None else round(_q(d, 0.95), 4),
                       "observed": bool(s.observed),
                       "baseline_status": "observed in reviewed research" if s.observed else "model estimate; not observed in supplied research",
                       "evidence_count": sum(len(i.evidence) for i in g.interactions.values() if i.target_id == sid)})
    questions = [{"id": h.id, "question": h.statement, "probability": round(h.probability, 3),
                  "informational_value": round(h.informational_value or 0.0, 4)}
                 for h in wm.hypotheses.values() if str(h.status).endswith("open")]
    questions.sort(key=lambda q: -q["informational_value"])
    return {"schema_version": f"{SCHEMA}_evidence_pack", "file_role": "EVIDENCE_PACK__AXELROD_CURRENT_STATE__LOAD_AFTER_DOMAIN_PACK",
            "domain_pack_id": pc["domain_pack_id"], "as_of": wm.clock.isoformat(), "state_version": version,
            "state_hash": state_hash, "values": values, "unresolved_questions": questions[:TOP_QUESTIONS],
            "evidence_boundary": "Live state from the Axelrod world model at a committed version. Evidence, not a conclusion."}


def _sd(d: Any) -> float | None:
    try:
        return float(d.sd())
    except Exception:
        return None


def forecast_record(fc: Any, explanation: Any, wm: Any, pc: dict) -> dict:
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
                      "axelrod_interaction_ids": [h.interaction_id.split(":")[0] for h in t.path],
                      "arrives_day": t.arrives_day, "peak_day": t.peak_day, "peak_sd": round(t.peak, 3),
                      "effect_at_horizon_sd": round(t.effect, 3), "material": t.material})
    key = []
    if explanation is not None:
        for iid, contrib in explanation.key_interactions[:10]:
            i = g.interactions.get(iid)
            key.append({"axelrod_interaction_id": iid, "contribution": round(float(contrib), 4),
                        "mechanism": f"{nm(i.source_id)} {i.label} {nm(i.target_id)}" if i else iid})
    return {"schema_version": f"{SCHEMA}_evidence_pack", "file_role": "EVIDENCE_PACK__AXELROD_FORECAST_DECISION_CONTEXT",
            "domain_pack_id": pc["domain_pack_id"], "forecast_id": fc.id, "thesis_id": fc.thesis_id, "question": fc.question,
            "based_on_version": fc.based_on_version, "seed": fc.seed, "config_hash": fc.config_hash,
            "horizon_days": fc.horizon_days, "targets": targets, "transmission": trans, "key_interactions": key,
            "constraints_binding": fc.constraints_binding, "scenario_table": fc.scenario_table,
            "scenarios": [{"id": s.id, "name": s.name, "weight": round(s.weight, 4)} for s in fc.scenarios],
            # Oct 18: what the numbers above are made of (inference/task.forecast_coverage): the quantified links that
            # contribute, the reached links that carry no size and why, the inputs that block them, and per target the
            # share of reached routes that are fully quantified
            "unquantified": fc.unquantified, "calculation_coverage": fc.coverage,
            "evidence_boundary": "A forecast the model computed; it grounds the agent's scenarios and never concludes an action."}


# which part of the context each of the client's agent cards reads
FEEDS = [
    {"agent": "Decision Engine", "card": "2 · Regime & thesis status", "reads": ["evidence.values", "domain_pack.clusters"]},
    {"agent": "Decision Engine", "card": "3 · What doesn't confirm", "reads": ["evidence.unresolved_questions",
                                                                               "domain_pack.industry_caveat_definitions",
                                                                               "domain_pack.required_search_scopes"]},
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
                 state_hash: str | None, forecast: Any = None, explanation: Any = None, pack_cfg: dict | None = None) -> dict:
    pc = pack_config(scenario_id, title, pack_cfg)
    pack = domain_pack(wm, ltm, pc=pc, book=book, version=version, state_hash=state_hash)
    evidence = evidence_pack(wm, pc=pc, version=version, state_hash=state_hash)
    day = str(evidence["as_of"])[:10]
    ev_file = f"evidence_pack_axelrod_{pc['slug']}_{day}_v{version}.json"
    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "generated_by": "Axelrod world model",
        "schema_version": SCHEMA, "boundary": BOUNDARY,
        "load_order": [
            {"file": f"000_core_world_model_common_contract_{SCHEMA}.json", "source": "yours, unchanged"},
            {"file": f"010_core_world_model_relationship_schema_{SCHEMA}_modular.txt", "source": "yours, unchanged"},
            {"file": f"020_world_model_domain_pack_registry_{SCHEMA}.json", "source": "yours, with this export: registry_entry appended"},
            {"file": pack_file_name(pc), "source": "this export: domain_pack"},
            {"file": ev_file, "source": "this export: evidence"},
            *([{"file": f"evidence_pack_axelrod_{pc['slug']}_forecast_{forecast.id}.json", "source": "this export: forecast"}]
              if forecast else []),
        ],
        "activate": {"domain_pack_id": pc["domain_pack_id"], "file_index": pc["file_index"]},
        "registry_entry_file": f"020_registry_entry_{pc['file_index']}_{pc['slug']}.json",
        "feeds": FEEDS,
    }
    out = {"manifest": manifest, "domain_pack": pack, "registry_entry": registry_entry(pc, pack), "evidence": evidence}
    if forecast is not None:
        out["forecast"] = forecast_record(forecast, explanation, wm, pc)
    return out


# Oct 18: the source catalogue and evidence references (context/construction.load_sources)
SOURCE_GAP = {"concept": "evidence references: the document, the location (sheet and cell, table and row, page and "
                         "paragraph), and the supporting passage behind a claim",
              "carried_in": "company_edge_relationships[].evidence_refs, macro_transmission_links[].evidence_refs, "
                            "evidence.values[].evidence_refs, and the source catalogue file",
              "canonical_nearest": "evidence_available"}


def source_catalogue_file(pack: dict) -> str:
    return f"source_catalogue_axelrod_{pack['domain_pack_id'].lower()}.json"


def attach_sources(ctx: dict, sources: dict) -> dict:
    """Bind an exported context (`context_pack`'s output, as JSON) to the local sources and citations.

    Each relationship (company edge or macro link) whose transition names source ids, or that has citations, gains
    `evidence_refs` [{source_id, document, location, passage}]; so does each evidence value with cited baselines. The
    domain pack's support objects gain `citation_gaps` (source ids that do not resolve, material claims without a
    citation giving a location, citation keys that name nothing exported) and a schema gap for the references. The
    catalogue (source id -> document, kind, publication date, period, basis, read state, proof limits) is its own file,
    listed in the manifest's load order right after the evidence pack; it is returned and kept under ctx["sources"].
    Passages are the client's text: an export with sources stays in the client's local folder."""
    from axelrod_wm.context.construction import citation_check, evidence_refs

    pack, ev, m = ctx["domain_pack"], ctx["evidence"], ctx["manifest"]
    sup = pack["domain_specific_support_objects"]
    links = []
    for r in [*pack["company_edge_relationships"], *sup["macro_transmission_links"]]:
        iid, tr = r["axelrod"]["interaction_id"], r["axelrod"].get("transition")
        links.append((iid, tr))
        refs = evidence_refs(iid, ((tr or {}).get("evidence") or {}).get("sources") or [], sources)
        if refs:
            r["evidence_refs"] = refs
    values = [v["metric_id"] for v in ev["values"]]
    for v in ev["values"]:
        refs = evidence_refs(v["metric_id"], [], sources)
        if refs:
            v["evidence_refs"] = refs
    chk = citation_check(links, values, sources, {iid for iid, _tr in links} | set(values))
    gaps = {"unresolved_source_ids": chk["unresolved"], "claims_without_citation": chk["claims_without_citation"],
            "unknown_citation_keys": chk["unknown_citation_keys"], "catalogue_problems": list(sources["problems"])}
    sup["citation_gaps"] = gaps
    sup["schema_gaps"] = [*sup["schema_gaps"], SOURCE_GAP]
    name = source_catalogue_file(pack)
    at = next(k for k, f in enumerate(m["load_order"]) if f["source"] == "this export: evidence") + 1
    m["load_order"].insert(at, {"file": name, "source": "this export: sources"})
    doc = {"schema_version": f"{SCHEMA}_source_catalogue",
           "file_role": "SOURCE_CATALOGUE__RESOLVES_EVIDENCE_REFS__LOAD_AFTER_EVIDENCE_PACK",
           "domain_pack_id": pack["domain_pack_id"], "companies": list(sources["companies"]),
           "sources": [sources["catalogue"][s] for s in sorted(sources["catalogue"])],
           "counts": {"sources": len(sources["catalogue"]), "resolved_ids": len(chk["resolved"]),
                      "unresolved_ids": len(chk["unresolved"]), "cited_links": chk["cited_links"],
                      "cited_values": chk["cited_values"],
                      "claims_without_citation": len(chk["claims_without_citation"]),
                      "unknown_citation_keys": len(chk["unknown_citation_keys"])},
           "citation_gaps": gaps,
           "evidence_boundary": "The client's own source material, named so an agent can open the document at the cited "
                                "location. Local to the client; never part of a pack."}
    ctx["sources"] = doc
    return doc
