"""Tracing: the stream of events that feeds the animator (§10)."""

from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict


class Phase(StrEnum):
    INIT = "init"
    UPDATE = "update"
    COLLECT = "collect"
    DAILY = "daily"
    INGEST = "ingest"
    TRANSLATE = "translate"
    REFINE = "refine"
    REVIEW = "review"
    PARSE = "parse"
    CLASSIFY = "classify"
    RECALL = "recall"
    PREFILL = "prefill"
    ANALYZE = "analyze"
    FOLD = "fold"
    GENERALIZE = "generalize"
    FRONTIER = "frontier"
    ABDUCE = "abduce"
    ISOLATE = "isolate"
    PREDICT = "predict"
    COUPLE = "couple"
    UNIFY = "unify"
    EXPLAIN = "explain"
    READ_OUT = "read_out"
    CONSOLIDATE = "consolidate"
    EVALUATE = "evaluate"
    DECIDE = "decide"
    SCENARIO = "scenario"     # captions and runner events (addition)


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int
    run_id: str
    phase: Phase
    kind: str
    sim_time: datetime
    state_version: int
    refs: list[str] = []          # ids of the objects involved, for highlighting
    payload: dict = {}
    # what the event belongs to (addition): a market event id while it is ingested, reviewed, and folded;
    # a thesis id while it is posed; "day:<date>" for a day's predict, record, and consolidation. The
    # demo's walkthrough reads one scope's events as the steps the model took.
    scope: str | None = None


def _plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_plain(v) for v in value), key=str)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except Exception:  # noqa: BLE001
            return str(value)
    if isinstance(value, float) and value != value:  # NaN
        return None
    return value


class Tracer(ABC):
    run_id: str = "run"
    sim_time: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)
    state_version: int = 0
    enabled: bool = True
    scope: str | None = None

    @contextmanager
    def scoped(self, scope: str | None):
        """Tag the events emitted inside the block with `scope` (None keeps the enclosing scope)."""
        prev = self.scope
        if scope is not None:
            self.scope = scope
        try:
            yield
        finally:
            self.scope = prev

    @abstractmethod
    def emit(self, phase: Phase, kind: str, /, refs: list[str] | None = None, **payload: Any) -> None: ...

    def set_context(self, sim_time: datetime | None = None, state_version: int | None = None) -> None:
        if sim_time is not None:
            self.sim_time = sim_time
        if state_version is not None:
            self.state_version = state_version


class NullTracer(Tracer):
    def emit(self, phase: Phase, kind: str, /, refs: list[str] | None = None, **payload: Any) -> None:
        return None


class RecordingTracer(Tracer):
    """Keeps events in memory and appends them to var/axelrod/traces/<run_id>.jsonl."""

    def __init__(self, run_id: str = "run-1", directory: str | Path | None = None, keep: int = 200_000) -> None:
        self.run_id = run_id
        self.events: list[TraceEvent] = []
        self.keep = keep
        self._seq = 0
        self._lock = threading.Lock()
        self._path: Path | None = None
        if directory is not None:
            d = Path(directory)
            d.mkdir(parents=True, exist_ok=True)
            self._path = d / f"{run_id}.jsonl"
            self._path.write_text("")
        self.muted = 0

    @property
    def last_seq(self) -> int:
        return self._seq

    def emit(self, phase: Phase, kind: str, /, refs: list[str] | None = None, **payload: Any) -> None:
        if not self.enabled or self.muted:
            return
        with self._lock:
            self._seq += 1
            ev = TraceEvent(seq=self._seq, run_id=self.run_id, phase=Phase(phase), kind=kind,
                            sim_time=self.sim_time, state_version=self.state_version,
                            refs=[str(r) for r in (refs or [])], payload=_plain(payload), scope=self.scope)
            self.events.append(ev)
            if len(self.events) > self.keep:
                del self.events[: len(self.events) - self.keep]
            if self._path is not None:
                with self._path.open("a") as fh:
                    fh.write(ev.model_dump_json() + "\n")
        self._publish(ev)

    def _publish(self, ev: TraceEvent) -> None:
        return None

    def since(self, seq: int) -> list[TraceEvent]:
        return [e for e in self.events if e.seq > seq]

    def export(self, path: str | Path) -> int:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w") as fh:
            for e in self.events:
                fh.write(e.model_dump_json() + "\n")
        return len(self.events)


class BroadcastTracer(RecordingTracer):
    """Also pushes each event to WebSocket subscribers."""

    def __init__(self, run_id: str = "run-1", directory: str | Path | None = None, keep: int = 200_000) -> None:
        super().__init__(run_id, directory, keep)
        self._subscribers: list[tuple[Any, Any]] = []   # (event loop, asyncio.Queue)

    def subscribe(self, loop: Any, queue: Any) -> None:
        with self._lock:
            self._subscribers.append((loop, queue))

    def unsubscribe(self, queue: Any) -> None:
        with self._lock:
            self._subscribers = [(lp, q) for lp, q in self._subscribers if q is not queue]

    def broadcast(self, message: dict) -> None:
        """Queue a JSON-ready message for every subscriber (the queues are read on their own loops)."""
        with self._lock:
            subs = list(self._subscribers)
        for loop, queue in subs:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, message)
            except RuntimeError:
                pass

    def _publish(self, ev: TraceEvent) -> None:
        self.broadcast({"type": "trace", "event": json.loads(ev.model_dump_json())})
