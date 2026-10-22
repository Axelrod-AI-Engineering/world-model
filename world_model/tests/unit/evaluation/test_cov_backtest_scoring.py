"""Backtest scoring on hand-built forecasts: omission and commission, interval coverage, CRPS, pattern hits,
realized series, and track-record updates."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from axelrod_wm.evaluation.backtest import (
    OmissionCommissionCalibrationScorer,
    apply_track_records,
    last_observed,
    pattern_hit,
    realized_series,
)
from axelrod_wm.evaluation.metrics import crps_quantiles
from axelrod_wm.model.distributions import DistSummary
from axelrod_wm.model.superentity import TrackRecord

NAN = float("nan")
AT = datetime(2024, 5, 1, tzinfo=timezone.utc)


def dist(*qs: float) -> DistSummary:
    q05, q10, q25, q50, q75, q90, q95 = qs
    return DistSummary.model_construct(mean=q50, sd=1.0, q05=q05, q10=q10, q25=q25, q50=q50, q75=q75, q90=q90, q95=q95)


def tight(c: float) -> DistSummary:
    """50% band c +- 0.1, 80% c +- 0.15, 90% c +- 0.2."""
    return dist(c - 0.2, c - 0.15, c - 0.1, c, c + 0.1, c + 0.15, c + 0.2)


WIDE_DOWN = dist(-3, -2.5, -2, -1, -0.5, 0.5, 1)    # median -1, P(X > 0) = 0.175
WIDE_UP = dist(-3, -2, -1, 0.6, 2, 3, 4)            # median 0.6, but P(X > 0) is only about 0.59
UNKNOWN = dist(*[NAN] * 7)

REALIZED = {
    "a": [0.0, None, 0.5, 1.0],       # rose 1.0, predicted to: both
    "b": [None, -1.0, None, None],    # no freeze-day point: measured from the forecast's own day 0
    "c": [0.0, 0.1, 0.1, 0.1],        # barely moved; a positive median without enough confidence
    "d": [0.0, 1.0, 1.0, 1.0],        # no forecast for it
    "e": [0.0, None, None, None],     # never observed in the window
    "f": [0.0, 0.2, None, None],      # an undefined forecast: no CRPS
    "g": [0.0, 0.0, 0.0, 0.0],        # predicted to rise, did not (commission)
    "h": [0.0, 0.0, 0.0, -2.0],       # fell, not predicted (omission)
}
Z = {"a": [tight(1.0)] * 4, "b": [tight(0.0)] + [WIDE_DOWN] * 3, "c": [WIDE_UP] * 4, "e": [tight(0.0)] * 4,
     "f": [UNKNOWN] * 4, "g": [tight(1.0)] * 4, "h": [tight(0.0)] * 4}


def forecast(targets=tuple(REALIZED) + ("z",), horizon: int = 3):
    return SimpleNamespace(horizon_days=horizon, targets=list(targets), z_summary=Z)


def test_scorer_omission_commission_coverage_and_crps():
    out = OmissionCommissionCalibrationScorer().score(forecast(), REALIZED, {})
    assert out["realized"] == ["a:+1", "b:-1", "h:-1"]
    assert out["predicted"] == ["a:+1", "b:-1", "g:+1"]
    assert out["omission_rate"] == pytest.approx(1 / 3) and out["commission_rate"] == pytest.approx(1 / 3)
    # observed days: a 2, b 1, c 3, f 1, g 3, h 3; covered in every band: a 1, b 1, c 3, h 2
    assert out["coverage"] == pytest.approx({"50": 7 / 13, "80": 7 / 13, "90": 7 / 13})
    assert set(out["per_target"]) == {"a", "b", "c", "g", "h"}
    a = out["per_target"]["a"]
    assert a["realized_change"] == 1.0 and a["predicted_change"] == 1.0 and a["observed_days"] == 2.0
    assert a["crps"] == pytest.approx((crps_quantiles(tight(1.0), 0.5) + crps_quantiles(tight(1.0), 1.0)) / 2)
    assert out["per_target"]["b"]["realized_change"] == -1.0


def test_scorer_thresholds_come_from_the_config():
    strict = OmissionCommissionCalibrationScorer().score(forecast(), REALIZED,
                                                        {"significant_effect": 1.5, "sign_probability": 0.99})
    assert strict["realized"] == ["h:-1"] and strict["predicted"] == []
    assert strict["omission_rate"] == 1.0 and strict["commission_rate"] == 0.0


def test_scorer_with_nothing_to_score():
    out = OmissionCommissionCalibrationScorer().score(forecast(targets=("d", "e")), REALIZED, {})
    assert out == {"omission_rate": 0.0, "commission_rate": 0.0, "coverage": {"50": 0.0, "80": 0.0, "90": 0.0},
                   "crps": 0.0, "per_target": {}, "realized": [], "predicted": []}


def test_last_observed():
    assert last_observed([0.0, 1.0, None, 2.0], 3) == 3
    assert last_observed([0.0, 1.0, None, 2.0], 2) == 1          # only up to the horizon
    assert last_observed([0.0, 1.0], 5) == 1                      # only as far as the series goes
    assert last_observed([0.0, None, None], 2) is None


def test_pattern_hit():
    fc = forecast()
    assert pattern_hit(["a"], fc, REALIZED, 0.5) is True
    assert pattern_hit(["a", "h"], fc, REALIZED, 0.5) is False   # h fell, predicted flat: 1 of 2 matched
    # none of these count: no forecast, no freeze-day point, never observed, or too small a move
    assert pattern_hit(["d", "b", "e", "c", "missing"], fc, REALIZED, 0.5) is None


class _Dev:
    def __init__(self) -> None:
        self.points = {11: SimpleNamespace(z=0.4, observed=True), 12: SimpleNamespace(z=0.9, observed=False)}

    def z_at(self, sid, day):
        return 0.1 if (sid, day) == ("x.v", 10) else None

    def point(self, sid, day):
        return self.points.get(day)


def test_realized_series_keeps_only_observed_points():
    assert realized_series(_Dev(), "x.v", 10, 3) == [0.1, 0.4, None, None]


class _Txn:
    def __init__(self) -> None:
        self.updates = []

    def update(self, path, key, **fields):
        self.updates.append((path, key, fields))


class _Engine:
    def __init__(self, updater) -> None:
        self.ltm = SimpleNamespace(object_generalizations=SimpleNamespace(patterns={
            "S1": SimpleNamespace(track_record=TrackRecord(hits=1, misses=1)),
            "S2": SimpleNamespace(track_record=TrackRecord()),
        }))
        self.components = {"generalization_updater": updater} if updater is not None else {}
        self.txn = _Txn()
        self.began = []
        self.mutator = SimpleNamespace(begin=self._begin)

    def context(self, learn, now):
        return ("ctx", learn, now)

    @contextmanager
    def _begin(self, cause, at):
        self.began.append((cause, at))
        yield self.txn


class _Updater:
    def __init__(self) -> None:
        self.calls = []

    def update_pattern(self, pid, ltm, ctx, txn, **kw):
        self.calls.append((pid, ctx, kw))


def test_track_records_go_through_the_mutator_and_the_updater():
    up = _Updater()
    eng = _Engine(up)
    apply_track_records(eng, {"S1": (2, 3), "S2": (0, 0), "S9": (1, 1)}, "evaluation:EVAL-1", AT)
    assert eng.began == [("evaluation:EVAL-1", AT)]
    # S2 had no trials and S9 is not a live pattern: only S1 changes
    assert eng.txn.updates == [("ltm.object_generalizations.patterns", "S1",
                                {"track_record": TrackRecord(hits=3, misses=2)})]
    assert up.calls == [("S1", ("ctx", True, AT), {"count_support": False, "hits": 2.0, "misses": 1.0})]


def test_track_records_without_an_updater():
    for eng in (_Engine(None), _Engine(SimpleNamespace())):        # none, or one that cannot pool patterns
        apply_track_records(eng, {"S2": (1, 1)}, "evaluation:EVAL-2", AT)
        assert eng.txn.updates == [("ltm.object_generalizations.patterns", "S2",
                                    {"track_record": TrackRecord(hits=1, misses=0)})]
