"""CATL's business construction in sally_demo (<client root>/worlds/sally_demo/construction/catl.yaml, Oct 22).

Holds the build to the structure its gap register (the client root's docs/construction/catl.md) asks for: a battery maker with customers and regions, lithium and FX exposure, and policy and rivalry links to automakers. The
compositions reconcile by accounting links, one view drives each total, the identities and stock-flows close, every named path
is connected with a transition on each step, and only the evidenced links carry sizes. The objects are checked in the internal
graph, the v4.1.4 export and the service API, in sally_demo and in its focused world (sally_focus_catl). Every material
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

skip_without_client('sally_demo', 'sally_focus_catl')

CO, PRE, CID = "catl", "ct.", "N_CATL"
OP = "catl.operating_profit"
LOCAL = SALLY_WORK / "construction"     # the client's data: local only, absent on CI
# (file, period, the compositions the bundle cannot check: blocked for want of reported parts, never flagged; None = not listed)
# the Oct 22 supplement adds the ct.comp.asbe_* views (PRC ASBE, unaudited): the H1 2026 and FY2025 bundles do not carry them, their own do
ASBE = ['ct.comp.asbe_adjusted', 'ct.comp.asbe_assets', 'ct.comp.asbe_equity', 'ct.comp.asbe_finance_expenses', 'ct.comp.asbe_financing_cash', 'ct.comp.asbe_investing_cash', 'ct.comp.asbe_investment_income', 'ct.comp.asbe_liabilities', 'ct.comp.asbe_net_profit', 'ct.comp.asbe_operating_cash', 'ct.comp.asbe_operating_profit', 'ct.comp.asbe_ownership', 'ct.comp.asbe_pretax_profit', 'ct.comp.asbe_q3_adjusted']
BASELINES = [('baselines.json', 'H1 2026', ['ct.comp.cost_nature', 'ct.comp.rev_customers', 'ct.comp.sales_volume', 'ct.comp.usage_geography', *ASBE]),
             ('baselines_fy2025.json', 'FY2025', None),
             ('baselines_q3_2026_asbe.json', 'Q3 2026 ASBE', None),
             ('baselines_q3_2025_asbe.json', 'Q3 2025 ASBE', None)]

COMPOSITIONS = {'ct.comp.rev_primary': ('catl.primary_operations_revenue', True),
                'ct.comp.rev_operations': ('catl.net_revenue', True),
                'ct.comp.rev_region': ('catl.net_revenue', True),
                'ct.comp.cost_primary': ('catl.primary_operations_cost', True),
                'ct.comp.cost_nature': ('catl.primary_operations_cost', True),
                'ct.comp.cost_operations': ('catl.cost_of_operations', True),
                'ct.comp.cost_region': ('catl.cost_of_operations', True),
                'ct.comp.gp_product': ('catl.gross_profit', True),
                'ct.comp.gp_region': ('catl.gross_profit', True),
                'ct.comp.operating_profit': ('catl.operating_profit', True),
                'ct.comp.financial_expenses': ('catl.financial_expenses', True),
                'ct.comp.investment_income': ('catl.investment_income', True),
                'ct.comp.pretax_profit': ('catl.profit_before_tax', True),
                'ct.comp.net_profit': ('catl.net_profit', True),
                'ct.comp.ownership': ('catl.net_profit', True),
                'ct.comp.adjusted': ('catl.net_profit_attributable', True),
                'ct.comp.assets': ('catl.total_assets', True),
                'ct.comp.liabilities': ('catl.total_liabilities', True),
                'ct.comp.equity': ('catl.total_equity', True),
                'ct.comp.investing_cash': ('catl.net_investing_outflow', True),
                'ct.comp.financing_cash': ('catl.net_financing_inflow', True),
                'ct.comp.sales_volume': ('catl.battery_sales_volume', True),
                'ct.comp.usage_geography': ('ev_battery_market.global_usage', True),
                'ct.comp.operating_cash': ('catl.operating_cash_flow', True),
                'ct.comp.financial_addback': ('catl.financial_expenses_addback', True),
                'ct.comp.provisions': ('catl.provisions', True),
                'ct.comp.rd_nature': ('catl.rd_expenses', True),
                'ct.comp.admin_nature': ('catl.admin_expenses', True),
                'ct.comp.selling_nature': ('catl.selling_expenses', True),
                'ct.comp.rev_customers': ('catl.net_revenue', True),
                'ct.comp.asbe_operating_profit': ('catl.asbe_9m_operating_profit', True),
                'ct.comp.asbe_finance_expenses': ('catl.asbe_9m_finance_expenses', True),
                'ct.comp.asbe_investment_income': ('catl.asbe_9m_investment_income', True),
                'ct.comp.asbe_pretax_profit': ('catl.asbe_9m_profit_before_tax', True),
                'ct.comp.asbe_net_profit': ('catl.asbe_9m_net_profit', True),
                'ct.comp.asbe_ownership': ('catl.asbe_9m_net_profit', True),
                'ct.comp.asbe_adjusted': ('catl.asbe_9m_net_profit_attributable', True),
                'ct.comp.asbe_q3_adjusted': ('catl.asbe_q3_net_profit_attributable', True),
                'ct.comp.asbe_assets': ('catl.asbe_total_assets', True),
                'ct.comp.asbe_liabilities': ('catl.asbe_total_liabilities', True),
                'ct.comp.asbe_equity': ('catl.asbe_total_equity', True),
                'ct.comp.asbe_operating_cash': ('catl.asbe_9m_operating_cash_flow', True),
                'ct.comp.asbe_investing_cash': ('catl.asbe_9m_net_investing_outflow', True),
                'ct.comp.asbe_financing_cash': ('catl.asbe_9m_net_financing_inflow', True)}
# one view drives each total; these reconcile against it without driving it
RECONCILING = {'ct.comp.adjusted': 'drives: false',
               'ct.comp.asbe_adjusted': 'drives: false',
               'ct.comp.asbe_equity': 'drives: false',
               'ct.comp.asbe_ownership': 'drives: false',
               'ct.comp.asbe_q3_adjusted': 'drives: false',
               'ct.comp.cost_primary': 'drives: false',
               'ct.comp.cost_region': 'drives: false',
               'ct.comp.equity': 'drives: false',
               'ct.comp.gp_product': 'drives: false',
               'ct.comp.gp_region': 'drives: false',
               'ct.comp.ownership': 'drives: false',
               'ct.comp.rev_customers': 'drives: false',
               'ct.comp.rev_region': 'drives: false',
               'ct.comp.usage_geography': 'drives: false'}
IDENTITIES = {'ct.id.gross_profit': ('difference', 'catl.gross_profit'),
              'ct.id.gp_ev': ('difference', 'catl.ev_battery_gross_profit'),
              'ct.id.gp_ess': ('difference', 'catl.ess_battery_gross_profit'),
              'ct.id.gp_materials': ('difference', 'catl.materials_gross_profit'),
              'ct.id.gp_other': ('difference', 'catl.other_businesses_gross_profit'),
              'ct.id.gp_domestic': ('difference', 'catl.domestic_gross_profit'),
              'ct.id.gp_overseas': ('difference', 'catl.overseas_gross_profit'),
              'ct.id.np_attributable': ('difference', 'catl.net_profit_attributable'),
              'ct.id.total_equity': ('difference', 'catl.total_equity'),
              'ct.id.gross_margin': ('ratio', 'catl.gross_margin'),
              'ct.id.ev_margin': ('ratio', 'catl.ev_battery_gross_margin'),
              'ct.id.ess_margin': ('ratio', 'catl.ess_battery_gross_margin'),
              'ct.id.materials_margin': ('ratio', 'catl.materials_gross_margin'),
              'ct.id.domestic_margin': ('ratio', 'catl.domestic_gross_margin'),
              'ct.id.overseas_margin': ('ratio', 'catl.overseas_gross_margin'),
              'ct.id.utilization': ('ratio', 'catl.capacity_utilization'),
              'ct.id.debt_to_asset': ('ratio', 'catl.debt_to_asset_ratio'),
              'ct.id.debt_to_equity': ('ratio', 'catl.debt_to_equity_ratio'),
              'ct.id.materials_share': ('ratio', 'catl.direct_materials_share'),
              'ct.id.materials_cost': ('product', 'catl.direct_materials_cost'),
              'ct.id.interest_income': ('product', 'catl.interest_income'),
              'ct.id.interest_expense': ('product', 'catl.interest_expense_booked'),
              'ct.id.catl_global_usage': ('product', 'catl.global_usage_gwh'),
              'ct.id.catl_exchina_usage': ('product', 'catl.exchina_usage_gwh'),
              'ct.id.byd_global_usage': ('product', 'ev_battery_market.byd_global_usage'),
              'ct.id.interim_dividend': ('product', 'catl.interim_dividend_declared'),
              'ct.id.asbe_np_attributable': ('difference', 'catl.asbe_9m_net_profit_attributable'),
              'ct.id.asbe_total_equity': ('difference', 'catl.asbe_total_equity')}
STOCK_FLOWS = {'ct.sf.cash': 'catl.cash_equivalents',
               'ct.sf.equity': 'catl.equity_attributable',
               'ct.sf.shares': 'catl.shares_issued',
               'ct.sf.asbe_cash': 'catl.asbe_cash_equivalents'}
MATRICES = {}
PATHS = {'ct.path.materials': 'catl.operating_profit',
         'ct.path.materials_offsets': 'catl.operating_profit',
         'ct.path.ev_demand': 'catl.operating_profit',
         'ct.path.ev_overseas': 'catl.operating_profit',
         'ct.path.ess_demand': 'catl.operating_profit',
         'ct.path.competition': 'catl.operating_profit',
         'ct.path.us_policy': 'catl.operating_profit',
         'ct.path.eu_policy': 'catl.net_investing_outflow',
         'ct.path.fx_usd': 'catl.operating_profit',
         'ct.path.fx_eur': 'catl.operating_profit',
         'ct.path.rates_lpr': 'catl.operating_profit',
         'ct.path.rates_fed': 'catl.operating_profit',
         'ct.path.capacity': 'catl.operating_profit',
         'ct.path.equity_income': 'catl.operating_profit',
         'ct.path.wealth_products': 'catl.operating_profit',
         'ct.path.below_operating_profit': 'catl.net_profit_attributable',
         'ct.path.inventory': 'catl.cash_equivalents',
         'ct.path.warranty': 'catl.operating_profit',
         'ct.path.payables': 'catl.cash_equivalents',
         'ct.path.placing': 'catl.cash_equivalents',
         'ct.path.bonds': 'catl.cash_equivalents',
         'ct.path.rebates': 'catl.total_liabilities'}
CALIBRATED = {'ct_eur_cny_exchange_loss': 'documented', 'ct_usd_cny_exchange_loss': 'documented'}


@pytest.fixture(scope="module", params=["sally_demo", "sally_focus_catl"])
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


def test_the_battery_rivalry_with_byd_is_an_uncalibrated_signed_link(g):
    i = link(g, "ev_battery_market.byd_global_share", "catl.global_usage_share")
    assert i.id == "ct_byd_share_catl_share" and not i.quantified and i.transition.sign == "-"
    assert i.transition.evidence.magnitude == "unknown" and i.transition.evidence.sources


def asbe_values(g) -> list[str]:
    return sorted(k for k, v in g.subentities.items() if v.entity_id == CO and k.startswith("catl.asbe_"))


def objects_values(g) -> dict[str, list[str]]:
    """The value ids each composition and identity names (a value of another company, a market, counts as it is)."""
    out = {cid: [c.total, *parts(c)] for cid, c in g.compositions.items() if c.entity_id == CO}
    for iid, x in g.identities.items():
        if x.entity_id == CO:
            out[iid] = [x.target, x.of, *x.minus, *x.factors, *x.numerator, *x.denominator]
    return {k: [v for v in vs if v] for k, vs in out.items()}


def test_every_asbe_value_is_labelled_prc_asbe_and_unaudited(g):
    ids = asbe_values(g)
    assert ids and len(ids) == len({*ids})
    for sid in ids:
        basis = (g.subentities[sid].features or {}).get("basis", "").lower()
        assert "prc asbe" in basis and "unaudited" in basis, sid


def test_no_view_mixes_asbe_with_h1_ifrs_values(g):
    """The ASBE values (nine months, unaudited) are never added to or differenced against the H1 IFRS/HKEX ones: a composition
    or identity holds only the one or the other."""
    asbe = set(asbe_values(g))
    mixed = {k: vs for k, vs in objects_values(g).items() if {v in asbe for v in vs} == {True, False}
             and [v for v in vs if v not in asbe and v in g.subentities and g.subentities[v].entity_id == CO]}
    assert not mixed, sorted(mixed)
    assert {k for k, vs in objects_values(g).items() if asbe & set(vs)} >= {k for k in COMPOSITIONS if k.startswith("ct.comp.asbe_")}


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
