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


class MarketEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: MarketEventKind
    source: str                       # feed or publisher name
    headline: str
    body: str = ""
    published_at: datetime
    occurred_at: datetime
    data: dict[str, float] = {}       # DATA events: series id -> value
    mentions: list[str] = []
    tags: list[str] = []              # e.g. ["energy-shock-like"]; copied into episodes
    event_type: str | None = None     # optional hint, e.g. "financial_stress" for history regimes
    url: str | None = None
    synthetic: bool = False           # True for demo events; the UI shows a "Synthetic" badge
