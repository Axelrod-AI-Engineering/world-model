"""The overlapping-views guard (intake/overlap.py): parts of two additive views of one total, observed in one item or
one day, are not all folded; the import preview and the import itself apply it (sim/imports.py)."""

from __future__ import annotations

import pytest

from axelrod_wm.control.updates import UpdateState
from axelrod_wm.intake.bundle import ImportItem, market_event_of, translate_item
from axelrod_wm.intake.overlap import RULE, overlap_guard, overlapping_views, views_by_part
from axelrod_wm.model.construction import Composition
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.imports import ImportRunner
from axelrod_wm.sim.scenario import ScenarioScript
from axelrod_wm.trace import RecordingTracer
from tests.unit.engine.test_cov_initialize import _taxonomy
from tests.unit.model.test_business_construction import ATTRS, _s, acme_construction, build, world

DAY = "2024-01-15T09:00:00Z"


def item(iid, *values, at=DAY, moves=(), extra=()):
    sigs = [{"type": "observe", "value_of": v, "value": 1.0} for v in values]
    sigs += [{"type": "move", "value_of": v, "delta": 0.1, "mode": "relative"} for v in moves]
    sigs += list(extra)
    return ImportItem.model_validate({"id": iid, "published_at": at, "source": "s", "headline": f"h {iid}",
                                      "signals": sigs})


@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("acme")
    return build(world(tmp, acme_construction()), tmp)


def test_the_views_of_each_total(graph):
    parts = views_by_part(graph)
    assert parts["acme.auto"] == [("acme.profit", "C1")] and parts["acme.elims"] == [("acme.profit", "C1")]
    assert parts["acme.na"] == [("acme.profit", "C2")]
    assert overlapping_views(graph) == {"acme.profit": ["C1", "C2"]}
    g = graph.model_copy(deep=True)
    g.compositions["C4"] = Composition(id="C4", entity_id="acme", view="products", basis="b", unit="u",
                                       total="acme.landed_cost", members=["acme.home"], additive=False)
    g.compositions["C5"] = Composition(id="C5", entity_id="acme", view="v", basis="b", unit="u",
                                       total="acme.landed_cost", members=["acme.na"])
    assert overlapping_views(g) == {"acme.profit": ["C1", "C2"]}          # a non-additive view never overlaps


def test_one_item_folds_the_view_it_observes_most(graph):
    it = item("A", "acme.auto", "acme.home", "acme.profit", moves=["acme.finance"],
              extra=[{"type": "link", "source": "acme.auto", "target": "acme.na", "label": "l", "effect": 0.1}])
    skip, warnings = overlap_guard(graph, [it])
    assert list(skip) == ["A"] and list(skip["A"]) == [1]
    assert skip["A"][1] == ("overlapping view: C1, C2 are views of acme.profit; C1 is folded (item rule), so "
                            "acme.home is not")
    assert warnings == [{"scope": "item", "where": "A", "total": "acme.profit", "compositions": ["C1", "C2"],
                         "kept": "C1", "observed": {"C1": ["acme.auto", "acme.finance"], "C2": ["acme.home"]},
                         "dropped": [{"item": "A", "signal": 1, "value_of": "acme.home"}]}]
    res, dropped = translate_item(it, market_event_of(it, "IM-A"), graph, skip["A"])
    assert [op.target.subentity_id for op in res.events[0].ops if op.op != "add_interaction"] == [
        "acme.auto", "acme.profit", "acme.finance"]
    assert dropped == [f"observe acme.home ({skip['A'][1]})"] and res.rationale.endswith(f"Not folded: {dropped[0]}.")
    every = translate_item(item("Z", "acme.home"), market_event_of(item("Z"), "IM-Z"), graph, {0: "held"})
    assert every[0].events == [] and every[0].rationale == "nothing to change: observe acme.home (held)"


def test_a_part_of_another_total_is_never_dropped_for_this_ones_overlap(graph):
    g = graph.model_copy(deep=True)
    g.compositions["C6"] = Composition(id="C6", entity_id="acme", view="cost", basis="b", unit="u",
                                       total="acme.landed_cost", members=["macro.tariff"])
    it = item("A", "acme.auto", "acme.finance", "acme.home", "macro.tariff")
    skip, warnings = overlap_guard(g, [it])
    assert skip == {"A": {2: skip["A"][2]}} and "acme.home is not" in skip["A"][2]     # home only: tariff stays
    assert [w["dropped"] for w in warnings] == [[{"item": "A", "signal": 2, "value_of": "acme.home"}]]


def test_ties_go_to_the_larger_share_of_parts_then_the_first_id(graph):
    _, w = overlap_guard(graph, [item("A", "acme.auto", "acme.home")])
    assert w[0]["kept"] == "C2"                                   # 1 of 2 regions beats 1 of 3 segment parts
    g = graph.model_copy(deep=True)
    g.compositions["C0"] = Composition(id="C0", entity_id="acme", view="v", basis="b", unit="u", total="acme.profit",
                                       members=["acme.landed_cost", "acme.finance"])
    _, w = overlap_guard(g, [item("A", "acme.landed_cost", "acme.home")])
    assert w[0]["kept"] == "C0"


def test_one_day_folds_one_view_across_its_items(graph):
    a, b = item("A", "acme.auto"), item("B", "acme.home", "acme.na")
    other_day = item("C", "acme.finance", at="2024-01-16T09:00:00Z")
    skip, w = overlap_guard(graph, [a, b, other_day])
    assert skip == {"A": {0: "overlapping view: C1, C2 are views of acme.profit; C2 is folded (day rule), so "
                             "acme.auto is not"}}
    assert [(x["scope"], x["where"], x["kept"]) for x in w] == [("day", "2024-01-15", "C2")]
    assert overlap_guard(graph, [a, other_day]) == ({}, [])


def test_a_view_already_folded_that_day_keeps_its_place(graph):
    done, new = item("F", "acme.auto"), item("N", "acme.home", "acme.na")
    skip, w = overlap_guard(graph, [new], folded=[done])
    assert set(skip["N"]) == {0, 1} and w[0]["kept"] == "C1"
    assert [d["item"] for d in w[0]["dropped"]] == ["N", "N"]            # the folded item is never changed


def test_a_part_of_two_conflicting_totals_is_dropped_once(graph):
    g = graph.model_copy(deep=True)
    g.compositions["C5"] = Composition(id="C5", entity_id="acme", view="v", basis="b", unit="u",
                                       total="acme.landed_cost", members=["acme.home"])
    g.compositions["C6"] = Composition(id="C6", entity_id="acme", view="w", basis="b", unit="u",
                                       total="acme.landed_cost", members=["acme.auto", "acme.finance"])
    skip, w = overlap_guard(g, [item("A", "acme.auto", "acme.finance", "acme.home")])
    assert list(skip["A"]) == [2] and [x["total"] for x in w] == ["acme.landed_cost", "acme.profit"]
    assert w[1]["dropped"] == []                                         # already held back for the first total


# -- the import preview and the import ---------------------------------------------------------------------------------
@pytest.fixture
def runner(tmp_path):
    c = acme_construction()
    c["subentities"].append({"entity": "acme", **_s("acme.share_price", unit="¥", mean=6000.0, scale=300.0,
                                                    features={"per_share": "true"})})
    c["corporate_actions"] = [{"entity": "acme", "type": "split", "ratio": 15, "effective": "2024-01-10"}]
    d = world(tmp_path, c)
    tax = _taxonomy(tmp_path, attrs=ATTRS, objects={"root": "gen:obj:root", "nodes": [
        {"id": "gen:obj:root", "name": "Object", "parent": None}]})
    script = ScenarioScript.model_validate({
        "id": "acme_imports", "title": "Acme", "start": "2024-01-01", "canvas": "seeded", "imports": True,
        "initialization": {"construction_dir": str(d), "taxonomy_dir": str(tax)}, "steps": []})
    r = ImportRunner(None, None, script, True, storage=MemoryBackend(), tracer=RecordingTracer(run_id="acme"))
    r.load()
    return r


def bundle(*items):
    return {"title": "Acme results", "items": [i.model_dump(mode="json") for i in items]}


def test_the_preview_shows_the_overlap_and_the_split_and_the_import_applies_them(runner):
    a = item("A", "acme.auto", "acme.finance", "acme.home", "acme.share_price")
    b = bundle(a, item("B", "acme.na", at="2024-01-16T09:00:00Z"))
    pv = runner.preview(b)
    assert pv["overlap_rule"] == RULE and [w["kept"] for w in pv["overlaps"]] == ["C1"]
    row = pv["items"][0]
    assert row["changes"] == 3 and len(row["dropped"]) == 1 and "acme.home" in row["dropped"][0]
    assert row["conversions"][0]["model_basis"] == 15.0 and pv["items"][1]["conversions"] == []
    out = runner.import_items(b, ["A"])
    assert [w["kept"] for w in out["overlaps"]] == ["C1"]
    assert list(runner.import_skips) == ["IM-A"] and list(runner.import_skips["IM-A"]) == [2]
    ctl = runner.controller
    prop = ctl.proposals[out["waiting_on"]]
    targets = [op.target.subentity_id for op in prop.event.ops]
    assert targets == ["acme.auto", "acme.finance", "acme.share_price"]
    assert [op.value for op in prop.event.ops][-1] == 15.0
    run = ctl.get_update(out["update_id"])
    while run.state == UpdateState.AWAITING_REVIEW:
        ctl.approve(run.waiting_on, "reviewer")
    # once A is in, B (another day) has no overlap; A shows what was held back
    again = runner.preview(b)
    assert again["overlaps"] == [] and again["items"][0]["status"] == "imported"
    assert len(again["items"][0]["dropped"]) == 1 and again["items"][1]["dropped"] == []
    later = runner.preview(bundle(a, item("C", "acme.na", at=DAY)))
    assert later["overlaps"][0]["kept"] == "C1" and len(later["items"][1]["dropped"]) == 1


def test_a_view_already_imported_needs_no_skip(runner):
    out = runner.import_items(bundle(item("A", "acme.auto")))
    assert runner.import_skips == {} and out["overlaps"] == []
    assert runner.preview(bundle(item("A", "acme.auto")))["items"][0]["dropped"] == []
