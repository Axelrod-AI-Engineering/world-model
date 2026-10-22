"""Theses: questions that pose a hypothetical event (§7.2)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from axelrod_wm.events.graph_update import EventKind, GraphUpdateEvent


class ThesisMode(StrEnum):
    OPEN_ENDED = "open_ended"
    SCAFFOLDED = "scaffolded"         # the person also specifies changes (extra ops, interventions)


class TargetGroup(BaseModel):
    """A forecast target coarser than one subentity (addition): an entity, a superentity, a sector, or a
    category. Its forecast is the average standardized effect of its subentities."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["entity", "superentity", "sector", "category"]
    ref: str                          # an entity id, a pattern id, a sector name, or a category code

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.ref}"


class Thesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str                     # e.g. "What if oil prices doubled next quarter?"
    mode: ThesisMode
    event: GraphUpdateEvent           # kind must be HYPOTHETICAL
    horizon_days: int = 182
    targets: list[str] = []           # subentities to report; empty means everything that moves
    target_groups: list[TargetGroup] = []   # coarser targets: entities, superentities, sectors, categories
    posed_by: str
    posed_at: datetime
    pinned: bool = False              # pinned forecasts survive consolidation

    @model_validator(mode="after")
    def _hypothetical(self) -> Thesis:
        if self.event.kind != EventKind.HYPOTHETICAL:
            raise ValueError(f"thesis {self.id}: its event must be hypothetical")
        return self
