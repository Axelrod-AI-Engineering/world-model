"""Entity memories: action buckets and decision profiles."""

from __future__ import annotations

import pytest

from axelrod_wm.memory.entity_memory import DecisionProfile, action_of


def test_action_of_buckets_by_half_a_standard_unit():
    assert action_of(0.3, 0.5) == "raised"
    assert action_of(-0.3, 0.5) == "cut"
    assert action_of(0.2, 0.5) == "held"
    assert action_of(0.0, 0.0) == "held"           # no scale: any non-zero move counts
    assert action_of(1e-6, 0.0) == "raised"


def test_profile_probabilities_and_totals():
    prof = DecisionProfile(by_context={"cpi>+0.75": [3, 0, 1]})
    assert prof.total("cpi>+0.75") == 4
    assert prof.total("unseen") == 0
    assert prof.p_action("cpi>+0.75", "raised") == pytest.approx(4 / 7)
    assert prof.p_action("unseen", "cut") == pytest.approx(1 / 3)
