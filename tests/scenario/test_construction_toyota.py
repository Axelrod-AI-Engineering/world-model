"""Toyota's business construction in sally_demo (<client root>/worlds/sally_demo/construction/toyota.yaml, Oct 17).

Holds the build to the reviewer's Toyota requirements (docs/construction/toyota.md): the composition views reconcile by
accounting links with their residuals and eliminations, and overlapping views never share a part or a calibrated route;
every named path is connected and every step carries a transition (a sign when uncalibrated); the tariff path has its
five transitions; the yen's parts are never added to the calibrated aggregate; s44 is re-routed; and a development the
paths were not written for (a stoppage of Japanese production) is traced through the structure to a financial endpoint.
The objects are checked in the internal graph, the v4.1.4 export, and the service API. sally_demo loads once.

Second review round (Oct 18): every material claim resolves to a located citation, no input is left unreviewed, and
every additive composition reconciles at the model's medians and at the local baselines. The citation and baseline
checks read the client's local files (data/work/sally, gitignored) and skip where they are absent, as on CI."""

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
from axelrod_wm.model.construction import (
    bundle_levels,
    bundle_series,
    model_levels,
    reconcile,
    reconcile_identities,
    reconcile_stock_flows,
    validate_construction,
)
from axelrod_wm.repo.snapshots import MemoryBackend
from tests.clients import SALLY_WORK, skip_without_client
from tests.scenario import v1_reads as v1

skip_without_client('sally_demo')

ROOT = Path(__file__).resolve().parents[2]
LOCAL = SALLY_WORK / "construction"     # the client's data: local only, absent on CI
OP, NI = "toyota.operating_profit", "toyota.net_income"
COMPS = {"ty.comp.reporting_segments", "ty.comp.regional_operating_income", "ty.comp.regional_external_revenue",
         "ty.comp.revenue_by_customer_location", "ty.comp.units_by_customer_region", "ty.comp.units_by_production_region",
         "ty.comp.retail_units_bridge", "ty.comp.retail_units_by_powertrain", "ty.comp.financial_services",
         "ty.comp.pretax_bridge", "ty.comp.net_income_bridge", "ty.comp.segment_revenue",
         "ty.comp.us_customs_base_by_origin", "ty.comp.fs_by_scope",
         "ty.comp.fs_revenue_lines", "ty.comp.fs_cost_lines", "ty.comp.us_fin_contribution"}
PATHS = {"ty.path.regional_growth", "ty.path.pricing_competition", "ty.path.asia_entrants", "ty.path.product_mix",
         "ty.path.tariffs_sourcing", "ty.path.yen", "ty.path.financing_funding", "ty.path.financing_credit_residual",
         "ty.path.execution_share", "ty.path.new_initiatives", "ty.path.china_affiliates", "ty.path.group_bridge",
         "ty.path.supply_availability", "ty.path.financing_borrower", "ty.path.production_disruption",
         "ty.path.cash_capital", "ty.path.us_finance_module"}


@pytest.fixture(scope="module", params=["sally_demo", "sally_focus"])
def client(request):
    # Oct 18: the same build holds in the focused world (Toyota and Tokio Marine only, engine/focus.py)
    app = create_app(scenario=request.param, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def g(client):
    return client.app.state.axelrod.controller.engine.wm.graph


def acct_links(g):
    return {(i.source_id, i.target_id): i for i in g.active_interactions() if str(i.edge_type) == "accounting"}


def parts(c):
    return [*c.members, *([c.residual] if c.residual else []), *([c.eliminations] if c.eliminations else [])]


def mean(g, sid):
    return float(g.subentities[sid].posterior.mean())


# -- structure ----------------------------------------------------------------------------------------------------------
def test_no_construction_problems_for_toyota(g):
    own = [p for p in validate_construction(g) if "toyota" in p or "ty." in p or "ty_" in p]
    assert own == []
    assert construction_view(g, "toyota")["problems"] == []


def test_required_compositions_exist(g):
    mine = {cid: c for cid, c in g.compositions.items() if c.entity_id == "toyota"}
    assert set(mine) == COMPS
    views = {c.view for c in mine.values()}
    assert {"reporting_segments", "regions", "customer_location", "production_location", "product", "financial_services"} <= views
    seg, reg = mine["ty.comp.reporting_segments"], mine["ty.comp.regional_operating_income"]
    assert set(seg.members) == {"toyota.automotive_operating_income", "toyota.financial_services_operating_income"}
    assert seg.residual == "toyota.other_business_operating_income" and seg.eliminations == "toyota.segment_eliminations"
    assert {m.split(".")[1] for m in reg.members} == {"japan_operating_income", "north_america_operating_income",
                                                      "europe_operating_income", "asia_operating_income"}
    assert reg.residual and reg.eliminations


def test_additive_views_reconcile_by_accounting_links(g):
    links = acct_links(g)
    for cid in COMPS:
        c = g.compositions[cid]
        for sid in parts(c):
            i = links.get((sid, c.total))
            assert i is not None, (cid, sid)
            assert i.transition is not None and i.transition.sign is not None, (cid, sid)
            if not c.drives:
                # a reconciling view's links carry no size into the total (one driving view per total)
                assert not i.quantified, (cid, sid)
                continue
            # deductions carry a negative weight, everything else a positive one
            assert (i.forward.effect.mean() < 0) == (i.transition.sign == "-"), (cid, sid)
        # the synthetic levels add up too (deductions subtracted), within a tenth of the total
        signed = sum(mean(g, s) * (1 if links[(s, c.total)].transition.sign == "+" else -1) for s in parts(c))
        assert abs(signed - mean(g, c.total)) <= 0.1 * abs(mean(g, c.total)) + 0.05, (cid, signed, mean(g, c.total))


def test_regional_and_business_views_never_share_a_part(g):
    seg, reg = g.compositions["ty.comp.reporting_segments"], g.compositions["ty.comp.regional_operating_income"]
    assert seg.total == reg.total == OP and not set(parts(seg)) & set(parts(reg))
    a, b = g.compositions["ty.comp.regional_external_revenue"], g.compositions["ty.comp.revenue_by_customer_location"]
    assert a.total == b.total and not set(parts(a)) & set(parts(b))
    # internal supply is its own value, not a part of the external-customer view
    assert "toyota.japan_intersegment_revenue" not in parts(a)


def test_customer_and_production_views_are_separate(g):
    sold, built = g.compositions["ty.comp.units_by_customer_region"], g.compositions["ty.comp.units_by_production_region"]
    assert (sold.view, built.view) == ("customer_location", "production_location")
    assert sold.total != built.total and not set(parts(sold)) & set(parts(built))
    # exports and imports are difference identities between the two views, not parts of either (Oct 18); Japan's
    # other flows (inventory build) are the export identity's explicit residual
    ex, im = g.identities["ty.id.japan_exports"], g.identities["ty.id.na_imports"]
    assert ex.form == im.form == "difference"
    assert (ex.target, ex.of, set(ex.minus)) == ("toyota.japan_export_units", "toyota.japan_production",
                                                 {"toyota.japan_units", "toyota.japan_other_flows"})
    assert (im.target, im.of, im.minus) == ("toyota.na_import_units", "toyota.north_america_units",
                                            ["toyota.north_america_production"])
    w = {(i.source_id, i.target_id): i.forward.effect.mean() for i in g.active_interactions()
         if str(i.edge_type) == "identity"}
    exp, imp = "toyota.japan_export_units", "toyota.na_import_units"
    assert w[("toyota.japan_production", exp)] > 0 > w[("toyota.japan_units", exp)]
    assert w[("toyota.north_america_units", imp)] > 0 > w[("toyota.north_america_production", imp)]


def test_no_product_margin_values(g):
    product = [s for s in g.subentities.values() if s.entity_id == "toyota" and s.features.get("view") == "product"]
    assert len(product) >= 5
    assert all(s.attribute_kind != "margin" and "margin" not in s.name.lower() for s in product)
    assert all(s.attribute_kind != "margin" for s in g.subentities.values() if s.entity_id == "toyota")


def test_every_new_value_states_its_view_and_basis(g):
    own = [s for s in g.subentities.values() if s.entity_id == "toyota" and s.id != "toyota.share_price"]
    assert len(own) > 60
    assert all(s.features.get("view") and s.features.get("basis") for s in own), \
        [s.id for s in own if not s.features.get("basis")]


def test_entity_describes_the_composition(g):
    d = g.entities["toyota"].description
    assert "financial-services" in d and "regions" in d and "JVs" in d


# -- paths --------------------------------------------------------------------------------------------------------------
def test_required_paths_exist(g):
    mine = {pid: p for pid, p in g.paths.items() if p.entity_id == "toyota"}
    assert set(mine) == PATHS
    for pid, p in mine.items():
        # the capital path ends in shares outstanding (capital, not earnings)
        assert p.endpoint in (OP, NI, "toyota.shares_outstanding"), pid
        for st in p.steps:
            i = g.interactions[st.interaction_id]
            assert i.transition is not None, (pid, i.id)
            assert i.transition.mechanism and i.transition.next_state, (pid, i.id)
            if not i.quantified:
                assert i.transition.sign in ("+", "-"), (pid, i.id)
        # a path is Toyota's own, not the shared exporter grouping
        assert any(g.interactions[s.interaction_id].source_id.startswith("toyota.") for s in p.steps), pid


def test_tariff_path_has_the_five_transitions(g):
    p = g.paths["ty.path.tariffs_sourcing"]
    steps = [(g.interactions[s.interaction_id], s.branch) for s in p.steps]
    pairs = {(i.source_id, i.target_id) for i, _ in steps}
    # 1. regime and sourcing -> incremental customs cost
    assert ("us_vehicle_tariffs.effective_rate", "toyota.us_tariff_cost") in pairs
    # 2. cost -> management response: parallel branches from the same state
    responses = {b for i, b in steps if i.source_id == "toyota.us_tariff_cost"}
    assert {"reprice", "resource", "absorb", "transfer_price"} <= responses
    # 3. price offer -> customer response
    assert ("toyota.na_list_price_index", "toyota.north_america_units") in pairs
    assert ("toyota.na_list_price_index", "toyota.na_revenue_per_vehicle") in pairs
    # 4. sales and production -> regional economics
    assert ("toyota.north_america_external_revenue", "toyota.north_america_operating_income") in pairs
    assert ("toyota.north_america_production", "toyota.japan_export_units") in pairs
    # 5. regional economics -> group result, by identity
    ends = {i.id: i for i, _ in steps if i.target_id == OP}
    assert ends and all(str(i.edge_type) == "accounting" for i in ends.values())
    # the customs cost per point of the rate is sized from the company's planned tariff cost (Oct 18). Pack round: the
    # company reports the tariff impact one for one inside consolidated operating income, so absorption is sized -1 per
    # +1 of cost, graded model because the regional split is not disclosed; every other response (price, sourcing,
    # transfer price, customer) stays unknown
    # Batch 2 (Q7): the rate's step is now a term of the exact duty identity (duty = covered customs value x rate), not a
    # guidance-sized reduced form; the customs base by origin feeds the other term
    cost = g.interactions["ty_tariff_cost"]
    assert str(cost.edge_type) == "identity" and cost.identity == "ty.id.us_duty"
    assert g.identities["ty.id.us_duty"].factors == ["toyota.us_customs_base", "us_vehicle_tariffs.effective_rate"]
    absorb = g.interactions["ty_tariff_absorb"]
    assert absorb.quantified and absorb.forward.effect.mean() < 0 and absorb.transition.evidence.magnitude == "model"
    assert "ty.dk" in absorb.transition.evidence.sources
    assert all(not i.quantified for i, _ in steps
               if str(i.edge_type) not in ("accounting", "identity") and i.id not in ("ty_tariff_cost", "ty_tariff_absorb"))
    # rate -> cost -> North America operating income -> operating profit is now sized on Toyota's own steps
    assert ("toyota.north_america_operating_income", OP) in {(i.source_id, i.target_id) for i, _ in steps}
    # plan round, operational: covered imports reach the cost through the customs base, which neither North America
    # imports nor Japan exports are (R14); the duty falls due at entry; incentives are a fifth response; dealers and
    # plants respond
    assert {"incentives"} <= responses
    assert ("toyota.na_import_units", "toyota.us_customs_base_third_country") in pairs
    assert ("toyota.japan_export_units", "toyota.us_customs_base_japan") in pairs
    assert ("toyota.north_america_production", "toyota.us_customs_base_north_america") in pairs
    assert ("toyota.us_customs_base", "toyota.us_tariff_cost") in pairs
    assert ("toyota.na_import_units", "toyota.us_tariff_cost") not in pairs
    assert all("R14" in (g.interactions[k].note or "") for k in ("ty_tariff_base", "ty_exports_customs_base"))
    assert "customs entry" in g.interactions["ty_customs_base_cost"].transition.timing.onset
    assert {("toyota.north_america_units", "toyota.na_dealer_inventory"),
            ("toyota.north_america_production", "toyota.north_america_operating_income")} <= pairs
    # Batch 2 (Q8): transfer support reallocates between regions and sums to zero at the group
    na, jp = g.interactions["ty_transfer_support_na"], g.interactions["ty_transfer_support_japan"]
    assert na.forward.effect.mean() > 0 > jp.forward.effect.mean()
    assert g.interactions["ty_tariff_transfer"].target_id == "toyota.tariff_transfer_support"


def test_yen_branches_are_separate_and_never_added_to_the_aggregate(g):
    p = g.paths["ty.path.yen"]
    br = {s.branch: g.interactions[s.interaction_id] for s in p.steps if s.branch}
    assert set(br) == {"disclosed_total", "transaction", "translation", "imported_inputs"}
    agg = br["disclosed_total"]
    assert agg.id == "m29" and agg.quantified and agg.transition is not None
    # pack round (R13): the company's own walks size the transaction branch (documented); m29 carries only the
    # remainder of the total FX effect (inferred); translation and imported inputs stay unsized inside that remainder
    assert br["transaction"].quantified and br["transaction"].transition.evidence.magnitude == "documented"
    assert "ty.dk" in br["transaction"].transition.evidence.sources
    assert all(not br[b].quantified for b in ("translation", "imported_inputs"))
    assert agg.transition.evidence.magnitude == "inferred" and "ty.fsum" in agg.transition.evidence.sources
    # transaction lands in Japan, translation in North America: separate accounts
    assert br["transaction"].target_id == "toyota.japan_operating_income"
    assert br["translation"].target_id == "toyota.north_america_operating_income"


def test_s44_is_rerouted_and_uncalibrated(g):
    i = g.interactions["s44"]
    assert (i.source_id, i.target_id) == ("toyota.consolidated_units", "toyota.automotive_revenue")
    assert not i.quantified and i.transition.sign == "+" and i.channels() == []
    assert not any(j.source_id == "toyota.vehicle_sales" and j.target_id == OP for j in g.active_interactions())


def test_broad_links_keep_their_records_and_gain_transitions(g):
    # m29 was re-sized in the pack round to the remainder after the transaction branch (0.7, model -> 0.5419, inferred)
    for iid, src, tgt, mu in (("m29", "dollar_yen.usd_jpy", OP, 0.5365),
                              ("s42", "us_economy.gdp_growth", "toyota.vehicle_sales", 0.3),
                              ("s43", "china_economy.gdp_growth", "toyota.vehicle_sales", 0.2)):
        i = g.interactions[iid]
        assert (i.source_id, i.target_id) == (src, tgt) and i.quantified, iid
        assert abs(i.forward.effect.mean() - mu) < 1e-9 and i.transition is not None, iid


def test_financing_debt_is_not_industrial(g):
    links = {(i.source_id, i.target_id): i for i in g.active_interactions()}
    assert ("toyota.fs_finance_receivables", "toyota.fs_borrowings") in links
    assert g.subentities["toyota.fs_borrowings"].features["view"] == "financial_services"
    # subvention is an incentive that reaches finance revenue once (eliminated at group level), not a second incentive
    sub = links[("toyota.na_incentive_per_unit", "toyota.financial_services_revenue")]
    assert "counted once" in sub.transition.mechanism


def test_group_bridge_reconciles(g):
    links = acct_links(g)
    assert links[(OP, "toyota.pretax_income")].transition.sign == "+"
    assert links[("toyota.equity_method_income", "toyota.pretax_income")].transition.sign == "+"
    assert links[("toyota.income_tax_expense", NI)].transition.sign == "-"
    assert links[("toyota.noncontrolling_interests", NI)].transition.sign == "-"
    tax = next(i for i in g.active_interactions() if i.id == "ty_tax_formula")
    assert tax.quantified and tax.transition.evidence.magnitude == "documented"
    # equity-method income is after the investees' tax: it offsets the formula's charge on it
    assert g.interactions["ty_tax_equity_exclusion"].forward.effect.mean() < 0


def test_no_calibrated_route_reaches_a_total_through_two_views(g):
    """A shock must not reach one total through the parts of two overlapping views by calibrated links (it would be
    counted twice); the only calibrated causal entry to Toyota's profit is the aggregate m29, straight to the total."""
    into: dict[str, list[str]] = {}
    for i in g.active_interactions():
        if i.quantified:
            into.setdefault(i.target_id, []).append(i.source_id)

    def ancestors(sids: list[str]) -> set[str]:
        seen, stack = set(), list(sids)
        while stack:
            v = stack.pop()
            for u in into.get(v, []):
                if u not in seen:
                    seen.add(u)
                    stack.append(u)
        return seen

    by_total: dict[str, list] = {}
    for c in g.compositions.values():
        if c.entity_id == "toyota" and c.additive:
            by_total.setdefault(c.total, []).append(c)
    shared = {t: cs for t, cs in by_total.items() if len(cs) > 1}
    assert set(shared) == {OP, "toyota.net_revenue", "toyota.financial_services_operating_income"}
    for t, cs in shared.items():
        # every pair of views of one total (net revenue has three since the plan round)
        reach = [ancestors(parts(c)) | set(parts(c)) for c in cs]
        for x in range(len(reach)):
            for y in range(x + 1, len(reach)):
                assert not reach[x] & reach[y], (t, cs[x].id, cs[y].id, sorted(reach[x] & reach[y]))


# -- generalization -------------------------------------------------------------------------------------------------------
def test_generalization_trace_japan_production_stoppage(g):
    """A stoppage at Japanese plants (supplier failure, quake, cyber incident): no path was written for it."""
    start = "toyota.japan_production"
    assert all(g.interactions[p.steps[0].interaction_id].source_id != start for p in g.paths.values())
    tr = trace(g, start, "toyota", through_totals=True)
    assert tr["reaches_endpoint"]
    to_op = [r for r in tr["routes"] if r["ends_at"] == OP]
    assert to_op, tr["stops"]
    hops = {tuple(s["target"] for s in r["steps"]) for r in to_op}
    # through the export margin of the Japan segment ...
    assert ("toyota.japan_export_units", "toyota.japan_intersegment_revenue", "toyota.japan_operating_income", OP) in hops
    # ... and through North American availability (dealer stock, volume, revenue, regional profit)
    assert any("toyota.na_dealer_inventory" in h and "toyota.north_america_operating_income" in h for h in hops)
    # it also reaches the production total by identity, and every step it uses carries a transition
    assert any(r["ends_at"] == "toyota.production_units" for r in tr["routes"])
    assert all(not r["steps_without_transition"] for r in to_op)
    # it reaches financial-services income through incentive subvention (a segment-level transfer eliminated at group
    # level, so it is a stop, never added to the regional routes) and the US duty base through lower imports
    assert any(r["ends_at"] == "toyota.financial_services_operating_income" for r in tr["routes"])
    touched = {s["target"] for r in tr["routes"] for s in r["steps"]}
    assert "toyota.us_tariff_cost" in touched
    # where it stops: every route to profit rests on uncalibrated steps, so it gives a direction, not a size. Traced
    # through totals (Oct 18), lost North American volume also reaches the automotive segment (consolidated volume ->
    # automotive revenue), a reconciling view that carries no size into operating profit; it never reaches equity-method
    # income or the powertrain view, and Japanese exports reach only North America (other regions' supply and component
    # exports to overseas plants are not represented)
    assert all(r["uncalibrated_steps"] for r in to_op)
    auto = [r for r in to_op if "toyota.automotive_operating_income" in {s["target"] for s in r["steps"]}]
    # (Batch 2: the dealer-stock roll-forward lengthens the availability routes, so within the trace depth the
    # automotive-segment route may not appear; when it does, it runs through s44)
    assert all(any(s["interaction_id"] == "s44" for s in r["steps"]) for r in auto)
    assert not touched & {"toyota.equity_method_income", "toyota.hybrid_retail_units",
                          "toyota.europe_operating_income", "toyota.asia_operating_income"}


# -- conversion round (Oct 18): one driving view per total, identities, state ------------------------------------------
IDENTITIES = {"ty.id.na_revenue", "ty.id.japan_revenue", "ty.id.europe_revenue", "ty.id.asia_revenue",
              "ty.id.fs_interest_income", "ty.id.fs_funding_interest", "ty.id.japan_exports", "ty.id.na_imports",
              "ty.id.industrial_fcf", "ty.id.dividends", "ty.id.us_duty", "ty.id.na_incentive_cost",
              "ty.id.incentive_breakeven", "ty.id.dealer_days", "ty.id.us_fin_income", "ty.id.us_fin_expense",
              "ty.id.us_fin_nii", "ty.id.fs_us_scope",
              # Batch 2, Part 3 (gaps the seeds exposed): US brand units, EPS on weighted-average shares, pure translation
              "ty.id.us_brand_units", "ty.id.eps", "ty.id.us_translation",
              "ty.id.hybrid_mix_op", "ty.id.price_recovery_in_year", "ty.id.cost_recognized_in_year", "ty.id.pricing_net_op",
              "ty.id.us_duty_avoided"}


def test_one_driving_view_per_total(g):
    """The regional view drives operating profit and the selling-company view drives net revenue; the business segments
    and revenue by customer location reconcile to the same totals without driving them."""
    mine = {cid: c for cid, c in g.compositions.items() if c.entity_id == "toyota"}
    driving: dict[str, list[str]] = {}
    for cid, c in mine.items():
        if c.additive and c.drives:
            driving.setdefault(c.total, []).append(cid)
    assert all(len(v) == 1 for v in driving.values()), driving
    assert driving[OP] == ["ty.comp.regional_operating_income"]
    assert driving["toyota.net_revenue"] == ["ty.comp.regional_external_revenue"]
    assert not mine["ty.comp.reporting_segments"].drives and not mine["ty.comp.revenue_by_customer_location"].drives
    assert not [p for p in validate_construction(g) if "driving views" in p and ("toyota" in p or "ty." in p)]


def test_identities_are_exact_and_reconcile(g):
    mine = {iid: x for iid, x in g.identities.items() if x.entity_id == "toyota"}
    assert set(mine) == IDENTITIES
    # each term reaches its target by an identity link with a derived, fixed weight; the written ones keep their
    # transitions (units x revenue per vehicle; receivables x contract rate; borrowings x funding rate)
    links = [i for i in g.active_interactions() if str(i.edge_type) == "identity" and i.identity in mine]
    assert len(links) == sum(len(x.terms()) for x in mine.values())
    assert all(i.quantified and i.transition is not None for i in links)
    for iid in ("ty_na_rev_units", "ty_japan_units_rev", "ty_receivables_rev", "ty_funding_cost"):
        assert str(g.interactions[iid].edge_type) == "identity"
    rows = [r for r in reconcile_identities(g, model_levels(g, "median")) if r["identity_id"] in IDENTITIES]
    assert len(rows) == len(IDENTITIES) and all(r["status"] == "ok" for r in rows), rows


def test_translation_sign_follows_north_america_profit(g):
    i = g.interactions["ty_yen_translation"]
    assert not i.quantified and i.transition.sign == "+"
    assert any(p.moderator_id == "toyota.north_america_operating_income" for p in i.parameters)


# -- second review round: sources, inputs, reconciliation ---------------------------------------------------------------
def local(name: str) -> Path:
    p = LOCAL / "toyota" / name
    if not p.exists():
        pytest.skip(f"the client's local {name} is absent (data/ is gitignored; CI has none)")
    return p


def test_every_material_claim_resolves_to_a_located_citation(g):
    local("citations.json")
    sources = load_sources(LOCAL)
    cc = company_citations(g, "toyota", sources)
    assert cc["claims_without_citation"] == [], [c["interaction_id"] for c in cc["claims_without_citation"]]
    assert cc["unresolved"] == [] and cc["unknown_citation_keys"] == []
    assert not [p for p in sources["problems"] if "ty." in p]
    # each cited source is a catalogued document, each citation has a location and a passage of at most ~300 chars
    mine = {k: [c for c in cs if c["company"] == "toyota"] for k, cs in sources["citations"].items()}
    refs = [c for cs in mine.values() for c in cs]
    assert refs and all(c["location"] and c["passage"] and len(c["passage"]) <= 300 for c in refs)
    assert {c["source"] for c in refs} <= {s for s, x in sources["catalogue"].items() if x["company"] == "toyota"}
    # every value the local baselines observe is cited too
    observed = set(bundle_levels(json.loads(local("baselines.json").read_text())))
    assert observed and observed <= set(mine), sorted(observed - set(mine))


def test_no_input_is_left_unreviewed(g):
    ins = inputs_by_status(g, "toyota")
    # its own inputs: those on links into its values (a link that only starts here, e.g. another company's use of
    # a shared market state, belongs to the company it leads into)
    own = set(g.entities["toyota"].subentity_ids)
    ins["inputs"] = [n for n in ins["inputs"] if any(g.interactions[i].target_id in own for i in n["interaction_ids"])]
    assert ins["not_yet_reviewed"] == [] and ins["counts"]["not_yet_reviewed"] == 0
    assert sum(ins["counts"].values()) >= 50
    for n in ins["inputs"]:
        # "missing" is declared only after a search, and "found" names where
        if n["status"] == "not_disclosed_in_reviewed_sources":
            assert n["searched"] and any(s.startswith("corpus: ") for s in n["searched"]), n["input"]
        if n["status"].startswith("found"):
            assert n["found_in"], n["input"]
    # every source a search or a finding names is a source id, never a client file name
    named = {s for n in ins["inputs"] for s in [*n["searched"], *n["found_in"]] if not s.startswith("corpus: ")}
    assert named and all(s.startswith("ty.") for s in named)


def toyota_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["entity_id"] == "toyota"]


def test_compositions_reconcile_at_the_model_medians(g):
    """Round synthetic construction levels add up exactly: total = members + residual + eliminations, deductions
    subtracted, at the medians (a lognormal's construction level)."""
    rows = toyota_rows(reconcile(g, model_levels(g, "median")))
    assert {r["composition_id"] for r in rows} == COMPS
    assert all(r["status"] == "ok" for r in rows), [(r["composition_id"], r["relative_difference"]) for r in rows]
    assert all(abs(r["relative_difference"]) < 1e-9 for r in rows)


def test_compositions_reconcile_at_the_local_baselines(g):
    """The reported parts add to the reported totals for one period (the client's workbook): operating profit equals
    both the business-segment and the regional sums, within the workbook's own rounding."""
    levels = bundle_levels(json.loads(local("baselines.json").read_text()))
    assert {OP, "toyota.vehicle_sales"} <= set(levels)
    rows = toyota_rows(reconcile(g, levels))
    assert {r["composition_id"] for r in rows} == COMPS
    # Batch 2: the customs base by origin and the finance scope view have no reported parts: blocked, never flagged
    unreported = {"ty.comp.us_customs_base_by_origin", "ty.comp.fs_by_scope",
         "ty.comp.fs_revenue_lines", "ty.comp.fs_cost_lines", "ty.comp.us_fin_contribution"}
    assert all(r["status"] == "blocked" for r in rows if r["composition_id"] in unreported)
    rows = [r for r in rows if r["composition_id"] not in unreported]
    assert all(r["status"] == "ok" and not r["missing_levels"] for r in rows), \
        [(r["composition_id"], r["missing_levels"], r["relative_difference"]) for r in rows]
    assert all(abs(r["relative_difference"]) < 1e-5 for r in rows)
    # the identities hold at the reported levels too; the two financing products are blocked, not flagged: the
    # contract and funding rates are not disclosed, so they have no level to compare
    ids = {r["identity_id"]: r for r in reconcile_identities(g, levels) if r["identity_id"] in IDENTITIES}
    blocked = {k for k, r in ids.items() if r["status"] == "blocked"}
    assert {"ty.id.fs_interest_income", "ty.id.fs_funding_interest", "ty.id.industrial_fcf"} <= blocked
    # Batch 2: the new arithmetic (duty, incentives, dealer days, the US module) has no reported terms: blocked, not flagged
    assert {"ty.id.us_duty", "ty.id.dealer_days", "ty.id.us_fin_income"} <= blocked
    assert all(r["status"] == "ok" for k, r in ids.items() if r["status"] != "blocked")


def test_fy2025_baselines_reconcile(g):
    """Pack round: a second dated year from the company's own FY2025 summary. The financial views reconcile; the unit
    views and unit identities are blocked (no FY2025 unit levels in the bundle), never flagged; the two financing
    identities are blocked by their rate alone, now that financial-services borrowings are observed."""
    levels = bundle_levels(json.loads(local("baselines_fy2025.json").read_text()))
    rows = {r["composition_id"]: r for r in toyota_rows(reconcile(g, levels))}
    money = {"ty.comp.reporting_segments", "ty.comp.regional_operating_income", "ty.comp.regional_external_revenue",
             "ty.comp.financial_services", "ty.comp.pretax_bridge", "ty.comp.net_income_bridge"}
    assert all(rows[c]["status"] == "ok" and abs(rows[c]["relative_difference"]) < 1e-5 for c in money)
    assert all(r["status"] in ("ok", "blocked") for r in rows.values())
    ids = {r["identity_id"]: r for r in reconcile_identities(g, levels) if r["identity_id"] in IDENTITIES}
    assert all(r["status"] == "blocked" for k, r in ids.items() if k != "ty.id.dividends")
    assert ids["ty.id.dividends"]["status"] == "ok"
    # Repair (Fix 5): the interest lines are not reported separately, so each is blocked by its own level and its rate
    assert set(ids["ty.id.fs_funding_interest"]["blocked_by"]) == {"toyota.fs_funding_interest", "toyota.fs_funding_cost_rate"}
    assert set(ids["ty.id.fs_interest_income"]["blocked_by"]) == {"toyota.fs_interest_income", "toyota.fs_customer_rate"}


def test_shares_roll_forward_between_dated_counts(g):
    """Pack round: shares outstanding is a stock-flow (buybacks out), checked between four dated share counts."""
    sf = g.stock_flows["ty.sf.shares"]
    assert sf.stock == "toyota.shares_outstanding" and sf.outflows == ["toyota.shares_repurchased"]
    link = g.interactions["ty_buyback_shares"]
    assert str(link.edge_type) == "stock_flow" and link.identity == "ty.sf.shares"
    rows = [r for r in reconcile_stock_flows(g, bundle_series(json.loads(local("shares.json").read_text())))
            if r["stock_flow_id"] == "ty.sf.shares"]
    assert len(rows) == 3 and all(r["status"] == "ok" and not r["missing_flows"] for r in rows), rows


def test_yen_channels_reconcile_to_the_disclosed_fx_impact(g):
    """Plan round (R13): per actual period, the transactional line is exactly its currency parts; the total FX effect is
    transactional plus translational; the transaction branch takes the dollar part and m29 the rest, so the two add to
    the disclosed total and nothing is counted twice. Imported inputs sit inside the net transactional line."""
    rows = json.loads(local("fx_reconciliation.json").read_text())["rows"]
    assert len(rows) == 8 and all(r["transactional_check"] for r in rows)
    assert all(abs(r["usd"] + r["m29_remainder"] - r["total_fx_effect"]) < 0.05 for r in rows)
    assert "R13" in g.interactions["ty_yen_imports"].note and not g.interactions["ty_yen_imports"].quantified


def path_pairs(g, pid: str) -> set[tuple[str, str]]:
    return {(g.interactions[s.interaction_id].source_id, g.interactions[s.interaction_id].target_id)
            for s in g.paths[pid].steps}


def test_pricing_and_mix_paths_are_operational(g):
    """Plan round: competitive conditions -> Toyota and dealer response -> realized price and volume -> regional profit;
    customer choice and supply availability -> mix and units -> automotive revenue. Units are not margins (R14)."""
    pr = path_pairs(g, "ty.path.pricing_competition")
    assert {("toyota.na_dealer_inventory", "toyota.na_incentive_per_unit"),
            ("toyota.na_incentive_per_unit", "toyota.na_revenue_per_vehicle"),
            ("toyota.north_america_operating_income", OP)} <= pr
    assert "R14" in g.paths["ty.path.pricing_competition"].description
    sup = path_pairs(g, "ty.path.supply_availability")
    assert ("toyota.electrified_supply_capacity", "toyota.hybrid_retail_units") in sup
    assert not g.interactions["ty_supply_hybrid"].quantified and "R14" in g.interactions["ty_supply_hybrid"].note


def test_financial_services_paths_and_subsidiary_scope(g):
    """Plan round: funding and refinancing -> financing economics; borrower conditions -> credit losses; used values ->
    lease outcomes; the US finance subsidiary connects to its consolidation scope but is never a composition part (R14)."""
    fs_oi = "toyota.financial_services_operating_income"
    assert ("toyota.fs_funding_cost_rate", "toyota.fs_funding_interest") in path_pairs(g, "ty.path.financing_funding")
    assert ("us_economy.gdp_growth", "toyota.fs_credit_loss_rate") in path_pairs(g, "ty.path.financing_borrower")
    assert ("toyota.fs_residual_value_losses", "toyota.fs_depreciation_other_costs") in path_pairs(g, "ty.path.financing_credit_residual")
    for pid in ("ty.path.financing_funding", "ty.path.financing_borrower", "ty.path.financing_credit_residual"):
        assert (fs_oi, OP) in path_pairs(g, pid)
    sub = "toyota.us_finance_subsidiary_earning_assets"
    scope = g.interactions["ty_us_finance_scope"]
    assert (scope.source_id, scope.target_id) == (sub, "toyota.fs_finance_receivables") and not scope.quantified
    assert "R14" in scope.note
    assert not any(sub in parts(c) for c in g.compositions.values())


def test_production_disruption_path_uses_dated_events(g):
    """Plan round: certification restriction -> available production -> deliveries and utilization, and recovery costs
    -> Japan operating income -> group. The production step is sized by definition; recovery costs one for one (model);
    the dated events with their measured loss are local."""
    pr = path_pairs(g, "ty.path.production_disruption")
    assert {("toyota.certification_shortfall", "toyota.japan_production"),
            ("toyota.certification_shortfall", "toyota.japan_units"),
            ("toyota.recovery_costs", "toyota.japan_operating_income"),
            ("toyota.japan_production", "toyota.japan_operating_income"),
            ("toyota.japan_operating_income", OP)} <= pr
    cut, cost = g.interactions["ty_cert_production"], g.interactions["ty_recovery_costs_oi"]
    assert cut.quantified and cut.forward.effect.mean() < 0 and cut.transition.evidence.magnitude == "documented"
    assert cost.quantified and cost.forward.effect.mean() < 0 and cost.transition.evidence.magnitude == "model"
    ev = {e["id"]: e for e in json.loads(local("events.json").read_text())["events"]}
    halt = ev["TY-EV-CERT-01"]
    assert halt["dates"]["announced"] < halt["dates"]["first_restart_production"] and halt["production_loss_units"] > 0


def test_history_is_standalone_and_bindings_name_their_formula(g):
    """R15: eight standalone quarters whose parts add to the fiscal years and to the group each quarter; walk components
    derived standalone from cumulative figures match the reported quarter; breaks are kept; each workbook binding
    records its version, location and the formula it feeds, and binds a level, never a displayed row as a sensitivity."""
    h = json.loads(local("history.json").read_text())
    for group in ("units_thousand", "revenue_bn_yen", "operating_income_bn_yen"):
        assert all(len(r["quarters"]) == 8 and r["sum_check"] for r in h[group].values()), group
    for check in h["checks"].values():
        assert all(abs(v) <= 0.5 for v in check.values())
    derived = [c for q in h["walk_components_bn_yen"].values() for c in q.values()]
    assert len(derived) >= 24 and all(c["derived_matches_reported"] for c in derived)
    assert len(h["breaks"]) >= 3
    binds = json.loads(local("bindings.json").read_text())
    assert all(x["workbook_version"] and x["cells"] and x["feeds"] and "not a sensitivity" in x["binding_kind"]
               for x in binds.values() if isinstance(x, dict))


def test_cash_and_capital_path_keeps_finance_funding_and_authorizations_apart(g):
    """Plan round: earnings -> industrial cash -> free cash flow (identity) -> liquid assets -> dividends (identity) and
    buybacks -> shares outstanding (stock-flow). The finance book is funded by its own debt; an authorization is not a
    purchase (R8). The dividend identity holds at both dated years; free cash flow is blocked (no reported level)."""
    cc = path_pairs(g, "ty.path.cash_capital")
    assert {("toyota.net_income", "toyota.industrial_operating_cash_flow"),
            ("toyota.industrial_operating_cash_flow", "toyota.industrial_free_cash_flow"),
            ("toyota.industrial_liquidity", "toyota.shares_repurchased"),
            ("toyota.shares_repurchased", "toyota.shares_outstanding")} <= cc
    assert not any("fs_" in s or "fs_" in t for s, t in cc)
    assert ("toyota.buyback_authorization", "toyota.shares_repurchased") in {
        (i.source_id, i.target_id) for i in g.active_interactions()}
    assert g.identities["ty.id.dividends"].form == "product"
    for name in ("baselines.json", "baselines_fy2025.json"):
        rows = {r["identity_id"]: r for r in reconcile_identities(g, bundle_levels(json.loads(local(name).read_text())))}
        assert rows["ty.id.dividends"]["status"] == "ok", name
        assert rows["ty.id.industrial_fcf"]["status"] == "blocked"


# -- validation cases (R16): through the internal model, the export, and the context an agent reads --------------------
def pose_case(client, tid: str, sid: str, delta: float, targets: list[str]) -> dict:
    from axelrod_wm.sim.scenario import thesis_from_spec

    ctl = client.app.state.axelrod.controller
    at = ctl.now.isoformat()
    spec = {"id": tid, "question": tid, "mode": "scaffolded", "horizon_days": 180, "targets": targets,
            "event": {"kind": "hypothetical", "event_type": "policy", "occurred_at": at,
                      "ops": [{"op": "change_value", "target": {"kind": "concrete", "subentity_id": sid}, "delta": delta,
                               "mode": "absolute", "persistence": "step", "intervention": True, "window_days": 180,
                               "at": at}]}}
    cov = ctl.pose_thesis(thesis_from_spec(spec, ctl.now)).coverage or {}
    return {"contributed": {c["interaction_id"] for c in cov.get("contributed", [])},
            "excluded": {c["interaction_id"] for c in cov.get("excluded", [])},
            "targets": {t["target"]: t for t in cov.get("targets") or []}}


def exported(client) -> dict:
    pack = v1.pack(client)
    return {r["axelrod"].get("interaction_id"): r for r in pack["company_edge_relationships"]}


def context_trace(client, start: str) -> dict:
    return v1.trace(client, "toyota", start, through_totals=True)


def test_validation_tariff_absorption_versus_price_recovery(client):
    """A higher US tariff rate: absorption is calculated (rate -> cost -> North America -> group), price recovery is
    direction only (reprice and incentives excluded as uncalibrated, never zero)."""
    fc = pose_case(client, "V-TARIFF", "us_vehicle_tariffs.effective_rate", 10.0,
                   ["toyota.us_tariff_cost", "toyota.north_america_operating_income", OP])
    assert {"ty_tariff_cost", "ty_tariff_absorb", "ty_reg_north_america_oi"} <= fc["contributed"]
    assert {"ty_tariff_reprice", "ty_tariff_incentives", "ty_tariff_resource", "ty_tariff_transfer"} <= fc["excluded"]
    assert fc["targets"][OP]["quantified_routes_through_own_steps"] >= 1
    rels = exported(client)
    assert rels["ty_tariff_absorb"]["axelrod"]["effect_sd_per_sd"] is not None
    assert rels["ty_tariff_reprice"]["axelrod"]["effect_sd_per_sd"] is None and rels["ty_tariff_reprice"]["axelrod"]["transition"]
    tr = context_trace(client, "us_vehicle_tariffs.effective_rate")
    assert tr["reaches_endpoint"]


def test_validation_financing_pressure(client):
    """Higher US funding rates: the financing path is traced to financial-services income and the group, every financing
    step direction only (the consolidated funding rate is not disclosed; the subsidiary's scenario is another basis)."""
    fc = pose_case(client, "V-FINANCING", "us_treasuries.yield_2y", 1.0,
                   ["toyota.fs_cost_of_financing", "toyota.financial_services_operating_income", OP])
    assert "ty_ust_funding" in fc["excluded"]
    assert fc["targets"]["toyota.financial_services_operating_income"]["quantified_routes"] == 0
    rels = exported(client)
    assert all(rels[i]["axelrod"]["transition"] for i in ("ty_ust_funding", "ty_funding_cost", "ty_us_finance_scope"))
    tr = context_trace(client, "us_treasuries.yield_2y")
    assert tr["reaches_endpoint"] and tr["routes"]


def test_validation_outside_the_cases_north_american_plant_stoppage(client):
    """A development no path was written for: a North American plant stoppage. It reaches imports by identity, the duty
    base, plant absorption and North America profit, and says which steps rest on unknown sizes."""
    fc = pose_case(client, "V-OUTSIDE", "toyota.north_america_production", -0.5,
                   ["toyota.na_import_units", "toyota.north_america_operating_income", OP])
    assert "ty_imports_na_production" in fc["contributed"]
    assert {"ty_na_production_to_oi", "ty_tariff_base"} <= fc["excluded"]
    assert fc["targets"]["toyota.na_import_units"]["quantified_routes"] >= 1
    tr = context_trace(client, "toyota.north_america_production")
    assert tr["reaches_endpoint"] and tr["routes"]


# -- delivery: export and API ---------------------------------------------------------------------------------------------
def test_new_objects_reach_the_export(client):
    pack = v1.pack(client)
    bridge = {b["composition_id"]: b for b in pack["domain_specific_support_objects"]["financial_bridge"]}
    assert COMPS <= set(bridge)
    assert bridge["ty.comp.reporting_segments"]["overlaps_other_views"]
    paths = [p for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction"
             and p["primary_company_id"] == "N_TOYOTA_MOTOR"]
    assert {p["axelrod"]["path_id"] for p in paths} == PATHS
    rels = {r["axelrod"].get("interaction_id"): r for r in pack["company_edge_relationships"]}
    t = rels["ty_tariff_reprice"]
    assert t["qualification_status"] == "uncalibrated" and t["axelrod"]["effect_sd_per_sd"] is None
    assert t["axelrod"]["transition"]["sign"] == "+" and t["invalidator"]
    assert rels["ty_tariff_cost"]["axelrod"]["effect_sd_per_sd"] is not None
    assert rels["s44"]["status"] == "represented_uncalibrated"
    assert rels["ty_seg_automotive_operating_income"]["dependency_type"] == "accounting_identity"


def test_new_objects_reach_the_api(client):
    ids = "toyota.us_tariff_cost,toyota.automotive_operating_income,toyota.japan_export_units"
    body = v1.graph(client, ids)
    got = {a["id"] for e in body["entities"] for a in e["attributes"]}
    assert set(ids.split(",")) <= got
    assert any(r["id"] == "ty_tariff_cost" for r in body["relationships"])
    view = v1.construction(client, "toyota")
    assert len(view["paths"]) == len(PATHS) and len(view["compositions"]) == len(COMPS) and view["problems"] == []
    steps = {s["relationship_id"]: s for p in view["paths"] if p["id"] == "ty.path.tariffs_sourcing" for s in p["steps"]}
    step = steps["ty_tariff_reprice"]
    # uncalibrated: a sign and no size (null, never 0)
    assert step["calibration"] == "uncalibrated" and step["effect"] is None and step["sign"] in ("positive", "negative")
    assert steps["ty_tariff_cost"]["calibration"] == "calibrated" and steps["ty_tariff_cost"]["effect"] is not None
    md = v1.construction_markdown(client, "toyota")
    assert "### Tariffs and sourcing" in md and "Unresolved inputs" in md
    tr = v1.trace(client, "toyota", "toyota.japan_production")
    assert tr["reaches_endpoint"]


# -- Batch 2 (W6): every active Toyota link carries its retrieval profile in the export and in the v1 reads ---------------
PROFILE = {"exposure", "unit", "date", "hedge", "pass_through", "financial_endpoint", "calculation", "source"}


def test_every_active_link_carries_its_retrieval_profile(client, g):
    own = set(g.entities["toyota"].subentity_ids)
    mine = {i.id for i in g.active_interactions() if (i.source_id in own or i.target_id in own) and i.transition is not None}
    rels = {r["axelrod"].get("interaction_id"): r for r in v1.pack(client)["company_edge_relationships"]}
    exported = {k for k in mine if k in rels}
    assert exported and all(PROFILE <= set(rels[k]["axelrod"]["transition_profile"]) for k in exported)
    # the profile never calls an unsized link zero, and states unknown hedging as unknown
    reprice = rels["ty_tariff_reprice"]["axelrod"]["transition_profile"]
    assert reprice["calculation"].startswith("unsized") and reprice["hedge"] == "unknown"
    assert "toyota.operating_profit" in reprice["financial_endpoint"]
    body = v1.graph(client, "toyota.us_tariff_cost")
    r = next(x for x in body["relationships"] if x["id"] == "ty_tariff_cost")
    assert PROFILE <= set(r["profile"]) and r["profile"]["source"]
