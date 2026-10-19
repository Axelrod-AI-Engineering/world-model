"""The Equities and Disruption repairs (Oct 19): business records, related values, observation classes, completion checks.

Everything here is invented: the made-up company and synthetic numbers of test_repair_attach.
"""

from __future__ import annotations

from axelrod_wm.context.earnings import attach_repair, build_business
from axelrod_wm.context.repair_checks import completion_checks
from tests.unit.context.test_repair_attach import CID, QTR, build, mkobs, value


def with_records():
    ctx, repair = build()
    repair["observations"] += [mkobs("P_PRI", 1.0, period=QTR), mkobs("P_CUR", 3.0, period=QTR), mkobs("W_PRI", 2.0, period=QTR), mkobs("W_CUR", 4.0, period=QTR),
                               mkobs("BROKER", 21.0, kind="broker statement", **{"class": "externally_estimated"}),
                               mkobs("OCF", 5.0), mkobs("CAPEX", 2.0)]
    repair["business_records"] = [
        {"record_id": "PRJ_X", "record_kind": "project", "facts": {"capacity": 10, "list": ["P_CUR", 2]}, "stage": "announced"},
        {"record_id": "rule.part", "record_kind": "classification", "part": "p", "whole": "w", "p": ["P_PRI", "P_CUR"], "w": ["W_PRI", "W_CUR"]},
        {"record_id": "rule.scopes", "record_kind": "scopes", "a": "inc", "b": "exc", "inc": ["W_PRI", "W_CUR"], "exc": ["P_PRI", "P_CUR"]},
        {"record_id": "recon.cash", "record_kind": "cash_reconciliation", "operands": {"industrial_operating_cash_flow": "OCF", "capex": "CAPEX"}, "missing": ["opening"]},
        {"record_id": "recon.cash_full", "record_kind": "cash_reconciliation", "operands": {"industrial_operating_cash_flow": "OCF", "capex": "CAPEX"}},
    ]
    repair["related_values"] = ["market.share"]
    repair["input_classes"]["market.share"] = {"class": "assumed", "verification": "unverified", "basis": "no source"}
    ctx["evidence"]["values"].append({**value("market.share", observed=True), "node_id": "C_MARKET"})
    return ctx, repair


def test_business_records_resolve_observations_and_carry_their_arithmetic():
    ctx, repair = with_records()
    attach_repair(ctx, repair)
    sup = ctx["domain_pack"]["domain_specific_support_objects"]
    recs = {r["record_id"]: r for r in sup["business_records"]}
    assert all(r["company_id"] == CID for r in recs.values())
    assert recs["PRJ_X"]["facts"]["list"][0]["observation_id"] == "P_CUR" and recs["PRJ_X"]["facts"]["list"][1] == 2
    assert [c["part_within_whole"] for c in recs["rule.part"]["check"]] == [True, True]
    assert [d["a_minus_b"] for d in recs["rule.scopes"]["difference"]] == [1.0, 1.0]
    assert recs["recon.cash"]["derived"]["industrial_free_cash_flow"] == 3.0 and recs["recon.cash"]["status"] == "blocked"
    assert recs["recon.cash_full"]["status"] == "ok"
    obs = {o["observation_id"]: o for o in sup["earnings_observations"]}
    assert obs["BROKER"]["observed"] is False and obs["BROKER"]["class"] == "externally_estimated"
    assert obs["OCF"]["observed"] is True and obs["OCF"]["class"] == "reported"
    share = next(v for v in ctx["evidence"]["values"] if v["metric_id"] == "market.share")
    assert share["observed"] is False and share["input_class"] == "assumed"
    assert ctx["manifest"]["repair"]["counts"]["business_records"] == 5
    assert build_business({}, {}) == []


def test_completion_checks_return_their_package_and_keep_three_states_apart():
    ctx, repair = with_records()
    attach_repair(ctx, repair)
    checks = {c["check_id"]: c for c in ctx["domain_pack"]["domain_specific_support_objects"]["model_checks"] if c["check_id"].startswith("C")}
    assert list(checks) == ["C01", "C02", "C03", "C04", "C05", "C06"]
    for c in checks.values():
        assert {"status", "changed_ids", "selected_baseline", "passages", "assumptions", "intermediate", "reconciliation", "unresolved_endpoints"} <= set(c)
        assert set(c["completion_states"]) == {"model_correctness", "runtime_access", "answer_quality"}
    assert checks["C01"]["passes"] and checks["C01"]["passages"] == ["E1"]
    assert checks["C03"]["intermediate"]["delta_op_bn"] == 5.0 and checks["C03"]["intermediate"]["spread_removed_tn"] == 0
    assert checks["C04"]["intermediate"]["incremental_expense_yen_bn"] == 37.5 and checks["C04"]["intermediate"]["lines_moved"] == ["funding_interest"]
    assert checks["C05"]["intermediate"]["payback_with_two_year_delay_from_spend"] == 7
    assert checks["C06"]["intermediate"]["closing_with_delay_tn"] == 14.5 and checks["C06"]["reconciliation"]["reported_roll_forward"] == "blocked"
    # the fixture's regional profit is positive, so C02 reports the north America loss as not preserved
    assert checks["C02"]["passes"] is False and checks["C02"]["completion_states"]["model_correctness"] == "failed"
    assert all(checks[k]["passes"] for k in ("C01", "C03", "C04", "C05", "C06"))


def test_completion_checks_block_without_a_quarterly_bridge_and_degrade_without_records():
    ctx, repair = build()
    pack = ctx["domain_pack"]
    out = {c["check_id"]: c for c in completion_checks(pack, repair, {}, [], [], {"endpoint_policy": {"treatment": "t"}}, [])}
    assert out["C01"]["status"] == "blocked" and not out["C01"]["passes"]
    assert out["C02"]["intermediate"]["north_america_reported"] is None and not out["C02"]["passes"]
    assert out["C06"]["reconciliation"]["reported_roll_forward"] is None
    assert out["C04"]["unresolved_endpoints"] == []
