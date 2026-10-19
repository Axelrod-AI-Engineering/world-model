"""Reported facts, bridges and reconciliations of the repair export (context/earnings.py), on invented numbers."""

import pytest

from axelrod_wm.context.earnings import _docs, build_bridge, reconcile_at
from axelrod_wm.context.reading import routing_text
from axelrod_wm.context.repair_checks import ASSUMPTIONS


def test_evidence_count_counts_distinct_documents_not_references():
    refs = [{"document": "a.pdf"}, {"document": "a.pdf"}, {"document": ["b.pdf", "c.pdf"]}, {"source_id": "s1"}, {}]
    assert _docs(refs) == {"a.pdf", "b.pdf", "c.pdf", "s1"}
    assert len(refs) == 5


def obs(oid, key, v):
    return {f"{oid}_{key}": {"observation_id": f"{oid}_{key}", "value": v, "unit": "u", "available_at": "d", "source": {"source_id": "s"}}}


def test_bridge_sums_each_period_and_the_change_by_line():
    cur = dict(OP=100, EQ=10, OFI=50, OFC=-5, FX=20, OTH=1, PRE=176, TAX=40, NCI=6, NI=130)
    pri = dict(OP=110, EQ=8, OFI=10, OFC=-1, FX=-20, OTH=2, PRE=109, TAX=30, NCI=4, NI=75)
    o = {}
    for k in cur:
        o |= obs(k, "Q1_FY3_27", cur[k]) | obs(k, "Q1_FY3_26", pri[k])
    roles = [("ty.line.operating_income", "start", 1, "OP"), ("ty.line.equity_method_income", "add", 1, "EQ"), ("ty.line.other_finance_income", "add", 1, "OFI"),
             ("ty.line.other_finance_costs", "add", 1, "OFC"), ("ty.line.fx_gain_loss", "add", 1, "FX"), ("ty.line.other_income_loss", "add", 1, "OTH"),
             ("ty.line.pretax_income", "subtotal", 1, "PRE"), ("ty.line.income_tax_expense", "deduct", -1, "TAX"),
             ("ty.line.noncontrolling_interests", "deduct", -1, "NCI"), ("ty.line.net_income_attributable", "result", 1, "NI")]
    spec = {"bridge_id": "b", "title": "t", "periods": {}, "formula": "f", "definitions": "d",
            "lines": [{"line_id": i, "role": r, "sign": s, "obs": k, "explained_by": ["E1", "E9"]} for i, r, s, k in roles]}
    b = build_bridge(spec, o, {"E1"})
    assert b["period_arithmetic"]["current"]["pretax_rounding_residual"] == 0 and b["period_arithmetic"]["prior"]["attributable_rounding_residual"] == 0
    y = b["year_on_year"]
    assert y["attributable_net_income_change"] == 55 and y["residual"] == 0
    assert y["by_line"]["ty.line.income_tax_expense"] == -10 and y["by_line"]["ty.line.operating_income"] == -10
    assert b["lines"][0]["explained_by"] == ["E1"]            # only explanations that exist are linked


def test_reconciliation_keeps_losses_and_signs_and_blocks_on_a_missing_level():
    bridge = [{"composition_id": "c", "additive": True, "reconciliation": {"unit": "u", "total": "t", "parts": ["a", "loss", "elim", "cost"], "subtracted": ["cost"], "tolerance": 0.005}}]
    ok = reconcile_at(bridge, {"t": 10.0, "a": 12.0, "loss": -3.0, "elim": 1.5, "cost": 0.5}, "base")["c"]
    assert ok["sum"] == pytest.approx(10.0) and ok["status"] == "ok"
    bad = reconcile_at(bridge, {"t": 10.0, "a": 12.0, "loss": 3.0, "elim": 1.5, "cost": 0.5}, "base")["c"]
    assert bad["status"] == "flag" and bad["difference"] == pytest.approx(-6.0)
    blocked = reconcile_at(bridge, {"t": 10.0, "a": 12.0}, "base")["c"]
    assert blocked["status"] == "blocked" and set(blocked["missing_levels"]) == {"loss", "elim", "cost"}


def test_assumptions_are_never_observed_and_each_is_fully_described():
    need = {"name", "binding", "entity_and_geography", "accounting_scope", "period", "currency_and_units", "assumed_value", "reason",
            "affected_calculation", "included_offsets", "replaced_by"}
    assert len({a["assumption_id"] for a in ASSUMPTIONS}) == len(ASSUMPTIONS)
    for a in ASSUMPTIONS:
        assert need <= set(a) and all(a[k] not in (None, "") for k in need), a["assumption_id"]


def test_start_here_routes_earnings_questions_to_the_bounded_files():
    rows = [{"file": f"{n}_toyota_01.json"} for n in ("41_earnings_quarterly", "42_earnings_baseline", "43_earnings_financing", "44_earnings_inputs")]
    text = "\n".join(routing_text(rows))
    assert "ty.bridge.quarterly_earnings_q1_fy3_27" in text and "41_earnings_quarterly_toyota_01.json" in text and "never observed company facts" in text
    assert routing_text([{"file": "20_relationships_toyota_01.json"}]) == []
