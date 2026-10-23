"""Hyundai Motor's business construction in sally_demo (<client root>/worlds/sally_demo/construction/hyundai.yaml, Oct 22).

Holds the build to the structure its gap register (the client root's docs/construction/hyundai.md) asks for: a Korean automaker with a captive finance arm, tariffs and sourcing, won and euro exposure, and affiliates. The
compositions reconcile by accounting links, one view drives each total, the identities and stock-flows close, every named path
is connected with a transition on each step, and only the evidenced links carry sizes. The objects are checked in the internal
graph, the v4.1.4 export and the service API, in sally_demo and in its focused world (sally_focus_hyundai). Every material
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

skip_without_client('sally_demo', 'sally_focus_hyundai')

CO, PRE, CID = "hyundai", "hy.", "N_HYUNDAI_MOTOR"
OP = "hyundai.operating_profit"
LOCAL = SALLY_WORK / "construction"     # the client's data: local only, absent on CI
# (file, period, the compositions the bundle cannot check: blocked for want of reported parts, never flagged; None = not listed)
# the Oct 22 supplement adds the Hyundai Card, HCS and Kia views: a group bundle cannot check the HCS ones (its own bundles do), nor Kia's at Q2 2026
HCS_BLOCKED = ['hy.comp.hcs_expense_lines', 'hy.comp.hcs_nonop_lines', 'hy.comp.hcs_pretax_bridge', 'hy.comp.hcs_receivable_lines', 'hy.comp.hcs_revenue_lines']
BASELINES = [('baselines_fy2025.json', 'FY2025', ['hy.comp.op_walk_q2', 'hy.comp.revenue_walk_q2', *HCS_BLOCKED]),
             ('baselines_q2_2026.json', 'Q2 2026', [*HCS_BLOCKED, 'hy.comp.kia_equity_income_bridge', 'hy.comp.kia_pretax_bridge']),
             ('baselines_hcs_fy2024.json', 'HCS FY2024', None),
             ('baselines_hcs_sep2025.json', 'HCS Sep 2025', None)]

COMPOSITIONS = {'hy.comp.op_by_segment': ('hyundai.operating_profit', True),
                'hy.comp.revenue_by_segment': ('hyundai.net_revenue', True),
                'hy.comp.revenue_by_entity_region': ('hyundai.net_revenue', True),
                'hy.comp.revenue_by_nature': ('hyundai.net_revenue', True),
                'hy.comp.segment_sales_incl_interseg': ('hyundai.net_revenue', True),
                'hy.comp.vehicle_sales_incl': ('hyundai.vehicle_sales_gross', True),
                'hy.comp.finance_sales_incl': ('hyundai.finance_sales_gross', True),
                'hy.comp.others_sales_incl': ('hyundai.others_sales_gross', True),
                'hy.comp.cos_by_segment': ('hyundai.cost_of_sales', True),
                'hy.comp.sga_by_segment': ('hyundai.sga', True),
                'hy.comp.sga_by_nature': ('hyundai.sga', True),
                'hy.comp.income_statement_lines': ('hyundai.operating_profit', True),
                'hy.comp.expenses_by_function': ('hyundai.total_expenses', True),
                'hy.comp.expenses_by_nature': ('hyundai.total_expenses', True),
                'hy.comp.pretax_bridge': ('hyundai.pretax_profit', True),
                'hy.comp.nonop_bridge': ('hyundai.non_operating_items', True),
                'hy.comp.nonop_lines': ('hyundai.non_operating_items', True),
                'hy.comp.equity_by_investee': ('hyundai.equity_method_income', True),
                'hy.comp.wholesale_by_region': ('hyundai.wholesale_units', True),
                'hy.comp.retail_by_region': ('hyundai.retail_units', True),
                'hy.comp.wholesale_by_powertrain': ('hyundai.wholesale_units', True),
                'hy.comp.wholesale_by_body': ('hyundai.wholesale_units', True),
                'hy.comp.wholesale_by_brand': ('hyundai.wholesale_units', True),
                'hy.comp.op_walk': ('hyundai.op_change_yoy', True),
                'hy.comp.revenue_walk': ('hyundai.rev_change_yoy', True),
                'hy.comp.op_walk_q2': ('hyundai.opq2_swing', True),
                'hy.comp.revenue_walk_q2': ('hyundai.revq2_swing', True),
                'hy.comp.investment_by_type': ('hyundai.investment_overall', True),
                'hy.comp.hca_pretax': ('hyundai.hca_pretax', True),
                'hy.comp.hcard_revenue_lines': ('hyundai.hcard_operating_revenue', True),
                'hy.comp.hcard_expense_lines': ('hyundai.hcard_operating_expenses', True),
                'hy.comp.hcard_pretax_bridge': ('hyundai.hcard_pretax', True),
                'hy.comp.hcard_debt_lines': ('hyundai.hcard_debt', True),
                'hy.comp.hcs_revenue_lines': ('hyundai.hcs_operating_revenue', True),
                'hy.comp.hcs_expense_lines': ('hyundai.hcs_operating_expenses', True),
                'hy.comp.hcs_nonop_lines': ('hyundai.hcs_nonop_income', True),
                'hy.comp.hcs_pretax_bridge': ('hyundai.hcs_pretax', True),
                'hy.comp.hcs_receivable_lines': ('hyundai.hcs_receivables', True),
                'hy.comp.kia_pretax_bridge': ('hyundai.kia_pretax', True),
                'hy.comp.kia_equity_income_bridge': ('hyundai.eq_kia', True)}
# one view drives each total; these reconcile against it without driving it
RECONCILING = {'hy.comp.expenses_by_nature': 'drives: false',
               'hy.comp.income_statement_lines': 'drives: false',
               'hy.comp.hcs_nonop_lines': 'drives: false',
               'hy.comp.nonop_lines': 'drives: false',
               'hy.comp.revenue_by_entity_region': 'drives: false',
               'hy.comp.revenue_by_nature': 'drives: false',
               'hy.comp.segment_sales_incl_interseg': 'drives: false',
               'hy.comp.sga_by_nature': 'drives: false',
               'hy.comp.wholesale_by_body': 'drives: false',
               'hy.comp.wholesale_by_brand': 'drives: false',
               'hy.comp.wholesale_by_powertrain': 'drives: false'}
IDENTITIES = {'hy.id.gross_profit': ('difference', 'hyundai.gross_profit'),
              'hy.id.vehicle_gp': ('difference', 'hyundai.vehicle_gp'),
              'hy.id.finance_gp': ('difference', 'hyundai.finance_gp'),
              'hy.id.others_gp': ('difference', 'hyundai.others_gp'),
              'hy.id.vehicle_op': ('difference', 'hyundai.vehicle_op'),
              'hy.id.finance_op': ('difference', 'hyundai.finance_op'),
              'hy.id.others_op': ('difference', 'hyundai.others_op'),
              'hy.id.opm': ('ratio', 'hyundai.operating_margin'),
              'hy.id.net_income': ('difference', 'hyundai.net_income'),
              'hy.id.net_income_owners': ('difference', 'hyundai.net_income_owners'),
              'hy.id.vehicle_revenue': ('product', 'hyundai.vehicle_revenue'),
              'hy.id.channel_stock': ('difference', 'hyundai.channel_stock_build'),
              'hy.id.us_imports': ('difference', 'hyundai.us_import_units'),
              'hy.id.us_duty': ('product', 'hyundai.us_tariff_cost'),
              'hy.id.tariff_offset': ('product', 'hyundai.tariff_mitigation_offset'),
              'hy.id.tariff_net': ('difference', 'hyundai.tariff_net_burden'),
              'hy.id.hca_net_financing': ('difference', 'hyundai.hca_net_financing_revenue'),
              'hy.id.hca_net_income': ('difference', 'hyundai.hca_net_income'),
              'hy.id.hca_interest': ('product', 'hyundai.hca_interest_expense'),
              'hy.id.hca_krw': ('product', 'hyundai.hca_pretax_krw'),
              'hy.id.payout': ('ratio', 'hyundai.payout_ratio'),
              'hy.id.hcard_op_income': ('difference', 'hyundai.hcard_operating_income'),
              'hy.id.hcard_profit': ('difference', 'hyundai.hcard_profit'),
              'hy.id.hcard_profit_owners': ('difference', 'hyundai.hcard_profit_owners'),
              'hy.id.hcard_equity': ('difference', 'hyundai.hcard_equity'),
              'hy.id.hcard_interest': ('product', 'hyundai.hcard_interest_expense'),
              'hy.id.hcs_op_income': ('difference', 'hyundai.hcs_operating_income'),
              'hy.id.hcs_net_income': ('difference', 'hyundai.hcs_net_income'),
              'hy.id.hcs_net_income_owners': ('difference', 'hyundai.hcs_net_income_owners'),
              'hy.id.hcs_equity': ('difference', 'hyundai.hcs_equity'),
              'hy.id.hcs_interest': ('product', 'hyundai.hcs_interest_expense'),
              'hy.id.hcs_p_equity': ('difference', 'hyundai.hcs_p_equity'),
              'hy.id.kia_gp': ('difference', 'hyundai.kia_gross_profit'),
              'hy.id.kia_op_profit': ('difference', 'hyundai.kia_operating_profit'),
              'hy.id.kia_profit': ('difference', 'hyundai.kia_profit'),
              'hy.id.kia_profit_owners': ('difference', 'hyundai.kia_profit_owners'),
              'hy.id.kia_equity': ('difference', 'hyundai.kia_equity'),
              'hy.id.kia_pro_rata': ('product', 'hyundai.eq_kia_pro_rata')}
STOCK_FLOWS = {'hy.sf.cash': 'hyundai.cash_equivalents',
               'hy.sf.affiliates': 'hyundai.invest_in_affiliates',
               'hy.sf.warranty': 'hyundai.warranty_provision'}
MATRICES = {}
PATHS = {'hy.path.tariffs_sourcing': 'hyundai.operating_profit',
         'hy.path.tariff_mitigation': 'hyundai.operating_profit',
         'hy.path.fx_won_dollar': 'hyundai.pretax_profit',
         'hy.path.fx_won_euro': 'hyundai.pretax_profit',
         'hy.path.pricing_incentives': 'hyundai.operating_profit',
         'hy.path.europe_competition': 'hyundai.operating_profit',
         'hy.path.powertrain_hybrid': 'hyundai.operating_profit',
         'hy.path.powertrain_ev': 'hyundai.operating_profit',
         'hy.path.input_costs': 'hyundai.operating_profit',
         'hy.path.labour': 'hyundai.operating_profit',
         'hy.path.supplier_disruption': 'hyundai.operating_profit',
         'hy.path.demand_us': 'hyundai.operating_profit',
         'hy.path.demand_europe': 'hyundai.operating_profit',
         'hy.path.demand_korea': 'hyundai.operating_profit',
         'hy.path.demand_india': 'hyundai.operating_profit',
         'hy.path.demand_china': 'hyundai.operating_profit',
         'hy.path.affiliates_china': 'hyundai.pretax_profit',
         'hy.path.affiliates_kia': 'hyundai.pretax_profit',
         'hy.path.affiliates_new_business': 'hyundai.pretax_profit',
         'hy.path.finance_us_funding': 'hyundai.operating_profit',
         'hy.path.finance_used_values': 'hyundai.operating_profit',
         'hy.path.finance_hca_growth': 'hyundai.operating_profit',
         'hy.path.finance_hca_credit': 'hyundai.operating_profit',
         'hy.path.finance_korea_funding': 'hyundai.operating_profit',
         'hy.path.finance_credit_korea': 'hyundai.operating_profit',
         'hy.path.finance_lease_book': 'hyundai.operating_profit',
         'hy.path.interest_rates_korea': 'hyundai.pretax_profit',
         'hy.path.interest_rates_us': 'hyundai.pretax_profit',
         'hy.path.capital_return': 'hyundai.cash_equivalents',
         'hy.path.investment_cash': 'hyundai.cash_equivalents',
         'hy.path.localization_investment': 'hyundai.operating_profit',
         'hy.path.group_bridge': 'hyundai.net_income_owners',
         'hy.path.warranty_roll': 'hyundai.warranty_provision',
         'hy.path.research_investment': 'hyundai.operating_profit',
         'hy.path.card_funding': 'hyundai.operating_profit',
         'hy.path.card_growth': 'hyundai.operating_profit',
         'hy.path.hcs_funding': 'hyundai.operating_profit',
         'hy.path.hcs_settlement_interest': 'hyundai.operating_profit',
         'hy.path.hcs_growth': 'hyundai.operating_profit',
         'hy.path.hcs_lease_book': 'hyundai.operating_profit',
         'hy.path.hcs_credit': 'hyundai.operating_profit',
         'hy.path.hcs_partial_profit': 'hyundai.operating_profit',
         'hy.path.kia_profit_equity': 'hyundai.net_income',
         'hy.path.kia_dividends': 'hyundai.invest_in_affiliates'}
HCS_PARTIAL = ['hyundai.hcs_p_assets', 'hyundai.hcs_p_liabilities', 'hyundai.hcs_p_sales', 'hyundai.hcs_p_profit', 'hyundai.hcs_p_equity']
CALIBRATED = {'hy_eur_net_fx': 'documented', 'hy_usd_net_fx': 'documented'}


@pytest.fixture(scope="module", params=["sally_demo", "sally_focus_hyundai"])
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


def test_the_business_records_are_projects_and_events(g):
    rep = load_repair(LOCAL, {CID})
    if not rep:
        pytest.skip("the client's local hyundai/repair.json is absent (data/ is gitignored; CI has none)")
    kinds = {r["record_kind"] for r in rep[0]["business_records"]}
    assert kinds == {"project", "event", "relationship", "rating", "coverage", "input_status"}
    assert len([r for r in rep[0]["business_records"] if r["record_kind"] in ("project", "event")]) == 12     # the earlier records stay


def test_the_hcs_partial_scope_is_labelled_partial(g):
    """The summary lines Hyundai Motor's notes give of Hyundai Capital Services are partial coverage, and say so in their basis
    and in their coverage; no other HCS value sits in that scope."""
    scoped = sorted(k for k, v in g.subentities.items() if (v.features or {}).get("view") == "hcs_partial_scope")
    assert scoped == sorted(HCS_PARTIAL)
    for sid in scoped:
        f = g.subentities[sid].features
        assert "partial" in f["basis"].lower() and "partial" in str(f.get("coverage", "")).lower(), sid


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
