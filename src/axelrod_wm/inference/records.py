"""Inference-task records (§8.9). Re-exported by ``inference.task``.

# DECISION: records live here so memory modules can import Forecast without importing the task.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict

from axelrod_wm.dynamics.propagation import Channel, PropagationResult, ShockInput
from axelrod_wm.inference.transmission import TransmissionEntry
from axelrod_wm.model.distributions import DistSummary


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
    boundary: dict[str, np.ndarray] = {}    # subentity -> exogenous input [samples, days]


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
    summary_days: list[int] = []                   # the days the scenario summaries refer to
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


class ForecastGroup(BaseModel):
    """The forecast for a coarser target (addition): the average standardized effect of its subentities,
    mixed across scenarios like any target."""

    model_config = ConfigDict(extra="forbid")

    id: str                                        # "<kind>:<ref>"
    kind: str                                      # entity | superentity | sector | category
    ref: str
    name: str
    members: list[str]                             # the subentities averaged
    effect_summary: list[DistSummary]              # per day, in standard deviations
    effect_density: list[list[float]] = []         # at the horizon: (effect, density / peak)
    top: list[list[Any]] = []                      # [subentity, median effect at the horizon], largest first
    split: dict = {}                               # at the horizon: the baseline and the forecast, apart (Oct 14)


class Forecast(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                                        # FC-<thesis id>-<n>
    thesis_id: str
    based_on_version: int
    config_hash: str
    seed: int
    created_at: datetime
    horizon_days: int
    targets: list[str]
    summary: dict[str, list[DistSummary]]          # levels: mixture, native units, per day
    effect_summary: dict[str, list[DistSummary]]   # effect of the thesis: standardized, per day
    scenarios: list[ForecastScenario]
    isolated: dict[str, dict[str, DistSummary]]    # network id -> target -> isolated effect at the horizon
    decomposition: dict[str, dict[str, float]]     # target -> {network id: isolated median, "coupling": rest}
    networks: list[NetworkSummary]
    explanation_id: str | None = None
    dropped_mass: float = 0.0
    z_summary: dict[str, list[DistSummary]] = {}   # levels in standardized units, per day
    question: str = ""
    is_baseline: bool = False                      # a thesis with no shocks
    start_day: int | None = None                   # day index of day 0 (the last processed day when posed)
    groups: list[ForecastGroup] = []               # coarser targets (entities, superentities, sectors, categories)
    effect_density: dict[str, list[list[float]]] = {}   # each target's effect at the horizon, as a small density
    movers: dict[str, float] = {}                  # the subentities it moves most: median effect at the horizon
    transmission: list[TransmissionEntry] = []    # every value reached: order, main path, timing (addition)
    shocked: list[str] = []                        # the subentities the thesis changes directly
    constraints_binding: dict[str, float] = {}     # subentity -> weighted share of samples a soft bound bent
    paths: dict | None = None                      # the transmission grid's source (inference/paths.py, Oct 11)
    split: dict[str, dict] = {}                    # each target at the horizon: the baseline and the forecast (Oct 14)
    scenario_table: dict = {}                      # bull, base, and bear bands of the draws, for the book (Oct 15)
