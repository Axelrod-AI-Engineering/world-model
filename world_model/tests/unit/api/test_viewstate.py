"""A login's compartment as a view onto the main engine (api/viewstate.py): the surface it shares with an engine of its
own, what its engine, controller, and runner refuse, and how it follows the main engine."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from axelrod_ingest.contract.bundle import ImportBundle
from axelrod_wm.api.app import AppState, create_app
from axelrod_wm.api.viewstate import CompartmentError, ViewController, ViewState
from axelrod_wm.control.controller import ControllerError
from axelrod_wm.control.updates import UpdateState
from axelrod_wm.events.thesis import Thesis
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend
from tests.service.helpers import service

ENV = {"WORLD_MODEL_BASIC_AUTH_USERNAME": "admin", "WORLD_MODEL_BASIC_AUTH_PASSWORD": "pw-admin",
       "WORLD_MODEL_LOGINS": "nw:pw-nw:northwind_focus", "WORLD_MODEL_API_KEYS": "", "WORLD_MODEL_TRUSTED_ISSUERS": ""}
BUNDLE = {"format": "axelrod.import/v1", "title": "Jet fuel (synthetic)", "collected_by": "test", "synthetic": True,
          "items": [{"id": "V-1", "published_at": "2026-09-13T10:00:00Z", "source": "Synthetic desk", "source_type": "data",
                     "kind": "data", "headline": "Jet fuel rises", "summary": "Jet fuel rose to 2.9 a gallon.",
                     "entities": ["jet_fuel"], "relevance": 0.8,
                     "signals": [{"type": "observe", "value_of": "jet_fuel.price", "value": 2.9}]}]}


@pytest.fixture(scope="module")
def client():
    with service(None, scenario="unified_demo", **ENV) as c:
        yield c


@pytest.fixture()
def view(client) -> ViewState:
    v = client.app.state.views["nw"]
    v.ensure_loaded()
    return v


def sign_in(c: TestClient, user: str) -> None:
    c.cookies.clear()
    assert c.post("/login", data={"username": user, "password": f"pw-{user}", "next": "/"},
                  follow_redirects=False).status_code == 303


def test_the_view_has_the_surface_of_an_engine_of_its_own(client, view):
    main = client.app.state.axelrod
    assert view.is_view and not main.is_view and view.scenario == view.first_scenario == "northwind_focus"
    assert view.lock is main.lock and view.play_delay == main.play_delay
    assert view.play_task is None and view.switching is None and view.play_requested is False
    assert view.runner.loaded and view.runner.script.title.startswith("Unified demo, Northwind")
    assert view.runner.script.initialization.layout is None and view.runner.script is view.runner.script
    assert view.demos() == {"current": "northwind_focus", "demos": [
        {"id": "northwind_focus", "label": "Unified demo, Northwind compartment",
         "note": "Northwind Air and the players it connects to", "current": True, "ready": True, "cold": False}],
        "switching": None}
    assert view.scenarios() == [{"id": "northwind_focus", "title": view.runner.script.title, "canvas": "seeded",
                                 "examples": None, "imports": True}]
    assert {"unified_demo", "northwind_focus"} <= {s["id"] for s in main.scenarios()}
    assert view.locked(lambda: 3) == 3 and asyncio.run(view.call(lambda: 4)) == 4
    with pytest.raises(KeyError):
        asyncio.run(view.switch("unified_demo"))
    for refused in (view.load, view.reset_all):
        with pytest.raises(CompartmentError, match="nothing to load"):
            refused()
    with pytest.raises(CompartmentError, match="staged review is for the unified model"):
        view.require_main("staged review")
    assert main.require_main("staged review") is None
    assert isinstance(CompartmentError("x"), (ControllerError, AttributeError))


def test_the_view_drives_runs_on_the_main_engine(client, view, monkeypatch):
    main = client.app.state.axelrod
    seen = []
    monkeypatch.setattr(main, "start_drive", lambda run_id: seen.append(("start", run_id)))

    async def drive(run_id):
        seen.append(("drive", run_id))
        return "done"

    monkeypatch.setattr(main, "drive", drive)
    view.start_drive("UPD-9")
    assert asyncio.run(view.drive("UPD-9")) == "done" and seen == [("start", "UPD-9"), ("drive", "UPD-9")]


def test_the_engine_of_a_compartment_commits_nothing_and_does_not_learn(view):
    eng = view.controller.engine
    with pytest.raises(CompartmentError, match="cannot change the model directly"):
        eng.mutator.begin("x")
    with pytest.raises(CompartmentError, match="does not learn"):
        _ = eng.learning
    with pytest.raises(CompartmentError, match="does not learn"):
        _ = eng.structural
    assert eng.config is view.unified_runner().controller.engine.config
    assert set(eng.wm.graph.entities) == {"crude_oil", "jet_fuel", "northwind_air"} and eng.ltm is eng.ltm
    ctx = eng.context(learn=False, now=eng.wm.clock)
    assert ctx.engine is eng and ctx.wm is eng.wm and ctx.ltm is eng.ltm
    # its history is the main engine's, with each cause cut to its kind
    versions = eng.storage.versions()
    assert versions and all(":" not in v.cause for v in versions)
    assert eng.snapshots.version_info(10**6) is None
    info = eng.snapshots.version_info(eng.version)
    assert info.version == eng.version and ":" not in info.cause
    wm, ltm = eng.restore(1)
    assert set(wm.graph.entities) == {"crude_oil", "jet_fuel", "northwind_air"}
    assert set(eng.snapshots.restore(1)[0].graph.entities) == set(wm.graph.entities)
    with pytest.raises(CompartmentError, match="not open to a compartment"):
        _ = eng.storage.append_version


def test_the_view_follows_the_main_engine_as_it_commits(client, view):
    eng = view.controller.engine
    first = eng.wm
    assert eng.wm is first                           # one narrowing until the main engine commits
    main = view.main_controller().engine
    with main.mutator.begin("test:nudge", at=main.wm.clock) as txn:
        txn.update("wm.graph.subentities", "jet_fuel.price", level_mean=0.25)
    assert eng.wm is not first and eng.wm.graph.subentities["jet_fuel.price"].level_mean == 0.25


def test_the_controller_of_a_compartment_reads_its_own_and_decides_only_what_it_imported(client, view):
    ctl = view.controller
    assert isinstance(ctl, ViewController) and ctl.engine is ctl.own.engine and ctl.main is view.main_controller()
    assert ctl.now == ctl.main.now
    ctl.own.now = datetime(2000, 1, 1, tzinfo=timezone.utc)                  # simulated time is the main engine's
    assert ctl.now == ctl.main.now
    assert ctl.proposals == {} and ctl.pending_proposals() == [] and ctl.updates == {} and ctl.active_update is None
    assert ctl.market_events == {} and ctl.market_status == {} and ctl.translations == {} and ctl.cycle is ctl.main.cycle
    for call in (ctl.approve, ctl.reject, ctl.defer, ctl.edit, ctl.set_confidence):
        with pytest.raises(ControllerError, match="unknown proposal PR-404"):
            call("PR-404")
    for call in (ctl.get_update, ctl.continue_update, ctl.cancel_update):
        with pytest.raises(ControllerError, match="unknown update UPD-404"):
            call("UPD-404")
    with pytest.raises(CompartmentError, match="whole unified model"):
        ctl.evaluate(None)
    with pytest.raises(CompartmentError, match="belongs to the unified model"):
        ctl.set_review_policy("review_all")
    # nothing the model holds changes by a direct edit either
    with pytest.raises(CompartmentError, match="cannot change the model directly"):
        ctl.pin_thesis("T-Q99")


def test_the_runner_of_a_compartment_imports_through_the_main_runner(client, view):
    runner, main = view.runner, view.unified_runner()
    assert runner.local_bundles() == [] and runner.pause().scenario_id == "northwind_focus"
    with pytest.raises(ControllerError, match="no bundle"):
        runner.local_bundle("x.json")
    # a bundle as a model is narrowed like one as data
    assert [i["id"] for i in runner.narrow(ImportBundle.model_validate(BUNDLE))["items"]] == ["V-1"]
    assert [i["id"] for i in runner.preview(BUNDLE)["items"]] == ["V-1"]
    with pytest.raises(CompartmentError, match="step: a compartment cannot do this"):
        _ = runner.step
    assert getattr(runner, "step", None) is None
    out = runner.import_items(BUNDLE)
    assert out["imported"] == ["V-1"] and out["update_id"] in view.runs and runner.pending_update() is None
    assert set(runner.imported) == {"IM-V-1"} and set(main.imported) >= {"IM-V-1"}
    status = runner.status()
    assert status.state == "awaiting_review" and status.pending_proposals == 1 and status.update_id == out["update_id"]
    # an update still running, with nothing waiting
    ctl = view.controller
    run = ctl.updates[out["update_id"]]
    pid = run.waiting_on
    ctl.main.proposals[pid].needs_review = False
    run.state = UpdateState.RUNNING
    assert runner.status().state == "running"
    run.state, ctl.main.proposals[pid].needs_review = UpdateState.AWAITING_REVIEW, True
    # it broadcasts its own status to the pages streaming it
    queue = asyncio.Queue()
    loop = asyncio.new_event_loop()
    view.tracer.subscribe(loop, queue)
    runner._broadcast()
    loop.run_until_complete(asyncio.sleep(0))
    assert queue.get_nowait()["status"]["scenario_id"] == "northwind_focus"
    view.tracer.unsubscribe(queue)
    loop.close()
    ctl.main.reject(pid, by="test", note="done with it")
    ctl.main.cycle.resume(run, run_to_end=True)


def item(n: int) -> dict:
    return {**BUNDLE, "items": [{**BUNDLE["items"][0], "id": f"V-{n}", "published_at": f"2026-09-{13 + n}T10:00:00Z",
                                 "signals": [{"type": "observe", "value_of": "jet_fuel.price", "value": 2.5 + n / 10}]}]}


def test_the_review_decisions_of_a_compartment_are_made_on_the_main_engine(view):
    ctl, runner = view.controller, view.runner
    pid = runner.import_items(item(2))["waiting_on"]
    run_id = ctl.proposals[pid].update_id
    ctl.set_confidence(pid, 0.8)
    ctl.edit(pid, ctl.proposals[pid].event, by="me")
    ctl.defer(pid, by="me")
    assert str(ctl.main.proposals[pid].status) == "deferred" and ctl.pending_proposals() == []
    ctl.approve(pid, by="me")
    assert str(ctl.main.proposals[pid].status) == "approved"
    ctl.main.cycle.resume(ctl.updates[run_id], run_to_end=True)
    # a rejection; then another run, cancelled and continued from the view
    other = runner.import_items(item(3))
    ctl.reject(other["waiting_on"], by="me", note="not today")
    assert str(ctl.main.proposals[other["waiting_on"]].status) == "rejected"
    ctl.main.cycle.resume(ctl.updates[other["update_id"]], run_to_end=True)
    last = runner.import_items(item(4))
    assert ctl.cancel_update(last["update_id"]).id == last["update_id"]
    assert ctl.continue_update(last["update_id"]).id == last["update_id"]


def test_a_forecast_pinned_on_a_compartment_is_kept_in_its_own_layer(view):
    ctl = view.controller
    thesis = ctl.thesis_from_question("What if oil prices rose by 10% next quarter?")
    fc = ctl.pose_thesis(thesis.model_copy(update={"pinned": True}))
    assert thesis.id in ctl.engine.layer.pinned and ctl.engine.layer.order[-1] == thesis.id
    assert ctl.engine.layer.pose_counts[thesis.id] == 1 and ctl.forecast(fc.id) is not None
    assert isinstance(ctl.theses[thesis.id], Thesis)
    assert view.main_controller().engine.wm.forecast_layer.by_thesis == {}


def test_a_view_starts_again_when_the_main_engine_is_rebuilt(client, view):
    old = view.controller
    view._engine = object()                         # as after a reset: the main controller has another engine
    assert view.ensure_loaded() is view.runner
    assert view.controller is not old


def test_the_browser_refuses_a_compartment_what_is_for_the_whole_model(client):
    sign_in(client, "nw")
    assert client.patch("/api/config/review", json={"policy": "review_all"}).status_code == 409
    assert client.post("/api/updates", json={}).status_code == 409
    assert client.post("/api/hypotheses", json={"kind": "interaction_present", "statement": "x"}).status_code in (409, 422)
    assert client.post("/api/graph-update-events", json={"id": "GUE-1", "kind": "user_drawn", "occurred_at": "2026-09-01T00:00:00Z",
                                                          "recorded_at": "2026-09-01T00:00:00Z", "produced_by": "human",
                                                          "ops": []}).status_code in (409, 422)
    assert client.post("/api/evaluate", json={"kind": "calibration"}).status_code in (409, 422)
    assert client.post("/api/proposals/PR-1/stage").status_code in (405, 409)
    assert client.get("/api/proposals/PR-1/stage").status_code == 409
    assert client.get("/api/paths/proposal/PR-1").status_code == 409
    assert client.get("/api/state", params={"version": 1}).json()["version"] == 1
    sign_in(client, "admin")


def test_the_stream_of_a_compartment_is_its_own(client):
    sign_in(client, "nw")
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "hello", "since_seq": 0})
        msgs = [ws.receive_json()]
        while msgs[-1]["type"] == "trace":                    # the view's own events (its forecasts), then its status
            msgs.append(ws.receive_json())
        assert msgs[-1]["type"] == "status" and msgs[-1]["status"]["scenario_id"] == "northwind_focus"
    sign_in(client, "admin")


def test_a_login_on_another_focus_keeps_its_own_engine(tmp_path, monkeypatch):
    """A compartment is a focus whose base is the main engine's scenario; a focus on another base is an engine of its own."""
    for k, v in {**ENV, "WORLD_MODEL_LOGINS": "own:pw-own:acme_focus,view:pw-view:northwind_focus,"
                                               "gone:pw-gone:no_such_scenario"}.items():
        monkeypatch.setenv(k, v)
    app = create_app(scenario="unified_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0,
                     lake_dir=tmp_path / "lake", load_on_startup=False)
    assert set(app.state.axelrod_by_login) == {"own"} and set(app.state.views) == {"view"}
    assert isinstance(app.state.axelrod_by_login["own"], AppState)
    with TestClient(app) as c:                       # nothing loaded at start: the first read loads the main engine
        c.post("/login", data={"username": "view", "password": "pw-view", "next": "/"}, follow_redirects=False)
        assert {e["id"] for e in c.get("/api/state").json()["entities"]} == {"crude_oil", "jet_fuel", "northwind_air"}
        assert app.state.axelrod.runner.loaded
    # the main engine is acme_demo: northwind_focus is not over it, and acme_focus is
    monkeypatch.setenv("WORLD_MODEL_LOGINS", "a:pw-a:acme_focus,n:pw-n:northwind_focus")
    other = create_app(scenario="acme_demo", storage=MemoryBackend(), trace_dir=None, lake_dir=tmp_path / "lake2",
                       load_on_startup=False)
    assert set(other.state.views) == {"a"} and set(other.state.axelrod_by_login) == {"n"}


def test_a_login_engine_is_stored_beside_the_main_engine(tmp_path, monkeypatch):
    """A login's own engine keeps its storage next to the main engine's (demo -> demo-<login>), never under the working
    directory, and in memory when the main engine is."""
    for k, v in {**ENV, "WORLD_MODEL_LOGINS": "own:pw-own:acme_focus"}.items():
        monkeypatch.setenv(k, v)
    app = create_app(scenario="unified_demo", storage=FilesBackend(path=tmp_path / "demo"), trace_dir=None,
                     lake_dir=tmp_path / "lake", load_on_startup=False)
    assert app.state.axelrod_by_login["own"].storage.path == tmp_path / "demo-own"
    mem = create_app(scenario="unified_demo", storage=MemoryBackend(), trace_dir=None, lake_dir=tmp_path / "lake2",
                     load_on_startup=False)
    assert isinstance(mem.state.axelrod_by_login["own"].storage, MemoryBackend)

