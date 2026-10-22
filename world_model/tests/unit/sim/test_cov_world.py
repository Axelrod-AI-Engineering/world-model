"""The synthetic world on a hand-built, noise-free construction: moderated channels (threshold and additive),
standardized shocks, the release calendar, realized values, and the data feed's set-up."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from axelrod_wm.engine.initialize import ConstructionSpec
from axelrod_wm.sim.world import SyntheticDataFeed, SyntheticWorld, TruthSpec

ORIGIN = date(2026, 1, 5)          # a Monday


def sub(sid: str) -> dict:
    return {"id": sid, "name": sid, "attribute_kind": "index_level", "unit": "pts", "family": "gaussian",
            "mean": 0.0, "scale": 1.0}


def construction(form: str, coefficient: float, threshold: float | None = None) -> ConstructionSpec:
    ent = lambda eid, subs: {"id": eid, "name": eid.upper(), "kind": "company", "category_tags": ["SC"],  # noqa: E731
                             "subentities": [sub(s) for s in subs]}
    return ConstructionSpec.model_validate({
        "entities": [ent("a", ["a.x", "a.m"]), ent("b", ["b.y"])],
        "interactions": [{"id": "e1", "source": "a.x", "target": "b.y", "label": "moves",
                          "effect": {"family": "gaussian", "mu": 1.0, "sigma": 0.1},
                          "kernel": {"delay_days": 1, "lag_days": 1},
                          "parameters": [{"name": "gate", "moderator": "a.m", "form": form,
                                          "coefficient": {"mu": coefficient}, "threshold": threshold}]}],
    })


TRUTH = TruthSpec(effect_multiplier_sd=0.0, ar_coefficient=0.0, noise_sd={"default": 0.0},
                  release_calendar={"default": ["weekly"], "daily": ["a.x", "ghost.v"], "never": None})


def world(form: str, coefficient: float, shocks: list[tuple[datetime, list[dict]]], threshold=None) -> SyntheticWorld:
    return SyntheticWorld(construction(form, coefficient, threshold), TRUTH, seed=1, scripted_shocks=shocks,
                          origin=ORIGIN)


def at(day: int) -> datetime:
    """Noon of `day`, without a time zone (read as UTC)."""
    return datetime(2026, 1, 5 + day, 12, 0)


X_UP = (at(1), [{"subentity": "a.x", "delta": 1.0}])          # standardized: a move of 1 sd
M_UP = (at(1), [{"subentity": "a.m", "delta": 1.0}])


def test_naive_times_and_shock_sizes():
    absolute = (at(2), [{"subentity": "a.m", "delta": 2.5, "mode": "absolute"}])     # native units (scale 1)
    w = world("threshold", 0.0, [X_UP, absolute], threshold=10.0)
    assert w.day_of(at(1)) == 1 == w.day_of(at(1).replace(tzinfo=timezone.utc))
    w.advance(at(6))
    assert w.z_at("a.x", 0) == 0.0 and w.z_at("a.x", 1) == 1.0 and w.z_at("a.x", 6) == 1.0
    assert w.z_at("a.m", 1) == 0.0 and w.z_at("a.m", 2) == pytest.approx(2.5)


def test_a_threshold_moderator_gates_the_channel():
    closed = world("threshold", 0.0, [X_UP], threshold=0.5)
    opened = world("threshold", 0.0, [X_UP, M_UP], threshold=0.5)
    for w in (closed, opened):
        w.advance(at(10))
    assert all(closed.z_at("b.y", d) == 0.0 for d in range(11))
    assert opened.z_at("b.y", 10) > 0.5


def test_an_additive_moderator_adds_to_the_target():
    w = world("additive", 2.0, [M_UP])
    w.advance(at(4))
    assert w.z_at("b.y", 1) == 0.0                     # reads the moderator through the day before
    assert w.z_at("b.y", 2) == pytest.approx(2.0) and w.z_at("b.y", 4) == pytest.approx(2.0)


def test_realized_values_in_native_units():
    w = world("threshold", 0.0, [X_UP], threshold=0.5)
    assert w.realized("a.x", at(-3), at(2)) == [0.0, 1.0, 1.0]     # from the origin on
    assert w.days_done == 3


def test_the_release_calendar():
    w = world("threshold", 0.0, [X_UP], threshold=0.5)
    cal = w._calendar()
    assert cal == {"a.x": "daily", "a.m": "weekly", "b.y": "weekly"}       # unknown ids are skipped
    w.advance(at(6))
    rel = w.releases(None, datetime(2026, 1, 11, tzinfo=timezone.utc))
    by_day = {e.published_at.date(): e.data for e in rel}
    assert set(by_day) == {date(2026, 1, d) for d in range(5, 10)}         # weekdays only
    assert by_day[date(2026, 1, 9)] == {"a.x": 1.0, "a.m": 0.0, "b.y": 0.0}  # Friday: the weekly series too
    assert by_day[date(2026, 1, 6)] == {"a.x": 1.0}
    empty = SyntheticWorld(construction("threshold", 0.0, 0.5), TRUTH.model_copy(update={"release_calendar": {
        "default": []}}), seed=1, origin=ORIGIN)
    assert set(empty._calendar().values()) == {"monthly"}


def test_the_data_feed_needs_a_world():
    with pytest.raises(ValueError, match="needs a SyntheticWorld"):
        SyntheticDataFeed()
