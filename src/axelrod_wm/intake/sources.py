"""Market event sources (§7.8). An update run polls each configured source for the window since
its cursor; scrapers, data feeds, and the history replay all plug in behind the same interface."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from axelrod_wm.engine.registry import register, registry
from axelrod_wm.events.market import MarketEvent, MarketEventChannel

SCENARIO_ONLY_FIELDS = ("world_shocks",)


def parse_market_event(data: dict) -> tuple[MarketEvent, dict]:
    """Strip scenario-only fields (world_shocks) before validation; return them separately."""
    extra = {k: data[k] for k in SCENARIO_ONLY_FIELDS if k in data}
    clean = {k: v for k, v in data.items() if k not in SCENARIO_ONLY_FIELDS}
    return MarketEvent.model_validate(clean), extra


def load_market_events(path: str | Path) -> tuple[list[MarketEvent], dict[str, dict]]:
    """Every MarketEvent in a JSONL file (in published_at order) and its scenario-only fields."""
    events: list[MarketEvent] = []
    extras: dict[str, dict] = {}
    p = Path(path)
    if not p.exists():
        return events, extras
    for line in p.read_text().splitlines():
        if line.strip():
            ev, extra = parse_market_event(json.loads(line))
            events.append(ev)
            extras[ev.id] = extra
    events.sort(key=lambda e: (e.published_at, e.id))
    return events, extras


def in_window(t: datetime, since: datetime | None, until: datetime) -> bool:
    return (since is None or t > since) and t <= until


class MarketEventSource(ABC):
    name: str = ""

    @abstractmethod
    def poll(self, since: datetime | None, until: datetime) -> list[MarketEvent]:
        """Market events with since < published_at <= until (since=None means from the start)."""


registry("source", MarketEventSource)


@register("source", "jsonl_replay")
class JsonlReplaySource(MarketEventSource):
    """Replays a market_events.jsonl file (registered as `jsonl_replay`). It can be limited to one
    channel."""

    name = "jsonl_replay"

    def __init__(self, path: str | Path, channel: str | MarketEventChannel | None = None, config: Any = None,
                 **_: Any) -> None:
        self.path = Path(path)
        self.channel = MarketEventChannel(channel) if channel else None
        self.events, self.extras = load_market_events(self.path)

    def get(self, event_id: str) -> MarketEvent | None:
        return next((e for e in self.events if e.id == event_id), None)

    def poll(self, since: datetime | None, until: datetime) -> list[MarketEvent]:
        return [e for e in self.events if in_window(e.published_at, since, until)
                and (self.channel is None or e.channel == self.channel)]


@register("source", "history_replay")
class HistoryReplaySource(MarketEventSource):
    """Serves the history's market events (from the synthetic world's generate_history(), or a JSONL
    file) to the initialization's update run (§8.13)."""

    name = "history_replay"

    def __init__(self, events: list[MarketEvent] | None = None, path: str | Path | None = None,
                 config: Any = None, **_: Any) -> None:
        if events is None and path is not None:
            events, _ = load_market_events(path)
        self.events = sorted(events or [], key=lambda e: (e.published_at, e.id))

    def poll(self, since: datetime | None, until: datetime) -> list[MarketEvent]:
        return [e for e in self.events if in_window(e.published_at, since, until)]
