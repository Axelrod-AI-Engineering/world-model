"""Sally's focused world (<client root>/scenarios/sally_focus, engine/focus.py, Oct 18): Toyota and Tokio Marine and the players
they connect to, with none of her other twelve covered companies. Both worlds load once; the focused one must hold each
focus company's construction exactly as sally_demo does, keep no trace of the removed companies, and run its theses."""

from __future__ import annotations

import pytest

from axelrod_wm.context.construction import construction_view, trace
from axelrod_wm.engine.focus import focus_result
from axelrod_wm.engine.initialize import read_construction
from axelrod_wm.model.construction import validate_construction
from axelrod_wm.model.ids import entity_of
from axelrod_wm.sim.scenario import (
    ScenarioScript,
    load_expected_paths,
    load_theses,
    load_watchlist,
    thesis_from_spec,
)
from tests.clients import client_path, skip_without_client

skip_without_client('sally_demo', 'sally_focus')

FOCUS = ["toyota", "tokio_marine"]
REMOVED = {"jpmorgan", "citigroup", "morgan_stanley", "unicredit", "china_construction_bank", "aib_group",
           "softbank_corp", "msad", "komatsu", "hyundai", "byd", "catl"}
TRACES = [("dollar_yen.usd_jpy", "toyota"), ("us_vehicle_tariffs.effective_rate", "toyota"),
          ("boj.policy_rate", "tokio_marine"), ("jgbs.yield_30y", "tokio_marine"),
          ("dollar_yen.usd_jpy", "tokio_marine")]


def _load(scenario):
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner

    r = build_runner(scenario, interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    return r


@pytest.fixture(scope="module")
def focused():
    return _load("sally_focus")


@pytest.fixture(scope="module")
def demo():
    return _load("sally_demo").controller.engine.wm.graph


@pytest.fixture(scope="module")
def g(focused):
    return focused.controller.engine.wm.graph


def test_the_focus_is_declared_over_sally_demo():
    s = ScenarioScript.load("sally_focus")
    assert s.focus.base == "sally_demo" and s.focus.companies == FOCUS and s.imports
    assert set(focus_result(s.focus).dropped_companies) == REMOVED


def test_no_removed_company_or_any_of_its_values_appears(g):
    assert not REMOVED & set(g.entities)
    assert not [s for s in g.subentities if entity_of(s) in REMOVED]
    for i in g.interactions.values():
        assert entity_of(i.source_id) not in REMOVED and entity_of(i.target_id) not in REMOVED, i.id
    _data, origin = read_construction(client_path("worlds/sally_demo"))
    assert not [iid for iid in g.interactions if origin.get(iid) in REMOVED]     # their constructions go whole
    for x in [*g.paths.values(), *g.compositions.values(), *g.identities.values(), *g.stock_flows.values(),
              *g.matrices.values()]:
        assert x.entity_id not in REMOVED, x.id
    for inst in g.instances.values():
        assert not REMOVED & set(inst.bindings.values()), inst.id
    assert not REMOVED & set(load_watchlist(ScenarioScript.load("sally_focus").directory)["entities"])


def test_the_taxonomy_lists_only_what_remains(focused, g):
    ltm = focused.controller.engine.ltm
    known = set(g.entities) | set(g.interactions) | set(ltm.object_generalizations.patterns)
    for tax in (ltm.object_generalizations.taxonomy, ltm.interaction_generalizations.taxonomy):
        for n in tax.nodes.values():
            assert set(n.instance_ids) <= known, (n.id, set(n.instance_ids) - known)


def test_every_remaining_interaction_has_both_ends(g):
    for i in g.interactions.values():
        assert i.source_id in g.subentities and i.target_id in g.subentities, i.id
        for p in i.parameters:
            assert p.moderator_id in g.subentities, (i.id, p.moderator_id)
    assert validate_construction(g) == []


@pytest.mark.parametrize("eid", FOCUS)
def test_each_focus_companys_construction_is_intact(g, demo, eid):
    def own(graph):
        def ids(coll):
            return sorted(x.id for x in coll.values() if x.entity_id == eid)

        links = sorted(i.id for i in graph.interactions.values()
                       if {entity_of(i.source_id), entity_of(i.target_id)} <= set(graph.entities) - REMOVED
                       and eid in {entity_of(i.source_id), entity_of(i.target_id)})
        return (ids(graph.compositions), ids(graph.paths), ids(graph.identities), ids(graph.stock_flows),
                ids(graph.matrices), sorted(graph.entities[eid].subentity_ids), links)

    assert own(g) == own(demo)
    view = construction_view(g, eid)
    assert view["problems"] == [] and view["compositions"] and view["paths"]


@pytest.mark.parametrize("start,eid", TRACES)
def test_traces_run_as_they_do_in_sally_demo(g, demo, start, eid):
    def routes(graph):
        tr = trace(graph, start, eid)
        return tr["reaches_endpoint"], sorted(map(str, tr["routes"]))

    assert routes(g) == routes(demo) and routes(g)[0]


def test_the_remaining_theses_run_and_reach_the_focus(focused, g):
    ctl = focused.controller
    specs, _ = load_theses(ctl.scenario_dir)
    assert sorted(specs) == ["S-T1", "S-T2", "S-T3", "S-T4"]
    expected = load_expected_paths(ctl.scenario_dir)["theses"]
    links = {(i.source_id, i.target_id) for i in g.active_interactions()}
    for tid, spec in specs.items():
        assert all(t in g.subentities for t in spec["targets"]), tid
        fc = ctl.pose_thesis(thesis_from_spec(spec, ctl.now))
        reached = set(fc.paths["values"])
        assert any(entity_of(t) in FOCUS and t in reached for t in spec["targets"]), tid
        assert fc.coverage["contributed"], tid
        for c in expected.get(tid, {}).get("channels", []):
            assert (c["source"], c["target"]) in links, (tid, c)
