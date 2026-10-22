"""Period arithmetic for the Toyota repair fixtures (Fixes 7 to 14): plain functions over stipulated inputs.

These are not an engine. Each states one identity of the repair instructions so that a fixture can be run, and so that
the export can show the intermediate values. Every input is a stipulated or assumed number; nothing here reads a
company figure. Units are the caller's and are stated in each docstring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


# -- Fix 7: hybrid mix at fixed total units -----------------------------------------------------------------------
def hybrid_mix_op(substituted_units: float, hybrid_contribution: float, displaced_contribution: float | None = None,
                  spread: float | None = None) -> float:
    """Delta OP from substituting eligible units at fixed total units: units x (hybrid - displaced contribution per unit),
    or units x spread. Units and contribution per unit are in the caller's units (units x yen per unit = yen)."""
    if spread is None:
        if displaced_contribution is None:
            raise ValueError("a spread, or the displaced contribution, is needed")
        spread = hybrid_contribution - displaced_contribution
    return substituted_units * spread


# -- Fix 8: cost recognition and price recovery by period ---------------------------------------------------------------
def quarter_weights_ok(weights: Sequence[float]) -> bool:
    return len(weights) == 4 and abs(sum(weights) - 1.0) < 1e-9 and all(w >= 0 for w in weights)


def in_year_share(start_quarter_fraction: float) -> float:
    """Share of a fiscal year a uniform annualized amount is realized when it starts `start_quarter_fraction` of the way into
    the year (0 = April 1, 0.5 = October 1)."""
    if not 0.0 <= start_quarter_fraction <= 1.0:
        raise ValueError("a start inside the fiscal year")
    return 1.0 - start_quarter_fraction


@dataclass(frozen=True)
class PricingResult:
    cost_by_quarter: tuple[float, ...]
    recovery_by_quarter: tuple[float, ...]
    cost_in_year: float
    recovery_in_year: float
    lost_unit_contribution: float
    net_op: float
    recovery_next_year_if_persisting: float


def pricing_by_period(annual_cost: float, annualized_recovery: float, recovery_start: float, cost_weights: Sequence[float] = (0.25,) * 4,
                      baseline_recovery_in_year: float = 0.0, lost_unit_contribution: float = 0.0,
                      other_response_costs: float = 0.0, independent_savings: float = 0.0) -> PricingResult:
    """Incremental OP of a cost and a price response, each on its own schedule. `recovery_start` is the fraction of the fiscal
    year elapsed when recovery begins; recovery is uniform from then. Cost recognition does not move with the recovery start.
    `baseline_recovery_in_year` is recovery already embedded in the selected baseline: it is deducted from the scenario's, never
    added again. Amounts in the caller's currency unit."""
    if not quarter_weights_ok(cost_weights):
        raise ValueError("cost-recognition weights are four numbers that sum to 1")
    cost_q = tuple(annual_cost * w for w in cost_weights)
    rec_q = []
    for q in range(4):
        lo, hi = q / 4, (q + 1) / 4
        overlap = max(0.0, hi - max(lo, recovery_start))
        rec_q.append(annualized_recovery * overlap)
    rec_year = sum(rec_q)
    incremental_recovery = rec_year - baseline_recovery_in_year
    net = -sum(cost_q) + incremental_recovery + independent_savings - lost_unit_contribution - other_response_costs
    return PricingResult(cost_q, tuple(rec_q), sum(cost_q), rec_year, lost_unit_contribution, net, annualized_recovery)


# -- Fix 9 and 10: financing and translation -----------------------------------------------------------------------------
def average_exposed_share_uniform(share_reset_by_period_end: float) -> float:
    """If balances reset uniformly through a period and a share `s` has reset by its end, the share exposed on average over
    the period is s / 2, not s. An input that is already a stipulated period-average exposed balance needs no such step."""
    return share_reset_by_period_end / 2.0


def delta_nii(asset_exposed: float, d_asset_yield_pp: float, funding_exposed: float, d_funding_pp: float, year_fraction: float) -> dict:
    """Delta NII = average exposed asset balance x delta yield x t - average exposed funding balance x delta all-in funding rate x t
    (rates in percentage points, divided by 100). The reset share is already inside each exposed balance."""
    inc = asset_exposed * (d_asset_yield_pp / 100.0) * year_fraction
    exp = funding_exposed * (d_funding_pp / 100.0) * year_fraction
    return {"income_increment": inc, "expense_increment": exp, "delta_nii": inc - exp}


def translate(local_profit_bn: float, jpy_per_usd: float) -> float:
    """Yen trillion = 0.001 x local USD profit (billions) x period-average JPY per USD. A loss keeps its sign."""
    return 0.001 * local_profit_bn * jpy_per_usd


# -- Fix 11: disruption inventory and deferred sales ---------------------------------------------------------------------------
@dataclass
class DisruptionPeriod:
    label: str
    missed_arrivals: float
    catch_up_deliveries: float = 0.0
    cancellations: float = 0.0
    extra_cost: float = 0.0


def disruption(compatible_buffer: float, periods: Sequence[DisruptionPeriod]) -> list[dict]:
    """Delivery shortfall by period for one eligible market pool. The buffer is used first (never below zero); the remaining
    missed arrivals are a shortfall; catch-up deliveries reduce the deferred (not lost) balance; cancellations move deferred to lost
    only once. Costs accrue whether or not sales later recover."""
    stock, deferred, lost, cost = compatible_buffer, 0.0, 0.0, 0.0
    out = []
    for p in periods:
        used = min(stock, p.missed_arrivals)
        stock -= used
        shortfall = p.missed_arrivals - used
        deferred += shortfall
        recovered = min(deferred, p.catch_up_deliveries)
        deferred -= recovered
        cancelled = min(deferred, p.cancellations)
        deferred -= cancelled
        lost += cancelled
        cost += p.extra_cost
        out.append({"period": p.label, "buffer_used": used, "stock_close": stock, "delivery_shortfall": shortfall,
                    "recovered": recovered, "cancelled": cancelled, "deferred_open_orders_close": deferred,
                    "lost_cumulative": lost, "cumulative_shortfall": deferred + lost, "extra_cost_cumulative": cost})
    return out


def elimination_roll(open_: float, new_unrealized: float, released_on_external_sale: float) -> float:
    """elimination_close = elimination_open + new unrealized profit - release on a qualifying external sale."""
    close = open_ + new_unrealized - released_on_external_sale
    if close < -1e-12:
        raise ValueError("a release larger than the elimination held")
    return close


# -- Fix 12: matched share --------------------------------------------------------------------------------------------------------
def matched_share(company_index_from: float, company_index_to: float, market_index_from: float, market_index_to: float,
                  opening_share: float | None = None) -> dict:
    """Relative share change = (1 + company unit growth) / (1 + matched market growth) - 1. Closing share = opening x (1 + relative change);
    the change in percentage points is 100 x (closing - opening) for shares as fractions."""
    g_c = company_index_to / company_index_from - 1.0
    g_m = market_index_to / market_index_from - 1.0
    rel = (1.0 + g_c) / (1.0 + g_m) - 1.0
    out = {"company_unit_growth": g_c, "market_growth": g_m, "relative_share_change": rel, "growth_difference_shortcut": g_c - g_m}
    if opening_share is not None:
        closing = opening_share * (1.0 + rel)
        out |= {"opening_share": opening_share, "closing_share": closing, "change_pp": 100.0 * (closing - opening_share)}
    return out


# -- Fix 13: sourcing project cash -------------------------------------------------------------------------------------------------------
def payback_years(upfront: float, annual_benefit: float, annual_extra_cost: float, benefit_delay_years: float = 0.0) -> float:
    """Years from the (fixed-date) upfront spending until cumulative net cash recovers it, with benefits starting after a delay.
    Simple payback: operating years needed after the delay are upfront / (benefit - cost); the total includes the delay."""
    net = annual_benefit - annual_extra_cost
    if net <= 0:
        return float("inf")
    return benefit_delay_years + upfront / net


def operating_years_needed(upfront: float, annual_benefit: float, annual_extra_cost: float) -> float:
    net = annual_benefit - annual_extra_cost
    return float("inf") if net <= 0 else upfront / net


def npv(cash_flows: Sequence[tuple[float, float]], rate: float) -> float:
    """Sum of cash flows (years from the start, amount) discounted at an assumed annual rate."""
    return sum(cf / (1.0 + rate) ** t for t, cf in cash_flows)


def project_cash_flows(upfront: float, annual_benefit: float, annual_extra_cost: float, benefit_delay_years: float, life_years: int,
                       upfront_year: float = 0.0) -> list[tuple[float, float]]:
    flows = [(upfront_year, -upfront)]
    for k in range(life_years):
        flows.append((upfront_year + benefit_delay_years + k + 1, annual_benefit - annual_extra_cost))
    return flows


# -- Fix 14: eligible cash and conditional buyback --------------------------------------------------------------------------------------------
def liquidity_close(opening: float, ocf: float, capex: float, other_cash: float, dividends: float, buybacks: float, collection_delay: float = 0.0) -> float:
    """Eligible industrial liquidity: opening + OCF - capex + identified other cash movements - dividends - executed buybacks.
    A collection delay is a reduction of OCF with OP unchanged (working capital inside OCF, not deducted again)."""
    return opening + (ocf - collection_delay) - capex + other_cash - dividends - buybacks


def buyback_capacity(cash_authorization_left: float, share_authorization_left: float, assumed_price: float, headroom_after_other_uses: float) -> dict:
    """Permitted spend = max(0, min(remaining cash authorization, remaining share authorization x price, eligible headroom)).
    A constraint, not a forecast that management uses it."""
    ceilings = {"cash_authorization": cash_authorization_left, "share_authorization_at_price": share_authorization_left * assumed_price,
                "eligible_headroom": headroom_after_other_uses}
    binding = min(ceilings, key=ceilings.get)
    return {"ceilings": ceilings, "binding": binding, "permitted_spend": max(0.0, ceilings[binding])}
