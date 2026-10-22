"""SoftBank Corp's business construction (Oct 18): the compositions, operating and financial paths, and their transitions
in <client root>/worlds/sally_demo/construction/softbank_corp.yaml, checked in the loaded model, in the v4.1.4 export, and
through the service API (the client root's docs/construction/softbank_corp.md has the gap register these tests close). The test of
whether the method carries over to a telecom operator: subscribers times ARPU, churn, price competition and
regulation, capex and depreciation, the AI build, funding costs in the yen rate environment, listed subsidiaries'
minorities, and the dividend. Sally's world loads once for the module; no client data is read."""

from __future__ import annotations

import math

import pytest
import yaml
from fastapi.testclient import TestClient

from axelrod_wm.api.app import create_app
from axelrod_wm.context.construction import construction_view, trace
from axelrod_wm.model.construction import model_levels, reconcile, reconcile_identities, validate_construction
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.clients import client_path, skip_without_client
from tests.scenario import v1_reads as v1

skip_without_client('sally_demo')

SBK = "softbank_corp"
OP, PRETAX, NI = "softbank_corp.operating_profit", "softbank_corp.pretax_income", "softbank_corp.net_income"
BOJ, JGB10 = "boj.policy_rate", "jgbs.yield_10y"

COMPOSITIONS = {   # id -> (total, additive)
    "sbk.comp.revenue_by_segment": ("softbank_corp.revenue", True),
    "sbk.comp.op_by_segment": (OP, True),
    "sbk.comp.op_ebitda_bridge": (OP, True),
    "sbk.comp.consumer_revenue": ("softbank_corp.consumer_revenue", True),
    "sbk.comp.consumer_profit": ("softbank_corp.consumer_op", True),
    "sbk.comp.enterprise_revenue": ("softbank_corp.enterprise_revenue", True),
    "sbk.comp.enterprise_profit": ("softbank_corp.enterprise_op", True),
    "sbk.comp.media_ec_profit": ("softbank_corp.media_ec_op", True),
    "sbk.comp.financial_profit": ("softbank_corp.financial_op", True),
    "sbk.comp.pretax": (PRETAX, True),
    "sbk.comp.net_income": (NI, True),
    "sbk.comp.consumer_ebitda": ("softbank_corp.consumer_ebitda", True),
    "sbk.comp.enterprise_ebitda": ("softbank_corp.enterprise_ebitda", True),
    "sbk.comp.minorities": ("softbank_corp.noncontrolling_interests", True),
}
RECONCILING = {"sbk.comp.op_ebitda_bridge"}      # drives: false: reconciled, carries no link into the total
IDENTITIES = {"sbk.id.mobile_revenue", "sbk.id.cancellations", "sbk.id.distribution_margin", "sbk.id.paypay_gmv",
              "sbk.id.tax", "sbk.id.nci_lycorp", "sbk.id.nci_paypay", "sbk.id.interest", "sbk.id.net_debt",
              "sbk.id.leverage", "sbk.id.dividends", "sbk.id.fcf"}
STOCK_FLOWS = {"sbk.sf.subscribers", "sbk.sf.debt"}
# views where the business leaves something out (the Other segment and eliminations, corporate adjustments, PayPay as
# the Financial remainder, other non-operating items); the others are exact splits or identities
WITH_REMAINDER = {"sbk.comp.revenue_by_segment", "sbk.comp.op_by_segment", "sbk.comp.financial_profit", "sbk.comp.pretax",
                  "sbk.comp.minorities"}
PATHS = {  # a telecom's economics -> the named path(s) that carry them
    "subscribers x ARPU and the existing-plan price increase": ["sbk.path.price_hike"],
    "churn and price competition": ["sbk.path.price_competition"],
    "regulation": ["sbk.path.regulation"],
    "AI data centres: capacity, utilization, depreciation": ["sbk.path.ai_compute"],
    "enterprise IT and distribution": ["sbk.path.enterprise_it"],
    "the yen rate environment and interest costs": ["sbk.path.policy_rate", "sbk.path.long_end"],
    "PayPay": ["sbk.path.paypay_growth"],
    "Media & EC and domestic demand": ["sbk.path.domestic_demand"],
    "costs: inflation and power": ["sbk.path.inflation", "sbk.path.power_prices"],
    "dividend policy, leverage and capital allocation": ["sbk.path.dividend_policy", "sbk.path.capital_allocation"],
}
SOURCES = {"sbk.r1", "sbk.r2", "sbk.r3", "sbk.r4", "sbk.co", "sbk.macro", "sbk.pub"}
NEW_MARKET_VALUES = {"japan_mobile_market.competitor_price_pressure", "japan_mobile_market.promotion_intensity",
                     "japan_mobile_market.data_traffic_per_user", "mic.mobile_pricing_regulation",
                     "japan_it_services_market.it_spending", "japan_it_services_market.ai_compute_demand",
                     "japan_power_market.wholesale_price"}
KEPT = "kept uncalibrated:"      # a step that fits no form says why
SPEC = client_path("worlds/sally_demo/construction/softbank_corp.yaml")
# a link's note (the form it needs: identity, stock-flow, matrix, state) lives in the construction file; the loaded
# graph does not keep notes
SPEC_LINKS = {i["id"]: i for i in yaml.safe_load(SPEC.read_text())["interactions"]}
NOTES = {k: i.get("note") or "" for k, i in SPEC_LINKS.items()}


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


def _sbk_links(g):
    own = set(g.entities[SBK].subentity_ids) | NEW_MARKET_VALUES
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
def test_no_construction_problems_for_softbank_corp(g):
    assert construction_view(g, SBK)["problems"] == []
    assert not [p for p in validate_construction(g) if "softbank_corp" in p or "sbk." in p or "sbk-" in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == SBK and c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid, (_total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        if not additive:
            continue
        if cid in RECONCILING:                                           # reconciling: no quantified link into the total
            assert not g.compositions[cid].drives
            assert not [i.id for i in g.active_interactions() if i.target_id == c.total and i.quantified
                        and i.source_id in _parts(c)]
            continue
        if cid in WITH_REMAINDER:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)                          # one unit within a view
        for sid in _parts(c):
            i = _link(g, sid, c.total)
            assert str(i.edge_type) == "accounting" and i.quantified and i.forward.effect.mean() > 0, (cid, sid)
            assert i.forward.effect.sd() <= 0.01                         # a fixed weight, not a fitted coefficient
            w = i.forward.effect.mean()                                  # the part's native sd over the total's
            assert w == pytest.approx(_native_sd(g.subentities[sid]) / _native_sd(g.subentities[c.total]), abs=0.01), (cid, sid)


def test_priors_reconcile_within_half_a_percent_and_every_view_is_checked(g):
    rows = {r["composition_id"]: r for r in reconcile(g, model_levels(g, "median")) if r["entity_id"] == SBK}
    assert {c for c, (_t, a) in COMPOSITIONS.items() if a} <= set(rows) and all(r["status"] == "ok" for r in rows.values())
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
            assert p.entity_id == SBK and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != SBK:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)   # no size is claimed


def test_shared_driver_responses_are_parallel_branches(g):
    def branches(pid):
        p = g.paths[pid]
        return {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}

    hike = branches("sbk.path.price_hike")
    assert {"arpu", "churn", "enterprise", "reinvest"} <= set(hike)
    assert {i.source_id for i in hike.values()} == {"softbank_corp.mobile_tariff_index"}
    comp = branches("sbk.path.price_competition")
    assert {i.source_id for i in comp.values()} == {"japan_mobile_market.competitor_price_pressure"} and len(comp) == 3
    assert {i.source_id for i in branches("sbk.path.policy_rate").values()} == {BOJ}
    assert {i.source_id for i in branches("sbk.path.long_end").values()} == {JGB10}
    assert {i.source_id for i in branches("sbk.path.power_prices").values()} == {"japan_power_market.wholesale_price"}


def test_reduced_forms_are_never_steps_of_their_structural_paths(g):
    steps = {pid: {s.interaction_id for s in p.steps} for pid, p in g.paths.items() if p.entity_id == SBK}
    assert "m33" not in steps["sbk.path.long_end"] and "s49" in steps["sbk.path.long_end"]
    assert "s47" not in steps["sbk.path.domestic_demand"]
    assert "s48" not in steps["sbk.path.ai_compute"]


# -- a telecom's economics -------------------------------------------------------------------------------------------------
def test_values_name_their_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == SBK and s.id != "softbank_corp.share_price"]
    assert len(own) >= 50
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]
    assert g.subentities[OP].features["metric"] == "operating_income"


def test_mobile_revenue_is_subscribers_times_arpu(g):
    rev = "softbank_corp.consumer_mobile_revenue"
    x = g.identities["sbk.id.mobile_revenue"]
    assert x.form == "product" and x.target == rev
    assert {"softbank_corp.mobile_arpu", "softbank_corp.main_subscribers"} <= set(x.factors)
    for src in ("softbank_corp.mobile_arpu", "softbank_corp.main_subscribers"):
        i = _link(g, src, rev)
        assert str(i.edge_type) == "identity" and i.quantified and i.forward.effect.mean() > 0
    assert _link(g, "softbank_corp.mobile_arpu", rev).id == "sbk-c-arpu-mobile"     # the written link keeps its transition
    sf = g.stock_flows["sbk.sf.subscribers"]
    assert sf.stock == "softbank_corp.main_subscribers" and sf.measure == "period_average"
    assert sf.outflows == ["softbank_corp.mobile_cancellations"] and sf.inflows == ["softbank_corp.gross_additions"]
    out = _link(g, "softbank_corp.mobile_cancellations", "softbank_corp.main_subscribers")
    assert str(out.edge_type) == "stock_flow" and out.forward.effect.mean() < 0
    assert "softbank_corp.mobile_churn_rate" in g.identities["sbk.id.cancellations"].factors
    assert rev in g.compositions["sbk.comp.consumer_revenue"].members


def test_price_increase_trades_arpu_against_churn_and_funds_the_network(g):
    tariff = "softbank_corp.mobile_tariff_index"
    assert _link(g, tariff, "softbank_corp.mobile_arpu").transition.sign == "+"
    assert _link(g, tariff, "softbank_corp.mobile_churn_rate").transition.sign == "+"        # the offset
    assert _link(g, tariff, "softbank_corp.network_capex").transition.sign == "+"
    assert _link(g, "softbank_corp.network_capex", "softbank_corp.consumer_depreciation").transition.sign == "-"
    assert _link(g, "softbank_corp.network_quality", "softbank_corp.mobile_churn_rate").transition.sign == "-"


def test_regulation_cuts_both_ways(g):
    reg = "mic.mobile_pricing_regulation"
    assert _link(g, reg, "softbank_corp.mobile_tariff_index").transition.sign == "-"           # ARPU pressure
    assert _link(g, reg, "japan_mobile_market.promotion_intensity").transition.sign == "-"     # lower sales costs
    promo = _link(g, "japan_mobile_market.promotion_intensity", "softbank_corp.consumer_cash_costs")
    assert promo.transition.sign == "-"                                                         # a larger charge


def test_segment_revenue_is_nested_in_its_own_profit_bridge(g):
    seg = g.compositions["sbk.comp.revenue_by_segment"]
    for rev, ebitda_view, bridge in (("softbank_corp.consumer_revenue", "sbk.comp.consumer_ebitda", "sbk.comp.consumer_profit"),
                                     ("softbank_corp.enterprise_revenue", "sbk.comp.enterprise_ebitda", "sbk.comp.enterprise_profit")):
        e = g.compositions[ebitda_view]
        assert rev in seg.members and rev in e.members and e.total in g.compositions[bridge].members
        assert str(_link(g, rev, e.total).edge_type) == "accounting"


def test_one_driving_view_of_operating_income(g):
    assert g.compositions["sbk.comp.op_by_segment"].drives and not g.compositions["sbk.comp.op_ebitda_bridge"].drives
    for v in ("softbank_corp.ebitda", "softbank_corp.depreciation"):
        into = [i.id for i in g.active_interactions() if i.target_id == v and str(i.edge_type) not in ("accounting", "identity")]
        assert into == [], (v, into)
        assert not [i.id for i in g.active_interactions() if i.source_id == v and i.target_id == OP]
    assert not set(_parts(g.compositions["sbk.comp.op_ebitda_bridge"])) & set(_parts(g.compositions["sbk.comp.op_by_segment"]))


def test_funding_costs_land_below_operating_income(g):
    reached = _reach(g, "softbank_corp.avg_borrowing_cost")
    assert {"softbank_corp.interest_expense", PRETAX, NI} <= reached and OP not in reached
    tr = g.interactions["m33"].transition
    assert tr is not None and tr.evidence.magnitude == "assumption" and "below operating income" in tr.mechanism


def test_a_hike_is_a_counter_path_inside_the_group(g):
    assert _link(g, BOJ, "softbank_corp.avg_borrowing_cost").transition.sign == "+"
    assert _link(g, "softbank_corp.avg_borrowing_cost", "softbank_corp.interest_expense").forward.effect.mean() < 0
    assert _link(g, BOJ, "softbank_corp.banking_nim").transition.sign == "+"
    assert OP in _reach(g, "softbank_corp.banking_nim")                   # the bank's gain reaches operating income


def test_minorities_take_part_of_the_listed_subsidiaries_profit(g):
    for seg, iid, nci in (("softbank_corp.media_ec_op", "sbk.id.nci_lycorp", "softbank_corp.nci_lycorp"),
                          ("softbank_corp.financial_op", "sbk.id.nci_paypay", "softbank_corp.nci_paypay")):
        x = g.identities[iid]
        assert x.form == "product" and seg in x.factors and x.coefficient == -1.0 and x.target == nci
        assert _link(g, seg, nci).forward.effect.mean() < 0                  # more segment income, a larger deduction
        assert nci in g.compositions["sbk.comp.minorities"].members
    assert "softbank_corp.noncontrolling_interests" in g.compositions["sbk.comp.net_income"].members


def test_dividend_ladder_is_calibrated_from_guidance(g):
    i = g.interactions["sbk-c-ni-dps"]
    assert i.quantified and i.transition.evidence.magnitude == "guidance" and NOTES[i.id].startswith("state:")
    st = SPEC_LINKS["sbk-c-ni-dps"]["state"]["asymmetry"]
    assert st["falls"]["mu"] == 0.0                                         # a ratchet: no cuts
    ni, dps = g.subentities[NI], g.subentities["softbank_corp.dividend_per_share"]
    z = math.log((_level(ni) + 100.0) / _level(ni)) / ni.scale              # +¥100bn of net income, in sd
    yen = st["rises"]["mu"] * z * dps.scale                                 # the implied DPS change
    assert 0.5 <= yen <= 1.0
    assert i.forward.kernel.delay.mean() >= 60                              # at the next dividend decision


def test_only_evidenced_links_carry_new_sizes(g):
    new_calibrated = {i.id for i in _sbk_links(g) if i.id.startswith("sbk-c-") and i.quantified
                      and str(i.edge_type) == "causal"}
    assert new_calibrated == {"sbk-c-ni-dps"}
    for iid in ("m33", "s47", "s48", "s49"):                              # the existing records keep their sizes, scoped
        tr = g.interactions[iid].transition
        assert tr is not None and tr.evidence.magnitude == "assumption" and tr.unresolved, iid


def test_debt_is_a_stock_fed_by_flows(g):
    sf = g.stock_flows["sbk.sf.debt"]
    assert sf.stock == "softbank_corp.interest_bearing_debt"
    for src, sign in (("softbank_corp.free_cash_flow", -1), ("softbank_corp.total_dividends", 1)):
        i = _link(g, src, sf.stock)
        assert str(i.edge_type) == "stock_flow" and sign * i.forward.effect.mean() > 0, src


def test_tagged_steps_are_converted_or_say_why_not(g):
    assert IDENTITIES <= set(g.identities) and STOCK_FLOWS <= set(g.stock_flows)
    for iid in IDENTITIES:                                               # every identity reconciles at the priors
        assert iid in g.identities
    rows = {r["identity_id"] if "identity_id" in r else r.get("id"): r for r in reconcile_identities(g, model_levels(g, "median"))}
    for iid in IDENTITIES:
        assert rows[iid]["status"] == "ok", (iid, rows[iid])
    tags = ("identity:", "stock-flow:", "matrix:", "state:")
    left = [k for k, n in NOTES.items() if n.startswith(tags) and k != "sbk-c-ni-dps"]
    assert left == [], left                                              # no unconverted tag remains
    kept = [i for i in _sbk_links(g) if not i.quantified and NOTES.get(i.id, "").startswith(KEPT)]
    assert len(kept) == 12


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _sbk_links(g):
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
def test_generalization_trace_a_yen_carry_unwind(g):
    """A yen carry-trade unwind: no SoftBank path starts at the carry or the yen. The structure carries it through
    USD/JPY (m18) to the dollar-priced AI build (GPUs: investment, then Enterprise depreciation, capacity and cloud and
    AI revenue, and capex -> free cash flow -> debt) and to handsets (Consumer cash costs and merchandise revenue); and
    through TOPIX (s62) to the share price. It stops at the share price, and it never reaches funding costs: this world
    has no link from the yen to Japanese inflation or the BoJ."""
    tr = trace(g, "dollar_yen.carry_positioning", SBK)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    assert routes[("m18", "sbk-c-usdjpy-aicapex", "s48")]["ends_at"] == OP           # the reduced form, calibrated
    assert routes[("m18", "sbk-c-usdjpy-aicapex", "sbk-c-aicapex-entdep", "sbk-a-entop-enterprise-depreciation")]["ends_at"] \
        == "softbank_corp.enterprise_op"
    assert ("m18", "sbk-c-usdjpy-conscosts", "sbk-a-consebitda-consumer-cash-costs") in routes
    assert routes[("m18", "sbk-c-usdjpy-aicapex", "sbk-c-aicapex-capex", "sbk-c-capex-fcf")]["ends_at"] \
        == "softbank_corp.free_cash_flow"                                  # an identity's target is an endpoint
    deep = trace(g, "dollar_yen.carry_positioning", SBK, through_totals=True)  # and on through it to the debt stock
    assert any(s["interaction_id"] == "sbk-c-fcf-debt" for r in deep["routes"] for s in r["steps"])
    assert tr["stops"] == ["softbank_corp.share_price"]
    assert "softbank_corp.avg_borrowing_cost" not in {s["target"] for r in tr["routes"] for s in r["steps"]}


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["sbk-a-op-consumer-op"]["dependency_type"] == "accounting_identity"
    assert rels["sbk-c-tariff-arpu"]["status"] == "represented_uncalibrated"
    assert rels["sbk-c-tariff-arpu"]["axelrod"]["transition"]["sign"] == "+"
    assert rels["sbk-c-arpu-mobile"]["dependency_type"] == "accounting_identity"
    assert rels["m33"]["axelrod"]["transition"]["evidence"]["magnitude"] == "assumption"


def test_new_objects_reach_the_api(client):
    ids = "softbank_corp.mobile_arpu,softbank_corp.consumer_op,softbank_corp.interest_expense,softbank_corp.dividend_per_share"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and "softbank_corp.consumer_mobile_revenue" in got
    view = v1.construction(client, SBK)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, SBK, BOJ)
    assert tr["reaches_endpoint"]
