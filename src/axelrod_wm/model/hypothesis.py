"""Hypotheses about interactions and entity decisions (§6.10)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, model_validator

from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.ids import entity_of


class HypothesisKind(StrEnum):
    INTERACTION_PRESENT = "interaction_present"
    INTERACTION_ABSENT = "interaction_absent"
    ENTITY_DECISION = "entity_decision"


class HypothesisStatus(StrEnum):
    OPEN = "open"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    EXPIRED = "expired"


class Hypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: HypothesisKind
    statement: str
    # INTERACTION_*: an existing interaction, or a proposed source/target pair
    interaction_id: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    # ENTITY_DECISION: the decision variable, the decision, and its window
    decision_subentity_id: str | None = None
    decision_change: float | None = None      # native units; 0 means "holds"
    decision_window_days: int | None = None
    probability: float                        # current p that the hypothesis holds
    informational_value: float = 0.0          # VOI at scored_at (§8.11)
    scored_at: datetime
    half_life_days: float = 14.0
    status: HypothesisStatus = HypothesisStatus.OPEN
    origin: Origin
    subject_entity_ids: list[str] = []        # filled by a validator when empty (see below)
    created_at: datetime | None = None        # defaults to scored_at
    from_thesis: str | None = None            # set when a hypothetical event proposed it
    comovement_id: str | None = None          # the frontier entry that owns it, if any
    sensitivity: float = 0.0                  # the last computed forecast sensitivity
    sensitivity_at: datetime | None = None    # when it was computed (None: never)

    @model_validator(mode="after")
    def _fill(self) -> Hypothesis:
        if not self.subject_entity_ids:
            ids = [entity_of(x) for x in (self.source_id, self.target_id, self.decision_subentity_id) if x]
            self.subject_entity_ids = sorted(set(ids))
        if self.created_at is None:
            self.created_at = self.scored_at
        return self

    def current_value(self, now: datetime) -> float:
        """informational_value * 0.5 ** ((now - scored_at).days / half_life_days)"""
        days = (now - self.scored_at).total_seconds() / 86400.0
        return self.informational_value * 0.5 ** (max(days, 0.0) / max(self.half_life_days, 1e-9))
