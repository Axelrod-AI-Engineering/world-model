"""R03 fixture (Toyota repair, Fix 5): $10bn exposed, +100bp, half a year -> $50m extra funding expense; non-interest
lines do not respond; zero exposure gives zero; a cohort that resets later gets less."""

import pytest

from axelrod_wm.model.rate_exposure import Cohort, apply_rate_shock, interest_increment


def test_controlled_fixture_is_fifty_million():
    assert interest_increment([Cohort(10.0)], 1.0, 0.5) == pytest.approx(0.05)


def test_only_the_interest_line_moves():
    lines = {"funding_interest": 5.04, "lease_depreciation": 2.0, "credit_losses": 0.3, "customer_income": 8.45}
    r = apply_rate_shock(lines, "funding_interest", [Cohort(10.0)], 1.0, 0.5)
    assert r.lines["funding_interest"] == pytest.approx(5.09)
    assert {k: v for k, v in r.lines.items() if k != "funding_interest"} == {k: v for k, v in lines.items() if k != "funding_interest"}
    assert r.changed == ("funding_interest",)


def test_zero_exposure_is_zero():
    assert interest_increment([], 1.0, 0.5) == 0.0
    assert interest_increment([Cohort(0.0)], 1.0, 0.5) == 0.0
    r = apply_rate_shock({"i": 1.0, "d": 2.0}, "i", [Cohort(10.0, hedged_share=1.0)], 1.0, 0.5)
    assert r.delta_interest == 0.0 and r.lines == {"i": 1.0, "d": 2.0} and r.changed == ()


def test_reset_date_and_hedge_scale_the_exposure():
    cohorts = [Cohort(10.0, reset_year=0.0), Cohort(10.0, reset_year=0.25, hedged_share=0.5), Cohort(10.0, reset_year=0.75)]
    assert interest_increment(cohorts, 1.0, 0.5) == pytest.approx(0.05 + 10 * 0.5 * 0.01 * 0.25)
    assert interest_increment(cohorts, 2.0, 0.5) == pytest.approx(2 * interest_increment(cohorts, 1.0, 0.5))
