"""Interactions: binary, directional, labeled causal relations between subentities (§6.7)."""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Optional

import numpy as np
from pydantic import BaseModel, ConfigDict
from scipy import special

from axelrod_wm.core.distributions import Beta, Distribution, DistSummary, summarize_samples
from axelrod_wm.core.evidence import Evidence, Origin
from axelrod_wm.core.temporal import KernelSpec, TimeState

REVERSE_SUFFIX = "~r"


class Direction(StrEnum):
    UNIDIRECTIONAL = "unidirectional"
    BIDIRECTIONAL = "bidirectional"


class EdgeType(StrEnum):
    CAUSAL = "causal"
    LEARNED_CAUSAL = "learned_causal"     # promoted from the correlation frontier


class EdgeDynamics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effect: Distribution      # impact magnitude: target standard units per source standard unit
    kernel: KernelSpec        # delay, lag, duration


class ParameterForm(StrEnum):
    MULTIPLICATIVE = "multiplicative"     # beta_eff = beta * (1 + gamma * z_mod)
    THRESHOLD = "threshold"               # beta_eff = beta if z_mod > threshold else 0
    ADDITIVE = "additive"                 # adds gamma * z_mod to the target


class ParameterBinding(BaseModel):
    """Brings a third input into a binary edge."""

    model_config = ConfigDict(extra="forbid")

    name: str                             # e.g. "household debt level"
    moderator_id: str                     # subentity id
    form: ParameterForm = ParameterForm.MULTIPLICATIVE
    coefficient: Distribution             # gamma
    threshold: float | None = None        # standardized units, for THRESHOLD


def abs_mean(effect: Distribution) -> float:
    """E|effect| (the folded-normal mean for a Gaussian)."""
    mu, sd = effect.mean(), effect.sd()
    if sd <= 1e-12:
        return abs(mu)
    return float(sd * math.sqrt(2.0 / math.pi) * math.exp(-mu * mu / (2 * sd * sd))
                 + mu * (1.0 - 2.0 * special.ndtr(-mu / sd)))


_GRID = (np.arange(41) + 0.5) / 41.0


class Interaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str                        # subentity id
    target_id: str                        # subentity id
    label: str                            # how A affects B, e.g. "raises saving"
    direction: Direction = Direction.UNIDIRECTIONAL
    edge_type: EdgeType = EdgeType.CAUSAL
    origin: Origin
    existence: Beta                       # probability that the relation holds
    forward: EdgeDynamics                 # source -> target
    reverse: Optional[EdgeDynamics] = None   # target -> source; only when BIDIRECTIONAL
    parameters: list[ParameterBinding] = []
    evidence: list[Evidence] = []
    time_states: list[TimeState] = []
    generalization_id: str | None = None
    internal: bool = False                # source and target belong to the same entity
    tags: list[str] = []                  # e.g. ["demo_addition"]
    created_at: datetime
    retired_at: datetime | None = None
    prior_source_id: str | None = None    # generalization the priors came from (set by classification)
    evidence_dropped: int = 0             # evidence records beyond the 50 kept

    def channels(self) -> list[tuple[str, str, EdgeDynamics]]:
        """One (source, target, dynamics) triple, or two for a bidirectional edge."""
        out = [(self.source_id, self.target_id, self.forward)]
        if self.direction == Direction.BIDIRECTIONAL and self.reverse is not None:
            out.append((self.target_id, self.source_id, self.reverse))
        return out

    def channel_items(self) -> list[tuple[str, str, str, EdgeDynamics]]:
        """(channel key, source, target, dynamics); the reverse channel's key is ``<id>~r``."""
        out = [(self.id, self.source_id, self.target_id, self.forward)]
        if self.direction == Direction.BIDIRECTIONAL and self.reverse is not None:
            out.append((self.id + REVERSE_SUFFIX, self.target_id, self.source_id, self.reverse))
        return out

    def polarity(self) -> int:
        """Sign of the forward effect's mean."""
        return 1 if self.forward.effect.mean() >= 0 else -1

    def significance_mean(self) -> float:
        """E[existence] * E|effect|: the weight used for path costs and ranking."""
        return self.existence.mean() * abs_mean(self.forward.effect)

    def significance(self) -> DistSummary:
        """Weight of causal significance now: w = existence * |effect|.
        The weight's history over time is kept in time_states["significance"].
        Computed on a deterministic quantile grid (no randomness)."""
        e = np.asarray(self.existence.quantile(_GRID), dtype=float)
        f = np.abs(np.asarray(self.forward.effect.quantile(_GRID), dtype=float))
        w = np.outer(e, f).ravel()
        s = summarize_samples(w)
        return s.model_copy(update={"mean": self.significance_mean()})

    def confidence(self) -> float:
        """P(the edge exists) * P(its sign is right) = E[existence] * Phi(|mu| / sigma)."""
        mu, sd = self.forward.effect.mean(), self.forward.effect.sd()
        p_sign = 1.0 if sd <= 1e-12 else float(special.ndtr(abs(mu) / sd))
        return self.existence.mean() * p_sign

    @property
    def active(self) -> bool:
        return self.retired_at is None


def base_interaction_id(channel_key: str) -> str:
    return channel_key[: -len(REVERSE_SUFFIX)] if channel_key.endswith(REVERSE_SUFFIX) else channel_key
