"""The engine behind the demo API (api/app.py AppState): storage per demo, the demo menu's switch and its progress,
update runs driven a day at a time, the daily schedule, and the app's startup, shutdown, and error handlers."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from types import SimpleNamespace

import pytest
import yaml
from fastapi.testclient import TestClient

from axelrod_wm.api import app as app_mod
from axelrod_wm.api.app import AppState, create_app
from axelrod_wm.control.controller import ControllerError
from axelrod_wm.control.updates import UpdateState
from axelrod_wm.engine.config import DEFAULT_CONFIG_PATH, deep_merge
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend


class Run:
    def __init__(self, rid="UPD-1", state=UpdateState.RUNNING):
        self.id, self.state = rid, state


class Runner:
    def __init__(self, scenario="small_demo", **kw):
        self.scenario = scenario
        self.loaded = False
        self.interactive = True
        self.progress = None
        self.broadcasts = 0
        self.steps = 0
        self.state = "idle"
        self.pending = None
        self.updates = {}
        self.cycle = SimpleNamespace(run_days=self._run_days, _fail=self._fail, resume=self._resume)
        self.controller = SimpleNamespace(auto_resume=True, updates=self.updates, cycle=self.cycle)
        self.failed = []
        self.days = []

    def load(self):
        self.loaded = True
        return SimpleNamespace(scenario=self.scenario)

    def status(self):
        return {"scenario": self.scenario}

    def pending_update(self):
        return self.pending

    def step(self, interactive):
        self.steps += 1

    def _broadcast(self):
        self.broadcasts += 1

    def _run_days(self, run, max_days):
        self.days.append(run.id)
        if getattr(run, "boom", False):
            raise RuntimeError("day failed")
        run.state = UpdateState.DONE

    def _fail(self, run, exc):
        self.failed.append(str(exc))
        run.state = UpdateState.FAILED

    def _resume(self, run, run_to_end):
        run.state = UpdateState.RUNNING


@pytest.fixture
def state(monkeypatch):
    made = []

    def build_runner(scenario, **kw):
        r = Runner(scenario)
        made.append(r)
        return r

    monkeypatch.setattr(app_mod, "build_runner", build_runner)
    st = AppState("small_demo", None, storage=MemoryBackend(), trace_dir=None, play_delay=0.0)
    st.made = made
    return st


# -- storage per demo ---------------------------------------------------------------------------------------
def test_each_demo_gets_storage_of_its_own(tmp_path):
    st = AppState("small_demo", None, storage=None, trace_dir=None)
    assert st.storage_for("prod_demo") is None
    files = AppState("small_demo", None, storage=FilesBackend(path=tmp_path / "demo"), trace_dir=None)
    assert files.storage_for("prod_demo").path == tmp_path / "demo-prod_demo"
    mem = AppState("small_demo", None, storage=MemoryBackend(), trace_dir=None)
    other = mem.storage_for("prod_demo")
    assert isinstance(other, MemoryBackend) and other is not mem.storage and mem.storage_for("prod_demo") is other


# -- the demo menu ------------------------------------------------------------------------------------------
def test_reset_all_waits_for_a_demo_being_opened(state):
    state.switch_task = SimpleNamespace(done=lambda: False)
    with pytest.raises(ControllerError, match="still opening"):
        state.reset_all()


def test_a_demo_whose_files_are_missing_is_still_listed(state, monkeypatch):
    from axelrod_wm.sim import scenario

    def broken(sid):
        raise FileNotFoundError(sid)

    monkeypatch.setattr(scenario.ScenarioScript, "load", staticmethod(broken))
    out = state.demos()
    assert [d["id"] for d in out["demos"]][:2] == ["small_demo", "prod_demo"]
    assert not any(d["cold"] for d in out["demos"])


def test_switch_progress_follows_a_replay():
    st = AppState("small_demo", None, storage=MemoryBackend(), trace_dir=None)
    eng = SimpleNamespace(wm=SimpleNamespace(last_processed_day=9))
    st.switching = {"demo": "prod_demo", "phase": "starting", "t0": time.monotonic(),
                    "runner": SimpleNamespace(progress={"phase": "replay", "engine": eng, "days": 20})}
    out = st.switch_progress()
    assert out["phase"] == "replay" and out["days"] == [10, 20] and out["fraction"] == 0.5 and "runner" not in out
    st.switching = {"demo": "prod_demo", "phase": "error", "error": "x", "t0": time.monotonic()}
    out = st.switch_progress()
    assert out["phase"] == "error" and "days" not in out


def test_prepare_builds_and_keeps_a_runner(state):
    r = state.prepare("prod_demo")
    assert r.loaded and r.progress == {"phase": "ready"} and not r.controller.auto_resume
    assert state.prepare("prod_demo") is r          # kept
    assert state.runners["prod_demo"] is r


def test_switch_refuses_a_second_demo_while_one_opens(state):
    async def go():
        state.switch_task = asyncio.get_running_loop().create_future()
        state.switching = {"demo": "prod_demo", "phase": "starting", "t0": time.monotonic()}
        out = await state.switch("prod_demo")             # the one already opening: its progress
        assert out["switching"]["demo"] == "prod_demo"
        with pytest.raises(ControllerError, match="already opening prod_demo"):
            await state.switch("emily_demo")
        state.switching = None
        with pytest.raises(ControllerError, match="already opening a demo"):
            await state.switch("emily_demo")
        state.switch_task.cancel()

    asyncio.run(go())


def test_switch_waits_for_the_running_update_then_swaps(state, monkeypatch):
    async def wait_for(aw, timeout):
        raise TimeoutError

    async def go():
        state.load()
        state.update_task = asyncio.get_running_loop().create_future()
        monkeypatch.setattr(app_mod.asyncio, "wait_for", wait_for)
        await state.switch("prod_demo")
        await state.switch_task
        assert state.scenario == "prod_demo" and state.switching is None
        state.update_task.cancel()

    asyncio.run(go())


def test_a_switch_that_fails_is_reported_and_the_current_demo_keeps_serving(state, monkeypatch):
    def boom(scenario, **kw):
        raise RuntimeError("no such files")

    async def go():
        state.load()
        monkeypatch.setattr(app_mod, "build_runner", boom)
        await state.switch("prod_demo")
        await state.switch_task
        out = state.demos()
        assert out["current"] == "small_demo"
        assert out["switching"]["phase"] == "error" and out["switching"]["error"] == "RuntimeError: no such files"

    asyncio.run(go())


# -- update runs, one day at a time ------------------------------------------------------------------------
def test_one_day_handles_a_reload_a_failure_and_a_runner_swapped_out(state):
    state.load()
    r = state.runner
    assert state._one_day("UPD-gone") == "done"           # reloaded meanwhile: nothing left to drive
    r.updates["UPD-1"] = Run()
    r.updates["UPD-1"].boom = True
    assert state._one_day("UPD-1") == str(UpdateState.FAILED) and r.failed == ["day failed"]
    r.updates["UPD-2"] = Run("UPD-2", state=UpdateState.AWAITING_REVIEW)
    r.broadcasts = 0
    assert state._one_day("UPD-2") == str(UpdateState.AWAITING_REVIEW) and r.broadcasts == 1   # not run, reported

    def swap(run, max_days):
        run.state = UpdateState.DONE
        state.runner = None                                # a demo swapped in meanwhile: nothing to broadcast to

    r.cycle.run_days = swap
    r.updates["UPD-3"] = Run("UPD-3")
    assert state._one_day("UPD-3") == str(UpdateState.DONE) and r.broadcasts == 1


def test_headless_drive_defers_reviews_and_goes_on(state):
    async def go():
        state.load(interactive=False)
        state.interactive = False
        r = state.runner
        r.updates["UPD-1"] = Run(state=UpdateState.AWAITING_REVIEW)
        r.pending = "UPD-1"

        def run_days(run, max_days):
            # the first day pauses for review; deferred and resumed, the second finishes
            r.days.append(run.id)
            run.state = UpdateState.AWAITING_REVIEW if len(r.days) == 1 else UpdateState.DONE

        r.cycle.run_days = run_days
        r.updates["UPD-1"].state = UpdateState.RUNNING
        out = await state.drive("UPD-1")
        assert out == str(UpdateState.DONE) and r.days == ["UPD-1", "UPD-1"] and r.steps == 1

    asyncio.run(go())


def test_headless_drive_stops_when_the_run_is_gone(state):
    async def go():
        state.load(interactive=False)
        state.interactive = False
        r = state.runner

        def run_days(run, max_days):
            run.state = UpdateState.AWAITING_REVIEW
            r.updates.clear()                      # a rewind dropped it

        r.cycle.run_days = run_days
        r.updates["UPD-1"] = Run()
        assert await state.drive("UPD-1") == "done"

    asyncio.run(go())


def test_start_drive_keeps_playing_afterwards_and_never_drives_twice(state, monkeypatch):
    played = []

    async def play_loop(st, until):
        played.append(until)

    monkeypatch.setattr("axelrod_wm.api.routes._play_loop", play_loop)

    async def go():
        state.load()
        state.runner.updates["UPD-1"] = Run()
        state.play_requested = True
        state.start_drive("UPD-1")
        first = state.update_task
        state.start_drive("UPD-1")                # already driving: no second task
        assert state.update_task is first
        await first
        await state.play_task
        assert played == [None]

    asyncio.run(go())


# -- the daily schedule ---------------------------------------------------------------------------------------
class Stop(Exception):
    pass


@pytest.mark.parametrize("daily_at, first_wait", [("06:00", 18 * 3600), ("18:00", 6 * 3600)])
def test_daily_schedule_requests_an_update_each_day(monkeypatch, daily_at, first_wait):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 5, 20, 12, 0, tzinfo=tz)

    monkeypatch.setattr(app_mod, "datetime", Clock)
    requests, driven, sleeps = [], [], []
    ctl = SimpleNamespace(config=SimpleNamespace(update=SimpleNamespace(timezone="UTC", daily_at=daily_at)),
                          active_update="UPD-0",
                          request_update=lambda req, run_to_end: requests.append(req) or SimpleNamespace(id="UPD-9"))

    async def call(fn):
        return fn()

    st = SimpleNamespace(runner=SimpleNamespace(controller=ctl), start_drive=driven.append, call=call)

    async def sleep(s):
        # the first wake finds a run still active (that day is skipped); it finishes before the second
        sleeps.append(s)
        if len(sleeps) == 2:
            ctl.active_update = None
        if len(sleeps) == 3:
            raise Stop

    monkeypatch.setattr(app_mod.asyncio, "sleep", sleep)
    with pytest.raises(Stop):
        asyncio.run(app_mod._daily_schedule(st))
    assert sleeps[0] == first_wait and len(requests) == 1 and driven == ["UPD-9"]
    assert requests[0].requested_by == "schedule" and requests[0].until.isoformat() == (
        "2026-05-21" if daily_at == "06:00" else "2026-05-20")


# -- startup, shutdown, error handlers, and the web files --------------------------------------------------------
def test_default_storage_lives_under_var(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app(scenario="small_demo", trace_dir=None, load_on_startup=False)
    with TestClient(app) as c:
        assert c.get("/api/session").json() == {"login": None}
    st = app.state.axelrod
    assert isinstance(st.storage, FilesBackend) and (tmp_path / "var/axelrod/demo/snapshots").is_dir()
    assert st.runner is None                      # nothing was loaded, and shutdown had no runner to pause


def test_start_at_an_example_and_schedule_daily_updates(tmp_path):
    cfg = deep_merge(yaml.safe_load(DEFAULT_CONFIG_PATH.read_text()), {"update": {"auto_daily": True}})
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(cfg))
    app = create_app(str(path), scenario="small_demo", storage=MemoryBackend(), trace_dir=None, play_delay=0.0,
                     start_example="create")
    with TestClient(app) as c:
        st = app.state.axelrod
        assert st.schedule_task is not None and not st.schedule_task.done()
        assert c.get("/api/sim/status").json()["pending_proposals"] >= 1
        task = st.schedule_task
    assert task.cancelled() or task.done()


def test_error_handlers_map_engine_errors_to_status_codes():
    from pydantic import BaseModel

    from axelrod_wm.events.graph_update import EventValidationError
    from axelrod_wm.inference.decisions import DecisionError
    from axelrod_wm.inference.task import UnboundThesis
    from axelrod_wm.intake.translators import LLMNotConfigured

    class M(BaseModel):
        x: int

    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, load_on_startup=False)
    errors = {"unbound": UnboundThesis([{"op_index": 0}]), "decision": DecisionError("no"),
              "event": EventValidationError("bad"), "llm": LLMNotConfigured("none")}

    def raiser(name):
        def route():
            if name == "validation":
                M.model_validate({"x": "nope"})
            raise errors[name]
        return route

    for name in [*errors, "validation"]:
        app.router.add_api_route(f"/boom/{name}", raiser(name))
    routes = app.router.routes                      # the test routes go ahead of the web files mounted at /
    routes[0:0] = [routes.pop() for _ in range(len(errors) + 1)]
    with TestClient(app) as c:
        assert c.get("/boom/unbound").json() == {"unbound": [{"op_index": 0}]}
        assert c.get("/boom/decision").status_code == 409
        assert c.get("/boom/event").status_code == 422
        r = c.get("/boom/validation")
        assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["x"]
        r = c.get("/boom/llm")
        assert r.status_code == 501 and r.json() == {"detail": "none"}


def test_web_files_must_be_revalidated(monkeypatch, tmp_path):
    app = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, load_on_startup=False)
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    monkeypatch.setattr(app_mod, "WEB_DIR", tmp_path / "no_web")
    bare = create_app(scenario="small_demo", storage=MemoryBackend(), trace_dir=None, load_on_startup=False)
    with TestClient(bare) as c:
        assert c.get("/").status_code == 404
