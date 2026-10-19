"""MS&AD's business construction (Oct 18): the compositions, operating and financial paths, and their transitions in
data/worlds/sally_demo/construction/msad.yaml, checked in the loaded model, in the v4.1.4 export, and through the
service API (docs/construction/msad.md has the gap register these tests close). The insurer method of the Tokio Marine
build, carried to the peer with its own reporting: domestic non-life by company, international by business, domestic
life, adjusted profit and its bridge to net income, and strategic-equity sale gains as their own part. Sally's world
loads once for the module; no client data is read."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import construction_view, trace
from axelrod_wm.model.construction import (
    model_levels,
    reconcile,
    reconcile_identities,
    reconcile_matrices,
    validate_construction,
)
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.scenario import v1_reads as v1

MSAD = "msad"
GAP, NI, DOM, INTL = "msad.operating_profit", "msad.net_income", "msad.domestic_profit", "msad.international_profit"

COMPOSITIONS = {   # id -> (total, additive)
    "msad.comp.adjusted_profit_by_business": (GAP, True),
    "msad.comp.net_income_bridge": (NI, True),
    "msad.comp.domestic_nonlife_by_company": (DOM, True),
    "msad.comp.domestic_nonlife_by_source": (DOM, True),
    "msad.comp.dnl_investment_income": ("msad.dnl_investment_income", True),
    "msad.comp.dnl_assets_by_class": ("msad.dnl_investment_portfolio", True),
    "msad.comp.dnl_premiums_by_line": ("msad.dnl_npw", True),
    "msad.comp.combined_ratio": ("msad.dnl_combined_ratio", True),
    "msad.comp.international_by_business": (INTL, True),
    "msad.comp.international_by_source": ("msad.intl_profit_cfx", True),
    "msad.comp.domestic_life": ("msad.domestic_life_profit", True),
    "msad.comp.capital_sources_uses": ("msad.excess_capital", False),
}
EXACT = {"msad.comp.combined_ratio"}           # an identity of two ratios: no remainder
RECONCILING = {"msad.comp.domestic_nonlife_by_company"}   # the columns of msad.mx.domestic_nonlife
IDENTITIES = {"msad.id.loss_ratio", "msad.id.expense_ratio", "msad.id.uw_profit", "msad.id.bond_income",
              "msad.id.adjusted_eps"}
STOCK_FLOWS = {"msad.sf.domestic_bonds", "msad.sf.cross_holding_book", "msad.sf.excess_capital"}
PATHS = {  # an insurer's economics -> the named path(s) that carry them
    "premium growth": ["msad.path.policy_growth"],
    "claims inflation and auto repricing": ["msad.path.auto_repricing"],
    "natural catastrophes, catastrophe reserves, reinsurance": ["msad.path.catastrophe_reserves",
                                                               "msad.path.international_underwriting"],
    "US casualty reserves": ["msad.path.us_casualty_reserves"],
    "investment income and the domestic bond portfolio": ["msad.path.domestic_yields", "msad.path.reinvestment",
                                                         "msad.path.fx_hedge_cost", "msad.path.overseas_yields"],
    "marks to equity and ESR": ["msad.path.asset_marks_liabilities", "msad.path.equity_marks"],
    "cross-shareholding reduction": ["msad.path.cross_holding_disposal"],
    "overseas translation": ["msad.path.overseas_translation"],
    "capital and shareholder return": ["msad.path.capital_payout", "msad.path.growth_execution"],
}
SOURCES = {"msad.r1", "msad.r2", "msad.macro", "msad.x1", "msad.peer", "msad.pub", "msad.corpus"}
# conversion tags (identity / stock-flow / matrix / state) live in the construction file's `note`, which the graph
# does not carry: read them from the file
NOTES = {i["id"]: i.get("note") or "" for i in yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "data/worlds/sally_demo/construction/msad.yaml").read_text())["interactions"]}


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


def _msad_links(g):
    own = set(g.entities[MSAD].subentity_ids)
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
def test_no_construction_problems_for_msad(g):
    assert construction_view(g, MSAD)["problems"] == []
    assert not [p for p in validate_construction(g) if "msad" in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == MSAD and c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        if cid not in EXACT:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)                          # one unit within a view
        for sid in _parts(c):
            i = _link(g, sid, c.total)
            assert str(i.edge_type) == "accounting", (cid, sid)
            if cid in RECONCILING:                                       # reconciles, never drives the total
                assert not i.quantified and c.drives is False or not i.quantified, (cid, sid)
                continue
            assert i.quantified and i.forward.effect.sd() <= 0.01        # a fixed weight, not a fitted coefficient
            w = abs(i.forward.effect.mean())                             # the part's native sd over the total's
            assert w == pytest.approx(_native_sd(g.subentities[sid]) / _native_sd(g.subentities[c.total]), abs=0.01), (cid, sid)


def test_priors_reconcile_within_half_a_percent(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        sign = {s: _link(g, s, c.total).polarity() for s in _parts(c)}
        total = _level(g.subentities[c.total])
        parts = sum(sign[s] * _level(g.subentities[s]) for s in _parts(c))
        assert abs(parts - total) <= 0.005 * abs(total), (cid, total, parts)


def test_required_paths_exist(g):
    for need, pids in PATHS.items():
        for pid in pids:
            p = g.paths[pid]
            assert p.entity_id == MSAD and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != MSAD:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)   # no size is claimed


def test_shared_driver_responses_are_parallel_branches(g):
    for pid, start in (("msad.path.domestic_yields", "jgbs.yield_30y"), ("msad.path.overseas_yields", "us_treasuries.yield_10y"),
                       ("msad.path.catastrophe_reserves", "japan_economy.nat_cat_insured_losses"),
                       ("msad.path.cross_holding_disposal", "msad.cross_holding_sales")):
        p = g.paths[pid]
        first = {s.branch: g.interactions[s.interaction_id].source_id for s in p.steps[:2]}
        assert len(first) == 2 and set(first.values()) == {start}, pid


def test_reinvestment_has_its_six_transitions(g):
    """Existing bonds -> redemptions -> eligible cash -> chosen investments -> the bond book (a stock) -> earned income
    (book x book yield, an identity) -> net investment result -> segment and group profit."""
    p = g.paths["msad.path.reinvestment"]
    ids = [s.interaction_id for s in p.steps]
    assert ids[:8] == ["msad-c-portfolio-cash", "msad-c-redeem-cash", "msad-c-cash-invest", "msad-c-invest-income",
                       "msad.id.bond_income:msad.dnl_domestic_bonds", "msad-a-inv-dombond", "msad-a-dnl-inv", "s40"]
    assert g.interactions[ids[0]].source_id == "msad.dnl_domestic_bonds"     # starts at the domestic bond portfolio
    assert str(g.interactions["msad-c-invest-income"].edge_type) == "stock_flow"
    assert {s.branch for s in p.steps[8:]} == {"payout", "capital"}


def test_reduced_forms_are_never_steps_of_their_structural_paths(g):
    steps = {pid: {s.interaction_id for s in p.steps} for pid, p in g.paths.items() if p.entity_id == MSAD}
    assert "s38" not in steps["msad.path.domestic_yields"] and "s38" not in steps["msad.path.reinvestment"]
    assert not {"s36", "s37"} & steps["msad.path.overseas_yields"]


# -- an insurer's economics, MS&AD's reporting -------------------------------------------------------------------------
def test_values_name_their_basis_and_export_metric(g):
    own = [s for s in g.subentities.values() if s.entity_id == MSAD and s.id != "msad.share_price"]
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]
    assert g.subentities[GAP].features["metric"] == "group_adjusted_profit"
    assert g.subentities[DOM].features["metric"] == "domestic_nonlife_adjusted_profit"
    assert g.subentities[INTL].features["metric"] == "international_adjusted_profit"
    assert "Mitsui Sumitomo profit" in g.subentities["msad.msi_profit"].aliases        # no longer on the group value
    assert "Mitsui Sumitomo profit" not in g.subentities[DOM].aliases


def test_adjusted_profit_view_reconciles(g):
    c = g.compositions["msad.comp.adjusted_profit_by_business"]
    assert {DOM, INTL, "msad.domestic_life_profit", "msad.financial_services_profit"} == set(c.members)
    for iid in ("s39", "s40"):                                    # the existing records, now accounting identities
        assert str(g.interactions[iid].edge_type) == "accounting"
    assert "absorbs" in g.subentities[c.residual].features["basis"]   # the residual says what it absorbs


def test_net_income_is_downstream_of_adjusted_profit(g):
    """The bridge runs one way, so no operating change is counted twice in adjusted profit."""
    assert _link(g, GAP, NI).polarity() > 0
    assert _link(g, "msad.reserve_addback", NI).polarity() < 0     # the add-back subtracts
    assert GAP not in _reach(g, NI)


def test_catastrophe_reserve_cushions_net_income_not_adjusted_profit(g):
    cat = "msad.japan_nat_cat_losses"
    assert _link(g, cat, "msad.dnl_incurred_losses").transition.sign == "+"        # hits adjusted profit in full
    assert _link(g, "msad.dnl_incurred_losses", "msad.dnl_underwriting_profit").polarity() < 0
    rev = _link(g, cat, "msad.cat_reserve_provision")
    assert rev.transition.sign == "-" and NOTES["msad-c-cat-reserve"].startswith("state:")    # a threshold rule
    assert [str(p.form) for p in rev.parameters if p.moderator_id == cat] == ["piecewise"]          # acts only above the budget
    # the reversal reaches net income only through the add-back, never adjusted profit
    assert GAP not in _reach(g, "msad.cat_reserve_provision") and NI in _reach(g, "msad.cat_reserve_provision")


def test_sale_gains_are_a_separate_nonrecurring_part(g):
    by_source = g.compositions["msad.comp.domestic_nonlife_by_source"]
    assert "msad.dnl_xholding_gains" in by_source.members and "msad.dnl_investment_income" in by_source.members
    inc = g.compositions["msad.comp.dnl_investment_income"]
    assert "msad.dnl_xholding_gains" not in _parts(inc)                         # never in recurring income
    tr = g.interactions["msad-a-dnl-xgain"].transition
    assert any("definition" in n.input for n in tr.unresolved)                  # the definition question stays open


def test_cross_holding_sales_reach_profit_only_as_gains_and_forgone_dividends(g):
    src = "msad.cross_holding_sales"
    direct = {i.target_id: i.transition.sign for i in g.active_interactions() if i.source_id == src}
    assert direct["msad.dnl_div_domestic_equity"] == "-" and direct["msad.dnl_xholding_gains"] == "+"
    assert direct["msad.cross_holding_book"] == "-"                     # a stock-flow outflow
    assert not set(direct) & {GAP, DOM, "msad.dnl_investment_income"}


def test_marks_never_reach_adjusted_profit(g):
    for start in ("msad.bond_valuation", "msad.liability_economic_value", "msad.cross_holding_book"):
        reached = _reach(g, start)
        assert "msad.esr" in reached or start == "msad.cross_holding_book", start
        if start != "msad.cross_holding_book":
            assert not reached & {GAP, DOM, NI}, start
    # the strategic book reaches profit only by being sold, never by its mark
    assert not [i for i in g.active_interactions() if i.source_id == "msad.cross_holding_book"
                and i.target_id in {GAP, DOM, "msad.dnl_xholding_gains"}]


def test_international_constant_fx_and_translation_are_separate(g):
    t = g.interactions["msad-a-intl-translate"]
    assert (t.source_id, t.target_id) == ("msad.intl_profit_cfx", INTL) and str(t.edge_type) == "accounting"
    assert g.interactions["s35"].source_id == "dollar_yen.usd_jpy" and g.interactions["s35"].quantified


def test_fx_counter_effect_is_represented_and_uncalibrated(g):
    i = g.interactions["msad-c-fx-reserves"]
    assert i.source_id == "dollar_yen.usd_jpy" and i.target_id == "msad.dnl_incurred_losses"
    assert not i.quantified and i.transition.sign == "+"            # more losses, so less underwriting profit
    assert [n.status for n in i.transition.unresolved] == ["not_disclosed_in_reviewed_sources"]


def test_broad_yield_links_state_their_scope(g):
    for iid in ("s36", "s38"):
        tr = g.interactions[iid].transition
        assert tr is not None and "not appl" in tr.mechanism and "Reduced-form" in tr.mechanism, iid
        assert tr.evidence.magnitude == "assumption" and tr.unresolved, iid
    for iid in ("s35", "s37", "s71"):
        assert g.interactions[iid].transition is not None, iid


def test_capital_is_a_stock_with_flows_not_an_additive_view(g):
    c = g.compositions["msad.comp.capital_sources_uses"]
    assert c.additive is False
    sf = g.stock_flows["msad.sf.excess_capital"]
    assert sf.stock == c.total and set(sf.inflows) == {GAP, "msad.cross_holding_sales", "msad.overseas_remittances"}
    assert set(sf.outflows) == {"msad.shareholder_returns", "msad.acquisition_spend"}
    for src, sign in ((GAP, 1), ("msad.cross_holding_sales", 1), ("msad.shareholder_returns", -1)):
        i = _link(g, src, c.total)
        assert str(i.edge_type) == "stock_flow" and i.quantified and i.polarity() == sign, src


def test_shared_drivers_are_reused_not_duplicated(g):
    used = {i.source_id for i in _msad_links(g)}
    assert {"jgbs.yield_30y", "dollar_yen.usd_jpy", "us_treasuries.yield_10y", "japan_capital_markets.equity_index",
            "tokio_marine.japan_claim_severity", "tokio_marine.us_liability_severity",
            "japan_economy.nat_cat_insured_losses", "us_economy.nat_cat_insured_losses"} <= used
    own = set(g.entities[MSAD].subentity_ids)
    assert not [s for s in own if any(k in s for k in ("claim_severity", "us_liability_severity", "yield_30y", "usd_jpy"))]


def test_no_invented_ladder(g):
    own = [s for s in g.subentities.values() if s.entity_id == MSAD]
    assert not [s.id for s in own if any(k in s.id for k in ("maturity", "ladder", "duration"))]
    names = " ".join(n.input for n in g.interactions["msad-c-portfolio-cash"].transition.unresolved)
    assert "maturity ladder" in names


def test_only_existing_records_carry_sizes(g):
    """A new causal link carries a size only when it is an identity or stock-flow term (a derived weight): the supplied
    material has no MS&AD sensitivity to size a behavioural link."""
    sized = [i for i in _msad_links(g) if i.id.startswith("msad-c-") and i.quantified]
    assert sized and all(str(i.edge_type) in ("identity", "stock_flow") for i in sized), [i.id for i in sized]
    for iid in ("s35", "s36", "s37", "s38"):
        assert g.interactions[iid].quantified and g.interactions[iid].transition.evidence.magnitude == "assumption", iid


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _msad_links(g):
        tr = i.transition
        if tr is None or not (i.id.startswith("msad-") or i.id in {"s35", "s36", "s37", "s38", "s39", "s40", "s71"}):
            continue
        assert set(tr.evidence.sources) <= SOURCES, (i.id, tr.evidence.sources)
        for need in tr.unresolved:
            seen += 1
            assert need.status != "not_yet_reviewed", (i.id, need.input)
            if need.status == "not_disclosed_in_reviewed_sources":
                assert any(s in SOURCES for s in need.searched) and any(s.startswith("corpus:") for s in need.searched)
            assert set(need.found_in) <= SOURCES, (i.id, need.found_in)
    assert seen >= 40


def test_converted_identities_stock_flows_matrix_and_state(g):
    assert IDENTITIES == {k for k, x in g.identities.items() if x.entity_id == MSAD}
    assert STOCK_FLOWS == {k for k, x in g.stock_flows.items() if x.entity_id == MSAD}
    levels = model_levels(g, "median")
    rows = {r["identity_id"]: r for r in reconcile_identities(g, levels)}
    assert all(rows[k]["status"] == "ok" for k in IDENTITIES), {k: rows[k]["status"] for k in IDENTITIES}
    assert all(r["status"] == "ok" for r in reconcile(g, levels) if r["entity_id"] == MSAD)
    m = g.matrices["msad.mx.domestic_nonlife"]
    assert m.driving == "msad.comp.domestic_nonlife_by_source" and m.passive == "msad.comp.domestic_nonlife_by_company"
    assert [r for r in reconcile_matrices(g, levels) if r["matrix_id"] == m.id]
    # every tag left as a note says why it stays uncalibrated
    tagged = {k: v for k, v in NOTES.items() if v.startswith(("identity:", "stock-flow:", "matrix:"))}
    assert not tagged, tagged
    assert NOTES["msad-c-cat-reserve"].startswith("state:")
    for iid in ("msad-c-npw-earned", "msad-c-exposure-npw", "msad-c-nmy-bondinc", "msad-c-reserve-addback",
                "msad-c-industrycat-losses", "msad-c-xholding-pershare"):
        assert NOTES[iid].startswith("stays uncalibrated:"), iid


# -- generalization -------------------------------------------------------------------------------------------------------
def test_generalization_trace_an_oil_shock(g):
    """An oil-price shock: no MS&AD path starts there. The structure carries it to international profit through the
    BoJ's response to Japanese inflation and the yen (m02 -> m08 -> m16 -> s35, calibrated) and through the Fed and US
    yields (calibrated); to domestic non-life through super-long JGBs (m13 -> m14 -> s38, calibrated); through claims
    severity into incurred losses and so, exactly, into the loss ratio and underwriting profit (an uncalibrated step,
    then identities); to investment income through a cheaper FX hedge and through the book yield (identity); and to the
    ESR and the strategic book through marks. It stops at net assets and the share price."""
    tr = trace(g, "oil.brent", MSAD)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    fx = ("m02", "m08", "m16", "s35")
    assert routes[fx]["ends_at"] == INTL and not routes[fx]["uncalibrated_steps"]
    jgb = ("m02", "m08", "m13", "m14", "s38")
    assert routes[jgb]["ends_at"] == DOM and not routes[jgb]["uncalibrated_steps"]
    sev = ("m02", "tm-c-cpi-severity", "msad-c-severity-loss", "msad.id.uw_profit:msad.dnl_incurred_losses")
    assert routes[sev]["ends_at"] == "msad.dnl_underwriting_profit"
    assert routes[sev]["uncalibrated_steps"] == ["tm-c-cpi-severity", "msad-c-severity-loss"]
    hedge = ("m02", "m08", "msad-c-boj-hedge", "msad-c-hedge-forinc", "msad-a-inv-forsec")
    assert routes[hedge]["ends_at"] == "msad.dnl_investment_income"
    ends = {r["ends_at"] for r in tr["routes"] if r["reaches_endpoint"]}
    assert {INTL, DOM, "msad.esr", "msad.dnl_loss_ratio", "msad.dnl_underwriting_profit", "msad.dnl_investment_income",
            "msad.dnl_inc_domestic_bonds", "msad.domestic_life_profit", "msad.cross_holding_book"} <= ends
    short_stops = {r["ends_at"] for r in tr["routes"] if not r["reaches_endpoint"] and len(r["steps"]) < 6}
    assert short_stops == {"msad.share_price"}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    for iid in ("s39", "s40"):
        assert rels[iid]["dependency_type"] == "accounting_identity"
        assert rels[iid]["affected_metrics"] == ["group_adjusted_profit"]    # the export names the definition
    assert rels["msad-c-cat-reserve"]["status"] == "represented_uncalibrated"
    assert rels["msad-c-cat-reserve"]["axelrod"]["transition"]["sign"] == "-"
    assert rels["s38"]["axelrod"]["transition"]["evidence"]["magnitude"] == "assumption"


def test_new_objects_reach_the_api(client):
    ids = "msad.net_income,msad.msi_profit,msad.intl_amlin_profit,msad.dnl_domestic_bonds,msad.esr"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and "msad.dnl_bond_redemptions" in got
    view = v1.construction(client, MSAD)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, MSAD, "jgbs.yield_30y")
    assert tr["reaches_endpoint"]
