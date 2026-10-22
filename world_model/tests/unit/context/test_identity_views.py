"""Identities, stock-flows, matrices, reconciling views and state-dependent links (Oct 18) where people and agents read
them: the readable view, the trace (which may go on through totals), the import overlap guard, the v4.1.4 export, and
the check script's tables. Synthetic bank (tests/unit/model/test_identities.py)."""

from __future__ import annotations

import importlib.util
from datetime import date

import pytest

from axelrod_wm.context.construction import construction_view, state_text, to_markdown, trace
from axelrod_wm.context.v4 import domain_pack, identity_ref, pack_config
from axelrod_wm.engine.engine import Engine
from axelrod_wm.engine.initialize import ConstructionSpec, Initializer, load_vocabulary
from axelrod_wm.intake.bundle import ImportItem
from axelrod_wm.intake.overlap import overlap_guard, overlapping_views, views_by_part
from axelrod_wm.model.construction import Threshold
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.trace import NullTracer
from tests.conftest import make_config
from tests.unit.engine.test_cov_initialize import _taxonomy
from tests.unit.model.test_business_construction import ATTRS, world
from tests.unit.model.test_identities import bank
from tests.where import SCRIPTS


def engine(tmp_path):
    tax = _taxonomy(tmp_path, attrs=ATTRS, objects={"root": "gen:obj:root", "nodes": [
        {"id": "gen:obj:root", "name": "Object", "parent": None}]})
    eng = Engine(make_config(), MemoryBackend(), NullTracer(), vocab=load_vocabulary(tax))
    Initializer(eng).construct(ConstructionSpec.load(world(tmp_path, bank()), tax), tax, start=date(2024, 1, 1),
                               vocab=load_vocabulary(tax))
    return eng


@pytest.fixture
def eng(tmp_path):
    return engine(tmp_path)


def test_the_view_lists_identities_stock_flows_matrices_and_states(eng):
    g = eng.wm.graph
    v = construction_view(g, "acme")
    ids = {x["id"]: x for x in v["identities"]}
    assert ids["acme.id.cet1"]["formula"] == "cet1 = 100 x capital / rwa"
    assert [(t["value"], t["role"], t["weight"]) for t in ids["acme.id.cet1"]["terms"]] == [
        ("acme.capital", "numerator", 2.0), ("acme.rwa", "denominator", -1.2)]
    (sf,) = v["stock_flows"]
    assert [(f["role"], f["weight"], f["interaction_id"]) for f in sf["flows"]] == [
        ("inflow", 0.2, "w-income"), ("outflow", -0.1, "acme.sf.capital:acme.dividends")]
    (m,) = v["matrices"]
    assert m["passive"] == "L" and m["cells"][0] == {"row": "acme.seg_a", "column": "acme.line_x", "value": "acme.a_x"}
    assert {c["id"]: c["role"] for c in v["compositions"]} == {"G": "reconciling", "L": "reconciling", "R": "driving"}
    lk = v["links"]
    assert (lk["identity"], lk["stock_flow"], lk["state_dependent"]) == (6, 2, 3)
    assert v["problems"] == []
    h = g.model_copy(deep=True)
    rid = "acme.id.cet1:acme.rwa"
    h.interactions[rid] = h.interactions[rid].model_copy(update={"retired_at": h.interactions[rid].created_at})
    terms = next(x for x in construction_view(h, "acme")["identities"] if x["id"] == "acme.id.cet1")["terms"]
    assert terms[1]["weight"] is None and terms[1]["interaction_id"] is None


def test_the_readable_view_shows_formulas_roll_forwards_grids_and_states(eng):
    g = eng.wm.graph
    v = construction_view(g, "acme")
    md = to_markdown(v)
    assert "6 identity, 2 stock-flow; 3 state-dependent" in md
    assert "## Identities" in md and "| `acme.id.cet1` (ratio) | cet1 = 100 x capital / rwa |" in md
    assert "capital (numerator, +2.000); rwa (denominator, -1.200)" in md and "bn = bn x % x 0.01" in md
    assert "## Stocks and flows" in md and "capital (closing) = capital (opening) + income - dividends, per 91 days" in md
    assert "## Matrix `M`: R x L (the rows drive the total; L reconciles)" in md
    assert "| seg a | `acme.a_x` | `acme.a_y` |" in md and "A reconciling view" in md
    v["matrices"][0]["cells"], v["matrices"][0]["note"] = [{"row": "r", "column": "c", "value": "v"}], "a note"
    v["matrices"].append({**v["matrices"][0], "id": "N", "cells": [], "note": ""})
    v["stock_flows"][0]["flows"][0]["weight"] = None
    md = to_markdown(v)
    assert "| r | `v` |" in md and "a note" in md and "No cells are given" in md and "(inflow, missing link)" in md
    # a path through a state-dependent and a stock-flow step says how each computes
    v["paths"] = [{"id": "P", "name": "Capital", "trigger": "t", "endpoint": "acme.cet1", "description": "",
                   "uncalibrated_steps": 0,
                   "steps": [s for s in [_step(g, "s-buyback"), _step(g, "w-income"), _step(g, "w-assets")]]}]
    md = to_markdown(v)
    assert "+0.50 sd/sd; acts only while cet1 is above 11.5" in md
    assert "+0.20 sd/sd (stock-flow, accumulates per 91 days)" in md and "+1.00 sd/sd (identity)" in md


def _step(g, iid):
    from axelrod_wm.context.construction import _step as step

    return step(g, g.interactions[iid], None)


def test_state_text_in_words(eng):
    g = eng.wm.graph
    names = {k: v.name for k, v in g.subentities.items()}
    assert state_text(g.interactions["s-beta"], names) == "+0.60 sd/sd while tariff is above its construction level, " \
                                                          "+0.30 below"
    assert state_text(g.interactions["s-reinvest"], names) == "sign as stated while nim is below 2, reversed otherwise"
    i = g.interactions["s-beta"]
    j = i.model_copy(update={"state": i.state.model_copy(update={
        "asymmetry": i.state.asymmetry.model_copy(update={"at": 3.0, "value": "acme.nim"}),
        "threshold": Threshold(value="acme.cet1", below=14.0)})})
    assert state_text(j, names) == "+0.60 sd/sd while nim is above 3, +0.30 below; acts only while cet1 is below 14"
    assert state_text(g.interactions["w-assets"], names) == ""


def test_a_trace_may_go_on_through_the_totals_it_reaches(eng):
    g = eng.wm.graph
    stop = trace(g, "acme.income", "acme")
    assert stop["through_totals"] is False
    assert [[s["interaction_id"] for s in r["steps"]] for r in stop["routes"]] == [["w-income"]]
    on = trace(g, "acme.income", "acme", through_totals=True)
    routes = {tuple(s["interaction_id"] for s in r["steps"]): r for r in on["routes"]}
    assert ("w-income",) in routes and ("w-income", "acme.id.cet1:acme.capital") in routes
    deep = routes[("w-income", "acme.id.cet1:acme.capital")]
    assert deep["passes"] == ["acme.capital"] and deep["ends_at"] == "acme.cet1" and deep["reaches_endpoint"]
    assert ("w-income", "s-buyback") in routes and routes[("w-income", "s-buyback")]["reaches_endpoint"] is False
    short = trace(g, "acme.income", "acme", max_depth=1, through_totals=True)
    assert [[s["interaction_id"] for s in r["steps"]] for r in short["routes"]] == [["w-income"]]


def item(iid, *values, at="2024-01-15T09:00:00Z"):
    return ImportItem.model_validate({"id": iid, "published_at": at, "source": "s", "headline": "h",
                                      "signals": [{"type": "observe", "value_of": v, "value": 1.0} for v in values]})


def test_a_results_day_reporting_every_view_folds_whole(eng):
    """Segments, lines (a matrix's passive view) and regions (drives: false) of one total, on one day: nothing drops."""
    g = eng.wm.graph
    assert views_by_part(g) == {"acme.seg_a": [("acme.rev", "R")], "acme.seg_b": [("acme.rev", "R")]}
    assert overlapping_views(g) == {}
    skip, warnings = overlap_guard(g, [item("A", "acme.seg_a", "acme.line_x", "acme.dom"),
                                       item("B", "acme.seg_b", "acme.line_y", "acme.intl", "acme.a_x")])
    assert skip == {} and warnings == []
    h = g.model_copy(deep=True)
    h.compositions["G"] = h.compositions["G"].model_copy(update={"drives": True})
    skip, warnings = overlap_guard(h, [item("A", "acme.seg_a", "acme.seg_b", "acme.dom")])
    assert warnings[0]["compositions"] == ["G", "R"] and skip == {"A": {2: skip["A"][2]}}     # a second driving view


def test_the_export_carries_formulas_roles_and_states(eng):
    pack = domain_pack(eng.wm, eng.ltm, pc=pack_config("acme_demo", "Acme"), book=["acme"], version=1, state_hash=None)
    sup = pack["domain_specific_support_objects"]
    ids = {x["identity_id"]: x for x in sup["financial_identities"]}
    assert ids["acme.id.nii"]["formula"] == "nii = 0.01 x assets x nim" and ids["acme.id.nii"]["form"] == "product"
    assert ids["acme.id.nii"]["reconciliation"]["status"] in ("ok", "flag")
    assert ids["acme.sf.capital"]["form"] == "stock_flow" and ids["acme.sf.capital"]["period_days"] == 91
    assert ids["acme.sf.capital"]["terms"][1] == {"metric": "acme.dividends", "role": "outflow", "exponent_or_sign": -1}
    (m,) = sup["financial_matrices"]
    assert (m["driving"], m["reconciling"]) == ("R", "L") and m["reconciliation"]["status"] == "ok"
    bridge = {b["composition_id"]: b for b in sup["financial_bridge"]}
    assert (bridge["R"]["role"], bridge["L"]["role"], bridge["G"]["role"]) == ("driving", "reconciling", "reconciling")
    assert bridge["L"]["matrix_id"] == "M" and bridge["G"]["matrix_id"] is None
    rels = [r for r in pack["company_edge_relationships"]]
    by = {r["axelrod"]["interaction_id"]: r for r in rels}
    assert by["w-assets"]["dependency_type"] == "accounting_identity"
    assert by["w-assets"]["axelrod"]["identity"]["formula"] == "nii = 0.01 x assets x nim"
    assert by["w-income"]["axelrod"]["identity"]["role"] == "inflow"
    assert "baseline accumulation" in by["w-income"]["axelrod"]["identity"]["computation"]
    assert by["s-buyback"]["axelrod"]["state"]["threshold"] == {"value": "acme.cet1", "above": 11.5}
    assert "acts only while" in by["s-buyback"]["axelrod"]["state"]["in_words"]
    assert by["s-buyback"]["axelrod"]["note"] == "buybacks stop below the requirement"
    assert "note" not in by["w-assets"]["axelrod"]
    assert any("stock-flow" in x["concept"] for x in sup["schema_gaps"])


def test_dormant_paths_and_proxy_series(eng):
    from axelrod_wm.model.construction import NamedPath, PathStep

    g = eng.wm.graph
    g.paths["P"] = NamedPath(id="P", name="Sell-down", entity_id="acme", trigger="t", endpoint="acme.capital",
                             steps=[PathStep(interaction_id="w-income")], active_when="the state stake is above zero")
    g.subentities["acme.dom"] = g.subentities["acme.dom"].model_copy(update={"features": {"proxy_for": "swap 10y"}})
    v = construction_view(g, "acme")
    assert v["paths"][0]["active_when"] == "the state stake is above zero"
    assert next(x for x in v["attributes"] if x["id"] == "acme.dom")["proxy_for"] == "swap 10y"
    assert "**Dormant unless:** the state stake is above zero." in to_markdown(v)
    pack = domain_pack(eng.wm, eng.ltm, pc=pack_config("acme_demo", "Acme"), book=["acme"], version=1, state_hash=None)
    path = next(p for p in pack["transmission_paths"] if p.get("path_kind") == "business_construction")
    assert path["axelrod"]["active_when"] == "the state stake is above zero"


def test_values_whose_head_word_is_a_common_word(eng):
    from axelrod_wm.context.construction import keyword_risks

    g = eng.wm.graph
    assert keyword_risks(g, "acme") == []
    sub = g.subentities["acme.dom"]
    g.subentities["acme.dom"] = sub.model_copy(update={"name": "Acme securities held (AFS)"})
    g.subentities["acme.ghost"] = sub.model_copy(update={"id": "acme.securities_held"})
    g.entities["acme"].subentity_ids.extend(["acme.securities_held", "acme.missing"])
    g.subentities["acme.securities_held"] = g.subentities.pop("acme.ghost")
    assert keyword_risks(g, "acme") == [
        {"value_id": "acme.dom", "name": "Acme securities held (AFS)", "keywords": ["held"]},
        {"value_id": "acme.securities_held", "name": "dom", "keywords": ["held"]}]


def test_an_identity_reference_to_a_missing_object(eng):
    g = eng.wm.graph.model_copy(deep=True)
    g.identities.clear()
    g.stock_flows.clear()
    assert identity_ref(g, g.interactions["w-assets"]) == {"identity_id": "acme.id.nii", "form": None, "formula": None}
    assert identity_ref(g, g.interactions["w-income"]) == {"identity_id": "acme.sf.capital", "form": "stock_flow",
                                                            "formula": None}
    out = identity_ref(eng.wm.graph, eng.wm.graph.interactions["acme.sf.capital:acme.dividends"])
    assert out["role"] == "outflow"


def _check():
    spec = importlib.util.spec_from_file_location("check_script", SCRIPTS / "construction" / "check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_check_scripts_identity_matrix_and_roll_forward_tables(eng, capsys):
    from axelrod_wm.model.construction import (
        model_levels,
        reconcile_identities,
        reconcile_matrices,
        reconcile_stock_flows,
    )

    check = _check()
    g = eng.wm.graph
    lv = model_levels(g, "median") | {"acme.nim": 25.0}
    assert check.print_identities([], "x") == check.print_matrices([], "x") == check.print_stock_flows([], "x") == 0
    assert check.print_identities(reconcile_identities(g, lv) + reconcile_identities(g, {})[:1], "the levels") == 1
    out = capsys.readouterr().out
    assert "FLAG  nii = 0.01 x assets x nim" in out and "no level: acme.cet1" in out and "BLOCKED" in out
    assert check.print_matrices(reconcile_matrices(g, lv | {"acme.seg_a": 9.0}), "the levels") == 1
    out = capsys.readouterr().out
    assert "M: FLAG" in out and "row acme.seg_a" in out
    h = g.model_copy(deep=True)
    h.matrices["M"] = h.matrices["M"].model_copy(update={"cells": {}})
    check.print_matrices(reconcile_matrices(h, lv), "x")
    assert "(incomplete: acme.seg_a" in capsys.readouterr().out
    rows = reconcile_stock_flows(g, {"acme.capital": [("a", 12.0), ("b", 13.0)], "acme.income": [("b", 1.0)]})
    assert check.print_stock_flows(rows, "b.json") == 0                     # blocked by a missing flow, not a flag
    out = capsys.readouterr().out
    assert "a -> b  opening 12, closing 13, implied 13" in out and "no flow: acme.dividends" in out


def test_the_bundle_check_names_totals_with_two_driving_views(eng):
    spec = importlib.util.spec_from_file_location("bundles_script", SCRIPTS / "imports" / "bundles.py")
    bundles = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bundles)
    g = eng.wm.graph
    items = [item("A", "acme.seg_a", "acme.dom")]
    assert bundles.driving_view_problems(g, items) == []
    h = g.model_copy(deep=True)
    h.compositions["G"] = h.compositions["G"].model_copy(update={"drives": True})
    assert bundles.driving_view_problems(h, items) == [
        "acme.rev has 2 driving views (G, R) and the bundle observes their parts; mark all but one `drives: false` so "
        "it imports whole"]
    assert bundles.driving_view_problems(h, [item("B", "acme.nim")]) == []
