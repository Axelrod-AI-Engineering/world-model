"""Interest on exposed balances, by reset date (Toyota repair, Fix 5).

A rate change reaches interest only through the balances that reprice, and only from the date they reprice. For a
simple-interest period

    delta_interest = sum over cohorts of  exposed balance x (delta_rate_pp / 100) x years of exposure

where a cohort's years of exposure run from its reset date (0 for floating or already-maturing balances) to the end
of the horizon, and a hedged share of a cohort does not reprice. The balance, the rate and the period must be the
same entity, currency and unit; a period-end stock is not an average balance, and the caller says which it passed.
This is an identity for a stipulated exposure, not a disclosed group sensitivity.

`apply_rate_shock` moves only the lines named as interest. Lease income, depreciation, credit losses and every other
line are returned unchanged, so a funding-rate change has no artificial response in a non-interest cost. Zero
exposure gives zero.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cohort:
    """Balance that reprices at `reset_year` (years from the start of the horizon; 0 = reprices at once)."""

    balance: float
    reset_year: float = 0.0
    hedged_share: float = 0.0            # fixed through the horizon by a swap or a fixed coupon: no exposure
    label: str = ""

    def __post_init__(self) -> None:
        if self.balance < 0:
            raise ValueError("a balance is not negative")
        if not 0.0 <= self.hedged_share <= 1.0:
            raise ValueError("a hedged share is a fraction")
        if self.reset_year < 0:
            raise ValueError("a reset year is not before the horizon starts")


def exposure_years(cohort: Cohort, horizon_years: float) -> float:
    """Years of the horizon that a cohort spends repriced."""
    return max(0.0, horizon_years - cohort.reset_year)


def interest_increment(cohorts: Sequence[Cohort], delta_rate_pp: float, horizon_years: float) -> float:
    """The extra interest over the horizon, in the balances' unit, for a rate change of `delta_rate_pp` percentage points."""
    if horizon_years < 0:
        raise ValueError("a horizon is not negative")
    return sum(c.balance * (1.0 - c.hedged_share) * (delta_rate_pp / 100.0) * exposure_years(c, horizon_years)
               for c in cohorts)


@dataclass(frozen=True)
class RateShockResult:
    lines: Mapping[str, float]
    delta_interest: float
    changed: tuple[str, ...] = field(default=())


def apply_rate_shock(lines: Mapping[str, float], interest_line: str, cohorts: Sequence[Cohort], delta_rate_pp: float,
                     horizon_years: float, sign: int = 1) -> RateShockResult:
    """`lines` with only `interest_line` moved by the cohorts' increment (`sign` -1 for an income line that falls
    when a funding rate rises is not applied here: pass the line the rate acts on, with the sign of its effect)."""
    if interest_line not in lines:
        raise KeyError(interest_line)
    d = sign * interest_increment(cohorts, delta_rate_pp, horizon_years)
    out = dict(lines)
    out[interest_line] = out[interest_line] + d
    return RateShockResult(out, d, (interest_line,) if d else ())
