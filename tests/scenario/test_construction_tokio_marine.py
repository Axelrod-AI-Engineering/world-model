"""Tokio Marine's business construction (Oct 17): the compositions, operating and financial paths, and their
transitions in <client root>/worlds/sally_demo/construction/tokio_marine.yaml, checked in the loaded model, in the v4.1.4
export, and through the service API (docs/construction/tokio_marine.md has the gap register these tests close).
Sally's world loads once for the module. The second review round (Oct 18) adds: every input searched before it is
declared missing, the additive views reconciling at the model's medians, a forecast's calculation coverage, and, only
where the client's local folder exists (never on CI), sources and citations that resolve and baselines that reconcile."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import (
    company_citations,
    construction_view,
    inputs_by_status,
    load_sources,
    trace,
)
from axelrod_wm.model.construction import bundle_levels, model_levels, reconcile, validate_construction
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.clients import skip_without_client
from tests.scenario import v1_reads as v1

skip_without_client('sally_demo')

TM = "tokio_marine"
ANI = "tokio_marine.operating_profit"
# the client's local folder (gitignored; absent on CI): <repo>/data/sally_data/construction, or $SALLY_CONSTRUCTION
LOCAL = Path(os.environ.get("SALLY_CONSTRUCTION") or Path(__file__).resolve().parents[2] / "data" / "sally_data" / "construction")
local_only = pytest.mark.skipif(not (LOCAL / TM / "citations.json").exists(),
                                reason="the client's local construction folder is absent (as on CI)")

COMPOSITIONS = {   # id -> (total, additive)
    "tm.comp.ani_by_business": (ANI, True),
    "tm.comp.jgaap_segments": ("tokio_marine.segment_profit", True),
    "tm.comp.japan_pc_ani": ("tokio_marine.japan_pc_profit", True),
    "tm.comp.japan_pc_financial": ("tokio_marine.jpc_financial_profit", True),
    "tm.comp.international_local": ("tokio_marine.intl_profit_local", True),
    "tm.comp.international_financial": ("tokio_marine.intl_financial_profit", True),
    "tm.comp.international_units": ("tokio_marine.intl_bup", True),
    "tm.comp.tmnf_lines": ("tokio_marine.tmnf_npw", True),
    "tm.comp.tmnf_income_by_asset": ("tokio_marine.tmnf_interest_dividends", True),
    "tm.comp.capital_sources_uses": ("tokio_marine.excess_capital", False),
    "tm.comp.net_income_bridge": ("tokio_marine.net_income_ifrs", True),
    "tm.comp.jpc_assets_by_class": ("tokio_marine.jpc_investment_portfolio", True),
    "tm.comp.jpc_yen_bond_ladder": ("tokio_marine.jpc_bonds_yen", True),
    "tm.comp.jpc_cash_sources": ("tokio_marine.jpc_reinvestable_cash", True),
    "tm.comp.international_regions": ("tokio_marine.international_profit", True),
    "tm.comp.group_debt_cash_flows": ("tokio_marine.group_debt_cf_undiscounted", True),
}
PATHS = {  # the reviewer's Tokio Marine paths -> their named path(s)
    "policy growth": ["tm.path.policy_growth"],
    "claims inflation and repricing": ["tm.path.claims_inflation_repricing"],
    "investment income": ["tm.path.reinvestment", "tm.path.domestic_yields", "tm.path.international_reinvestment",
                          "tm.path.fx_hedge_cost"],
    "overseas translation": ["tm.path.overseas_translation"],
    "asset marks and liabilities": ["tm.path.asset_marks_liabilities", "tm.path.equity_marks"],
    "cross-holding disposal": ["tm.path.cross_holding_disposal"],
    "growth execution": ["tm.path.growth_execution"],
    "reserves, catastrophes and reinsurance": ["tm.path.us_liability_reserves", "tm.path.catastrophe_reinsurance"],
    "capital and payout": ["tm.path.capital_payout", "tm.path.domestic_dividends"],
    "Japan Life rates and lapses": ["tm.path.japan_life_rates", "tm.path.japan_life_lapse"],
    "per-share value": ["tm.path.per_share"],
}


@pytest.fixture(scope="module", params=["sally_demo", "sally_focus"])
def client(request):
    # Oct 18: the same build holds in the focused world (Toyota and Tokio Marine only, engine/focus.py)
    app = create_app(scenario=request.param, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        c.app_state = app.state.axelrod
        yield c


@pytest.fixture(scope="module")
def g(client):
    return client.app_state.controller.engine.wm.graph


def _native_sd(sub) -> float:
    """One standard unit in native units: the scale itself, or the log scale times the level for a lognormal."""
    import math
    return sub.scale * (math.exp(sub.anchor) if getattr(sub.prior, "family", "") == "lognormal" else 1.0)


def _link(g, src, tgt):
    hits = [i for i in g.active_interactions() if i.source_id == src and i.target_id == tgt]
    assert len(hits) == 1, (src, tgt, [i.id for i in hits])
    return hits[0]


# -- structure ---------------------------------------------------------------------------------------------------------
def test_no_construction_problems_for_tokio_marine(g):
    assert construction_view(g, TM)["problems"] == []
    assert not [p for p in validate_construction(g) if "tokio_marine" in p or "tm." in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == TM and c.total == total and c.additive is additive and c.basis, cid


def test_composition_parts_have_accounting_links(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        parts = [*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])]
        assert c.residual or c.eliminations, cid               # every additive view states what its parts leave out
        for sid in parts:
            i = _link(g, sid, c.total)
            if c.drives is False:                                # a reconciling view carries no size into its total
                assert str(i.edge_type) == "accounting" and not i.quantified, (cid, sid)
                continue
            assert str(i.edge_type) == "accounting" and i.quantified and i.forward.effect.mean() > 0, (cid, sid)
            assert i.forward.effect.sd() <= 0.01                 # a fixed weight, not a fitted coefficient


def test_required_paths_exist(g):
    for need, pids in PATHS.items():
        for pid in pids:
            p = g.paths[pid]
            assert p.entity_id == TM and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != TM:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)   # no size is claimed


def test_reinvestment_has_its_six_transitions(g):
    """The reviewer's six steps: cash freed (redemptions of the maturing bucket, coupons, underwriting cash) less cash held
    back; the deployed share allocated by class, currency and hedge into stocks; income over the holding period
    (assets x yield, the yield moved only by what is reinvested); joined with underwriting in Japan P&C; then group
    earnings, with parent dividends, payout and solvency as separate branches."""
    p = g.paths["tm.path.reinvestment"]
    pair = lambda s: (g.interactions[s.interaction_id].source_id, g.interactions[s.interaction_id].target_id)  # noqa: E731
    main = [pair(s) for s in p.steps if not s.branch]
    J = "tokio_marine."
    assert main == [
        (J + "jpc_yen_bonds_due_1y", J + "jpc_bond_maturities"),                  # 1 the maturing bucket redeems
        (J + "jpc_bond_maturities", J + "jpc_reinvestable_cash"),                 # 1-2 cash freed, net of cash held back
        (J + "jpc_reinvestable_cash", J + "jpc_new_investments"),                 # 3 the deployed share
        (J + "jpc_new_yen_bonds", J + "jpc_bonds_yen"),                           # 3 allocated into a stock
        (J + "jpc_bonds_yen", J + "jpc_investment_portfolio"),
        (J + "jpc_investment_portfolio", J + "jpc_gross_investment_income"),      # 4 income = assets x yield
        (J + "jpc_income_yield", J + "jpc_gross_investment_income"),
        (J + "jpc_gross_investment_income", J + "jpc_net_investment_income"),     # 4 net of investment expenses
        (J + "jpc_net_investment_income", J + "jpc_financial_profit"),            # 5 net investment result
        (J + "jpc_financial_profit", J + "japan_pc_profit"),                      # 5 with underwriting, one basis
        (J + "japan_pc_profit", ANI),                                             # 6 group earnings
    ]
    assert {s.branch for s in p.steps if s.branch} == {"yield", "allocation", "runoff", "parent", "payout", "capital"}
    assert g.compositions["tm.comp.jpc_cash_sources"].eliminations == J + "jpc_cash_reserved_liquidity"  # 2 held back
    assert not g.interactions["tm-c-portfolio-cash"].quantified       # the redemption entry waits on the ladder
    # R14: no market yield reaches the portfolio or its income except through money reinvested
    market = {"jgbs.yield_10y", "jgbs.yield_30y", "us_treasuries.yield_10y"}
    assert not [i.id for i in g.active_interactions() if i.source_id in market and i.target_id in
                {J + "jpc_income_yield", J + "jpc_gross_investment_income", J + "jpc_investment_portfolio"}]


def test_parallel_responses_are_branches_not_a_sequence(g):
    p = g.paths["tm.path.asset_marks_liabilities"]
    by = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch in ("assets", "liabilities")}
    assert by["assets"].source_id == by["liabilities"].source_id == "jgbs.yield_30y"


# -- definitions and financial integrity ---------------------------------------------------------------------------------
def test_adjusted_net_income_view_reconciles(g):
    c = g.compositions["tm.comp.ani_by_business"]
    assert set(c.members) == {"tokio_marine.international_profit", "tokio_marine.japan_pc_profit",
                              "tokio_marine.japan_life_profit", "tokio_marine.solution_profit"}
    assert c.eliminations == "tokio_marine.ani_consolidation_adjustment"
    for iid in ("m22", "m23"):                                   # the reviewer's two aggregation links, ids kept
        i = g.interactions[iid]
        assert str(i.edge_type) == "accounting" and i.target_id == ANI
    # each accounting weight is the part's native sd over the total's
    tot = g.subentities[ANI]
    for sid in [*c.members, c.eliminations]:
        part = g.subentities[sid]
        w = _link(g, sid, ANI).forward.effect.mean()
        assert w == pytest.approx(_native_sd(part) / _native_sd(tot), abs=0.02), sid


def test_values_name_their_basis_and_export_metric(g):
    f = g.subentities[ANI].features
    assert f["metric"] == "adjusted_net_income" and "adjusted net income" in f["basis"].lower()
    assert g.subentities["tokio_marine.international_profit"].features["metric"] == "international_adjusted_net_income"
    assert g.subentities["tokio_marine.japan_pc_profit"].features["metric"] == "japan_pc_adjusted_net_income"
    own = [s for s in g.subentities.values() if s.entity_id == TM and s.id != "tokio_marine.share_price"]
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]


def test_profit_definitions_are_separate_and_every_label_matches_its_target(g):
    """R2: statutory, adjusted and segment profit are three values; adjusted and statutory reconcile through a bridge;
    a link whose label or next state names a definition targets a value of that definition."""
    metric = {v: g.subentities[v].features.get("metric") for v in
              (ANI, "tokio_marine.net_income_ifrs", "tokio_marine.segment_profit")}
    assert metric == {ANI: "adjusted_net_income", "tokio_marine.net_income_ifrs": "net_income_attributable",
                      "tokio_marine.segment_profit": "jgaap_segment_profit"}
    bridge = g.compositions["tm.comp.net_income_bridge"]
    assert bridge.total == "tokio_marine.net_income_ifrs" and bridge.members == [ANI] and bridge.residual
    own = set(g.entities[TM].subentity_ids)
    words = {"adjusted net income": "adjusted_net_income", "segment profit": "segment_profit",
             "net income attributable": "net_income_attributable"}
    for i in g.active_interactions():
        if i.target_id not in own or i.transition is None:
            continue
        said = f"{i.label} {i.transition.next_state}".lower()
        m = str(g.subentities[i.target_id].features.get("metric") or "")
        for phrase, key in words.items():
            if phrase in said:
                assert key in m, (i.id, phrase, i.target_id, m)


def test_segment_profit_view_is_separate_and_reconciles(g):
    seg, ani = g.compositions["tm.comp.jgaap_segments"], g.compositions["tm.comp.ani_by_business"]
    assert not set(seg.members) & set(ani.members) and seg.basis != ani.basis
    ani_side = {ANI, *ani.members, ani.eliminations}
    assert not [i.id for i in g.active_interactions()        # no link joins the two bases
                if i.source_id in {seg.total, *seg.members, seg.eliminations} and i.target_id in ani_side]


def test_international_local_and_translation_are_separate(g):
    t = g.interactions["tm-a-intl-translate"]
    assert (t.source_id, t.target_id) == ("tokio_marine.intl_profit_local", "tokio_marine.international_profit")
    assert str(t.edge_type) == "accounting"
    assert g.interactions["m19"].source_id == "dollar_yen.usd_jpy" and g.interactions["m19"].quantified


def test_fx_counter_effect_is_calibrated_from_disclosure(g):
    i = g.interactions["tm-c-fx-reserves"]
    assert i.quantified and i.forward.effect.mean() < 0 and i.transition.evidence.magnitude == "documented"
    # translation gain outweighs the reserve charge at group level, as the disclosure says
    gain = g.interactions["m19"].forward.effect.mean() * g.interactions["m22"].forward.effect.mean()
    loss = i.forward.effect.mean() * g.interactions["m23"].forward.effect.mean()
    assert gain + loss > 0


def test_broad_yield_links_state_their_scope(g):
    for iid in ("m20", "m21"):
        tr = g.interactions[iid].transition
        assert tr is not None and ("not apply to all" in tr.mechanism or "not applied to all" in tr.mechanism), iid
        assert tr.evidence.magnitude == "assumption" and tr.unresolved, iid
    for iid in ("m19", "s41", "s55", "s70"):
        assert g.interactions[iid].transition is not None, iid


def test_marks_never_reach_recurring_income(g):
    out_of = {}
    for i in g.active_interactions():
        out_of.setdefault(i.source_id, []).append(i.target_id)
    for start in ("tokio_marine.bond_valuation", "tokio_marine.liability_economic_value"):
        seen, stack = set(), [start]
        while stack:
            v = stack.pop()
            if v not in seen:
                seen.add(v)
                stack += out_of.get(v, [])
        assert ANI not in seen and "tokio_marine.japan_pc_profit" not in seen, start


def test_cross_holding_proceeds_never_reach_recurring_income_except_forgone_dividends(g):
    p = g.paths["tm.path.cross_holding_disposal"]
    src = "tokio_marine.cross_holding_sales"
    into_income = [g.interactions[s.interaction_id] for s in p.steps if g.interactions[s.interaction_id].source_id == src
                   and g.interactions[s.interaction_id].target_id == "tokio_marine.tmnf_div_domestic_equity"]
    assert len(into_income) == 1 and into_income[0].polarity() < 0
    direct = {i.target_id for i in g.active_interactions() if i.source_id == src}
    assert not direct & {ANI, "tokio_marine.japan_pc_profit", "tokio_marine.jpc_net_investment_income"}


def test_no_invented_ladder(g):
    """The pack's maturity analysis is group scope (every segment and currency, undiscounted cash flows): it is held
    as its own reconciling view and never sizes the Japan P&C redemptions (R14)."""
    own = [s for s in g.subentities.values() if s.entity_id == TM]
    assert not [s.id for s in own if any(k in s.id for k in ("maturity", "ladder", "duration"))]
    assert "maturity ladder" in " ".join(u.input for u in g.interactions["tm-c-portfolio-cash"].transition.unresolved)
    grp = g.compositions["tm.comp.group_debt_cash_flows"]
    assert grp.drives is False and "group" in grp.basis.lower()
    assert not [i.id for i in g.active_interactions() if i.source_id in {grp.total, *grp.members, grp.residual}
                and i.target_id.startswith("tokio_marine.jpc_")]


# -- second review round (Oct 18) ------------------------------------------------------------------------------------------
def test_every_input_was_searched_before_it_is_declared_missing(g):
    ins = inputs_by_status(g, TM)
    # its own inputs: those on links into its values (a link that only starts here, e.g. another company's use of
    # a shared market state, belongs to the company it leads into)
    own = set(g.entities[TM].subentity_ids)
    ins["inputs"] = [n for n in ins["inputs"] if any(g.interactions[i].target_id in own for i in n["interaction_ids"])]
    assert ins["not_yet_reviewed"] == [] and ins["counts"]["not_yet_reviewed"] == 0
    rows = {(n["input"], n["status"]): n for n in ins["inputs"]}
    for (name, status), n in rows.items():
        if status in ("not_disclosed_in_reviewed_sources", "disclosed_not_supplied"):       # Tokio Marine's own files and the corpus queries
            assert {"tm.wb", "tm.seg"} <= set(n["searched"]) and any(s.startswith("corpus: ") for s in n["searched"]), name
        if status.startswith("found"):
            assert n["found_in"], name
    # the reviewer's question: maturity information was searched for, and it is not disclosed in the supplied material
    ladder = rows[("maturity ladder", "found_proxy")]      # the pack's securities report has it at group scope only
    assert ladder["interaction_ids"] == ["tm-c-portfolio-cash"]
    assert {"corpus: maturity ladder", "corpus: maturity", "corpus: redemption", "corpus: duration"} <= set(ladder["searched"])
    assert not g.interactions["tm-c-portfolio-cash"].quantified           # so the first reinvestment step has no size


def test_additive_views_reconcile_at_the_model_medians(g):
    rows = [r for r in reconcile(g, model_levels(g, "median")) if r["entity_id"] == TM]
    assert len(rows) == sum(1 for c in g.compositions.values() if c.entity_id == TM and c.additive)
    assert [(r["composition_id"], r["relative_difference"], r["missing_levels"], r["unit_mismatches"])
            for r in rows if r["status"] != "ok"] == []


def test_a_forecast_reports_its_calculation_coverage(client):
    """A BoJ hike: the translation links and the reserve counter-effect carry a size; the hedge-cost and new-money links
    it reaches are excluded as uncalibrated, with their sign, and their inputs say why."""
    cov = v1.simulate(client, "What if the BoJ hiked by 25bp next quarter?", 365)
    got = {c["interaction_id"] for c in cov["contributed"]}
    assert {"m19", "tm-c-fx-reserves", "m22", "m23"} <= got
    ex = {c["interaction_id"]: c for c in cov["excluded"]}
    assert ex["tm-c-boj-hedge"]["reason"] == "uncalibrated" and ex["tm-c-boj-hedge"]["sign"] == "-"
    assert not got & set(ex)
    statuses = {b["status"] for b in cov["blocking_inputs"] if any(i.startswith("tm-") for i in b["interaction_ids"])}
    assert statuses and "not_yet_reviewed" not in statuses


def test_converted_steps_are_exact_forms(g):
    """Conversion round: investment income = assets x income yield (a product identity), the cross-holding book and
    parent capital as stocks that accumulate their flows, and reinvestment whose sign follows new-money versus book
    yield. Each reconciles at the construction levels; each converted link carries a derived weight."""
    from axelrod_wm.model.construction import reconcile_identities

    gross, nii = g.identities["tm.id.jpc_gross_income"], g.identities["tm.id.jpc_nii"]
    assert gross.form == "product" and gross.target == "tokio_marine.jpc_gross_investment_income"
    assert nii.form == "difference" and nii.minus == ["tokio_marine.jpc_investment_expenses"]
    # the pack's IFRS breakdown has no hedge line inside net investment income: the hedge cost goes to other items
    h = g.interactions["tm-a-hedge-financial"]
    assert (h.source_id, h.target_id) == ("tokio_marine.jpc_hedge_cost_amount", "tokio_marine.jpc_financial_residual")
    assert h.forward.effect.mean() < 0
    rows = [r for r in reconcile_identities(g, model_levels(g, "median")) if r["entity_id"] == TM]
    assert len(rows) == len([x for x in g.identities.values() if x.entity_id == TM])
    assert [r["identity_id"] for r in rows if r["status"] != "ok"] == []
    for iid in ("tm-i-jpc-nii-assets", "tm-i-jpc-nii-yield"):
        i = g.interactions[iid]
        assert str(i.edge_type) == "identity" and i.quantified and i.forward.effect.mean() > 0, iid
    xh, cap = g.stock_flows["tm.sf.cross_holdings"], g.stock_flows["tm.sf.parent_capital"]
    assert xh.stock == "tokio_marine.cross_holding_book" and xh.outflows == ["tokio_marine.cross_holding_sales"]
    # plan round (R13): overseas remittances reach the holding company inside the Japan P&C subsidiary's dividend
    assert cap.inflows == ["tokio_marine.domestic_subsidiary_dividends"]
    assert g.interactions["tm-c-remit-capital"].target_id == "tokio_marine.domestic_subsidiary_dividends"
    assert set(cap.outflows) == {"tokio_marine.shareholder_returns", "tokio_marine.acquisition_spend"}
    for iid, sign in (("tm-c-sale-book", -1), ("tm-sf-parent-domestic", 1)):
        i = g.interactions[iid]
        assert str(i.edge_type) == "stock_flow" and i.forward.kernel.accumulates and i.polarity() == sign, iid
    # proceeds still never reach recurring income: the stock-flow ends at the book
    assert not g.interactions["tm-c-invest-income"].quantified
    assert g.interactions["tm-c-invest-income"].target_id == "tokio_marine.jpc_income_yield"
    assert any(p.form == "piecewise" for p in g.interactions["tm-c-invest-income"].parameters)
    # a candidate left sign-only says why
    assert "not converted" in (g.interactions["tm-c-portfolio-cash"].note or "")


@local_only
def test_sources_and_citations_resolve_locally(g):
    cc = company_citations(g, TM, load_sources(LOCAL))
    assert cc["unresolved"] == [] and cc["unknown_citation_keys"] == []
    assert cc["claims_without_citation"] == []                          # every material claim has a located citation
    cites = json.loads((LOCAL / TM / "citations.json").read_text())
    assert all(c["location"] and c["passage"] and len(c["passage"]) <= 300 for cs in cites.values() for c in cs)


@local_only
def test_the_baselines_reconcile_in_every_view(g):
    levels = bundle_levels(json.loads((LOCAL / TM / "baselines.json").read_text()))
    rows = [r for r in reconcile(g, levels) if r["entity_id"] == TM]
    assert len(rows) == sum(1 for c in g.compositions.values() if c.entity_id == TM and c.additive)
    assert [r["composition_id"] for r in rows if r["status"] == "flag"] == []       # blocked (no level yet) is not a flag


# -- generalization -------------------------------------------------------------------------------------------------------
def test_generalization_trace_a_boj_hike(g):
    """A BoJ hike: no path was written for it. The structure carries it to group adjusted net income through
    translation (m16 -> m19 -> m22) and the offsetting reserve charge (m16 -> tm-c-fx-reserves), to Japan P&C financial
    profit through a cheaper FX hedge (uncalibrated) and new-money yields (uncalibrated), and to solvency through asset
    and liability marks in parallel; it stops at equity (net assets) and the share price, which lead nowhere further."""
    tr = trace(g, "boj.policy_rate", TM)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    # international profit is a total (its regional view, plan round): the route stops there, and goes on to ANI
    assert routes[("m16", "m19")]["ends_at"] == "tokio_marine.international_profit"
    full = {tuple(s["interaction_id"] for s in r["steps"]): r for r in trace(g, "boj.policy_rate", TM, through_totals=True)["routes"]}
    assert full[("m16", "m19", "m22")]["ends_at"] == ANI
    assert ("m16", "tm-c-fx-reserves") in routes
    # the hedge cost lowers the book income yield; income = assets x yield (identity), whose target is an endpoint
    hedge = ("tm-c-boj-hedge", "tm-c-hedge-nii")
    assert hedge in routes and routes[hedge]["uncalibrated_steps"] == ["tm-c-boj-hedge"]
    assert routes[hedge]["ends_at"] == "tokio_marine.jpc_hedge_cost_amount"     # hedge cost = hedged bonds x rate
    ends = {r["ends_at"] for r in tr["routes"] if r["reaches_endpoint"]}
    assert {ANI, "tokio_marine.esr", "tokio_marine.jpc_financial_profit", "tokio_marine.excess_capital"} <= ends
    assert set(tr["stops"]) <= {"tokio_marine.net_assets", "tokio_marine.share_price", "tokio_marine.japan_life_ev"}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    for iid in ("m22", "m23"):
        assert rels[iid]["dependency_type"] == "accounting_identity"
        assert rels[iid]["affected_metrics"] == ["adjusted_net_income"]     # the export names the definition
    assert rels["tm-c-portfolio-cash"]["status"] == "represented_uncalibrated"
    assert rels["tm-c-portfolio-cash"]["axelrod"]["transition"]["sign"] == "+"
    assert pack["domain_specific_support_objects"]["schema_gaps"]


def test_new_objects_reach_the_api(client):
    ids = "tokio_marine.jpc_reinvestable_cash,tokio_marine.intl_profit_local,tokio_marine.esr"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and "tokio_marine.jpc_new_investments" in got
    view = v1.construction(client, TM)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, TM, "jgbs.yield_30y")
    assert tr["reaches_endpoint"]


# -- validation cases (plan round, R16): each runs through the model, the export, and the context reads ------------------
AT = "2026-10-20T00:00:00Z"
J = "tokio_marine."


def _pose(client, cid, ops, targets):
    """Pose a thesis of direct value changes; return each value's peak response in native units, the links that
    contributed, and the links left out with their reason."""
    from axelrod_wm.sim.scenario import thesis_from_spec

    ctl = client.app_state.controller
    spec = {"id": f"VT-{cid}", "question": f"validation case {cid}", "mode": "scaffolded", "horizon_days": 365,
            "targets": targets, "event": {"kind": "hypothetical", "event_type": "other", "occurred_at": AT, "ops": [
                {"op": "change_value", "target": {"kind": "concrete", "subentity_id": sid}, "delta": d, "mode": "absolute",
                 "persistence": "step", "intervention": True, "window_days": 400, "at": AT} for sid, d in ops]}}
    fc = ctl.pose_thesis(thesis_from_spec(spec, ctl.now))
    g = ctl.engine.wm.graph
    peak = {t.subentity_id: t.peak * _native_sd(g.subentities[t.subentity_id]) for t in fc.transmission or []}
    used = {c["interaction_id"] for c in fc.coverage["contributed"]}
    left = {c["interaction_id"]: c["reason"] for c in fc.coverage["excluded"]}
    return peak, used, left


def test_validation_reinvestment_uplift_against_underwriting_deterioration(client):
    """Case 1. The book income yield rises 0.1pt (what reinvestment at higher new-money yields buys over a year) while
    claims rise ¥20bn. By hand, on the model's levels: gross income = 6,400 x 0.1% = +6.4; net investment income moves
    with it (expenses do not); insurance-related profit = -20 (identity); Japan P&C profit = +6.4 - 20 < 0. The model
    carries both through the identities, shows underwriting outweighing the uplift, and uses no market yield on the
    whole book (R14)."""
    peak, used, left = _pose(client, "reinvest-vs-uw", [(J + "jpc_income_yield", 0.1), (J + "jpc_claims_incurred", 20.0)],
                             [J + "jpc_gross_investment_income", J + "jpc_insurance_profit", J + "japan_pc_profit", ANI])
    # a forecast samples its effects, so the hand figures hold within a band
    assert peak[J + "jpc_gross_investment_income"] == pytest.approx(6.4, rel=0.2)
    assert peak[J + "jpc_net_investment_income"] == pytest.approx(peak[J + "jpc_gross_investment_income"], rel=0.05)
    assert peak[J + "jpc_insurance_profit"] == pytest.approx(-20.0, rel=0.2)
    assert peak[J + "japan_pc_profit"] < 0 and peak[ANI] < 0                     # underwriting outweighs the uplift
    assert {"tm-i-jpc-nii-yield", "tm-i-jpc-nii-gross", "tm-i-uw-claims", "tm-a-jpc-nii", "tm-a-jpc-insurance", "m23"} <= used
    assert not used & {"tm-c-jgb10-nmy", "tm-c-jgb30-nmy", "m20", "m21"}
    # the export carries the identities; the context trace reaches Japan P&C profit from both shocks
    pack = v1.pack(client)
    ids = {x.get("identity_id") or x.get("id") for x in pack["domain_specific_support_objects"]["financial_identities"]}
    assert {"tm.id.jpc_gross_income", "tm.id.jpc_nii", "tm.id.jpc_uw"} <= ids
    for start in (J + "jpc_income_yield", J + "jpc_claims_incurred"):
        tr = trace(client.app_state.controller.engine.wm.graph, start, TM, through_totals=True)
        assert any(J + "japan_pc_profit" in [*r["passes"], r["ends_at"]] for r in tr["routes"]), start


def test_validation_asset_marks_against_solvency(client):
    """Case 2. Equities fall 30% (the book moves -30%): the company's disclosed ESR sensitivity has the ratio rising
    when equities fall; equity falls through OCI; adjusted net income does not move. A 50bp rate rise: the disclosed
    ESR move is net of two parallel marks (assets, liabilities) not sized apart, so the model leaves the ratio unmoved
    and lists both branches as uncalibrated, while Japan Life embedded value moves by its disclosed rate sensitivity.
    The disclosed figures are client data: with the local folder they are checked against the model within a band;
    on CI the directions are."""
    vf = LOCAL / TM / "validation.json"
    v = json.loads(vf.read_text()) if vf.exists() else None
    import math
    book = v["cross_holding_book_level"] if v else \
        math.exp(client.app_state.controller.engine.wm.graph.subentities[J + "cross_holding_book"].anchor)
    peak, used, left = _pose(client, "equity-marks", [(J + "cross_holding_book", -0.3 * book)], [J + "esr", J + "net_assets", ANI])
    assert peak[J + "esr"] > 0 and peak[J + "net_assets"] < 0 and abs(peak.get(ANI, 0.0)) < 1e-6
    if v:
        assert peak[J + "esr"] == pytest.approx(v["esr_equities_down_30"], rel=0.2)
    assert {"tm-c-xholding-esr", "tm-c-xholding-equity"} <= used
    peak, used, left = _pose(client, "rate-marks", [("jgbs.yield_30y", 0.5)], [J + "esr", J + "japan_life_ev"])
    assert peak[J + "japan_life_ev"] < 0 and abs(peak.get(J + "esr", 0.0)) < 1e-6
    if v:
        assert peak[J + "japan_life_ev"] == pytest.approx(v["ev_rates_up_50bp"], rel=0.2)
        assert v["esr_rates_up_50bp"] != 0          # the disclosure moves; the model cannot, until the branches are sized
    assert left.get("tm-c-jgb-bondmark") == left.get("tm-c-jgb-liability") == "uncalibrated"
    rels = {r["axelrod"]["interaction_id"]: r
            for r in v1.pack(client)["company_edge_relationships"]}
    assert rels["tm-c-xholding-esr"]["axelrod"]["state"]["asymmetry"]["falls"]["mu"] < 0
    assert rels["tm-c-jgb-bondmark"]["status"] == "represented_uncalibrated"


def test_validation_a_catastrophe_outside_both(client):
    """Case 3, outside reinvestment and marks: a ¥50bn domestic catastrophe. By hand: claims +50 (one for one),
    insurance-related profit -50 (identity), Japan P&C profit and group adjusted net income lower. Recoveries above the
    retention are real but unsized (the retention is not disclosed): the model shows the case gross of recoveries and
    says so."""
    peak, used, left = _pose(client, "nat-cat", [(J + "japan_nat_cat_losses", 50.0)],
                             [J + "jpc_claims_incurred", J + "jpc_insurance_profit", J + "japan_pc_profit", ANI])
    assert peak[J + "jpc_claims_incurred"] > 0
    assert peak[J + "jpc_insurance_profit"] == pytest.approx(-peak[J + "jpc_claims_incurred"], rel=0.03)  # the identity
    assert peak[J + "japan_pc_profit"] < 0 and peak[ANI] < 0
    assert {"tm-c-cat-profit", "tm-i-uw-claims"} <= used and left.get("tm-c-cat-recoveries") == "uncalibrated"
    view = v1.construction(client, TM)
    assert "tm.path.catastrophe_reinsurance" in {p["id"] for p in view["paths"]}
