"""Working memory's small helpers: point keys, the deviation views, hedge posteriors, ripple corrections,
and the processing day and channel regressors."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from axelrod_wm.dynamics.kernels import KernelRecursion
from axelrod_wm.memory.working import (
    ChannelState,
    DeviationHistory,
    DeviationPoint,
    PendingRefinement,
    RippleJudgment,
    point_key,
    ripple_correction,
    ripple_key,
    split_point_key,
)
from axelrod_wm.repo.snapshots import empty_state

AT = datetime(2024, 3, 1, tzinfo=UTC)


def test_split_point_key_inverts_point_key_even_with_pipes_in_the_id():
    assert split_point_key(point_key("a.b", 12)) == ("a.b", 12)
    assert split_point_key("odd|id|-3") == ("odd|id", -3)


def test_series_get_returns_the_point_or_none():
    hist = DeviationHistory(origin_date=date(2024, 1, 1))
    pt = DeviationPoint(z=1.5, var=0.2, level=1.0)
    hist.points[point_key("x.y", 4)] = pt
    s = hist.series("x.y")
    assert s.get(4) is pt
    assert s.get(5) is None
    assert s[4] == 1.5 and s[5] == 0.0


def test_day_of_treats_a_naive_timestamp_as_utc():
    hist = DeviationHistory(origin_date=date(2024, 1, 1))
    assert hist.day_of(datetime(2024, 1, 3, 23, 0)) == 2
    assert hist.day_of(datetime(2024, 1, 3, 23, 0, tzinfo=UTC)) == 2


def _pending(**kw) -> PendingRefinement:
    op = {"op": "change_value", "target": {"kind": "concrete", "subentity_id": "a.b"}, "delta": 1.0,
          "mode": "relative", "persistence": "step", "at": AT.isoformat()}
    return PendingRefinement.model_validate({
        "id": "PR-1", "op": op, "end": "target", "reached": 1, "node_id": "a", "evidence": [],
        "source_event_id": "GUE-1", "created_at": AT, "expires_at": AT, **kw})


def test_posterior_without_alpha_normalizes_the_scores():
    pr = _pending(candidates={"a.x": 3.0, "a.y": 1.0})
    assert pr.posterior() == {"a.x": 0.75, "a.y": 0.25}


def test_posterior_without_alpha_and_zero_scores_does_not_divide_by_zero():
    pr = _pending(candidates={"a.x": 0.0})
    assert pr.posterior() == {"a.x": 0.0}


def test_posterior_with_alpha_and_no_open_mass_omits_open():
    pr = _pending(candidates={"a.x": 0.5, "a.y": 0.5}, alpha={"a.x": 3.0, "a.y": 1.0})
    assert pr.posterior() == {"a.x": 0.75, "a.y": 0.25}


def test_posterior_with_open_mass_adds_open():
    pr = _pending(candidates={"a.x": 1.0}, alpha={"a.x": 3.0}, open_alpha=1.0)
    assert pr.posterior() == {"a.x": 0.75, "__open__": 0.25}


def test_ripple_correction_sums_only_this_value_within_its_path():
    wm, _ = empty_state()
    wm.ripple_judgments[ripple_key("E1", "a.x")] = RippleJudgment(
        event_id="E1", subentity_id="a.x", weight=0.5, start_day=10, path=[1.0, 2.0])
    wm.ripple_judgments[ripple_key("E2", "a.x")] = RippleJudgment(
        event_id="E2", subentity_id="a.x", weight=0.0, start_day=11, path=[4.0])
    wm.ripple_judgments[ripple_key("E1", "b.y")] = RippleJudgment(
        event_id="E1", subentity_id="b.y", weight=0.0, start_day=10, path=[9.0, 9.0])
    assert ripple_correction(wm, "a.x", 9) == 0.0            # before the paths
    assert ripple_correction(wm, "a.x", 10) == pytest.approx(-0.5)
    assert ripple_correction(wm, "a.x", 11) == pytest.approx(-1.0 - 4.0)
    assert ripple_correction(wm, "a.x", 12) == 0.0           # after both paths end
    assert ripple_correction(wm, "c.z", 10) == 0.0


def test_processing_day_is_the_day_after_the_last_processed():
    wm, _ = empty_state()
    assert wm.processing_day() == 0
    wm.last_processed_day = 41
    assert wm.processing_day() == 42


def test_phi_reads_the_channel_recursion_or_zero():
    wm, _ = empty_state()
    assert wm.phi("e01") == 0.0
    wm.channels["e01"] = ChannelState(channel_id="e01", recursion=KernelRecursion(d=1, l=4, lam=0.5, S=2.0, T=0.25))
    assert wm.phi("e01") == pytest.approx(2.0 / 4 + 0.25)
