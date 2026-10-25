"""The play loop and the handlers that wait on background tasks (api/routes.py), driven with a stand-in runner so
each way a play can end is exercised deterministically."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest

from axelrod_wm.api import routes
from axelrod_wm.control.updates import UpdateState


class Runner:
    """A scripted runner: `plan[i]` says what step i does ("ok", "update:<state>", "review", "done", or "boom")."""

    def __init__(self, plan, *, state="idle", pending=None, run_state=UpdateState.RUNNING, proposals=()):
        self.script = SimpleNamespace(steps=list(plan))
        self.plan = list(plan)
        self.step_index = 0
        self.state = state
        self.playing = False
        self.error = None
        self._pause = threading.Event()
        self._pending = pending
        self.broadcasts = 0
        self.steps = []
        self.controller = SimpleNamespace(get_update=lambda rid: SimpleNamespace(state=run_state),
                                          pending_proposals=lambda: list(proposals))

    def pending_update(self):
        return self._pending

    def step(self, interactive):
        what = self.plan[self.step_index]
        self.steps.append(self.step_index)
        self.step_index += 1
        if what == "boom":
            raise RuntimeError("step failed")
        if what.startswith("update:"):
            self._pending = what.split(":", 1)[1]
            self.state = "running"
        elif what == "done":
            self.state = "done"
        elif what == "pause":
            self._pause.set()
        return SimpleNamespace(model_dump=lambda mode: {"step": self.step_index})

    def status(self):
        return SimpleNamespace(model_dump=lambda mode: {"state": self.state, "playing": self.playing})

    def pause(self):
        return self.status()

    def _broadcast(self):
        self.broadcasts += 1


class State:
    def __init__(self, runner, drive_result="done"):
        self.runner = runner
        self.play_delay = 0.0
        self.play_task = None
        self.update_task = None
        self.play_requested = False
        self.emitted = []
        self.tracer = SimpleNamespace(emit=lambda *a, **k: self.emitted.append((a, k)))
        self.drive_result = drive_result
        self.driven = []

    async def call(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def drive(self, run_id):
        self.driven.append(run_id)
        self.runner._pending = None
        return self.drive_result

    def ensure_loaded(self):
        return self.runner


def play(st, until=None):
    asyncio.run(routes._play_loop(st, until))


def test_play_runs_every_step_and_ends_idle():
    r = Runner(["ok", "ok", "ok"])
    play(State(r))
    assert r.steps == [0, 1, 2] and r.state == "idle" and not r.playing and r.broadcasts == 1


def test_play_stops_at_the_requested_step():
    r = Runner(["ok", "ok", "ok"])
    play(State(r), until=2)
    assert r.steps == [0, 1]


def test_play_drives_a_steps_update_and_stops_at_its_review():
    r = Runner(["update:UPD-1", "ok"])
    st = State(r, drive_result="awaiting_review")
    play(st)
    assert st.driven == ["UPD-1"] and r.steps == [0]


def test_play_drives_a_finished_update_and_goes_on():
    r = Runner(["update:UPD-1", "ok"])
    st = State(r, drive_result="done")
    play(st)
    assert st.driven == ["UPD-1"] and r.steps == [0, 1]


def test_play_stops_when_the_scenario_is_done_or_paused():
    r = Runner(["done", "ok"])
    play(State(r))
    assert r.steps == [0] and r.state == "done"
    r = Runner(["pause", "ok"])
    play(State(r))
    assert r.steps == [0]


def test_play_does_not_start_past_a_waiting_review():
    r = Runner(["ok"], pending="UPD-1", run_state=UpdateState.AWAITING_REVIEW)
    play(State(r))
    assert r.steps == []
    r = Runner(["ok"], state="awaiting_review", proposals=["PR-1"])
    play(State(r))
    assert r.steps == [] and r.state == "awaiting_review"
    # a pending update that is still running does not stop the play
    r = Runner(["ok"], pending="UPD-1", run_state=UpdateState.RUNNING)
    play(State(r))
    assert r.steps == [0]


def test_a_failing_step_is_reported_not_swallowed():
    r = Runner(["boom"])
    st = State(r)
    play(st)
    assert r.error == "RuntimeError: step failed"
    ((args, kw),) = st.emitted
    assert args[1] == "scenario.error" and kw["error"] == r.error


# -- stopping a play ---------------------------------------------------------------------------------------
def test_stop_play_pauses_the_runner_and_waits_for_the_task():
    async def go():
        st = State(Runner(["ok"]))
        st.play_task = asyncio.create_task(asyncio.sleep(0.01))
        await routes._stop_play(st)
        assert st.runner._pause.is_set() and st.play_task is None
        # without a runner, the task is still awaited
        st = State(None)
        task = asyncio.create_task(asyncio.sleep(0.01))
        st.play_task = task
        await routes._stop_play(st)
        assert task.done() and st.play_task is None

    asyncio.run(go())


def test_stop_play_cancels_a_task_that_will_not_stop(monkeypatch):
    async def wait_for(aw, timeout):
        aw.cancel()
        raise TimeoutError

    async def go():
        monkeypatch.setattr(routes.asyncio, "wait_for", wait_for)
        st = State(Runner(["ok"]))
        task = asyncio.create_task(asyncio.sleep(10))
        st.play_task = task
        await routes._stop_play(st)
        await asyncio.sleep(0)
        assert task.cancelled() and st.play_task is None

    asyncio.run(go())


def request_for(st):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(axelrod=st, axelrod_by_login={}, views={})), scope={})


def test_play_while_playing_and_play_while_waiting_on_review():
    async def go():
        r = Runner(["ok"], state="awaiting_review", proposals=["PR-1"])
        st = State(r)
        out = await routes.sim_play(request_for(st), None)
        assert out == {"state": "awaiting_review", "playing": False} and st.play_requested
        await st.play_task
        busy = asyncio.create_task(asyncio.sleep(0.01))
        st.play_task = busy
        await routes.sim_play(request_for(st), routes.PlayBody(until_step=1))
        assert st.play_task is busy                # a second play does not start another loop
        await busy

    asyncio.run(go())


def test_pause_waits_for_the_running_play():
    async def go():
        st = State(Runner(["ok"]))
        st.play_requested = True
        st.play_task = asyncio.create_task(asyncio.sleep(0.01))
        out = await routes.sim_pause(request_for(st))
        assert out["state"] == "idle" and st.play_task is None and not st.play_requested
        assert st.runner._pause.is_set()

    asyncio.run(go())


def test_cancel_waits_for_the_running_update(monkeypatch):
    runs = {"UPD-1": SimpleNamespace(cancel_requested=False)}
    cancelled = []
    ctl = SimpleNamespace(get_update=runs.__getitem__, cancel_update=cancelled.append)
    monkeypatch.setattr(routes, "update_run_view", lambda run, c: {"cancel_requested": run.cancel_requested})

    async def go():
        r = Runner(["ok"], pending="UPD-1")
        r.controller = ctl
        st = State(r)
        st.controller = ctl
        st.update_task = asyncio.create_task(asyncio.sleep(0.01))
        out = await routes.cancel_update(request_for(st), "UPD-1")
        assert out == {"cancel_requested": True} and cancelled == ["UPD-1"]
        assert r.steps == [0]                       # the step waiting on the run finishes

    asyncio.run(go())


def test_cancel_and_pause_give_up_waiting_on_a_task_that_will_not_stop(monkeypatch):
    runs = {"UPD-1": SimpleNamespace(cancel_requested=False)}
    cancelled = []
    ctl = SimpleNamespace(get_update=runs.__getitem__, cancel_update=cancelled.append)
    monkeypatch.setattr(routes, "update_run_view", lambda run, c: {"cancel_requested": run.cancel_requested})

    async def wait_for(aw, timeout):
        raise TimeoutError

    async def go():
        r = Runner(["ok"])
        st = State(r)
        st.controller = ctl
        # no run in the background: cancel at once
        assert await routes.cancel_update(request_for(st), "UPD-1") == {"cancel_requested": False}
        monkeypatch.setattr(routes.asyncio, "wait_for", wait_for)
        stuck = asyncio.get_running_loop().create_future()
        st.update_task = stuck
        assert await routes.cancel_update(request_for(st), "UPD-1") == {"cancel_requested": True}
        st.play_task = stuck
        out = await routes.sim_pause(request_for(st))
        assert out["state"] == "idle" and st.play_task is None
        stuck.cancel()
        assert cancelled == ["UPD-1", "UPD-1"] and r.steps == []

    asyncio.run(go())


def test_resume_if_awaited_leaves_an_undecided_proposal_waiting():
    run = SimpleNamespace(id="UPD-1", state=UpdateState.AWAITING_REVIEW, waiting_on="PR-1")
    resumed = []
    ctl = SimpleNamespace(active_update="UPD-1", updates={"UPD-1": run},
                          proposals={"PR-1": SimpleNamespace(status="pending")},
                          cycle=SimpleNamespace(resume=lambda r, run_to_end: resumed.append(r.id)))
    st = SimpleNamespace(controller=ctl)
    assert routes._resume_if_awaited(st, "PR-1") is None and resumed == []
    ctl.proposals["PR-1"].status = "approved"
    assert routes._resume_if_awaited(st, "PR-1") == "UPD-1" and resumed == ["UPD-1"]


@pytest.mark.parametrize("model, out", [([1, "a"], [1, "a"]), ("x", "x"), (None, None)])
def test_json_passes_plain_values_through(model, out):
    assert routes._json(model) == out
