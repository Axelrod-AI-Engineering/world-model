"""Time, kernels, and time states (§6.4).

The kernel answers the notes' "lag, delay, duration": delay is the dead time before any effect
(at least one day), lag is the time from onset to peak, and duration is how long the effect takes
to fade after its peak (about 95% gone after one duration). Everything is on a daily grid (D13).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator

from axelrod_wm.core.distributions import Distribution, Gamma, parse_distribution

KERNEL_CV = 0.3


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
    """Step response of one channel, in days. It is zero before `delay`, rises linearly over
    `lag`, then fades over `duration`. duration=None means the effect is permanent."""

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


def kernel_days(delay: float, lag: float, duration: float | None, min_delay: int = 1) -> tuple[int, int, float]:
    """(d, l, lam) on the daily grid: delay and lag rounded to whole days and floored at
    `min_delay` and 1, and lam = exp(-3 / duration), or 1 for a permanent effect (§6.4)."""
    d = max(int(min_delay), int(round(float(delay))))
    l = max(1, int(round(float(lag))))
    if duration is None or not np.isfinite(duration):
        lam = 1.0
    else:
        lam = float(np.exp(-3.0 / max(float(duration), 1e-9)))
    return d, l, lam


def step_response(d: int, l: int, D: float | None, n_days: int) -> np.ndarray:
    """Reference definition, used by tests. Returns g[tau] for tau = 0..n_days, with integer
    days d >= 1 and l >= 1 (sampled values are rounded and floored at 1):
        g = 0                                   for tau < d
        g = (tau - d + 1) / l                   for d <= tau <= d + l - 1   (peak 1 at tau = d + l - 1)
        g = lam ** (tau - (d + l - 1))          for tau >= d + l, lam = exp(-3 / D), when D is given
        g = 1                                   for tau >= d + l, when D is None (lam = 1)
    """
    d = max(1, int(d))
    l = max(1, int(l))
    lam = 1.0 if D is None else float(np.exp(-3.0 / max(float(D), 1e-9)))
    tau = np.arange(n_days + 1)
    g = np.zeros(n_days + 1)
    rising = (tau >= d) & (tau <= d + l - 1)
    g[rising] = (tau[rising] - d + 1) / l
    after = tau >= d + l
    g[after] = lam ** (tau[after] - (d + l - 1)).astype(float)
    return g


__all__ = [
    "Bitemporal",
    "TimeState",
    "KernelSpec",
    "gamma_from_mean",
    "kernel_days",
    "parse_kernel",
    "parse_distribution",
    "step_response",
]
