"""Citigroup's business construction (Oct 18): the compositions, operating and financial paths, and their transitions in
<client root>/worlds/sally_demo/construction/citigroup.yaml, checked in the loaded model, in the v4.1.4 export, and through the
service API (docs/construction/citigroup.md has the gap register these tests close). The second bank after JPMorgan:
the same bank skeleton on Citi's own reporting (five businesses plus All Other, NII and non-interest revenue per
segment, a mostly non-USD rate sensitivity, an international footprint, card credit, the expense program, capital and
the Banamex exit). Sally's world loads once for the module; no client data is read."""

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
    reconcile_matrices,
    reconciling_views,
    validate_construction,
)
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.clients import client_path, skip_without_client
from tests.scenario import v1_reads as v1

skip_without_client('sally_demo')

CIT = "citigroup"
C = "citigroup."
NII, REV, NI = C + "net_interest_income", C + "net_revenue", C + "net_income"
FED, UST10, SPREAD = "federal_reserve.policy_rate", "us_treasuries.yield_10y", "us_capital_markets.credit_spread"
UNEMP, BASKET, FXB = "us_economy.unemployment_rate", C + "non_usd_rate_basket", C + "translation_fx_basket"

COMPOSITIONS = {   # id -> (total, additive)
    "cit.comp.revenue_by_segment": (REV, True),
    "cit.comp.services": (C + "services_revenue", True),
    "cit.comp.services_nii": (C + "services_nii", True),
    "cit.comp.services_nir": (C + "services_nir", True),
    "cit.comp.markets": (C + "markets_revenue", True),
    "cit.comp.fixed_income": (C + "fixed_income_markets", True),
    "cit.comp.banking": (C + "banking_revenue", True),
    "cit.comp.wealth": (C + "wealth_revenue", True),
    "cit.comp.uscc": (C + "uscc_revenue", True),
    "cit.comp.uscc_nir": (C + "uscc_nir", True),
    "cit.comp.all_other": (C + "all_other_revenue", True),
    "cit.comp.revenue_by_type": (REV, True),
    "cit.comp.nii_balance_sheet": (NII, True),
    "cit.comp.revenue_by_region": (REV, True),
    "cit.comp.pretax": (C + "pretax_income", True),
    "cit.comp.net_income": (NI, True),
    "cit.comp.net_income_by_segment": (NI, True),
    "cit.comp.expense": (C + "operating_expenses", True),
    "cit.comp.credit_costs": (C + "provision_for_credit_losses", True),
    "cit.comp.uscc_provision": (C + "uscc_provision", True),
    "cit.comp.cet1_target": (C + "cet1_target", True),
    "cit.comp.capital_sources_uses": (C + "cet1_capital", False),
}
# one driving view per total: these reconcile to their totals without driving them
RECONCILING = {"cit.comp.revenue_by_type": "matrix cit.mx.revenue", "cit.comp.revenue_by_region": "drives: false",
               "cit.comp.nii_balance_sheet": "drives: false", "cit.comp.net_income_by_segment": "drives: false"}
IDENTITIES = {"cit.id.nii_ex_markets": "difference", "cit.id.uscc_nii": "product", "cit.id.uscc_ncl": "product",
              "cit.id.uscc_nco": "weighted_average", "cit.id.interchange": "product", "cit.id.rewards": "product",
              "cit.id.mexico": "ratio", "cit.id.efficiency": "ratio", "cit.id.cet1_ratio": "ratio"}
# views where the business leaves something out (reconciling items, Corporate/Other, other fees, NCI, other segments)
WITH_REMAINDER = {"cit.comp.revenue_by_segment", "cit.comp.uscc_nir", "cit.comp.all_other", "cit.comp.revenue_by_region",
                  "cit.comp.net_income", "cit.comp.net_income_by_segment", "cit.comp.expense", "cit.comp.credit_costs"}
REVENUE_VIEWS = ("cit.comp.revenue_by_segment", "cit.comp.revenue_by_type", "cit.comp.revenue_by_region")
PATHS = {  # Citi's economics -> the named path(s) that carry them
    "non-USD rates and Services NII": ["cit.path.non_usd_rates"],
    "USD rates, deposit costs and the segment cells": ["cit.path.usd_rates"],
    "securities repricing and the long end": ["cit.path.securities_reinvestment", "cit.path.long_end"],
    "cross-border flows and Services fees": ["cit.path.cross_border"],
    "markets and volatility": ["cit.path.markets"],
    "deal activity and Banking": ["cit.path.deals_banking"],
    "credit spreads, loan hedges and wholesale credit": ["cit.path.wholesale_credit"],
    "card credit cycle": ["cit.path.card_credit"],
    "card growth and card fees net of rewards": ["cit.path.card_growth", "cit.path.card_spend"],
    "market levels and custody and wealth fees": ["cit.path.market_levels_fees"],
    "international footprint and FX translation": ["cit.path.fx_translation", "cit.path.mexico"],
    "transformation and the expense program": ["cit.path.transformation", "cit.path.investment_program"],
    "Banamex separation and legacy exits": ["cit.path.legacy_exits"],
    "capital, buybacks and dividends": ["cit.path.capital_payout", "cit.path.capital_requirement"],
}
YAML = client_path("worlds/sally_demo/construction/citigroup.yaml")
SOURCES = {"cit.v1", "cit.wb", "cit.co", "cit.r1", "cit.r2", "cit.r3", "cit.r4", "cit.r5", "cit.r6", "cit.x1", "cit.x2",
           "cit.x3", "cit.peer", "cit.pub"}


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


def _cit_links(g):
    own = set(g.entities[CIT].subentity_ids)
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


def _notes() -> dict[str, str]:
    """The conversion tags in each link's `note` (the YAML keeps them; the loaded graph does not carry notes)."""
    return {i["id"]: i.get("note", "") for i in yaml.safe_load(YAML.read_text())["interactions"]}


def _branches(g, pid):
    return {s.branch: g.interactions[s.interaction_id] for s in g.paths[pid].steps if s.branch}


# -- structure ---------------------------------------------------------------------------------------------------------
def test_no_construction_problems_for_citigroup(g):
    assert construction_view(g, CIT)["problems"] == []
    assert not [p for p in validate_construction(g) if "citigroup" in p or "cit." in p or "cit-" in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == CIT and c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        if cid in WITH_REMAINDER:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)                          # one unit within a view
        if cid in RECONCILING:                                           # observed and reconciled, never driving
            assert not [i.id for i in g.active_interactions() if i.source_id in _parts(c) and i.target_id == c.total
                        and str(i.edge_type) == "accounting" and i.quantified], cid
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


def test_one_driving_view_per_total(g):
    assert {cid: why for cid, why in reconciling_views(g).items() if cid.startswith("cit.")} == RECONCILING
    m = g.matrices["cit.mx.revenue"]
    assert m.rows == "cit.comp.revenue_by_segment" and m.drives == "rows"
    assert {cell for cols in m.cells.values() for cell in cols.values()} >= {C + "services_nii", C + "uscc_nii", C + "markets_nii"}
    assert all(r["status"] == "ok" for row in reconcile_matrices(g, model_levels(g, "median")) if row["matrix_id"] == "cit.mx.revenue" for r in row["lines"])
    for row in reconcile(g, model_levels(g, "median")):          # round construction levels add up at the medians
        if row["composition_id"].startswith("cit."):
            assert row["status"] == "ok", row["composition_id"]


def test_identities_and_the_capital_stock_flow_hold_with_derived_weights(g):
    for iid, form in IDENTITIES.items():
        assert g.identities[iid].form == form, iid
        terms = [i for i in g.active_interactions() if str(i.edge_type) == "identity" and i.identity == iid]
        assert terms and all(i.quantified and i.forward.effect.sd() < 0.01 for i in terms), iid
    rows = {r["identity_id"]: r for r in reconcile_identities(g, model_levels(g, "median"))}
    assert all(rows[iid]["status"] == "ok" for iid in IDENTITIES)
    sf = g.stock_flows["cit.sf.cet1"]
    assert sf.stock == C + "cet1_capital" and set(sf.inflows) == {NI, C + "dta_utilization"}
    for src in (NI, C + "buybacks", C + "common_dividends", C + "dta_utilization"):
        i = _link(g, src, C + "cet1_capital")
        assert str(i.edge_type) == "stock_flow" and i.forward.kernel.accumulates, src
    assert _link(g, C + "net_revenue", C + "efficiency_ratio").forward.effect.mean() < 0   # more revenue, a lower ratio


def test_views_of_net_revenue_are_never_added(g):
    parts = {cid: set(_parts(g.compositions[cid])) for cid in REVENUE_VIEWS}
    for a in REVENUE_VIEWS:
        for b in REVENUE_VIEWS:
            if a < b:
                assert not parts[a] & parts[b], (a, b)
    # no segment cell belongs to the type or regions view: the matrix is not expressed as two additive views
    cells = {s for cid in ("cit.comp.services", "cit.comp.uscc") for s in _parts(g.compositions[cid])}
    assert not cells & (parts["cit.comp.revenue_by_type"] | parts["cit.comp.revenue_by_region"])


def test_required_paths_exist(g):
    for need, pids in PATHS.items():
        for pid in pids:
            p = g.paths[pid]
            assert p.entity_id == CIT and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != CIT:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)   # no size is claimed


def test_shared_driver_responses_are_parallel_branches(g):
    usd = _branches(g, "cit.path.usd_rates")
    assert {"beta", "tts_spread", "wealth_spread", "loans", "cards", "treasury", "markets", "markets_offset"} <= set(usd)
    assert {i.source_id for i in usd.values()} == {FED}
    assert {i.source_id for i in _branches(g, "cit.path.long_end").values()} == {UST10}
    assert {i.source_id for i in _branches(g, "cit.path.wholesale_credit").values()} == {SPREAD}
    assert {i.source_id for i in _branches(g, "cit.path.fx_translation").values()} == {FXB}
    assert {i.source_id for i in _branches(g, "cit.path.non_usd_rates").values()} == {BASKET}


def test_reduced_forms_are_never_steps_of_their_structural_paths(g):
    steps = {pid: {s.interaction_id for s in p.steps} for pid, p in g.paths.items() if p.entity_id == CIT}
    assert "m26" not in steps["cit.path.usd_rates"]
    assert "cit-c-nonusd-nii" not in steps["cit.path.non_usd_rates"]
    assert "s16" not in steps["cit.path.markets"]
    assert "s19" not in steps["cit.path.cross_border"]


# -- Citi's economics ---------------------------------------------------------------------------------------------------
def test_values_name_their_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == CIT and s.id != C + "share_price"]
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]
    assert g.subentities[NII].features["metric"] == "net_interest_income"
    assert g.subentities["usd_mxn.rate"].features.get("basis")


def test_segments_follow_the_recast_perimeter(g):
    seg = g.compositions["cit.comp.revenue_by_segment"]
    assert seg.members == [C + x for x in ("services_revenue", "markets_revenue", "banking_revenue", "wealth_revenue",
                                           "uscc_revenue", "all_other_revenue")]
    assert C + "citigold_retail_banking" in g.compositions["cit.comp.wealth"].members      # retail banking now in Wealth
    assert "U.S. Personal Banking" in g.subentities[C + "uscc_revenue"].features["basis"]   # named only as the former perimeter
    assert not [s for s in g.subentities if s.startswith(C) and "uspb" in s]


def test_nii_ex_markets_is_its_own_view_of_firm_nii(g):
    kpi, bs = g.identities["cit.id.nii_ex_markets"], g.compositions["cit.comp.nii_balance_sheet"]
    assert kpi.of == NII and kpi.minus == [C + "markets_nii"] and bs.total == NII and not bs.drives
    down, back = g.interactions["cit-c-fed-mktsnii"].transition, g.interactions["cit-c-fed-nir-offset"].transition
    assert down.sign == "-" and back.sign == "+"      # NII falls, principal transactions earn it back: revenue neutral


def test_non_usd_rates_reach_services_nii_and_the_reduced_form_is_calibrated_from_the_disclosure(g):
    for src in ("ecb.policy_rate", "boj.policy_rate", "pboc.loan_prime_rate"):
        assert _link(g, src, BASKET).transition.sign == "+"
    assert _link(g, BASKET, C + "tts_nii").transition.sign == "+" and _link(g, BASKET, C + "ss_nii").transition.sign == "+"
    i = g.interactions["cit-c-nonusd-nii"]
    assert i.quantified and i.transition.evidence.magnitude == "documented"
    assert i.state is not None and i.state.asymmetry is not None          # cuts move NII more than hikes
    assert i.state.asymmetry.falls["mu"] > i.state.asymmetry.rises["mu"] > 0
    z = i.forward.effect.mean() / g.subentities[BASKET].scale            # NII sd per +1pp of the basket (a rise)
    pct = math.exp(z * g.subentities[NII].scale) - 1
    assert 0.01 <= pct <= 0.03                                          # a percent or two of NII per 100bp, not more
    assert i.forward.kernel.lag.mean() >= 90                            # a gradual shift over the year


def test_usd_book_nets_out_within_the_year(g):
    up, catch_up = _link(g, FED, C + "tts_nii").transition, _link(g, C + "ib_deposit_cost", C + "tts_nii").transition
    assert up.sign == "+" and catch_up.sign == "-"
    m26 = g.interactions["m26"].transition
    assert m26 is not None and m26.evidence.magnitude == "assumption" and "neutral" in m26.breaker


def test_marks_reach_capital_not_income(g):
    reached = _reach(g, C + "aoci")
    assert C + "cet1_capital" in reached and C + "cet1_ratio" in reached
    assert not reached & {NI, REV, NII, C + "pretax_income"}


def test_loan_hedges_offset_wholesale_provisions(g):
    br = _branches(g, "cit.path.wholesale_credit")
    assert br["hedges"].target_id == C + "loan_hedges" and br["hedges"].transition.sign == "+"
    assert br["reserves"].target_id == C + "banking_provision" and br["reserves"].transition.sign == "-"


def test_card_fees_are_net_of_rewards_and_partner_payments(g):
    c = g.compositions["cit.comp.uscc_nir"]
    assert {C + "card_interchange", C + "card_rewards_partner"} <= set(c.members)
    assert g.subentities[C + "card_rewards_partner"].prior.mean() < 0 and g.subentities[C + "uscc_nir"].prior.mean() < 0
    assert _link(g, C + "card_spend_volume", C + "card_interchange").transition.sign == "+"
    assert _link(g, C + "card_spend_volume", C + "card_rewards_partner").transition.sign == "-"
    assert _link(g, C + "plcc_nco_rate", C + "card_rewards_partner").transition.sign == "+"   # partners share losses


def test_two_credit_clocks(g):
    assert _link(g, UNEMP, C + "uscc_reserve_build").transition.sign == "-"     # CECL: the outlook, at once
    assert not [i for i in g.active_interactions() if i.source_id == UNEMP and i.target_id in
                (C + "uscc_nco_rate", C + "gpcc_nco_rate", C + "plcc_nco_rate")]
    for book in ("gpcc_nco_rate", "plcc_nco_rate"):                             # losses: through delinquency
        lag = _link(g, C + "uscc_delinquency_rate", C + book)
        assert "quarter" in lag.transition.timing.onset and lag.transition.sign == "+"
    assert _link(g, C + "uscc_loans", C + "uscc_reserve_build").transition.sign == "-"   # growth costs a day-one reserve
    assert _link(g, C + "uscc_delinquency_rate", C + "uscc_loans").transition.sign == "-"  # underwriting tightens


def test_translation_hits_revenue_expenses_and_capital(g):
    signs = {t: _link(g, FXB, C + t).transition.sign for t in ("international_revenue", "operating_expenses", "aoci", "rwa")}
    assert signs == {"international_revenue": "-", "operating_expenses": "+", "aoci": "-", "rwa": "-"}
    assert _link(g, "usd_mxn.rate", C + "mexico_consumer_revenue").transition.sign == "-"
    # the dollar enters revenue only through the regions view (and Mexico, which the regions view leaves in its residual)
    revenue_parts = {s for cid in REVENUE_VIEWS for s in _parts(g.compositions[cid])} | \
        {s for cid in ("cit.comp.services", "cit.comp.markets", "cit.comp.fixed_income", "cit.comp.banking", "cit.comp.wealth",
                       "cit.comp.uscc", "cit.comp.uscc_nir", "cit.comp.all_other") for s in _parts(g.compositions[cid])}
    hit = {i.target_id for i in g.active_interactions() if i.source_id in (FXB, "usd_mxn.rate") and i.target_id in revenue_parts}
    assert hit == {C + "international_revenue", C + "mexico_consumer_revenue"} | {C + f"{s}_revenue" for s in ("services", "markets", "banking", "wealth")}
    assert str(_link(g, "usd_mxn.rate", C + "mexico_consumer_revenue").edge_type) == "identity"   # exact translation


def test_expense_program_has_a_payback_counter_path(g):
    assert _link(g, C + "investment_program", C + "compensation_expense").transition.sign == "-"
    assert _link(g, C + "investment_program", C + "productivity_savings").transition.sign == "+"
    assert _link(g, C + "productivity_savings", C + "compensation_expense").transition.sign == "+"
    assert _link(g, C + "transformation_spend", C + "technology_expense").transition.sign == "-"


def test_capital_is_a_stock_with_flows_not_an_additive_view(g):
    c = g.compositions["cit.comp.capital_sources_uses"]
    assert c.additive is False
    for src, sign in ((NI, "+"), (C + "buybacks", "-"), (C + "common_dividends", "-"), (C + "aoci", "+"), (C + "dta_utilization", "+")):
        i = _link(g, src, c.total)
        assert str(i.edge_type) != "accounting" and i.transition.sign == sign, src
    assert str(_link(g, C + "aoci", c.total).edge_type) == "causal"      # a level part of CET1, not a flow: no form


def test_banamex_exit_hits_earnings_not_capital(g):
    br = _branches(g, "cit.path.legacy_exits")
    assert br["cta_recycling"].target_id == C + "reconciling_items_revenue" and br["cta_recycling"].transition.sign == "+"
    assert br["cta_release"].target_id == C + "aoci" and br["cta_release"].transition.sign == "-"   # the offset in capital
    assert C + "reconciling_items_revenue" == g.compositions["cit.comp.revenue_by_segment"].residual


def test_only_evidenced_links_carry_new_sizes(g):
    new_calibrated = {i.id for i in _cit_links(g) if i.id.startswith("cit-c-") and i.quantified and str(i.edge_type) == "causal"}
    assert new_calibrated == {"cit-c-nonusd-nii"}
    for iid in ("m26", "s16", "s19"):                                  # the existing records keep their sizes, scoped
        tr = g.interactions[iid].transition
        assert tr is not None and tr.evidence.magnitude == "assumption" and tr.unresolved, iid


def test_existing_records_keep_their_sizes_and_are_scoped(g):
    for iid, mu in (("m26", 0.1), ("s16", 0.3), ("s19", 0.3), ("s25", 0.3), ("s26", 0.2)):
        assert g.interactions[iid].forward.effect.mean() == pytest.approx(mu), iid


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _cit_links(g):
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


def test_conversion_notes_say_what_was_converted_and_why_not(g):
    tags = _notes()
    assert tags["cit-c-nco-ncl"].startswith("converted Oct 18: identity cit.id.uscc_ncl")
    assert tags["cit-c-ni-cet1"].startswith("converted Oct 18: stock-flow cit.sf.cet1")
    assert tags["cit-c-ratio-buyback"].startswith("converted Oct 18: state")
    # every remaining uncalibrated Citi link that once carried a conversion tag says why it was not converted
    left = {k: v for k, v in tags.items() if k.startswith("cit-c-") and v.split(":")[0] in ("identity", "stock-flow", "state", "matrix")}
    assert not left, left


# -- generalization -------------------------------------------------------------------------------------------------------
def test_generalization_trace_an_oil_shock(g):
    """An oil-price shock: no Citi path starts there. The structure carries it to firm NII through the Fed's response to
    inflation (m01 -> m05 -> m06 -> m26, calibrated) and through slower growth (m04 -> m07 -> m26); to Services through
    growth (m04 -> s19, calibrated); to card reserves through unemployment (CECL now, uncalibrated); to card fees through
    nominal spend (card interchange, an identity now); to expenses through wage inflation; to capital through the
    long-end mark on AFS securities. Short routes stop only at parts of reconciling views (international revenue,
    non-interest revenue), which by design lead nowhere."""
    tr = trace(g, "oil.brent", CIT)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    assert routes[("m01", "m05", "m06", "m26")]["ends_at"] == NII and not routes[("m01", "m05", "m06", "m26")]["uncalibrated_steps"]
    assert routes[("m04", "s19")]["ends_at"] == C + "services_revenue"
    assert ("m04", "jpm-c-gdp-unemp", "cit-c-unemp-usccreserve", "cit-a-usccprov-uscc-reserve-build") in routes
    assert routes[("m01", "cit-c-cpi-spend", "cit-c-spend-interchange")]["ends_at"] == C + "card_interchange"   # an identity target
    assert ("m01", "m05", "cit-c-corecpi-comp", "cit-a-exp-compensation-expense") in routes
    ends = {r["ends_at"] for r in tr["routes"] if r["reaches_endpoint"]}
    assert {NII, C + "services_revenue", C + "uscc_provision", C + "operating_expenses", C + "cet1_capital",
            C + "cet1_ratio", C + "markets_revenue"} <= ends
    # short stops are only parts of reconciling views (nothing leads on from them by design)
    assert {r["ends_at"] for r in tr["routes"] if not r["reaches_endpoint"] and len(r["steps"]) < 8} <= \
        {C + "international_revenue", C + "noninterest_revenue"}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["cit-a-seg-services-revenue"]["dependency_type"] == "accounting_identity"
    assert rels["cit-c-basket-ttsnii"]["status"] == "represented_uncalibrated"
    assert rels["cit-c-basket-ttsnii"]["axelrod"]["transition"]["sign"] == "+"
    assert rels["m26"]["axelrod"]["transition"]["evidence"]["magnitude"] == "assumption"


def test_new_objects_reach_the_api(client):
    ids = "citigroup.tts_nii,citigroup.uscc_reserve_build,citigroup.cet1_capital,citigroup.net_revenue"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and C + "services_revenue" in got
    view = v1.construction(client, CIT)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, CIT, "ecb.policy_rate")
    assert tr["reaches_endpoint"]
