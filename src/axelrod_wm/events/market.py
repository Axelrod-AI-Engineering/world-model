"""Market events: raw real-world input before translation (§7.1)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class MarketEventKind(StrEnum):
    NEWS = "news"
    DATA = "data"
    FILING = "filing"
    ANALYST = "analyst"


class MarketEventChannel(StrEnum):
    SCRAPER = "scraper"               # found by a web scraper
    DATA_FEED = "data_feed"           # released by a data source
    USER = "user"                     # typed in by the user with an update request


class MarketEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: MarketEventKind
    channel: MarketEventChannel
    source: str                       # feed, site, or publisher name; "user" for user events
    headline: str
    body: str = ""
    published_at: datetime            # when the information became available; decides the day it is folded in
    occurred_at: datetime             # when it happened in the world
    data: dict[str, float] = {}       # DATA events: series id -> value
    mentions: list[str] = []
    tags: list[str] = []              # e.g. ["energy-shock-like"]; copied into episodes
    event_type: str | None = None     # optional hint, e.g. "financial_stress" for history regimes
    url: str | None = None
    update_id: str | None = None      # the update run that collected it
    synthetic: bool = False           # True for demo events; the UI shows a "Synthetic" badge
