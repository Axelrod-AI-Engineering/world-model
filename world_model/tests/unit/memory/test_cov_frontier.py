"""The correlation frontier: running correlations, backfilling, and the abstract tester."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pytest

from axelrod_wm.memory.frontier import CoMovement, FrontierResult, FrontierTester, RunningCorr, backfilled
from axelrod_wm.memory.working import DeviationHistory, DeviationPoint, point_key

AT = datetime(2024, 1, 1, tzinfo=UTC)


def test_push_ignores_non_finite_pairs():
    rc = RunningCorr()
    rc.push(1.0, 2.0)
    rc.push(math.nan, 1.0)
    rc.push(1.0, math.inf)
    assert rc.n == 1.0
    assert rc.pairs == [(1.0, 2.0)]


def _pt(z: float, innovation: float | None = None, observed: bool = False) -> DeviationPoint:
    return DeviationPoint(z=z, var=0.1, level=z, innovation=innovation, observed=observed)


def test_backfilled_skips_windows_with_no_move_at_all():
    dev = DeviationHistory(origin_date=date(2024, 1, 1))
    later, earlier = "b.y", "a.x"
    # day 6 is the later value's first report; on day 7 it is observed but nothing moved
    dev.points[point_key(later, 6)] = _pt(0.0, 0.0, True)
    dev.points[point_key(later, 7)] = _pt(0.0, 0.0, True)
    dev.points[point_key(later, 8)] = _pt(1.0, 1.0, True)
    dev.points[point_key(later, 9)] = _pt(3.0, 2.0, True)
    dev.points[point_key(earlier, 8)] = _pt(0.5)
    dev.points[point_key(earlier, 9)] = _pt(2.0)
    co = CoMovement(id="CM-1", earlier_id=earlier, later_id=later, lag_days=0, sign=1, first_seen=AT, last_seen=AT)
    out = backfilled(co, dev, day=10, width=1, backfill_days=3)
    # day 7 is skipped (all zero), days 8 and 9 are pushed
    assert out.corr.pairs == [(0.5, 1.0), (1.5, 2.0)]
    assert out.response.pairs == [(0.5, 1.0), (1.5, 2.0)]
    assert co.corr.n == 0.0                       # the original is untouched


def test_frontier_tester_is_abstract_and_its_stub_returns_nothing():
    with pytest.raises(TypeError):
        FrontierTester()  # type: ignore[abstract]

    class Echo(FrontierTester):
        def test(self, fold, wm, ltm, ctx, txn) -> FrontierResult:
            assert super().test(fold, wm, ltm, ctx, txn) is None
            return FrontierResult(logged=["x"])

    assert Echo().test(None, None, None, None, None).logged == ["x"]
