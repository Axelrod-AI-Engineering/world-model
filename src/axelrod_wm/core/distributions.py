"""Distributions, link functions, and posterior updates (§6.3, D6).

Each family has a link that maps native values to the space where effects add up. A
subentity's standardized deviation is ``z = (link(x) - anchor) / scale``.

# DECISION: beta and gamma use the delta method in both directions (link_moments and
# from_link_moments), so a refit round trip is exact and the Kalman update in link space is
# consistent with the native moments. LogNormal and Gaussian are exact.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import datetime
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Union

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from scipy import special, stats

QUANTILE_LEVELS: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)
_EPS = 1e-12


class Link(StrEnum):
    IDENTITY = "identity"
    LOG = "log"
    LOGIT = "logit"


class DistSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mean: float
    sd: float
    q05: float
    q10: float
    q25: float
    q50: float
    q75: float
    q90: float
    q95: float

    def quantiles(self) -> list[float]:
        return [self.q05, self.q10, self.q25, self.q50, self.q75, self.q90, self.q95]

    def map(self, fn) -> DistSummary:
        """Apply a monotone increasing map to the quantiles (mean and sd are mapped approximately)."""
        qs = [float(fn(q)) for q in self.quantiles()]
        lo, hi = float(fn(self.mean - self.sd)), float(fn(self.mean + self.sd))
        return DistSummary(mean=float(fn(self.mean)), sd=abs(hi - lo) / 2.0, q05=qs[0], q10=qs[1],
                           q25=qs[2], q50=qs[3], q75=qs[4], q90=qs[5], q95=qs[6])


def summarize_samples(x: np.ndarray) -> DistSummary:
    x = np.asarray(x, dtype=float).ravel()
    if x.size == 0:
        return DistSummary(mean=0.0, sd=0.0, q05=0.0, q10=0.0, q25=0.0, q50=0.0, q75=0.0, q90=0.0, q95=0.0)
    qs = np.quantile(x, QUANTILE_LEVELS)
    return DistSummary(mean=float(x.mean()), sd=float(x.std()), q05=float(qs[0]), q10=float(qs[1]),
                       q25=float(qs[2]), q50=float(qs[3]), q75=float(qs[4]), q90=float(qs[5]),
                       q95=float(qs[6]))


def to_link(x, link: Link | str):
    """Map native values to link space."""
    link = Link(link)
    arr = np.asarray(x, dtype=float)
    if link is Link.IDENTITY:
        out = arr
    elif link is Link.LOG:
        out = np.log(np.maximum(arr, _EPS))
    else:
        p = np.clip(arr, 1e-9, 1 - 1e-9)
        out = np.log(p) - np.log1p(-p)
    return float(out) if np.ndim(out) == 0 else out


def from_link(eta, link: Link | str):
    """Map link-space values back to native units."""
    link = Link(link)
    arr = np.asarray(eta, dtype=float)
    if link is Link.IDENTITY:
        out = arr
    elif link is Link.LOG:
        out = np.exp(np.minimum(arr, 700.0))
    else:
        out = special.expit(arr)
    return float(out) if np.ndim(out) == 0 else out


def link_derivative_inverse(eta: float, link: Link | str) -> float:
    """d from_link / d eta at eta (used by the delta method)."""
    link = Link(link)
    if link is Link.IDENTITY:
        return 1.0
    if link is Link.LOG:
        return float(np.exp(min(eta, 700.0)))
    p = float(special.expit(eta))
    return p * (1.0 - p)


class DistributionBase(BaseModel, ABC):
    model_config = ConfigDict(extra="forbid")

    family: str
    link_kind: ClassVar[Link] = Link.IDENTITY

    @property
    def link(self) -> Link:
        return self.link_kind

    @abstractmethod
    def mean(self) -> float: ...

    @abstractmethod
    def var(self) -> float: ...

    def sd(self) -> float:
        return math.sqrt(max(self.var(), 0.0))

    @abstractmethod
    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray: ...

    @abstractmethod
    def logpdf(self, x: np.ndarray) -> np.ndarray: ...

    @abstractmethod
    def quantile(self, q: np.ndarray) -> np.ndarray: ...

    @abstractmethod
    def link_moments(self) -> tuple[float, float]:
        """Mean and variance of link(x)."""

    @classmethod
    @abstractmethod
    def from_link_moments(cls, mean: float, var: float) -> DistributionBase:
        """Refit this family from link-space moments by moment matching."""

    def summary(self) -> DistSummary:
        qs = np.asarray(self.quantile(np.asarray(QUANTILE_LEVELS)), dtype=float)
        return DistSummary(mean=float(self.mean()), sd=float(self.sd()), q05=float(qs[0]),
                           q10=float(qs[1]), q25=float(qs[2]), q50=float(qs[3]), q75=float(qs[4]),
                           q90=float(qs[5]), q95=float(qs[6]))

    def link_summary(self) -> tuple[float, float]:
        m, v = self.link_moments()
        return m, math.sqrt(max(v, 0.0))


class Gaussian(DistributionBase):
    family: Literal["gaussian"] = "gaussian"
    mu: float
    sigma: float = Field(ge=0.0)
    link_kind: ClassVar[Link] = Link.IDENTITY

    def mean(self) -> float:
        return self.mu

    def var(self) -> float:
        return self.sigma**2

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        return rng.normal(self.mu, self.sigma, size=n)

    def logpdf(self, x: np.ndarray) -> np.ndarray:
        return stats.norm.logpdf(x, self.mu, max(self.sigma, _EPS))

    def quantile(self, q: np.ndarray) -> np.ndarray:
        return self.mu + self.sigma * special.ndtri(np.asarray(q, dtype=float))

    def link_moments(self) -> tuple[float, float]:
        return self.mu, self.sigma**2

    @classmethod
    def from_link_moments(cls, mean: float, var: float) -> Gaussian:
        return cls(mu=float(mean), sigma=math.sqrt(max(float(var), _EPS)))


class Beta(DistributionBase):
    family: Literal["beta"] = "beta"
    alpha: float = Field(gt=0.0)
    beta: float = Field(gt=0.0)
    link_kind: ClassVar[Link] = Link.LOGIT

    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def var(self) -> float:
        a, b = self.alpha, self.beta
        return a * b / ((a + b) ** 2 * (a + b + 1.0))

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        return rng.beta(self.alpha, self.beta, size=n)

    def logpdf(self, x: np.ndarray) -> np.ndarray:
        return stats.beta.logpdf(x, self.alpha, self.beta)

    def quantile(self, q: np.ndarray) -> np.ndarray:
        return special.betaincinv(self.alpha, self.beta, np.asarray(q, dtype=float))

    def link_moments(self) -> tuple[float, float]:
        m = min(max(self.mean(), 1e-9), 1 - 1e-9)
        d = m * (1.0 - m)
        return math.log(m) - math.log1p(-m), self.var() / (d * d)

    @classmethod
    def from_link_moments(cls, mean: float, var: float) -> Beta:
        m = float(special.expit(mean))
        m = min(max(m, 1e-9), 1 - 1e-9)
        d = m * (1.0 - m)
        native_var = max(float(var), _EPS) * d * d
        kappa = d / native_var - 1.0
        kappa = min(max(kappa, 0.5), 1e7)
        return cls(alpha=m * kappa, beta=(1.0 - m) * kappa)


class LogNormal(DistributionBase):
    family: Literal["lognormal"] = "lognormal"
    mu: float
    sigma: float = Field(ge=0.0)
    link_kind: ClassVar[Link] = Link.LOG

    def mean(self) -> float:
        return math.exp(min(self.mu + 0.5 * self.sigma**2, 700.0))

    def var(self) -> float:
        s2 = self.sigma**2
        return (math.exp(min(s2, 700.0)) - 1.0) * math.exp(min(2 * self.mu + s2, 700.0))

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        return rng.lognormal(self.mu, self.sigma, size=n)

    def logpdf(self, x: np.ndarray) -> np.ndarray:
        return stats.lognorm.logpdf(x, max(self.sigma, _EPS), scale=math.exp(self.mu))

    def quantile(self, q: np.ndarray) -> np.ndarray:
        return np.exp(self.mu + self.sigma * special.ndtri(np.asarray(q, dtype=float)))

    def link_moments(self) -> tuple[float, float]:
        return self.mu, self.sigma**2

    @classmethod
    def from_link_moments(cls, mean: float, var: float) -> LogNormal:
        return cls(mu=float(mean), sigma=math.sqrt(max(float(var), _EPS)))


class Gamma(DistributionBase):
    family: Literal["gamma"] = "gamma"
    k: float = Field(gt=0.0)
    theta: float = Field(gt=0.0)
    link_kind: ClassVar[Link] = Link.LOG

    def mean(self) -> float:
        return self.k * self.theta

    def var(self) -> float:
        return self.k * self.theta**2

    def sample(self, n: int, rng: np.random.Generator) -> np.ndarray:
        return rng.gamma(self.k, self.theta, size=n)

    def logpdf(self, x: np.ndarray) -> np.ndarray:
        return stats.gamma.logpdf(x, self.k, scale=self.theta)

    def quantile(self, q: np.ndarray) -> np.ndarray:
        return special.gammaincinv(self.k, np.asarray(q, dtype=float)) * self.theta

    def link_moments(self) -> tuple[float, float]:
        return math.log(max(self.mean(), _EPS)), 1.0 / self.k

    @classmethod
    def from_link_moments(cls, mean: float, var: float) -> Gamma:
        m = math.exp(min(float(mean), 700.0))
        k = 1.0 / max(float(var), 1e-9)
        k = min(k, 1e9)
        return cls(k=k, theta=max(m / k, _EPS))


Distribution = Annotated[Union[Gaussian, Beta, LogNormal, Gamma], Field(discriminator="family")]
DIST_ADAPTER: TypeAdapter = TypeAdapter(Distribution)

FAMILIES: dict[str, type[DistributionBase]] = {
    "gaussian": Gaussian,
    "beta": Beta,
    "lognormal": LogNormal,
    "gamma": Gamma,
}


def family_link(family: str) -> Link:
    return FAMILIES[family].link_kind


def from_link_moments(family: str, mean: float, var: float) -> DistributionBase:
    return FAMILIES[family].from_link_moments(mean, var)


def prior_from_native(family: str, value: float, link_sd: float) -> DistributionBase:
    """A prior whose link-space mean maps back to ``value`` and whose link sd is ``link_sd``."""
    link = family_link(family)
    return from_link_moments(family, float(to_link(value, link)), float(link_sd) ** 2)


def parse_distribution(data) -> DistributionBase:
    if isinstance(data, DistributionBase):
        return data
    return DIST_ADAPTER.validate_python(data)


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float            # native units
    noise_sd: float         # standardized units (multiples of the subentity's scale)
    observed_at: datetime


class PosteriorUpdater(ABC):
    @abstractmethod
    def update(self, current: Distribution, obs: Observation, scale: float,
               process_noise_sd: float = 0.0) -> Distribution: ...

    @abstractmethod
    def shift(self, current: Distribution, delta_link: float, extra_var_link: float = 0.0) -> Distribution:
        """Move a distribution by a known change in link space (a real change_value op)."""


class LinkKalmanUpdater(PosteriorUpdater):
    """Default ``link_kalman`` updater: a scalar Kalman step in link space, then a refit."""

    def update(self, current: Distribution, obs: Observation, scale: float,
               process_noise_sd: float = 0.0) -> Distribution:
        m, v = current.link_moments()
        v += (process_noise_sd * scale) ** 2
        r = (obs.noise_sd * scale) ** 2
        eta = float(to_link(obs.value, current.link))
        gain = v / (v + r) if (v + r) > 0 else 0.0
        m2 = m + gain * (eta - m)
        v2 = (1.0 - gain) * v
        return type(current).from_link_moments(m2, v2)

    def shift(self, current: Distribution, delta_link: float, extra_var_link: float = 0.0) -> Distribution:
        m, v = current.link_moments()
        return type(current).from_link_moments(m + delta_link, v + extra_var_link)
