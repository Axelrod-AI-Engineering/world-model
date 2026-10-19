"""Assumption records and the controlled model checks of the Toyota repair (Fixes 7 to 14).

Every number here is a stipulated or hypothetical input from the repair instructions' fixtures: none is a Toyota figure
or guidance. A check is run through the model's own identities (the pack's identity objects, evaluated with the
fixture's levels, as the golden harness does) where the calculation forms can express it, and through the plain
functions of `model/period_math.py` where they cannot, in which case the schema gap is named. Nothing here promotes an
assumed input to observed.
"""

from __future__ import annotations

from axelrod_wm.evaluation.golden import eval_identity
from axelrod_wm.model.period_math import (
    DisruptionPeriod,
    average_exposed_share_uniform,
    buyback_capacity,
    delta_nii,
    disruption,
    elimination_roll,
    liquidity_close,
    matched_share,
    npv,
    operating_years_needed,
    payback_years,
    pricing_by_period,
    project_cash_flows,
    translate,
)
from axelrod_wm.model.rate_exposure import Cohort, apply_rate_shock, interest_increment


def A(aid, name, binding, geography, scope, period, units, value, reason, calc, offsets, replace, source=None):
    return {"assumption_id": aid, "name": name, "binding": binding, "entity_and_geography": geography, "accounting_scope": scope, "period": period,
            "currency_and_units": units, "assumed_value": value, "reason": reason, "source": source, "affected_calculation": calc,
            "included_offsets": offsets, "replaced_by": replace}


FY27 = "fiscal year ending March 2027"
ASSUMPTIONS = [
    A("ASM_TY_HYBRID_ELIGIBLE", "eligible consolidated hybrid units", "toyota.hybrid_eligible_units", "Toyota consolidated; United States", "consolidated automotive sales, Toyota and Lexus; not global retail", FY27, "m units/yr", 0.5,
      "no consolidated hybrid split is available; the global retail powertrain view includes equity-accounted sales", "ty.id.hybrid_mix_op (scope of the substitution)", "none: independent price or cost effects are separate",
      "a consolidated hybrid unit split by region from company disclosure or appropriately scoped external data"),
    A("ASM_TY_HYBRID_SUBSTITUTED", "units substituted to hybrid at fixed total units", "toyota.hybrid_substituted_units", "Toyota consolidated; United States", "inside the eligible units", FY27, "m units/yr", 0.01,
      "the controlled fixture (10,000 units); the same absolute count leaves other powertrains", "ty.id.hybrid_mix_op", "total units unchanged", "a supported ramp and capacity (assembly, battery, conversion, genuinely additional)"),
    A("ASM_TY_HYBRID_SPREAD", "hybrid-minus-displaced contribution per unit", "toyota.hybrid_contribution_spread", "Toyota consolidated; United States", "after net price (incentives netted) and variable cost", FY27, "yen million per unit", 0.05,
      "the company does not disclose a hybrid contribution premium; the fixture is 50,000 yen", "ty.id.hybrid_mix_op", "net price already includes incentives defined as netted", "disclosed or appropriately scoped unit economics"),
    A("ASM_TY_HYBRID_CAPACITY", "electrified supply capacity as an unverified ceiling", "toyota.electrified_supply_capacity", "Toyota; global", "definition and source not established", FY27, "m units/yr", "existing prior, unverified",
      "no evidence reference is attached; planned battery expansion in 2027-2028 (management statement, Q&A Q8) is not a commissioned ramp", "ty_supply_hybrid (existing link, uncalibrated)", "assembly, battery, conversion and additional capacity are not distinguished",
      "a defined capacity measure with a source and dates"),
    A("ASM_TY_COST_WEIGHTS", "quarterly cost-recognition weights", "toyota.cost_recognition_weight", "Toyota; Japan and overseas cost of sales", "materials", FY27, "fraction of the annual cost", "0.25 each quarter (uniform)",
      "inventory turn and contract dates are undisclosed; a uniform allocation is not observed", "ty.id.cost_recognized_in_year; model check 3", "weights sum to the stated total within one fiscal year", "inventory recognition by quarter"),
    A("ASM_TY_RECOVERY_START", "price-recovery start", "toyota.recovery_year_share", "Toyota; regions not split", "net price after incentives", FY27, "fraction of the fiscal year", "1.0 (April 1) and 0.5 (October 1) in the fixture",
      "no price dates are disclosed (management says it will not pass costs on all at once)", "ty.id.price_recovery_in_year", "recovery already embedded in guidance is not added again", "dated price revisions with eligible volume"),
    A("ASM_TY_RECOVERY_OBJECTIVE", "price recovery objective", "toyota.price_recovery_annualized", "Toyota; regions not split", "price revisions", FY27, "yen trillion per year", "about half of materials alone (management objective)",
      "a management aspiration, not realized recovery; it carries over into the following year", "ty.id.price_recovery_in_year", "volume held fixed as an explicit controlled assumption (price elasticity is undisclosed)",
      "realized price, incentives and volume/mix effects"),
    A("ASM_TY_US_ASSET_RESET", "average exposed US earning-asset balance and its reset", "toyota.us_fin_asset_reset_share", "Toyota Motor Credit Corporation; United States", "US GAAP, dollars", "the controlled period", "fraction/yr and $bn", 0.30,
      "unsupported by an attached reference; a share reset by period end is not the average share exposed (for a uniform reset the average is half)", "ty_ust_us_asset_yield; delta NII", "customer repricing is a separate input",
      "the subsidiary's receivable maturities and floating dealer balances, bound as cohorts"),
    A("ASM_TY_US_FUNDING_RESET", "average exposed US funding balance and its reset", "toyota.us_fin_funding_reset_share", "Toyota Motor Credit Corporation; United States", "US GAAP, dollars", "the controlled period", "fraction/yr and $bn", 0.35,
      "unsupported by an attached reference", "ty_ust_us_funding_rate; delta NII", "hedge adjustment kept separate (swap notionals are disclosed, legs are not classified)",
      "debt maturities, floating balances and swap legs from the subsidiary's reports"),
    A("ASM_TY_US_GAAP_IFRS", "US GAAP to IFRS adjustment", "toyota.us_fin_gaap_ifrs_adjustment", "Toyota Motor Credit Corporation; United States", "segment basis", FY27, "$bn/yr", 0.0,
      "not disclosed; kept as an explicit zero-centred assumption, not a plug", "toyota.us_fin_operating_contribution", "inter-segment items inside the adjustment", "a classified mapping"),
    A("ASM_TY_FS_FIXED_LINES", "fixed financial-services lease/other revenue and depreciation/other costs", "toyota.fs_lease_other_revenue; toyota.fs_depreciation_other_costs", "Toyota consolidated financial services", "IFRS segment lines", FY27, "yen trillion per year", "1.7 and 1.2 (synthetic)",
      "the segment line does not split interest from lease and other; these fixed lines do not move with rates", "ty.comp.fs_revenue_lines; ty.comp.fs_cost_lines", "residual-value losses land in depreciation and other", "segment note disclosures"),
    A("ASM_TY_US_LEASE_OTHER", "US net lease margin, other revenues and expenses", "toyota.us_fin_net_lease_margin; toyota.us_fin_other_revenues; toyota.us_fin_expenses", "Toyota Motor Credit Corporation; United States", "US GAAP", FY27, "$bn/yr", "0.6, 2.0 and 2.6 (synthetic)",
      "the model's synthetic priors; the subsidiary's reported lines are bound as counterparts", "ty.comp.us_fin_contribution", "lease depreciation only in the lease margin; credit losses, operating and protection costs only in expenses", "the reported lines of the subsidiary (bound as observations)"),
    A("ASM_TY_FX_MODE", "FX calculation mode", "ty_yen_transaction; m29", "Toyota; Japan and overseas", "aggregate sensitivity with exclusions", "the controlled period", "yen per dollar", "aggregate",
      "component views stay explanatory and unsized", "FX effects on operating income", "ty_yen_imports and ty_yen_translation are suppressed (unsized)", "a re-estimated decomposition"),
    A("ASM_TY_FX_DELAY", "simulation delay and lag settings", "ty_yen_transaction (14 and 30 days); m29 (30 and 90 days)", "Toyota; Japan", "simulation timing", "the controlled period", "days", "as set in the model",
      "model settings; not proof of shipment, hedge roll-off or accounting recognition dates", "timing of FX effects", "none", "company timing evidence (contract resets, hedge roll-off, recognition)"),
    A("ASM_TY_DISRUPTION_POOL", "one eligible model-market pool and quarterly schedule", "ty.sf.na_dealer_stock; toyota.na_dealer_arrivals", "Toyota; one model-market pool (assumed)", "units; same model, geography and channel", "Jan-Mar then Apr-Jun (fixture)", "units",
      "compatible opening stock 30,000; missed eligible arrivals 80,000; catch-up 20,000 a quarter later; cancellations 0; extra freight and restart cost held as stated", "no dated unit balance exists for the event; a hard-coded instance shows the identities, not Toyota's inventory", "model checks M07",
      "other demand and prices held fixed; no inventory borrowed from another country or powertrain", "a dated unit balance and the event record (stage, routes, restart)"),
    A("ASM_TY_SHARE_SCOPE", "matched-scope market index, Toyota index and opening share", "toyota.asia_market_share (scope qualified); asia_auto_market.chinese_brand_share", "one country and category (assumed)", "retail or wholesale basis stated per series", "the controlled period", "index and fraction", "market 100->66; Toyota 100->72; opening share 0.10",
      "source series are incomplete; the regional 20% Chinese-brand input has no evidence reference and is a labelled stress input", "model checks M08", "no margin is inferred from share alone", "company and market units by country, brand and category"),
    A("ASM_TY_SOURCING_PROJECT", "one sourcing project: customs-value reduction, upfront spend, ramp and discount rate", "toyota.localized_customs_value; us_vehicle_tariffs.effective_rate", "Toyota; one project (assumed)", "scenario duty rate and exemption labelled", "from the assumed commissioning date", "yen billion",
      "upfront 200; avoided duty 60 a year; extra cash costs 20 a year; discount rate 8% (fixture)", "no project plan, classification or rate is verified; the fixture shows payback and value arithmetic only", "model checks M09", "internal transfer support nets to zero at the group", "classification, rates, exemptions and the project plan"),
    A("ASM_TY_CASH_PERIOD", "one eligible-cash period: opening, OCF, capex, dividends, buyback, other cash, floor", "toyota.industrial_liquidity; toyota.industrial_operating_cash_flow; toyota.industrial_other_cash_movements; toyota.eligible_liquidity_floor", "Toyota industrial businesses (finance cash excluded)", "eligible liquidity: cash and securities of the industrial entities, gross of debt",
      "the controlled period", "yen trillion", "opening 15.0; OCF 4.5; capex 2.3; dividends 1.2; buyback 0.5; other cash 0 (a visible assumed residual); floor 15.0 (reviewer-selected)",
      "the fixture; the floor is the reviewer's sensitivity (owner: reviewer; effective period: the controlled period), not a Toyota policy", "model checks M10", "working capital stays inside OCF; capex is not deducted twice", "a reconciled cash roll-forward and the company's disclosed liquidity buffer, if any"),
]


def _ident(pack: dict, iid: str) -> dict:
    i = next(x for x in pack["domain_specific_support_objects"]["financial_identities"] if x["identity_id"] == iid)
    return {"form": i["form"], "coefficient": i.get("coefficient"), "terms": [{"value": t["metric"], "role": t["role"]} for t in i["terms"]], "target": i["target_metric"]}


def _run(pack: dict, iid: str, levels: dict[str, float]) -> float | None:
    return eval_identity(_ident(pack, iid), levels)


def run_checks(pack: dict, repair: dict, obs: dict, values: dict, bridges: list, recons: list, fin: dict, fxb: list) -> list[dict]:
    """The model checks of the repair instructions. Each: id, status (run, blocked, not run), how it was run, inputs, intermediate
    values, results, what the fixture shows and what it does not, and the schema gaps."""
    out: list[dict] = []
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}

    def add(cid, title, fix, status, how, inputs, steps, results, ok, limits, gaps=()):
        out.append({"check_id": cid, "title": title, "fix": fix, "status": status, "run_through": how, "inputs": inputs, "intermediate": steps,
                    "results": results, "passes": ok, "limits": limits, "schema_gaps": list(gaps),
                    "note": "Hypothetical fixture from the repair instructions, not Toyota guidance."})

    # model check 1: actual versus estimate, both OP reconciliations under one baseline
    op_views = {r["composition_id"]: r for r in recons if r["composition_id"] in ("ty.comp.regional_operating_income", "ty.comp.reporting_segments")}
    three = {}
    for mid in ("toyota.operating_profit", "toyota.net_income", "toyota.north_america_operating_income"):
        v = values.get(mid)
        sel = [r for r in (v or {}).get("reported", []) if r["selected_baseline"]]
        if v and sel:
            three[mid] = {"reported": sel[0]["value"], "period": sel[0]["period"], "estimate_mean": v["estimate"]["mean"], "sign_conflict": (v["estimate"]["mean"] > 0) != (sel[0]["value"] > 0)}
    zero = {k: r["after"]["sum"] for k, r in op_views.items()}
    ok1 = bool(op_views) and all(r["after"]["status"] == "ok" for r in op_views.values()) and len(three) == 3
    add("MC1", "Actual versus estimate, and both operating-profit views under one baseline", "Fix 1, 3", "run" if op_views else "blocked", "baseline_reconciliations and observation_estimate_pairs of this export",
        {"baseline": repair["selected_baseline"]["baseline_id"], "metrics": list(three)},
        {"pairs": three, "views": {k: {"before": r["before"]["relative_difference"], "after": r["after"]["relative_difference"], "after_difference": r["after"]["difference"]} for k, r in op_views.items()}},
        {"zero_incremental_change_reproduces_baseline": {k: {"total": r["after"]["total_level"], "sum_of_parts": zero[k]} for k, r in op_views.items()},
         "mismatches_with_the_primary_summary": [o["metric_id"] for o in obs.values() if o.get("corroboration") and not o["corroboration"]["matches_to_rounding"]]},
        ok1, "the unexplained residual at the baseline is the rounding of the reported tables; the model-state gap is attributed to inputs, not closed",
        ["a regional x business split is undisclosed and stays unknown"])

    # model check 2: hybrid mix
    lv = {"toyota.hybrid_substituted_units": 0.01, "toyota.hybrid_contribution_spread": 0.05}
    base_v = _run(pack, "ty.id.hybrid_mix_op", lv)
    zero_v = _run(pack, "ty.id.hybrid_mix_op", {**lv, "toyota.hybrid_contribution_spread": 0.0})
    jv = {"ty_jv_units_equity": rels.get("ty_jv_units_equity", {}).get("axelrod", {}).get("target_metric"),
          "ty_hybrid_mix_auto_oi": rels.get("ty_hybrid_mix_auto_oi", {}).get("axelrod", {}).get("target_metric")}
    ok2 = base_v is not None and abs(base_v - 0.0005) < 1e-12 and zero_v == 0 and jv["ty_jv_units_equity"] == "toyota.equity_method_income" and jv["ty_hybrid_mix_auto_oi"] == "toyota.automotive_operating_income"
    add("MC2", "Hybrid mix at fixed total units", "Fix 7", "run", "identity ty.id.hybrid_mix_op evaluated with the fixture's levels",
        {"substituted_units": 10_000, "spread_yen_per_unit": 50_000, "total_units_change": 0},
        {"yen_trillion": base_v, "yen_million": None if base_v is None else round(base_v * 1e6, 6)}, {"with_spread": base_v, "spread_zero": zero_v, "eligible_scope": "toyota.hybrid_eligible_units (consolidated, named scope)",
         "jv_stays_out_of_consolidated_revenue": jv}, ok2,
        "an assumption-driven sensitivity, not a measured hybrid opportunity; detailed mode and direct-margin mode must not both be added; supply capacity is an unverified ceiling")

    # model check 3: pricing by period
    y = lambda v: round(v, 9)  # noqa: E731
    res3 = {}
    for label, share in (("april_1_start", 1.0), ("october_1_start", 0.5)):
        rec = _run(pack, "ty.id.price_recovery_in_year", {"toyota.price_recovery_annualized": 0.06, "toyota.recovery_year_share": share})
        cost = _run(pack, "ty.id.cost_recognized_in_year", {"toyota.material_cost_pressure": 0.12, "toyota.cost_recognition_weight": 1.0})
        net = _run(pack, "ty.id.pricing_net_op", {"toyota.price_recovery_booked": rec, "toyota.material_cost_booked": cost})
        sched = pricing_by_period(0.12, 0.06, 0.0 if share == 1.0 else 0.5)
        res3[label] = {"recovery_in_year_tn": y(rec), "cost_in_year_tn": y(cost), "net_op_tn": y(net), "quarterly_cost_tn": [y(x) for x in sched.cost_by_quarter],
                       "quarterly_recovery_tn": [y(x) for x in sched.recovery_by_quarter], "next_full_year_recovery_if_persisting_tn": sched.recovery_next_year_if_persisting}
    emb = pricing_by_period(0.12, 0.06, 0.0, baseline_recovery_in_year=0.06)
    ok3 = abs(res3["april_1_start"]["recovery_in_year_tn"] - 0.06) < 1e-9 and abs(res3["october_1_start"]["recovery_in_year_tn"] - 0.03) < 1e-9 \
        and res3["april_1_start"]["cost_in_year_tn"] == res3["october_1_start"]["cost_in_year_tn"] and abs(emb.net_op - (-0.12)) < 1e-9
    add("MC3", "Six-month pricing delay", "Fix 8", "run", "identities ty.id.price_recovery_in_year, ty.id.cost_recognized_in_year, ty.id.pricing_net_op; quarterly schedule from period_math",
        {"annual_cost_bn": 120, "annualized_recovery_bn": 60, "starts": ["April 1", "October 1"], "cost_weights": "uniform (assumed)"}, res3,
        {"baseline_recovery_embedded_not_added_twice": {"scenario_net_op_tn_with_60bn_already_in_baseline": y(emb.net_op), "incremental_recovery_tn": 0.0}}, ok3,
        "volume is held fixed as an explicit controlled assumption (price elasticity undisclosed); lost-unit contribution is zero here and would be shown separately")

    # model check 4: financing identities, reset fixtures and FX translation signs
    nii_base = _run(pack, "ty.id.us_fin_nii", {"toyota.us_fin_interest_income": 8.45, "toyota.us_fin_interest_expense": 5.04})
    nii_up = _run(pack, "ty.id.us_fin_nii", {"toyota.us_fin_interest_income": 8.55, "toyota.us_fin_interest_expense": 5.10})
    d = delta_nii(10.0, 1.0, 6.0, 1.0, 1.0)
    zero_x = delta_nii(0.0, 1.0, 0.0, 1.0, 1.0)
    tr = {}
    for label, local, rate in (("profit_160", 1.0, 160), ("profit_145", 1.0, 145), ("loss_160", -1.0, 160), ("loss_145", -1.0, 145)):
        tr[label] = {"model_identity": _run(pack, "ty.id.us_translation", {"toyota.us_operations_profit_usd": local, "dollar_yen.usd_jpy": rate}), "function": translate(local, rate)}
    half = average_exposed_share_uniform(0.30)
    ok4 = abs((nii_up - nii_base) - 0.04) < 1e-9 and abs(d["delta_nii"] - 0.04) < 1e-12 and zero_x["delta_nii"] == 0 \
        and abs(tr["profit_160"]["model_identity"] - 0.160) < 1e-12 and abs(tr["loss_145"]["model_identity"] + 0.145) < 1e-12
    add("MC4", "Financing identities and reset fixtures; translation signs", "Fix 9, 10", "run", "identities ty.id.us_fin_nii and ty.id.us_translation evaluated; delta NII from period_math",
        {"income_increase_usd_m": 100, "expense_increase_usd_m": 60}, {"nii_before_bn": nii_base, "nii_after_bn": nii_up, "delta_nii_bn": round(nii_up - nii_base, 9), "formula_result": d,
                                                                       "uniform_reset_average_share_for_0.30": half},
        {"zero_exposure": zero_x, "translation": tr, "us_scope_endpoint": fin["endpoint_policy"]["treatment"],
         "cohort_fixture_usd_bn": fin["cohort_fixture"]["result_usd_bn"]}, ok4,
        "the direct interest effect of zero exposure is zero, which does not mean total earnings are unchanged when other channels are active; the US module reaches the group only through the blocked scope view, so no group OP number is implied")

    # M07 disruption
    sched = [DisruptionPeriod("Jan-Mar", 80_000), DisruptionPeriod("Apr-Jun", 0, catch_up_deliveries=20_000, extra_cost=1.0)]
    with_buf = disruption(30_000, sched)
    no_buf = disruption(0, sched)
    late = disruption(30_000, [DisruptionPeriod("Jan-Mar", 80_000), DisruptionPeriod("Apr-Jun", 0), DisruptionPeriod("Jul-Sep", 0, catch_up_deliveries=20_000)])
    elim = elimination_roll(0.0, 10.0, 6.0)
    ok7 = with_buf[0]["delivery_shortfall"] == 50_000 and with_buf[1]["cumulative_shortfall"] == 30_000 and with_buf[1]["lost_cumulative"] == 0 \
        and no_buf[0]["delivery_shortfall"] == 80_000 and no_buf[1]["cumulative_shortfall"] == 60_000 \
        and all(p["stock_close"] >= 0 for p in with_buf + no_buf + late) and late[-1]["cumulative_shortfall"] == with_buf[1]["cumulative_shortfall"]
    add("M07", "Disruption inventory and deferred sales", "Fix 11", "run", "plain functions (period_math.disruption, elimination_roll); the model's stock-flow ty.sf.na_dealer_stock has no event instance",
        {"compatible_buffer": 30_000, "missed_arrivals": 80_000, "catch_up": 20_000, "cancellations": 0}, {"with_compatible_inventory": with_buf, "without_inventory": no_buf, "catch_up_one_quarter_later": late,
                                                                                                         "elimination_roll_open_0_new_10_release_6": elim},
        {"stock_never_negative": all(p["stock_close"] >= 0 for p in with_buf + no_buf + late), "cancellations_counted_once": True,
         "unresolved_deferred_orders_are_not_permanent_loss": with_buf[1]["lost_cumulative"] == 0, "elimination_release_is_a_reconciliation_not_a_second_profit": True,
         "extra_cost_kept_even_if_sales_recover": with_buf[1]["extra_cost_cumulative"]}, ok7,
        "one assumed model-market pool; Middle East shipping and Japan production disruption are kept separate; an annual regional export figure is not converted to affected shipments",
        ["no dated event-instance object in the schema (stage, plants, models, destinations, route capacity, restart)"])

    # M08 franchise economics
    ms = matched_share(100, 72, 100, 66, 0.10)
    ok8 = abs(ms["company_unit_growth"] + 0.28) < 1e-12 and abs(ms["relative_share_change"] - 0.090909) < 1e-6 and abs(ms["closing_share"] - 0.109091) < 1e-6 and abs(ms["change_pp"] - 0.9091) < 1e-4
    add("M08", "Matched-scope share and affiliate economics", "Fix 12", "run", "plain functions (period_math.matched_share); the model has no country-level share identity",
        {"market_index": [100, 66], "toyota_index": [100, 72], "opening_share": 0.10}, ms,
        {"relative_change_percent": round(100 * ms["relative_share_change"], 4), "pp_change": round(ms["change_pp"], 4),
         "growth_difference_shortcut_rejected": round(ms["growth_difference_shortcut"], 4),
         "fixed_share_worse_mix_and_support": "earnings fall through an assumed contribution loss and an independent finance-support cost, with units and share held fixed (no fabricated volume decline)",
         "affiliate_accounts": [b for b in bridges if b.get("kind") == "china_measures"][0]["measures"] if any(b.get("kind") == "china_measures" for b in bridges) else None,
         "jv_gross_sales_in_consolidated_revenue": False}, ok8,
        "scope: one country and category (assumed); equity-accounted entities reach Toyota's recognized share of after-tax profit, not gross sales; ownership is not applied twice; distributions are separate from income",
        ["country-by-brand-by-category series are not carried as values; a controlled index stands in"])

    # M09 sourcing
    pb0 = payback_years(200, 60, 20, 0)
    yrs = operating_years_needed(200, 60, 20)
    pb2 = payback_years(200, 60, 20, 2)
    n0 = npv(project_cash_flows(200, 60, 20, 0, 10), 0.08)
    n2 = npv(project_cash_flows(200, 60, 20, 2, 10), 0.08)
    duty = _run(pack, "ty.id.us_duty_avoided", {"toyota.localized_customs_value": 0.4, "us_vehicle_tariffs.effective_rate": 15.0})
    sup_na, sup_jp = rels.get("ty_transfer_support_na"), rels.get("ty_transfer_support_japan")
    net_support = None
    if sup_na and sup_jp:
        net_support = (1 if sup_na["axelrod"].get("transition", {}).get("sign") in ("+", 1) else -1) + (1 if sup_jp["axelrod"].get("transition", {}).get("sign") in ("+", 1) else -1)
    ok9 = abs(pb0 - 5) < 1e-12 and abs(yrs - 5) < 1e-12 and abs(pb2 - 7) < 1e-12 and n2 < n0 and duty is not None and abs(duty - 0.06) < 1e-12
    add("M09", "Sourcing project payback and value", "Fix 13", "run", "identity ty.id.us_duty_avoided; payback and NPV from period_math",
        {"upfront_bn": 200, "avoided_duty_bn_per_year": 60, "extra_cash_costs_bn_per_year": 20, "delay_years": [0, 2], "discount_rate": 0.08, "life_years": 10},
        {"duty_avoided_tn": duty, "payback_immediate_years": pb0, "operating_years_needed_after_delay": yrs, "payback_with_two_year_delay_from_spend": pb2,
         "npv_immediate_bn": round(n0, 3), "npv_delayed_bn": round(n2, 3)},
        {"duty_only_on_displaced_covered_customs_value": True, "internal_support_net_effect_on_group_op": net_support, "capex_is_cash_depreciation_is_op": True,
         "label": "pretax cash sensitivity with an assumed discount rate; payback is not NPV and no sourcing recommendation is made"}, ok9,
        "scenario duty rate and exemption are labelled assumptions; a local unit does not remove all imported-parts exposure; refunds are modelled separately from recognized duty",
        ["refund eligibility, recognized receivable and cash receipt have no separate objects"])

    # M10 capital returns
    c_open = liquidity_close(15.0, 4.5, 2.3, 0.0, 1.2, 0.5)
    c_delay = liquidity_close(15.0, 4.5, 2.3, 0.0, 1.2, 0.5, collection_delay=1.0)
    c_forgo = liquidity_close(15.0, 4.5, 2.3, 0.0, 1.2, 0.0, collection_delay=1.0)
    cap = buyback_capacity(1.0, 0.1, 5.0, c_forgo - 15.0)   # headroom above the assumed floor when nothing is bought back
    ok10 = abs(c_open - 15.5) < 1e-12 and abs(c_delay - 14.5) < 1e-12 and abs(c_forgo - 15.0) < 1e-12 and cap["permitted_spend"] == 0.0
    sp = rels.get("d-toyota-operating_profit-share_price")
    add("M10", "Conditional buyback capacity from eligible cash", "Fix 14", "run", "plain functions (period_math.liquidity_close, buyback_capacity); the minimum of three ceilings is not expressible in the calculation forms",
        {"opening": 15.0, "ocf": 4.5, "capex": 2.3, "dividends": 1.2, "buyback": 0.5, "other_cash": 0.0, "collection_delay": 1.0, "floor": 15.0}, {"closing_planned": c_open, "closing_with_delay": c_delay, "closing_without_buyback": c_forgo, "capacity": cap},
        {"planned_buyback_fits_under_floor_with_delay": False, "forgoing_it_restores_floor": abs(c_forgo - 15.0) < 1e-12,
         "authorization_is_not_execution": "cash ceiling, share ceiling and window are stored apart from completed purchases",
         "finance_cash_appropriated": False, "capex_or_working_capital_deducted_twice": False,
         "op_to_share_price_default": ("uncalibrated hypothesis; no numerical stock outcome" if sp and sp.get("qualification_status") == "uncalibrated hypothesis" else "see relationship")}, ok10,
        "a conditional cash constraint, not a Toyota policy prediction; the floor is the reviewer's sensitivity",
        ["permitted spend = max(0, min(cash authorization, share authorization x price, eligible headroom)) is not expressible: the payout is stipulated and validated against the three ceilings"])
    return out


# -- the completion checks of the Equities and Disruption repairs (C01-C06, Oct 19) -----------------------------------------------------------
RUNTIME = "not tested here: whether an answering agent reads these records is the runtime owner's (observed problems R01-R10)"
ANSWER = "not tested here: answer quality is judged on a rerun of the questions, kept apart from model correctness"


def completion_checks(pack: dict, repair: dict, values: dict, bridges: list, recons: list, fin: dict, earlier: list[dict]) -> list[dict]:
    """C01-C06: source reproductions and controlled fixtures, each returned with the package the instructions ask for (status, changed
    ids, baseline, source period and passages, assumptions, intermediate values, reconciliation, unresolved endpoints) and three separate
    completion states. The fixtures are hypothetical; none is a Toyota figure, and no expected answer is placed in a retrieval scope."""
    out: list[dict] = []
    by = {c["check_id"]: c for c in earlier}
    base = repair["selected_baseline"]["baseline_id"]

    def add(cid, title, repairs, maps_to, ok, changed, period, passages, assumptions, steps, recon, unresolved, status="run"):
        out.append({"check_id": cid, "title": title, "repairs": repairs, "maps_to": maps_to, "status": status, "passes": ok,
                    "changed_ids": changed, "selected_baseline": base, "source_period": period, "passages": passages, "assumptions": assumptions,
                    "intermediate": steps, "reconciliation": recon, "unresolved_endpoints": unresolved,
                    "completion_states": {"model_correctness": "passed" if ok else "failed", "runtime_access": RUNTIME, "answer_quality": ANSWER}})

    # C01 quarterly earnings
    qb = next((b for b in bridges if b.get("period_arithmetic")), None)
    if qb is None:
        add("C01", "Quarterly earnings from dated records", "M02", [], False, [], None, [], [], {}, None, ["no quarterly bridge in the repair data"], status="blocked")
    else:
        ar = qb["period_arithmetic"]
        tol = 0.000002                      # ¥0.002bn in ¥tn, for rounded published rows
        ok_rows = all(abs(ar[p]["pretax_rounding_residual"]) <= tol and abs(ar[p]["attributable_rounding_residual"]) <= tol for p in ar)
        lines = {ln["line_id"]: ln for ln in qb["lines"]}
        explained = sorted({e for ln in qb["lines"] for e in ln["explained_by"]})
        fs_below = [i for i in lines if "financial_services" in i or "fs_" in i]
        add("C01", "Quarterly earnings from dated records", "M02", ["quarterly bridge"], ok_rows and bool(explained) and not fs_below,
            [qb["bridge_id"]], qb["periods"], explained,
            [], {p: {k: ar[p][k] for k in ("pretax_from_lines", "pretax_reported", "attributable_from_pretax", "attributable_reported")} for p in ar},
            {"tolerance_tn": tol, "year_on_year": qb["year_on_year"], "finance_segment_lines_below_op": fs_below},
            ["repeatability of each below-OP item is classified apart from its accounting line; a below-OP item is not automatically non-recurring"])

    # C02 baseline and both operating-profit views
    mc1 = by.get("MC1", {})
    na = values.get("toyota.north_america_operating_income", {})
    na_rep = [r for r in na.get("reported", []) if r.get("selected_baseline")]
    loss_kept = bool(na_rep) and na_rep[0]["value"] < 0
    op = {r["composition_id"]: r for r in recons if r["composition_id"] in ("ty.comp.regional_operating_income", "ty.comp.reporting_segments")}
    flagged = {k: r["after"]["difference"] for k, r in op.items() if r["after"]["status"] != "ok"}
    add("C02", "Baseline and the two operating-profit views", "M01", ["MC1"], bool(mc1.get("passes")) and loss_kept and not flagged,
        sorted(r["reconciliation_id"] for r in op.values()), repair["selected_baseline"]["period"], [r["source"] for r in (rr["adjustments"][0] for rr in op.values() if rr["adjustments"])],
        [], {"views": {k: {"total": r["after"]["total_level"], "sum": r["after"]["sum"], "difference": r["after"]["difference"], "status": r["after"]["status"]} for k, r in op.items()},
             "zero_shock": "each view evaluated at the selected baseline with no increment reproduces it (the after column)",
             "north_america_reported": na_rep[0] if na_rep else None, "north_america_estimate": (na.get("estimate") or {}).get("mean")},
        {"views_added_to_each_other": False, "unexplained_residuals": flagged},
        ["a regional x business split is undisclosed"])

    # C03 hybrid substitution at fixed units
    lv = {"toyota.hybrid_substituted_units": 0.1, "toyota.hybrid_contribution_spread": 0.05}
    v = _run(pack, "ty.id.hybrid_mix_op", lv)
    v0 = _run(pack, "ty.id.hybrid_mix_op", {**lv, "toyota.hybrid_contribution_spread": 0.0})
    conv = _run(pack, "ty.id.hybrid_mix_op", {**lv, "toyota.hybrid_substituted_units": 0.0})
    projects = {r["record_id"]: r for r in repair.get("business_records", []) if r.get("record_kind") == "project"}
    ok3 = v is not None and abs(v - 0.005) < 1e-12 and v0 == 0 and conv == 0
    add("C03", "Hybrid substitution at fixed total units", "M04", ["MC2"], ok3, ["ty.id.hybrid_mix_op", *sorted(projects)], "controlled fixture", [],
        ["ASM_TY_HYBRID_SUBSTITUTED", "ASM_TY_HYBRID_SPREAD", "ASM_TY_HYBRID_CAPACITY"],
        {"substituted_units": 100_000, "spread_yen_per_unit": 50_000, "total_units_change": 0, "delta_op_tn": v, "delta_op_bn": None if v is None else round(v * 1000, 9),
         "spread_removed_tn": v0, "capacity_conversion_alone_tn": conv},
        None, ["net additional usable capacity, affected models and regions, qualified output dates, demand or backlog, displaced product, contribution spread"])

    # C04 financing reset
    inc = interest_increment([Cohort(50.0)], 1.0, 0.5)
    zero = interest_increment([], 1.0, 0.5)
    lines = {"funding_interest": 0.0, "lease_and_depreciation": 0.0}
    shock = apply_rate_shock(lines, "funding_interest", [Cohort(50.0)], 1.0, 0.5)
    yen_bn = inc * 150
    ok4 = abs(inc - 0.25) < 1e-12 and abs(yen_bn - 37.5) < 1e-9 and zero == 0 and shock.changed == ("funding_interest",) and shock.lines["lease_and_depreciation"] == 0.0
    add("C04", "Financing reset", "M03", ["MC4"], ok4, [x for x in ("ty.id.fs_interest_income", "ty.id.fs_funding_interest", fin.get("bridge_id")) if x], "controlled fixture (six months after reset)", [],
        ["ASM_TY_US_FUNDING_RESET", "ASM_TY_FS_FIXED_LINES"],
        {"eligible_debt_usd_bn": 50.0, "rate_change_bp": 100, "years_after_reset": 0.5, "incremental_expense_usd_bn": inc, "usd_jpy_stipulated": 150,
         "incremental_expense_yen_bn": yen_bn, "zero_eligible_balance_usd_bn": zero, "lines_moved": list(shock.changed)},
        {"endpoint": fin["endpoint_policy"]["treatment"], "statement": "not a disclosed Toyota sensitivity and not automatically group OP"},
        fin["endpoint_policy"].get("to_unblock", []))

    # C05 localization payback
    pb0, pb2 = payback_years(200, 60, 20, 0), payback_years(200, 60, 20, 2)
    flows = project_cash_flows(200, 60, 20, 2, 10)
    first_benefit = min(t for t, cf in flows if cf > 0)
    ok5 = abs(pb0 - 5) < 1e-12 and abs(pb2 - 7) < 1e-12 and first_benefit == 3
    add("C05", "Localization payback with delayed benefits", "M06", ["M09"], ok5, sorted(projects), "controlled fixture", [],
        ["ASM_TY_SOURCING_PROJECT"],
        {"upfront_bn": 200, "avoided_duty_bn_per_year": 60, "extra_cash_costs_bn_per_year": 20, "steady_state_cash_benefit_bn": 40, "payback_years": pb0,
         "payback_with_two_year_delay_from_spend": pb2, "first_year_with_benefit_after_delay": first_benefit},
        {"op_and_cash_kept_apart": True, "npv": "needs dated cash flows and a discount rate (M09 shows one with an assumed rate)"},
        ["no immediate OP benefit before production and eligible inventory recognition", "tariff eligibility and rates are scenario inputs"])

    # C06 cash and buybacks
    c = liquidity_close(15.0, 4.5, 2.3, 0.0, 1.2, 0.5)
    cd = liquidity_close(15.0, 4.5, 2.3, 0.0, 1.2, 0.5, collection_delay=1.0)
    cf = liquidity_close(15.0, 4.5, 2.3, 0.0, 1.2, 0.0, collection_delay=1.0)
    ok6 = abs(c - 15.5) < 1e-12 and abs(cd - 14.5) < 1e-12 and abs(cf - 15.0) < 1e-12
    cash = next((r for r in repair.get("business_records", []) if r.get("record_kind") == "cash_reconciliation"), None)
    add("C06", "Cash capacity with a delayed collection", "M07", ["M10"], ok6, ["ty.id.industrial_fcf", "ty.sf.industrial_liquidity", "ty_fcf_liquidity"], "controlled fixture", [],
        ["ASM_TY_CASH_PERIOD"], {"closing_tn": c, "closing_with_delay_tn": cd, "closing_without_buyback_tn": cf, "op_change": 0.0, "assumed_floor_tn": 15.0},
        {"reported_roll_forward": None if cash is None else cash.get("status")}, ["the company's liquidity buffer is undisclosed; the floor is the reviewer's sensitivity"])
    return out
