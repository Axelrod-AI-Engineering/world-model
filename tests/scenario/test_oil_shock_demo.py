"""The oil_shock_demo scenario: initialization, determinism, and restore (§15.1, §15.3, M7)."""

from __future__ import annotations

import pytest

from axelrod_wm.control.mutator import ChangeSet, apply_changeset
from axelrod_wm.events.ledger import LedgerKind
from axelrod_wm.memory.snapshots import MemoryBackend, load_state, state_hash
from axelrod_wm.sim.runner import build_runner
from axelrod_wm.sim.scenario import thesis_from_spec


def loaded_runner(record_checklist: bool = True):
    r = build_runner("oil_shock_demo", auto_approve=True, storage=MemoryBackend(), record_checklist=record_checklist)
    r.load()
    return r


def ledger_digest(runner) -> list[tuple]:
    return [(e.seq, str(e.kind), e.recorded_at.isoformat(), e.state_version, state_hash_of(e.payload))
            for e in runner.controller.engine.ledger.entries]


def state_hash_of(payload: dict) -> str:
    from axelrod_wm.core.serialization import canonical_json, sha256_text

    return sha256_text(canonical_json(payload))


def test_initialization_produces_the_step_0_state():
    r = loaded_runner()
    label, ok, detail = r.recorder.items[1]
    assert ok, detail
    eng = r.controller.engine
    assert r.step_index == 0
    # after the init snapshot, loading only adds the scenario's hypotheses
    info = eng.version_info(r.init_version)
    after = [e for e in eng.ledger.read(info.seq) if e.kind == LedgerKind.CHANGESET]
    assert after and all(e.payload["cause"].startswith("hypothesis:") for e in after)
    assert eng.state_hash == eng.full_state_hash()


def test_two_runs_with_the_same_seed_write_identical_ledgers():
    a, b = loaded_runner(False), loaded_runner(False)
    for _ in range(5):
        a.step()
        b.step()
    assert ledger_digest(a) == ledger_digest(b)
    assert a.controller.engine.state_hash == b.controller.engine.state_hash
    assert a.controller.engine.version == b.controller.engine.version


def test_posing_the_same_thesis_twice_is_identical_and_changes_nothing():
    r = loaded_runner(False)
    ctl = r.controller
    eng = ctl.engine
    spec = dict(r.theses_spec["T-01"])
    h0, v0, ids0, eng_ids0 = eng.state_hash, eng.version, dict(ctl.ids.counters), dict(eng.wm.ids.counters)
    first = ctl.pose_thesis(thesis_from_spec({**spec, "id": "T-01a"}, ctl.now))
    second = ctl.pose_thesis(thesis_from_spec({**spec, "id": "T-01a"}, ctl.now))
    assert first.based_on_version == second.based_on_version == v0
    for t in first.targets:
        assert first.summary[t] == second.summary[t]
        assert first.effect_summary[t] == second.effect_summary[t]
    assert [s.weight for s in first.scenarios] == [s.weight for s in second.scenarios]
    assert eng.state_hash == h0 and eng.version == v0
    assert dict(eng.wm.ids.counters) == eng_ids0
    # only the control plane's forecast counter moves
    assert {k: v for k, v in ctl.ids.counters.items() if not k.startswith("FC")} == \
        {k: v for k, v in ids0.items() if not k.startswith("FC")}


def test_the_init_snapshot_plus_the_ledger_restores_the_live_state():
    r = loaded_runner(False)
    for _ in range(4):
        r.step()
    eng = r.controller.engine
    info = eng.version_info(r.init_version)
    wm, ltm = load_state(eng.storage.load_snapshot(r.init_version))
    for e in eng.ledger.read(info.seq if info else 0):
        if e.kind == LedgerKind.CHANGESET:
            apply_changeset(wm, ltm, ChangeSet.model_validate(e.payload))
    assert state_hash(wm, ltm) == eng.full_state_hash() == eng.state_hash


@pytest.mark.slow
def test_the_full_checklist_passes_headless():
    r = loaded_runner()
    r.play()
    failed = [(label, r.recorder.items[n][2]) for n, (label, ok) in enumerate(r.checklist(), start=1) if not ok]
    assert not failed, failed
