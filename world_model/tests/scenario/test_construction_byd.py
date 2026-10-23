"""BYD's business construction in sally_demo (<client root>/worlds/sally_demo/construction/byd.yaml, Oct 22).

Holds the build to the structure its gap register (the client root's docs/construction/byd.md) asks for: a Chinese vehicle and battery maker with segment and place matrices, a disclosed USD/CNY sensitivity, and a joint venture with Toyota. The
compositions reconcile by accounting links, one view drives each total, the identities and stock-flows close, every named path
is connected with a transition on each step, and only the evidenced links carry sizes. The objects are checked in the internal
graph, the v4.1.4 export and the service API, in sally_demo and in its focused world (sally_focus_byd). Every material
claim resolves to a located citation, no input is left unreviewed, and the compositions reconcile at the model's medians and at
every local baseline; the repair data binds into the export. The citation, baseline and repair checks read the client's local
files (data/work/sally, gitignored) and skip where they are absent, as on CI. Ids appear here; no figure or quote does."""

from __future__ import annotations

import json
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
from axelrod_wm.context.earnings import attach_repair, load_repair
from axelrod_wm.model.construction import (
    bundle_levels,
    model_levels,
    reconcile,
    reconcile_identities,
    reconcile_matrices,
    reconciling_views,
    validate_construction,
)
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.clients import SALLY_WORK, skip_without_client
from tests.scenario import v1_reads as v1

skip_without_client('sally_demo', 'sally_focus_byd')

CO, PRE, CID = "byd", "by.", "N_BYD"
OP = "byd.operating_profit"
LOCAL = SALLY_WORK / "construction"     # the client's data: local only, absent on CI
# (file, period, the compositions the bundle cannot check: blocked for want of reported parts, never flagged; None = not listed)
BASELINES = [('baselines.json', 'H1 2026', []), ('baselines_h1_2025.json', 'H1 2025', ['by.comp.byde_segments', 'by.comp.byde_smart_terminal'])]

COMPOSITIONS = {'by.comp.rev_nature': ('byd.operating_revenue', True),
                'by.comp.rev_segment_ext': ('byd.operating_revenue', True),
                'by.comp.rev_location': ('byd.operating_revenue', True),
                'by.comp.rev_segment_total': ('byd.operating_revenue', True),
                'by.comp.crev_segment': ('byd.contract_revenue', True),
                'by.comp.crev_place': ('byd.contract_revenue', True),
                'by.comp.cost_nature': ('byd.operating_costs', True),
                'by.comp.ccost_segment': ('byd.contract_cost', True),
                'by.comp.ccost_place': ('byd.contract_cost', True),
                'by.comp.op_bridge': ('byd.operating_profit', True),
                'by.comp.pretax': ('byd.total_profit', True),
                'by.comp.net_bridge': ('byd.net_profit', True),
                'by.comp.finance': ('byd.finance_expenses', True),
                'by.comp.investment': ('byd.investment_income', True),
                'by.comp.interest_income': ('byd.interest_income', True),
                'by.comp.segment_profit': ('byd.total_profit', True),
                'by.comp.units_destination': ('byd.nev_sales_units', True),
                'by.comp.units_type': ('byd.nev_sales_units', True),
                'by.comp.units_passenger': ('byd.passenger_sales_units', True),
                'by.comp.units_commercial': ('byd.commercial_sales_units', True),
                'by.comp.prod_type': ('byd.nev_production_units', True),
                'by.comp.prod_passenger': ('byd.passenger_production_units', True),
                'by.comp.byde_segments': ('byd.byde_revenue', True),
                'by.comp.byde_smart_terminal': ('byd.byde_smart_terminal_revenue', True),
                'by.comp.da_segment': ('byd.depreciation_amortisation', True),
                'by.comp.capex_segment': ('byd.capex_accrual', True),
                'by.comp.rd_investment': ('byd.rd_investment', True)}
# one view drives each total; these reconcile against it without driving it
RECONCILING = {'by.comp.ccost_place': 'matrix by.mx.contract_cost',
               'by.comp.crev_place': 'matrix by.mx.contract_revenue',
               'by.comp.rev_location': 'drives: false',
               'by.comp.rev_segment_ext': 'drives: false',
               'by.comp.rev_segment_total': 'drives: false',
               'by.comp.segment_profit': 'drives: false',
               'by.comp.units_type': 'drives: false'}
IDENTITIES = {'by.id.gross_profit': ('difference', 'byd.gross_profit'),
              'by.id.gross_margin': ('ratio', 'byd.gross_margin'),
              'by.id.auto_overseas_gp': ('difference', 'byd.auto_overseas_gross_profit'),
              'by.id.auto_prc_gp': ('difference', 'byd.auto_prc_gross_profit'),
              'by.id.electronics_overseas_gp': ('difference', 'byd.electronics_overseas_gross_profit'),
              'by.id.electronics_prc_gp': ('difference', 'byd.electronics_prc_gross_profit'),
              'by.id.auto_gross_profit': ('difference', 'byd.auto_gross_profit'),
              'by.id.auto_overseas_margin': ('ratio', 'byd.auto_overseas_margin'),
              'by.id.auto_prc_margin': ('ratio', 'byd.auto_prc_margin'),
              'by.id.auto_gross_margin': ('ratio', 'byd.auto_gross_margin'),
              'by.id.auto_overseas_share': ('ratio', 'byd.auto_overseas_share'),
              'by.id.net_profit_parent': ('difference', 'byd.net_profit_parent'),
              'by.id.income_tax': ('product', 'byd.income_tax'),
              'by.id.interest_expense': ('product', 'byd.interest_expense'),
              'by.id.auto_overseas_revenue': ('product', 'byd.auto_overseas_revenue'),
              'by.id.auto_overseas_cost': ('product', 'byd.auto_overseas_cost'),
              'by.id.auto_prc_revenue': ('product', 'byd.auto_prc_revenue'),
              'by.id.auto_prc_cost': ('product', 'byd.auto_prc_cost'),
              'by.id.production_less_sales': ('difference', 'byd.production_less_sales_units'),
              'by.id.premium_units': ('product', 'byd.premium_brand_units'),
              'by.id.staff_cost_ratio': ('ratio', 'byd.staff_cost_ratio'),
              'by.id.total_equity': ('difference', 'byd.total_equity'),
              'by.id.parent_equity': ('difference', 'byd.parent_equity'),
              'by.id.eu_duty': ('product', 'byd.eu_duty_cost')}
STOCK_FLOWS = {'by.sf.cash': 'byd.cash_equivalents', 'by.sf.borrowings': 'byd.total_borrowings',
               'by.sf.auto_finance_jv': 'byd.auto_finance_jv_carrying'}
MATRICES = {'by.mx.contract_revenue': ('by.comp.crev_segment', 'by.comp.crev_place'),
            'by.mx.contract_cost': ('by.comp.ccost_segment', 'by.comp.ccost_place')}
PATHS = {'by.path.export_demand': 'byd.operating_profit',
         'by.path.domestic_demand': 'byd.operating_profit',
         'by.path.price_competition': 'byd.operating_profit',
         'by.path.battery_capacity': 'byd.operating_profit',
         'by.path.eu_duties': 'byd.operating_profit',
         'by.path.brazil_duties': 'byd.operating_profit',
         'by.path.localisation_capex': 'byd.operating_profit',
         'by.path.working_capital': 'byd.operating_profit',
         'by.path.cash_roll': 'byd.cash_equivalents',
         'by.path.fx': 'byd.operating_profit',
         'by.path.rates': 'byd.operating_profit',
         'by.path.inventory_impairment': 'byd.operating_profit',
         'by.path.input_costs': 'byd.operating_profit',
         'by.path.electronics': 'byd.operating_profit',
         'by.path.byde_scope': 'byd.electronics_total_revenue',
         'by.path.ai_infrastructure': 'byd.operating_profit',
         'by.path.auto_finance': 'byd.operating_profit',
         'by.path.labour': 'byd.operating_profit',
         'by.path.group_bridge': 'byd.net_profit_parent'}
CALIBRATED = {'by_fx_finance': 'documented'}


@pytest.fixture(scope="module", params=["sally_demo", "sally_focus_byd"])
def client(request):
    app = create_app(scenario=request.param, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def g(client):
    return client.app.state.axelrod.controller.engine.wm.graph


def parts(c) -> list[str]:
    return [*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])]


def link(g, src, tgt):
    hits = [i for i in g.active_interactions() if i.source_id == src and i.target_id == tgt]
    assert len(hits) == 1, (src, tgt, [i.id for i in hits])
    return hits[0]


def own_links(g):
    own = set(g.entities[CO].subentity_ids)
    return [i for i in g.active_interactions() if i.source_id in own or i.target_id in own]


def local(name: str) -> Path:
    p = LOCAL / CO / name
    if not p.exists():
        pytest.skip(f"the client's local {CO}/{name} is absent (data/ is gitignored; CI has none)")
    return p


# -- structure ---------------------------------------------------------------------------------------------------------
def test_no_construction_problems(g):
    assert construction_view(g, CO)["problems"] == []
    assert not [p for p in validate_construction(g) if CO in p or PRE in p]


def test_required_compositions_exist(g):
    mine = {k for k, c in g.compositions.items() if c.entity_id == CO}
    assert mine == set(COMPOSITIONS)
    for cid, (total, additive) in COMPOSITIONS.items():
        c = g.compositions[cid]
        assert c.total == total and c.additive is additive and c.basis and c.unit, cid


def test_one_view_drives_each_total(g):
    mine = {cid: why for cid, why in reconciling_views(g).items() if cid.startswith(PRE)}
    assert mine == RECONCILING
    driving: dict[str, list[str]] = {}
    for cid, (total, _) in COMPOSITIONS.items():
        if cid not in RECONCILING:
            driving.setdefault(total, []).append(cid)
    assert driving and all(len(v) == 1 for v in driving.values()), {t: v for t, v in driving.items() if len(v) > 1}


def test_composition_parts_have_fixed_weight_accounting_links(g):
    for cid in COMPOSITIONS:
        c = g.compositions[cid]
        units = {g.subentities[sid].unit for sid in [c.total, *parts(c)]}
        assert units == {c.unit}, (cid, units)                          # one unit within a view
        for sid in parts(c):
            i = link(g, sid, c.total)
            assert str(i.edge_type) == "accounting", (cid, sid)
            if cid in RECONCILING:                                       # reconciled against, never driving
                assert not i.quantified, (cid, sid)
                continue
            assert i.quantified and i.forward.effect.sd() <= 0.01, (cid, sid)   # a fixed weight, not a fitted one


def test_priors_reconcile_at_the_model_medians(g):
    rows = [r for r in reconcile(g, model_levels(g, "median"), tolerance=0.005) if r["entity_id"] == CO]
    assert {r["composition_id"] for r in rows} == set(COMPOSITIONS)
    assert all(r["status"] == "ok" for r in rows), [(r["composition_id"], r["relative_difference"]) for r in rows]


def test_matrices_reconcile_rows_against_columns(g):
    assert {k for k in g.matrices if k.startswith(PRE)} == set(MATRICES)
    rows = {r["matrix_id"]: r for r in reconcile_matrices(g, model_levels(g, "median"), tolerance=0.005)}
    for mid, (by_row, by_col) in MATRICES.items():
        mx = g.matrices[mid]
        assert (mx.rows, mx.columns) == (by_row, by_col) and mx.cell_list(), mid
        assert by_row in RECONCILING or by_col in RECONCILING, mid      # one of the two views is the reconciling one
        assert rows[mid]["status"] == "ok" and not rows[mid]["incomplete"], mid


def test_identities_hold_at_the_medians(g):
    assert {k for k, x in g.identities.items() if x.entity_id == CO} == set(IDENTITIES)
    for iid, (form, target) in IDENTITIES.items():
        x = g.identities[iid]
        assert x.form == form and x.target == target, iid
    rows = {r["identity_id"]: r for r in reconcile_identities(g, model_levels(g, "median"), tolerance=0.005)}
    assert all(rows[iid]["status"] == "ok" for iid in IDENTITIES), {k: rows[k]["relative_difference"] for k in IDENTITIES}


def test_stock_flows_roll_forward(g):
    assert {k for k, x in g.stock_flows.items() if x.entity_id == CO} == set(STOCK_FLOWS)
    for sfid, stock in STOCK_FLOWS.items():
        x = g.stock_flows[sfid]
        assert x.stock == stock and stock in g.subentities, sfid
        flows = [v for v, _ in x.terms()]
        assert flows, sfid
        for v in flows:                                               # each flow reaches its stock by a stock-flow link
            assert str(link(g, v, stock).edge_type) == "stock_flow", (sfid, v)


def test_the_auto_finance_joint_venture_values_are_labelled_partial(g):
    """BYD's share of the BYD Auto Finance joint venture is partial coverage (its carrying amount and the income booked on
    it), and the stock-flow says so through its values."""
    x = g.stock_flows["by.sf.auto_finance_jv"]
    for sid in ("byd.auto_finance_jv_carrying", "byd.auto_finance_jv_income"):
        assert "partial" in (g.subentities[sid].features or {}).get("basis", "").lower(), sid
    assert {v for v, _ in x.terms()} <= {"byd.auto_finance_jv_income"} and x.stock == "byd.auto_finance_jv_carrying"


def test_required_paths_exist(g):
    assert {k for k, p in g.paths.items() if p.entity_id == CO} == set(PATHS)
    for pid, endpoint in PATHS.items():
        p = g.paths[pid]
        assert p.steps and p.endpoint == endpoint and endpoint in g.subentities, pid


def test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign(g):
    for pid in PATHS:
        for s in g.paths[pid].steps:
            i = g.interactions[s.interaction_id]
            assert i.transition is not None and i.transition.mechanism, (pid, i.id)
            if str(i.edge_type) in ("identity", "stock_flow", "accounting"):    # a weight derived from the levels (a reconciling view has none)
                continue
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)


def test_only_evidenced_links_carry_sizes(g):
    sized = {i.id: i.transition.evidence.magnitude for i in own_links(g)
             if i.quantified and str(i.edge_type) == "causal" and i.transition is not None}
    assert sized == CALIBRATED
    for i in own_links(g):                                              # the rest carry a sign, never a size
        if str(i.edge_type) == "causal" and not i.quantified and i.transition is not None:
            assert i.transition.sign in ("+", "-"), i.id


# -- sources, inputs, reconciliation ---------------------------------------------------------------------------------------
def test_every_material_claim_resolves_to_a_located_citation(g):
    local("citations.json")
    sources = load_sources(LOCAL)
    cc = company_citations(g, CO, sources)
    assert cc["claims_without_citation"] == [], [c["interaction_id"] for c in cc["claims_without_citation"]]
    assert cc["unresolved"] == [] and cc["unknown_citation_keys"] == []
    mine = {k: [c for c in cs if c["company"] == CO] for k, cs in sources["citations"].items()}
    refs = [c for cs in mine.values() for c in cs]
    assert refs and all(c["location"] and c["passage"] and len(c["passage"]) <= 300 for c in refs)
    assert {c["source"] for c in refs} <= {s for s, x in sources["catalogue"].items() if x["company"] == CO}
    named = {s for i in own_links(g) if i.transition for s in i.transition.evidence.sources}
    assert named <= set(sources["catalogue"]), sorted(named - set(sources["catalogue"]))


def test_no_input_is_left_unreviewed(g):
    ins = inputs_by_status(g, CO)
    own = set(g.entities[CO].subentity_ids)                  # the inputs on links into its values
    ins["inputs"] = [n for n in ins["inputs"] if any(g.interactions[i].target_id in own for i in n["interaction_ids"])]
    assert ins["not_yet_reviewed"] == [] and ins["counts"]["not_yet_reviewed"] == 0
    assert sum(ins["counts"].values()) >= 20
    for n in ins["inputs"]:
        if n["status"] == "not_disclosed_in_reviewed_sources":      # "missing" is declared only after a search
            assert n["searched"] and any(s.startswith("corpus: ") for s in n["searched"]), n["input"]
        if n["status"].startswith("found"):
            assert n["found_in"], n["input"]


@pytest.mark.parametrize("name,period,blocked", BASELINES, ids=[b[1] for b in BASELINES])
def test_compositions_reconcile_at_each_local_baseline(g, name, period, blocked):
    """The reported parts add to the reported totals for one period: every composition the bundle can check is ok, the
    others are blocked for want of reported parts, none is flagged; the identities likewise."""
    levels = bundle_levels(json.loads(local(name).read_text()))
    rows = {r["composition_id"]: r for r in reconcile(g, levels) if r["entity_id"] == CO}
    assert set(rows) == set(COMPOSITIONS)
    assert not [c for c, r in rows.items() if r["status"] == "flag"], [(c, r["relative_difference"]) for c, r in rows.items() if r["status"] == "flag"]
    assert any(r["status"] == "ok" for r in rows.values()), period
    if blocked is not None:
        assert {c for c, r in rows.items() if r["status"] == "blocked"} == set(blocked), period
    ids = {r["identity_id"]: r for r in reconcile_identities(g, levels) if r["identity_id"] in IDENTITIES}
    assert not [k for k, r in ids.items() if r["status"] == "flag"], period


def test_the_repair_data_binds_into_the_export(client):
    """repair.json (the minimal generic format of context/earnings.py) binds to the live export: its business records, its
    observations against the model's values, and a reconciliation for every composition."""
    rep = load_repair(LOCAL, {CID})
    if not rep:
        pytest.skip(f"the client's local {CO}/repair.json is absent (data/ is gitignored; CI has none)")
    (repair,) = rep
    ctx = client.get("/api/context/v4").json()
    n = attach_repair(ctx, repair)
    sup = ctx["domain_pack"]["domain_specific_support_objects"]
    assert {r["record_id"] for r in sup["business_records"]} == {r["record_id"] for r in repair["business_records"]}
    assert all(r["company_id"] == CID for r in sup["business_records"])
    assert n["observations"] == len(repair.get("observations", [])) == len(sup["earnings_observations"])
    assert len(sup["baseline_reconciliations"]) == len(COMPOSITIONS) == n["reconciliations"]
    assert ctx["manifest"]["repair"]["repair_version"] == repair["repair_version"]
    if repair.get("observations"):
        assert 0 < n["values_with_reported_observation"] <= n["values"]
        assert {p["metric_id"] for p in sup["observation_estimate_pairs"]} <= {v["metric_id"] for v in ctx["evidence"]["values"]}


def test_the_toyota_joint_venture_is_a_business_record_not_a_link(client, g):
    """The BYD-Toyota EV joint venture is a relationship record: it comes through the export as a business record, and no
    link or value stands for it (the records carry no size)."""
    rep = load_repair(LOCAL, {CID})
    if not rep:
        pytest.skip("the client's local byd/repair.json is absent (data/ is gitignored; CI has none)")
    (repair,) = rep
    (jv,) = [r for r in repair["business_records"] if r["record_id"] == "REC_BY_TOYOTA_JV"]
    assert jv["record_kind"] == "relationship" and "toyota" in json.dumps(jv).lower()
    ctx = client.get("/api/context/v4").json()
    attach_repair(ctx, repair)
    got = {r["record_id"]: r for r in ctx["domain_pack"]["domain_specific_support_objects"]["business_records"]}
    assert got["REC_BY_TOYOTA_JV"]["record_kind"] == "relationship" and got["REC_BY_TOYOTA_JV"]["company_id"] == CID
    assert not [i for i in g.interactions if "toyota_jv" in i] and not [s for s in g.subentities if "toyota_jv" in s]


def test_the_combined_focus_shows_the_four_companies_and_their_connections():
    """sally_focus_autos_batteries: Toyota, Hyundai, BYD and CATL in one world. The battery rivalry is a link between them,
    and every company's repair data reaches one export without replacing another's (the BYD-Toyota record included)."""
    from tests.clients import client_present
    if not client_present("sally_focus_autos_batteries"):
        pytest.skip("the combined focus scenario is absent (client root scenarios/; data/ is gitignored)")
    four = {"toyota": "N_TOYOTA_MOTOR", "hyundai": "N_HYUNDAI_MOTOR", "byd": CID, "catl": "N_CATL"}
    app = create_app(scenario="sally_focus_autos_batteries", storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        graph = c.app.state.axelrod.controller.engine.wm.graph
        assert set(four) <= set(graph.entities)
        rivalry = link(graph, "ev_battery_market.byd_global_share", "catl.global_usage_share")
        assert rivalry.transition.sign == "-" and not rivalry.quantified
        ctx = c.get("/api/context/v4").json()
        if not (LOCAL / "toyota" / "repair.json").exists():
            pytest.skip("the client's local repair data is absent (data/ is gitignored; CI has none)")
        reps = load_repair(LOCAL, set(four.values()))
        assert {r["entity"] for r in reps} == set(four)
        for rep in reps:
            attach_repair(ctx, rep)
    sup = ctx["domain_pack"]["domain_specific_support_objects"]
    by_company = {}
    for r in sup["business_records"]:
        by_company.setdefault(r["company_id"], set()).add(r["record_id"])
    assert set(by_company) == set(four.values())
    assert {r["record_id"] for rep in reps for r in rep["business_records"]} == set().union(*by_company.values())
    assert "REC_BY_TOYOTA_JV" in by_company[CID]
    assert [m["company_id"] for m in ctx["manifest"]["repairs"]] == [r["company_id"] for r in reps]


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    sup = pack["domain_specific_support_objects"]
    bridge = {b["composition_id"] for b in sup["financial_bridge"]}
    assert set(COMPOSITIONS) <= bridge
    assert set(IDENTITIES) <= {x["identity_id"] for x in sup["financial_identities"]}
    paths = {p["axelrod"]["path_id"] for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"}
    assert set(PATHS) <= paths
    rels = {r["axelrod"]["interaction_id"]: r for r in pack["company_edge_relationships"]}
    for iid, magnitude in CALIBRATED.items():
        assert rels[iid]["axelrod"]["transition"]["evidence"]["magnitude"] == magnitude, iid
    assert any(r["dependency_type"] == "accounting_identity" for r in rels.values() if r["company_id"] == CID)


def test_new_objects_reach_the_api(client, g):
    pid = next(iter(PATHS))
    start = g.interactions[g.paths[pid].steps[0].interaction_id].source_id
    ids = f"{OP},{next(iter(STOCK_FLOWS.values()))}"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got
    view = v1.construction(client, CO)
    assert {c["id"] for c in view["compositions"]} == set(COMPOSITIONS) and not view["problems"]
    assert trace(g, start, CO)["routes"]
    tr = v1.trace(client, CO, start)
    assert tr["routes"]
