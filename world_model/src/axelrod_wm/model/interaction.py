"""Interactions: binary, directional, labeled causal relations between subentities (§6.7)."""

from __future__ import annotations

import math
from datetime import datetime
from enum import StrEnum
from typing import Literal, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict
from scipy import special

from axelrod_wm.model.construction import ResponseState, Transition
from axelrod_wm.model.distributions import Beta, Distribution, DistSummary, summarize_samples
from axelrod_wm.model.evidence import Evidence, Origin
from axelrod_wm.model.temporal import KernelSpec, TimeState

REVERSE_SUFFIX = ":rev"


class Direction(StrEnum):
    UNIDIRECTIONAL = "unidirectional"
    BIDIRECTIONAL = "bidirectional"


class EdgeType(StrEnum):
    CAUSAL = "causal"
    LEARNED_CAUSAL = "learned_causal"     # promoted from the correlation frontier
    ACCOUNTING = "accounting"             # a part adds to its total (Oct 17): a fixed weight learning never refits
    IDENTITY = "identity"                 # a term of a product, ratio or difference identity (Oct 18): weight derived
    STOCK_FLOW = "stock_flow"             # a flow accumulating into a stock (Oct 18): weight derived, kernel integrates


FIXED_EDGE_TYPES = frozenset({EdgeType.ACCOUNTING, EdgeType.IDENTITY, EdgeType.STOCK_FLOW})


class Calibration(StrEnum):
    """Whether a link's size is estimated (Oct 17). An uncalibrated link keeps its mechanism, direction, and
    conditions but carries no numbers: it adds nothing to a simulation, and what depends on it is reported as such."""

    CALIBRATED = "calibrated"
    UNCALIBRATED = "uncalibrated"


class EdgeDynamics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effect: Distribution      # impact magnitude: target standard units per source standard unit
    kernel: KernelSpec        # delay, lag, duration


class ParameterForm(StrEnum):
    MULTIPLICATIVE = "multiplicative"     # beta_eff = beta * (1 + gamma * z_mod)
    THRESHOLD = "threshold"               # beta_eff = beta if z_mod > threshold else 0
    ADDITIVE = "additive"                 # adds gamma * z_mod to the target
    PIECEWISE = "piecewise"               # beta_eff = beta on `side` of the threshold, gamma * beta on the other (Oct 18)


class ParameterBinding(BaseModel):
    """Brings a third input into a binary edge."""

    model_config = ConfigDict(extra="forbid")

    name: str                             # e.g. "household debt level"
    moderator_id: str                     # subentity id
    form: ParameterForm = ParameterForm.MULTIPLICATIVE
    coefficient: Distribution             # gamma
    threshold: float | None = None        # standardized units, for THRESHOLD and PIECEWISE
    side: Literal["above", "below"] = "above"   # PIECEWISE: where the full effect applies

    def on(self, z: float) -> bool:
        """PIECEWISE: whether the moderator's z is on the side where the full effect applies."""
        thr = self.threshold if self.threshold is not None else 0.0
        return z > thr if self.side == "above" else z < thr


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
    calibration: Calibration = Calibration.CALIBRATED
    transition: Transition | None = None  # the link as a business step (model/construction.py)
    identity: str | None = None           # the identity or stock-flow (model/construction.py) whose term it is
    state: ResponseState | None = None    # the state-dependent responses its parameters were compiled from (readable)
    note: str | None = None               # the builder's note (conversion tags, a sign flip's reason); loaded and exported

    @property
    def fixed(self) -> bool:
        """An accounting, identity or stock-flow link: its weight (and kernel) is part of an identity, so learning, process
        noise and kernel updates never change it."""
        return self.edge_type in FIXED_EDGE_TYPES

    @property
    def quantified(self) -> bool:
        """Whether the link carries numbers: an uncalibrated one is structure only."""
        return self.calibration == Calibration.CALIBRATED

    def channels(self) -> list[tuple[str, str, EdgeDynamics]]:
        """One (source, target, dynamics) triple, or two for a bidirectional edge; none for an uncalibrated link,
        whose size is unknown, so nothing numeric (propagation, learning, recall) ever reads it."""
        if not self.quantified:
            return []
        out = [(self.source_id, self.target_id, self.forward)]
        if self.direction == Direction.BIDIRECTIONAL and self.reverse is not None:
            out.append((self.target_id, self.source_id, self.reverse))
        return out

    def channel_items(self) -> list[tuple[str, str, str, EdgeDynamics]]:
        """(channel key, source, target, dynamics); the reverse channel's key is ``<id>:rev``. None for an
        uncalibrated link (see `channels`)."""
        if not self.quantified:
            return []
        out = [(self.id, self.source_id, self.target_id, self.forward)]
        if self.direction == Direction.BIDIRECTIONAL and self.reverse is not None:
            out.append((self.id + REVERSE_SUFFIX, self.target_id, self.source_id, self.reverse))
        return out

    def polarity(self) -> int:
        """Sign of the forward effect's mean; for an uncalibrated link, the sign its transition states."""
        if not self.quantified and self.transition is not None and self.transition.sign is not None:
            return 1 if self.transition.sign == "+" else -1
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
