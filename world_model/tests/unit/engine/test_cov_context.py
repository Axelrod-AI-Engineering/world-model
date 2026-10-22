"""The hypothetical overlay and the process context's derived values."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from axelrod_wm.engine.context import GraphOverlay
from axelrod_wm.engine.engine import Engine
from axelrod_wm.repo.snapshots import MemoryBackend, empty_state
from axelrod_wm.trace import NullTracer
from tests.conftest import START, make_config


def test_overlay_ids_are_scoped_and_counted_per_prefix():
    wm, _ = empty_state()
    ov = GraphOverlay(wm, scope="T-01")
    assert [ov.next_id("inst"), ov.next_id("inst"), ov.next_id("H")] == ["inst-T-01-1", "inst-T-01-2", "H-T-01-1"]
    assert GraphOverlay(wm, scope="T-02").next_id("inst") == "inst-T-02-1"     # counters belong to one overlay


@pytest.mark.parametrize("collection", ["entities", "subentities", "interactions", "instances", "hypotheses"])
def test_overlay_put_never_touches_the_base(collection):
    wm, _ = empty_state()
    ov = GraphOverlay(wm, scope="T")
    obj = SimpleNamespace(id="x-1")
    ov.put(collection, obj)
    ov.put(collection, SimpleNamespace(id="x-2"))
    held = ov.wm.hypotheses if collection == "hypotheses" else getattr(ov.graph, collection)
    assert held["x-1"] is obj and ov.created == {collection: ["x-1", "x-2"]}
    base = wm.hypotheses if collection == "hypotheses" else getattr(wm.graph, collection)
    assert "x-1" not in base


def test_overlay_put_rejects_an_unknown_collection():
    wm, _ = empty_state()
    with pytest.raises(KeyError):
        GraphOverlay(wm, scope="T").put("patterns", SimpleNamespace(id="p"))


def test_context_step_days_and_overlay_wm():
    cfg = make_config(time={"step_days": 7})
    eng = Engine(cfg, MemoryBackend(), NullTracer())
    ctx = eng.context(learn=False, now=START)
    assert ctx.step_days == 7.0 and isinstance(ctx.step_days, float)
    assert ctx.wm is eng.wm
    ctx.overlay = GraphOverlay(eng.wm, scope="T")
    assert ctx.wm is ctx.overlay.wm and ctx.wm is not eng.wm
