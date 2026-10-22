"""Daily consolidation (§8.12): episodes, analog responses, entity memories, reset and prune."""

from __future__ import annotations

from axelrod_wm.repo.snapshots import state_hash
from tests.conftest import close_day, constructed_engine, make_config, observe_event, predict_day, run_days
from tests.unit.dynamics.test_daily_model import _native

OIL, CPI = "resources_energy.oil_price", "inflation.headline_cpi"


def _day(eng, z_oil, z_cpi, tags=(), event_type="data_release", extra=None):
    """Predict, fold one or two events, and close the next day."""
    d = eng.wm.last_processed_day + 1
    dev = eng.wm.deviations
    predict_day(eng, d)
    evs = [observe_event(f"GUE-{d}", {OIL: _native(eng, OIL, z_oil), CPI: _native(eng, CPI, z_cpi)}, dev.date_of(d),
                         event_type=event_type, tags=list(tags))]
    if extra is not None:
        evs.append(extra(d))
    from datetime import datetime, time, timezone

    for ev in evs:
        eng.learning.run(ev, datetime.combine(dev.date_of(d), time(21), tzinfo=timezone.utc), d)
    return close_day(eng, d)


def test_consolidation_builds_an_episode_and_resets(warm_engine):
    eng = warm_engine
    _day(eng, 0.0, 0.0)
    moves, rep = _day(eng, 2.0, 0.5, tags=["energy-shock-like"], event_type="supply_shock")
    ep = eng.ltm.prior_states.episodes[rep.episode_id]
    assert ep.day == eng.wm.deviations.date_of(1) and ep.day_index == 1
    assert "energy-shock-like" in ep.tags and "supply_shock" in ep.event_types
    assert not ep.routine
    assert OIL in ep.deltas and ep.deltas[OIL][1] > ep.deltas[OIL][0]
    assert eng.wm.episode_buffer == [] and eng.wm.fold_accumulators == {}
    assert eng.wm.last_processed_day == 1 and eng.wm.clock == eng.wm.deviations.day_end(1)
    assert rep.version == eng.version


def test_routine_days_make_routine_episodes(warm_engine):
    eng = warm_engine
    _, rep = _day(eng, 0.1, 0.0)
    assert eng.ltm.prior_states.episodes[rep.episode_id].routine
    assert rep.episode_id not in [e.id for e in eng.ltm.prior_states.analog_candidates()]


def test_non_routine_episodes_pool_the_response_that_followed(warm_engine):
    eng = warm_engine
    _day(eng, 0.0, 0.0)
    _, rep = _day(eng, 2.0, 0.0, tags=["energy-shock-like"], event_type="supply_shock")
    first = eng.ltm.prior_states.episodes[rep.episode_id]
    w0 = sum(w for _, w in first.response_effects.values())
    for k in range(20):
        _day(eng, 2.0, 0.05 * k)
    ep = eng.ltm.prior_states.episodes[rep.episode_id]
    assert sum(w for _, w in ep.response_effects.values()) >= w0
    assert CPI in ep.response_deltas


def test_entity_memory_sets_level_noise_after_eight_weeks():
    eng = constructed_engine(build=True)
    eng.components  # noqa: B018
    run_days(eng, 70, lambda d: [observe_event(f"GUE-{d}", {OIL: _native(eng, OIL, 0.3 * ((d // 7) % 3))},
                                               eng.wm.deviations.date_of(d))])
    sub = eng.wm.graph.subentities[OIL]
    assert sub.level_noise is not None and 0.02 <= sub.level_noise <= 1.0
    assert len(eng.ltm.entity_memories["resources_energy"].entries) == 10


def test_prune_keeps_the_activity_window_and_history_window():
    eng = constructed_engine(build=True, config=make_config(history={"keep_days": 30}))
    run_days(eng, 40, lambda d: [observe_event(f"GUE-{d}", {OIL: _native(eng, OIL, 0.5 * (d % 5))},
                                               eng.wm.deviations.date_of(d))])
    dev = eng.wm.deviations
    width = eng.config.abduction.window_days
    last = eng.wm.last_processed_day
    assert all(r.day > last - width for r in eng.wm.activity_log.values())
    assert all(int(k.rpartition("|")[2]) > last - width for k in eng.wm.channel_phi)
    keep = eng.config.keep_days(0)
    if keep < last:
        assert dev.first_kept_day == last - keep + 1
        assert dev.point(OIL, dev.first_kept_day - 1) is None


def test_consolidation_is_replayable(warm_engine):
    eng = warm_engine
    for k in range(3):
        _day(eng, 0.5 * k, 0.2 * k)
    wm, ltm = eng.restore(eng.version)
    assert state_hash(wm, ltm) == eng.state_hash == state_hash(eng.wm, eng.ltm)
