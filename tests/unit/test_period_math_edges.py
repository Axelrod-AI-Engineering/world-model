"""Edge branches of the period arithmetic (invented numbers)."""

import pytest

from axelrod_wm.model.period_math import (
    elimination_roll,
    hybrid_mix_op,
    in_year_share,
    matched_share,
    operating_years_needed,
    payback_years,
    quarter_weights_ok,
)


def test_hybrid_from_displaced_contribution_or_error():
    assert hybrid_mix_op(10.0, 5.0, displaced_contribution=3.0) == 20.0
    with pytest.raises(ValueError, match="spread"):
        hybrid_mix_op(10.0, 5.0)


def test_quarter_weights_and_in_year_share():
    assert quarter_weights_ok((0.25,) * 4)
    assert not quarter_weights_ok((0.5, 0.5))
    assert not quarter_weights_ok((0.5, 0.5, 0.5, -0.5))
    assert in_year_share(0.5) == 0.5
    with pytest.raises(ValueError, match="fiscal year"):
        in_year_share(1.5)


def test_elimination_cannot_go_negative():
    with pytest.raises(ValueError, match="release"):
        elimination_roll(1.0, 1.0, 3.0)


def test_matched_share_without_an_opening_share():
    m = matched_share(100, 90, 100, 100)
    assert "closing_share" not in m and m["relative_share_change"] == pytest.approx(-0.1)


def test_no_payback_when_net_benefit_is_not_positive():
    assert payback_years(100, 10, 10) == float("inf")
    assert operating_years_needed(100, 10, 20) == float("inf")
