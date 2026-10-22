"""Reported facts, estimates, bridges, reconciliations and assumptions for one company's export (Toyota repair, Oct 19).

The domain pack and evidence pack from `context/v4` hold the model. This module binds a company's *local* repair data
(`<company>/repair.json`, client material that stays in the client's folder: dated observations with their sources,
management explanations, a financing bridge, input classes) to them, and adds what the repair instructions ask for:

- each value of the company carries the reported observation(s) apart from the model's current estimate, with the
  estimate's derivation and model version; `observed` is true only when a dated reported observation is attached;
- `evidence_count` counts DISTINCT SOURCE DOCUMENTS among the value's evidence references and reported observations
  (`evidence_ref_count` counts references); a value with a usable reference is never reported as having none;
- support objects in the domain pack: dated observations, evidence records, quarterly earnings bridges (each period's
  arithmetic and the year-on-year change by line), observation/estimate pairs, baseline reconciliations (before at the
  model state, after at one selected dated baseline), financing bridges, input classes (reported, derived, externally
  estimated, assumed) with the outputs that depend on assumptions, assumption records, FX channel boundaries, and the
  controlled model checks of Fixes 7 to 14 with their intermediate values;
- an earnings-quality search scope, and honest timing and hypothesis labels on the company's relationships.

Which sections a company gets. The core (values, observations, evidence records, input classes, business records, a selected
baseline with its pairs and reconciliations) is driven by the repair data's own ids and the company's construction, and every
part of it is optional: a repair file needs only `repair_version`, `entity` and `company_id`. The statement profile (quarterly
statement bridges, partial-scope measures, an operating-income walk, a financing bridge, the FX boundaries, the assumption
records and the controlled model checks) is built around one company's statements and ids; a repair file for another company that
carries one of its sections is refused by name, and `key_outputs` (the metrics whose upstream assumptions are listed) is read from
the repair data.

Every figure comes from the local repair data or from a hypothetical fixture; this module holds none. Without a
`repair.json` nothing is changed.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

from axelrod_wm.context.repair_checks import ASSUMPTIONS, completion_checks, run_checks
from axelrod_wm.model.rate_exposure import Cohort, interest_increment

REPAIR_FILE = "repair.json"
REQUIRED = ("repair_version", "entity", "company_id")
# A repair file may carry any of these sections of the statement profile: dated statement bridges, a partial-scope measure
# set, an operating-income walk, a financing bridge. Their arithmetic, the controlled model checks and the FX boundaries
# are built for one company's statements (`STATEMENT_PROFILE`); a company without that profile gets the generic core
# (its observations, evidence records, input classes, business records, baselines and reconciliations), and a repair
# file that carries a profile section for another company is refused by name instead of failing on a missing id.
STATEMENT_PROFILE = "toyota"
PROFILE_SECTIONS = ("quarter_bridges", "china_measures", "operating_income_walk", "financing_bridge")
PROFILE_KEY_OUTPUTS = ("toyota.operating_profit", "toyota.net_income", "toyota.financial_services_operating_income", "toyota.fs_income_us_scope",
                       "toyota.automotive_operating_income", "toyota.us_fin_net_interest_income", "toyota.pricing_net_op_effect",
                       "toyota.hybrid_mix_contribution")
SECTIONS = ("earnings_observations", "earnings_evidence_records", "earnings_bridges", "observation_estimate_pairs",
            "baseline_reconciliations", "financing_bridges", "input_classification", "assumption_records", "model_checks",
            "fx_boundaries", "business_records")
EVIDENCE_COUNT_DEFINITION = (
    "evidence_count is the number of DISTINCT SOURCE DOCUMENTS among the value's evidence_refs and reported observations "
    "(a document is its `document` path, or its source id when no path is given). evidence_ref_count is the number of "
    "references. The count is regenerated from the references on every export, so a value with a usable reference never "
    "reports zero. A count is not evidence quality.")
OBSERVED_DEFINITION = (
    "observed is true only when a dated reported observation (period, unit, scope, availability date, source location) is "
    "attached in `reported`. `reportable` says a source could report the value. A model estimate, an assumption or a derived "
    "value is never observed.")
CLASSES = ("reported", "derived", "externally_estimated", "assumed")


def load_repair(root: str | Path, companies: set[str] | None = None) -> list[dict]:
    """Every <company>/repair.json under `root` whose company node is among `companies` (all when None)."""
    out = []
    for d in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        f = d / REPAIR_FILE
        if f.exists():
            data = json.loads(f.read_text())
            if companies is None or data.get("company_id") in companies:
                out.append(data)
    return out


def _docs(refs: list[dict]) -> set[str]:
    """Distinct documents among references; a source made of several files (a list) counts each file."""
    out: set[str] = set()
    for r in refs:
        d = r.get("document") or r.get("source_id") or ""
        out |= set(d) if isinstance(d, list) else {d}
    return out - {""}


def _compact(o: dict) -> dict:
    return {"observation_id": o["observation_id"], "period": o["period"]["label"], "period_start": o["period"]["start"], "period_end": o["period"]["end"],
            "value": o["value"], "unit": o["unit"], "kind": o["kind"], "available_at": o["available_at"],
            "perimeter": o["scope"].get("perimeter"), "source_id": o["source"]["source_id"],
            "location": o["source"].get("primary_location") or o["source"].get("location"),
            "selected_baseline": bool(o.get("selected_baseline")), **({"sign_note": o["sign_note"]} if o.get("sign_note") else {})}


def _signals(days_dir: str | Path | None) -> dict[str, list[dict]]:
    """Signals in the imported day bundles by the value they touch (observe and move), for an estimate's derivation."""
    out: dict[str, list[dict]] = defaultdict(list)
    if not days_dir:
        return out
    for f in sorted(Path(days_dir).glob("*.json")):
        for it in json.loads(f.read_text()).get("items", []):
            for s in it.get("signals", []):
                if s.get("value_of") and s.get("type") in ("observe", "move"):
                    out[s["value_of"]].append({"day": f.stem, "item_id": it.get("id"), "type": s["type"], "value": s.get("value"),
                                               "quote": (s.get("quote") or "")[:140], "headline": (it.get("headline") or "")[:120]})
    return out


# -- reconciliation ------------------------------------------------------------------------------------------------------------------
def _sum_parts(rec: dict, lv: dict[str, float]) -> tuple[float | None, list[str]]:
    sub = set(rec["subtracted"])
    missing = [m for m in [rec["total"], *rec["parts"]] if m not in lv]
    got = [(-1 if p in sub else 1) * lv[p] for p in rec["parts"] if p in lv]
    return (sum(got) if got else None), missing


def reconcile_at(bridge: list[dict], levels: dict[str, float], label: str) -> dict[str, dict]:
    """Each composition's reconciliation at the given levels (the same arithmetic as model/construction.reconcile)."""
    out = {}
    for c in bridge:
        r = c.get("reconciliation")
        if not r or not c.get("additive", True):
            continue
        s, missing = _sum_parts(r, levels)
        tot = levels.get(r["total"])
        diff = rel = None
        if tot is not None and s is not None:
            diff = tot - s
            rel = diff / abs(tot) if tot else 0.0
        status = "blocked" if missing else ("ok" if rel is not None and abs(rel) <= r["tolerance"] else "flag")
        out[c["composition_id"]] = {"levels": label, "unit": r["unit"], "total": r["total"], "total_level": tot, "parts": r["parts"],
                                    "subtracted": r["subtracted"], "sum": s, "difference": diff, "relative_difference": rel,
                                    "missing_levels": missing, "tolerance": r["tolerance"], "status": status, "blocked_by": missing}
    return out


# -- the quarterly bridge --------------------------------------------------------------------------------------------------------------
def build_bridge(spec: dict, obs: dict[str, dict], evidence_ids: set[str]) -> dict:
    """Each period's arithmetic and the year-on-year change by line, from the observations (¥tn, rounded display left to the reader)."""
    periods = {"current": "Q1_FY3_27", "prior": "Q1_FY3_26"}
    lines = []
    for ln in spec["lines"]:
        row = {"line_id": ln["line_id"], "role": ln["role"], "sign_in_bridge": ln["sign"]}
        for p, k in periods.items():
            o = obs[f"{ln['obs']}_{k}"]
            row[p] = {"observation_id": o["observation_id"], "value": o["value"], "unit": o["unit"], "available_at": o["available_at"],
                      "source": o["source"]}
        row["change"] = round(row["current"]["value"] - row["prior"]["value"], 6)
        row["signed_change"] = round(ln["sign"] * row["change"], 6) if ln["role"] in ("add", "deduct", "start") else None
        row["explained_by"] = [e for e in ln.get("explained_by", []) if e in evidence_ids]
        if ln.get("repeatability"):
            row["repeatability"] = ln["repeatability"]
        lines.append(row)
    by = {r["line_id"]: r for r in lines}
    checks = {}
    for p in periods:
        pre = sum(by[i][p]["value"] for i in ("ty.line.operating_income", "ty.line.equity_method_income", "ty.line.other_finance_income",
                                              "ty.line.other_finance_costs", "ty.line.fx_gain_loss", "ty.line.other_income_loss"))
        ni = by["ty.line.pretax_income"][p]["value"] - by["ty.line.income_tax_expense"][p]["value"] - by["ty.line.noncontrolling_interests"][p]["value"]
        checks[p] = {"pretax_from_lines": round(pre, 6), "pretax_reported": by["ty.line.pretax_income"][p]["value"],
                     "pretax_rounding_residual": round(by["ty.line.pretax_income"][p]["value"] - pre, 6),
                     "attributable_from_pretax": round(ni, 6), "attributable_reported": by["ty.line.net_income_attributable"][p]["value"],
                     "attributable_rounding_residual": round(by["ty.line.net_income_attributable"][p]["value"] - ni, 6),
                     "note": "statement amounts are rounded to ¥1 million; residuals are at most a few ¥million and are shown, not allocated"}
    d_attr = by["ty.line.net_income_attributable"]["change"]
    parts = {i: by[i]["signed_change"] for i in ("ty.line.operating_income", "ty.line.equity_method_income", "ty.line.other_finance_income",
                                                 "ty.line.other_finance_costs", "ty.line.fx_gain_loss", "ty.line.other_income_loss",
                                                 "ty.line.income_tax_expense", "ty.line.noncontrolling_interests")}
    nonop = sum(v for k, v in parts.items() if k in ("ty.line.equity_method_income", "ty.line.other_finance_income", "ty.line.other_finance_costs",
                                                     "ty.line.fx_gain_loss", "ty.line.other_income_loss"))
    yoy = {"attributable_net_income_change": d_attr, "sum_of_line_changes": round(sum(parts.values()), 6),
           "residual": round(d_attr - sum(parts.values()), 6), "by_line": parts,
           "operating_income_change": by["ty.line.operating_income"]["change"], "non_operating_lines_change": round(nonop, 6),
           "tax_and_minorities_change": round(parts["ty.line.income_tax_expense"] + parts["ty.line.noncontrolling_interests"], 6),
           "reading": "Attributable income rose while operating income fell because the lines below operating income rose by more than operating income fell: "
                      "the statement lines above, not the deck's 'Other income' aggregate (which includes the equity-method line)."}
    return {"bridge_id": spec["bridge_id"], "company_id": None, "title": spec["title"], "periods": spec["periods"], "unit": "¥tn per quarter",
            "formula": spec["formula"], "definitions": spec["definitions"], "lines": lines, "period_arithmetic": checks, "year_on_year": yoy}


def build_china(spec: dict, obs: dict[str, dict]) -> dict:
    ms = []
    for m in spec["measures"]:
        cur, pri = obs[m["obs_current"]], obs[m["obs_prior"]]
        ms.append({**m, "current": _compact(cur), "prior": _compact(pri), "change": round(cur["value"] - pri["value"], 6), "scope": cur["scope"]})
    return {"bridge_id": spec["measure_set_id"], "company_id": None, "title": spec["title"], "kind": "china_measures", "measures": ms, "rule": spec["rule"]}


def _refs(x, obs: dict[str, dict]):
    """Observation ids inside a record, replaced by the observation (compact) so a reader needs no second lookup."""
    if isinstance(x, str) and x in obs:
        return _compact(obs[x])
    if isinstance(x, list):
        return [_refs(i, obs) for i in x]
    if isinstance(x, dict):
        return {k: _refs(v, obs) for k, v in x.items()}
    return x


def build_business(repair: dict, obs: dict[str, dict]) -> list[dict]:
    """The business records (projects, plans, classification and scope rules, the authoritative driver of an effect, a cash
    reconciliation, review notes), with observation ids resolved and the arithmetic each kind carries."""
    out = []
    for r in repair.get("business_records", []):
        rec = _refs(r, obs)
        k = r["record_kind"]
        if k == "classification":        # the part sits inside the whole in every period
            rec["check"] = [{"period": p["period"], "part": p["value"], "whole": w["value"], "part_within_whole": p["value"] <= w["value"]}
                            for p, w in zip(rec[r["part"]], rec[r["whole"]], strict=True)]
        elif k == "scopes":              # two scopes of one line: their difference, never their sum
            rec["difference"] = [{"period": a["period"], "a_minus_b": round(a["value"] - b["value"], 6), "unit": a["unit"]}
                                 for a, b in zip(rec[r["a"]], rec[r["b"]], strict=True)]
        elif k == "cash_reconciliation":
            o = rec["operands"]
            rec["derived"] = {"industrial_free_cash_flow": round(o["industrial_operating_cash_flow"]["value"] - o["capex"]["value"], 6),
                              "formula": "industrial operating cash flow - capex", "unit": o["capex"]["unit"]}
            rec["status"] = "blocked" if r.get("missing") else "ok"
            rec["roll_forward"] = ("closing eligible liquidity = opening + industrial OCF - industrial capex + identified other cash movements - cash dividends - "
                                   "executed buybacks; working capital and taxes are inside OCF and capex is not deducted twice")
        out.append(rec)
    return out


# -- the dependence of outputs on assumptions ---------------------------------------------------------------------------------------------
def _graph(pack: dict) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    fwd: dict[str, set[str]] = defaultdict(set)
    rev: dict[str, set[str]] = defaultdict(set)
    sup = pack["domain_specific_support_objects"]

    def add(a: str, b: str) -> None:
        if a and b and a != b:
            fwd[a].add(b)
            rev[b].add(a)

    for r in [*pack["company_edge_relationships"], *sup["macro_transmission_links"]]:
        ax = r["axelrod"]
        if ax.get("effect_sd_per_sd") is not None or r.get("dependency_type") == "accounting_identity":
            add(ax["source_metric"], ax["target_metric"])
    for i in sup["financial_identities"]:
        for t in i["terms"]:
            add(t["metric"], i["target_metric"])
    for c in sup["financial_bridge"]:
        if c.get("role") == "reconciling":
            continue
        for m in [*c["member_metrics"], c["residual_metric"], c["eliminations_metric"]]:
            add(m, c["total_metric"])
    return fwd, rev


def _reach(start: str, adj: dict[str, set[str]]) -> list[str]:
    seen, q = {start}, deque([start])
    while q:
        for n in adj.get(q.popleft(), ()):
            if n not in seen:
                seen.add(n)
                q.append(n)
    return sorted(seen - {start})


# -- the attachment ----------------------------------------------------------------------------------------------------------------------------
def attach_repair(ctx: dict, repair: dict, days_dir: str | Path | None = None) -> dict:
    """Bind one company's repair data to an exported context (see the module docstring); returns counts."""
    pack, ev, m = ctx["domain_pack"], ctx["evidence"], ctx["manifest"]
    sup = pack["domain_specific_support_objects"]
    missing = [k for k in REQUIRED if k not in repair]
    if missing:
        raise ValueError(f"repair data lacks {', '.join(missing)}")
    cid, ent = repair["company_id"], repair["entity"]
    profile = repair.get("profile", ent) == STATEMENT_PROFILE
    unsupported = [k for k in PROFILE_SECTIONS if k in repair] if not profile else []
    if unsupported:
        raise ValueError(f"repair data for {ent} carries {', '.join(unsupported)}, sections that only the {STATEMENT_PROFILE} "
                         f"profile builds (set `profile` to name it)")
    obs_all: list[dict] = repair.get("observations", [])
    obs = {o["observation_id"]: o for o in obs_all}
    if len(obs) != len(obs_all):
        raise ValueError("observation ids repeat")
    base = repair.get("selected_baseline")
    version = ev["state_version"]
    as_of = ev["as_of"]
    sigs = _signals(days_dir)
    by_metric: dict[str, list[dict]] = defaultdict(list)
    for o in obs_all:
        if o.get("metric_id") and o["kind"].startswith("reported actual"):
            by_metric[o["metric_id"]].append(o)
    classes = repair.get("input_classes", {})
    related = set(repair.get("related_values", []))      # values of other nodes the company's links read (a market share)
    values = {v["metric_id"]: v for v in ev["values"] if v.get("node_id") == cid or v["metric_id"] in related}

    # 1. the company's values: reported apart from estimated, counts regenerated, honest observed flag, input class
    n_reported = 0
    for mid, v in values.items():
        refs = v.get("evidence_refs", [])
        rep = by_metric.get(mid, [])
        docs = _docs(refs) | _docs([o["source"] for o in rep])
        v["link_evidence_items"] = v.get("evidence_count", 0)
        v["evidence_ref_count"] = len(refs)
        v["evidence_count"] = len(docs)
        v["reportable"] = bool(v.get("observed"))
        v["observed"] = bool(rep)
        n_reported += bool(rep)
        v["reported"] = [_compact(o) for o in sorted(rep, key=lambda o: o["period"]["end"])]
        inputs = sigs.get(mid, [])
        v["estimate"] = {"kind": "model estimate", "mean": v["mean"], "sd": v["sd"], "q05": v["q05"], "q95": v["q95"], "unit": v["unit"],
                         "as_of": as_of, "model_version": version, "state_hash": ev.get("state_hash"),
                         "prior": {"mean": v.get("prior_mean"), "sd": v.get("prior_sd"), "kind": "construction prior (synthetic), not a reported figure"},
                         "derivation": ("the construction prior updated by the imported research items that touch this value ("
                                        + "; ".join(f"{s['day']} {s['item_id']} {s['type']} {s['value'] if s['value'] is not None else ''}".strip() for s in inputs) + ") and propagated through the model's links"
                                        if inputs else "the construction prior, moved only by propagation through the model's links; no imported item observed it directly"),
                         "update_inputs": inputs}
        if rep:
            v["baseline_status"] = "reported observation attached (see reported); mean is the model estimate, not the observation"
        elif refs:
            v["baseline_status"] = "model estimate; research is cited (see evidence_refs) but no dated reported observation is attached"
        else:
            v["baseline_status"] = "model estimate; no reported observation and no evidence reference attached"

    # 2. input classes
    fwd, rev = _graph(pack)
    key_outputs = [k for k in repair.get("key_outputs", PROFILE_KEY_OUTPUTS if profile else ()) if k in values]
    cls_objs: dict[str, dict] = {}
    for mid, v in values.items():
        spec = classes.get(mid, {})
        declared = v.get("input_class_declared")
        if spec.get("class"):
            c, why = spec["class"], spec.get("basis", "")
        elif v["reported"]:
            c, why = "reported", "a dated reported observation is attached"
        elif declared in CLASSES:
            c, why = declared, "declared on the value in the construction"
        elif v.get("evidence_refs"):
            c, why = "externally_estimated", "cited research (not a company disclosure of this value) is attached"
        else:
            c, why = "assumed", "no reported observation and no evidence reference: a synthetic construction prior"
        o = {"classification_id": f"CLASS_{mid.upper().replace('.', '_')}", "company_id": cid, "metric_id": mid, "class": c, "basis": why,
             "unit": v["unit"], "evidence_count": v["evidence_count"], "observed": v["observed"]}
        for k in ("reported_counterpart", "derived_counterpart", "resolution", "evidence"):
            if k in spec:
                o[k] = spec[k]
        cls_objs[mid] = o
        v["input_class"] = c
    assumed = {k for k, o in cls_objs.items() if o["class"] == "assumed"}
    for mid, o in cls_objs.items():
        if o["class"] in ("assumed", "derived"):
            down = [x for x in _reach(mid, fwd) if x in values]
            o["outputs_depending_on_it"] = down[:40]
            o["outputs_depending_count"] = len(down)
    for mid in key_outputs:
        up = [x for x in _reach(mid, rev) if x in assumed]
        cls_objs[mid]["assumed_inputs_upstream"] = up[:60]
        cls_objs[mid]["assumed_inputs_upstream_count"] = len(up)
        values[mid]["depends_on_assumptions"] = bool(up)

    # 3. observations, evidence records, bridges
    evid = {e["evidence_id"]: e for e in repair.get("evidence_records", [])}
    evid_out = [{**e, "company_id": cid} for e in repair.get("evidence_records", [])]
    bridges = []
    for spec in repair.get("quarter_bridges", []):
        b = build_bridge(spec, obs, set(evid))
        b["company_id"] = cid
        bridges.append(b)
    for spec in repair.get("china_measures", []):
        b = build_china(spec, obs)
        b["company_id"] = cid
        bridges.append(b)
    walk = repair.get("operating_income_walk")
    if walk:
        bridges.append({"bridge_id": "ty.bridge.operating_income_walk_q1_fy3_27", "company_id": cid, "title": "Operating income change by driver, Q1 FY3/27 against Q1 FY3/26",
                        "kind": "operating_income_walk", "unit": "billion JPY", "lines": walk, "sum": round(sum(x["billion_jpy"] for x in walk), 1),
                        "source": evid["EVD_TY_Q1_OP_WALK"]["source"]})
    obs_out = [{**o, "company_id": cid, "selected_baseline": bool(o.get("selected_baseline")),
                "observed": o.get("class", "reported") == "reported", "class": o.get("class", "reported")} for o in obs_all]

    # 4. observation / estimate pairs
    pairs = []
    for mid, rep in sorted(by_metric.items() if base else ()):
        sel = [o for o in rep if o.get("selected_baseline")]
        if mid not in values or not sel:
            continue
        o, v = sel[0], values[mid]
        est = v["estimate"]
        diff = round(est["mean"] - o["value"], 6)
        pairs.append({"pair_id": f"PAIR_{mid.upper().replace('.', '_')}", "company_id": cid, "metric_id": mid, "baseline_id": base["baseline_id"],
                      "reported": _compact(o) | {"raw": o.get("raw"), "conversion": o.get("conversion"), "corroboration": o.get("corroboration"),
                                                 "bundle_ref": o.get("bundle_ref")},
                      "estimate": est, "estimate_minus_reported": diff,
                      "sign_conflict": (est["mean"] > 0) != (o["value"] > 0) and o["value"] != 0,
                      "comparability": "The reported figure is a fiscal-year actual (period above). The estimate is the model's current annual level at the as-of date; "
                                       "it is not a restatement of that actual and no transformation turns one into the other. A reported loss is never replaced by a posterior mean.",
                      "use": "calculations take the reported observation as the baseline; the estimate is shown beside it"})

    # 5. reconciliations: before (model state) and after (the selected baseline)
    levels = {o["metric_id"]: o["value"] for o in obs_all if o.get("selected_baseline") and o.get("metric_id")}
    state_lv = {k: v["mean"] for k, v in values.items() if v.get("mean") is not None}
    bridge_objs = [c for c in sup["financial_bridge"] if c["company_id"] == cid] if base else []
    after = reconcile_at(bridge_objs, levels, f"{base['baseline_id']} ({base['period']['label']}, reported actuals)") if base else {}
    recons = []
    for c in bridge_objs:
        cidn = c["composition_id"]
        r = c.get("reconciliation")
        if not r or cidn not in after:
            continue
        a = after[cidn]
        c["reconciliation_at_model_state"] = r
        c["reconciliation"] = {k: a[k] for k in ("unit", "total", "total_level", "parts", "subtracted", "sum", "difference", "relative_difference",
                                                 "missing_levels", "tolerance", "status", "blocked_by")} | {
            "levels": a["levels"], "residual": r.get("residual"), "unit_mismatches": r.get("unit_mismatches", []),
            "baseline_id": base["baseline_id"], "before_at_model_state": "reconciliation_at_model_state"}
        attrib = []
        for p in [r["total"], *r["parts"]]:
            if p in levels and p in state_lv:
                attrib.append({"metric": p, "role": "total" if p == r["total"] else "part", "model_state_level": round(state_lv[p], 6),
                               "baseline_level": levels[p], "state_minus_baseline": round(state_lv[p] - levels[p], 6),
                               "cause": ("moved by imported research: " + "; ".join(f"{s['day']} {s['item_id']} {s['type']} {s['value']}" for s in sigs[p]))
                               if sigs.get(p) else "construction prior (synthetic); the dated actual was not imported into the exported state",
                               "source": next((_compact(o)["location"] for o in obs_all if o["metric_id"] == p and o.get("selected_baseline")), None)})
        recons.append({"reconciliation_id": f"RECON_{cidn.upper().replace('.', '_')}", "company_id": cid, "composition_id": cidn, "role": c["role"],
                       "baseline_id": base["baseline_id"], "baseline_period": base["period"], "baseline_available_at": base["available_at"],
                       "before": {"levels": "model state at the as-of date (posterior means)", **{k: r.get(k) for k in ("total_level", "sum", "difference", "relative_difference", "status")}},
                       "after": {k: a[k] for k in ("levels", "total_level", "sum", "difference", "relative_difference", "status", "blocked_by")},
                       "adjustments": attrib,
                       "residual": ({"metric": r.get("residual"), "value_at_baseline": levels.get(r.get("residual")),
                                     "unexplained_difference": a["difference"], "unit": a["unit"],
                                     "derivation": "total less the signed parts at the same dated baseline; at this baseline the difference is the rounding of the reported tables",
                                     "limits": "arithmetic closure is not evidence that a residual is economically correct; none is allocated to other regions or businesses"}
                                    if a["difference"] is not None else None),
                       "overlaps_other_views": c["overlaps_other_views"],
                       "rule": "overlapping views of one total: never added to each other",
                       "qualifies": ("only calculations that use this view" if a["status"] != "ok" else None)})
    sels = sorted({x["composition_id"] for x in recons if x["after"]["status"] != "ok"})

    # 6. financing bridge with computed checks
    fb: dict | None = None
    fin_objs: list[dict] = []
    if profile:
        fin = repair["financing_bridge"]
        q = lambda oid: obs[oid]["value"]  # noqa: E731
        cur, pri = "Q1_FY3_27", "Q1_FY3_26"
        us_check = {}
        for k in (cur, pri):
            nfr = q(f"OBS_TMCC_Q_FIN_REV_{k}") - q(f"OBS_TMCC_Q_DEPR_{k}") - q(f"OBS_TMCC_Q_INTEREST_{k}")
            interest_based = q(f"OBS_TMCC_Q_RETAIL_REV_{k}") + q(f"OBS_TMCC_Q_DEALER_REV_{k}") - q(f"OBS_TMCC_Q_INTEREST_{k}")
            lease_margin = q(f"OBS_TMCC_Q_OPLEASE_REV_{k}") - q(f"OBS_TMCC_Q_DEPR_{k}")
            other = q(f"OBS_TMCC_Q_VPC_REV_{k}") + q(f"OBS_TMCC_Q_INVEST_{k}")
            exp = q(f"OBS_TMCC_Q_PROVISION_{k}") + q(f"OBS_TMCC_Q_OPADMIN_{k}") + q(f"OBS_TMCC_Q_VPC_EXP_{k}")
            us_check[k] = {"unit": "$m per quarter", "net_financing_revenues_from_lines": nfr, "net_financing_revenues_reported": q(f"OBS_TMCC_Q_NFR_{k}"),
                           "interest_based_margin (retail + dealer revenue - interest expense)": interest_based, "net_lease_margin (lease revenue - depreciation)": lease_margin,
                           "interest_based + lease = net financing revenues": interest_based + lease_margin, "other_revenues": other, "expenses": exp,
                           "pretax_from_bridge": nfr + other - exp, "pretax_reported": q(f"OBS_TMCC_Q_PRETAX_{k}"),
                           "gaap_to_ifrs_adjustment": "not disclosed: an explicit assumption (zero-centred), never a plug"}
        fx_rate = None
        fb = {**fin, "company_id": cid, "us_reported_bridge_check": us_check,
              "cohort_fixture": {"function": fin["rate_exposure"]["function"], "result_usd_bn": interest_increment([Cohort(10.0)], 1.0, 0.5),
                                 "zero_exposure_result": interest_increment([], 1.0, 0.5)},
              "group_scope": "The US scope covers the subsidiary only; the Japan and other financing scopes are unknown here, not zero. A complete US scope does not validate a global finance sensitivity.",
              "fx_note": fx_rate}
        fin_objs = [fb]

    # 7. FX boundaries and timing basis
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"] if r["company_id"] == cid}
    fxb: list[dict] = []
    if profile:
        FX = [("m29", "aggregate", "aggregate yen effect on operating income (transaction, translation of overseas profits, dearer imported inputs, euro and other currencies)",
               "the remainder of the company's total FX effect after the dollar transactional line (ty_yen_transaction), so its size already excludes that line", ["ty_yen_transaction"]),
              ("ty_yen_transaction", "aggregate component (calibrated)", "dollar transactional line of the company's walk (dollar exports net of dollar imports)",
               "re-solved on six standalone actual quarters; it nets dollar imports and exports, so the dollar-input effect (ty_yen_imports) is inside it", ["ty_yen_imports", "m29 (remainder only)"]),
              ("ty_yen_imports", "explanatory (unsized)", "dollar-priced inputs bought by Japan", "unsized to avoid adding the dollar-input effect a second time", ["ty_yen_transaction"]),
              ("ty_yen_translation", "explanatory (unsized)", "translation of North American dollar profits", "sign follows the sign of the region's profit; unsized", ["m29"])]
        for iid, mode, includes, excl, overl in FX:
            r = rels.get(iid)
            if r is None:
                continue
            ax = r["axelrod"]
            tl = (ax.get("transition") or {}).get("evidence", {}).get("timing")
            fxb.append({"boundary_id": f"FXB_{iid.upper()}", "company_id": cid, "interaction_id": iid, "relationship_id": r["relationship_id"], "role_in_calculation": mode,
                        "calibration": r.get("qualification_status"), "includes_channels": includes, "exclusions_and_netting": excl, "overlaps": overl,
                        "baseline_and_period": ax.get("note") or "see the relationship note",
                        "simulation_delay_lag_days": {"delay": ax.get("delay_days"), "lag": ax.get("lag_days"), "status": "model setting for the simulation; not evidence of shipment, hedge roll-off or recognition dates"},
                        "timing_evidence": {"documented_in_transition": tl, "recognition": ((ax.get("transition") or {}).get("timing") or {}).get("recognition")}})
        fxb.append({"boundary_id": "FXB_SELECTED_MODE", "company_id": cid, "interaction_id": None, "role_in_calculation": "selection",
                    "selected_mode": "aggregate",
                    "rule": "A calculation uses either the aggregate sensitivity with its exclusions (m29 for the remainder plus ty_yen_transaction for the dollar transactional line, which do not overlap), or a scoped component run with stated exposures that suppresses the overlapping aggregate. Component links stay explanatory and unsized. A broad branch does not justify another numerical effect.",
                    "translation": {"identity": "ty.id.us_translation", "formula": "yen trillion = 0.001 x local USD profit (billions) x period-average JPY per USD", "sign_rule": "a lower JPY per USD means yen appreciation; a loss keeps its sign, so appreciation shrinks its yen magnitude; translation is kept apart from transaction exposure"},
                    "do_not": "change a calibrated aggregate into gross export exposure without re-estimating the decomposition"})
    n_t = 0
    for iid, r in rels.items():
        ax = r["axelrod"]
        tr = ax.get("transition") or {}
        t_ev = (tr.get("evidence") or {}).get("timing")
        if ax.get("delay_days") is not None or ax.get("lag_days") is not None:
            ax["timing_basis"] = ("company timing evidence is attached to the transition" if t_ev in ("documented", "guidance", "model")
                                  else "model assumption: the simulation's delay and lag settings, not evidence of company timing or accounting recognition dates")
            n_t += 1
        if iid == f"d-{ent}-operating_profit-share_price":
            r["qualification_status"] = "uncalibrated hypothesis"
            r["status"] = "represented_uncalibrated"
            ax["calibration_note"] = ("a default link of Companies (coefficient 0.5) kept as a qualitative hypothesis; not a calibrated return estimate and not "
                                      "used for numerical stock outcomes until an explicit expectations or valuation bridge exists")
            ax["hypothesis_default_effect_sd_per_sd"] = ax.get("effect_sd_per_sd")
            ax["effect_sd_per_sd"] = None
            ax["effect_q05"] = ax["effect_q95"] = None

    # 8. assumptions and checks
    asm = [{**a, "company_id": cid, "observed": False, "class": "assumed", "assumption_id": a["assumption_id"]} for a in ASSUMPTIONS] if profile else []
    business = build_business(repair, obs)
    repair = {**repair, "business_records": business}
    checks = run_checks(pack, repair, obs, values, bridges, recons, fb, fxb) if profile else []
    checks += completion_checks(pack, repair, values, bridges, recons, fb, checks) if profile else []
    for c in checks:
        c["company_id"] = cid

    # 9. the search scope
    mf_ids = [f["metric_family_id"] for f in pack.get("metric_families", [])][:6]
    co = next(c for c in pack["companies"] if c["company_id"] == cid)
    pack["required_search_scopes"].append({
        "required_search_scope_id": f"REQ_SEARCH_EARNINGS_QUALITY_{ent.upper()}", "search_scope_label": f"{co['company_name']} earnings quality required search scope",
        "sector_pack_ids": [co["primary_sector_pack_id"]], "cluster_ids": [], "caveat_ids": [], "metric_family_ids": mf_ids,
        "why_required": "Questions about what drove a quarter's operating profit, non-operating lines or attributable net income, and which drivers repeat, need the dated statement lines, "
                        "management's explanations and the line definitions, not a macro transmission link.",
        "member_selector": {"companies": [cid], "aliases": co.get("aliases", []) + [co["company_name"]], "question_types": ["latest-quarter earnings", "attributable income against operating profit", "one-time items", "China measures", "baseline versus estimate", "reconciliation"],
                            "periods": ["latest reported quarter and its prior-year quarter", *([base["period"]["label"]] if base else [])]},
        "seed_search_targets": [f"{co['company_name']} quarterly earnings bridge", f"{co['company_name']} operating income to net income", f"{co['company_name']} other finance income",
                                f"{co['company_name']} equity-method income", f"{co['company_name']} China operating income and equity-method income"],
        "mechanisms_to_inspect": ["operating income", "equity-method income", "other finance income and costs", "foreign exchange gain (loss)", "income tax", "non-controlling interests"],
        "confirming_evidence": ["the statement line moves and management's explanation names the cause"], "breaking_evidence": ["a line moves with no stated cause, or an explanation does not map to a statement line"],
        "search_templates": ["{company} {period} operating income to net income bridge", "{company} {period} management explanation {line}", "{company} {metric} reported versus estimate"],
        "routes": {"earnings_questions": [s for s in ("earnings_observations", "earnings_evidence_records", "earnings_bridges")],
                   "baseline_questions": ["observation_estimate_pairs", "baseline_reconciliations"], "financing_questions": ["financing_bridges", "fx_boundaries"],
                   "input_questions": ["input_classification", "assumption_records", "model_checks"]},
        "search_cost_hint": "low", "freshness_window_default": "120d",
        "result_states_allowed": ["Qualified signal found", "Quiet / medium-high confidence", "No qualifying signal / low confidence", "Unavailable"]})

    # 10. write the objects. Several companies bind to one pack (a combined focus): each adds to the lists, none replaces another's.
    def put(key: str, items: list) -> None:
        sup[key] = [*sup.get(key, []), *items]

    put("earnings_observations", obs_out)
    put("earnings_evidence_records", evid_out)
    put("earnings_bridges", bridges)
    put("observation_estimate_pairs", pairs)
    put("baseline_reconciliations", recons)
    put("financing_bridges", fin_objs)
    put("input_classification", list(cls_objs.values()))
    put("assumption_records", asm)
    put("model_checks", checks)
    put("fx_boundaries", fxb)
    put("business_records", [{**r, "company_id": cid} for r in business])
    sup["schema_gaps"] = [*sup["schema_gaps"], *(g for g in SCHEMA_GAPS if g not in sup["schema_gaps"])]
    ev["evidence_count_definition"] = EVIDENCE_COUNT_DEFINITION
    ev["observed_definition"] = OBSERVED_DEFINITION
    if base:
        ev["baseline_selection"] = {**base, "rule": "A calculation names its baseline; the reported observation is the baseline, never the estimate. A zero incremental change reproduces it."}
        ev["baseline_selections"] = [*ev.get("baseline_selections", []), {"company_id": cid, **ev["baseline_selection"]}]
    ev["repair_version"] = repair["repair_version"]
    m["repair"] = {"repair_version": repair["repair_version"], "company_id": cid, "decision_date": repair.get("decision_date"), "instruction": repair.get("instruction"),
                   "as_of": as_of, "state_version": version, "selected_baseline": base["baseline_id"] if base else None,
                   "note": "Decision and as-of dates come from the instruction and the model state; the generation time above is not an observation date."}
    m["as_of"] = as_of
    m["decision_date"] = repair.get("decision_date", m.get("decision_date"))
    counts = {"values": len(values), "values_with_reported_observation": n_reported, "observations": len(obs_out), "evidence_records": len(evid_out),
              "bridges": len(bridges), "pairs": len(pairs), "reconciliations": len(recons), "reconciliations_not_ok": sels,
              "input_classes": dict(sorted(_count(o["class"] for o in cls_objs.values()).items())), "assumption_records": len(asm), "checks": len(checks),
              "fx_boundaries": len(fxb), "business_records": len(business), "timing_labelled_relationships": n_t,
              "values_zero_count_with_refs": sum(1 for v in values.values() if v["evidence_count"] == 0 and v.get("evidence_refs"))}
    m["repair"]["counts"] = counts
    m["repairs"] = [*m.get("repairs", []), m["repair"]]
    return counts


def _count(it) -> dict[str, int]:
    out: dict[str, int] = {}
    for x in it:
        out[x] = out.get(x, 0) + 1
    return out


SCHEMA_GAPS = [
    {"concept": "dated reported observation apart from the model estimate on a value", "carried_in": "evidence.values[].reported and .estimate; domain_specific_support_objects.earnings_observations", "canonical_nearest": "evidence_available"},
    {"concept": "assumption record (name, binding, scope, period, units, value, reason, affected calculation, replacement evidence)", "carried_in": "domain_specific_support_objects.assumption_records", "canonical_nearest": "do_not_infer"},
    {"concept": "a dated event instance (stage, plant, models, destinations, restart, route capacity, compatible inventory, catch-up limit, cancellations, cost)", "carried_in": "assumption_records and model_checks M07 (no event-instance object in the schema)", "canonical_nearest": "industry_caveat_definitions"},
    {"concept": "a permitted spend as the minimum of cash authorization, share authorization x price and eligible headroom", "carried_in": "model_checks M10 (the calculation forms have no minimum; the payout is stipulated and validated against the three ceilings)", "canonical_nearest": "cross_validation_assertions"},
    {"concept": "regional x business operating-income split", "carried_in": "unknown: not disclosed, so no matrix is built", "canonical_nearest": "financial_matrices"},
]
