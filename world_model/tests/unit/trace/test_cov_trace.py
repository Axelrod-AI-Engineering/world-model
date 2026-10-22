"""Tracing: plain-value conversion, scopes, recording to memory and to a file, and broadcasting."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel

from axelrod_wm.trace import BroadcastTracer, NullTracer, Phase, RecordingTracer, _plain

AT = datetime(2024, 3, 1, 12, 0, tzinfo=timezone.utc)


class _M(BaseModel):
    a: int
    when: datetime


class _BadItem:
    def item(self):
        raise ValueError("no scalar")

    def __str__(self) -> str:
        return "bad-item"


def test_plain_turns_values_into_json_ready_ones():
    assert _plain(_M(a=1, when=AT)) == {"a": 1, "when": "2024-03-01T12:00:00Z"}
    assert _plain({1: (2, 3)}) == {"1": [2, 3]}
    assert _plain([np.float64(1.5), np.int64(2)]) == [1.5, 2]
    assert _plain({"b", "a"}) == ["a", "b"]
    assert _plain(frozenset({3, 1})) == [1, 3]
    assert _plain(AT) == "2024-03-01T12:00:00+00:00"
    assert _plain(_BadItem()) == "bad-item"
    assert _plain(float("nan")) is None
    assert _plain(2.5) == 2.5
    assert _plain("x") == "x"


def test_scoped_sets_and_restores_the_scope():
    t = NullTracer()
    assert t.scope is None
    with t.scoped("ME-1"):
        assert t.scope == "ME-1"
        with t.scoped(None):                   # None keeps the enclosing scope
            assert t.scope == "ME-1"
        with t.scoped("TH-1"):
            assert t.scope == "TH-1"
        assert t.scope == "ME-1"
    assert t.scope is None
    assert t.emit(Phase.INIT, "x") is None


def test_set_context_only_changes_what_is_given():
    t = NullTracer()
    t.set_context()
    assert t.state_version == 0
    t.set_context(sim_time=AT)
    assert t.sim_time == AT and t.state_version == 0
    t.set_context(state_version=7)
    assert t.sim_time == AT and t.state_version == 7


def test_recording_tracer_keeps_events_and_appends_them_to_its_file(tmp_path):
    t = RecordingTracer(run_id="r1", directory=tmp_path / "traces", keep=2)
    t.set_context(sim_time=AT, state_version=3)
    with t.scoped("ME-9"):
        t.emit("init", "a", refs=["x", 1], n=np.int64(4))
    t.emit(Phase.DAILY, "b")
    t.emit(Phase.DAILY, "c")
    assert t.last_seq == 3
    assert [e.kind for e in t.events] == ["b", "c"]          # only the last `keep`
    assert [e.kind for e in t.since(2)] == ["c"]
    lines = (tmp_path / "traces" / "r1.jsonl").read_text().splitlines()
    first = json.loads(lines[0])
    assert len(lines) == 3 and first["refs"] == ["x", "1"] and first["payload"] == {"n": 4}
    assert first["scope"] == "ME-9" and first["state_version"] == 3 and first["phase"] == "init"
    assert t.export(tmp_path / "out" / "e.jsonl") == 2
    assert len((tmp_path / "out" / "e.jsonl").read_text().splitlines()) == 2


def test_recording_tracer_skips_events_when_disabled_or_muted():
    t = RecordingTracer()
    t.enabled = False
    t.emit(Phase.INIT, "a")
    t.enabled = True
    t.muted = 1
    t.emit(Phase.INIT, "b")
    t.muted = 0
    t.emit(Phase.INIT, "c")
    assert [e.kind for e in t.events] == ["c"] and t.last_seq == 1


class _Loop:
    def __init__(self, closed: bool = False) -> None:
        self.closed = closed

    def call_soon_threadsafe(self, fn, msg):
        if self.closed:
            raise RuntimeError("loop closed")
        fn(msg)


class _Queue:
    def __init__(self) -> None:
        self.items = []

    def put_nowait(self, msg):
        self.items.append(msg)


def test_broadcast_tracer_pushes_each_event_to_live_subscribers():
    t = BroadcastTracer(run_id="b1")
    live, gone, dropped = _Queue(), _Queue(), _Queue()
    t.subscribe(_Loop(), live)
    t.subscribe(_Loop(closed=True), gone)        # a closed loop is skipped
    t.subscribe(_Loop(), dropped)
    t.unsubscribe(dropped)
    t.emit(Phase.SCENARIO, "caption", text="hi")
    assert len(live.items) == 1 and not gone.items and not dropped.items
    msg = live.items[0]
    assert msg["type"] == "trace" and msg["event"]["kind"] == "caption" and msg["event"]["payload"] == {"text": "hi"}
    t.broadcast({"type": "status"})
    assert live.items[-1] == {"type": "status"}
