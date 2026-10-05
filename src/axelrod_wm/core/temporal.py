"""Time, kernels, and time states (§6.4).

The kernel answers the notes' "lag, delay, duration": delay is the dead time before any
effect, lag is the time from onset to peak, and duration is how long the effect lasts after
its peak.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator

from axelrod_wm.core.distributions import Distribution, Gamma, parse_distribution

KERNEL_CV = 0.3
ZERO_LAG = 1e-6   # steps; a shorter lag counts as zero ("l = 0 jumps straight to 1")


class Bitemporal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid_at: datetime       # when it was true in the world
    recorded_at: datetime    # when the model learned it


class TimeState(BaseModel):
    """An annotation that keeps a past value of an object (context-graph style)."""

    model_config = ConfigDict(extra="forbid")

    at: Bitemporal
    values: dict[str, float]
    source_event_id: str | None = None
    note: str | None = None


def gamma_from_mean(mean_days: float, cv: float = KERNEL_CV) -> Gamma:
    """A gamma distribution with the given mean (days) and coefficient of variation."""
    k = 1.0 / (cv * cv)
    return Gamma(k=k, theta=max(float(mean_days) / k, 1e-9))


class KernelSpec(BaseModel):
    """Step response of one channel, in days. It is zero before `delay`, rises to 1 over
    `lag`, then fades to 0 over `duration`. duration=None means the effect is permanent."""

    model_config = ConfigDict(extra="forbid")

    delay: Distribution
    lag: Distribution
    duration: Optional[Distribution] = None
    shape: str = "ramp_decay"

    @model_validator(mode="before")
    @classmethod
    def _shorthand(cls, data: Any) -> Any:
        """Accept {"delay_days": 7, "lag_days": 30, "duration_days": null}."""
        if isinstance(data, dict) and any(k in data for k in ("delay_days", "lag_days", "duration_days")):
            out = {k: v for k, v in data.items() if k not in ("delay_days", "lag_days", "duration_days")}
            out["delay"] = gamma_from_mean(data.get("delay_days", 0.0) or 0.0)
            out["lag"] = gamma_from_mean(data.get("lag_days", 0.0) or 0.0)
            dur = data.get("duration_days")
            out["duration"] = gamma_from_mean(dur) if dur is not None else None
            return out
        return data

    def means(self) -> tuple[float, float, float | None]:
        """(delay, lag, duration) means in days."""
        return (self.delay.mean(), self.lag.mean(),
                self.duration.mean() if self.duration is not None else None)

    def cv(self) -> float:
        d = self.delay
        if isinstance(d, Gamma):
            return float(1.0 / np.sqrt(d.k))
        return KERNEL_CV

    def rescaled(self, multiplier: float, cv: float | None = None) -> KernelSpec:
        """All three means multiplied by `multiplier`; optionally a new coefficient of variation."""
        cv = self.cv() if cv is None else cv
        d, l, dur = self.means()
        return KernelSpec(delay=gamma_from_mean(d * multiplier, cv), lag=gamma_from_mean(l * multiplier, cv),
                          duration=gamma_from_mean(dur * multiplier, cv) if dur is not None else None,
                          shape=self.shape)

    def shorthand(self) -> dict[str, float | None]:
        d, l, dur = self.means()
        return {"delay_days": d, "lag_days": l, "duration_days": dur}


def parse_kernel(data: Any) -> KernelSpec:
    if isinstance(data, KernelSpec):
        return data
    return KernelSpec.model_validate(data)


def smoothstep(s: np.ndarray) -> np.ndarray:
    s = np.clip(s, 0.0, 1.0)
    return s * s * (3.0 - 2.0 * s)


def step_response(delay: float, lag: float, duration: float | None,
                  n_steps: int, step_days: float, shape: str = "ramp_decay") -> np.ndarray:
    """Return g[tau] for tau = 0..n_steps. Convert d, l, D from days to steps first.
    Default shape:
        g = 0                            for tau < d
        g = smoothstep((tau - d) / l)    for d <= tau < d + l   (l = 0 jumps straight to 1)
        g = exp(-3 * (tau - d - l) / D)  for tau >= d + l, when D is given
        g = 1                            for tau >= d + l, when D is None
    """
    if shape != "ramp_decay":
        raise ValueError(f"unknown kernel shape: {shape}")
    tau = np.arange(n_steps + 1, dtype=float)
    d = float(delay) / step_days
    l = float(lag) / step_days
    g = np.zeros_like(tau)
    if l > ZERO_LAG:
        rising = (tau >= d) & (tau < d + l)
        g[rising] = smoothstep((tau[rising] - d) / l)
    if l <= ZERO_LAG:
        l = 0.0
    after = tau >= d + l
    if duration is None:
        g[after] = 1.0
    else:
        dd = max(float(duration) / step_days, 1e-9)
        g[after] = np.exp(-3.0 * (tau[after] - d - l) / dd)
    return g


def step_response_batch(delay_steps: np.ndarray, lag_steps: np.ndarray, dur_steps: np.ndarray | None,
                        n_steps: int) -> np.ndarray:
    """Vectorized step responses. Inputs are in steps, shape [k]; dur_steps may contain inf for
    permanent effects. Returns [k, n_steps + 1]."""
    tau = np.arange(n_steps + 1, dtype=float)[None, :]
    d = np.asarray(delay_steps, dtype=float)[:, None]
    l = np.asarray(lag_steps, dtype=float)[:, None]
    g = np.zeros((d.shape[0], n_steps + 1))
    l = np.where(l > ZERO_LAG, l, 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(l > 0, (tau - d) / np.where(l > 0, l, 1.0), 1.0)
    rising = (tau >= d) & (tau < d + l)
    g = np.where(rising, smoothstep(s), g)
    after = tau >= d + l
    if dur_steps is None:
        decay = np.ones_like(g)
    else:
        dd = np.asarray(dur_steps, dtype=float)[:, None]
        with np.errstate(over="ignore", invalid="ignore"):
            decay = np.where(np.isinf(dd), 1.0, np.exp(-3.0 * (tau - d - l) / np.maximum(dd, 1e-9)))
    g = np.where(after, decay, g)
    return g


__all__ = [
    "Bitemporal",
    "TimeState",
    "KernelSpec",
    "gamma_from_mean",
    "parse_kernel",
    "parse_distribution",
    "step_response",
    "step_response_batch",
    "smoothstep",
]
