"""The world model as an evaluation export: `axelrod.wm-export/v1`, the schema core's Mission Control defines for scoring a
world model's representation without an agent in the loop (Oct 31).

The v4.1.4 export (context/v4.py) is the client's upload layout for an answering agent. This one is for an evaluator: it
says what the model holds and how well each piece is supported, in plain semantic objects any world model could fill
(entities, variables, records, bindings, sources, relations, views, paths, assumptions, history), and it never states
more than the model knows:

- a variable's estimate is the model's posterior and says so; what it rests on is its input class (reported, derived,
  externally estimated, assumed), taken the way context/earnings.attach_repair takes it, never from `observed`, which
  is true for every constructed value;
- a record is a dated, scoped figure: a reported observation from the company's repair data (period, scope,
  availability date, page) or an observation the model folded from an import. Every record says where it came from:
  `model_state` (inside the state hash) or `attachment` (bound at export time from local files, outside it), so an
  evaluator can tell what the versioned model itself holds;
- a binding names its document by content hash and page, so it can be checked against a frozen corpus without sharing
  ids with it;
- a relation without a calibrated size has no effect, never 0; its evidence is given claim by claim (existence,
  direction, magnitude, timing);
- a path keeps every step as declared, including one whose relation is gone, so a dangling step is visible;
- what the model cannot do (supersession, undo) is declared in `capabilities`, and known gaps in `schema_gaps`.

Pure: it reads domain objects and the attachments it is given, writes nothing, sorts every list by id, and takes no clock
except the `generated_at` passed in. Document hashes are passed in too (the script computes them from local files).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

SCHEMA = "axelrod.wm-export/v1"
GENERATOR = "karthik-world-model"

CURRENCIES = (("¥", "JPY"), ("$", "USD"), ("€", "EUR"), ("£", "GBP"), ("yen", "JPY"), ("dollar", "USD"))
SCALES = (("trillion", "trillion"), ("tn", "trillion"), ("billion", "billion"), ("bn", "billion"),
          ("million", "million"), ("mn", "million"), ("m", "million"), ("thousand", "thousand"), ("k", "thousand"))
# the repair data's period types, in the export's vocabulary
PERIOD_TYPES = {"fiscal_year": "annual", "year": "annual", "calendar_year": "annual", "quarter": "quarter",
                "half": "half", "month": "month", "point": "point_in_time", "cumulative": "cumulative"}
INPUT_CLASSES = ("reported", "derived", "externally_estimated", "assumed")
EPISTEMIC_OF_CLASS = {"reported": "reported", "derived": "derived", "externally_estimated": "estimated",
                      "assumed": "assumption"}
DRIVER_KINDS = ("macro_factor", "market", "external_factor", "agency")
CAPABILITIES = {"as_of": True, "restore": True, "retire": True, "idempotent_import": True, "supersession": False,
                "undo": False}
SCHEMA_GAPS = [
    {"concept": "supersession", "reason": "not built: a restated figure does not supersede the earlier one (D-12 proposed)"},
    {"concept": "undo", "reason": "a version can be restored read-only; there is no revert-and-continue operation"},
    {"concept": "record metadata in the state",
     "reason": "period, scope, availability date and page come from local repair data bound at export time, outside "
               "the state hash (records with origin 'attachment')"},
    {"concept": "per-passage claim aspect", "reason": "evidence is split by claim only on relations, not on citations"},
]


# -- small parsers -------------------------------------------------------------------------------------------------------
def parse_unit(text: str | None) -> dict:
    """A unit string ("¥tn per quarter", "$m", "m units/yr", "pct") as unit, scale, currency, denominator and flow;
    what it does not say stays null (Oct 31: the model writes magnitude and currency into its unit strings)."""
    raw = (text or "").strip()
    low = raw.lower()
    currency = next((code for mark, code in CURRENCIES if mark in low), None)
    words = re.findall(r"[a-z]+", low)
    head = re.split(r"[/ ]", low.replace("¥", "").replace("$", "").replace("€", "").replace("£", "").strip())[0]
    scale = next((s for token, s in SCALES if head == token or (token in words and token not in ("m", "k"))), None)
    if scale is None and raw:
        scale = "unit"
    per = "share" if "/share" in low or "per share" in low else "unit" if "/unit" in low else None
    flow = "per_year" if re.search(r"/yr|per year|/year|annual", low) else \
        "per_quarter" if "quarter" in low else "per_month" if "month" in low else None
    if currency:
        unit = currency
    elif low in ("pct", "%") or "percent" in low:
        unit, scale = "percent", "unit"
    elif "pp" in words or "pts" in words:
        unit, scale = "pp", "unit"
    elif "share" in low:
        unit = "shares"
    elif "unit" in low or "vehicle" in low:
        unit = "units"
    elif low in ("x", "ratio", "times"):
        unit, scale = "ratio", "unit"
    else:
        unit = "other" if raw else None
    return {"unit": unit, "scale": scale, "currency": currency, "per": per, "flow": flow, "unit_text": raw}


def parse_date(text: str | None) -> str | None:
    """The ISO date a free-text publication date starts with ("2026-08-03 (Update Log: …)"), else null."""
    m = re.match(r"\s*(\d{4}-\d{2}-\d{2})\b", text or "")
    return m.group(1) if m else None


def short_hash(*parts: Any) -> str:
    return hashlib.sha256("|".join("" if p is None else str(p) for p in parts).encode()).hexdigest()[:16]


def consolidation(scope: dict | None, kind: str) -> dict:
    """A repair observation's free-text scope as the export's scope: the consolidation level read from its words
    (segment, region, equity method, subsidiary, consolidated), null when they do not say; the texts are kept."""
    s = scope or {}
    text = " ".join(str(s.get(k) or "") for k in ("basis", "perimeter", "view")).lower()
    view = s.get("view")
    if "equity method" in text:
        level = "equity_method"
    elif "subsidiar" in kind or "subsidiar" in text or "tmcc" in text:
        level = "subsidiary"
    elif view in ("reporting_segments", "financial_services") or "segment" in text:
        level = "segment"
    elif view in ("regions", "customer_location", "production_location") or "geographic" in text or "region" in text:
        level = "region"
    elif "consolidated" in text:
        level = "consolidated"
    else:
        level = None
    geo = {"customer_location": "customer_location", "production_location": "production_location",
           "regions": "entity_location"}.get(view or "")
    return {"consolidation": level, "geography_basis": geo, "view_text": view,
            "basis_text": s.get("basis"), "perimeter_text": s.get("perimeter")}


def epistemic_of_observation(o: dict) -> str:
    kind = str(o.get("kind") or "").lower()
    if o.get("class") == "externally_estimated" or "broker" in kind or "third party" in kind:
        return "third_party"
    if kind.startswith("reported"):
        return "reported"
    if "guidance" in kind or "forecast" in kind:
        return "guidance"
    return "unknown"


def _text(x: Any) -> str | None:
    """A free-form note as one line of text: a {class, note} resolution reads "class: note"."""
    if isinstance(x, dict):
        return "; ".join(f"{k}: {v}" for k, v in x.items()) or None
    return None if x is None else str(x)


def _iso(t: Any) -> str | None:
    return t.isoformat() if isinstance(t, datetime) else (str(t) if t else None)


def _r(x: Any) -> float | None:
    try:
        return round(float(x), 6)
    except (TypeError, ValueError):
        return None


# -- the parts ---------------------------------------------------------------------------------------------------------
class _Bindings:
    """Bindings deduplicated by content: one id per (source, document, page, location, passage)."""

    def __init__(self, catalogue: dict, document_hashes: dict[str, str]) -> None:
        self.catalogue = catalogue
        self.hashes = document_hashes
        self.rows: dict[str, dict] = {}

    def document(self, source_id: str, document: Any) -> str | None:
        """The one document a reference names: its own path, or the source's when the source has exactly one."""
        if isinstance(document, str) and document:
            return document
        cat = (self.catalogue.get(source_id) or {}).get("document")
        return cat if isinstance(cat, str) and cat else None

    def add(self, *, source_id: str, document: Any = None, location: str | None = None, passage: str | None = None,
            page: Any = None, printed_page: Any = None, aspects: list[str] | None = None,
            evidence_type: str | None = None) -> str:
        doc = self.document(source_id, document)
        bid = "b_" + short_hash(source_id, doc, page, location, passage)
        if bid not in self.rows:
            self.rows[bid] = {
                "binding_id": bid, "source_id": source_id or None,
                "document_name": PurePosixPath(doc).name if doc else None,
                "document_sha256": self.hashes.get(doc) if doc else None,
                "page": int(page) if isinstance(page, int | float) and not isinstance(page, bool) else None,
                "printed_page": None if printed_page is None else str(printed_page),
                "location_text": location or None, "passage": passage or None,
                "aspects": sorted(aspects or []), "evidence_type": evidence_type}
        return bid


def _sources(catalogue: dict, document_hashes: dict[str, str]) -> list[dict]:
    out = []
    for sid, s in sorted(catalogue.items()):
        docs = s.get("document")
        docs = [docs] if isinstance(docs, str) else [d for d in docs or [] if isinstance(d, str) and d]
        documents = [{"document_id": f"{sid}#{k}", "name": PurePosixPath(d).name, "sha256": document_hashes.get(d)}
                     for k, d in enumerate(docs)]
        out.append({"source_id": sid, "title": documents[0]["name"] if documents else None, "kind": s.get("kind"),
                    "available_at": parse_date(s.get("publication_date")),
                    "available_at_text": s.get("publication_date"), "documents": documents})
    return out


def _input_class(sid: str, sub: Any, spec: dict, reported: bool, cited: bool) -> tuple[str, str]:
    """What a value rests on, by the precedence context/earnings.attach_repair uses."""
    declared = (sub.features or {}).get("input_class")
    if spec.get("class") in INPUT_CLASSES:
        return spec["class"], spec.get("basis", "")
    if reported:
        return "reported", "a dated reported observation is attached"
    if declared in INPUT_CLASSES:
        return declared, "declared on the value in the construction"
    if cited:
        return "externally_estimated", "cited research (not a company disclosure of this value) is attached"
    return "assumed", "no reported observation and no evidence reference: a construction prior"


def _roles(graph: Any, ids: set[str]) -> dict[str, str]:
    """A variable's role in the mechanism, from the model's structure only: views and path endpoints are financial,
    path triggers and macro or market values are drivers, operating-state values and path interiors are operating
    states; a variable the structure does not place has no role (null)."""
    financial: set[str] = set()
    for c in graph.compositions.values():
        financial |= {c.total, *c.members, *(x for x in (c.residual, c.eliminations) if x)}
    financial |= {p.endpoint for p in graph.paths.values()}
    drivers = {sid for sid in ids if str(graph.entities[graph.subentities[sid].entity_id].kind) in DRIVER_KINDS}
    interior: set[str] = set()
    for p in graph.paths.values():
        nodes = []
        for st in p.steps:
            i = graph.interactions.get(st.interaction_id)
            if i is not None:
                nodes += [i.source_id, i.target_id]
        if nodes:
            drivers.add(nodes[0])
            interior |= set(nodes[1:])
    states = {sid for sid in ids if (graph.subentities[sid].features or {}).get("view") == "operating_state"}
    roles = {}
    for sid in ids:
        if sid in financial:
            roles[sid] = "financial_endpoint"
        elif sid in drivers:
            roles[sid] = "driver"
        elif sid in states or sid in interior:
            roles[sid] = "operating_state"
    return roles


def _estimate(sub: Any) -> dict:
    d = sub.posterior
    try:
        q05, q95 = _r(d.quantile(0.05)), _r(d.quantile(0.95))
    except (AttributeError, ValueError):
        q05 = q95 = None
    return {"kind": "model", "mean": _r(d.mean()), "sd": _r(d.sd()), "q05": q05, "q95": q95}


def _relation(i: Any, sid_in: set[str], non_driving: dict[str, set[str]], binds: list[str]) -> dict:
    tr = i.transition
    k = i.forward.kernel
    sized = i.quantified
    sign = tr.sign if tr is not None and tr.sign else ("+" if i.polarity() > 0 else "-")
    timing = (tr.timing.model_dump(mode="json") if tr is not None else
              {"onset": "unknown", "build": "unknown", "persistence": "unknown", "recognition": "unknown", "calendar": ""})
    timing["lag_days"] = _r(k.lag.mean()) if sized else None
    timing["delay_days"] = _r(k.delay.mean()) if sized else None
    support = ({c: getattr(tr.evidence, c) for c in ("existence", "direction", "magnitude", "timing")} if tr is not None
               else {c: "unknown" for c in ("existence", "direction", "magnitude", "timing")})
    drives = not (str(i.edge_type) == "accounting" and i.source_id in non_driving.get(i.target_id, set()))
    return {
        "relation_id": i.id, "source_variable_id": i.source_id, "target_variable_id": i.target_id,
        "type": str(i.edge_type), "label": i.label, "sign": sign, "timing": timing, "drives": drives,
        "calibration_status": str(i.calibration),
        "effect": {"mean": _r(i.forward.effect.mean()), "sd": _r(i.forward.effect.sd())} if sized else None,
        "existence_probability": _r(i.existence.mean()), "evidence_support": support, "bindings": binds,
        "mechanism": tr.mechanism if tr is not None else None,
        "condition": (tr.condition or None) if tr is not None else None,
        "breaker": (tr.breaker or None) if tr is not None else None,
        "observable": tr.observable.name if tr is not None and tr.observable is not None else None,
        "unresolved_inputs": [{"input": u.input, "status": u.status} for u in tr.unresolved] if tr is not None else [],
        "identity_id": i.identity, "status": "retired" if i.retired_at is not None else "active",
        "endpoints_exported": i.source_id in sid_in and i.target_id in sid_in, "origin": "model_state"}


def _history(versions: Iterable[Any], changes: Iterable[Any], proposals: Iterable[Any]) -> dict:
    def verbs(counts: dict[str, dict[str, int]]) -> dict[str, int]:
        out: dict[str, int] = {}
        for by_verb in counts.values():
            for verb, n in by_verb.items():
                out[verb] = out.get(verb, 0) + n
        return dict(sorted(out.items()))

    return {
        "versions": [{"version": v.version, "state_hash": v.state_hash, "recorded_at": _iso(v.recorded_at),
                      "cause": v.cause} for v in sorted(versions, key=lambda v: v.version)],
        "changes": [{"change_id": c.id, "version_after": c.version, "recorded_at": _iso(c.recorded_at), "cause": c.cause,
                     "process": c.process, "actor_kind": "person" if c.vetted_by else "system",
                     "counts": verbs(c.counts),
                     "targets": sorted({x for by_verb in c.touched.values() for ids in by_verb.values() for x in ids})}
                    for c in sorted(changes, key=lambda c: c.version)],
        "proposals": [{"proposal_id": p.id, "kind": str(p.kind), "status": str(p.status),
                       "reasons": list(p.review_reasons),
                       "decided_by_kind": None if not p.decided_by else
                       "system" if str(p.decided_by).startswith("policy:") or str(p.status) == "auto_applied" else "person"}
                      for p in sorted(proposals, key=lambda p: p.id)]}


# -- the export ----------------------------------------------------------------------------------------------------------
def wm_export(wm: Any, ltm: Any, *, world_model_id: str, label: str, version: int, state_hash: str,
              generated_at: str, entity_ids: Iterable[str] | None = None, subjects: Iterable[str] = (),
              sources: dict | None = None, repairs: Iterable[dict] = (), document_hashes: dict[str, str] | None = None,
              versions: Iterable[Any] = (), changes: Iterable[Any] = (), proposals: Iterable[Any] = (),
              scenario: dict | None = None, commit: str | None = None) -> dict:
    """The world model (`wm`, `ltm`) at `version` as an `axelrod.wm-export/v1` document; `entity_ids` narrows it to some
    entities (all by default), `sources` is context/construction.load_sources' result and `repairs` the companies'
    repair data (context/earnings.load_repair, matched on `entity`), `document_hashes` maps a document path to its sha256, and the history
    arguments are the engine's versions, commit summaries (repo/history.log) and proposals."""
    del ltm   # the taxonomy is not part of the evaluation export (concepts are the variables' kinds)
    g = wm.graph
    keep = sorted(entity_ids) if entity_ids is not None else sorted(g.entities)
    keep = [e for e in keep if e in g.entities]
    sids = sorted(sid for sid, s in g.subentities.items() if s.entity_id in keep)
    sid_in = set(sids)
    src = sources or {"catalogue": {}, "citations": {}}
    hashes = document_hashes or {}
    binds = _Bindings(src["catalogue"], hashes)
    # a repair file names the engine entity in `entity`; its `company_id` is the v4.1.4 node id
    repairs = [r for r in repairs if r.get("entity") in keep]

    # records: reported observations (attachment) and folded observations (model state)
    records: list[dict] = []
    reported_metrics: set[str] = set()
    classes: dict[str, dict] = {}
    for rep in repairs:
        classes.update(rep.get("input_classes", {}))
        for o in rep.get("observations", []):
            s = o.get("source") or {}
            b = binds.add(source_id=str(s.get("source_id") or ""), document=s.get("document"),
                          location=s.get("location") or s.get("primary_location"), passage=s.get("quote"),
                          page=s.get("page"), printed_page=s.get("printed_page"), aspects=["magnitude"],
                          evidence_type="document")
            kind = str(o.get("kind") or "")
            status = epistemic_of_observation(o)
            mid = o.get("metric_id")
            if mid and kind.startswith("reported actual"):
                reported_metrics.add(mid)
            period = o.get("period") or {}
            raw = o.get("raw") or {}
            records.append({
                "record_id": o["observation_id"], "variable_id": mid if mid in sid_in else None,
                "entity_id": rep["entity"], "metric": o.get("label") or o.get("line_id") or mid,
                "value": _r(o.get("value")), "value_state": "known" if o.get("value") is not None else "unknown",
                **{k: v for k, v in parse_unit(o.get("unit")).items()},
                "period": {"type": PERIOD_TYPES.get(str(period.get("type")), "other" if period.get("type") else None),
                           "label": period.get("label"), "start": period.get("start"), "end": period.get("end")},
                "scope": consolidation(o.get("scope"), kind.lower()), "epistemic_status": status,
                "kind_text": kind or None, "valid_at": period.get("end"), "available_at": o.get("available_at"),
                "recorded_at": None,
                "as_reported": {"value": _r(raw.get("amount")), "unit_text": raw.get("unit")} if raw else None,
                "bindings": [b], "supersedes": None, "current": True,
                "derived_from": {"operands": [], "rule": o["derived_from"]} if o.get("derived_from") else None,
                "origin": "attachment"})
    from axelrod_wm.model.distributions import from_link

    for sid in sids:
        sub = g.subentities[sid]
        unit = parse_unit(sub.unit)
        for ts in sub.history:
            if "y" not in ts.values:
                continue
            value = _r(from_link(sub.anchor + sub.scale * ts.values["y"], sub.link))
            rid = "obs_" + short_hash(sid, _iso(ts.at.valid_at), ts.source_event_id, value)
            records.append({
                "record_id": rid, "variable_id": sid, "entity_id": sub.entity_id, "metric": sub.name, "value": value,
                "value_state": "known", **unit, "period": None, "scope": None,
                # the import that carried it is not resolved here: its kind of claim is not known to the export
                "epistemic_status": "unknown", "kind_text": None, "valid_at": _iso(ts.at.valid_at),
                "available_at": None, "recorded_at": _iso(ts.at.recorded_at), "as_reported": None,
                "event_id": ts.source_event_id, "bindings": [], "supersedes": None, "current": True,
                "derived_from": None, "origin": "model_state"})

    # variables, with what each rests on
    roles = _roles(g, sid_in)
    # a value an identity or a stock-flow defines is derived from its terms by the rule the model states
    derived = {idn.target: idn for idn in g.identities.values()} | {sf.stock: sf for sf in g.stock_flows.values()}
    variables, assumptions = [], []
    for sid in sids:
        sub = g.subentities[sid]
        cited = [binds.add(source_id=c["source"], location=c["location"], passage=c["passage"],
                           evidence_type="citation") for c in src["citations"].get(sid, [])]
        spec = classes.get(sid, {})
        cls, why = _input_class(sid, sub, spec, sid in reported_metrics, bool(cited))
        feats = sub.features or {}
        calibration = "synthetic" if feats.get("prior") == "synthetic" else "proxy" if feats.get("proxy_for") else None
        idn = derived.get(sid)
        variables.append({
            "variable_id": sid, "entity_id": sub.entity_id, "name": sub.name, "concept": sub.attribute_kind,
            **parse_unit(sub.unit), "role": roles.get(sid), "input_class": cls, "input_class_basis": why or None,
            "epistemic_status": EPISTEMIC_OF_CLASS[cls], "calibration_status": calibration, "estimate": _estimate(sub),
            "derived_from": {"operands": sorted({v for v, _ in idn.terms()}), "rule": idn.formula()}
            if idn is not None else None,
            "view_text": feats.get("view") or None, "basis_text": feats.get("basis") or None,
            "bindings": sorted(set(cited)), "origin": "model_state"})
        if cls == "assumed":
            assumptions.append({"assumption_id": f"assume:{sid}", "variable_id": sid, "name": sub.name,
                                "assumed_value": _r(sub.prior.mean()), "reason": why or None,
                                "replaced_by": _text(spec.get("resolution")), "sources": []})

    # relations, views, paths
    non_driving: dict[str, set[str]] = {}
    for c in g.compositions.values():
        if not c.drives:
            non_driving.setdefault(c.total, set()).update([*c.members, *(x for x in (c.residual, c.eliminations) if x)])
    relations = []
    for i in sorted(g.interactions.values(), key=lambda x: x.id):
        if i.source_id not in sid_in and i.target_id not in sid_in:
            continue
        support = i.transition.evidence if i.transition is not None else None
        aspects = [c for c in ("existence", "direction", "magnitude", "timing")
                   if support is not None and getattr(support, c) not in ("unknown", "inferred")]
        cites = [binds.add(source_id=c["source"], location=c["location"], passage=c["passage"], aspects=aspects,
                           evidence_type="citation") for c in src["citations"].get(i.id, [])]
        covered = {c["source"] for c in src["citations"].get(i.id, [])}
        cites += [binds.add(source_id=s, aspects=aspects, evidence_type="source")
                  for s in dict.fromkeys(support.sources if support is not None else []) if s not in covered]
        relations.append(_relation(i, sid_in, non_driving, sorted(set(cites))))
    accounting_sign = {(i.source_id, i.target_id): ("+" if i.polarity() > 0 else "-")
                       for i in g.interactions.values() if str(i.edge_type) == "accounting"}
    views = []
    for c in sorted(g.compositions.values(), key=lambda c: c.id):
        if c.entity_id not in keep:
            continue
        same_total = sorted(o.id for o in g.compositions.values() if o.total == c.total and o.id != c.id)
        views.append({"view_id": c.id, "entity_id": c.entity_id, "kind": c.view, "basis_text": c.basis or None,
                      "period_text": c.period or None, "unit_text": c.unit, "total": c.total, "components": list(c.members),
                      "eliminations": [{"variable_id": c.eliminations,
                                        "sign": accounting_sign.get((c.eliminations, c.total), "unknown")}]
                      if c.eliminations else [], "residual": c.residual, "additive": c.additive, "drives": c.drives,
                      "non_additive_with": same_total})
    paths = [{"path_id": p.id, "entity_id": p.entity_id, "name": p.name, "trigger": p.trigger,
              "steps": [{"relation_id": st.interaction_id, "branch": st.branch} for st in p.steps],
              "endpoint": p.endpoint, "active_when": p.active_when or None}
             for p in sorted(g.paths.values(), key=lambda p: p.id) if p.entity_id in keep]
    entities = [{"entity_id": e.id, "kind": str(e.kind), "name": e.name, "aliases": list(e.aliases),
                 "identifiers": {}, "status": "active"} for e in (g.entities[x] for x in keep)]

    attachments = [{"name": "sources", "in_state_hash": False, "description": "source catalogue and citations"}] \
        if src["catalogue"] or src["citations"] else []
    attachments += [{"name": f"repair:{r['entity']}", "in_state_hash": False,
                     "description": f"repair data {r.get('repair_version')}: reported observations, input classes"}
                    for r in repairs]
    return {
        "schema_version": SCHEMA,
        "manifest": {"world_model_id": world_model_id, "label": label, "subjects": list(subjects),
                     "version": str(version), "state_hash": state_hash, "as_of": _iso(wm.clock),
                     "generated_at": generated_at,
                     "generator": {"name": GENERATOR, "version": _package_version(), "commit": commit},
                     "attachments": attachments, "scenario": scenario},
        "capabilities": dict(CAPABILITIES),
        "sources": _sources(src["catalogue"], hashes),
        "entities": entities,
        "variables": variables,
        "records": sorted(records, key=lambda r: r["record_id"]),
        "bindings": [binds.rows[k] for k in sorted(binds.rows)],
        "relations": relations,
        "views": views,
        "paths": paths,
        "assumptions": assumptions,
        "history": _history(versions, changes, proposals),
        "schema_gaps": [dict(x) for x in SCHEMA_GAPS],
    }


def _package_version() -> str:
    from axelrod_wm import __version__

    return __version__
