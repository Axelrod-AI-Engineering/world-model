"""UniCredit's business construction (Oct 18, converted to the method's new forms): the compositions (one driving view
per total, a division x line matrix), identities, a stock-flow, operating and financial paths and their transitions in
data/worlds/sally_demo/construction/unicredit.yaml, checked in the loaded model, in the v4.1.4 export, and through the
service API (docs/construction/unicredit.md has the gap register these tests close). The second bank after JPMorgan:
a European bank on IFRS, by geographic division, with a structural hedge, an Italian sovereign book, stakes and a
Russia wind-down. Sally's world loads once for the module; no client data is read."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import construction_view, trace
from axelrod_wm.model.construction import (
    model_levels,
    reconcile,
    reconcile_identities,
    reconcile_matrices,
    reconcile_stock_flows,
    reconciling_views,
    validate_construction,
)
from axelrod_wm.repo.snapshots import MemoryBackend

UCG = "unicredit"
B = "/api/world-model"
NII, REV, NP = "unicredit.net_interest_income", "unicredit.revenue", "unicredit.net_profit"
ECB, BUND, UNEMP = "ecb.policy_rate", "bunds.yield_10y", "euro_economy.unemployment_rate"

COMPOSITIONS = {   # id -> (total, role)
    "ucg.comp.revenue_by_line": (REV, "driving"),
    "ucg.comp.revenue_by_division": (REV, "reconciling"),          # the passive view of matrix ucg.mx.revenue
    "ucg.comp.nii_by_division": (NII, "driving"),
    "ucg.comp.fees_by_division": ("unicredit.fees_insurance", "driving"),
    "ucg.comp.costs_by_division": ("unicredit.operating_costs", "driving"),
    "ucg.comp.llp_by_division": ("unicredit.loan_loss_provisions", "reconciling"),   # ucg.id.llp drives the total
    "ucg.comp.pretax": ("unicredit.profit_before_tax", "driving"),
    "ucg.comp.net_profit": (NP, "driving"),
    "ucg.comp.net_profit_by_division": (NP, "reconciling"),
    "ucg.comp.distributions": ("unicredit.total_distributions", "driving"),
    "ucg.comp.cet1_capital": ("unicredit.cet1_capital", "driving"),
    "ucg.comp.payout": ("unicredit.payout_ratio", "driving"),
}
EXACT = {"ucg.comp.distributions", "ucg.comp.cet1_capital", "ucg.comp.payout"}  # exact splits; every other view keeps a remainder
IDENTITIES = {   # id -> (form, target)
    "ucg.id.hedge_income": ("product", "unicredit.hedge_income"),
    "ucg.id.deposit_interest": ("product", "unicredit.deposit_interest_expense"),
    "ucg.id.loan_interest": ("product", "unicredit.loan_interest_income"),
    "ucg.id.cbk_income": ("product", "unicredit.cbk_equity_income"),
    "ucg.id.llp": ("product", "unicredit.loan_loss_provisions"),
    "ucg.id.cet1_ratio": ("ratio", "unicredit.cet1_ratio"),
    "ucg.id.cash_dividends": ("product", "unicredit.cash_dividends"),
    "ucg.id.ordinary_buybacks": ("product", "unicredit.buybacks"),
}
DIVISIONS = ("italy", "germany", "austria", "cee", "russia")
PATHS = {  # a European bank's economics -> the named path(s) that carry them
    "ECB deposit rate, Euribor, pass-through and NII": ["ucg.path.rates_nii"],
    "the structural hedge and the long end": ["ucg.path.long_end"],
    "the Italian sovereign book": ["ucg.path.sovereign_spread"],
    "cost of risk and the credit cycle": ["ucg.path.credit_cycle"],
    "loan volumes and RWA": ["ucg.path.loan_growth"],
    "fees on market levels": ["ucg.path.fees_markets"],
    "costs and inflation": ["ucg.path.cost_inflation"],
    "capital and the distribution policy": ["ucg.path.capital_distribution", "ucg.path.capital_requirements"],
    "stakes and M&A (Commerzbank)": ["ucg.path.commerzbank"],
    "the Russia wind-down": ["ucg.path.russia"],
}
SOURCES = {"ucg.wb", "ucg.co", "ucg.r1", "ucg.r2", "ucg.r3", "ucg.r4", "ucg.r5", "ucg.r6", "ucg.r7", "ucg.peer", "ucg.macro",
           "ucg.pub"}
PENDING_TAGS = ("identity:", "stock-flow:", "matrix:")       # converted: none of these may remain


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


def _links(g, src, tgt):
    return [i for i in g.active_interactions() if i.source_id == src and i.target_id == tgt]


def _link(g, src, tgt):
    hits = _links(g, src, tgt)
    assert len(hits) == 1, (src, tgt, [i.id for i in hits])
    return hits[0]


def _ucg_links(g):
    own = set(g.entities[UCG].subentity_ids)
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


def _note(i) -> str:
    return getattr(i, "note", None) or ""


# -- structure ---------------------------------------------------------------------------------------------------------
def test_no_construction_problems_for_unicredit(g):
    assert construction_view(g, UCG)["problems"] == []
    assert not [p for p in validate_construction(g) if "unicredit" in p or "ucg." in p or "ucg-" in p]


def test_one_driving_view_per_total(g):
    passive = reconciling_views(g)
    for cid, (total, role) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == UCG and c.total == total and c.additive and c.basis and c.unit, cid
        assert (cid in passive) == (role == "reconciling"), cid
    assert passive["ucg.comp.revenue_by_division"] == "matrix ucg.mx.revenue"
    driving = {}
    for cid, (total, role) in COMPOSITIONS.items():
        if role == "driving":
            driving.setdefault(total, []).append(cid)
    assert all(len(v) == 1 for v in driving.values()), driving


def test_driving_parts_have_fixed_weight_accounting_links(g):
    for cid, (_total, role) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if cid not in EXACT:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)                          # one unit within a view
        for sid in _parts(c):
            if role == "reconciling":                                  # observed and reconciled, never driving
                assert not [i for i in _links(g, sid, c.total) if i.quantified], (cid, sid)
                continue
            i = _link(g, sid, c.total)
            assert str(i.edge_type) == "accounting" and i.quantified and i.forward.effect.mean() > 0, (cid, sid)
            assert i.forward.effect.sd() <= 0.01                         # a fixed weight, not a fitted coefficient
            w = i.forward.effect.mean()
            assert w == pytest.approx(_native_sd(g.subentities[sid]) / _native_sd(g.subentities[c.total]), abs=0.01), (cid, sid)


def test_priors_reconcile_views_identities_and_the_matrix(g):
    rows = {r["composition_id"]: r for r in reconcile(g)}
    for cid in COMPOSITIONS:
        c = g.compositions[cid]
        total, parts = _level(g.subentities[c.total]), sum(_level(g.subentities[s]) for s in _parts(c))
        assert abs(parts - total) <= 0.005 * abs(total), (cid, total, parts)
        assert cid in rows
    med = model_levels(g, "median")                                  # round construction levels (lognormal medians)
    ids = {r["identity_id"]: r for r in reconcile_identities(g, med)}
    for iid, (form, target) in IDENTITIES.items():
        x = g.identities[iid]
        assert x.entity_id == UCG and x.form == form and x.target == target and x.unit_check, iid
        assert ids[iid]["status"] == "ok", ids[iid]
    mx = [r for r in reconcile_matrices(g, med) if r.get("matrix_id") == "ucg.mx.revenue"]
    assert mx and all(r["status"] == "ok" for r in mx if r.get("status")), mx


def test_the_division_by_line_matrix(g):
    m = g.matrices["ucg.mx.revenue"]
    assert (m.rows, m.columns, m.drives) == ("ucg.comp.revenue_by_line", "ucg.comp.revenue_by_division", "rows")
    cells = m.cell_list()
    assert {r for r, _c, _v in cells} == {NII, "unicredit.fees_insurance"}
    assert len(cells) == 12                                           # NII and fees for five divisions and the centre
    for row, col, cell in cells:
        for part in (row, col):
            i = _link(g, cell, part)
            assert str(i.edge_type) == "accounting" and i.quantified, (cell, part)
    assert not [i for i in g.active_interactions() if i.id.startswith("ucg-c-bridge-")]   # the matrix replaced them


def test_required_paths_exist(g):
    for need, pids in PATHS.items():
        for pid in pids:
            p = g.paths[pid]
            assert p.entity_id == UCG and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != UCG:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)   # no size is claimed


def test_shared_driver_responses_are_parallel_branches(g):
    p = g.paths["ucg.path.rates_nii"]
    by = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}
    assert {"euribor", "pass_through", "migration", "stake"} <= set(by)
    assert {i.source_id for i in by.values()} == {ECB}
    q = g.paths["ucg.path.long_end"]
    assert {s.branch for s in q.steps if s.branch} == {"hedge", "marks"}
    assert {g.interactions[s.interaction_id].source_id for s in q.steps if s.branch} == {BUND}
    c = g.paths["ucg.path.credit_cycle"]
    assert {g.interactions[s.interaction_id].source_id for s in c.steps if s.branch} == {UNEMP}


def test_summary_links_are_never_steps_of_their_structural_paths(g):
    steps = {pid: {s.interaction_id for s in p.steps} for pid, p in g.paths.items() if p.entity_id == UCG}
    assert "m28" not in steps["ucg.path.rates_nii"]
    assert not {"s76", "s33"} & steps["ucg.path.long_end"]
    assert "s33" not in steps["ucg.path.sovereign_spread"]
    # the structural steps into NII stay unsized, so the summary links are never counted twice
    for iid in ("ucg-c-hedgeincome-nii", *[f"ucg-c-{k}-{d}nii" for k in ("loanint", "depint") for d in ("italy", "germany", "austria")]):
        i = g.interactions[iid]
        assert not i.quantified and "twice" in _note(i), iid


# -- a European bank's economics ---------------------------------------------------------------------------------------------
def test_values_name_their_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == UCG and s.id != "unicredit.share_price"]
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]
    assert g.subentities[NII].features["metric"] == "net_interest_income"
    assert "standalone" in g.subentities["unicredit.cet1_ratio"].features["basis"]


def test_division_views_follow_the_reported_divisions(g):
    for cid in ("ucg.comp.revenue_by_division", "ucg.comp.nii_by_division", "ucg.comp.fees_by_division",
                "ucg.comp.costs_by_division", "ucg.comp.llp_by_division", "ucg.comp.net_profit_by_division"):
        c = g.compositions[cid]
        assert [m.split(".")[1].split("_")[0] for m in c.members] == list(DIVISIONS), cid
        assert c.residual.startswith("unicredit.gcc_"), cid              # the Group Corporate Centre is the residual


def test_deposit_pass_through_is_calibrated_and_lags(g):
    i = g.interactions["ucg-c-ecb-depcost"]
    assert i.quantified and i.forward.effect.mean() > 0 and i.transition.evidence.magnitude == "documented"
    beta = i.forward.effect.mean() * g.subentities["unicredit.deposit_cost"].scale / g.subentities[ECB].scale
    assert 0.25 <= beta <= 0.35                                       # a cumulative pass-through, not one for one
    assert i.forward.kernel.lag.mean() >= 90                           # it builds over quarters
    assert "state:" in _note(i)                                        # asymmetry: no size disclosed by side
    dep = _link(g, "unicredit.deposit_cost", "unicredit.deposit_interest_expense")
    assert str(dep.edge_type) == "identity" and dep.identity == "ucg.id.deposit_interest" and dep.quantified


def test_hedge_roll_and_hedge_income(g):
    i = g.interactions["ucg-c-bund-hedgeyield"]
    assert i.quantified and i.transition.evidence.magnitude == "model"
    roll = i.forward.effect.mean() * g.subentities["unicredit.hedge_yield"].scale / g.subentities[BUND].scale
    assert roll == pytest.approx(0.2, abs=0.02)                        # one over the hedge's maturity, a year
    assert i.forward.kernel.lag.mean() >= 180
    inc = g.interactions["ucg-c-hedgeyield-nii"]
    assert str(inc.edge_type) == "identity" and inc.target_id == "unicredit.hedge_income" and inc.quantified


def test_rate_summary_links_are_sized_jointly_from_the_disclosed_scenarios(g):
    m28, s76 = g.interactions["m28"], g.interactions["s76"]
    for i in (m28, s76):
        assert i.quantified and i.transition.evidence.magnitude == "model" and "least squares" in _note(i), i.id
        assert i.transition.unresolved and all(u.status == "found_connected" for u in i.transition.unresolved)
    assert 0 < m28.forward.effect.mean() < 0.5 and 0 < s76.forward.effect.mean() < 0.2   # below the original records
    assert "s76" in _note(m28) and "m28" in _note(s76)


def test_only_evidenced_links_carry_new_causal_sizes(g):
    causal = {i.id for i in _ucg_links(g) if i.id.startswith(("ucg-c-", "ucg-m-")) and i.quantified
              and str(i.edge_type) == "causal"}
    assert causal == {"ucg-c-ecb-depcost", "ucg-c-bund-hedgeyield"}
    assert not [i.id for i in g.active_interactions() if i.id.startswith("ucg-m-") and i.quantified]
    for iid in ("s33", "s34"):                                         # the other records keep their sizes, scoped
        tr = g.interactions[iid].transition
        assert tr is not None and tr.evidence.magnitude == "assumption" and tr.unresolved, iid


def test_converted_steps_are_exact_and_untagged(g):
    kinds = {}
    for i in _ucg_links(g):
        kinds.setdefault(str(i.edge_type), set()).add(i.id)
        assert not _note(i).startswith(PENDING_TAGS), (i.id, _note(i))   # every tagged step was converted or explained
    assert len(kinds["identity"]) >= 14 and len(kinds["stock_flow"]) == 2
    for i in _ucg_links(g):
        if str(i.edge_type) in ("identity", "stock_flow"):
            assert i.quantified, i.id
    left = [i for i in _ucg_links(g) if not i.quantified and _note(i)]
    assert all(len(_note(i)) > 30 for i in left)                        # each says why it stays unsized


def test_overlays_absorb_before_provisions_rise(g):
    assert _link(g, UNEMP, "unicredit.cost_of_risk").transition.sign == "+"
    assert _link(g, UNEMP, "unicredit.overlays").transition.sign == "-"            # the counter-path: overlays used
    assert _link(g, "unicredit.overlays", "unicredit.loan_loss_provisions").transition.sign == "-"
    cor = _link(g, "unicredit.cost_of_risk", "unicredit.loan_loss_provisions")
    assert str(cor.edge_type) == "identity" and cor.forward.effect.mean() < 0      # more cost of risk, larger charge


def test_marks_reach_capital_not_income(g):
    reached = _reach(g, "unicredit.fvoci_reserve")
    assert "unicredit.cet1_capital" in reached and "unicredit.cet1_ratio" in reached
    assert not reached & {NP, REV, NII, "unicredit.profit_before_tax"}
    assert _link(g, "btps.bund_spread_10y", "unicredit.fvoci_reserve").transition.sign == "-"


def test_capital_is_a_stock_with_flows_and_a_ratio(g):
    sf = g.stock_flows["ucg.sf.core_cet1"]
    assert sf.stock == "unicredit.core_cet1_capital" and sf.inflows == [NP] and sf.outflows == ["unicredit.total_distributions"]
    inc = _link(g, NP, sf.stock)
    out = _link(g, "unicredit.total_distributions", sf.stock)
    assert str(inc.edge_type) == "stock_flow" and inc.forward.effect.mean() > 0
    assert str(out.edge_type) == "stock_flow" and out.forward.effect.mean() < 0
    lv = {s: _level(g.subentities[s]) for s in (sf.stock, NP, "unicredit.total_distributions")}
    closing = lv[sf.stock] + lv[NP] - lv["unicredit.total_distributions"]
    series = {sf.stock: [("2026-01-01", lv[sf.stock]), ("2027-01-01", closing)],
              NP: [("2027-01-01", lv[NP])], "unicredit.total_distributions": [("2027-01-01", lv["unicredit.total_distributions"])]}
    rows = [r for r in reconcile_stock_flows(g, series) if r.get("stock_flow_id") == "ucg.sf.core_cet1"]
    assert rows and all(r["status"] == "ok" for r in rows), rows
    ratio = _link(g, "unicredit.cet1_capital", "unicredit.cet1_ratio")
    rwa = _link(g, "unicredit.rwa", "unicredit.cet1_ratio")
    assert ratio.identity == rwa.identity == "ucg.id.cet1_ratio" and rwa.forward.effect.mean() < 0


def test_distributions_split_into_dividends_and_buybacks(g):
    c = g.compositions["ucg.comp.distributions"]
    assert set(c.members) == {"unicredit.cash_dividends", "unicredit.buybacks"}
    assert _link(g, NP, "unicredit.cash_dividends").identity == "ucg.id.cash_dividends"
    assert _link(g, NP, "unicredit.buybacks").identity == "ucg.id.ordinary_buybacks"
    xs = _link(g, "unicredit.cet1_ratio", "unicredit.buybacks")
    assert xs.transition.sign == "+" and not xs.quantified and _note(xs).startswith("state:")   # only above target
    assert _link(g, "unicredit.cet1_target", "unicredit.buybacks").transition.sign == "-"


def test_commerzbank_stake_reaches_capital_and_distributions(g):
    reached = _reach(g, "unicredit.cbk_stake")
    assert {"unicredit.rwa", "unicredit.cet1_ratio", "unicredit.buybacks", "unicredit.total_distributions", REV} <= reached
    rwa = _link(g, "unicredit.cbk_stake", "unicredit.rwa")
    assert rwa.transition.sign == "+" and "state:" in _note(rwa)                    # a step at control, not a slope
    inc = _link(g, "unicredit.cbk_stake", "unicredit.cbk_equity_income")
    assert inc.identity == "ucg.id.cbk_income" and inc.quantified
    line = _link(g, "unicredit.cbk_equity_income", "unicredit.dividends_equity_income")
    assert not line.quantified and "not disclosed" in _note(line)                   # a part whose level is undisclosed


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _ucg_links(g):
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
    """An oil-price shock: no UniCredit path starts there. The structure carries it to group NII through the ECB's
    response to euro inflation (m03 -> m10 -> m28, sized from the disclosed scenarios) and on the structural side to
    interest paid (the calibrated pass-through, then deposits x cost, exact) and loan interest; to the long end and
    capital (s05 -> s76, s33; the hedge roll into hedge income, exact; FVOCI marks into CET1, exact); to costs through
    inflation; to fees through the equity market; to the stake's income; and, through slower euro growth, to
    unemployment, the cost of risk (provisions = loans x cost of risk, exact) and the overlay release, loan volumes, RWA
    and the Italian spread. It stops at the share price, at the reconciling division revenues (matrix columns), and, at
    the trace depth, inside the fee chains."""
    tr = trace(g, "oil.brent", UCG)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    assert routes[("m03", "m10", "m28")]["ends_at"] == NII and not routes[("m03", "m10", "m28")]["uncalibrated_steps"]
    full = routes[("m03", "m10", "ucg-c-ecb-depcost", "ucg-c-depcost-interest")]
    assert full["ends_at"] == "unicredit.deposit_interest_expense" and not full["uncalibrated_steps"]
    assert routes[("m03", "m10", "s05", "ucg-c-bund-hedgeyield", "ucg-c-hedgeyield-nii")]["ends_at"] == "unicredit.hedge_income"
    assert ("ucg-m-oil-eurogdp", "ucg-m-gdp-unemp", "ucg-c-unemp-cor", "ucg-c-cor-llp") in routes
    assert ("ucg-m-oil-eurogdp", "ucg-m-gdp-unemp", "ucg-c-unemp-overlays", "ucg-c-overlays-llp") in routes
    assert ("m03", "ucg-c-cpi-italycosts", "ucg-a-costs-italy-costs") in routes
    ends = {r["ends_at"] for r in tr["routes"] if r["reaches_endpoint"]}
    assert {NII, "unicredit.operating_costs", "unicredit.loan_loss_provisions", "unicredit.fees_insurance",
            "unicredit.cet1_ratio", "unicredit.cet1_capital", "unicredit.cbk_equity_income",
            "unicredit.loan_interest_income", "unicredit.deposit_interest_expense", "unicredit.hedge_income"} <= ends
    short_stops = {r["ends_at"] for r in tr["routes"] if not r["reaches_endpoint"] and len(r["steps"]) < 8}
    assert short_stops == {"unicredit.share_price", *{f"unicredit.{d}_revenue" for d in ("italy", "germany", "austria", "cee", "gcc")}}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = client.get(f"{B}/context/v4").json()["domain_pack"]
    support = pack["domain_specific_support_objects"]
    bridge = {b["composition_id"]: b for b in support["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    assert bridge["ucg.comp.revenue_by_division"]["role"] == "reconciling"
    assert bridge["ucg.comp.revenue_by_line"]["role"] == "driving"
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["ucg-a-rev-net-interest-income"]["dependency_type"] == "accounting_identity"
    assert rels["ucg-c-cor-llp"]["dependency_type"] == "accounting_identity"
    assert rels["ucg-c-depint-italynii"]["status"] == "represented_uncalibrated"
    assert rels["ucg-c-depint-italynii"]["axelrod"]["transition"]["sign"] == "-"
    assert rels["m28"]["axelrod"]["transition"]["evidence"]["magnitude"] == "model"
    assert "financial_identities" in support


def test_new_objects_reach_the_api(client):
    ids = "unicredit.deposit_cost,unicredit.hedge_yield,unicredit.cet1_capital,unicredit.revenue,unicredit.italy_nii"
    body = client.get(f"{B}/query", params={"node_ids": ids, "depth": 1}).json()
    got = {v["id"] for v in body["values"]}
    assert set(ids.split(",")) <= got and "unicredit.cet1_ratio" in got
    view = client.get(f"{B}/construction/{UCG}").json()["construction"]
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = client.get(f"{B}/construction/{UCG}/trace", params={"start": ECB}).json()["trace"]
    assert tr["reaches_endpoint"]
