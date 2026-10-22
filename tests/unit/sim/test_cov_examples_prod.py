"""The production demo's runner on the oil-shock world (loaded from the shared init cache), its own superentity
seeds, and the production catalog's operation builders and edits."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from axelrod_wm.control.controller import ControllerError
from axelrod_wm.engine import initialize
from axelrod_wm.repo.review import ProposalStatus
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.sim.examples.prod import PROD
from axelrod_wm.sim.examples.session import ProdDemoRunner
from axelrod_wm.sim.runner import build_runner
from axelrod_wm.trace import RecordingTracer

AT = datetime(2026, 2, 2, 15, 0, tzinfo=UTC)
OWN = {"S21", "S22", "S23", "S24"}          # world_model/examples/scenarios/prod_demo/superentity_seeds.yaml
OPS = {"add_entity", "add_subentity", "add_interaction", "change_value", "observe_value", "reweight_interaction"}


def prod():
    return build_runner("prod_demo", interactive=True, tracer=RecordingTracer(run_id="p"), storage=MemoryBackend(),
                        record_checklist=False)


@pytest.fixture(scope="module")
def runner():
    r = prod()
    r.load()
    return r


def test_before_loading():
    r = prod()
    assert isinstance(r, ProdDemoRunner)
    st = r.status()
    assert st.loaded is False and st.examples is None
    with pytest.raises(ControllerError, match="do not keep sessions"):
        r.resume({})


def test_loaded_with_its_own_seeds_and_every_change_reviewed(runner):
    st = runner.status()
    assert st.loaded and st.scenario_id == "prod_demo" and st.canvas == "scripted" and st.examples == "prod"
    assert st.step_index == 0 and st.state == "idle"
    ctl = runner.controller
    assert ctl.engine.config.review.policy == "review_all"
    assert len(ctl.engine.wm.graph.entities) > 50                       # the oil world after its history
    assert {x["id"] for x in runner.examples()} == {e.id for e in PROD.examples}
    assert all(x["status"] == "ready" for x in runner.examples())
    assert OWN <= set(ctl.engine.ltm.object_generalizations.patterns)   # superentities only prod_demo adds


def test_without_its_own_seeds_file(monkeypatch, tmp_path):
    real = initialize.resolve_path
    monkeypatch.setattr(initialize, "resolve_path",
                        lambda p: tmp_path / "missing.yaml" if "prod_demo" in str(p) else real(p))
    r = prod()
    r.load()
    assert r.controller.engine.config.review.policy == "review_all"
    assert not OWN & set(r.controller.engine.ltm.object_generalizations.patterns)


def test_every_operation_builder(runner):
    ctl = runner.controller
    for key, build in sorted(PROD.ops.items()):
        ops = build(ctl, AT)
        assert ops, key
        assert {op["op"] for op in ops} <= OPS, key
    assert PROD.ops["weaken"](ctl, AT)[0]["supports"] is False       # the oil-to-TFP link is there to weaken


def test_the_edits(runner):
    ctl = runner.controller
    group = PROD.edits["group"](ctl, "backend user")
    ctl.approve(group.id, by="backend user")
    nest = PROD.edits["nest"](ctl, "backend user")
    ctl.approve(nest.id, by="backend user")
    dissolve = PROD.edits["dissolve"](ctl, "backend user")
    assert {p.status for p in (group, nest)} == {ProposalStatus.APPROVED} and dissolve.status == ProposalStatus.PENDING
    ctl.reject(dissolve.id, by="backend user", note="keep it")
    assert PROD.edits["dissolve_provided"](ctl, "backend user").status == ProposalStatus.PENDING
    assert PROD.edits["retire"](ctl, "backend user").status == ProposalStatus.PENDING
    with pytest.raises(ControllerError):
        PROD.edits["retire_northwind"](ctl, "backend user")           # Northwind arrives only in a later example


def test_the_retire_edit_needs_its_link():
    small = build_runner("small_demo", interactive=True, storage=MemoryBackend(), record_checklist=False)
    small.load()
    with pytest.raises(ControllerError, match="no Oil price → TFP growth link"):
        PROD.edits["retire"](small.controller, "backend user")
    assert PROD.ops["weaken"](small.controller, AT) == []
