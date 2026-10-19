"""A company's construction, readable (context/construction.py), traced, exported to the v4.1.4 pack, and what a
forecast says about the uncalibrated links it reaches (inference/task.unquantified_links)."""

from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from axelrod_wm.context.construction import construction_view, to_markdown, trace
from axelrod_wm.inference.task import unquantified_links
from tests.unit.model.test_business_construction import TWO_DRIVING, acme_construction, build, world


@pytest.fixture
def graph(tmp_path):
    return build(world(tmp_path, acme_construction()), tmp_path)


def test_the_view_holds_compositions_paths_transitions_and_link_counts(graph):
    v = construction_view(graph, "acme")
    assert v["name"] == "Acme" and {x["id"] for x in v["values"]} >= {"acme.auto", "acme.landed_cost"}
    auto = next(x for x in v["values"] if x["id"] == "acme.auto")
    assert auto["view"] == "reporting_segments" and auto["unit"] == "bn/yr" and auto["mean"] == pytest.approx(10.0)
    assert [c["id"] for c in v["compositions"]] == ["C1", "C2"] and v["compositions"][0]["eliminations"] == "acme.elims"
    p = v["paths"][0]
    assert p["id"] == "P1" and [s["interaction_id"] for s in p["steps"]] == ["t1", "t2", "t3", "a4"]
    t1 = p["steps"][0]
    assert t1["calibration"] == "uncalibrated" and t1["effect"] is None and t1["magnitude"] == "unknown (uncalibrated)"
    assert t1["sign"] == "+" and t1["transition"]["breaker"] == "local sourcing"
    assert p["steps"][3]["edge_type"] == "accounting" and p["steps"][3]["effect"] == pytest.approx(0.33)
    assert p["uncalibrated_steps"] == 1 and p["steps_without_transition"] == 2
    assert v["links"] == {"total": 8, "calibrated": 7, "uncalibrated": 1, "accounting": 5, "identity": 0,
                          "stock_flow": 0, "state_dependent": 0, "with_transition": 2}
    assert v["problems"] == [TWO_DRIVING]
    assert [c["role"] for c in v["compositions"]] == ["driving", "driving"]
    assert v["identities"] == v["stock_flows"] == v["matrices"] == []
    with pytest.raises(KeyError):
        construction_view(graph, "nobody")


def test_the_view_lists_the_companys_own_problems(graph):
    g = graph.model_copy(deep=True)
    g.interactions["t1"] = g.interactions["t1"].model_copy(update={"transition": None})
    g.paths["P1"].steps[0].interaction_id = "t1"
    assert construction_view(g, "acme")["problems"] == [TWO_DRIVING]   # t1 is not acme's id: it shows by its path
    g.compositions["C1"].members.append("acme.landed_cost")
    assert any("C1" in p for p in construction_view(g, "acme")["problems"])


def test_a_level_without_a_mean_still_shows_its_unit(graph):
    g = graph.model_copy(deep=True)
    sub = g.subentities["acme.auto"]
    g.subentities["acme.auto"] = sub.model_copy(update={"posterior": NS(mean=lambda: 1 / 0)})
    auto = next(x for x in construction_view(g, "acme")["values"] if x["id"] == "acme.auto")
    assert auto["mean"] is None and auto["unit"] == "bn/yr"


def test_the_readable_view(graph):
    md = to_markdown(construction_view(graph, "acme"))
    assert md.startswith("# Acme: business construction")
    assert "8 links touch its values: 7 calibrated, 1 uncalibrated" in md
    assert "### reporting segments: segment operating income (bn/yr)" in md and "| Eliminations: elims | `acme.elims` |" in md
    assert "never added to it." in md and "overlaps C1" in md and "carry changes into it" in md
    assert "### Tariffs and sourcing" in md and "tariff → landed cost? → [regional] na → [segment] auto → profit" in md
    assert "(? marks a step whose size is unknown)" in md
    assert "| 1 `t1` | a tariff raises the landed cost of imported vehicles (importer) |" in md
    assert "onset at customs entry; build unknown" in md and "documented / documented / unknown / unknown" in md
    assert "| 4 `a4` | na adds to profit | unknown | unknown | unknown | unknown | unknown | +0.33 sd/sd (accounting) |" in md
    assert "Unresolved inputs: eligible import volume (not yet reviewed)." in md and "## Problems" in md
    assert "## Identities" not in md and "## Stocks and flows" not in md and "## Matrix" not in md


def test_the_readable_view_of_bare_structure():
    view = {"name": "X", "values": [], "links": {"total": 0, "calibrated": 0, "uncalibrated": 0, "accounting": 0,
                                                  "identity": 0, "stock_flow": 0, "state_dependent": 0,
                                                  "with_transition": 0},
            "compositions": [{"id": "C", "view": "products", "basis": "b", "unit": "u", "period": "FY", "additive": False,
                              "total": "x.t", "members": ["x.a"], "residual": "x.r", "eliminations": None, "note": "",
                              "role": "non_additive"}],
            "identities": [], "stock_flows": [], "matrices": [],
            "paths": [{"id": "P", "name": "Empty", "trigger": "t", "endpoint": "x.t", "description": "why",
                       "steps": [], "uncalibrated_steps": 0}], "problems": ["a problem"]}
    md = to_markdown(view)
    assert "(u, FY)" in md and "| Residual: x.r | `x.r` |" in md and "A non-additive view" in md
    assert "why" in md and "## Problems\n\n- a problem" in md


def test_a_trace_follows_every_link_and_says_where_it_stops(graph):
    t = trace(graph, "macro.tariff", "acme")
    assert t["reaches_endpoint"] and t["stops"] == []
    routes = [[s["interaction_id"] for s in r["steps"]] for r in t["routes"]]
    assert ["t1", "t2", "a4"] in routes and ["t1", "t3", "a0"] in routes
    first = next(r for r in t["routes"] if [s["interaction_id"] for s in r["steps"]] == ["t1", "t2", "a4"])
    assert first["uncalibrated_steps"] == ["t1"] and first["steps_without_transition"] == ["a4"]
    with pytest.raises(KeyError):
        trace(graph, "macro.none", "acme")


def test_a_trace_that_stops_short_or_never_reaches_the_company(graph):
    g = graph.model_copy(deep=True)
    for iid in ("a0", "a4"):
        g.interactions[iid] = g.interactions[iid].model_copy(update={"retired_at": g.interactions[iid].created_at})
    t = trace(g, "macro.tariff", "acme")
    assert not t["reaches_endpoint"] and t["stops"] == ["acme.auto", "acme.na"]
    assert trace(g, "acme.profit", "acme")["routes"] == []                  # nothing leads on from the total
    assert trace(graph, "macro.tariff", "ghost")["routes"] == []            # no such company: nothing of it is reached
    deep = trace(graph, "macro.tariff", "acme", max_depth=1)
    assert deep["routes"] and all(len(r["steps"]) == 1 for r in deep["routes"])


def test_a_forecast_names_the_uncalibrated_links_it_reaches(graph):
    rows = unquantified_links(graph, {"macro.tariff"}, [NS(subentity_id="macro.tariff", peak=0.8)])
    assert rows == [{"interaction_id": "t1", "source": "macro.tariff", "target": "acme.landed_cost", "sign": "+",
                     "mechanism": "a tariff raises the landed cost of imported vehicles", "source_peak": 0.8,
                     "downstream": ["acme.auto", "acme.landed_cost", "acme.na", "acme.profit"]}]
    assert unquantified_links(graph, {"acme.profit"}, []) == []              # not reached: not listed
    g = graph.model_copy(deep=True)
    g.interactions["t1"] = g.interactions["t1"].model_copy(update={"transition": None})
    row = unquantified_links(g, {"macro.tariff"}, [])[0]
    assert row["sign"] is None and row["mechanism"] == "raises" and row["source_peak"] == 0.0


def test_other_companies_paths_stay_out_and_a_bare_company_has_no_sections(graph):
    from axelrod_wm.model.construction import NamedPath, PathStep

    g = graph.model_copy(deep=True)
    g.paths["Z"] = NamedPath(id="Z", name="macro", entity_id="macro", trigger="t", endpoint="acme.landed_cost",
                             steps=[PathStep(interaction_id="t1")])
    assert [p["id"] for p in construction_view(g, "acme")["paths"]] == ["P1"]
    md = to_markdown(construction_view(g, "macro"))
    assert "## Business composition" not in md and "## Operating and financial paths" in md
    g.paths.clear()
    assert "## Operating and financial paths" not in to_markdown(construction_view(g, "macro"))

