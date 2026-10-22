"""A tiny engine on a hand-built graph, for the dynamics and shared coverage tests."""

from __future__ import annotations

from datetime import datetime, timezone

from axelrod_wm.engine.engine import Engine
from axelrod_wm.memory.working import DeviationPoint, point_key
from axelrod_wm.model.graph import CausalGraph
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.trace import NullTracer
from tests.conftest import VOCAB, make_config
from tests.unit.model.graphkit import small_graph

NOW = datetime(1970, 1, 21, 23, 59, 59, tzinfo=timezone.utc)   # end of day 20 (the engine's origin is 1970-01-01)


class ListTracer(NullTracer):
    """A tracer that keeps what it is asked to emit."""

    enabled = True
    muted = 0

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple] = []

    def emit(self, phase, kind, **kw):
        self.events.append((phase, kind, kw))


def tiny_engine(graph: CausalGraph | None = None, z: dict[str, list[float]] | None = None, today: int = 20,
                tracer=None, **config) -> Engine:
    """An engine whose working memory holds `graph` (small_graph by default) and the given daily z
    (each list is days 0..), with day `today` the last processed day."""
    eng = Engine(make_config(**config), MemoryBackend(), tracer or NullTracer(), vocab=VOCAB)
    g = graph if graph is not None else small_graph()
    with eng.mutator.begin("setup", at=NOW) as txn:
        for e in g.entities.values():
            txn.add("wm.graph.entities", e)
        for s in g.subentities.values():
            txn.add("wm.graph.subentities", s)
        for i in g.interactions.values():
            txn.add("wm.graph.interactions", i)
        for inst in g.instances.values():
            txn.add("wm.graph.instances", inst)
        for sid, zs in (z or {}).items():
            for d, v in enumerate(zs):
                txn.add("wm.deviations.points", DeviationPoint(z=v, var=0.1, level=0.0), key=point_key(sid, d))
    eng.wm.last_processed_day = today
    eng.wm.clock = NOW
    return eng
