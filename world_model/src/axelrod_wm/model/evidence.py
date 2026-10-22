"""Provenance and evidence (§6.5)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Origin(StrEnum):
    CONSTRUCTION = "construction"
    EVENT_PARSING = "event_parsing"
    FRONTIER_PROMOTION = "frontier_promotion"
    INFERENCE = "inference"
    HUMAN = "human"
    SEED = "seed"


class SourceType(StrEnum):
    NEWS = "news"
    DATA = "data"
    FILING = "filing"
    ANALYST = "analyst"
    HUMAN = "human"
    MODEL = "model"
    HISTORY = "history"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_type: SourceType
    source_ref: str | None = None     # URL, dataset id, or document id
    excerpt: str | None = None
    observed_at: datetime
    strength: float = 0.5             # 0..1, how far this item should move beliefs
    market_event_id: str | None = None
    user_confidence: float | None = None   # the reviewer's confidence in it (Oct 8); strength already includes it


MAX_EVIDENCE = 50
