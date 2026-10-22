"""Binding a company's repair data to an exported context (context/earnings.py, context/repair_checks.py).

Everything here is invented: a made-up company ("Acme Motor") with synthetic numbers, local files built in tmp_path.
"""

from __future__ import annotations

import copy
import json

import pytest

from axelrod_wm.context.earnings import attach_repair, load_repair
from axelrod_wm.context.repair_checks import run_checks

CID, ENT = "C_TY", "toyota"
CUR, PRI = "Q1_FY3_27", "Q1_FY3_26"
FY = {"label": "FY3/26", "type": "year", "start": "2025-04-01", "end": "2026-03-31"}
QTR = {"label": "Q1", "type": "quarter", "start": "2026-04-01", "end": "2026-06-30"}


def mkobs(oid, value, metric=None, period=FY, kind="reported actual", selected=False, perimeter="group", **extra):
    o = {"observation_id": oid, "metric_id": metric, "value": value, "unit": "u", "kind": kind, "period": period, "available_at": "2026-05-01",
         "scope": {"perimeter": perimeter}, "source": {"source_id": "S1", "document": "doc.pdf", "primary_location": "p1"}}
    if selected:
        o["selected_baseline"] = True
    return o | extra


def quarter_obs():
    cur = dict(OP=100, EQ=10, OFI=50, OFC=-5, FX=20, OTH=1, PRE=176, TAX=40, NCI=6, NI=130)
    pri = dict(OP=110, EQ=8, OFI=10, OFC=-1, FX=-20, OTH=2, PRE=109, TAX=30, NCI=4, NI=75)
    out = [mkobs(f"{k}_{CUR}", cur[k], period=QTR) for k in cur] + [mkobs(f"{k}_{PRI}", pri[k], period=QTR) for k in pri]
    tm = ("FIN_REV DEPR INTEREST RETAIL_REV DEALER_REV OPLEASE_REV VPC_REV INVEST PROVISION OPADMIN VPC_EXP NFR PRETAX").split()
    for k in (CUR, PRI):
        for i, n in enumerate(tm, 1):
            out.append(mkobs(f"OBS_TMCC_Q_{n}_{k}", float(i), period=QTR, perimeter="Toyota Motor Credit subsidiary"))
    return out


def baseline_obs():
    pairs = {"toyota.operating_profit": 100.0, "toyota.net_income": 50.0, "toyota.north_america_operating_income": 40.0,
             "toyota.japan_operating_income": 70.0, "toyota.elimination": 10.0, "toyota.automotive_operating_income": 90.0,
             "toyota.financial_services_operating_income": 10.0, "toyota.orphan_metric": 1.0}
    out = []
    for i, (mid, v) in enumerate(pairs.items()):
        extra = {"corroboration": {"matches_to_rounding": i != 1}} if i < 3 else {}
        out.append(mkobs(f"B_{i}", v, metric=mid, selected=True, **extra))
    out.append(mkobs("B_unselected", 3.0, metric="toyota.fs_income_us_scope"))          # reported, but not the selected baseline
    out.append(mkobs("B_estimate", 3.0, metric="toyota.hybrid_mix_contribution", kind="analyst estimate"))   # not a reported actual
    out.append(mkobs("B_china_cur", 41.5, period=QTR, sign_note="loss keeps its sign"))
    out.append(mkobs("B_china_pri", 30.0, period=QTR))
    out[-1]["source"] = {"source_id": "S2", "location": "p9"}                       # location rather than primary_location
    return out


def value(mid, mean=1.0, refs=(), declared=None, observed=False, count=2):
    v = {"metric_id": mid, "node_id": CID, "mean": mean, "sd": 0.1, "q05": 0.0, "q95": 2.0, "unit": "u", "evidence_refs": [{"document": d} for d in refs],
         "evidence_count": count, "observed": observed, "prior_mean": 0.5, "prior_sd": 0.2}
    if declared:
        v["input_class_declared"] = declared
    return v


def comp(cid, role, total, parts, subtracted=(), additive=True, reconciliation=True, members=None):
    c = {"composition_id": cid, "company_id": CID, "role": role, "total_metric": total, "member_metrics": members if members is not None else list(parts),
         "residual_metric": "toyota.residual", "eliminations_metric": "toyota.elimination", "overlaps_other_views": ["x"], "additive": additive}
    if reconciliation:
        c["reconciliation"] = {"unit": "u", "total": total, "parts": list(parts), "subtracted": list(subtracted), "tolerance": 0.005, "residual": "toyota.residual"}
    return c


def ident(iid, form, terms, target, coefficient=None):
    return {"identity_id": iid, "form": form, "coefficient": coefficient, "terms": [{"metric": m, "role": r} for m, r in terms], "target_metric": target}


IDENTITIES = [
    ident("ty.id.hybrid_mix_op", "product", [("toyota.hybrid_substituted_units", "factor"), ("toyota.hybrid_contribution_spread", "factor")], "toyota.hybrid_mix_contribution"),
    ident("ty.id.price_recovery_in_year", "product", [("toyota.price_recovery_annualized", "factor"), ("toyota.recovery_year_share", "factor")], "toyota.price_recovery_booked"),
    ident("ty.id.cost_recognized_in_year", "product", [("toyota.material_cost_pressure", "factor"), ("toyota.cost_recognition_weight", "factor")], "toyota.material_cost_booked"),
    ident("ty.id.pricing_net_op", "difference", [("toyota.price_recovery_booked", "total"), ("toyota.material_cost_booked", "cost")], "toyota.pricing_net_op_effect"),
    ident("ty.id.us_fin_nii", "difference", [("toyota.us_fin_interest_income", "total"), ("toyota.us_fin_interest_expense", "cost")], "toyota.us_fin_net_interest_income"),
    ident("ty.id.us_translation", "product", [("toyota.us_operations_profit_usd", "factor"), ("dollar_yen.usd_jpy", "factor")], "toyota.us_translated", 0.001),
    ident("ty.id.us_duty_avoided", "product", [("toyota.localized_customs_value", "factor"), ("us_vehicle_tariffs.effective_rate", "factor")], "toyota.duty_avoided", 0.01),
]


def rel(iid, company=CID, source="a", target="b", effect=None, dep=None, delay=None, lag=None, timing=None, status="calibrated", note="n", transition=True):
    ax = {"interaction_id": iid, "source_metric": source, "target_metric": target, "effect_sd_per_sd": effect, "delay_days": delay, "lag_days": lag,
          "effect_q05": -1, "effect_q95": 1}
    if note:
        ax["note"] = note
    if transition:
        ax["transition"] = {"sign": "+", "evidence": {"timing": timing}, "timing": {"recognition": "booked"}}
    r = {"company_id": company, "relationship_id": f"REL_{iid}", "qualification_status": status, "axelrod": ax}
    if dep:
        r["dependency_type"] = dep
    return r


def build():
    values = [
        value("toyota.operating_profit", refs=["doc.pdf"], observed=True),
        value("toyota.net_income", mean=-5.0, refs=["doc.pdf", "doc.pdf"]),
        value("toyota.north_america_operating_income"),
        value("toyota.japan_operating_income", refs=["j.pdf"]),
        value("toyota.elimination", count=0),
        value("toyota.automotive_operating_income", declared="derived"),
        value("toyota.financial_services_operating_income"),
        value("toyota.fs_income_us_scope", refs=["f.pdf"]),
        value("toyota.hybrid_mix_contribution", declared="derived"),
        value("toyota.us_fin_net_interest_income", refs=["u.pdf"]),
        value("toyota.pricing_net_op_effect", declared="bogus"),
        value("toyota.residual"),
    ]
    values.append({**value("other.metric"), "node_id": "C_OTHER"})
    sup = {
        "macro_transmission_links": [
            {"axelrod": {"source_metric": "toyota.residual", "target_metric": "toyota.automotive_operating_income", "effect_sd_per_sd": 0.5}},
            {"axelrod": {"source_metric": "toyota.residual", "target_metric": "toyota.financial_services_operating_income", "effect_sd_per_sd": 0.5}}],
        "financial_identities": copy.deepcopy(IDENTITIES),
        "financial_bridge": [
            comp("ty.comp.regional_operating_income", "primary", "toyota.operating_profit",
                 ["toyota.north_america_operating_income", "toyota.japan_operating_income", "toyota.elimination"], subtracted=["toyota.elimination"]),
            comp("ty.comp.reporting_segments", "alternate", "toyota.operating_profit",
                 ["toyota.automotive_operating_income", "toyota.financial_services_operating_income"]),
            comp("ty.comp.blocked", "alternate", "toyota.net_income", ["toyota.never_observed"]),
            {**comp("ty.comp.no_reconciliation", "alternate", "toyota.net_income", [], reconciliation=False), "residual_metric": None},
            comp("ty.comp.not_additive", "alternate", "toyota.net_income", ["toyota.japan_operating_income"], additive=False),
            comp("ty.comp.reconciling", "reconciling", "toyota.net_income", [], reconciliation=False, members=["m"]),
            {**comp("ty.comp.foreign", "primary", "z", []), "company_id": "C_OTHER"},
        ],
        "schema_gaps": [{"concept": "existing"}],
    }
    pack = {
        "companies": [{"company_id": CID, "company_name": "Acme Motor", "primary_sector_pack_id": "SP1", "aliases": ["Acme"]},
                      {"company_id": "C_OTHER", "company_name": "Other", "primary_sector_pack_id": "SP2"}],
        "metric_families": [{"metric_family_id": f"MF{i}"} for i in range(8)],
        "required_search_scopes": [],
        "company_edge_relationships": [
            rel("ty_jv_units_equity", target="toyota.equity_method_income"), rel("ty_hybrid_mix_auto_oi", target="toyota.automotive_operating_income"),
            rel("ty_transfer_support_na"), rel("ty_transfer_support_japan"),
            rel("m29", delay=5, timing="documented"), rel("ty_yen_transaction", delay=1, lag=2, timing="none", note=None),
            rel("ty_yen_imports", lag=3, timing="model", transition=False), rel("unlisted_fx", delay=None, lag=None),
            rel(f"d-{ENT}-operating_profit-share_price", effect=0.5, status="calibrated"),
            rel("acct", dep="accounting_identity", source="toyota.automotive_operating_income", target="toyota.operating_profit"),
            rel("noeffect", dep="other", source="x", target="y"),
            rel("acct2", dep="accounting_identity", source="toyota.hybrid_mix_contribution", target="toyota.automotive_operating_income"),
            {**rel("ty_yen_translation", company="C_OTHER"), },
        ],
        "domain_specific_support_objects": sup,
    }
    ev = {"state_version": "v1", "as_of": "2026-10-01", "state_hash": "h", "values": values}
    repair = {
        "company_id": CID, "entity": ENT, "repair_version": "R1", "decision_date": "2026-10-02", "instruction": "do it",
        "observations": quarter_obs() + baseline_obs(),
        "selected_baseline": {"baseline_id": "BASE", "period": FY, "available_at": "2026-05-01"},
        "input_classes": {"toyota.north_america_operating_income": {"class": "externally_estimated", "basis": "b", "resolution": "r"}},
        "evidence_records": [{"evidence_id": "E1", "source": "src"}, {"evidence_id": "EVD_TY_Q1_OP_WALK", "source": "walk-src"}],
        "quarter_bridges": [{"bridge_id": "qb", "title": "t", "periods": {}, "formula": "f", "definitions": "d", "lines": [
            {"line_id": i, "role": r, "sign": s, "obs": k, "explained_by": ["E1", "E9"], **({"repeatability": "once"} if k == "OTH" else {})}
            for i, r, s, k in [("ty.line.operating_income", "start", 1, "OP"), ("ty.line.equity_method_income", "add", 1, "EQ"),
                               ("ty.line.other_finance_income", "add", 1, "OFI"), ("ty.line.other_finance_costs", "add", 1, "OFC"),
                               ("ty.line.fx_gain_loss", "add", 1, "FX"), ("ty.line.other_income_loss", "add", 1, "OTH"),
                               ("ty.line.pretax_income", "subtotal", 1, "PRE"), ("ty.line.income_tax_expense", "deduct", -1, "TAX"),
                               ("ty.line.noncontrolling_interests", "deduct", -1, "NCI"), ("ty.line.net_income_attributable", "result", 1, "NI")]]}],
        "china_measures": [{"measure_set_id": "cm", "title": "China", "rule": "r", "measures": [{"obs_current": "B_china_cur", "obs_prior": "B_china_pri", "name": "m"}]}],
        "operating_income_walk": [{"driver": "fx", "billion_jpy": 1.25}, {"driver": "price", "billion_jpy": -0.5}],
        "financing_bridge": {"rate_exposure": {"function": "interest_increment"}, "endpoint_policy": {"treatment": "blocked"}},
    }
    return {"domain_pack": pack, "evidence": ev, "manifest": {}}, repair


@pytest.fixture
def days(tmp_path):
    d = tmp_path / "days"
    d.mkdir()
    items = [{"id": "I1", "headline": "h" * 200, "signals": [
        {"value_of": "toyota.operating_profit", "type": "observe", "value": 3.0, "quote": "q" * 300},
        {"value_of": "toyota.operating_profit", "type": "move", "value": None},
        {"value_of": "toyota.japan_operating_income", "type": "narrate"},
        {"type": "observe"}]}, {"id": "I2"}]
    (d / "2026-09-30.json").write_text(json.dumps({"items": items}))
    (d / "2026-10-01.json").write_text(json.dumps({}))
    return d


def test_attach_binds_reported_apart_from_estimated_and_counts_documents(days):
    ctx, repair = build()
    counts = attach_repair(ctx, repair, days)
    vals = {v["metric_id"]: v for v in ctx["evidence"]["values"]}
    op, ni, na = vals["toyota.operating_profit"], vals["toyota.net_income"], vals["toyota.north_america_operating_income"]
    assert op["observed"] and op["reportable"] and op["evidence_count"] == 1 and op["evidence_ref_count"] == 1 and op["link_evidence_items"] == 2
    assert "imported research items" in op["estimate"]["derivation"] and len(op["estimate"]["update_inputs"]) == 2
    assert op["baseline_status"].startswith("reported observation")
    assert vals["toyota.us_fin_net_interest_income"]["baseline_status"].startswith("model estimate; research is cited")
    assert vals["toyota.residual"]["baseline_status"].startswith("model estimate; no reported")
    assert "no imported item observed" in vals["toyota.residual"]["estimate"]["derivation"]
    assert ni["evidence_count"] == 1 and ni["evidence_ref_count"] == 2 and na["evidence_count"] == 1
    assert "other.metric" not in counts["input_classes"]
    assert counts["values"] == 12 and counts["values_with_reported_observation"] == 8 and counts["bridges"] == 3
    assert counts["values_zero_count_with_refs"] == 0 and counts["timing_labelled_relationships"] == 3


def test_input_classes_and_their_dependents():
    ctx, repair = build()
    attach_repair(ctx, repair)
    cls = {o["metric_id"]: o for o in ctx["domain_pack"]["domain_specific_support_objects"]["input_classification"]}
    assert cls["toyota.north_america_operating_income"]["class"] == "externally_estimated" and cls["toyota.north_america_operating_income"]["resolution"] == "r"
    assert cls["toyota.operating_profit"]["class"] == "reported"
    assert cls["toyota.hybrid_mix_contribution"]["class"] == "derived"
    assert cls["toyota.us_fin_net_interest_income"]["class"] == "externally_estimated"
    assert cls["toyota.residual"]["class"] == "assumed"
    assert cls["toyota.pricing_net_op_effect"]["class"] == "assumed"
    assert cls["toyota.hybrid_mix_contribution"]["outputs_depending_on_it"] == ["toyota.automotive_operating_income", "toyota.operating_profit"]
    assert "toyota.residual" in cls["toyota.operating_profit"]["assumed_inputs_upstream"]
    vals = {v["metric_id"]: v for v in ctx["evidence"]["values"]}
    assert vals["toyota.operating_profit"]["depends_on_assumptions"] is True and vals["toyota.operating_profit"]["input_class"] == "reported"


def test_pairs_reconciliations_bridges_and_search_scope():
    ctx, repair = build()
    counts = attach_repair(ctx, repair)
    sup = ctx["domain_pack"]["domain_specific_support_objects"]
    pairs = {p["metric_id"]: p for p in sup["observation_estimate_pairs"]}
    assert set(pairs) == {"toyota.operating_profit", "toyota.net_income", "toyota.north_america_operating_income", "toyota.japan_operating_income",
                          "toyota.elimination", "toyota.automotive_operating_income", "toyota.financial_services_operating_income"}
    assert pairs["toyota.net_income"]["sign_conflict"] is True and pairs["toyota.operating_profit"]["sign_conflict"] is False
    recons = {r["composition_id"]: r for r in sup["baseline_reconciliations"]}
    assert set(recons) == {"ty.comp.regional_operating_income", "ty.comp.reporting_segments", "ty.comp.blocked"}
    assert recons["ty.comp.regional_operating_income"]["after"]["status"] == "ok" and recons["ty.comp.regional_operating_income"]["qualifies"] is None
    assert recons["ty.comp.blocked"]["after"]["status"] == "blocked" and recons["ty.comp.blocked"]["residual"] is None and recons["ty.comp.blocked"]["qualifies"]
    adj = {a["metric"]: a for a in recons["ty.comp.regional_operating_income"]["adjustments"]}
    assert adj["toyota.operating_profit"]["cause"].startswith("construction prior") and adj["toyota.operating_profit"]["source"] == "p1"
    assert counts["reconciliations_not_ok"] == ["ty.comp.blocked"]
    kinds = {b["bridge_id"]: b for b in sup["earnings_bridges"]}
    assert set(kinds) == {"qb", "cm", "ty.bridge.operating_income_walk_q1_fy3_27"} and kinds["ty.bridge.operating_income_walk_q1_fy3_27"]["sum"] == 0.8
    assert sup["earnings_bridges"][0]["lines"][5]["repeatability"] == "once"
    assert kinds["cm"]["measures"][0]["current"]["sign_note"] == "loss keeps its sign" and kinds["cm"]["measures"][0]["prior"]["location"] == "p9"
    fin = sup["financing_bridges"][0]
    assert fin["cohort_fixture"]["result_usd_bn"] == pytest.approx(0.05) and fin["cohort_fixture"]["zero_exposure_result"] == 0.0
    assert fin["us_reported_bridge_check"][CUR]["net_financing_revenues_from_lines"] == 1.0 - 2.0 - 3.0
    scope = ctx["domain_pack"]["required_search_scopes"][0]
    assert scope["required_search_scope_id"] == "REQ_SEARCH_EARNINGS_QUALITY_TOYOTA" and scope["metric_family_ids"] == [f"MF{i}" for i in range(6)]
    assert scope["member_selector"]["aliases"] == ["Acme", "Acme Motor"]
    assert ctx["manifest"]["repair"]["counts"] == counts and ctx["manifest"]["decision_date"] == "2026-10-02"
    assert sup["schema_gaps"][0] == {"concept": "existing"} and len(sup["schema_gaps"]) == 6


def test_fx_boundaries_and_timing_labels():
    ctx, repair = build()
    attach_repair(ctx, repair)
    pack = ctx["domain_pack"]
    fxb = {b["boundary_id"]: b for b in pack["domain_specific_support_objects"]["fx_boundaries"]}
    assert set(fxb) == {"FXB_M29", "FXB_TY_YEN_TRANSACTION", "FXB_TY_YEN_IMPORTS", "FXB_SELECTED_MODE"}
    assert fxb["FXB_TY_YEN_TRANSACTION"]["baseline_and_period"] == "see the relationship note"
    assert fxb["FXB_TY_YEN_IMPORTS"]["timing_evidence"]["recognition"] is None
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["m29"]["axelrod"]["timing_basis"].startswith("company timing evidence")
    assert rels["ty_yen_transaction"]["axelrod"]["timing_basis"].startswith("model assumption")
    assert "timing_basis" not in rels["unlisted_fx"]["axelrod"]
    hyp = rels[f"d-{ENT}-operating_profit-share_price"]
    assert hyp["qualification_status"] == "uncalibrated hypothesis" and hyp["axelrod"]["effect_sd_per_sd"] is None
    assert hyp["axelrod"]["hypothesis_default_effect_sd_per_sd"] == 0.5


def test_the_controlled_checks_all_run_and_pass():
    ctx, repair = build()
    attach_repair(ctx, repair)
    checks = {c["check_id"]: c for c in ctx["domain_pack"]["domain_specific_support_objects"]["model_checks"]}
    earlier = ["MC1", "MC2", "MC3", "MC4", "M07", "M08", "M09", "M10"]
    assert list(checks) == [*earlier, "C01", "C02", "C03", "C04", "C05", "C06"]
    assert all(checks[k]["status"] == "run" and checks[k]["passes"] and checks[k]["company_id"] == CID for k in earlier), {k: c["passes"] for k, c in checks.items()}
    assert checks["MC1"]["results"]["mismatches_with_the_primary_summary"] == ["toyota.net_income"]
    assert checks["M10"]["results"]["op_to_share_price_default"].startswith("uncalibrated hypothesis")


def test_without_a_walk_without_signals_and_with_a_duplicate_id():
    ctx, repair = build()
    del repair["operating_income_walk"]
    del repair["input_classes"]
    attach_repair(ctx, repair, None)
    assert len(ctx["domain_pack"]["domain_specific_support_objects"]["earnings_bridges"]) == 2
    ctx, repair = build()
    repair["observations"].append(copy.deepcopy(repair["observations"][0]))
    with pytest.raises(ValueError, match="repeat"):
        attach_repair(ctx, repair)


def test_checks_degrade_when_the_inputs_are_missing():
    ctx, repair = build()
    pack = ctx["domain_pack"]
    pack["company_edge_relationships"] = []
    checks = {c["check_id"]: c for c in run_checks(pack, repair, {}, {}, [], [], {"endpoint_policy": {"treatment": "t"}, "cohort_fixture": {"result_usd_bn": 0.05}}, [])}
    assert checks["MC1"]["status"] == "blocked" and not checks["MC1"]["passes"]
    assert not checks["MC2"]["passes"] and checks["M08"]["results"]["affiliate_accounts"] is None
    assert checks["M09"]["results"]["internal_support_net_effect_on_group_op"] is None
    assert checks["M10"]["results"]["op_to_share_price_default"] == "see relationship"


def test_load_repair_reads_only_the_named_companies(tmp_path):
    for name, cid in (("a", "C_A"), ("b", "C_B")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "repair.json").write_text(json.dumps({"company_id": cid}))
    (tmp_path / "empty").mkdir()
    (tmp_path / "loose.txt").write_text("x")
    assert [r["company_id"] for r in load_repair(tmp_path)] == ["C_A", "C_B"]
    assert [r["company_id"] for r in load_repair(tmp_path, {"C_B"})] == ["C_B"]
    assert load_repair(tmp_path, set()) == []


# -- a second synthetic company, whose repair data has none of the statement profile's sections ("Borealis Ferries") -------------------------
BO, BO_ENT = "C_BO", "borealis"


def generic():
    """An export context and repair data for a company that is not the statement profile's: observations, input classes
    and a business record only."""
    values = [{**value(f"borealis.{m}", refs=["bo.pdf"] if m == "revenue" else (), declared="derived" if m == "profit" else None), "node_id": BO}
              for m in ("revenue", "cost", "profit")]
    comp_obj = {"composition_id": "bo.comp", "company_id": BO, "role": "primary", "total_metric": "borealis.profit", "member_metrics": ["borealis.revenue", "borealis.cost"],
                "residual_metric": None, "eliminations_metric": None, "overlaps_other_views": [], "additive": True,
                "reconciliation": {"unit": "u", "total": "borealis.profit", "parts": ["borealis.revenue", "borealis.cost"], "subtracted": ["borealis.cost"],
                                   "tolerance": 0.005, "residual": None}}
    pack = {"companies": [{"company_id": BO, "company_name": "Borealis Ferries", "primary_sector_pack_id": "SP9"}],
            "metric_families": [], "required_search_scopes": [], "company_edge_relationships": [
                rel("bo_fuel", company=BO, delay=3, timing="none"), rel("bo_tourism", company=BO, delay=None, lag=None)],
            "domain_specific_support_objects": {"macro_transmission_links": [], "financial_identities": [], "financial_bridge": [comp_obj],
                                                "schema_gaps": []}}
    ev = {"state_version": "v2", "as_of": "2026-10-01", "state_hash": "h", "values": values}
    obs = [mkobs("BO_REV", 10.0, metric="borealis.revenue", selected=True), mkobs("BO_COST", 6.0, metric="borealis.cost", selected=True),
           mkobs("BO_PROFIT", 4.0, metric="borealis.profit", selected=True)]
    repair = {"company_id": BO, "entity": BO_ENT, "repair_version": "B1", "observations": obs,
              "selected_baseline": {"baseline_id": "BBASE", "period": FY, "available_at": "2026-05-01"},
              "key_outputs": ["borealis.profit", "borealis.not_in_the_export"],
              "input_classes": {"borealis.cost": {"class": "assumed", "basis": "b"}},
              "business_records": [{"record_id": "PRJ_BO_1", "record_kind": "project", "stage": "planned"}]}
    return {"domain_pack": pack, "evidence": ev, "manifest": {"decision_date": "kept"}}, repair


def test_a_company_outside_the_statement_profile_gets_the_generic_core():
    ctx, repair = generic()
    counts = attach_repair(ctx, repair)
    sup = ctx["domain_pack"]["domain_specific_support_objects"]
    assert counts["values"] == 3 and counts["values_with_reported_observation"] == 3 and counts["observations"] == 3
    assert (counts["bridges"], counts["checks"], counts["assumption_records"], counts["fx_boundaries"]) == (0, 0, 0, 0)
    assert sup["earnings_bridges"] == sup["financing_bridges"] == sup["fx_boundaries"] == sup["model_checks"] == sup["assumption_records"] == []
    assert [b["record_id"] for b in sup["business_records"]] == ["PRJ_BO_1"] and sup["business_records"][0]["company_id"] == BO
    (recon,) = sup["baseline_reconciliations"]
    assert recon["after"]["status"] == "ok" and recon["baseline_id"] == "BBASE"
    assert {p["metric_id"] for p in sup["observation_estimate_pairs"]} == {"borealis.revenue", "borealis.cost", "borealis.profit"}
    cls = {o["metric_id"]: o for o in sup["input_classification"]}
    assert cls["borealis.cost"]["class"] == "assumed" and cls["borealis.profit"]["class"] == "reported"
    vals = {v["metric_id"]: v for v in ctx["evidence"]["values"]}
    assert vals["borealis.profit"]["depends_on_assumptions"] is True and "depends_on_assumptions" not in vals["borealis.revenue"]
    assert ctx["domain_pack"]["required_search_scopes"][0]["required_search_scope_id"] == "REQ_SEARCH_EARNINGS_QUALITY_BOREALIS"
    assert ctx["evidence"]["baseline_selection"]["baseline_id"] == "BBASE" and ctx["manifest"]["repair"]["selected_baseline"] == "BBASE"
    rels = {r["axelrod"]["interaction_id"]: r for r in ctx["domain_pack"]["company_edge_relationships"]}
    assert rels["bo_fuel"]["axelrod"]["timing_basis"].startswith("model assumption") and "timing_basis" not in rels["bo_tourism"]["axelrod"]


def test_repair_data_that_has_no_observations_or_baseline_is_attached_as_it_is():
    ctx, repair = generic()
    bare = {k: repair[k] for k in ("company_id", "entity", "repair_version")} | {"business_records": repair["business_records"]}
    counts = attach_repair(ctx, bare)
    sup = ctx["domain_pack"]["domain_specific_support_objects"]
    assert counts["observations"] == 0 and counts["pairs"] == 0 and counts["reconciliations"] == 0 and counts["values_with_reported_observation"] == 0
    assert sup["baseline_reconciliations"] == [] and sup["earnings_observations"] == [] and "baseline_selection" not in ctx["evidence"]
    assert ctx["manifest"]["repair"]["selected_baseline"] is None and ctx["manifest"]["repair"]["decision_date"] is None
    assert ctx["manifest"]["decision_date"] == "kept"                      # the manifest's own date stands when the data has none
    assert ctx["domain_pack"]["required_search_scopes"][0]["member_selector"]["periods"] == ["latest reported quarter and its prior-year quarter"]
    assert {c["input_class"] for c in ctx["evidence"]["values"]} == {"assumed", "derived", "externally_estimated"}


def test_a_profile_section_for_another_company_is_refused_by_name():
    ctx, repair = generic()
    with pytest.raises(ValueError, match="carries quarter_bridges, financing_bridge, sections that only the toyota profile builds"):
        attach_repair(ctx, {**repair, "quarter_bridges": [], "financing_bridge": {}})
    with pytest.raises(ValueError, match="lacks repair_version, entity"):
        attach_repair(ctx, {"company_id": BO})
    full, full_repair = build()
    with pytest.raises(ValueError, match="china_measures"):
        attach_repair(full, {**full_repair, "profile": "another"})           # naming another profile turns the statement sections off


def test_load_repair_skips_a_file_without_a_company(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "repair.json").write_text(json.dumps({"entity": "x"}))
    assert load_repair(tmp_path) == [{"entity": "x"}] and load_repair(tmp_path, {"C_X"}) == []
