"""The world view ingestion reads (intake/world_view.py): a pure, sorted adapter over the graph; the committed fixture
ingestion's tests run against is exactly what the adapter makes of the synthetic Acme world (a drift test)."""

import importlib.util
import json
import os

import pytest
import yaml

from axelrod_ingest.contract.world_view import WorldView
from axelrod_wm.intake.world_view import world_view_of
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.runner import build_runner
from tests.where import ACME_WORLD, ACME_WORLD_VIEW, EXPORT_WORLD_VIEW


@pytest.fixture(scope="module")
def acme():
    r = build_runner("acme_demo", interactive=True, storage=MemoryBackend(), record_checklist=False)
    r.load()
    return r.controller.engine.wm.graph


def test_the_adapter_reads_what_the_graph_holds(acme):
    v = world_view_of(acme)
    assert set(v.entities) == set(acme.entities) and set(v.values) == set(acme.subentities)
    assert [i.id for i in v.links] == [i.id for i in acme.active_interactions()]
    bank, rate = v.entities["acme_bank"], v.values["central_bank.policy_rate"]
    assert (bank.kind, bank.region, bank.sector) == ("company", "US", "banking")
    assert bank.subentity_ids == tuple(acme.entities["acme_bank"].subentity_ids)
    s = acme.subentities["central_bank.policy_rate"]
    assert (rate.unit, rate.scale, rate.mean, rate.sd) == (s.unit, s.scale, float(s.posterior.mean()), float(s.posterior.sd()))
    link = next(i for i in acme.active_interactions() if i.fixed)
    got = next(x for x in v.links if x.id == link.id)
    assert got.fixed and got.polarity == link.polarity() and got.effect_mean == float(link.forward.effect.mean())


def test_the_view_is_sorted_and_its_json_is_stable(acme):
    v = world_view_of(acme)
    assert list(v.entities) == sorted(v.entities) and list(v.values) == sorted(v.values)
    assert world_view_of(acme).to_json() == v.to_json()
    assert WorldView.from_json(v.to_json()) == v


def test_the_committed_fixture_is_what_the_adapter_makes_of_acme(acme):
    """If this fails, regenerate the fixture:  uv run python world_model/scripts/export_world_view.py acme_demo
    ingestion/tests/fixtures/world_view_acme.json --client-dir world_model/tests/fixtures/clients"""
    fixture = json.loads(ACME_WORLD_VIEW.read_text())
    assert WorldView.from_json(json.dumps(fixture["world_view"])) == world_view_of(acme)
    templates = yaml.safe_load((ACME_WORLD / "templates.yaml").read_text())
    assert fixture["inverted"] == sorted(s["pattern"] for s in templates["subjects"] if s.get("invert")) != []


def test_the_export_script_writes_the_fixture_byte_for_byte(tmp_path, monkeypatch):
    monkeypatch.setenv("WORLD_MODEL_CLIENT_DIR", os.environ["WORLD_MODEL_CLIENT_DIR"])   # the script sets it; undone after
    spec = importlib.util.spec_from_file_location("export_world_view", EXPORT_WORLD_VIEW)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    out = tmp_path / "view.json"
    assert script.main(["acme_demo", str(out)]) == 0               # the tests' client root already names the fixture client
    assert out.read_text() == ACME_WORLD_VIEW.read_text()
    out2 = tmp_path / "again.json"
    assert script.main(["acme_demo", str(out2), "--client-dir", str(ACME_WORLD.parents[1])]) == 0
    assert out2.read_text() == out.read_text()
