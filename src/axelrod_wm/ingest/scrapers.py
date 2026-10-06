"""Web scrapers: fetch items from the web and normalize them into market events (§7.8)."""

from __future__ import annotations

import hashlib
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.registry import register
from axelrod_wm.events.market import MarketEvent, MarketEventChannel, MarketEventKind
from axelrod_wm.ingest.sources import MarketEventSource, in_window, load_market_events


class ScrapedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    site: str
    title: str
    body: str
    published_at: datetime
    fetched_at: datetime
    # DECISION: a scraper may pass extra fields it already knows (an id, occurred_at, mentions, tags,
    # event_type, kind). The mock scraper uses this to keep the fixture ids that hand-drawn
    # translations are keyed by.
    meta: dict[str, Any] = {}


def normalize_title(title: str) -> str:
    """Lower case, punctuation removed, whitespace collapsed."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title.lower())).strip()


def url_event_id(url: str) -> str:
    return "ME-" + hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]


def dedup_keys(event: MarketEvent) -> list[str]:
    """Keys that identify the same item: its URL, and its site with its normalized title."""
    keys = []
    if event.url:
        keys.append(f"url:{event.url}")
    if event.channel == MarketEventChannel.SCRAPER:
        keys.append(f"title:{event.source}|{normalize_title(event.headline)}")
    return keys


class WebScraper(MarketEventSource, ABC):
    """Fetches items from the web and normalizes them into MarketEvents (kind NEWS, channel
    SCRAPER, id "ME-<first 10 hex of SHA-256 of the URL>", occurred_at = published_at unless the
    item says otherwise). Deduplicates by URL and by (site, normalized title)."""

    def __init__(self) -> None:
        self.last_dropped = 0          # duplicates dropped by the last poll

    @abstractmethod
    def fetch(self, since: datetime | None, until: datetime) -> list[ScrapedItem]: ...

    def normalize(self, item: ScrapedItem) -> MarketEvent:
        meta = item.meta
        return MarketEvent(
            id=str(meta.get("id") or url_event_id(item.url)),
            kind=MarketEventKind(meta.get("kind", MarketEventKind.NEWS)),
            channel=MarketEventChannel.SCRAPER, source=item.site, headline=item.title, body=item.body,
            published_at=item.published_at, occurred_at=meta.get("occurred_at") or item.published_at,
            mentions=list(meta.get("mentions", [])), tags=list(meta.get("tags", [])),
            event_type=meta.get("event_type"), url=item.url, synthetic=bool(meta.get("synthetic", False)))

    def poll(self, since: datetime | None, until: datetime) -> list[MarketEvent]:
        seen: set[str] = set()
        out: list[MarketEvent] = []
        self.last_dropped = 0
        for item in sorted(self.fetch(since, until), key=lambda i: (i.published_at, i.url)):
            ev = self.normalize(item)
            keys = dedup_keys(ev)
            if any(k in seen for k in keys):
                self.last_dropped += 1
                continue
            seen.update(keys)
            out.append(ev)
        return out


@register("source", "mock_web_scraper")
class MockWebScraper(WebScraper):
    """v0's scraper (registered as `mock_web_scraper`). Reads the scenario's market_events.jsonl and
    returns the entries with channel "scraper" published in the window, keeping their fixture ids
    so that hand-drawn translations still match. To exercise the real code paths, it can repeat an
    item under a second URL (dedup must drop it) and sleep a configurable latency."""

    name = "mock_web_scraper"

    def __init__(self, path: str | Path | None = None, latency_s: float = 0.0, config: Any = None,
                 scenario_dir: str | Path | None = None, **_: Any) -> None:
        super().__init__()
        if path is None and scenario_dir is not None:
            path = Path(scenario_dir) / "market_events.jsonl"
        self.path = Path(path) if path is not None else None
        self.latency_s = float(latency_s)
        self.events, self.extras = load_market_events(self.path) if self.path is not None else ([], {})

    def fetch(self, since: datetime | None, until: datetime) -> list[ScrapedItem]:
        if self.latency_s > 0:
            time.sleep(self.latency_s)
        out = []
        for e in self.events:
            if e.channel != MarketEventChannel.SCRAPER or not in_window(e.published_at, since, until):
                continue
            url = e.url or f"https://{re.sub(r'[^a-z0-9]+', '-', e.source.lower()).strip('-')}.example/{e.id.lower()}"
            out.append(ScrapedItem(url=url, site=e.source, title=e.headline, body=e.body,
                                   published_at=e.published_at, fetched_at=until,
                                   meta={"id": e.id, "kind": str(e.kind), "occurred_at": e.occurred_at,
                                         "mentions": e.mentions, "tags": e.tags, "event_type": e.event_type,
                                         "synthetic": e.synthetic}))
        return out
