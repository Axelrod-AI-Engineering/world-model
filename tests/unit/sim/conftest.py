"""A mini scripted scenario: the oil demo's world, events, theses, and decisions, with one week of history and no
regimes, so a ScenarioRunner loads in about a second. Its init cache lives in a temporary folder."""

from __future__ import annotations

import pytest
import yaml

from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.runner import ScenarioRunner
from axelrod_wm.sim.scenario import ScenarioScript
from axelrod_wm.trace import RecordingTracer

OIL_YAML = "data/scenarios/oil_shock_demo/scenario.yaml"


@pytest.fixture(scope="session")
def mini_paths(tmp_path_factory):
    root = tmp_path_factory.mktemp("mini_scenario")
    regimes = root / "regimes.yaml"
    regimes.write_text("regimes: []\n")
    return {"root": root, "regimes": regimes, "cache": root / "cache"}


@pytest.fixture
def mini_script(mini_paths):
    def make(steps: list[dict] | None = None, **over) -> ScenarioScript:
        raw = yaml.safe_load(open(OIL_YAML))
        raw["initialization"]["history"]["from"] = "2026-01-19"
        raw["initialization"]["history"]["regimes"] = str(mini_paths["regimes"])
        raw["checklist"] = False
        raw["steps"] = steps if steps is not None else []
        raw.update(over)
        return ScenarioScript.model_validate(raw)

    return make


@pytest.fixture
def mini_runner(mini_script, mini_paths):
    def make(steps: list[dict] | None = None, *, interactive: bool = False, storage=None, tracer=None,
             **kw) -> ScenarioRunner:
        return ScenarioRunner(None, None, mini_script(steps), interactive,
                              storage=storage if storage is not None else MemoryBackend(),
                              tracer=tracer if tracer is not None else RecordingTracer(run_id="mini"),
                              cache_dir=mini_paths["cache"], **kw)

    return make
