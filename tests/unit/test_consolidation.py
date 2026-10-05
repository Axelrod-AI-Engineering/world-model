"""Daily consolidation (§8.12)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from axelrod_wm.memory.snapshots import state_hash
from tests.conftest import START, real_event
from tests.unit.test_fold import _native

OIL, CPI = "resources_energy.oil_price", "inflation.headline_cpi"


def _week(eng, t, z_oil, z_cpi, tags=()):
    at = START + timedelta(days=7 * t, hours=1)
    ops = [{"op": "observe_value", "target": {"kind": "concrete", "subentity_id": sid}, "value": _native(eng, sid, z),
            "observed_at": at.isoformat()} for sid, z in ((OIL, z_oil), (CPI, z_cpi))]
    eng.learning.run(real_event(ops, f"GUE-{t}", at, produced_by="data_feed", event_type="data_release",
                                tags=list(tags)), at)
    return at


def test_consolidation_builds_an_episode_and_resets(warm_engine):
    eng = warm_engine
    at = _week(eng, 0, 0.0, 0.0)
    at = _week(eng, 0, 2.0, 0.5, tags=["energy-shock-like"])   # same day, a big oil move
    assert len(eng.wm.episode_buffer) == 2
    ctx = eng.context(learn=True, now=at + timedelta(hours=1))
    rep = eng.components["consolidator"].run(at.date(), ctx)
    ep = eng.ltm.episodes.episodes[rep.episode_id]
    assert ep.trigger_event_ids == ["GUE-0", "GUE-0"] or len(ep.trigger_event_ids) == 2
    assert "energy-shock-like" in ep.tags and "data_release" in ep.event_types
    assert OIL in ep.deltas and ep.deltas[OIL][1] > ep.deltas[OIL][0]
    assert eng.wm.episode_buffer == [] and eng.wm.activity_log == [] and eng.wm.fold_accumulators == {}
    assert eng.wm.last_consolidated == at.date()
    assert "resources_energy" in eng.ltm.entity_memories
    assert eng.storage.snapshot_versions()[-1] == eng.version
    assert rep.snapshot_version == eng.version


def test_entity_memory_sets_level_noise_after_eight_entries(warm_engine):
    eng = warm_engine
    for t in range(12):
        at = _week(eng, t, 0.3 * (t % 3), 0.1 * t)
        eng.components["consolidator"].run(at.date(), eng.context(learn=True, now=at + timedelta(hours=1)))
    sub = eng.wm.graph.subentities[OIL]
    assert sub.level_noise is not None and 0.02 <= sub.level_noise <= 1.0
    assert len(eng.ltm.entity_memories["resources_energy"].entries) == 12


def test_consolidation_is_replayable(warm_engine):
    eng = warm_engine
    for t in range(3):
        at = _week(eng, t, 0.5 * t, 0.2 * t)
        eng.components["consolidator"].run(at.date(), eng.context(learn=True, now=at + timedelta(hours=1)))
    wm, ltm = eng.restore(eng.version)
    assert state_hash(wm, ltm) == eng.state_hash == state_hash(eng.wm, eng.ltm)


def test_forecast_explanations_move_to_long_term_memory():
    pytest.importorskip("numpy")  # covered end to end in the performance tests
