"""The client root (src/axelrod_wm/clients.py): client content lives outside the tracked tree, found through
`WORLD_MODEL_CLIENT_DIR`, and a scenario's paths are read against the root that holds it."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from axelrod_wm import clients
from axelrod_wm.clients import (
    DATA_DIR,
    EXAMPLES_DIR,
    REPO_ROOT,
    anchor,
    anchor_paths,
    client_roots,
    find_scenario,
    find_world,
    load_scenario_yaml,
    scenario_dirs,
    scenario_root,
)
from axelrod_wm.engine.focus import FocusSpec, focus_result
from axelrod_wm.sim.scenario import ScenarioScript, list_scenarios, scenario_raw
from tests.clients import client_path, client_present, skip_without_client
from tests.where import FIXTURE_CLIENTS


def write(path: Path, text: str = "x: 1\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def root(tmp_path, monkeypatch):
    """A client root holding one scenario ("zed") built on its own world, with every kind of path."""
    r = tmp_path / "client"
    write(r / "worlds/zed/entities.yaml")
    write(r / "worlds/zed/taxonomy/objects.yaml")
    write(r / "scenarios/zed/superentity_seeds.yaml")
    write(r / "scenarios/zed/layout.yaml")
    write(r / "configs/zed.yaml")
    write(r / "history/regimes.yaml")
    write(r / "truth.yaml")
    write(r / "days/a.json")
    write(r / "scenarios/zed/scenario.yaml", yaml.safe_dump({
        "id": "zed", "title": "Zed", "start": "2026-01-05",
        "initialization": {"construction_dir": "worlds/zed", "taxonomy_dir": "world_model/taxonomy",
                           "seeds": "scenarios/zed/superentity_seeds.yaml", "layout": "scenarios/zed/layout.yaml",
                           "history": {"from": "2026-01-01", "to": "2026-02-01", "regimes": "history/regimes.yaml"}},
        "world": {"truth": "truth.yaml"}, "config_overrides": "configs/zed.yaml", "imports_dir": "days", "steps": []}))
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", str(r))
    return r


def test_the_client_root_is_the_variable_or_data_clients(monkeypatch, tmp_path):
    monkeypatch.delenv("WORLD_MODEL_CLIENT_DIR", raising=False)
    assert client_roots() == [DATA_DIR / "clients"]
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", " ")
    assert client_roots() == [DATA_DIR / "clients"]
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", f"{tmp_path / 'a'}{os.pathsep}{tmp_path / 'b'}")
    assert client_roots() == [tmp_path / "a", tmp_path / "b"]
    assert scenario_dirs() == [EXAMPLES_DIR / "scenarios", tmp_path / "a" / "scenarios", tmp_path / "b" / "scenarios"]


def test_scenarios_and_worlds_are_found_in_the_repository_then_the_client_root(root):
    assert find_scenario("small_demo") == EXAMPLES_DIR / "scenarios" / "small_demo"
    assert find_scenario("zed") == root / "scenarios" / "zed"
    assert find_scenario("nobody") is None
    assert find_world("small_demo") == EXAMPLES_DIR / "worlds" / "small_demo"
    assert find_world("zed") == root / "worlds" / "zed"
    assert find_world("nobody") is None


def test_the_root_that_holds_a_scenario(root, tmp_path):
    assert scenario_root(root / "scenarios" / "zed") == root
    assert scenario_root(EXAMPLES_DIR / "scenarios" / "small_demo") == REPO_ROOT
    assert scenario_root(tmp_path / "elsewhere") == REPO_ROOT


def test_a_path_is_read_against_the_root_holding_the_scenario_then_the_repository(root):
    assert anchor("worlds/zed", root) == str(root / "worlds/zed")
    assert anchor("world_model/taxonomy", root) == "world_model/taxonomy"                  # not under the client root: the repository's
    assert anchor("worlds/zed", REPO_ROOT) == "worlds/zed"                    # a repository scenario's paths stay as written
    assert anchor(str(root / "worlds/zed"), root) == str(root / "worlds/zed")  # absolute: as it is


def test_every_path_of_a_client_scenario_is_anchored(root):
    raw = scenario_raw("zed")
    ini = raw["initialization"]
    assert ini["construction_dir"] == str(root / "worlds/zed") and ini["taxonomy_dir"] == "world_model/taxonomy"
    assert ini["seeds"] == str(root / "scenarios/zed/superentity_seeds.yaml")
    assert ini["layout"] == str(root / "scenarios/zed/layout.yaml")
    assert ini["history"]["regimes"] == str(root / "history/regimes.yaml") and ini["history"]["to"] == "2026-02-01"
    assert raw["world"]["truth"] == str(root / "truth.yaml")
    assert raw["config_overrides"] == str(root / "configs/zed.yaml") and raw["imports_dir"] == str(root / "days")
    script = ScenarioScript.load("zed")
    assert script.directory == root / "scenarios" / "zed" and script.initialization.seeds == ini["seeds"]


def test_a_scenario_with_no_paths_is_left_alone(tmp_path):
    assert anchor_paths({"id": "x", "focus": {"base": "y"}}, tmp_path) == {"id": "x", "focus": {"base": "y"}}
    assert anchor_paths({"initialization": {"seeds": None}}, tmp_path) == {"initialization": {"seeds": None}}
    assert anchor_paths({}, tmp_path) == {}


def test_load_scenario_yaml_reads_an_empty_file_as_nothing(tmp_path):
    assert load_scenario_yaml(write(tmp_path / "scenario.yaml", "")) == {}


def test_scenarios_list_from_both_places_and_the_repository_wins_a_clash(root):
    write(root / "scenarios/small_demo/scenario.yaml", yaml.safe_dump({"id": "small_demo", "title": "Clash", "start": "2026-01-05",
                                                                        "initialization": {}, "steps": []}))
    ids = [s["id"] for s in list_scenarios()]
    assert "zed" in ids and ids.count("small_demo") == 1
    assert next(s["title"] for s in list_scenarios() if s["id"] == "small_demo") != "Clash"
    os.environ["WORLD_MODEL_CLIENT_DIR"] = str(root / "none")                  # a root that does not exist lists nothing
    assert "zed" not in [s["id"] for s in list_scenarios()]


def test_a_focused_client_scenario_reads_its_base_through_the_client_root(root):
    write(root / "scenarios/zed_focus/scenario.yaml", yaml.safe_dump({
        "id": "zed_focus", "title": "Zed focus", "focus": {"base": "zed", "companies": ["x"]}}))
    raw = scenario_raw("zed_focus")
    assert raw["initialization"]["construction_dir"] == str(root / "worlds/zed")
    assert raw["initialization"]["focus"]["base"] == "zed"


def test_the_synthetic_client_is_on_the_roots_and_its_scenarios_are_found():
    assert FIXTURE_CLIENTS in client_roots() and client_present("acme_demo", "acme_focus")
    assert not client_present("acme_demo", "no_such_scenario")
    assert client_path("worlds/acme_demo/entities.yaml") == FIXTURE_CLIENTS / "worlds/acme_demo/entities.yaml"
    assert client_path("worlds/nobody/entities.yaml") == client_roots()[-1] / "worlds/nobody/entities.yaml"
    skip_without_client("acme_demo")                                            # present: nothing is skipped
    with pytest.raises(pytest.skip.Exception, match="no_such_scenario"):
        skip_without_client("acme_demo", "no_such_scenario")
    ids = [s["id"] for s in list_scenarios()]
    assert {"acme_demo", "acme_focus", "small_demo", "oil_shock_demo"} <= set(ids)
    focused = focus_result(FocusSpec(base="acme_demo", companies=["acme_motors", "acme_re"]))
    assert focused.world_dir == FIXTURE_CLIENTS / "worlds" / "acme_demo"


def test_the_module_exposes_the_variable_name():
    assert clients.CLIENT_DIR_ENV == "WORLD_MODEL_CLIENT_DIR"


def test_the_tracked_content_lives_under_world_model_and_data_is_local():
    assert EXAMPLES_DIR == REPO_ROOT / "world_model" / "examples" and (EXAMPLES_DIR / "scenarios" / "small_demo").is_dir()
    assert clients.TAXONOMY_DIR == REPO_ROOT / "world_model" / "taxonomy" and (clients.TAXONOMY_DIR / "objects.yaml").exists()
    assert DATA_DIR in (REPO_ROOT / "data", Path(os.environ.get(clients.DATA_DIR_ENV, "")))
