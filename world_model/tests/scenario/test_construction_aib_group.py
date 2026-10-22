"""AIB Group's business construction (Oct 18): the compositions, operating and financial paths, and their transitions in
<client root>/worlds/sally_demo/construction/aib_group.yaml, checked in the loaded model, in the v4.1.4 export, and through the
service API (world_model/docs/construction/aib_group.md has the gap register these tests close). The second bank after JPMorgan,
in its own reporting: an Irish retail and commercial bank (IFRS, EUR) whose NII follows the ECB through central bank
cash, floating loans and low deposit betas, offset by a structural hedge. Sally's world loads once for the module; no
client data is read."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import construction_view, trace
from axelrod_wm.model.construction import (
    model_levels,
    reconcile_identities,
    reconciling_views,
    validate_construction,
)
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.clients import skip_without_client
from tests.scenario import v1_reads as v1

skip_without_client('sally_demo')

AIB = "aib_group"
NII, TOI = "aib_group.net_interest_income", "aib_group.total_operating_income"
PBT, PAT = "aib_group.profit_before_tax", "aib_group.profit_after_tax"
ECB, BUND = "ecb.policy_rate", "bunds.yield_10y"

COMPOSITIONS = {   # id -> (total, additive)
    "aib.comp.income_by_line": (TOI, True),
    "aib.comp.income_by_segment": (TOI, True),
    "aib.comp.expenses": ("aib_group.operating_expenses", True),
    "aib.comp.ecl_by_portfolio": ("aib_group.ecl_charge", True),
    "aib.comp.mortgage_ecl": ("aib_group.mortgage_ecl", True),
    "aib.comp.business_ecl": ("aib_group.business_ecl", True),
    "aib.comp.pbt": (PBT, True),
    "aib.comp.pbt_by_segment": (PBT, True),
    "aib.comp.profit_after_tax": (PAT, True),
    "aib.comp.nii": (NII, True),
    "aib.comp.interest_income": ("aib_group.interest_income", True),
    "aib.comp.interest_expense": ("aib_group.interest_expense", True),
    "aib.comp.loans_by_portfolio": ("aib_group.gross_loans", True),
    "aib.comp.deposits": ("aib_group.customer_deposits", True),
    "aib.comp.capital_roll_forward": ("aib_group.cet1_capital", False),
}
# views where the business leaves something out (Group, other income, exceptional items, other lines); the others are
# identities or exact splits
WITH_REMAINDER = {"aib.comp.income_by_line", "aib.comp.income_by_segment", "aib.comp.expenses", "aib.comp.ecl_by_portfolio",
                  "aib.comp.pbt", "aib.comp.pbt_by_segment", "aib.comp.interest_income", "aib.comp.interest_expense",
                  "aib.comp.loans_by_portfolio"}
PATHS = {  # the bank's economics -> the named path(s) that carry them
    "ECB rates, deposit betas, central bank cash and NII": ["aib.path.rates_nii"],
    "structural hedge and the euro long end": ["aib.path.structural_hedge"],
    "mortgage book": ["aib.path.mortgage_lending", "aib.path.house_prices_credit"],
    "cost of risk and the Irish economy": ["aib.path.credit_cycle", "aib.path.house_prices_credit"],
    "fees": ["aib.path.fees", "aib.path.wealth_fees"],
    "costs": ["aib.path.cost_inflation"],
    "the UK": ["aib.path.uk_rates"],
    "capital and distributions": ["aib.path.capital_distributions", "aib.path.capital_requirements",
                                  "aib.path.balance_sheet_growth"],
    "the State's sell-down": ["aib.path.state_selldown"],
}
# one view drives each total; the segment views reconcile (drives: false)
RECONCILING = {"aib.comp.income_by_segment", "aib.comp.pbt_by_segment"}
IDENTITIES = {  # id -> (form, target)
    "aib.id.cash_income": ("product", "aib_group.cash_interest_income"),
    "aib.id.hedge_spread": ("difference", "aib_group.hedge_spread"),
    "aib.id.hedge_income": ("product", "aib_group.structural_hedge_income"),
    "aib.id.loan_income": ("product", "aib_group.loan_interest_income"),
    "aib.id.deposit_expense": ("product", "aib_group.deposit_interest_expense"),
    "aib.id.securities_income": ("product", "aib_group.securities_interest_income"),
    "aib.id.new_lending": ("product", "aib_group.new_mortgage_lending"),
    "aib.id.rwa": ("product", "aib_group.rwa"),
    "aib.id.cet1_ratio": ("ratio", "aib_group.cet1_ratio"),
    "aib.id.dividends": ("product", "aib_group.ordinary_dividends"),
}
STOCK_FLOWS = {"aib.sf.mortgage_book": "aib_group.mortgage_book", "aib.sf.cet1": "aib_group.cet1_capital"}
SOURCES = {"aib.r1", "aib.r2", "aib.peer", "aib.peer2", "aib.macro", "aib.pub"}


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
    return sub.scale * (math.exp(sub.anchor) if _lognormal(sub) else 1.0)


def _level(sub) -> float:
    return math.exp(sub.anchor) if _lognormal(sub) else sub.anchor


def _parts(c) -> list[str]:
    return [*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])]


def _link(g, src, tgt):
    hits = [i for i in g.active_interactions() if i.source_id == src and i.target_id == tgt]
    assert len(hits) == 1, (src, tgt, [i.id for i in hits])
    return hits[0]


def _aib_links(g):
    own = set(g.entities[AIB].subentity_ids)
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
def test_no_construction_problems_for_aib(g):
    assert construction_view(g, AIB)["problems"] == []
    assert not [p for p in validate_construction(g) if "aib_group" in p or "aib." in p or "aib-" in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == AIB and c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        if cid in WITH_REMAINDER:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)
        for sid in _parts(c):
            i = _link(g, sid, c.total)
            if cid in RECONCILING:                                       # observed and reconciled, never driven
                assert str(i.edge_type) == "accounting" and not i.quantified and i.transition.sign == "+", (cid, sid)
                continue
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
            assert p.entity_id == AIB and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != AIB:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)


def test_shared_driver_responses_are_parallel_branches(g):
    p = g.paths["aib.path.rates_nii"]
    by = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}
    assert {"short_rate", "loans", "beta", "migration", "wholesale", "credit"} <= set(by)
    assert {i.source_id for i in by.values()} == {ECB}
    q = g.paths["aib.path.structural_hedge"]
    assert {g.interactions[s.interaction_id].source_id for s in q.steps if s.branch} == {BUND}
    h = g.paths["aib.path.house_prices_credit"]
    assert {g.interactions[s.interaction_id].source_id for s in h.steps if s.branch} == {"ireland_economy.house_price_growth"}


def test_reduced_form_is_never_a_step_of_its_structural_path(g):
    steps = {s.interaction_id for s in g.paths["aib.path.rates_nii"].steps}
    assert "s32" not in steps
    tr = g.interactions["s32"].transition
    assert tr is not None and tr.evidence.magnitude == "assumption" and tr.unresolved
    assert g.interactions["s32"].forward.effect.mean() == pytest.approx(0.65)          # Sally's record keeps its size


# -- a deposit-rich euro bank's economics ---------------------------------------------------------------------------------
def test_values_name_their_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == AIB and s.id != "aib_group.share_price"]
    assert len(own) >= 60
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]
    assert g.subentities[NII].features["metric"] == "net_interest_income"
    assert all(s.unit.startswith("€") or s.unit == "pct" for s in own)                # EUR reporting, no dollars


def test_the_structural_hedge_is_a_counter_path_to_the_ecb(g):
    """A cut lowers central bank cash and floating-loan income at once but raises the hedge's net interest (it pays
    floating); the long end then rolls the hedge's fixed yield slowly."""
    short = "aib_group.short_rate"
    assert _link(g, ECB, short).transition.sign == "+"
    cash = _link(g, short, "aib_group.cash_interest_income")
    spread = _link(g, short, "aib_group.hedge_spread")
    assert str(cash.edge_type) == "identity" and cash.forward.effect.mean() > 0
    assert str(spread.edge_type) == "identity" and spread.forward.effect.mean() < 0      # the hedge pays floating
    assert _link(g, ECB, "aib_group.loan_yield").transition.sign == "+"
    roll = _link(g, BUND, "aib_group.hedge_yield")                                    # sized from a named peer
    assert roll.quantified and roll.transition.evidence.magnitude == "peer"
    assert roll.forward.effect.mean() == pytest.approx(0.2) and roll.forward.effect.sd() == pytest.approx(0.1)
    assert roll.forward.kernel.lag.mean() >= 365 and "years" in roll.transition.timing.build


def test_deposit_beta_lags_and_migration_shrinks_the_hedgeable_base(g):
    beta = _link(g, ECB, "aib_group.deposit_cost").transition
    assert beta.sign == "+" and "quarter" in beta.timing.build
    assert _link(g, ECB, "aib_group.current_accounts").transition.sign == "-"
    assert _link(g, "aib_group.current_accounts", "aib_group.structural_hedge_notional").transition.sign == "+"
    assert _link(g, "aib_group.current_accounts", "aib_group.interest_bearing_deposits").transition.sign == "-"
    expense = _link(g, "aib_group.interest_bearing_deposits", "aib_group.deposit_interest_expense")
    assert str(expense.edge_type) == "identity" and expense.forward.effect.mean() < 0    # a charge held negative


def test_rates_have_a_credit_counter_path(g):
    assert _link(g, ECB, "aib_group.property_ecl").transition.sign == "-"
    assert _link(g, ECB, "aib_group.npe_ratio").transition.sign == "+"


def test_two_credit_clocks(g):
    un = "ireland_economy.unemployment_rate"
    assert _link(g, un, "aib_group.mortgage_allowance_build").transition.sign == "-"    # IFRS 9: the outlook, at once
    assert not [i for i in g.active_interactions() if i.source_id == un and i.target_id == "aib_group.mortgage_write_offs"]
    late = _link(g, "aib_group.npe_ratio", "aib_group.mortgage_write_offs").transition    # losses: after default
    assert late.sign == "-" and "quarter" in late.timing.onset
    assert _link(g, "ireland_economy.house_price_growth", "aib_group.mortgage_allowance_build").transition.sign == "+"


def test_marks_reach_capital_not_income(g):
    reached = _reach(g, "aib_group.fvoci_reserve")
    assert "aib_group.cet1_capital" in reached and "aib_group.cet1_ratio" in reached
    assert not reached & {PAT, PBT, NII, TOI}


def test_capital_is_a_stock_with_flows_not_an_additive_view(g):
    c = g.compositions["aib.comp.capital_roll_forward"]
    assert c.additive is False
    for src, sign in ((PAT, 1), ("aib_group.buybacks", -1), ("aib_group.ordinary_dividends", -1)):
        i = _link(g, src, c.total)
        assert str(i.edge_type) == "stock_flow" and i.identity == "aib.sf.cet1" and i.polarity() == sign, src
        assert i.forward.kernel.accumulates
    marks = _link(g, "aib_group.fvoci_reserve", c.total)                    # a level inside CET1, not a flow
    assert not marks.quantified and marks.transition.sign == "+"


def test_state_selldown_is_represented(g):
    p = g.paths["aib.path.state_selldown"]
    by = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}
    assert {"stake", "directed_buyback", "placing"} <= set(by)
    assert by["directed_buyback"].transition.sign == "+" and by["placing"].transition.sign == "-"
    assert any(n.input.startswith("the State's remaining shareholding") for n in by["stake"].transition.unresolved)
    assert "zero" in p.active_when                                            # dormant once the sell-down is complete


def test_one_view_drives_each_total(g):
    assert reconciling_views(g).keys() >= RECONCILING
    for cid in RECONCILING:
        assert g.compositions[cid].drives is False


def test_identities_and_stock_flows_exist_and_reconcile(g):
    for iid, (form, target) in IDENTITIES.items():
        x = g.identities[iid]
        assert x.entity_id == AIB and x.form == form and x.target == target, iid
    rows = {r["identity_id"]: r for r in reconcile_identities(g, model_levels(g, "median")) if r["entity_id"] == AIB}
    assert set(rows) == set(IDENTITIES) and all(r["status"] == "ok" for r in rows.values()), rows
    for sid, stock in STOCK_FLOWS.items():
        assert g.stock_flows[sid].stock == stock and g.stock_flows[sid].period_days == 365
    tagged = [i.id for i in _aib_links(g) if (i.note or "").startswith(("identity:", "stock-flow:", "matrix:"))]
    assert tagged == []                                                     # every tag converted, or its note says why not


def test_the_ecb_entries_stay_unsized_so_s32_is_not_counted_twice(g):
    """s32 carries the ECB's net effect on NII; every step below the ECB entries is now an exact identity into NII, so
    the entries carry no size until AIB's own sensitivity is supplied (then size them and retire s32 together)."""
    for tgt in ("aib_group.short_rate", "aib_group.loan_yield", "aib_group.deposit_cost", "aib_group.current_accounts",
                "aib_group.debt_interest_expense"):
        i = _link(g, ECB, tgt)
        assert not i.quantified and "s32" in (i.note or ""), tgt
    new = {i.id for i in _aib_links(g) if i.id.startswith("aib-c-") and i.quantified
           and str(i.edge_type) not in ("identity", "stock_flow")}
    assert new == {"aib-c-bund-hedgeyield"}                                 # the one size: a named peer's hedge roll
    assert g.subentities["aib_group.short_rate"].features.get("proxy_for")


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _aib_links(g):
        tr = i.transition
        if tr is None:
            continue
        assert set(tr.evidence.sources) <= SOURCES, (i.id, tr.evidence.sources)
        for need in tr.unresolved:
            seen += 1
            assert need.status != "not_yet_reviewed", (i.id, need.input)
            if need.status in ("not_disclosed_in_reviewed_sources", "disclosed_not_supplied"):
                assert any(s in SOURCES for s in need.searched) and any(s.startswith("corpus:") for s in need.searched)
            assert set(need.found_in) <= SOURCES, (i.id, need.found_in)
    assert seen >= 30


# -- generalization -------------------------------------------------------------------------------------------------------
def test_generalization_trace_an_oil_shock(g):
    """An oil-price shock: no AIB path starts there. Oil lifts euro inflation, the ECB responds (m03 -> m10), and the
    structure carries it to NII through the calibrated reduced form (s32) and through every parallel rate branch
    (uncalibrated); to costs through wage and vendor inflation; to credit through domestic demand, unemployment and
    defaults (both clocks); to the hedge, securities and FVOCI marks through the long end (s05); and to capital. It
    stops at the share price (nothing leads on) and, at the trace depth, inside the long-end chains that start in the
    US curve."""
    tr = trace(g, "oil.brent", AIB)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    r = routes[("m03", "m10", "s32")]
    assert r["ends_at"] == NII and not r["uncalibrated_steps"]
    assert ("m03", "aib-c-cpi-staff", "aib-a-opex-staff-costs") in routes
    assert ("m03", "m10", "aib-c-ecb-shortrate", "aib-c-shortrate-spread") in routes
    assert not routes[("m03", "m10", "s05", "aib-c-bund-hedgeyield", "aib-c-hedgeyield-spread")]["uncalibrated_steps"]
    assert ("m03", "m10", "aib-c-ecb-dd", "aib-c-dd-unemp", "aib-c-unemp-mortallow", "aib-a-mecl-mortgage-allowance-build") in routes
    assert ("m03", "m10", "s05", "aib-c-bund-fvoci", "aib-c-fvoci-cet1") in routes
    ends = {x["ends_at"] for x in tr["routes"] if x["reaches_endpoint"]}
    assert {NII, TOI, "aib_group.hedge_spread", "aib_group.cash_interest_income", "aib_group.interest_expense",
            "aib_group.operating_expenses", "aib_group.ecl_charge", "aib_group.mortgage_ecl", "aib_group.cet1_capital",
            "aib_group.gross_loans"} <= ends
    short_stops = {x["ends_at"] for x in tr["routes"] if not x["reaches_endpoint"] and len(x["steps"]) < 8}
    assert short_stops == {"aib_group.share_price"}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["aib-a-nii-interest-income"]["dependency_type"] == "accounting_identity"
    assert rels["aib-c-ecb-shortrate"]["status"] == "represented_uncalibrated"
    assert rels["aib-c-ecb-shortrate"]["axelrod"]["transition"]["sign"] == "+"
    assert rels["aib-c-loanyield-income"]["dependency_type"] == "accounting_identity"
    roles = {b["composition_id"]: b["role"] for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert roles["aib.comp.income_by_line"] == "driving" and roles["aib.comp.income_by_segment"] == "reconciling"
    assert rels["s32"]["axelrod"]["transition"]["evidence"]["magnitude"] == "assumption"


def test_new_objects_reach_the_api(client):
    ids = "aib_group.deposit_cost,aib_group.structural_hedge_income,aib_group.cet1_capital,aib_group.total_operating_income"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and "aib_group.deposit_interest_expense" in got
    view = v1.construction(client, AIB)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, AIB, ECB)
    assert tr["reaches_endpoint"]


def test_an_ecb_cut_reports_its_calculation_coverage(client):
    """An ECB cut: NII moves only through the reduced form (a summary link); the ECB entries are excluded as
    uncalibrated with their signs, and the long end (ECB -> Bund -> the peer-sized hedge roll -> exact identities) is
    the own-step route that carries a size."""
    cov = v1.simulate(client, "What if the ECB cut rates by 25bp next quarter?", 365)
    got = {c["interaction_id"] for c in cov["contributed"]}
    assert {"s32", "aib-c-bund-hedgeyield", "aib.id.hedge_income:aib_group.hedge_spread"} <= got
    ex = {c["interaction_id"]: c for c in cov["excluded"]}
    assert ex["aib-c-ecb-shortrate"]["reason"] == "uncalibrated" and ex["aib-c-ecb-depcost"]["sign"] == "+"
    nii = {t["target"]: t for t in cov["targets"]}[NII]
    assert nii["quantified_routes_through_summary_links_only"] >= 1
