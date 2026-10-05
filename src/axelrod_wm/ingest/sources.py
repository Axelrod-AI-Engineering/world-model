"""Market event sources and the monitor (§7.8)."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from axelrod_wm.events.market import MarketEvent

if TYPE_CHECKING:
    from axelrod_wm.control.review import Proposal
    from axelrod_wm.ingest.pipeline import IngestionPipeline

SCENARIO_ONLY_FIELDS = ("world_shocks",)


def parse_market_event(data: dict) -> tuple[MarketEvent, dict]:
    """Strip scenario-only fields (world_shocks) before validation; return them separately."""
    extra = {k: data[k] for k in SCENARIO_ONLY_FIELDS if k in data}
    clean = {k: v for k, v in data.items() if k not in SCENARIO_ONLY_FIELDS}
    return MarketEvent.model_validate(clean), extra


class MarketEventSource(ABC):
    @abstractmethod
    def poll(self, until: datetime) -> list[MarketEvent]:
        """Market events published up to `until` that have not been returned before."""


class JsonlReplaySource(MarketEventSource):
    """Replays a market_events.jsonl file in published_at order."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.events: list[MarketEvent] = []
        self.extras: dict[str, dict] = {}
        for line in self.path.read_text().splitlines():
            if line.strip():
                ev, extra = parse_market_event(json.loads(line))
                self.events.append(ev)
                self.extras[ev.id] = extra
        self.events.sort(key=lambda e: (e.published_at, e.id))
        self._cursor = 0

    def get(self, event_id: str) -> MarketEvent | None:
        return next((e for e in self.events if e.id == event_id), None)

    def poll(self, until: datetime) -> list[MarketEvent]:
        out = []
        while self._cursor < len(self.events) and self.events[self._cursor].published_at <= until:
            out.append(self.events[self._cursor])
            self._cursor += 1
        return out

    def reset(self) -> None:
        self._cursor = 0


class Monitor:
    """Polls its sources at each simulated (or real) tick and hands new events to the pipeline."""

    def __init__(self, sources: list[MarketEventSource], pipeline: IngestionPipeline) -> None:
        self.sources = sources
        self.pipeline = pipeline

    def tick(self, now: datetime) -> list[Proposal]:
        events: list[MarketEvent] = []
        for src in self.sources:
            events.extend(src.poll(now))
        out: list[Any] = []
        for ev in sorted(events, key=lambda e: (e.published_at, e.id)):
            out.extend(self.pipeline.ingest(ev, ev.published_at))
        return out
