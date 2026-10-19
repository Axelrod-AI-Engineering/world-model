"""China Construction Bank's business construction (Oct 18): the compositions, operating and financial paths, and their
transitions in data/worlds/sally_demo/construction/china_construction_bank.yaml, checked in the loaded model, in the
v4.1.4 export, and through the service API (docs/construction/china_construction_bank.md has the gap register these
tests close). The second bank after JPMorgan, with its own economics: administered benchmarks (the LPR, posted deposit
rates), a large government bond book, a mortgage-heavy loan book, fee caps, and the state as shareholder. Sally's world
loads once for the module; no client data is read."""

from __future__ import annotations

import math

import pytest
import yaml
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import construction_view, trace
from axelrod_wm.model.construction import model_levels, reconcile_identities, validate_construction
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.scenario import v1_reads as v1

CCB = "china_construction_bank"
P = CCB + "."
NII, OI, PBT, NP = P + "net_interest_income", P + "operating_income", P + "profit_before_tax", P + "operating_profit"
NIM, NPL = P + "net_interest_margin", P + "npl_ratio"
LPR, CGB, PROP = "pboc.loan_prime_rate", "cgbs.yield_10y", "china_economy.property_sales"

COMPOSITIONS = {   # id -> (total, additive)
    "ccb.comp.operating_income_by_line": (OI, True),
    "ccb.comp.operating_income_by_segment": (OI, True),
    "ccb.comp.nii": (NII, True),
    "ccb.comp.interest_income": (P + "interest_income", True),
    "ccb.comp.interest_expense": (P + "interest_expense", True),
    "ccb.comp.fees": (P + "net_fee_income", True),
    "ccb.comp.pretax": (PBT, True),
    "ccb.comp.pbt_by_segment": (PBT, True),
    "ccb.comp.net_profit": (NP, True),
    "ccb.comp.credit_impairment": (P + "credit_impairment", True),
    "ccb.comp.loan_impairment": (P + "loan_impairment", True),
    "ccb.comp.loans_by_type": (P + "loans", True),
    "ccb.comp.earning_assets": (P + "earning_assets", True),
    "ccb.comp.loan_interest": (P + "loan_interest_income", True),
    "ccb.comp.capital_sources_uses": (P + "cet1_capital", False),
}
RECONCILING = {"ccb.comp.operating_income_by_segment", "ccb.comp.pbt_by_segment"}   # drives: false; the others drive
IDENTITIES = {   # id -> (form, target)
    "ccb.id.corporate_loan_income": ("product", P + "corporate_loan_income"),
    "ccb.id.mortgage_income": ("product", P + "mortgage_income"),
    "ccb.id.deposit_interest": ("product", P + "deposit_interest_expense"),
    "ccb.id.investment_interest": ("product", P + "investment_interest_income"),
    "ccb.id.nim": ("ratio", P + "net_interest_margin"),
    "ccb.id.cet1_ratio": ("ratio", P + "cet1_ratio"),
    "ccb.id.dividends": ("product", P + "dividends"),
    "ccb.id.npl_ratio": ("weighted_average", P + "npl_ratio"),
    "ccb.id.nonperforming_loans": ("product", P + "nonperforming_loans"),
    "ccb.id.provision_coverage": ("ratio", P + "provision_coverage"),
}
STOCK_FLOWS = {"ccb.sf.cet1_capital": P + "cet1_capital", "ccb.sf.mortgages": P + "mortgages",
               "ccb.sf.loan_loss_reserve": P + "loan_loss_reserve"}
CONVERTED = {   # the 23 tagged steps that now have a form (link -> edge type or "state")
    **{i: "identity" for i in ("ccb-c-corpyield-loanii", "ccb-c-corploans-loanii", "ccb-c-mortyield-loanii",
                               "ccb-c-mortgages-loanii", "ccb-c-depcost-depexp", "ccb-c-deposits-depexp",
                               "ccb-c-invyield-invii", "ccb-c-nii-nim", "ccb-c-iea-nim", "ccb-c-cet1cap-ratio",
                               "ccb-c-rwa-ratio", "ccb-c-np-dividends", "ccb-c-payout-dividends", "ccb-c-mortnpl-npl",
                               "ccb-c-devnpl-npl", "ccb-c-npl-coverage")},
    **{i: "stock_flow" for i in ("ccb-c-np-cet1", "ccb-c-dividends-cet1", "ccb-c-injection-cet1", "ccb-c-prepay-mortgages")},
    **{i: "state" for i in ("ccb-c-coverage-allowance", "ccb-c-req-payout", "ccb-c-maturities-invyield")},
}
NOT_CONVERTED = {"ccb-c-npy-invyield", "ccb-c-listrate-timeshare", "ccb-c-timeshare-depcost", "ccb-c-deposits-oea",
                 "ccb-c-cgb-trading", "ccb-c-fvoci-cet1", "ccb-c-npl-writeoffs", "ccb-c-otherpers-loanii",
                 "ccb-c-loans-rwa", "ccb-c-corploans-corpyield"}
# views that leave something out (other income, the Others segment, central bank and interbank items, other
# impairment, bills and overseas loans); the rest are identities (NII, net profit, the allowance roll-forward)
WITH_REMAINDER = set(COMPOSITIONS) - {"ccb.comp.nii", "ccb.comp.net_profit", "ccb.comp.loan_impairment",
                                      "ccb.comp.capital_sources_uses"}
PATHS = {  # a Chinese state bank's economics -> the named path(s) that carry them
    "LPR cuts, loan repricing and NII": ["ccb.path.lpr_nii"],
    "deposit-rate cuts, repricing and migration": ["ccb.path.deposit_repricing"],
    "bond yields, reinvestment, gains and FVOCI": ["ccb.path.cgb_yields", "ccb.path.securities_reinvestment"],
    "property, mortgages and asset quality": ["ccb.path.property_credit"],
    "policy direction: fiscal mortgage subsidy": ["ccb.path.mortgage_subsidy"],
    "loan growth by type and RWA": ["ccb.path.credit_growth"],
    "fees": ["ccb.path.wealth_fees"],
    "capital, payout and state support": ["ccb.path.capital_payout", "ccb.path.state_capital",
                                          "ccb.path.capital_requirements"],
}
REDUCED_FORMS = {"s27": "ccb.path.lpr_nii", "s29": "ccb.path.lpr_nii", "s58": "ccb.path.cgb_yields",
                 "s28": "ccb.path.property_credit", "s30": "ccb.path.property_credit", "s31": "ccb.path.credit_growth"}
SIZES = {"s27": 0.6, "s28": -0.4, "s29": 0.55, "s30": -0.3, "s31": 0.2, "s58": 0.2}   # Sally's records, unchanged
# identity, stock-flow, matrix and state steps carry a conversion tag in their note; notes stay in the construction
# file (the graph does not hold them), so they are read from there
NOTES = {i["id"]: i.get("note") or "" for i in yaml.safe_load(
    open("data/worlds/sally_demo/construction/china_construction_bank.yaml"))["interactions"]}
SOURCES = {"ccb.v1", "ccb.r1", "ccb.r2", "ccb.r3", "ccb.r4", "ccb.r5", "ccb.pub"}


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


def _own_links(g):
    own = set(g.entities[CCB].subentity_ids)
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
def test_no_construction_problems_for_ccb(g):
    assert construction_view(g, CCB)["problems"] == []
    assert not [p for p in validate_construction(g) if CCB in p or "ccb." in p or "ccb-" in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == CCB and c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        if cid in WITH_REMAINDER:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)                          # one unit within a view
        if cid in RECONCILING:                                          # reconciled, never linked into the total
            assert c.drives is False
            assert not [i for i in g.active_interactions() if i.source_id in _parts(c) and i.target_id == c.total]
            continue
        assert c.drives is True, cid
        for sid in _parts(c):
            i = _link(g, sid, c.total)
            assert str(i.edge_type) == "accounting" and i.quantified and i.forward.effect.mean() > 0, (cid, sid)
            assert i.forward.effect.sd() <= 0.01                         # a fixed weight, not a fitted coefficient
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
            assert p.entity_id == CCB and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != CCB:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            if i.id in ("s56", "s03"):                                   # shared macro records, used as given
                continue
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)   # no size is claimed


def test_shared_driver_responses_are_parallel_branches(g):
    p = g.paths["ccb.path.lpr_nii"]
    by = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}
    assert {"corporate", "mortgage", "deposits", "bonds", "volume"} <= set(by)
    assert {i.source_id for i in by.values()} == {LPR}
    for pid, src in (("ccb.path.cgb_yields", CGB), ("ccb.path.property_credit", PROP),
                     ("ccb.path.deposit_repricing", P + "deposit_list_rate")):
        q = g.paths[pid]
        assert {g.interactions[s.interaction_id].source_id for s in q.steps if s.branch} == {src}, pid


def test_reduced_forms_are_never_steps_of_their_structural_paths(g):
    steps = {pid: {s.interaction_id for s in p.steps} for pid, p in g.paths.items() if p.entity_id == CCB}
    for iid, pid in REDUCED_FORMS.items():
        assert iid not in steps[pid], (iid, pid)
        assert pid in g.interactions[iid].transition.mechanism, iid    # the record names its structural path


# -- a Chinese state bank's economics ---------------------------------------------------------------------------------
def test_values_name_their_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == CCB and s.id != P + "share_price"]
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]
    assert g.subentities[NP].features["metric"] == "net_profit"           # the id says operating profit; it is not
    assert all(s.unit.startswith("CNY") or s.unit == "pct" for s in own)  # the company's own currency


def test_loans_reprice_off_two_lpr_tenors_and_deposits_lag(g):
    assert _link(g, LPR, P + "corporate_loan_yield").transition.sign == "+"
    assert _link(g, LPR, "pboc.loan_prime_rate_5y").transition.sign == "+"
    mort = _link(g, "pboc.loan_prime_rate_5y", P + "mortgage_yield").transition
    assert "reset" in mort.mechanism and "12 months" in mort.timing.build and "1 January" in mort.timing.calendar
    dep = _link(g, P + "deposit_list_rate", P + "deposit_cost").transition
    assert "mature" in dep.timing.onset and "years" in dep.timing.build      # slower than the asset side
    assert not [i for i in g.active_interactions() if i.source_id == LPR and i.target_id == P + "deposit_cost"]


def test_deposit_repricing_has_its_counter_paths(g):
    p = g.paths["ccb.path.deposit_repricing"]
    by = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}
    assert by["cost"].transition.sign == "+" and by["migration"].transition.sign == "+"
    assert by["wealth"].transition.sign == "-"          # a cut lifts agency fees: the offset
    assert by["prepayment"].transition.sign == "-"      # a cut speeds mortgage prepayment
    assert by["mix"].transition.sign == "-" and "state in words" in NOTES[by["mix"].id]


def test_falling_yields_reach_income_gains_and_capital_separately(g):
    marks = _reach(g, P + "fvoci_reserve")
    assert P + "cet1_capital" in marks and not marks & {NII, OI, PBT, NP}          # marks reach capital, not profit
    assert _link(g, CGB, P + "other_operating_income").transition.sign == "-"      # gains when yields fall
    reinvest = _link(g, P + "bond_maturities", P + "investment_yield")
    assert reinvest.transition.sign == "-" and NOTES[reinvest.id].startswith("state:")  # below-book reinvestment
    assert [p.form for p in reinvest.parameters] == ["piecewise"]                   # the sign flips above book


def test_property_reaches_impairment_through_npls_and_the_outlook(g):
    p = g.paths["ccb.path.property_credit"]
    by = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}
    assert {"mortgage_quality", "developer_quality", "volume", "outlook"} <= set(by)
    assert by["outlook"].target_id == P + "allowance_build"            # IFRS 9: the outlook books a reserve at once
    assert _link(g, NPL, P + "allowance_build").transition.sign == "-"
    assert _link(g, P + "provision_coverage", P + "allowance_build").transition.sign == "+"   # the smoothing buffer
    assert g.compositions["ccb.comp.loan_impairment"].members == [P + "net_write_offs", P + "allowance_build"]


def test_policy_support_is_represented(g):
    sub = "china_economy.mortgage_interest_subsidy"
    assert _link(g, sub, P + "mortgage_npl_ratio").transition.sign == "-"
    assert not [i for i in g.active_interactions() if i.source_id == sub and i.target_id in (P + "mortgage_yield", NIM)]
    assert _link(g, P + "capital_injection", P + "cet1_capital").transition.sign == "+"


def test_capital_is_a_stock_with_flows_not_an_additive_view(g):
    c = g.compositions["ccb.comp.capital_sources_uses"]
    assert c.additive is False
    for src, sign in ((NP, "+"), (P + "dividends", "-"), (P + "capital_injection", "+")):
        i = _link(g, src, c.total)                           # flows accumulate into the stock (ccb.sf.cet1_capital)
        assert str(i.edge_type) == "stock_flow" and i.identity == "ccb.sf.cet1_capital" and i.quantified, src
        assert (i.forward.effect.mean() > 0) == (sign == "+"), src
    fvoci = _link(g, P + "fvoci_reserve", c.total)          # a stock's change into a stock: no form, a signed link
    assert not fvoci.quantified and fvoci.transition.sign == "+" and NOTES[fvoci.id].startswith("not converted")


def test_segment_views_are_separate_from_the_driven_view(g):
    line, seg = g.compositions["ccb.comp.operating_income_by_line"], g.compositions["ccb.comp.operating_income_by_segment"]
    assert not set(_parts(line)) & set(_parts(seg))
    seg_side = set(_parts(seg)) | set(_parts(g.compositions["ccb.comp.pbt_by_segment"]))
    assert not [i.id for i in g.active_interactions() if i.target_id in seg_side and str(i.edge_type) != "accounting"]


def test_identities_and_stock_flows_exist_and_reconcile(g):
    for iid, (form, target) in IDENTITIES.items():
        x = g.identities[iid]
        assert x.form == form and x.target == target and x.entity_id == CCB, iid
    rows = {r["identity_id"]: r for r in reconcile_identities(g, model_levels(g, "median"))}
    assert all(rows[iid]["status"] == "ok" for iid in IDENTITIES), {k: rows[k]["status"] for k in IDENTITIES}
    for sid, stock in STOCK_FLOWS.items():
        assert g.stock_flows[sid].stock == stock and g.stock_flows[sid].period_days == 365, sid
    # a deposit-cost rise makes the (negative) expense larger; a larger NII widens the margin, more assets dilute it
    assert _link(g, P + "deposit_cost", P + "deposit_interest_expense").forward.effect.mean() < 0
    assert _link(g, NII, NIM).forward.effect.mean() > 0 > _link(g, P + "earning_assets", NIM).forward.effect.mean()


def test_tagged_steps_are_converted_or_say_why_not(g):
    for iid, form in CONVERTED.items():
        i = g.interactions[iid]
        if form == "state":
            assert i.parameters and NOTES[iid].startswith("state:"), iid
        else:
            assert str(i.edge_type) == form and i.identity and i.quantified, iid
            assert i.transition is not None and i.transition.mechanism, iid    # the business text is kept
    for iid in NOT_CONVERTED:
        assert not g.interactions[iid].quantified and NOTES[iid].startswith("not converted"), iid
    assert len(CONVERTED) + len(NOT_CONVERTED) == 33


def test_no_new_statistical_link_on_nii(g):
    i = _link(g, NII, P + "share_price")                    # written out, so the taxonomy default does not apply
    assert not i.quantified and i.transition.sign == "+"
    new_calibrated = {i.id for i in _own_links(g) if i.id.startswith("ccb-c-") and i.quantified
                      and str(i.edge_type) == "causal"}
    assert new_calibrated == set()                           # sizes come only from identities and stock-flows


def test_existing_records_keep_their_sizes_and_are_scoped(g):
    for iid, mu in SIZES.items():
        i = g.interactions[iid]
        assert i.forward.effect.mean() == pytest.approx(mu), iid
        tr = i.transition
        assert tr is not None and tr.evidence.magnitude == "assumption" and tr.unresolved, iid


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _own_links(g):
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
    assert seen >= 40


# -- generalization -------------------------------------------------------------------------------------------------------
def test_generalization_trace_a_china_growth_slowdown(g):
    """A slowdown in Chinese growth: no CCB path starts there. The structure carries it through the PBoC's easing
    (s02) into every LPR branch (loan repricing, mortgages via the 5-year LPR, posted deposit cuts, the bond curve,
    credit demand), through the bond curve (s57) into reinvestment, gains and FVOCI marks, through property (s04) into
    asset quality, and through activity into card and settlement fees. Calibrated end to end along Sally's records
    (s02 -> s27 -> s29; s57 -> s58 -> s29; s02 -> s04 -> s28 -> s30; s02 -> s03 -> s31) and, since the conversion, on
    through the exact steps: net profit -> CET1 capital (stock-flow) -> CET1 ratio (identity), and net profit ->
    dividends (identity) -> CET1 capital. Traced through totals; it stops at the share price (nothing leads on) and,
    at the depth bound, at the allowance build."""
    tr = trace(g, "china_economy.gdp_growth", CCB, through_totals=True)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    for calibrated in (("s02", "s27", "s29"), ("s57", "s58", "s29"), ("s02", "s04", "s28", "s30"), ("s02", "s03", "s31")):
        assert routes[calibrated]["ends_at"] == NP and not routes[calibrated]["uncalibrated_steps"], calibrated
    for calibrated in (("s02", "s27", "s29", "ccb-c-np-cet1", "ccb-c-cet1cap-ratio"),
                       ("s02", "s27", "s29", "ccb-c-np-dividends", "ccb-c-dividends-cet1", "ccb-c-cet1cap-ratio")):
        assert routes[calibrated]["ends_at"] == P + "cet1_ratio" and not routes[calibrated]["uncalibrated_steps"]
    assert ("ccb-c-gdp-cardfees", "ccb-a-fee-card-fees") in routes
    assert ("s02", "ccb-c-lpr-listrate", "ccb-c-listrate-agency", "ccb-a-fee-agency-fees") in routes
    ends = {r["ends_at"] for r in tr["routes"] if r["reaches_endpoint"]}
    assert {NP, P + "net_fee_income", P + "loan_interest_income", P + "deposit_interest_expense", P + "loan_impairment",
            P + "cet1_capital", P + "cet1_ratio", P + "dividends", P + "provision_coverage"} <= ends
    stops = {r["ends_at"] for r in tr["routes"] if not r["reaches_endpoint"]}
    assert stops <= {P + "share_price", P + "allowance_build"}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["ccb-a-nii-interest-income"]["dependency_type"] == "accounting_identity"
    assert rels["ccb-c-lpr-corpyield"]["status"] == "represented_uncalibrated"
    assert rels["ccb-c-nii-nim"]["dependency_type"] == "accounting_identity"          # an identity, derived weight
    ids = {x.get("id") or x.get("identity_id") for x in pack["domain_specific_support_objects"]["financial_identities"]}
    assert set(IDENTITIES) | set(STOCK_FLOWS) <= ids
    roles = {cid: bridge[cid].get("role") for cid in RECONCILING}
    assert set(roles.values()) == {"reconciling"}
    assert rels["ccb-c-depcost-depexp"]["axelrod"]["transition"]["sign"] == "-"
    assert rels["s27"]["axelrod"]["transition"]["evidence"]["magnitude"] == "assumption"


def test_new_objects_reach_the_api(client):
    ids = f"{P}deposit_cost,{P}allowance_build,{P}cet1_capital,{P}operating_income"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and P + "deposit_interest_expense" in got
    view = v1.construction(client, CCB)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, CCB, LPR)
    assert tr["reaches_endpoint"]
