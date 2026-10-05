"""Performance-task records (§8.9). Re-exported by ``engine.performance.task``.

# DECISION: records live here so memory modules can import Forecast without importing the task.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.core.distributions import DistSummary
from axelrod_wm.engine.propagation import Channel, PropagationResult, ShockInput


class NetworkKind(StrEnum):
    SUPERENTITY = "superentity"
    RESIDUAL = "residual"


class Network(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                              # NW-<thesis id>-<k>
    kind: NetworkKind
    instance_id: str | None              # the bound superentity instance; None for the residual network
    pattern_id: str | None
    subentity_ids: list[str]
    channels: list[Channel]              # dynamics_for(c, episode_ids)
    boundary_in: list[str] = []          # interaction ids entering from other kept networks
    boundary_out: list[str] = []
    forced_present: list[str] = []       # the pattern's present relations (forced on when it is the chosen rival)
    forced_absent: list[str] = []        # the pattern's present=False relations
    relevance: float
    episode_ids: list[str] = []          # model.network_episodes[instance]
    name: str = ""
    attention: float = 0.0
    reach: float = 0.0
    transient: bool = False


class NetworkInputs(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    shocks: list[ShockInput]
    boundary: dict[str, np.ndarray] = {}    # subentity -> exogenous input [samples, steps]


class NetworkPrediction(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    network_id: str
    result: PropagationResult


class ForecastScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    weight: float
    network_ids: list[str]
    forced_existence: dict[str, bool] = {}
    branched_hypothesis_ids: dict[str, bool] = {}
    summary: dict[str, list[DistSummary]] = {}
    effect_summary: dict[str, list[DistSummary]] = {}
    rival_choices: dict[str, str] = {}             # rival group key -> chosen network id


class NetworkSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: NetworkKind
    name: str
    relevance: float
    pattern_id: str | None
    subentity_ids: list[str]
    instance_id: str | None = None
    entity_ids: list[str] = []
    channel_ids: list[str] = []


class Forecast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                                        # FC-<thesis id>-<n>
    thesis_id: str
    based_on_version: int
    config_hash: str
    seed: int
    created_at: datetime
    step_days: float
    horizon_steps: int
    targets: list[str]
    summary: dict[str, list[DistSummary]]          # levels: mixture, native units, per step
    effect_summary: dict[str, list[DistSummary]]   # effect of the thesis: standardized, per step
    scenarios: list[ForecastScenario]
    isolated: dict[str, dict[str, DistSummary]]    # network id -> target -> isolated effect at the horizon
    decomposition: dict[str, dict[str, float]]     # target -> {network id: isolated median, "coupling": rest}
    networks: list[NetworkSummary]
    explanation_id: str | None = None
    dropped_mass: float = 0.0
    z_summary: dict[str, list[DistSummary]] = {}   # levels in standardized units, per step
    question: str = ""
    is_baseline: bool = False                      # a thesis with no shocks
