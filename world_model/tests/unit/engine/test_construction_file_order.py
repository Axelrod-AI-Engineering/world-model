"""A construction file's own entities are read before its top-level `subentities:` (engine/initialize.read_construction), and a
scenario that no client root holds stops with a message naming what a root needs."""

from __future__ import annotations

import pytest

from axelrod_wm.engine.initialize import ConstructionError, read_construction
from axelrod_wm.sim.scenario import ScenarioScript
from tests.unit.model.test_business_construction import _s, world

FILE = {
    "entities": [{"id": "borealis", "name": "Borealis Ferries", "kind": "company", "category_tags": ["SD"],
                  "subentities": [_s("borealis.fleet")]}],
    "subentities": [{"entity": "borealis", **_s("borealis.revenue")}, {"entity": "acme", **_s("acme.fuel_cost")}],
}


def test_a_file_can_add_values_to_an_entity_it_defines_itself(tmp_path):
    d = world(tmp_path, FILE)
    data, origin = read_construction(d)
    borealis = next(e for e in data["entities"] if e["id"] == "borealis")
    assert [s["id"] for s in borealis["subentities"]] == ["borealis.fleet", "borealis.revenue"]   # inline first, then the top level
    assert "entity" not in borealis["subentities"][1]
    acme = next(e for e in data["entities"] if e["id"] == "acme")
    assert "acme.fuel_cost" in [s["id"] for s in acme["subentities"]]                             # an earlier file's entity still works
    assert origin["borealis.revenue"] == origin["borealis"] == origin["acme.fuel_cost"] == "acme"
    assert read_construction(d)[0] == data                                                        # the same every time


def test_a_value_naming_an_entity_nobody_defines_is_still_refused(tmp_path):
    d = world(tmp_path, {"subentities": [{"entity": "ghost", **_s("ghost.x")}]})
    with pytest.raises(ConstructionError, match="names unknown entity 'ghost'"):
        read_construction(d)


def test_a_scenario_no_root_holds_names_what_a_client_root_needs(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "worlds" / "w").mkdir(parents=True)                         # worlds/ alone, no scenarios/ or configs/
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", str(root))
    with pytest.raises(FileNotFoundError, match="no scenario 'private_demo'.*scenarios/, worlds/ and configs/ side by side"):
        ScenarioScript.load("private_demo")
