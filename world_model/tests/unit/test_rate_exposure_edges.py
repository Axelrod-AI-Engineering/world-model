"""Input guards of the rate-exposure functions (invented numbers)."""

import pytest

from axelrod_wm.model.rate_exposure import Cohort, apply_rate_shock, interest_increment


def test_a_cohort_rejects_impossible_inputs():
    with pytest.raises(ValueError, match="balance"):
        Cohort(-1.0)
    with pytest.raises(ValueError, match="hedged"):
        Cohort(1.0, hedged_share=1.5)
    with pytest.raises(ValueError, match="reset year"):
        Cohort(1.0, reset_year=-0.1)


def test_a_negative_horizon_is_refused():
    with pytest.raises(ValueError, match="horizon"):
        interest_increment([Cohort(1.0)], 1.0, -1.0)


def test_the_shock_needs_the_named_interest_line():
    with pytest.raises(KeyError):
        apply_rate_shock({"a": 1.0}, "missing", [Cohort(1.0)], 1.0, 1.0)
