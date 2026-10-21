"""Komatsu's business construction (Oct 18): the compositions, operating and financial paths, and their transitions in
<client root>/worlds/sally_demo/construction/komatsu.yaml, checked in the loaded model, in the v4.1.4 export, and through the
service API (docs/construction/komatsu.md has the gap register these tests close). An industrial after Toyota, with
its own economics: construction, mining and utility equipment sold as new machines and a large aftermarket in eight
regions, a captive finance arm, industrial machinery, disclosed yen sensitivities, mining capex and fleet hours,
construction activity and dealer stock, price realization, steel and tariffs. Sally's world loads once for the module;
no client data is read."""

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
    reconcile_stock_flows,
    reconciling_views,
    validate_construction,
)
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.clients import client_path, skip_without_client
from tests.scenario import v1_reads as v1

skip_without_client('sally_demo')

KM = "komatsu"
OP, SALES, CMU, NI = "komatsu.operating_profit", "komatsu.net_sales", "komatsu.cmu_sales", "komatsu.owners_net_income"
SEGP = "komatsu.cmu_segment_result"
USDJPY = "dollar_yen.usd_jpy"
REGIONS = ["japan", "north_america", "latin_america", "europe_cis", "china", "asia", "oceania", "middle_east_africa"]

COMPOSITIONS = {   # id -> (total, additive)
    "km.comp.segment_sales": (SALES, True),
    "km.comp.segment_profit": (OP, True),
    "km.comp.cmu_by_demand": (CMU, True),
    "km.comp.construction_by_product": ("komatsu.construction_sales", True),
    "km.comp.mining_by_product": ("komatsu.mining_sales", True),
    "km.comp.cmu_by_region": (CMU, True),
    "km.comp.construction_by_region": ("komatsu.construction_sales", True),
    "km.comp.mining_by_region": ("komatsu.mining_sales", True),
    **{f"km.comp.{r}_by_demand": (f"komatsu.{r}_cmu_sales", True) for r in REGIONS},
    "km.comp.retail_finance": ("komatsu.rf_segment_result", True),     # a nested bridge (rf revenue is in sales too)
    "km.comp.rf_costs": ("komatsu.rf_costs", True),
    "km.comp.cmu_profit_walk": ("komatsu.cmu_result_delta", True),
    "km.comp.pretax": ("komatsu.pretax_income", True),
    "km.comp.net_income": (NI, True),
}
# one view drives each total; the others reconcile to it without driving it
RECONCILING = {"km.comp.cmu_by_region": "matrix km.mx.cmu_sales", "km.comp.construction_by_product": "drives: false",
               "km.comp.mining_by_region": "drives: false", "km.comp.cmu_profit_walk": "drives: false"}
DRIVING = {CMU: "km.comp.cmu_by_demand", "komatsu.construction_sales": "km.comp.construction_by_region",
           "komatsu.mining_sales": "km.comp.mining_by_product"}
IDENTITIES = {"km.id.price_effect": ("product", "komatsu.walk_price_factor"),
              "km.id.cmu_result_delta": ("difference", "komatsu.cmu_result_delta"),
              "km.id.rf_revenue": ("product", "komatsu.rf_revenue"),
              "km.id.rf_interest": ("product", "komatsu.rf_interest_expense")}
STOCK_FLOWS = {"km.sf.dealer_inventory": "komatsu.na_dealer_inventory", "km.sf.rf_assets": "komatsu.rf_assets"}
# views where the business leaves something out (corporate items, other walk factors, non-operating items, affiliates)
WITH_REMAINDER = {"km.comp.segment_profit", "km.comp.cmu_profit_walk", "km.comp.pretax", "km.comp.net_income",
                  "km.comp.rf_costs"}
PATHS = {  # an equipment maker's economics -> the named path(s) that carry them
    "commodity prices and mining capex": ["km.path.mining_capex", "km.path.coal_contractors"],
    "parts and service (mix)": ["km.path.aftermarket"],
    "construction activity and dealer inventories": ["km.path.us_construction", "km.path.us_rates"],
    "China": ["km.path.china_construction"],
    "price realization and steel cost": ["km.path.price_cost"],
    "tariffs": ["km.path.tariffs"],
    "yen sensitivity": ["km.path.yen"],
    "retail finance": ["km.path.retail_finance_rates", "km.path.finance_book"],
    "industrial machinery": ["km.path.industrial_machinery"],
    "fixed costs": ["km.path.fixed_costs"],
    "group bridge": ["km.path.group_bridge"],
}
NEW_CALIBRATED = {  # the only new sizes, each from a disclosure or a broker's stated sensitivity
    "km-c-usdjpy-sales": "documented", "km-c-eurjpy-op": "documented", "km-c-eurjpy-sales": "documented",
    "km-c-audjpy-op": "documented", "km-c-audjpy-sales": "documented", "km-c-tariff-profit": "documented",
    "km-c-tax": "documented", "km-c-price-profit": "documented", "km-c-mineq-profit": "broker",
    "km-c-nacon-profit": "broker",
}
# the round-one conversion tags (identity:/stock-flow:/state:/matrix:) are gone: each step is converted or says why not
NOTES = {i["id"]: i.get("note") or "" for i in
         yaml.safe_load(open(client_path("worlds/sally_demo/construction/komatsu.yaml")))["interactions"]}
TAGS = ("identity:", "stock-flow:", "state:", "matrix:")
SOURCES = {"km.wb", "km.r1", "km.r2", "km.r3", "km.r4", "km.x1", "km.x2", "km.peer", "km.pub"}


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


def _km_links(g):
    own = set(g.entities[KM].subentity_ids)
    return [i for i in g.active_interactions() if i.source_id in own or i.target_id in own]


def _causal_into(g, target):
    return [i for i in g.active_interactions() if i.target_id == target and str(i.edge_type) != "accounting"]


# -- structure ---------------------------------------------------------------------------------------------------------
def test_no_construction_problems_for_komatsu(g):
    assert construction_view(g, KM)["problems"] == []
    assert not [p for p in validate_construction(g) if "komatsu" in p or "km." in p or "km-" in p]


def test_required_compositions_exist(g):
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.entity_id == KM and c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_one_view_drives_each_total(g):
    mine = {cid: why for cid, why in reconciling_views(g).items() if cid.startswith("km.")}
    assert mine == RECONCILING
    for total, cid in DRIVING.items():
        driving = [k for k, c in g.compositions.items() if c.total == total and k not in RECONCILING]
        assert driving == [cid], (total, driving)


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid in COMPOSITIONS:
        c = g.compositions[cid]
        if cid in WITH_REMAINDER:
            assert c.residual or c.eliminations, cid
        units = {g.subentities[sid].unit for sid in [c.total, *_parts(c)]}
        assert units == {c.unit}, (cid, units)                          # one unit within a view
        for sid in _parts(c):
            i = _link(g, sid, c.total)
            assert str(i.edge_type) == "accounting", (cid, sid)
            if cid in RECONCILING:                                       # reconciled against, never driving
                assert not i.quantified, (cid, sid)
                continue
            assert i.quantified and i.forward.effect.sd() <= 0.01, (cid, sid)   # a fixed weight, not a fitted one
            w = i.forward.effect.mean()                                  # the part's native sd over the total's
            sign = -1 if i.transition.sign == "-" else 1                 # a deduction held positive subtracts
            assert w * sign > 0, (cid, sid)
            assert abs(w) == pytest.approx(_native_sd(g.subentities[sid]) / _native_sd(g.subentities[c.total]),
                                           abs=0.01), (cid, sid)


def test_priors_reconcile_within_half_a_percent(g):
    rows = {r["composition_id"]: r for r in reconcile(g, model_levels(g, "median"), tolerance=0.005)}
    for cid in COMPOSITIONS:
        assert rows[cid]["status"] == "ok", (cid, rows[cid]["relative_difference"])
    assert rows["km.comp.rf_costs"]["subtracted"] == ["komatsu.rf_interest_expense"]


def test_region_by_demand_type_is_one_matrix(g):
    mx = g.matrices["km.mx.cmu_sales"]
    assert (mx.rows, mx.columns) == ("km.comp.cmu_by_demand", "km.comp.cmu_by_region") and len(mx.cell_list()) == 16
    by_region, by_demand = g.compositions["km.comp.cmu_by_region"], g.compositions["km.comp.cmu_by_demand"]
    assert len(by_region.members) == 8 and not set(_parts(by_region)) & set(_parts(by_demand))
    for r in REGIONS:                                               # each cell adds to its row part and its column part
        assert g.compositions[f"km.comp.{r}_by_demand"].members == \
            [f"komatsu.{r}_construction_sales", f"komatsu.{r}_mining_sales"]
    (row,) = [r for r in reconcile_matrices(g, model_levels(g, "median"), tolerance=0.005) if r["matrix_id"] == "km.mx.cmu_sales"]
    assert row["status"] == "ok" and not row["incomplete"] and len(row["lines"]) == 10


def test_retail_finance_is_a_nested_bridge_with_its_identities(g):
    rf = g.compositions["km.comp.retail_finance"]
    assert rf.additive and "komatsu.rf_revenue" in rf.members
    assert "komatsu.rf_revenue" in g.compositions["km.comp.segment_sales"].members      # the same part, two totals
    assert g.subentities["komatsu.rf_costs"].anchor < 0
    for iid, (form, target) in IDENTITIES.items():
        x = g.identities[iid]
        assert x.entity_id == KM and x.form == form and x.target == target, iid
    rows = {r["identity_id"]: r for r in reconcile_identities(g, model_levels(g, "median"), tolerance=0.005)}
    assert all(rows[iid]["status"] == "ok" for iid in IDENTITIES), {k: rows[k]["relative_difference"] for k in IDENTITIES}
    for src, tgt, iid in (("komatsu.rf_assets", "komatsu.rf_revenue", "km.id.rf_revenue"),
                          ("komatsu.rf_contract_rate", "komatsu.rf_revenue", "km.id.rf_revenue"),
                          ("komatsu.rf_debt", "komatsu.rf_interest_expense", "km.id.rf_interest"),
                          ("komatsu.rf_funding_cost", "komatsu.rf_interest_expense", "km.id.rf_interest")):
        i = _link(g, src, tgt)
        assert str(i.edge_type) == "identity" and i.identity == iid, (src, tgt)


def test_stock_flows_roll_forward(g):
    for sfid, stock in STOCK_FLOWS.items():
        x = g.stock_flows[sfid]
        assert x.entity_id == KM and x.stock == stock and x.period_days == 365, sfid
        for v, _ in x.terms():                                       # each flow reaches its stock by a stock-flow link
            assert str(_link(g, v, stock).edge_type) == "stock_flow", (sfid, v)
    # a roll-forward needs two dated stock levels; on a synthetic year it closes exactly
    series = {"komatsu.na_dealer_inventory": [("2026-03-31", 300.0), ("2027-03-31", 320.0)],
              "komatsu.north_america_construction_sales": [("2027-03-31", 690.0)],
              "komatsu.na_dealer_retail_sales": [("2027-03-31", 670.0)]}
    (row,) = [r for r in reconcile_stock_flows(g, series) if r["stock_flow_id"] == "km.sf.dealer_inventory"]
    assert row["status"] == "ok" and row["implied_closing"] == pytest.approx(320.0)


def test_required_paths_exist(g):
    for need, pids in PATHS.items():
        for pid in pids:
            p = g.paths[pid]
            assert p.entity_id == KM and p.steps and p.endpoint in g.subentities, (need, pid)


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid, p in g.paths.items():
        if p.entity_id != KM:
            continue
        for s in p.steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if str(i.edge_type) in ("identity", "stock_flow"):          # its weight is derived from the levels
                assert i.quantified, (pid, i.id)
                continue
            assert i.transition.next_state, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
                assert i.transition.evidence.magnitude == "unknown", (pid, i.id)   # no size is claimed


def test_shared_driver_responses_are_parallel_branches(g):
    def branches(pid):
        return {s.branch: g.interactions[s.interaction_id] for s in g.paths[pid].steps if s.branch}

    b = branches("km.path.mining_capex")
    assert b["capex"].source_id == b["utilization"].source_id == "copper.price"
    assert b["parts"].source_id == b["service"].source_id == "komatsu.installed_fleet_hours"
    b = branches("km.path.price_cost")
    assert b["absorb"].source_id == b["reprice"].source_id == "komatsu.material_cost_index"
    assert b["absorb"].transition.sign == "-" and b["reprice"].transition.sign == "+"
    b = branches("km.path.tariffs")
    assert b["absorb"].source_id == b["reprice"].source_id == "komatsu.us_tariff_cost"
    b = branches("km.path.us_rates")
    assert b["residential"].source_id == b["nonresidential"].source_id == "us_treasuries.yield_10y"
    b = branches("km.path.yen")
    assert {i.source_id for i in b.values()} == {USDJPY}
    assert {k for k, i in b.items() if i.quantified} == {"disclosed_total", "disclosed_sales"}   # the parts carry no size


def test_reduced_forms_are_never_steps_of_their_structural_paths(g):
    steps = {pid: {s.interaction_id for s in p.steps} for pid, p in g.paths.items() if p.entity_id == KM}
    assert not {"m31", "m32"} & (steps["km.path.mining_capex"] | steps["km.path.coal_contractors"])
    assert not {"s45", "s46"} & steps["km.path.china_construction"]
    for iid, mu in (("m31", 0.3), ("m32", 0.4), ("s45", 0.4), ("s46", 0.3)):     # Sally's records keep their sizes
        i = g.interactions[iid]
        assert i.forward.effect.mean() == pytest.approx(mu) and i.transition.evidence.magnitude == "assumption", iid
        assert i.transition.unresolved and i.transition.mechanism.startswith("Reduced form"), iid


# -- an equipment maker's economics -----------------------------------------------------------------------------------------
def test_values_name_their_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == KM and s.id != "komatsu.share_price"]
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not (s.features.get("view") and s.features.get("basis"))]


def test_the_yen_sensitivity_is_the_disclosed_one(g):
    fx = g.subentities[USDJPY]
    z_fx = math.log((_level(fx) + 1) / _level(fx)) / fx.scale              # one yen weaker, in sd

    def per_yen(iid, target):                                              # ¥bn of the target per ¥1 weaker
        sub = g.subentities[target]
        return _level(sub) * (math.exp(g.interactions[iid].forward.effect.mean() * z_fx * sub.scale) - 1)

    for iid in ("m30", "km-c-usdjpy-sales"):
        i = g.interactions[iid]
        assert i.quantified and i.transition.evidence.magnitude == "documented" and i.forward.effect.sd() > 0, iid
    assert 0 < per_yen("m30", OP) < per_yen("km-c-usdjpy-sales", SALES)    # profit moves less than sales, same sign
    assert g.interactions["m30"].forward.effect.mean() != pytest.approx(0.3)   # resized from the disclosure
    eur = g.interactions["km-c-eurjpy-op"]
    assert eur.source_id == "jpy_eur.rate" and eur.forward.effect.mean() < 0  # JPY/EUR up = a stronger yen


def test_only_evidenced_links_carry_new_sizes(g):
    new = {i.id: i.transition.evidence.magnitude for i in g.active_interactions()
           if i.id.startswith("km-c-") and i.quantified and str(i.edge_type) not in ("identity", "stock_flow")}
    assert new == NEW_CALIBRATED


def test_mining_is_driven_through_products_and_construction_through_regions(g):
    for r in REGIONS:                                               # never both views of CM&U sales from one shock
        assert not _causal_into(g, f"komatsu.{r}_mining_sales"), r
    for p in ("equipment", "parts", "service"):
        assert not _causal_into(g, f"komatsu.construction_{p}_sales"), p
    assert {i.source_id for i in _causal_into(g, "komatsu.mining_equipment_sales")} == {"komatsu.mining_demand"}
    assert {i.source_id for i in _causal_into(g, "komatsu.mining_parts_sales")} == {"komatsu.installed_fleet_hours"}
    # two clocks: capex buys machines after quarters, hours lift the aftermarket sooner
    assert "quarters" in _link(g, "copper.price", "global_mining.capex").transition.timing.onset
    assert "quarter" in _link(g, "komatsu.installed_fleet_hours", "komatsu.mining_parts_sales").transition.timing.onset
    # mix: mining equipment drops through far more than US construction (the broker's two sensitivities)
    assert _link(g, "komatsu.mining_equipment_sales", SEGP).forward.effect.mean() > \
        _link(g, "komatsu.north_america_construction_sales", SEGP).forward.effect.mean() > 0


def test_dealer_destocking_is_a_stock_with_a_threshold(g):
    retail = _link(g, "us_construction.nonresidential_spending", "komatsu.na_dealer_retail_sales")
    restock = _link(g, "komatsu.na_dealer_retail_sales", "komatsu.north_america_construction_sales")
    cut = _link(g, "komatsu.na_dealer_inventory", "komatsu.north_america_construction_sales")
    assert retail.transition.sign == restock.transition.sign == "+" and cut.transition.sign == "-"
    assert str(_link(g, "komatsu.na_dealer_retail_sales", "komatsu.na_dealer_inventory").edge_type) == "stock_flow"
    th = cut.state.threshold                                         # destocking bites only above normal stock
    assert th.value == "komatsu.na_dealer_inventory" and th.above == pytest.approx(300.0)
    assert not cut.quantified                                        # the side sizes are not observed


def test_price_cost_and_tariffs_keep_gross_effects_apart(g):
    absorb = _link(g, "komatsu.us_tariff_cost", SEGP)
    assert absorb.quantified and absorb.forward.effect.mean() < 0      # the gross cost, a yen for a yen
    assert not _link(g, "komatsu.us_tariff_cost", "komatsu.price_realization").quantified
    assert _link(g, "komatsu.price_realization", "komatsu.na_dealer_retail_sales").transition.sign == "-"
    x = g.identities["km.id.price_effect"]                           # the walk's price factor, as a product
    assert x.factors == ["komatsu.price_realization", "komatsu.cmu_sales"] and x.coefficient == pytest.approx(0.01)
    price = _link(g, "komatsu.price_realization", SEGP)               # and its drop-through, from the disclosure
    assert price.quantified and price.transition.evidence.magnitude == "documented"


def test_finance_debt_is_not_industrial(g):
    i = _link(g, "komatsu.rf_assets", "komatsu.rf_debt")
    assert "not industrial stress" in i.transition.mechanism
    assert _link(g, "komatsu.rf_interest_expense", "komatsu.rf_costs").transition.sign == "-"


def test_round_one_conversion_tags_are_gone(g):
    assert not [iid for iid, n in NOTES.items() if n.startswith(TAGS)]
    for iid in ("km-c-material-price", "km-c-price-nacon", "km-c-funding-yield"):   # no form fits: each says why
        assert not g.interactions[iid].quantified and NOTES[iid], iid


def test_missing_inputs_say_whether_the_material_was_searched(g):
    seen = 0
    for i in _km_links(g):
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
def test_generalization_trace_an_oil_shock(g):
    """An oil-price shock (a Middle East disruption): no Komatsu path starts there. The structure carries it to
    operating profit through the reduced form (m31 -> m32) and structurally through mining demand to new equipment
    (whose drop-through is calibrated); through fuel and logistics cost (absorbed or repriced); through the BoJ and the
    yen (m02 -> m08 -> m16 -> m30, calibrated end to end); through US rates to the finance arm's funding cost and to
    North American construction; and to Middle East construction through Gulf budgets. It stops at the regional sales
    totals (regional profit is not reported) and, at the trace depth, inside the finance book and dealer chains."""
    tr = trace(g, "oil.brent", KM)
    assert tr["reaches_endpoint"]
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in tr["routes"]}
    assert routes[("m31", "m32")]["ends_at"] == OP and not routes[("m31", "m32")]["uncalibrated_steps"]
    assert routes[("m31", "km-c-miningdemand-equipment", "km-c-mineq-profit", "km-a-op-cmu")]["uncalibrated_steps"] == \
        ["km-c-miningdemand-equipment"]
    assert routes[("km-c-oil-material", "km-c-material-profit", "km-a-op-cmu")]["ends_at"] == OP
    assert not routes[("m02", "m08", "m16", "m30")]["uncalibrated_steps"]
    assert routes[("km-c-oil-meafcon", "km-a-middle_east_africa-construction")]["ends_at"] == \
        "komatsu.middle_east_africa_cmu_sales"
    assert ("m01", "m05", "m06", "m11", "km-c-ust2-funding", "km-c-funding-rfcosts") in routes
    ends = {r["ends_at"] for r in tr["routes"] if r["reaches_endpoint"]}
    assert {OP, SALES, "komatsu.rf_segment_result", "komatsu.north_america_cmu_sales"} <= ends
    short_stops = {r["ends_at"] for r in tr["routes"] if not r["reaches_endpoint"] and len(r["steps"]) < 8}
    assert short_stops == set()


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert set(COMPOSITIONS) <= set(bridge)
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert {pid for pids in PATHS.values() for pid in pids} <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    assert rels["km-a-op-cmu"]["dependency_type"] == "accounting_identity"
    assert rels["km-c-retail-nacon"]["status"] == "represented_uncalibrated"
    assert rels["km-c-retail-nacon"]["axelrod"]["transition"]["sign"] == "+"
    assert rels["m30"]["axelrod"]["transition"]["evidence"]["magnitude"] == "documented"


def test_new_objects_reach_the_api(client):
    ids = "komatsu.cmu_segment_result,komatsu.mining_equipment_sales,komatsu.na_dealer_inventory,komatsu.net_sales"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got and "komatsu.price_realization" in got
    view = v1.construction(client, KM)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    tr = v1.trace(client, KM, "copper.price")
    assert tr["reaches_endpoint"]
