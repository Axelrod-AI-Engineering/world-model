"""Morgan Stanley's business construction (Oct 18): the compositions, operating and financial paths, and their transitions
in <client root>/worlds/sally_demo/construction/morgan_stanley.yaml, checked in the loaded model, in the v4.1.4 export, and
through the service API (the client root's docs/construction/morgan_stanley.md has the gap register these tests close). An investment bank
and wealth manager: its segments follow its drivers (markets and deals in Institutional Securities, client assets and
rates in Wealth Management, AUM in Investment Management), so the segment view is the driven one. Sally's world loads
once for the module; no client data is read."""

from __future__ import annotations

import math

import pytest
import yaml
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import construction_view, trace
from axelrod_wm.model.construction import (
    model_levels,
    reconcile,
    reconcile_identities,
    reconcile_stock_flows,
    validate_construction,
)
from tests.clients import client_path, skip_without_client
from tests.scenario import v1_reads as v1

skip_without_client('sally_demo')

MS = "morgan_stanley"
P = "morgan_stanley."
REV, PRETAX, NI = P + "net_revenue", P + "pretax_income", P + "net_income"
WM, ISG, IM = P + "wealth_revenue", P + "isg_revenue", P + "im_revenue"
FED, UST10 = "federal_reserve.policy_rate", "us_treasuries.yield_10y"
EQ, VOL, DEALS = "us_capital_markets.equity_index", "us_capital_markets.market_volatility", "us_capital_markets.deal_activity"

COMPOSITIONS = {   # id -> (total, additive)
    "ms.comp.revenue_by_segment": (REV, True),
    "ms.comp.isg": (ISG, True),
    "ms.comp.trading": (P + "trading_revenue", True),
    "ms.comp.equity": (P + "equity_revenue", True),
    "ms.comp.ib": (P + "ib_fees", True),
    "ms.comp.wm": (WM, True),
    "ms.comp.im": (IM, True),
    "ms.comp.wm_deposits": (P + "wm_deposits", True),
    "ms.comp.revenue_by_line": (REV, True),
    "ms.comp.nii": (P + "firm_nii", True),
    "ms.comp.expense": (P + "noninterest_expense", True),
    "ms.comp.pretax": (PRETAX, True),
    "ms.comp.net_income": (NI, True),
    "ms.comp.pretax_by_segment": (PRETAX, True),
    "ms.comp.wm_interest_income": (P + "wm_interest_income", True),
    "ms.comp.tier1": (P + "tier1_capital", True),
    "ms.comp.capital_sources_uses": (P + "cet1_capital", False),
}
# one driving view per total: the line view and segment pretax reconcile to their totals without driving them
RECONCILING = {"ms.comp.revenue_by_line", "ms.comp.pretax_by_segment"}
IDENTITIES = {  # id -> (form, target)
    "ms.id.wm_loan_interest": ("product", "wm_loan_interest_income"),
    "ms.id.wm_deposit_interest": ("product", "wm_deposit_interest"),
    "ms.id.wm_nii": ("difference", "wm_nii"), "ms.id.wm_am_fees": ("product", "wm_asset_mgmt_fees"),
    "ms.id.im_fees": ("product", "im_mgmt_fees"), "ms.id.advisory": ("product", "advisory_fees"),
    "ms.id.financing": ("product", "equity_financing"), "ms.id.compensation": ("product", "compensation_expense"),
    "ms.id.tax": ("product", "income_tax"), "ms.id.cet1_ratio": ("ratio", "cet1_ratio"), "ms.id.slr": ("ratio", "slr"),
}
STOCK_FLOWS = {"ms.sf.client_assets": "wm_client_assets", "ms.sf.fee_based_assets": "wm_fee_based_assets",
               "ms.sf.im_aum": "im_aum", "ms.sf.cet1": "cet1_capital"}
# views where the business leaves something out (ISG other, WM other, other lines and expenses, noncontrolling
# interests) or eliminates intersegment amounts; the others are exact splits as reported
WITH_REMAINDER = {"ms.comp.revenue_by_segment", "ms.comp.isg", "ms.comp.wm", "ms.comp.revenue_by_line", "ms.comp.expense",
                  "ms.comp.net_income", "ms.comp.pretax_by_segment", "ms.comp.wm_interest_income"}
PATHS = {  # the economics asked for -> the named path(s) that carry them
    "rates, deposits and sweeps to WM NII": ["ms.path.rates_wm_nii"],
    "market levels to asset-based fees (WM and IM), prime balances, deferred pay": ["ms.path.market_levels"],
    "net new assets": ["ms.path.net_new_assets"],
    "IM AUM, fees and performance fees": ["ms.path.investment_management", "ms.path.market_levels"],
    "deal activity to advisory and underwriting": ["ms.path.deals_ib"],
    "volatility to equities, FICC and retail trading": ["ms.path.volatility"],
    "credit": ["ms.path.credit_spreads", "ms.path.recession"],
    "rates (long end) to capital and fees": ["ms.path.long_end"],
    "compensation ratio and operating leverage": ["ms.path.expense_inflation"],
    "capital (CET1, SCB, SLR) and payout": ["ms.path.capital_payout", "ms.path.capital_requirements", "ms.path.balance_sheet"],
}
REDUCED_FORMS = {"s75": "ms.path.rates_wm_nii", "s13": "ms.path.deals_ib", "s15": "ms.path.volatility",
                 "s17": "ms.path.volatility", "ms-c-equity-amfees": "ms.path.market_levels"}
# the notes in the construction file (each sign-only link that could not take a new form says why)
with open(client_path("worlds/sally_demo/construction/morgan_stanley.yaml")) as _f:
    NOTES = {i["id"]: i.get("note") or "" for i in yaml.safe_load(_f)["interactions"]}
SOURCES = {"ms.wb", "ms.vm", "ms.co", "ms.r1", "ms.r2", "ms.r3", "ms.r4", "ms.r5", "ms.x1", "ms.pub"}


@pytest.fixture(scope="module")
def client():
    from axelrod_wm.repo.snapshots import MemoryBackend

    app = create_app(scenario="sally_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        c.app_state = app.state.axelrod
        yield c


@pytest.fixture(scope="module")
def g(client):
    return client.app_state.controller.engine.wm.graph


def _lognormal(sub) -> bool:
    return getattr(sub.prior, "family", "") == "lognormal"


def _native_sd(sub) -> float:
    return sub.scale * (math.exp(sub.anchor) if _lognormal(sub) else 1.0)


def _level(sub) -> float:
    return math.exp(sub.anchor) if _lognormal(sub) else sub.anchor


def _parts(c) -> list[str]:
    return [*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])]


def _link(g, src, tgt):
    hits = [i for i in g.active_interactions() if i.source_id == src and i.target_id == tgt]
    assert len(hits) == 1, (src, tgt, [i.id for i in hits])
    return hits[0]


def _ms_links(g):
    own = set(g.entities[MS].subentity_ids)
    return [i for i in g.active_interactions() if i.source_id in own or i.target_id in own]


def _reach(g, start):
    out_of = {}
    for i in g.active_interactions():
        out_of.setdefault(i.source_id, []).append(i.target_id)
    seen, stack = set(), [start]
    while stack:
        v = stack.pop()
        if v not in seen:
            seen.add(v)
            stack += out_of.get(v, [])
    return seen


# -- structure ---------------------------------------------------------------------------------------------------------
def test_no_construction_problems_for_morgan_stanley(g):
    assert construction_view(g, MS)["problems"] == []
    assert not [p for p in validate_construction(g) if MS in p or "ms." in p or "ms-" in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == MS and c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        if cid in WITH_REMAINDER:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)
        assert c.drives is (cid not in RECONCILING), cid
        if cid in RECONCILING:                                 # reconciles, never drives: no quantified link to the total
            assert all(not _link(g, sid, c.total).quantified for sid in _parts(c)), cid
            continue
        for sid in _parts(c):
            i = _link(g, sid, c.total)
            assert str(i.edge_type) == "accounting" and i.quantified and i.forward.effect.mean() > 0, (cid, sid)
            assert i.forward.effect.sd() <= 0.01
            w = i.forward.effect.mean()
            assert w == pytest.approx(_native_sd(g.subentities[sid]) / _native_sd(g.subentities[c.total]), abs=0.01), (cid, sid)


def test_priors_reconcile_within_half_a_percent(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        total, parts = _level(g.subentities[c.total]), sum(_level(g.subentities[s]) for s in _parts(c))
        assert abs(parts - total) <= 0.005 * abs(total), (cid, total, parts)


def test_required_paths_exist(g):
    for need, pids in PATHS.items():
        for pid in pids:
            p = g.paths[pid]
            assert p.entity_id == MS and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != MS:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)


def test_shared_driver_responses_are_parallel_branches(g):
    for pid, src, want in (("ms.path.rates_wm_nii", FED, {"beta", "sorting", "savings", "loans"}),
                           ("ms.path.market_levels", EQ, {"wm_fees", "client_assets", "im_aum", "carry", "prime",
                                                          "activity", "deferred_pay", "ipo_window"}),
                           ("ms.path.volatility", VOL, {"execution", "ficc", "retail", "ipo_window", "risk_off", "credit", "costs"}),
                           ("ms.path.long_end", UST10, {"marks", "bond_sleeve", "carry", "issuance"}),
                           ("ms.path.deals_ib", DEALS, {"advisory", "ecm", "dcm"})):
        by = {s.branch: g.interactions[s.interaction_id] for s in g.paths[pid].steps if s.branch}
        assert want <= set(by), (pid, set(by))
        assert {by[b].source_id for b in want} == {src}, pid


def test_reduced_forms_are_never_steps_of_their_structural_paths(g):
    for iid, pid in REDUCED_FORMS.items():
        assert iid not in {s.interaction_id for s in g.paths[pid].steps}, (iid, pid)
        assert g.interactions[iid].quantified and "Reduced form" in g.interactions[iid].transition.mechanism


# -- an investment bank and wealth manager's economics ---------------------------------------------------------------
def test_values_name_their_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == MS and s.id != P + "share_price"]
    assert len(own) > 60
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]


def test_the_segment_view_is_driven_and_eliminates_intersegment_revenue(g):
    seg = g.compositions["ms.comp.revenue_by_segment"]
    assert set(seg.members) == {ISG, WM, IM} and seg.eliminations == P + "intersegment_eliminations"
    assert g.subentities[seg.eliminations].prior.mean() < 0
    line = g.compositions["ms.comp.revenue_by_line"]
    assert not set(_parts(line)) & set(_parts(seg))
    # the line view is reached from the segment side only by size-free bridges
    line_side = set(_parts(line))
    crossing = [i for i in g.active_interactions() if i.target_id in line_side and str(i.edge_type) != "accounting"]
    assert crossing and all(not i.quantified and i.id.startswith("ms-c-bridge-") for i in crossing)
    assert g.compositions["ms.comp.pretax_by_segment"].eliminations == P + "elim_pretax"


def test_wm_nii_is_balances_times_rates_and_the_disclosed_sensitivity_sizes_the_reduced_form(g):
    s75 = g.interactions["s75"]
    assert s75.transition.evidence.magnitude == "documented" and "ms.co" in s75.transition.evidence.sources
    assert 0 < s75.forward.effect.mean() < 0.15          # resized from the disclosure, below the old statistical size
    st = s75.state                                        # sized for rises and falls: a cut costs more than a hike earns
    assert st is not None and st.asymmetry.falls["mu"] > st.asymmetry.rises["mu"] > 0
    # WM NII = loans x rate + securities interest - deposits x cost: exact identities, derived weights
    for iid, src, tgt in (("ms-c-loans-loaninterest", "wm_loans", "wm_loan_interest_income"),
                          ("ms-c-depcost-depinterest", "wm_deposit_cost", "wm_deposit_interest"),
                          ("ms-c-depinterest-wmnii", "wm_deposit_interest", "wm_nii")):
        i = g.interactions[iid]
        assert str(i.edge_type) == "identity" and i.quantified and (i.source_id, i.target_id) == (P + src, P + tgt), iid
    assert g.interactions["ms-c-depinterest-wmnii"].forward.effect.mean() < 0
    assert _link(g, FED, P + "wm_sweep_deposits").transition.sign == "-"         # cash sorting
    assert _link(g, P + "wm_sweep_deposits", P + "wm_deposit_cost").transition.sign == "-"


def test_asset_based_fees_follow_markets_with_a_month_lag(g):
    i = g.interactions["ms-c-equity-amfees"]
    assert i.quantified and i.transition.evidence.magnitude == "broker"
    elasticity = i.forward.effect.mean() * g.subentities[P + "wm_asset_mgmt_fees"].scale / g.subentities[EQ].scale
    assert 0 < elasticity < 1                    # a fee base that is only partly equities moves less than the market
    assert i.forward.kernel.lag.mean() >= 20
    assert str(g.interactions["ms-c-feeassets-amfees"].edge_type) == "identity"
    for iid in ("ms-c-nna-clientassets", "ms-c-feeflows-feeassets", "ms-c-imflows-aum"):
        i = g.interactions[iid]
        assert str(i.edge_type) == "stock_flow" and i.forward.kernel.accumulates, iid
    # every tagged step was converted, or says why it could not be
    assert not [k for k, n in NOTES.items() if n.startswith(("identity:", "stock-flow:", "matrix:"))]


def test_deferred_pay_offsets_its_hedge_and_pay_follows_revenue(g):
    assert _link(g, EQ, P + "wm_transactional").transition.sign == "+"
    assert _link(g, EQ, P + "compensation_expense").transition.sign == "-"        # the offset
    comp = _link(g, REV, P + "compensation_expense")                            # pay = ratio x revenue (negative)
    assert str(comp.edge_type) == "identity" and comp.forward.effect.mean() < 0
    ratio = _link(g, REV, P + "comp_ratio")
    assert ratio.transition.sign == "-" and not ratio.quantified
    adv = _link(g, DEALS, P + "completed_ma_volume").transition
    assert "quarter" in adv.timing.onset                                          # advisory waits for completion


def test_marks_reach_capital_not_income(g):
    reached = _reach(g, P + "aoci")
    assert P + "cet1_capital" in reached and P + "cet1_ratio" in reached
    assert not reached & {NI, REV, PRETAX}


def test_capital_is_a_stock_with_flows_and_the_leverage_ratio_can_bind(g):
    c = g.compositions["ms.comp.capital_sources_uses"]
    assert c.additive is False
    for src, sign in ((NI, "+"), (P + "buybacks", "-"), (P + "common_dividends", "-"), (P + "aoci", "+")):
        i = _link(g, src, c.total)
        assert str(i.edge_type) != "accounting" and i.transition.sign == sign, src
        assert (str(i.edge_type) == "stock_flow") is (src != P + "aoci"), src           # AOCI is a stock: sign-only
    assert _link(g, P + "cet1_requirement", P + "buybacks").transition.sign == "-"
    assert _link(g, P + "slr", P + "buybacks").transition.sign == "+"
    assert _link(g, P + "prime_balances", P + "leverage_exposure").transition.sign == "+"


def test_only_evidenced_links_carry_new_sizes(g):
    new_calibrated = {i.id for i in _ms_links(g) if i.id.startswith("ms-c-") and i.quantified
                      and str(i.edge_type) == "causal"}
    assert new_calibrated == {"ms-c-equity-amfees"}
    assert g.interactions["s75"].transition.evidence.magnitude == "documented"
    for iid in ("s13", "s15", "s17"):                                            # kept sizes, scoped
        tr = g.interactions[iid].transition
        assert tr is not None and tr.evidence.magnitude == "assumption" and tr.unresolved, iid


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _ms_links(g):
        tr = i.transition
        if tr is None:
            continue
        assert set(tr.evidence.sources) <= SOURCES or i.id.startswith(("jpm-", "m", "s0")), (i.id, tr.evidence.sources)
        for need in tr.unresolved:
            if not i.id.startswith(("ms-", "s13", "s15", "s17", "s75")):
                continue
            seen += 1
            assert need.status != "not_yet_reviewed", (i.id, need.input)
            if need.status == "not_disclosed_in_reviewed_sources":
                assert any(s in SOURCES for s in need.searched) and any(s.startswith("corpus:") for s in need.searched)
            assert set(need.found_in) <= SOURCES, (i.id, need.found_in)
    assert seen >= 60


def test_identities_and_stock_flows_are_declared_and_reconcile(g):
    for iid, (form, target) in IDENTITIES.items():
        x = g.identities[iid]
        assert x.entity_id == MS and x.form == form and x.target == P + target, iid
    rows = {r["identity_id"]: r for r in reconcile_identities(g, model_levels(g, "median"))}
    assert all(rows[iid]["status"] == "ok" for iid in IDENTITIES), {k: rows[k]["status"] for k in IDENTITIES}
    rec = {r["composition_id"]: r for r in reconcile(g, model_levels(g, "median"))}
    assert all(rec[cid]["status"] == "ok" for cid, (_t, add) in COMPOSITIONS.items() if add)
    for sfid, stock in STOCK_FLOWS.items():
        x = g.stock_flows[sfid]
        assert x.stock == P + stock and x.period_days == 365
        # a roll-forward closes: opening + inflows - outflows (synthetic dated levels, one year apart)
        opening = 100.0
        flows = {v: [("2026-12-31", 10.0)] for v, _ in x.terms()}
        closing = opening + sum(e * 10.0 for _v, e in x.terms())
        row = reconcile_stock_flows(g, {**flows, x.stock: [("2025-12-31", opening), ("2026-12-31", closing)]})
        assert [r["status"] for r in row if r["stock_flow_id"] == sfid] == ["ok"], sfid


# -- generalization -------------------------------------------------------------------------------------------------------
def test_generalization_trace_a_yen_carry_unwind(g):
    """A yen carry unwind: no Morgan Stanley path starts there. The structure carries it through volatility to sales and
    trading (s15) and WM revenue (s17), both calibrated; through lower equity prices to asset-based fees (the calibrated
    market-level step after an uncalibrated volatility-to-price step), IM marks, prime balances, deferred pay and the
    IPO window; through wider spreads to provisions, FICC marks, ISG loan marks and debt issuance; through the yen to
    the Japanese joint venture's dollar income; and through prime balances and leverage exposure to the SLR and buybacks.
    It stops at the composition totals it reaches, and once at the trace depth inside the net-new-asset funnel."""
    tr = trace(g, "dollar_yen.carry_positioning", MS)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    assert routes[("s10", "s15")]["ends_at"] == P + "trading_revenue" and not routes[("s10", "s15")]["uncalibrated_steps"]
    assert routes[("s10", "s17")]["ends_at"] == WM
    assert ("m18", "ms-c-usdjpy-isgother", "ms-a-isg-isg-other-revenue") in routes
    assert ("s10", "jpm-c-vol-equityindex", "ms-c-equity-amfees") in routes        # identity targets are endpoints
    assert ("s10", "jpm-c-vol-spread", "ms-c-spread-provision", "ms-a-pretax-provision-for-credit-losses") in routes
    ends = {r["ends_at"] for r in tr["routes"] if r["reaches_endpoint"]}
    assert {P + "trading_revenue", WM, ISG, IM, P + "ib_fees", PRETAX, P + "noninterest_expense", P + "cet1_ratio",
            P + "slr", P + "wm_asset_mgmt_fees", P + "wm_deposit_interest"} <= ends
    assert all(r["reaches_endpoint"] for r in tr["routes"])
    # through the totals it goes on to net income and capital
    deep = trace(g, "dollar_yen.carry_positioning", MS, max_depth=10, through_totals=True)
    assert {NI, P + "cet1_capital"} <= {t for r in deep["routes"] for t in [r["ends_at"], *r.get("passes", [])]}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["ms-a-seg-wealth-revenue"]["dependency_type"] == "accounting_identity"
    assert rels["ms-c-fed-sweep"]["status"] == "represented_uncalibrated"
    assert rels["ms-c-fed-sweep"]["axelrod"]["transition"]["sign"] == "-"
    assert rels["s75"]["axelrod"]["transition"]["evidence"]["magnitude"] == "documented"


def test_new_objects_reach_the_api(client):
    ids = f"{P}wm_sweep_deposits,{P}wm_fee_based_assets,{P}cet1_capital,{P}net_revenue"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and P + "wm_deposits" in got
    view = v1.construction(client, MS)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, MS, FED)
    assert tr["reaches_endpoint"]
