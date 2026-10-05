"""Explanation records (§8.10). Re-exported by ``engine.explain``.

# DECISION: the pydantic records live in this small module so that memory modules can import
# them without pulling in the explainer implementation (which depends on the engine).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.serialization import StrSet


class PathContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interaction_ids: list[str]
    shock_id: str
    target_id: str
    gain: float          # product of mean effects along the path, times the kernels' value at the horizon
    share: float


class Explanation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                                       # EX-... for learning; EX-<forecast id> for forecasts
    subject_kind: Literal["forecast", "learning"]
    subject_id: str
    state_version: int
    created_at: datetime
    key_interactions: list[tuple[str, float]]     # (interaction id, contribution)
    top_paths: list[PathContribution]
    analogs: list[tuple[str, float]]              # (episode id, attention)
    networks: list[tuple[str, float]]             # (network id, share)
    scenarios: list[tuple[str, float]]            # (scenario name, weight)
    assumptions: list[str]                        # branched hypotheses and absent relations
    notes: list[str]                              # prefill adjustments
    text: str
    index_keys: StrSet                            # generalization and pattern ids, for later recall
    frontier_changes: list[str] = []              # learning: frontier entries logged, verified, or proposed
    pending_touched: list[str] = []               # learning: pending refinements touched
