"""The import bundle (`axelrod.import/v1`): research a collection agent has already read and categorized, ready to fold in.

A bundle is what an upstream agent hands the world model after scraping and sorting sources: dated items, each with
its source, a summary in the agent's words, the entities it is about, a category, and **signals**: the specific
claims the item makes about the model, each tied to the phrase that makes it. Ingestion produces bundles from
documents; the world model consumes them. This module is the whole format: it imports only the standard library and
pydantic, so either side can depend on it without the other.

Signals name the model's own ids. A signal whose ends are not in the model is dropped by the consumer (and reported),
so a bundle written for a richer model still imports into a smaller one.

    {"format": "axelrod.import/v1", "title": ..., "collected_by": ..., "collected_at": ..., "items": [
       {"id": "EM-001", "published_at": "2026-09-11T06:00:00Z", "source": "...", "source_type": "broker_research",
        "kind": "analyst", "headline": "...", "summary": "...", "entities": ["boj"], "tickers": ["8766 JP"],
        "category": "rates", "stance": "hawkish", "relevance": 0.9, "confidence": 0.8,
        "signals": [{"type": "observe", "value_of": "boj.policy_rate", "value": 1.25, "quote": "..."}]}]}
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

FORMAT = "axelrod.import/v1"


class _S(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote: str = ""                    # the phrase of the summary that makes this claim (highlighted in review)
    note: str = ""                     # the agent's reason, shown beside the change


class Observe(_S):
    """A reported level: a value is now this, in its native unit."""

    type: Literal["observe"]
    value_of: str
    value: float


class Move(_S):
    """A change to a value: relative (0.1 = +10%), absolute (native units), or standardized (sd)."""

    type: Literal["move"]
    value_of: str
    delta: float
    mode: Literal["relative", "absolute", "standardized"] = "absolute"


class Link(_S):
    """A causal link the item states: source drives target, with a sign, a size (target sd per source sd), and
    timing (mean days until it starts, builds, and how long it lasts; no duration is permanent)."""

    type: Literal["link"]
    source: str
    target: str
    label: str
    effect: float
    delay_days: float = 7.0
    lag_days: float = 30.0
    duration_days: float | None = None


class Support(_S):
    """Evidence for (or against) a link already in the model, named by its two ends."""

    type: Literal["support", "contradict"]
    source: str
    target: str
    strength: float = 0.5


Signal = Annotated[Observe | Move | Link | Support, Field(discriminator="type")]


class ImportItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    published_at: datetime
    occurred_at: datetime | None = None
    source: str
    source_type: Literal["broker_research", "expert_call", "news", "central_bank", "data", "filing",
                         "client_model", "other"] = "news"
    kind: Literal["news", "data", "analyst", "filing"] = "news"
    headline: str
    summary: str = ""
    url: str | None = None
    entities: list[str] = []           # the model's entity ids the agent tagged
    tickers: list[str] = []
    category: str = ""                 # the agent's topic, e.g. "rates", "fx", "earnings"
    stance: str = ""                   # e.g. "hawkish", "positive", "estimates down"
    relevance: float = Field(0.5, ge=0, le=1)     # to the book, as the agent judged it
    confidence: float = Field(0.7, ge=0, le=1)    # in its own reading
    tags: list[str] = []
    signals: list[Signal] = []


class ImportBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: Literal["axelrod.import/v1"] = FORMAT
    title: str = "Imported research"
    collected_by: str = "research agent"
    collected_at: datetime | None = None
    description: str = ""
    synthetic: bool = False            # made up for a demo or a test (the review shows a "synthetic" badge)
    items: list[ImportItem]


__all__ = ["FORMAT", "ImportBundle", "ImportItem", "Link", "Move", "Observe", "Signal", "Support"]
