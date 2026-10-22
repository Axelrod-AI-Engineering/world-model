"""A focused world (engine/focus.py), on a small synthetic world: covered companies a and b, a company c with no
construction file, and the players around them. Focusing on a keeps a, what reaches it, and one link past it."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from axelrod_ingest.contract.bundle import ImportBundle
from axelrod_wm.engine import focus as fo
from axelrod_wm.engine.focus import FocusSpec, focus_result
from axelrod_wm.engine.initialize import ConstructionError
from axelrod_wm.sim import scenario as sc
from axelrod_wm.sim.imports import ImportRunner


def _v(i: str) -> dict:
    return {"id": i, "name": i, "attribute_kind": "level", "unit": "x"}


def _i(i: str, s: str, t: str, **kw) -> dict:
    return {"id": i, "source": s, "target": t, "label": "moves", **kw}


ENTITIES = {"decision_variables": ["m.rate", "n.price"], "entities": [
    {"id": "a", "name": "Acme", "kind": "company", "aliases": ["AAA Corp", "A1"], "subentities": [_v("a.profit"), _v("a.sales")]},
    {"id": "b", "name": "Bco Holdings", "short": "Bco", "kind": "company", "aliases": ["BB", "B9 JP"],
     "subentities": [_v("b.profit")]},
    {"id": "c", "name": "Rival", "kind": "company", "subentities": [_v("c.x")]},
    {"id": "m", "name": "Central bank", "kind": "agency", "description": "sets rates that Bco watches",
     "subentities": [_v("m.rate")]},
    {"id": "n", "name": "Metal", "kind": "market", "subentities": [_v("n.price")]},
    {"id": "p", "name": "Index", "kind": "market", "subentities": [_v("p.level")]},
    {"id": "q", "name": "Far", "kind": "market", "subentities": [_v("q.v")]},
]}
INTERACTIONS = {"entity_link_labels": {"m->a": "moves", "n->b": "moves"}, "interactions": [
    _i("i1", "m.rate", "a.profit", parameters=[{"name": "k", "moderator": "c.x", "coefficient": {"mu": 1}}],
       note="as Bco once said", tags=["x"], evidence=[{"strength": 0.5}]),
    _i("i2", "n.price", "b.profit"),
    _i("i3", "a.profit", "p.level"),
    _i("i4", "p.level", "q.v"),
    _i("i5", "c.x", "a.sales"),
    _i("i6", "m.rate", "b.profit", state={"threshold": {"value": "m.rate", "above": 1.0}, "asymmetry": None}),
]}
A_FILE = {
    "subentities": [{"entity": "m", **_v("m.extra_a")}],
    "interactions": [_i("a1", "m.extra_a", "a.sales"), _i("a2", "a.sales", "a.profit", identity="a.id1"),
                     _i("a3", "a.sales", "a.profit", identity="a.sf")],
    "identities": [{"id": "a.id1", "entity_id": "a", "target": "a.profit", "form": "product", "factors": ["a.sales"]}],
    "stock_flows": [{"id": "a.sf", "entity_id": "a", "stock": "a.profit", "period_days": 91, "inflows": ["a.sales"]}],
    "compositions": [{"id": "a.c1", "entity_id": "a", "total": "a.profit", "members": ["a.sales"], "residual": "a.sales",
                      "eliminations": "a.sales"}],
    "matrices": [{"id": "a.mx", "entity_id": "a", "rows": "a.c1", "columns": "a.c1", "cells": {"r": {"c": "a.sales"}}}],
    "paths": [{"id": "a.p1", "entity_id": "a", "endpoint": "a.profit", "steps": [{"interaction_id": "a1"}]}],
}
B_FILE = {
    "subentities": [{"entity": "m", **_v("m.extra_b")}],
    "entities": [{"id": "z", "name": "Zed", "kind": "market", "subentities": [_v("z.v")]}],
    "interactions": [_i("b1", "m.rate", "m.extra_b"), _i("b2", "m.extra_b", "a.sales"), _i("b3", "z.v", "b.profit")],
    "compositions": [{"id": "b.c1", "entity_id": "b", "total": "b.profit", "members": ["b.profit"]}],
    "matrices": [{"id": "b.mx", "entity_id": "b", "rows": "b.c1", "columns": "b.c1"}],
    "paths": [{"id": "b.p1", "entity_id": "b", "endpoint": "b.profit", "steps": [{"interaction_id": "b3"}]}],
}
SEEDS = {"patterns": [
    {"id": "P1", "name": "Core", "members": ["m", "c", "a"], "interactions": ["i1", "i2"], "rivals": ["P2"]},
    {"id": "P2", "name": "B side", "members": ["b", "n"]},
    {"id": "P3", "name": "Raw", "members": ["m", "n"]},
    {"id": "P4", "name": "Pair", "members": ["a", "p"], "description": "a with Bco"},
    {"id": "P5", "name": "Old", "members": ["a", "m"], "description": "a and BB"},
    {"id": "P6", "name": "Top", "members": ["m", "p"], "sub_patterns": ["P1", "P2"], "absent_interactions": ["i3", "i2"]},
], "super_interaction_labels": [{"source": "P1", "target": "P6", "label": "x"}, {"source": "P2", "target": "P1", "label": "y"}],
    "frontier_seeds": [{"earlier": "m.rate", "later": "a.profit"}, {"earlier": "n.price", "later": "a.profit"}]}


def _op(sid: str | None) -> dict:
    return {"op": "change_value", "target": {"kind": "concrete", "subentity_id": sid} if sid else {"kind": "pattern"}}


THESES = {"theses": [
    {"id": "T1", "question": "Rates up?", "targets": ["a.profit", "n.price"], "event": {"ops": [_op("m.rate"), _op(None)]},
     "target_groups": [{"kind": "superentity", "ref": "P1"}, {"kind": "superentity", "ref": "P2"},
                       {"kind": "entity", "ref": "a"}, {"kind": "entity", "ref": "b"}]},
    {"id": "T2", "question": "Metal?", "targets": ["a.profit"], "event": {"ops": [_op("n.price")]}},
    {"id": "T3", "question": "Index?", "targets": ["p.level"], "event": {"ops": [_op("m.rate")]}},
    {"id": "T4", "question": "What about AAA Corp and Bco?", "targets": ["a.profit"], "event": {"ops": [_op("m.rate")]}},
    {"id": "T5", "question": "And Bco?", "targets": ["a.profit"], "event": {"ops": [_op("m.rate")]}},
], "hypotheses": [{"id": "H1"}]}
EXPECTED = {"theses": {
    "T1": {"chains": [["m.rate", "a.profit"], ["n.price", "b.profit"]],
           "channels": [{"source": "m.rate", "target": "a.profit"}, {"source": "n.price", "target": "b.profit"}],
           "missing_links": [{"source": "c.x", "target": "a.profit"}, {"source": "z.v", "target": "a.profit"}],
           "outputs": {"a.profit": "up", "n.price": "down"}},
    "T2": {"chains": [["n.price", "a.profit"]], "channels": [{"source": "n.price", "target": "a.profit"}],
           "outputs": {"a.profit": "up"}},
}}
OVERRIDES = {"P5": {"description": "a and its bank"}, "T5": {"question": "And the rival?"},
             "watchlist": {"name": "focused book"}, "i5": {"note": "the rival's pull"}}


def _write(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(obj, sort_keys=False))


@pytest.fixture()
def world(tmp_path, monkeypatch):
    w, s = tmp_path / "world", tmp_path / "scenarios"
    _write(w / "entities.yaml", ENTITIES)
    _write(w / "interactions.yaml", INTERACTIONS)
    _write(w / "construction" / "a.yaml", A_FILE)
    _write(w / "construction" / "b.yaml", B_FILE)
    _write(s / "base" / "scenario.yaml", {"id": "base", "title": "Base", "start": "2026-01-01", "canvas": "seeded",
                                          "imports": True, "context_pack": {"file_index": "036", "slug": "base"},
                                          "initialization": {"construction_dir": str(w), "taxonomy_dir": str(w),
                                                             "seeds": str(s / "base" / "seeds.yaml")}, "steps": []})
    _write(s / "base" / "seeds.yaml", SEEDS)
    _write(s / "base" / "theses.yaml", THESES)
    _write(s / "base" / "expected_paths.yaml", EXPECTED)
    _write(s / "base" / "watchlist.yaml", {"name": "book", "entities": ["a", "b", "m"]})
    _write(s / "bare" / "scenario.yaml", {"id": "bare", "initialization": {"construction_dir": str(w)}})
    _write(s / "focused" / "scenario.yaml", {"id": "focused", "title": "Focused", "context_pack": {"file_index": "037"},
                                             "focus": {"base": "base", "companies": ["a"], "overrides": OVERRIDES}})
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", str(tmp_path))      # the scenarios above are a client root's
    fo._CACHE.clear()
    return SimpleNamespace(world=w, scenarios=s, spec=FocusSpec(base="base", companies=["a"], overrides=OVERRIDES))


def test_the_focus_keeps_its_company_what_reaches_it_and_one_link_past_it(world):
    fr = focus_result(world.spec)
    assert fr.covered == ["a", "b"] and fr.dropped_companies == ["b"]
    rep = fr.report()
    assert rep["entities_kept"] == ["a", "c", "m", "p"] and rep["entities_dropped"] == ["b", "n", "q", "z"]
    # b's construction goes whole: its value on m and its link into a's value, though neither names b
    assert rep["added_values_dropped"] == ["m.extra_b"]
    data = fr.construction()
    assert [i["id"] for i in data["interactions"]] == ["i1", "i3", "i5", "a1", "a2", "a3"]
    assert [x["id"] for x in data["paths"]] == ["a.p1"] and [x["id"] for x in data["matrices"]] == ["a.mx"]
    assert [x["id"] for x in data["compositions"]] == ["a.c1"] and [x["id"] for x in data["identities"]] == ["a.id1"]
    assert [x["id"] for x in data["stock_flows"]] == ["a.sf"]
    assert data["decision_variables"] == ["m.rate"] and data["entity_link_labels"] == {"m->a": "moves"}
    m = next(e for e in data["entities"] if e["id"] == "m")
    assert [s["id"] for s in m["subentities"]] == ["m.rate", "m.extra_a"]
    assert next(i for i in data["interactions"] if i["id"] == "i5")["note"] == "the rival's pull"
    c = rep["counts"]
    assert c["entities: covered companies"] == {"kept": 1, "dropped": 1}
    assert c["entities: other market"] == {"kept": 1, "dropped": 3}
    assert c["interactions"] == {"kept": 6, "dropped": 6} and c["matrices"] == {"kept": 1, "dropped": 1}
    assert c["values (declared)"] == {"kept": 6, "dropped": 5}
    assert {"b", "i2", "b2", "P2", "P3", "P4"} <= set(fr.dropped_ids()) and "a" not in fr.dropped_ids()
    assert fr.keeps_value("a.share_price") and not fr.keeps_value("m.extra_b") and not fr.keeps_value("b.profit")
    assert rep["mentions"] == {"i1": ["Bco"], "m": ["Bco"]}
    assert fr.construction() is not fr.construction()


def test_groups_keep_what_remains_and_drop_what_was_about_the_removed(world):
    fr = focus_result(world.spec)
    seeds = fr.seeds()
    assert [p["id"] for p in seeds["patterns"]] == ["P1", "P5", "P6"]
    p1, p5, p6 = seeds["patterns"]
    assert p1["members"] == ["m", "c", "a"] and p1["interactions"] == ["i1"] and p1["rivals"] == []
    assert p5["description"] == "a and its bank"
    assert p6["sub_patterns"] == ["P1"] and p6["absent_interactions"] == ["i3"]
    assert seeds["super_interaction_labels"] == [{"source": "P1", "target": "P6", "label": "x"}]
    assert seeds["frontier_seeds"] == [{"earlier": "m.rate", "later": "a.profit"}]
    why = fr.report()["groups_dropped"]
    assert why["P2"].startswith("its companies were all removed") and why["P3"].startswith("fewer than two")
    assert why["P4"] == "its text names Bco (give it an override)"


def test_theses_and_expected_paths_keep_what_concerns_the_focus(world):
    fr = focus_result(world.spec)
    th = {t["id"]: t for t in fr.theses()["theses"]}
    assert list(th) == ["T1", "T5"] and fr.theses()["hypotheses"] == []
    assert th["T1"]["targets"] == ["a.profit"]
    assert th["T1"]["target_groups"] == [{"kind": "superentity", "ref": "P1"}, {"kind": "entity", "ref": "a"}]
    assert th["T5"]["question"] == "And the rival?"
    why = fr.report()["theses_dropped"]
    assert why == {"T2": "its shock is on a removed value", "T3": "no focus company is among its targets",
                   "T4": "its question names Bco (give it an override)"}
    ex = fr.expected_paths()["theses"]
    assert list(ex) == ["T1"]
    assert ex["T1"]["chains"] == [["m.rate", "a.profit"]] and ex["T1"]["outputs"] == {"a.profit": "up"}
    assert ex["T1"]["missing_links"] == [{"source": "c.x", "target": "a.profit"}]
    c = fr.report()["counts"]
    assert c["expected chains"] == {"kept": 1, "dropped": 2} and c["expected channels"] == {"kept": 1, "dropped": 2}
    assert c["theses"] == {"kept": 2, "dropped": 3}
    assert fr.watchlist() == {"name": "focused book", "entities": ["a", "m"]}


def test_import_bundles_lose_the_items_about_removed_companies(world):
    fr = focus_result(world.spec)

    def item(i, **kw):
        return {"id": i, "headline": "news", **kw}

    bundle = {"items": [
        item("x1", entities=["b"]),
        item("x2", signals=[{"type": "observe", "value_of": "b.profit"}]),
        item("x3", tickers=["B9 JP"]),
        item("x4", headline="Bco beats"),
        item("x5", entities=["a", "n"], signals=[{"type": "observe", "value_of": "a.profit"},
                                                 {"type": "support", "source": "n.price", "target": "a.profit"}]),
        item("x6", signals=[{"type": "observe", "value_of": "n.price"}]),
        item("x7", entities=["a", "n"]),
    ]}
    out, n = fr.narrow_bundle(bundle)
    assert [i["id"] for i in out["items"]] == ["x5", "x7"]
    assert n == {"items_dropped": ["x1", "x2", "x3", "x4", "x6"], "signals_dropped": 2, "items_kept": 2}
    assert out["items"][0]["entities"] == ["a"] and len(out["items"][0]["signals"]) == 1
    # the import runner narrows any bundle, parsed or not, only in a focused scenario
    runner = SimpleNamespace(script=SimpleNamespace(initialization=SimpleNamespace(focus=world.spec)))
    b = ImportBundle.model_validate({"title": "t", "items": [
        {"id": "y1", "published_at": "2026-01-02T00:00:00Z", "source": "s", "headline": "Bco up", "summary": ""},
        {"id": "y2", "published_at": "2026-01-02T00:00:00Z", "source": "s", "headline": "Acme up", "summary": ""}]})
    assert [i["id"] for i in ImportRunner.narrow(runner, b)["items"]] == ["y2"]
    runner.script.initialization.focus = None
    assert ImportRunner.narrow(runner, b) is b


def test_bad_focuses_are_refused_and_results_are_cached_per_file_version(world):
    with pytest.raises(ConstructionError, match="covered companies of base"):
        focus_result({"base": "base", "companies": ["c"]})
    with pytest.raises(ConstructionError, match="none given"):
        focus_result({"base": "base", "companies": []})
    with pytest.raises(ConstructionError, match="itself a focused scenario"):
        focus_result({"base": "focused", "companies": ["a"]})
    first = focus_result(world.spec)
    assert focus_result(world.spec.model_dump()) is first
    f = world.world / "construction" / "a.yaml"
    st = f.stat()
    os.utime(f, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert focus_result(world.spec) is not first


def test_a_base_without_groups_theses_or_watchlist(world):
    fr = focus_result({"base": "bare", "companies": ["a"]})
    assert fr.seeds()["patterns"] == [] and fr.theses()["theses"] == [] and fr.expected_paths()["theses"] == {}
    assert fr.watchlist() is None


def test_a_focused_scenario_inherits_its_base_and_narrows_its_files(world):
    s = sc.ScenarioScript.load("focused")
    assert s.id == "focused" and s.imports and s.canvas == "seeded" and s.title == "Focused"
    assert s.context_pack == {"file_index": "037", "slug": "base"}
    assert s.initialization.focus == world.spec and s.focus == world.spec
    assert sc.ScenarioScript.load("base").initialization.focus is None
    d = world.scenarios / "focused"
    theses, hyps = sc.load_theses(d, datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert list(theses) == ["T1", "T5"] and hyps == {}
    assert list(sc.load_expected_paths(d)["theses"]) == ["T1"]
    assert sc.load_watchlist(d)["entities"] == ["a", "m"]
    base = world.scenarios / "base"
    assert list(sc.load_expected_paths(base)["theses"]) == ["T1", "T2"]
    assert sc.load_watchlist(base)["entities"] == ["a", "b", "m"]
    assert sc.load_expected_paths(world.scenarios / "bare") == {} and sc.load_watchlist(world.scenarios / "bare") is None
    assert sc.scenario_focus(world.scenarios / "nowhere") is None
    listed = {x["id"]: x for x in sc.list_scenarios()}
    assert listed["focused"]["imports"] and listed["focused"]["canvas"] == "seeded"
