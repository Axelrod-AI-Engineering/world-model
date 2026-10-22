"""A forecast's calculation coverage (inference/task.forecast_coverage, channel_contributions; Oct 18): the quantified
links that contribute, the reached links that carry no size and why, the inputs that block them, and per target the
share of the reached routes that are fully quantified. Synthetic world (tests/unit/model/test_business_construction)."""

from __future__ import annotations

from types import SimpleNamespace as NS

import numpy as np
import pytest

from axelrod_wm.inference.task import channel_contributions, forecast_coverage
from tests.unit.model.test_business_construction import acme_construction, build, world


@pytest.fixture
def graph(tmp_path):
    return build(world(tmp_path, acme_construction()), tmp_path)


REACHED = {"macro.tariff", "acme.landed_cost", "acme.na", "acme.auto"}


def test_coverage_splits_reached_links_into_contributed_and_excluded(graph):
    cov = forecast_coverage(graph, ["macro.tariff"], REACHED, ["acme.profit", "acme.home"],
                            {"t2": -0.2, "a4": 0.05}, live={"t2", "a4"}, absent={"t3"})
    assert [(r["interaction_id"], r["contribution_sd"]) for r in cov["contributed"]] == [("t2", -0.2), ("a4", 0.05)]
    assert cov["contributed"][1]["edge_type"] == "accounting"
    ex = {r["interaction_id"]: r for r in cov["excluded"]}
    assert ex["t1"]["reason"] == "uncalibrated" and ex["t1"]["sign"] == "+"
    assert ex["t1"]["mechanism"].startswith("a tariff raises") and ex["t1"]["unresolved"] == ["eligible import volume"]
    assert ex["t3"]["reason"] == "absent_in_every_scenario" and ex["t3"]["sign"] == "-" and ex["t3"]["unresolved"] == []
    assert ex["a0"]["reason"] == "outside_the_forecast_networks" and ex["a0"]["mechanism"] == "adds to"
    assert [(b["input"], b["status"], b["interaction_ids"]) for b in cov["blocking_inputs"]] == [
        ("eligible import volume", "not_yet_reviewed", ["t1"])]
    # every route from the tariff passes through the uncalibrated t1: none is fully quantified
    assert cov["targets"] == [
        {"target": "acme.profit", "routes": 2, "quantified_routes": 0, "share_quantified": 0.0,
         "quantified_routes_through_own_steps": 0, "quantified_routes_through_summary_links_only": 0, "own_steps": 4,
         "own_steps_quantified": 2, "share_own_steps_quantified": 0.5,
         "own_steps_unquantified": ["a0", "t3"], "truncated": False},
        {"target": "acme.home", "routes": 0, "quantified_routes": 0, "share_quantified": None,
         "quantified_routes_through_own_steps": 0, "quantified_routes_through_summary_links_only": 0, "own_steps": 0,
         "own_steps_quantified": 0, "share_own_steps_quantified": None, "own_steps_unquantified": [],
         "truncated": False}]
    assert cov["summary"] == {"contributed": 2, "excluded": 3, "blocking_inputs": 1, "excluded_by_reason": {
        "absent_in_every_scenario": 1, "outside_the_forecast_networks": 1, "uncalibrated": 1}}
    assert cov["max_route_depth"] == 6


def test_a_shock_past_the_uncalibrated_link_has_quantified_routes(graph):
    cov = forecast_coverage(graph, ["macro.tariff", "acme.landed_cost"], REACHED, ["acme.profit"], {},
                            live={"t2", "a4"}, absent=set())
    row = cov["targets"][0]
    assert {k: row[k] for k in ("routes", "quantified_routes", "share_quantified", "truncated")} == {
        "routes": 4, "quantified_routes": 1, "share_quantified": 0.25, "truncated": False}
    assert row["quantified_routes_through_own_steps"] == 1 and row["quantified_routes_through_summary_links_only"] == 0


def test_own_construction_steps_are_counted_apart_from_summary_routes(graph):
    """A quantified macro -> total summary link must not hide that the company's own steps are unsized."""
    from axelrod_wm.model.interaction import Interaction

    g = graph.model_copy(deep=True)
    g.interactions["m1"] = Interaction(**{**g.interactions["t2"].model_dump(), "id": "m1", "source_id": "macro.tariff",
                                          "target_id": "acme.profit", "transition": None, "internal": False})
    cov = forecast_coverage(g, ["macro.tariff"], REACHED, ["acme.profit"], {}, live={"m1"}, absent=set())
    row = cov["targets"][0]
    assert row["routes"] == 3 and row["quantified_routes"] == 1 and row["share_quantified"] == pytest.approx(0.3333)
    assert row["quantified_routes_through_summary_links_only"] == 1 and row["quantified_routes_through_own_steps"] == 0
    assert row["own_steps"] == 4 and row["own_steps_quantified"] == 0 and row["share_own_steps_quantified"] == 0.0
    ghost = forecast_coverage(g, ["macro.tariff"], REACHED, ["ghost.x"], {}, live=set(), absent=set())
    assert ghost["targets"][0]["own_steps"] == 0
    assert cov["contributed"][0]["contribution_sd"] == 0.0                   # ran, but nothing recorded for it


def test_an_unsigned_link_route_depth_and_the_walking_budget(graph):
    g = graph.model_copy(deep=True)
    g.interactions["t1"] = g.interactions["t1"].model_copy(update={"transition": None})
    cov = forecast_coverage(g, ["macro.tariff"], {"macro.tariff"}, ["acme.profit"], {}, set(), set(), max_depth=2)
    assert cov["excluded"] == [{"interaction_id": "t1", "source": "macro.tariff", "target": "acme.landed_cost",
                                "reason": "uncalibrated", "sign": None, "mechanism": "raises", "unresolved": []}]
    assert cov["blocking_inputs"] == [] and cov["targets"][0]["routes"] == 0    # profit is three links away
    cut = forecast_coverage(graph, ["macro.tariff"], REACHED, ["acme.profit"], {}, set(), set(), budget=2)
    assert cut["targets"][0]["truncated"] is True


def test_channel_contributions_weigh_scenarios_and_skip_channels_forced_off():
    def run(contrib):
        return NS(horizon_days=1, channels=[NS(channel_key=k, forced=f) for k, f in
                                            (("t2", None), ("t3", False), ("b1:rev", True))],
                  contrib_of=lambda k: np.array(contrib.get(k, [[0.0, 0.0]] * 3)))

    on = run({"t2": [[0, 1.0], [0, 2.0], [0, 3.0]], "b1:rev": [[0, 0.5]] * 3})
    off = run({"t2": [[0, 1.0]] * 3})
    scen = [NS(id="s1", weight=0.75), NS(id="s2", weight=0.25)]
    contrib, live, absent = channel_contributions(scen, {"s1": on, "s2": on}, {"s1": off, "s2": off})
    assert contrib == {"t2": pytest.approx(1.0), "b1": pytest.approx(0.5)}
    assert live == {"t2", "b1"} and absent == {"t3"}
    assert channel_contributions([], {}, {}) == ({}, set(), set())
