"""JPMorgan's business construction (Oct 18): the compositions, operating and financial paths, and their transitions in
data/worlds/sally_demo/construction/jpmorgan.yaml, checked in the loaded model, in the v4.1.4 export, and through the
service API (docs/construction/jpmorgan.md has the gap register these tests close). The test of whether the method
built for an automaker and an insurer carries over to a bank. Converted (Oct 18) to one driving view per total, product,
ratio and difference identities, a CET1 stock-flow, a lines x segments matrix and state-dependent responses. Sally's
world loads once for the module; no client data is read."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import construction_view, trace
from axelrod_wm.model.construction import (
    composition_role,
    model_levels,
    reconcile_identities,
    reconcile_matrices,
    reconcile_stock_flows,
    validate_construction,
)
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.scenario import v1_reads as v1

JPM = "jpmorgan"
NII, REV, NI = "jpmorgan.net_interest_income", "jpmorgan.net_revenue", "jpmorgan.net_income"
FED, UST10 = "federal_reserve.policy_rate", "us_treasuries.yield_10y"

COMPOSITIONS = {   # id -> (total, additive)
    "jpm.comp.revenue_by_line": (REV, True),
    "jpm.comp.revenue_by_segment": (REV, True),
    "jpm.comp.ccb_lines": ("jpmorgan.ccb_revenue", True),
    "jpm.comp.cib_businesses": ("jpmorgan.cib_revenue", True),
    "jpm.comp.markets": ("jpmorgan.markets_revenue", True),
    "jpm.comp.awm_businesses": ("jpmorgan.awm_revenue", True),
    "jpm.comp.pretax": ("jpmorgan.pretax_income", True),
    "jpm.comp.net_income": (NI, True),
    "jpm.comp.net_income_by_segment": (NI, True),
    "jpm.comp.expense": ("jpmorgan.noninterest_expense", True),
    "jpm.comp.credit_costs": ("jpmorgan.provision_for_credit_losses", True),
    "jpm.comp.card_provision": ("jpmorgan.card_provision", True),
    "jpm.comp.wholesale_provision": ("jpmorgan.wholesale_provision", True),
    "jpm.comp.nii_balance_sheet": (NII, True),
    "jpm.comp.interest_income": ("jpmorgan.interest_income", True),
    "jpm.comp.interest_expense": ("jpmorgan.interest_expense", True),
    "jpm.comp.loans": ("jpmorgan.avg_loans", True),
}
RECONCILING = {"jpm.comp.revenue_by_segment", "jpm.comp.net_income_by_segment"}   # observed, never driving
IDENTITIES = {"jpm.id.nib_deposits": "product", "jpm.id.ib_deposits": "difference", "jpm.id.deposit_expense": "product",
              "jpm.id.cash_income": "product", "jpm.id.loan_income": "product", "jpm.id.securities_income": "product",
              "jpm.id.card_nco": "product", "jpm.id.wholesale_nco": "product", "jpm.id.am_fees": "product",
              "jpm.id.card_income": "product", "jpm.id.cet1_ratio": "ratio", "jpm.id.nii_ex_markets": "difference"}
# views where the business leaves something out (Corporate, other lines, other loans); the others
# are exact splits as reported (an identity, or a product split with no remainder)
WITH_REMAINDER = {"jpm.comp.revenue_by_line", "jpm.comp.revenue_by_segment", "jpm.comp.cib_businesses",
                  "jpm.comp.net_income_by_segment", "jpm.comp.expense", "jpm.comp.credit_costs",
                  "jpm.comp.interest_income", "jpm.comp.interest_expense", "jpm.comp.loans"}
PATHS = {  # a bank's economics -> the named path(s) that carry them
    "rates, deposit betas and NII": ["jpm.path.rates_nii"],
    "securities repricing and the long end": ["jpm.path.securities_reinvestment", "jpm.path.long_end"],
    "markets and volatility": ["jpm.path.markets"],
    "deal activity and investment banking fees": ["jpm.path.deals_ib"],
    "card and payments": ["jpm.path.card_growth"],
    "asset management fees": ["jpm.path.asset_management"],
    "credit cycle": ["jpm.path.card_credit", "jpm.path.wholesale_credit"],
    "expenses and operating leverage": ["jpm.path.expense_inflation"],
    "capital, buybacks and dividends": ["jpm.path.capital_payout", "jpm.path.capital_requirements",
                                        "jpm.path.balance_sheet_growth"],
}
SOURCES = {"jpm.wb", "jpm.co", "jpm.r1", "jpm.r2", "jpm.r3", "jpm.r4", "jpm.r5", "jpm.r6", "jpm.r7", "jpm.r8", "jpm.r9",
           "jpm.r10", "jpm.r11", "jpm.x1", "jpm.macro", "jpm.peer", "jpm.pub"}


@pytest.fixture(scope="module")
def client():
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
    """One standard unit in native units: the scale itself, or the log scale times the level for a lognormal."""
    return sub.scale * (math.exp(sub.anchor) if _lognormal(sub) else 1.0)


def _level(sub) -> float:
    return math.exp(sub.anchor) if _lognormal(sub) else sub.anchor


def _parts(c) -> list[str]:
    return [*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])]


def _link(g, src, tgt):
    hits = [i for i in g.active_interactions() if i.source_id == src and i.target_id == tgt]
    assert len(hits) == 1, (src, tgt, [i.id for i in hits])
    return hits[0]


def _jpm_links(g):
    own = set(g.entities[JPM].subentity_ids)
    return [i for i in g.active_interactions() if i.source_id in own or i.target_id in own]


def _reach(g, start, through=None):
    out_of = {}
    for i in g.active_interactions():
        if through is None or through(i):
            out_of.setdefault(i.source_id, []).append(i.target_id)
    seen, stack = set(), [start]
    while stack:
        v = stack.pop()
        if v not in seen:
            seen.add(v)
            stack += out_of.get(v, [])
    return seen


# -- structure ---------------------------------------------------------------------------------------------------------
def test_no_construction_problems_for_jpmorgan(g):
    assert construction_view(g, JPM)["problems"] == []
    assert not [p for p in validate_construction(g) if "jpmorgan" in p or "jpm." in p or "jpm-" in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == JPM and c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        if cid in WITH_REMAINDER:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)                          # one unit within a view
        if cid in RECONCILING:                                          # observed against the total, never driving it
            assert not [i.id for i in g.active_interactions() if i.source_id in _parts(c) and i.target_id == c.total
                        and str(i.edge_type) == "accounting"], cid
            continue
        for sid in _parts(c):
            i = _link(g, sid, c.total)
            assert str(i.edge_type) == "accounting" and i.quantified and i.forward.effect.mean() > 0, (cid, sid)
            assert i.forward.effect.sd() <= 0.01                         # a fixed weight, not a fitted coefficient
            w = i.forward.effect.mean()                                  # the part's native sd over the total's
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
            assert p.entity_id == JPM and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != JPM:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)   # no size is claimed


def test_shared_driver_responses_are_parallel_branches(g):
    p = g.paths["jpm.path.rates_nii"]
    by = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}
    assert {"beta", "migration", "balances", "loans", "cash", "markets", "markets_nii", "unrepresented"} <= set(by)
    assert {i.source_id for i in by.values()} == {FED}
    q = g.paths["jpm.path.long_end"]
    assert {g.interactions[s.interaction_id].source_id for s in q.steps if s.branch} == {UST10}


def test_the_reduced_form_carries_only_what_the_identities_do_not(g):
    """m25 is a branch of the rates path beside the exact deposit and cash channels, sized net of them; the other reduced
    forms stay out of their structural paths."""
    steps = {pid: {s.interaction_id: s.branch for s in p.steps} for pid, p in g.paths.items() if p.entity_id == JPM}
    assert steps["jpm.path.rates_nii"]["m25"] == "unrepresented"
    m25 = g.interactions["m25"]
    assert m25.quantified and m25.state and m25.state.asymmetry and "netting" in (m25.note or "")
    assert m25.transition.evidence.magnitude == "inferred"
    assert not {"jpm-c-ust10-nii", "s18"} & set(steps["jpm.path.long_end"])
    assert "s14" not in steps["jpm.path.markets"]


# -- a bank's economics ---------------------------------------------------------------------------------------------------
def test_values_name_their_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == JPM and s.id != "jpmorgan.share_price"]
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]
    assert g.subentities[NII].features["metric"] == "net_interest_income"


def test_markets_nii_is_counted_once_through_a_difference_identity(g):
    line = g.compositions["jpm.comp.revenue_by_line"]
    assert "jpmorgan.nii_ex_markets" in line.members and "jpmorgan.markets_revenue" in line.members
    assert NII not in line.members and not line.eliminations
    x = g.identities["jpm.id.nii_ex_markets"]
    assert x.form == "difference" and x.target == "jpmorgan.nii_ex_markets"
    assert {v for v, _ in x.terms()} == {NII, "jpmorgan.markets_nii"}
    up = g.interactions["jpm-c-fed-mktnii"]
    down = g.interactions["jpm-c-fed-mktfunding"].transition
    assert up.target_id == "jpmorgan.markets_nii" and up.transition.sign == "-" and down.sign == "-"


def test_one_driving_view_per_total_and_the_segments_reconcile(g):
    assert composition_role(g, "jpm.comp.revenue_by_line") == "driving"
    assert composition_role(g, "jpm.comp.net_income") == "driving"
    assert {cid for cid in COMPOSITIONS if composition_role(g, cid) == "reconciling"} == RECONCILING
    m = g.matrices["jpm.mx.revenue"]
    assert m.rows == "jpm.comp.revenue_by_line" and m.columns == "jpm.comp.revenue_by_segment" and m.driving == m.rows
    assert [r for r in reconcile_matrices(g) if "jpm.mx.revenue" in str(r)]   # reported; its cells are not built


def test_segment_views_are_separate_from_the_driven_view(g):
    line, seg = g.compositions["jpm.comp.revenue_by_line"], g.compositions["jpm.comp.revenue_by_segment"]
    assert not set(_parts(line)) & set(_parts(seg))
    seg_side = {seg.total, *_parts(seg)} - {REV}
    crossing = [i.id for i in g.active_interactions()
                if i.source_id in set(_parts(line)) and i.target_id in seg_side | {"jpmorgan.cib_markets_adjustments"}]
    assert crossing == ["jpm-c-bridge-markets-cib"] and not g.interactions["jpm-c-bridge-markets-cib"].quantified
    assert g.compositions["jpm.comp.net_income_by_segment"].residual == "jpmorgan.corporate_net_income"


def test_identities_have_their_term_links_and_reconcile(g):
    for iid, form in IDENTITIES.items():
        x = g.identities[iid]
        assert x.entity_id == JPM and x.form == form, iid
        for v, _ in x.terms():
            i = _link(g, v, x.target)
            assert str(i.edge_type) == "identity" and i.identity == iid and i.quantified, (iid, v)
    rows = {r["identity_id"]: r for r in reconcile_identities(g, model_levels(g, "median"))}
    assert {iid: rows[iid]["status"] for iid in IDENTITIES} == {iid: "ok" for iid in IDENTITIES}


def test_capital_is_a_stock_that_rolls_forward(g):
    sf = g.stock_flows["jpm.sf.cet1"]
    assert sf.stock == "jpmorgan.cet1_capital" and sf.inflows == [NI]
    assert set(sf.outflows) == {"jpmorgan.common_dividends", "jpmorgan.buybacks"}
    for src in (NI, "jpmorgan.buybacks", "jpmorgan.common_dividends"):
        i = _link(g, src, sf.stock)
        assert str(i.edge_type) == "stock_flow" and i.identity == "jpm.sf.cet1", src
    aoci = _link(g, "jpmorgan.aoci", sf.stock)                        # a level, not a flow: a signed link
    assert str(aoci.edge_type) != "stock_flow" and aoci.transition.sign == "+"
    lv = model_levels(g, "median")
    opening = lv[sf.stock]
    closing = opening + lv[NI] - lv["jpmorgan.common_dividends"] - lv["jpmorgan.buybacks"]
    series = {sf.stock: [("2026-01-01", opening), ("2026-12-31", closing)],
              **{v: [("2026-12-31", lv[v])] for v in (NI, "jpmorgan.common_dividends", "jpmorgan.buybacks")}}
    rows = [r for r in reconcile_stock_flows(g, series) if r["stock_flow_id"] == "jpm.sf.cet1"]
    assert [r["status"] for r in rows] == ["ok"]
    one_level = reconcile_stock_flows(g, {sf.stock: [("2026-06-30", opening)]})   # one dated level: nothing to check
    assert not [r for r in one_level if r["entity_id"] == JPM]


def test_deposit_beta_is_calibrated_from_the_research_asymmetric_and_lags(g):
    i = g.interactions["jpm-c-fed-depcost"]
    assert i.quantified and i.transition.evidence.magnitude == "broker"
    per = g.subentities["jpmorgan.ib_deposit_cost"].scale / g.subentities[FED].scale
    up, down = i.state.asymmetry.rises["mu"] * per, i.state.asymmetry.falls["mu"] * per
    assert 0.4 <= down < up <= 0.6                                    # cumulative betas, lower in cuts than in hikes
    assert i.forward.kernel.lag.mean() >= 90                           # it builds over quarters


def test_only_evidenced_links_carry_new_sizes(g):
    causal = [i for i in _jpm_links(g) if i.id.startswith("jpm-c-") and str(i.edge_type) not in ("identity", "stock_flow")]
    assert {i.id for i in causal if i.quantified} == {"jpm-c-fed-depcost", "jpm-c-ust10-nii", "jpm-c-fed-cashyield"}
    assert g.interactions["jpm-c-ust10-nii"].transition.evidence.magnitude == "documented"
    for iid in ("s12", "s14", "s18"):                                 # the existing records keep their sizes, scoped
        tr = g.interactions[iid].transition
        assert tr is not None and tr.evidence.magnitude == "assumption" and tr.unresolved, iid


def test_state_dependent_responses(g):
    flip = g.interactions["jpm-c-purchases-secyield"].state.sign_flip
    gate = g.interactions["jpm-c-ratio-buybacks"].state.threshold
    assert flip.value == "jpmorgan.new_purchase_yield" and gate.value == "jpmorgan.cet1_ratio"


def test_two_credit_clocks(g):
    unemp = "us_economy.unemployment_rate"
    assert _link(g, unemp, "jpmorgan.card_reserve_build").transition.sign == "-"     # CECL: the outlook, at once
    assert not [i for i in g.active_interactions() if i.source_id == unemp and i.target_id == "jpmorgan.card_nco_rate"]
    lag = _link(g, "jpmorgan.card_delinquency_rate", "jpmorgan.card_nco_rate")       # losses: through delinquency
    assert "quarter" in lag.transition.timing.onset and lag.transition.sign == "+"
    growth = _link(g, "jpmorgan.card_loans", "jpmorgan.card_reserve_build")          # growth costs a day-one reserve
    assert growth.transition.sign == "-"


def test_marks_reach_capital_not_income(g):
    reached = _reach(g, "jpmorgan.aoci")
    assert "jpmorgan.cet1_capital" in reached and "jpmorgan.cet1_ratio" in reached
    assert not reached & {NI, REV, NII, "jpmorgan.pretax_income"}


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _jpm_links(g):
        tr = i.transition
        if tr is None:
            continue
        assert set(tr.evidence.sources) <= SOURCES, (i.id, tr.evidence.sources)
        for need in tr.unresolved:
            seen += 1
            assert need.status != "not_yet_reviewed", (i.id, need.input)
            if need.status == "not_disclosed_in_reviewed_sources":
                assert any(s in SOURCES for s in need.searched) and any(s.startswith("corpus:") for s in need.searched)
            assert set(need.found_in) <= SOURCES, (i.id, need.found_in)
    assert seen >= 30


# -- generalization -------------------------------------------------------------------------------------------------------
def test_generalization_trace_an_oil_shock(g):
    """An oil-price shock: no JPMorgan path starts there. The structure carries it to firmwide NII through the Fed's
    response to inflation (m01 -> m05 -> m06 -> m25, calibrated) and through the long end (m11 -> m12 ->
    jpm-c-ust10-nii, calibrated); to card credit through growth and unemployment (CECL reserve now, charge-offs after
    delinquencies, uncalibrated); to expenses through wage inflation; to IB fees through growth and deals (s09 -> s12,
    calibrated); and to capital through the AFS mark. It stops at the share price (nothing leads on) and, at the trace
    depth, inside the securities and asset-management chains."""
    tr = trace(g, "oil.brent", JPM)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    assert routes[("m01", "m05", "m06", "m25")]["ends_at"] == NII and not routes[("m01", "m05", "m06", "m25")]["uncalibrated_steps"]
    assert routes[("m04", "s09", "s12", "jpm-a-rev-ib-fees")]["ends_at"] == REV
    assert ("m04", "jpm-c-gdp-unemp", "jpm-c-unemp-cardreserve", "jpm-a-cardprov-card-reserve-build") in routes
    assert ("m01", "m05", "jpm-c-cpi-comp", "jpm-a-exp-compensation-expense") in routes
    ends = {r["ends_at"] for r in tr["routes"] if r["reaches_endpoint"]}
    assert {NII, REV, "jpmorgan.card_provision", "jpmorgan.noninterest_expense", "jpmorgan.cet1_ratio",
            "jpmorgan.interest_expense", "jpmorgan.cet1_capital"} <= ends
    short_stops = {r["ends_at"] for r in tr["routes"] if not r["reaches_endpoint"] and len(r["steps"]) < 8}
    assert short_stops == {"jpmorgan.share_price"}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["jpm-a-rev-nii-ex-markets"]["dependency_type"] == "accounting_identity"
    assert rels["jpm-c-depcost-expense"]["axelrod"]["transition"]["sign"] == "-"
    assert rels["jpm-c-aoci-cet1"]["status"] == "represented_uncalibrated"
    assert rels["m25"]["axelrod"]["transition"]["evidence"]["magnitude"] == "inferred"


def test_new_objects_reach_the_api(client):
    ids = "jpmorgan.ib_deposit_cost,jpmorgan.card_reserve_build,jpmorgan.cet1_capital,jpmorgan.net_revenue"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and "jpmorgan.deposit_interest_expense" in got
    view = v1.construction(client, JPM)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, JPM, FED)
    assert tr["reaches_endpoint"]
