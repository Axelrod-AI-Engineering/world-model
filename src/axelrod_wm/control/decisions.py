"""Decisions and the learning loop (§8.15, G5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from axelrod_wm.engine.explain_records import Explanation
from axelrod_wm.engine.performance.records import Forecast


class Outcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_at: datetime
    realized: dict[str, float]           # target -> realized standardized deviation
    crps: float
    notes: str = ""


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    agent_id: str
    recommendation: str
    rationale: str = ""
    forecast_ids: list[str]
    thesis_ids: list[str]
    state_version: int
    created_at: datetime
    review_after: datetime
    outcome: Outcome | None = None


class DecisionTrace(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    decision: DecisionRecord
    forecasts: list[Forecast]
    explanations: list[Explanation]
    state_hash_at_version: str
    view_at_version: Any                 # GraphView (api/views.py)
    changes_since: list[str]             # ChangeSet ids recorded after the decision's version
    hash_verified: bool = False


class DecisionError(ValueError):
    pass
