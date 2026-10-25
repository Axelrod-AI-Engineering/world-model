"""One unified base (Oct 25): a scenario's `construction_dirs` merge several client worlds, in order, into one engine.

The synthetic fixtures: `acme_demo` and `northwind_demo` are two client worlds that share the crude-oil market (defined the
same way in both), and `unified_demo` is the scenario that merges them."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from axelrod_wm.engine import focus as fo
from axelrod_wm.engine.focus import focus_result
from axelrod_wm.engine.initialize import (
    ConstructionError,
    ConstructionSpec,
    FileOrigin,
    SeedFile,
    as_paths,
    read_construction,
    read_seeds,
)
from axelrod_wm.sim.scenario import ScenarioScript, scenario_raw
from tests.where import ACME_WORLD as ACME
from tests.where import FIXTURE_CLIENTS
from tests.where import NORTHWIND_WORLD as NORTHWIND

SEEDS = [FIXTURE_CLIENTS / "scenarios" / "acme_demo" / "superentity_seeds.yaml",
         FIXTURE_CLIENTS / "scenarios" / "unified_demo" / "northwind_seeds.yaml"]


def edited(tmp_path: Path, file: str, change) -> Path:
    """A copy of the northwind world with one of its YAML files changed by `change(doc)`."""
    dest = tmp_path / "northwind_demo"
    shutil.copytree(NORTHWIND, dest)
    doc = yaml.safe_load((dest / file).read_text())
    change(doc)
    (dest / file).write_text(yaml.safe_dump(doc))
    return dest


# -- the merge --------------------------------------------------------------------------------------------------------
def test_worlds_merge_in_order_and_a_shared_definition_is_kept_once():
    data, origin = read_construction([ACME, NORTHWIND])
    ids = [e["id"] for e in data["entities"]]
    assert len(ids) == len(set(ids)) and ids.index("acme_bank") < ids.index("northwind_air")
    assert ids.count("crude_oil") == 1
    links = [i["id"] for i in data["interactions"]]
    assert links.count("m01") == 1 and {"n01", "n02", "n03", "n04", "n05", "m02"} <= set(links)
    # a world alone reads as it did before
    alone, _ = read_construction([NORTHWIND])
    assert [e["id"] for e in alone["entities"]] == ["crude_oil", "jet_fuel", "industrial_demand", "harbor_steel", "northwind_air"]
    assert read_construction(NORTHWIND)[0] == alone


def test_each_id_keeps_its_origin_file_and_world():
    _data, origin = read_construction([ACME, NORTHWIND])
    mine = origin["acme_motors.automotive_operating_income"]
    assert mine == "acme_motors" and mine.world == "acme_demo"
    assert origin["northwind_air.fuel_cost"] == "northwind_air" and origin["northwind_air.fuel_cost"].world == "northwind_demo"
    assert origin["n05"] == "harbor_steel" and origin["n05"].world == "northwind_demo"
    assert isinstance(origin["n04"], FileOrigin) and origin["n04"] in {"harbor_steel"}


def test_the_merged_world_builds_a_spec():
    spec = ConstructionSpec.load([str(ACME), str(NORTHWIND)], ACME / "taxonomy")
    assert {"northwind_air", "acme_bank", "crude_oil"} <= {e.id for e in spec.entities}
    one = ConstructionSpec.load(str(NORTHWIND), ACME / "taxonomy")
    assert [e.id for e in one.entities][0] == "crude_oil"


@pytest.mark.parametrize("file, change, what", [
    ("entities.yaml", lambda d: d["entities"][0].update(description="another description"),
     "entity 'crude_oil' is defined differently in acme_demo/entities.yaml and northwind_demo/entities.yaml"),
    ("interactions.yaml", lambda d: d["interactions"][0].update(label="loosens"),
     "interaction 'm01' is defined differently in acme_demo/interactions.yaml and northwind_demo/interactions.yaml"),
])
def test_two_worlds_defining_one_id_differently_stop_the_load(tmp_path, file, change, what):
    world = edited(tmp_path, file, change)
    with pytest.raises(ConstructionError) as err:
        read_construction([ACME, world])
    assert what in str(err.value)


def test_a_clash_between_construction_files_names_both_files(tmp_path):
    clash = tmp_path / "acme_copy"
    shutil.copytree(ACME, clash)
    mine = yaml.safe_load((NORTHWIND / "construction" / "harbor_steel.yaml").read_text())["interactions"][0]
    (clash / "construction" / "extra.yaml").write_text(yaml.safe_dump({"interactions": [{**mine, "label": "other"}]}))
    with pytest.raises(ConstructionError) as err:
        read_construction([clash, NORTHWIND])
    assert "interaction 'n04' is defined differently in acme_copy/construction/extra.yaml and " \
           "northwind_demo/construction/harbor_steel.yaml" in str(err.value)


def test_decision_variables_and_link_labels_merge(tmp_path):
    def labels(d):
        d["entity_link_labels"] = {"crude_oil->jet_fuel": "feeds"}

    one = edited(tmp_path, "interactions.yaml", labels)
    other = tmp_path / "other"
    shutil.copytree(NORTHWIND, other)
    doc = yaml.safe_load((other / "entities.yaml").read_text())
    doc["decision_variables"] = ["jet_fuel.price"]
    (other / "entities.yaml").write_text(yaml.safe_dump(doc))
    doc = yaml.safe_load((one / "entities.yaml").read_text())
    doc["decision_variables"] = ["jet_fuel.price", "industrial_demand.index"]
    (one / "entities.yaml").write_text(yaml.safe_dump(doc))
    data, _ = read_construction([one, other])
    assert data["decision_variables"] == ["jet_fuel.price", "industrial_demand.index"]
    assert data["entity_link_labels"] == {"crude_oil->jet_fuel": "feeds"}
    # the same label again is fine; a different one is not
    doc = yaml.safe_load((other / "interactions.yaml").read_text())
    doc["entity_link_labels"] = {"crude_oil->jet_fuel": "feeds"}
    (other / "interactions.yaml").write_text(yaml.safe_dump(doc))
    assert read_construction([one, other])[0]["entity_link_labels"] == {"crude_oil->jet_fuel": "feeds"}
    doc["entity_link_labels"] = {"crude_oil->jet_fuel": "supplies"}
    (other / "interactions.yaml").write_text(yaml.safe_dump(doc))
    with pytest.raises(ConstructionError, match="entity link label 'crude_oil->jet_fuel' is defined differently"):
        read_construction([one, other])


# -- the seeds --------------------------------------------------------------------------------------------------------
def test_seed_files_merge_and_a_repeat_is_kept_once(tmp_path):
    merged = read_seeds(as_paths([str(p) for p in SEEDS]))
    ids = [p["id"] for p in merged["patterns"]]
    assert ids[-2:] == ["N1", "N2"] and len(ids) == len(set(ids)) == 12
    spec = SeedFile.load([str(p) for p in SEEDS])
    assert len(spec.patterns) == 12
    assert read_seeds(as_paths([str(SEEDS[1])])) == yaml.safe_load(SEEDS[1].read_text())
    # the same file twice is the file once
    assert read_seeds(as_paths([str(SEEDS[1]), str(SEEDS[1])]))["patterns"] == yaml.safe_load(SEEDS[1].read_text())["patterns"]


def test_seed_files_that_define_one_id_differently_stop_the_load(tmp_path):
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    base = {"patterns": [{"id": "P", "name": "One", "members": ["x", "y"]}],
            "super_interaction_labels": [{"source": "P", "target": "Q", "label": "l"}],
            "frontier_seeds": [{"earlier": "x.v", "later": "y.v"}], "palettes": {"h1": {"fill": "#fff", "line": "#000"}}}
    a.write_text(yaml.safe_dump(base))
    same = tmp_path / "same.yaml"
    same.write_text(yaml.safe_dump(base))
    assert read_seeds([a, same]) == {**base}
    for key, change, what in [
        ("patterns", lambda d: d["patterns"][0].update(name="Two"), "seed pattern 'P'"),
        ("super_interaction_labels", lambda d: d["super_interaction_labels"][0].update(label="m"), "seed label 'P->Q'"),
        ("frontier_seeds", lambda d: d["frontier_seeds"][0].update(lag_days=9), "seed frontier seed 'x.v->y.v'"),
        ("palettes", lambda d: d["palettes"]["h1"].update(fill="#eee"), "seed palette 'h1'")]:
        doc = yaml.safe_load(a.read_text())
        change(doc)
        b.write_text(yaml.safe_dump(doc))
        with pytest.raises(ConstructionError, match=f"{what} is defined differently in a.yaml and b.yaml"):
            read_seeds([a, b])


# -- the scenario -----------------------------------------------------------------------------------------------------
def test_a_scenario_names_its_worlds_with_construction_dirs():
    raw = scenario_raw("unified_demo")
    ini = raw["initialization"]
    assert "construction_dirs" not in ini
    assert [Path(p).name for p in ini["construction_dir"]] == ["acme_demo", "northwind_demo"]
    assert all(Path(p).is_absolute() for p in ini["construction_dir"] + ini["seeds"])
    script = ScenarioScript.load("unified_demo")
    assert script.canvas == "seeded" and script.imports and len(script.initialization.seeds) == 2
    # a single folder is still one string
    assert isinstance(ScenarioScript.load("acme_demo").initialization.construction_dir, str)


def test_a_scenario_names_one_form_or_the_other(tmp_path, monkeypatch):
    root = tmp_path / "scenarios"
    for name, ini in {"both": {"construction_dir": "w", "construction_dirs": ["w"]},
                      "empty": {"construction_dirs": []}, "text": {"construction_dirs": "w"}}.items():
        (root / name).mkdir(parents=True)
        (root / name / "scenario.yaml").write_text(yaml.safe_dump({"id": name, "initialization": ini}))
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", str(tmp_path))
    with pytest.raises(ValueError, match="not both"):
        scenario_raw("both")
    with pytest.raises(ValueError, match="a list of world folders"):
        scenario_raw("empty")
    with pytest.raises(ValueError, match="a list of world folders"):
        scenario_raw("text")


def test_the_unified_scenario_loads_as_one_seeded_engine():
    from axelrod_wm.repo.snapshots import MemoryBackend
    from axelrod_wm.sim.runner import build_runner
    from axelrod_wm.trace import NullTracer

    runner = build_runner("unified_demo", interactive=True, storage=MemoryBackend(), tracer=NullTracer())
    runner.load()
    g = runner.controller.engine.wm.graph
    assert {"acme_motors", "northwind_air", "harbor_steel", "crude_oil"} <= set(g.entities)
    assert {"N1", "N2", "S1"} <= set(runner.controller.engine.ltm.object_generalizations.patterns)
    # the templates come from the first world
    assert runner.controller.world_dir() == ACME


# -- a focus over the merged base ---------------------------------------------------------------------------------------
def test_a_focus_over_the_merged_base_drops_the_other_worlds_companies():
    fo._CACHE.clear()
    fr = focus_result({"base": "unified_demo", "companies": ["northwind_air"]})
    assert fr.covered == ["acme_bank", "acme_motors", "acme_re", "delta_bank", "harbor_steel", "northwind_air"]
    assert fr.dropped_companies == ["acme_bank", "acme_motors", "acme_re", "delta_bank", "harbor_steel"]
    assert sorted(fr.entities) == ["crude_oil", "jet_fuel", "northwind_air"]
    links = [i["id"] for i in fr.construction()["interactions"]]
    assert {"n01", "n02", "n03", "m01"} <= set(links) and not {"n04", "n05", "m02"} & set(links)
    kept = {p["id"] for p in fr.seeds()["patterns"]}
    assert "N1" in kept and "N2" not in kept and "S1" not in kept
    assert "harbor_steel" in fr.report()["dropped_companies"]


def test_a_focus_on_the_first_world_drops_the_second_whole():
    fo._CACHE.clear()
    fr = focus_result({"base": "unified_demo", "companies": ["acme_motors", "acme_re"]})
    assert {"northwind_air", "harbor_steel"} <= set(fr.dropped_companies)
    assert not {"jet_fuel", "northwind_air", "harbor_steel", "industrial_demand"} & fr.entities
    spec = ConstructionSpec.load("worlds/acme_demo", ACME / "taxonomy", focus={"base": "unified_demo",
                                 "companies": ["acme_motors", "acme_re"]})
    assert "northwind_air" not in {e.id for e in spec.entities}


def test_the_focus_reloads_when_a_world_file_changes(tmp_path, monkeypatch):
    """The cache key covers every world folder and seed file a unified scenario names."""
    fo._CACHE.clear()
    spec = fo.FocusSpec(base="unified_demo", companies=["northwind_air"])
    versions = fo._versions(spec)
    names = {Path(p).name for p, _t in versions}
    assert {"northwind_air.yaml", "harbor_steel.yaml", "acme_motors.yaml", "northwind_seeds.yaml",
            "superentity_seeds.yaml", "scenario.yaml"} <= names
