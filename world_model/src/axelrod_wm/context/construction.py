"""A company's business construction, readable (Oct 17): its compositions, its named paths with every transition, its
links' calibration, and what is still missing, built from the model's own objects, so a reviewer can follow the logic
and see where it stops (model/construction.py).

`construction_view(graph, entity_id)` gives the objects as a dict (the API and MCP serve it); `to_markdown(view)` gives
the readable view: one table per composition, and per path a readable chain plus its transition table.

Oct 18: whether the evidence resolves (`load_sources`, `citation_check`: each cited source id to a document in the
company's local sources.json, each material claim to a citation with a location in its citations.json), the inputs a
company's transitions still need by status (`inputs_by_status`), and a plain keyword search of the supplied material
for each input before it is declared missing (`search_inputs`).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from axelrod_wm.model.construction import composition_role, validate_construction
from axelrod_wm.model.interaction import FIXED_EDGE_TYPES

UNKNOWN = "unknown"


def _level(sub: Any) -> dict:
    try:
        return {"mean": round(float(sub.posterior.mean()), 6), "unit": sub.unit}
    except Exception:  # noqa: BLE001 - a family without a mean still has a unit
        return {"mean": None, "unit": sub.unit}


def state_text(i: Any, names: dict[str, str]) -> str:
    """A link's state-dependent responses in words (Oct 18), or "" when it has none."""
    st = i.state
    if st is None:
        return ""
    out = []
    if st.asymmetry is not None:
        a = st.asymmetry
        v = a.value or i.source_id
        at = "its construction level" if a.at is None else f"{a.at:g}"
        out.append(f"{a.rises.get('mu', 0.0):+.2f} sd/sd while {names.get(v, v)} is above {at}, "
                   f"{a.falls.get('mu', 0.0):+.2f} below")
    if st.threshold is not None:
        t = st.threshold
        side, lvl = ("above", t.above) if t.above is not None else ("below", t.below)
        out.append(f"acts only while {names.get(t.value, t.value)} is {side} {lvl:g}")
    if st.sign_flip is not None:
        f = st.sign_flip
        out.append(f"sign as stated while {names.get(f.value, f.value)} is {f.positive} {f.at:g}, reversed otherwise")
    return "; ".join(out)


def _kind(i: Any) -> str:
    """How a link computes, beyond an estimate: accounting, identity, or a stock-flow with its period."""
    e = str(i.edge_type)
    if e == "stock_flow":
        return f"stock-flow, accumulates per {i.forward.kernel.lag.mean():g} days"
    return e if e in ("accounting", "identity") else ""


def _step(graph: Any, i: Any, branch: str | None) -> dict:
    tr = i.transition
    subs = graph.subentities
    row = {"interaction_id": i.id, "branch": branch, "source": i.source_id, "source_name": subs[i.source_id].name,
           "target": i.target_id, "target_name": subs[i.target_id].name, "label": i.label,
           "edge_type": str(i.edge_type), "calibration": str(i.calibration),
           "effect": round(float(i.forward.effect.mean()), 4) if i.quantified else None,
           "magnitude": "estimated" if i.quantified else "unknown (uncalibrated)",
           "sign": "+" if i.polarity() > 0 else "-", "transition": tr.model_dump(mode="json") if tr is not None else None,
           "computes_as": _kind(i), "identity": i.identity,
           "state": state_text(i, {k: v.name for k, v in subs.items()})}
    return row


def _terms(graph: Any, x: Any, target: str, edge: str) -> list[dict]:
    """Each term of an identity or stock-flow, its role, and its link's derived weight (None when the link is missing)."""
    links = {(i.source_id, i.identity): i for i in graph.active_interactions()
             if str(i.edge_type) == edge and i.target_id == target}
    out = []
    for v, e in x.terms():
        i = links.get((v, x.id))
        role = x.role(v) if edge == "identity" else ("inflow" if e > 0 else "outflow")
        out.append({"value": v, "role": role, "interaction_id": i.id if i else None,
                    "weight": round(float(i.forward.effect.mean()), 4) if i else None})
    return out


def construction_view(graph: Any, entity_id: str) -> dict:
    """The construction of one company: its attributes (with their view), compositions, named paths, links, and
    problems."""
    if entity_id not in graph.entities:
        raise KeyError(entity_id)
    ent = graph.entities[entity_id]
    own = [graph.subentities[s] for s in ent.subentity_ids if s in graph.subentities]
    attributes = [{"id": s.id, "key": s.id.removeprefix(f"{entity_id}."), "name": s.name, "concept": s.attribute_kind,
                   **_level(s), "view": s.features.get("view", ""), "basis": s.features.get("basis", ""),
                   "proxy_for": s.features.get("proxy_for", "")} for s in own]
    comps = [{"id": c.id, "view": c.view, "basis": c.basis, "unit": c.unit, "period": c.period, "additive": c.additive,
              "total": c.total, "members": list(c.members), "residual": c.residual, "eliminations": c.eliminations,
              "note": c.note, "role": composition_role(graph, c.id)}
             for c in sorted(graph.compositions.values(), key=lambda c: c.id) if c.entity_id == entity_id]
    names = {k: v.name for k, v in graph.subentities.items()}
    identities = [{"id": x.id, "form": x.form, "target": x.target, "formula": x.formula(names),
                   "coefficient": x.coefficient, "unit_check": x.unit_check, "basis": x.basis, "period": x.period,
                   "note": x.note, "terms": _terms(graph, x, x.target, "identity")}
                  for _, x in sorted(graph.identities.items()) if x.entity_id == entity_id]
    stock_flows = [{"id": x.id, "stock": x.stock, "formula": x.formula(names), "period_days": x.period_days,
                    "basis": x.basis, "note": x.note, "flows": _terms(graph, x, x.stock, "stock_flow")}
                   for _, x in sorted(graph.stock_flows.items()) if x.entity_id == entity_id]
    matrices = [{"id": m.id, "rows": m.rows, "columns": m.columns, "drives": m.drives, "passive": m.passive,
                 "cells": [{"row": r, "column": c, "value": v} for r, c, v in m.cell_list()], "note": m.note}
                for _, m in sorted(graph.matrices.items()) if m.entity_id == entity_id]
    paths = []
    for p in sorted(graph.paths.values(), key=lambda p: p.id):
        if p.entity_id != entity_id:
            continue
        steps = [_step(graph, graph.interactions[s.interaction_id], s.branch) for s in p.steps
                 if s.interaction_id in graph.interactions]
        paths.append({"id": p.id, "name": p.name, "trigger": p.trigger, "endpoint": p.endpoint,
                      "description": p.description, "active_when": p.active_when, "steps": steps,
                      "uncalibrated_steps": sum(1 for s in steps if s["calibration"] == "uncalibrated"),
                      "steps_without_transition": sum(1 for s in steps if s["transition"] is None)})
    sids = {s.id for s in own}
    links = [i for i in graph.active_interactions() if i.source_id in sids or i.target_id in sids]
    mine = [x["id"] for x in [*comps, *paths, *identities, *stock_flows, *matrices]]
    problems = [p for p in validate_construction(graph) if entity_id in p or any(x in p for x in mine)]
    return {"entity_id": entity_id, "name": ent.name, "attributes": attributes, "compositions": comps,
            "identities": identities, "stock_flows": stock_flows, "matrices": matrices, "paths": paths,
            "links": {"total": len(links),
                      "sized_causal": sum(1 for i in links if i.edge_type not in FIXED_EDGE_TYPES and i.quantified),
                      "uncalibrated_causal": sum(1 for i in links if i.edge_type not in FIXED_EDGE_TYPES and not i.quantified),
                      "fixed": sum(1 for i in links if i.edge_type in FIXED_EDGE_TYPES),
                      "accounting": sum(1 for i in links if str(i.edge_type) == "accounting"),
                      "identity": sum(1 for i in links if str(i.edge_type) == "identity"),
                      "stock_flow": sum(1 for i in links if str(i.edge_type) == "stock_flow"),
                      "state_dependent": sum(1 for i in links if i.state is not None),
                      "with_transition": sum(1 for i in links if i.transition is not None)},
            "problems": problems}


def _cell(x: Any) -> str:
    s = UNKNOWN if x in (None, "", []) else ", ".join(map(str, x)) if isinstance(x, list) else str(x)
    return s.replace("|", "/").replace("\n", " ")


ROLE_TEXT = {
    "driving": "Parts add to the total on this basis only, and carry changes into it; other views of the same business "
               "overlap and are never added to it.",
    "reconciling": "A reconciling view: its parts are observed and reconciled against the total but carry nothing into "
                   "it, so it can be imported alongside the driving view without counting a change twice.",
    "non_additive": "A non-additive view: its parts overlap.",
}


def _terms_text(terms: list[dict], names: dict[str, str]) -> str:
    return "; ".join(f"{names.get(t['value'], t['value'])} ({t['role']}, "
                     f"{'missing link' if t['weight'] is None else format(t['weight'], '+.3f')})" for t in terms)


def _identity_sections(view: dict, names: dict[str, str]) -> list[str]:
    """Identities, stocks and flows, and matrices, readably (Oct 18)."""
    lines: list[str] = []
    if view["identities"]:
        lines += ["## Identities", "", "Each weight is derived from the values' levels and scales at construction "
                  "(sd of the target per sd of the term), never estimated.", "",
                  "| Identity | Formula | Terms (weight, sd/sd) | Unit check |", "|---|---|---|---|"]
        for x in view["identities"]:
            lines.append(f"| `{x['id']}` ({x['form']}) | {_cell(x['formula'])} | {_cell(_terms_text(x['terms'], names))} | "
                         f"{_cell(x['unit_check'])} |")
        lines.append("")
    if view["stock_flows"]:
        lines += ["## Stocks and flows", "", "A flow held one sd above its level adds its weight to the stock every "
                  "period: the stock accumulates it.", "", "| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |",
                  "|---|---|---|"]
        for x in view["stock_flows"]:
            lines.append(f"| `{x['id']}` | {_cell(x['formula'])} | {_cell(_terms_text(x['flows'], names))} |")
        lines.append("")
    for m in view["matrices"]:
        cells = {(c["row"], c["column"]): c["value"] for c in m["cells"]}
        rows = sorted({r for r, _ in cells})
        cols = sorted({c for _, c in cells})
        lines += [f"## Matrix `{m['id']}`: {m['rows']} x {m['columns']} (the {m['drives']} drive the total; "
                  f"{m['passive']} reconciles)", ""]
        if cells:
            lines += ["| | " + " | ".join(names.get(c, c) for c in cols) + " |", "|---|" + "---|" * len(cols)]
            for r in rows:
                lines.append(f"| {names.get(r, r)} | " + " | ".join(f"`{cells[(r, c)]}`" if (r, c) in cells else "-"
                                                                 for c in cols) + " |")
        else:
            lines.append("No cells are given: the views reconcile to the total only.")
        if m["note"]:
            lines += ["", m["note"]]
        lines.append("")
    return lines


def to_markdown(view: dict) -> str:
    """The readable view: compositions, then each path as a chain and a transition table."""
    lines = [f"# {view['name']}: business construction", ""]
    lk = view["links"]
    lines += [f"{lk['total']} links touch its values: {lk['sized_causal']} sized causal, {lk['uncalibrated_causal']} "
              f"uncalibrated causal (represented, size unknown), and {lk['fixed']} fixed by construction "
              f"({lk['accounting']} accounting, {lk['identity']} identity, {lk['stock_flow']} stock-flow; their weights are "
              f"derived, not estimated); {lk['state_dependent']} state-dependent; {lk['with_transition']} carry a "
              "transition.", ""]
    names = {a["id"]: a["name"] for a in view["attributes"]}
    if view["compositions"]:
        lines += ["## Business composition", ""]
        for c in view["compositions"]:
            lines += [f"### {c['view'].replace('_', ' ')}: {c['basis']} ({c['unit']}{', ' + c['period'] if c['period'] else ''})",
                      "", "| Part | Value |", "|---|---|"]
            for m in c["members"]:
                lines.append(f"| {names.get(m, m)} | `{m}` |")
            for label, sid in (("Residual", c["residual"]), ("Eliminations", c["eliminations"])):
                if sid:
                    lines.append(f"| {label}: {names.get(sid, sid)} | `{sid}` |")
            lines.append(f"| **Total: {names.get(c['total'], c['total'])}** | `{c['total']}` |")
            lines += ["", ROLE_TEXT[c["role"]]]
            if c["note"]:
                lines.append(c["note"])
            lines.append("")
    lines += _identity_sections(view, names)
    if view["paths"]:
        lines += ["## Operating and financial paths", ""]
    for p in view["paths"]:
        chain = " → ".join([p["steps"][0]["source_name"], *[
            (f"[{s['branch']}] " if s["branch"] else "") + s["target_name"] + ("?" if s["calibration"] == "uncalibrated" else "")
            for s in p["steps"]]]) if p["steps"] else ""
        lines += [f"### {p['name']}", "", f"**Trigger:** {p['trigger']}. **Endpoint:** {names.get(p['endpoint'], p['endpoint'])}.",
                  "", chain + ("  (? marks a step whose size is unknown)" if p["uncalibrated_steps"] else ""), ""]
        if p["description"]:
            lines += [p["description"], ""]
        if p.get("active_when"):
            lines += [f"**Dormant unless:** {p['active_when']}.", ""]
        lines += ["| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / "
                  "magnitude / timing) | Breaker | Next state | Size |", "|---|---|---|---|---|---|---|---|"]
        for k, s in enumerate(p["steps"], 1):
            tr = s["transition"] or {}
            tm, ev = tr.get("timing") or {}, tr.get("evidence") or {}
            mech = tr.get("mechanism") or f"{s['source_name']} {s['label']} {s['target_name']}"
            actor = f" ({tr['actor']})" if tr.get("actor") else ""
            cond = "; ".join(x for x in (tr.get("condition"), tr.get("condition_observable") and
                                         f"observable: {tr['condition_observable']}") if x)
            timing = f"onset {_cell(tm.get('onset'))}; build {_cell(tm.get('build'))}; persists {_cell(tm.get('persistence'))}; " \
                     f"recognized {_cell(tm.get('recognition'))}" if tm else UNKNOWN
            evid = " / ".join(_cell(ev.get(k2)) for k2 in ("existence", "direction", "magnitude", "timing")) if ev else UNKNOWN
            size = (f"{s['effect']:+.2f} sd/sd" if s["effect"] is not None else "unknown") + \
                   (f" ({s['computes_as']})" if s["computes_as"] else "") + (f"; {s['state']}" if s["state"] else "")
            lines.append(f"| {k}{' [' + s['branch'] + ']' if s['branch'] else ''} `{s['interaction_id']}` | {_cell(mech)}{actor} | "
                         f"{_cell(cond)} | {timing} | {evid} | {_cell(tr.get('breaker'))} | {_cell(tr.get('next_state'))} | {size} |")
        unresolved = sorted({f"{u['input']} ({u['status'].replace('_', ' ')})"
                             for s in p["steps"] for u in ((s["transition"] or {}).get("unresolved") or [])})
        if unresolved:
            lines += ["", "Unresolved inputs: " + "; ".join(unresolved) + "."]
        lines.append("")
    if view["problems"]:
        lines += ["## Problems", "", *[f"- {p}" for p in view["problems"]], ""]
    return "\n".join(lines)


def trace(graph: Any, start: str, entity_id: str, max_depth: int = 8, through_totals: bool = False) -> dict:
    """Follow a change in `start` through every link, calibrated or not, to the values of `entity_id`: each route
    as its steps, where it ends (a financial endpoint, or a value nothing leads on from), and what it rests on
    (uncalibrated steps, steps without a transition). For validating construction on a development the paths were not
    written for: a fluent answer is not evidence; the objects a trace runs through are.

    Endpoints are the company's composition totals, identity targets, stocks, and path endpoints. A route stops at the
    first endpoint it reaches unless `through_totals` (Oct 18): then the route up to each endpoint is kept and the walk
    goes on through it (a segment total into group profit, profit into capital), still within `max_depth` links. Each
    route lists the endpoints it `passes` before its end."""
    if start not in graph.subentities:
        raise KeyError(start)
    own = set(graph.entities[entity_id].subentity_ids) if entity_id in graph.entities else set()
    out_of: dict[str, list[Any]] = {}
    for i in graph.active_interactions():
        out_of.setdefault(i.source_id, []).append(i)
    endpoints = {c.total for c in graph.compositions.values() if c.entity_id == entity_id} | \
                {p.endpoint for p in graph.paths.values() if p.entity_id == entity_id} | \
                {x.target for x in graph.identities.values() if x.entity_id == entity_id} | \
                {x.stock for x in graph.stock_flows.values() if x.entity_id == entity_id}
    routes: list[list[Any]] = []

    def walk(v: str, route: list[Any], seen: set[str]) -> None:
        nxt = [i for i in out_of.get(v, []) if i.target_id not in seen]
        if v in endpoints and route:
            routes.append(route)
            if not through_totals:
                return
            nxt = nxt if len(route) < max_depth else []
        elif not nxt or len(route) >= max_depth:
            if route and route[-1].target_id in own:
                routes.append(route)
            return
        for i in sorted(nxt, key=lambda i: i.id):
            walk(i.target_id, route + [i], seen | {i.target_id})

    walk(start, [], {start})
    rows = []
    for r in routes:
        end = r[-1].target_id
        rows.append({"steps": [{"interaction_id": i.id, "source": i.source_id, "target": i.target_id,
                                "calibration": str(i.calibration), "edge_type": str(i.edge_type),
                                "has_transition": i.transition is not None} for i in r],
                     "ends_at": end, "reaches_endpoint": end in endpoints,
                     "passes": [i.target_id for i in r[:-1] if i.target_id in endpoints],
                     "uncalibrated_steps": [i.id for i in r if not i.quantified],
                     "steps_without_transition": [i.id for i in r if i.transition is None]})
    rows.sort(key=lambda x: (not x["reaches_endpoint"], len(x["steps"]), [s["interaction_id"] for s in x["steps"]]))
    return {"start": start, "entity_id": entity_id, "through_totals": through_totals, "routes": rows,
            "reaches_endpoint": any(x["reaches_endpoint"] for x in rows),
            "stops": sorted({x["ends_at"] for x in rows if not x["reaches_endpoint"]})}


# -- extraction keywords (Oct 18) ----------------------------------------------------------------------------------------
# The ingest gazetteer (ingest/gazetteer.py) makes the last word of a value's own phrase (its id's slot in words, or its
# name without the entity's words) a world-wide head keyword when one value of an entity ends in it. A common English
# word there ("held" from "securities held") then matches ordinary prose ("The ECB held rates").
COMMON_WORDS = frozenset(
    "held hold holds rose rise rises fell fall falls cut cuts kept keep said says made make set sets new net total other "
    "more less high low up down out over under back next last first one two all some any each per still also just only "
    "year years month months day days time times part parts end ends open close level levels change changes move moves "
    "good well better best big small large small plan plans view views case cases note notes term terms".split())


def keyword_risks(graph: Any, entity_id: str) -> list[dict]:
    """The company's values the extraction gazetteer would match on a common English word.

    Mirrors the gazetteer (axelrod_ingest/gazetteer.py): the last word of a value's own phrase (its id's slot in words,
    and its name without the entity's leading words, parentheses dropped) becomes a head keyword only when it is a word
    of more than two letters AND exactly one of the entity's values ends in it (two values with one head make no
    keyword, so nothing can match). A head keyword matches only right after the entity's name or its possessive
    ("Toyota's total"), or as the label of a short key-data line, so the warning is for values whose unique head is a
    common word (`COMMON_WORDS`)."""
    ent = graph.entities[entity_id]
    mine = set(re.findall(r"[a-z0-9]+", " ".join([ent.name, *ent.aliases]).lower()))
    owners: dict[str, set[str]] = {}
    for sid in ent.subentity_ids:
        s = graph.subentities.get(sid)
        if s is None:
            continue
        name = re.sub(r"\([^)]*\)", "", s.name.lower())
        words = re.findall(r"[a-z0-9]+", name)
        lead = 0
        while lead < len(words) - 1 and words[lead] in mine:
            lead += 1
        phrases = [sid.split(".", 1)[-1].replace("_", " ").split(), words[lead:]]
        for w in phrases:
            if len(w) > 1 and w[-1].isalpha() and len(w[-1]) > 2:
                owners.setdefault(w[-1], set()).add(sid)
    out: dict[str, set[str]] = {}
    for head in sorted(owners):
        if head in COMMON_WORDS and len(owners[head]) == 1:
            out.setdefault(next(iter(owners[head])), set()).add(head)
    return [{"value_id": sid, "name": graph.subentities[sid].name, "keywords": sorted(h)} for sid, h in sorted(out.items())]


# -- sources and citations (Oct 18)-------------------------------------------------------------------------------------
MATERIAL = ("documented", "guidance", "broker", "peer", "model")      # supports that make a claim material: it needs a citation
CLAIMS = ("existence", "direction", "magnitude", "timing")
SOURCE_FIELDS = (("document", "file"), ("kind", "kind"), ("publication_date", "publication_date"), ("period", "period"),
                 ("basis", "accounting_basis"), ("read_state", "read_state"), ("proof_limits", "proof_limits"),
                 ("location", "location"))


def _source_entries(raw: dict) -> dict[str, dict]:
    """A sources.json is {source id: {...}}, or the same under "sources" beside other keys."""
    inner = raw["sources"] if isinstance(raw.get("sources"), dict) else raw
    return {k: v for k, v in inner.items() if isinstance(v, dict)}


def load_sources(root: str | Path) -> dict:
    """Every <company>/sources.json and <company>/citations.json under `root` (local client data, never tracked).

    Returns {"catalogue": {source id: {source_id, company, document, kind, publication_date, period, basis,
    read_state, proof_limits, location}}, "citations": {interaction or value id: [{source, location, passage,
    company}]}, "companies": [folder names], "problems": [...]}. A source id defined by two companies keeps the first
    (in folder order) and is reported."""
    catalogue: dict[str, dict] = {}
    citations: dict[str, list[dict]] = {}
    problems: list[str] = []
    companies = []
    for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        src, cit = d / "sources.json", d / "citations.json"
        if not (src.exists() or cit.exists()):
            continue
        companies.append(d.name)
        for sid, s in sorted(_source_entries(json.loads(src.read_text())).items()) if src.exists() else []:
            if sid in catalogue:
                problems.append(f"source id {sid!r} is defined by {catalogue[sid]['company']} and {d.name}")
                continue
            catalogue[sid] = {"source_id": sid, "company": d.name, **{k: s.get(f) for k, f in SOURCE_FIELDS}}
        for key, refs in sorted(json.loads(cit.read_text()).items()) if cit.exists() else []:
            for r in refs or []:
                citations.setdefault(key, []).append({"source": str(r.get("source") or ""),
                                                      "location": str(r.get("location") or ""),
                                                      "passage": str(r.get("passage") or ""), "company": d.name})
    return {"catalogue": catalogue, "citations": citations, "companies": companies, "problems": problems}


def material_claims(evidence: dict | None) -> list[str]:
    """The claims of a transition's evidence whose support is material (documented, guidance, broker, model)."""
    ev = evidence or {}
    return [f"{k}: {ev[k]}" for k in CLAIMS if ev.get(k) in MATERIAL]


def evidence_refs(key: str, cited: list[str], sources: dict) -> list[dict]:
    """A link's or a value's references: each citation of `key` (its document, location, and passage), then each
    source id it names (`cited`) that no citation covers, at the document level."""
    cat = sources["catalogue"]
    refs = [{"source_id": c["source"], "document": (cat.get(c["source"]) or {}).get("document"),
             "location": c["location"] or None, "passage": c["passage"] or None}
            for c in sources["citations"].get(key, [])]
    covered = {r["source_id"] for r in refs}
    refs += [{"source_id": s, "document": (cat.get(s) or {}).get("document"), "location": None, "passage": None}
             for s in dict.fromkeys(cited) if s not in covered]
    return refs


def citation_check(links: list[tuple[str, dict | None]], values: list[str], sources: dict,
                   known: set[str] | None = None, company: str | None = None) -> dict:
    """Do the cited sources resolve, and does every material claim have a citation with a location?

    `links` are (interaction id, its transition as a dict, or None); `values` are value ids whose baselines may be
    cited. Reports the source ids that resolve to the catalogue, the ones that do not (with what cites them), the
    links whose transition makes a material claim (`material_claims`) without a citation that gives a location, and,
    when `known` (every id the model holds) is given, citation keys that name nothing in the model (of `company`'s
    citations file only, when given)."""
    cat, cites = sources["catalogue"], sources["citations"]
    resolved: set[str] = set()
    unresolved: dict[str, list[str]] = {}

    def look(sid: str, by: str) -> None:
        if sid in cat:
            resolved.add(sid)
        elif by not in unresolved.setdefault(sid, []):
            unresolved[sid].append(by)

    uncited = []
    for iid, tr in links:
        ev = (tr or {}).get("evidence") or {}
        for sid in [*(ev.get("sources") or []), *(c["source"] for c in cites.get(iid, []))]:
            look(sid, iid)
        claims = material_claims(ev)
        if claims and not any(c["location"] for c in cites.get(iid, [])):
            uncited.append({"interaction_id": iid, "claims": claims, "sources": list(ev.get("sources") or [])})
    for vid in values:
        for c in cites.get(vid, []):
            look(c["source"], vid)
    unknown = sorted(k for k, cs in cites.items() if known is not None and k not in known
                     and (company is None or any(c["company"] == company for c in cs)))
    return {"resolved": sorted(resolved),
            "unresolved": [{"source_id": s, "cited_by": by} for s, by in sorted(unresolved.items())],
            "claims_without_citation": uncited, "unknown_citation_keys": unknown,
            "cited_links": sum(1 for iid, _tr in links if cites.get(iid)),
            "cited_values": sum(1 for v in values if cites.get(v))}


def _own_links(graph: Any, entity_id: str) -> list[Any]:
    own = set(graph.entities[entity_id].subentity_ids)
    return sorted((i for i in graph.active_interactions() if i.source_id in own or i.target_id in own), key=lambda i: i.id)


def company_citations(graph: Any, entity_id: str, sources: dict) -> dict:
    """`citation_check` for one company: the links that touch its values, and its values."""
    links = [(i.id, i.transition.model_dump(mode="json") if i.transition is not None else None)
             for i in _own_links(graph, entity_id)]
    known = set(graph.interactions) | set(graph.subentities)
    return citation_check(links, sorted(graph.entities[entity_id].subentity_ids), sources, known, entity_id)


# -- inputs a transition needs (Oct 18) -----------------------------------------------------------------------------------
STATUSES = ("found_connected", "found_not_connected", "found_proxy", "not_yet_reviewed", "disclosed_not_supplied",
            "not_disclosed_in_reviewed_sources")


def input_needs(links: list[tuple[str, Any]]) -> list[dict]:
    """The inputs the links' transitions still need, one row per input and status: [{input, status, interaction_ids,
    searched, found_in}]. `links` are (interaction id, its Transition or None)."""
    rows: dict[tuple[str, str], dict] = {}
    for iid, tr in links:
        for u in (tr.unresolved if tr is not None else []):
            r = rows.setdefault((u.input, u.status), {"input": u.input, "status": u.status, "interaction_ids": [],
                                                      "searched": [], "found_in": []})
            r["interaction_ids"].append(iid)
            r["searched"] = sorted(set(r["searched"]) | set(u.searched))
            r["found_in"] = sorted(set(r["found_in"]) | set(u.found_in))
    return [rows[k] for k in sorted(rows)]


def inputs_by_status(graph: Any, entity_id: str) -> dict:
    """A company's inputs (from the links that touch its values), counted by status, with the not-yet-reviewed ones."""
    needs = input_needs([(i.id, i.transition) for i in _own_links(graph, entity_id)])
    return {"counts": {s: sum(1 for n in needs if n["status"] == s) for s in STATUSES}, "inputs": needs,
            "not_yet_reviewed": [n["input"] for n in needs if n["status"] == "not_yet_reviewed"]}


STOPWORDS = frozenset("the and for with from into onto per its their this that what which by of on in at to or as an a "
                      "is are be vs".split())
_WORD = re.compile(r"[a-z0-9][a-z0-9.%-]*")


def _words(text: str) -> list[str]:
    """Lowercased words, trailing punctuation off, a plural's final s off (a simple stem)."""
    out = []
    for w in _WORD.findall(text.lower()):
        w = w.strip(".-")
        out.append(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def query_terms(name: str, extra: list[str] | None = None) -> tuple[list[str], list[str]]:
    """An input's phrases (its name and any extra terms, lowercased) and its words (stemmed, without stopwords)."""
    phrases = list(dict.fromkeys(p.strip().lower() for p in [name, *(extra or [])] if p.strip()))
    words = list(dict.fromkeys(w for w in _words(name) if w not in STOPWORDS and len(w) > 1))
    return phrases, words


def passages(label: str, parsed: Any) -> list[tuple[str, str, str]]:
    """(file, location, text) per non-empty line of each page, sheet, or slide: a spreadsheet row, a line of a page."""
    out = []
    for seg in parsed.segments:
        where = seg.label or (f"page {seg.page}" if seg.page is not None else "text")
        for k, line in enumerate(seg.text.split("\n"), 1):
            if line.strip():
                out.append((label, f"{where}, line {k}", line.strip()))
    return out


def score_passage(text: str, phrases: list[str], words: list[str]) -> tuple[float, list[str]]:
    """A passage's score for one input: 3 per phrase it contains, plus the share of the input's words it contains.
    It is a candidate (score > 0) only if it holds a phrase, or most of the words (three in five, at least two; or the
    only one)."""
    low = text.lower()
    hit = [p for p in phrases if p in low]
    have = set(_words(text))
    got = [w for w in words if w in have]
    enough = bool(words) and len(got) >= (1 if len(words) == 1 else max(2, -(-3 * len(words) // 5)))
    if not hit and not enough:
        return 0.0, []
    return 3.0 * len(hit) + len(got) / max(1, len(words)), hit + got


def search_inputs(needs: list[dict], docs: list[tuple[str, Any]], extra: dict[str, list[str]] | None = None,
                  top: int = 5) -> list[dict]:
    """Search the parsed documents (`docs`: [(file label, Parsed)]) for each input that is not yet connected: its
    candidate passages (best first, at most `top`) and the status they suggest. Found: `found_not_connected` (a
    candidate, to confirm and bind); nothing found: `not_disclosed_in_reviewed_sources`, with what was searched.
    Deterministic: the same files and terms give the same report."""
    extra = extra or {}
    lines = [p for label, parsed in docs for p in passages(label, parsed)]
    files = list(dict.fromkeys(label for label, _p in docs))
    out = []
    for n in needs:
        if n["status"] == "found_connected":
            continue
        phrases, words = query_terms(n["input"], extra.get(n["input"]))
        cands = []
        for f, loc, text in lines:
            s, matched = score_passage(text, phrases, words)
            if s > 0:
                cands.append({"file": f, "location": loc, "score": round(s, 3), "matched": matched,
                              "passage": text[:300]})
        cands.sort(key=lambda c: (-c["score"], c["file"], c["location"]))
        found = cands[:top]
        queries = [f"corpus: {q}" for q in phrases]
        row = {**n, "queries": queries, "candidates": found, "searched_files": files}
        if found:
            row.update(suggested_status="found_not_connected", suggested_found_in=sorted({c["file"] for c in found}))
        else:
            row.update(suggested_status="not_disclosed_in_reviewed_sources", suggested_searched=[*files, *queries])
        out.append(row)
    return out


def search_markdown(entity_id: str, rows: list[dict]) -> str:
    """The input search, readable: per input, the suggested status and the candidate passages."""
    lines = [f"# {entity_id}: input search", "", "Suggestions only: no world file was changed. A candidate passage is "
             "found_not_connected until it is confirmed and bound to a value, an observation, or a citation.", ""]
    for r in rows:
        lines += [f"## {r['input']}", "", f"Now: {r['status']}. Suggested: **{r['suggested_status']}**. "
                  f"Links: {', '.join(r['interaction_ids'])}. Queries: {', '.join(r['queries'])}.", ""]
        if r["candidates"]:
            lines += ["| Score | File | Location | Passage |", "|---|---|---|---|"]
            lines += [f"| {c['score']} | {_cell(c['file'])} | {_cell(c['location'])} | {_cell(c['passage'])} |"
                      for c in r["candidates"]]
        else:
            lines.append(f"Nothing found in {len(r['searched_files'])} file(s).")
        lines.append("")
    return "\n".join(lines)
