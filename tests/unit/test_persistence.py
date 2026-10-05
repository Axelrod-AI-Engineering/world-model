"""M2: the mutator, change sets, ledger, versions, snapshots, hashes, frontier seeds, tracers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest

from axelrod_wm.core.distributions import Beta, DistSummary
from axelrod_wm.core.evidence import Origin
from axelrod_wm.core.hypothesis import Hypothesis, HypothesisKind
from axelrod_wm.core.temporal import Bitemporal, TimeState
from axelrod_wm.engine.engine import Engine
from axelrod_wm.engine.explain_records import Explanation
from axelrod_wm.engine.initialize import ConstructionSpec, Initializer, SeedFile
from axelrod_wm.engine.performance.records import Forecast
from axelrod_wm.events.ledger import LedgerKind
from axelrod_wm.memory.snapshots import FilesBackend, state_hash
from axelrod_wm.memory.working import ActivityRecord, ForecastStateView
from axelrod_wm.trace import BroadcastTracer, NullTracer, Phase, RecordingTracer
from tests.conftest import SEEDS, START, constructed_engine, make_config

T1 = START + timedelta(days=7)
T2 = START + timedelta(days=14)


def _mixed_changes(eng: Engine, now: datetime) -> None:
    with eng.mutator.begin("test-mixed", now=now) as txn:
        txn.set("wm.clock", now)
        sub = eng.wm.graph.subentities["inflation.headline_cpi"]
        txn.update("subentities", sub.id, level_mean=0.5, level_var=0.2, last_update_step=3)
        ts = TimeState(at=Bitemporal(valid_at=now, recorded_at=now), values={"mean": 3.0}, source_event_id="X")
        txn.append_to("subentities", sub.id, "history", ts)
        txn.merge("wm.deviations", {"z": {sub.id: {3: 0.5, 4: 0.7}}, "innovation": {sub.id: {4: 1.2}}})
        txn.merge("wm.fold_accumulators", {"e08": (0.3, 0.9)})
        txn.append("wm.activity_log", ActivityRecord(step=4, interaction_id="e08", contribution=0.4, target_move=0.2))
        txn.update("interactions", "e08", existence=Beta(alpha=10.0, beta=1.0))
        hid = txn.new_id("H")
        txn.add("hypotheses", Hypothesis(id=hid, kind=HypothesisKind.INTERACTION_ABSENT, statement="e43 absent",
                                         interaction_id="e43", source_id="inflation.headline_cpi",
                                         target_id="federal_reserve.policy_stance", probability=0.4,
                                         scored_at=now, origin=Origin.HUMAN))
        txn.remove("super_interactions", sorted(eng.wm.graph.super_interactions)[0])


def test_live_hash_matches_full_hash_and_restore():
    eng = constructed_engine()
    v0 = eng.version
    _mixed_changes(eng, T1)
    assert eng.version == v0 + 1
    assert eng.state_hash == state_hash(eng.wm, eng.ltm)
    wm, ltm = eng.snapshots.restore(eng.version)          # replays from the empty state
    assert state_hash(wm, ltm) == eng.state_hash
    assert wm.deviations.z["inflation.headline_cpi"] == {3: 0.5, 4: 0.7}
    assert wm.fold_accumulators["e08"] == (0.3, 0.9)


def test_restore_from_snapshot_plus_ledger():
    eng = constructed_engine()
    eng.save_snapshot()
    snap_version = eng.version
    _mixed_changes(eng, T1)
    with eng.mutator.begin("more", now=T2) as txn:
        txn.merge("wm.deviations", {"z": {"inflation.headline_cpi": {4: None, 5: 1.0}}})
        txn.set("wm.clock", T2)
    assert eng.storage.snapshot_versions() == [snap_version]
    wm, ltm = eng.snapshots.restore(eng.version)
    assert state_hash(wm, ltm) == eng.state_hash
    assert wm.deviations.z["inflation.headline_cpi"] == {3: 0.5, 5: 1.0}
    # an intermediate version restores too, and matches its stored hash
    wm_mid, ltm_mid = eng.snapshots.restore(eng.version - 1)
    assert state_hash(wm_mid, ltm_mid) == eng.version_info(eng.version - 1).state_hash


def test_as_of_returns_the_right_version():
    eng = constructed_engine()
    _mixed_changes(eng, T1)
    v1 = eng.version
    with eng.mutator.begin("later", now=T2) as txn:
        txn.set("wm.clock", T2)
    _, _, v = eng.snapshots.as_of(T1 + timedelta(days=1))
    assert v == v1
    _, _, v = eng.snapshots.as_of(T2)
    assert v == eng.version


def test_rollback_on_exception_leaves_no_trace():
    eng = constructed_engine()
    before_hash, before_version = eng.state_hash, eng.version
    before_seq = eng.ledger.next_seq
    with pytest.raises(RuntimeError):
        with eng.mutator.begin("boom", now=T1) as txn:
            _ = txn.new_id("int")
            txn.update("subentities", "inflation.headline_cpi", level_mean=9.0)
            txn.merge("wm.deviations", {"z": {"inflation.headline_cpi": {1: 1.0}}})
            txn.remove("interactions", "e01")
            raise RuntimeError("fail")
    assert eng.version == before_version and eng.ledger.next_seq == before_seq
    assert state_hash(eng.wm, eng.ltm) == before_hash
    assert "e01" in eng.wm.graph.interactions
    assert "int" not in eng.wm.ids.counters


def test_nested_transactions_commit_once():
    eng = constructed_engine()
    v = eng.version
    with eng.mutator.begin("outer", now=T1) as outer:
        outer.set("wm.clock", T1)
        with eng.mutator.begin("inner") as inner:
            assert inner is outer
            inner.update("subentities", "inflation.core_cpi", level_mean=0.1)
    assert eng.version == v + 1
    cs = eng.mutator.last_changeset
    assert cs.cause == "outer" and len(cs.changes) == 2


def _forecast_view(thesis_id: str) -> ForecastStateView:
    now = START
    s = DistSummary(mean=0, sd=0, q05=0, q10=0, q25=0, q50=0, q75=0, q90=0, q95=0)
    fc = Forecast(id=f"FC-{thesis_id}-1", thesis_id=thesis_id, based_on_version=1, config_hash="x", seed=1,
                  created_at=now, step_days=7, horizon_steps=1, targets=["a.b"], summary={"a.b": [s, s]},
                  effect_summary={"a.b": [s, s]}, scenarios=[], isolated={}, decomposition={}, networks=[])
    ex = Explanation(id=f"EX-{fc.id}", subject_kind="forecast", subject_id=fc.id, state_version=1, created_at=now,
                     key_interactions=[], top_paths=[], analogs=[], networks=[], scenarios=[], assumptions=[],
                     notes=[], text="", index_keys=set())
    return ForecastStateView(thesis_id=thesis_id, forecast=fc, explanation=ex)


def test_forecast_layer_changes_do_not_bump_version_or_hash():
    eng = constructed_engine()
    v, h = eng.version, eng.state_hash
    ids_before = dict(eng.wm.ids.counters)
    with eng.mutator.begin("pose:T-01", now=T1) as txn:
        txn.add("forecast_layer", _forecast_view("T-01"))
        txn.set("forecast_layer.pose_counts", {"T-01": 1})
    assert eng.version == v
    assert state_hash(eng.wm, eng.ltm) == h
    assert eng.wm.ids.counters == ids_before
    last = eng.ledger.entries[-1]
    assert last.kind == LedgerKind.CHANGESET and last.payload["version_after"] == v


def test_ids_are_deterministic_and_saved_in_changesets():
    a, b = constructed_engine(), constructed_engine()
    for eng in (a, b):
        with eng.mutator.begin("ids", now=T1) as txn:
            ids = [txn.new_id("int"), txn.new_id("int"), txn.new_id("PEND")]
        assert ids == ["int-000001", "int-000002", "PEND-000001"]
        cs = eng.mutator.last_changeset
        assert cs.id_counters_after["int"] == 2 and cs.id_counters_after["CS"] == eng.wm.ids.counters["CS"]
    assert [e.payload for e in a.ledger.entries] == [e.payload for e in b.ledger.entries]


def test_files_backend_round_trip(tmp_path):
    cfg = make_config(storage={"backend": "files", "path": str(tmp_path / "store")})
    store = FilesBackend(tmp_path / "store")
    eng = Engine(cfg, store, NullTracer())
    init = Initializer(eng)
    init.construct(ConstructionSpec.load("data/construction"), "data/taxonomy", start=START)
    init.load_seeds(SeedFile.load(SEEDS), now=START)
    eng.save_snapshot()
    _mixed_changes(eng, T1)
    # a fresh engine reading the same files restores the live state
    store2 = FilesBackend(tmp_path / "store")
    eng2 = Engine(cfg, store2, NullTracer())
    assert len(eng2.ledger.entries) == len(eng.ledger.entries)
    wm, ltm = eng2.snapshots.restore(eng.version)
    assert state_hash(wm, ltm) == eng.state_hash
    assert (tmp_path / "store" / "ledger.jsonl").exists()
    assert list((tmp_path / "store" / "snapshots").glob("v*.json.gz"))


def test_frontier_seeds_load():
    eng = constructed_engine()
    Initializer(eng).load_frontier_seeds(SeedFile.load(SEEDS), now=START + timedelta(days=1100))
    entries = list(eng.ltm.frontier.entries.values())
    assert len(entries) == 1
    co = entries[0]
    assert (co.earlier_id, co.later_id, co.lag_steps, co.sign, co.support, co.seeded) == (
        "inflation.headline_cpi", "confidence.consumer_confidence", 1, -1, 1.0, True)
    h = eng.wm.hypotheses[co.hypothesis_id]
    assert h.kind == HypothesisKind.INTERACTION_PRESENT and h.comovement_id == co.id
    assert h.subject_entity_ids == ["confidence", "inflation"]
    assert abs(h.probability - 1.0 / 5.0) < 1e-12


def test_tracers(tmp_path):
    NullTracer().emit(Phase.INGEST, "x")
    rec = RecordingTracer("run-t", tmp_path)
    rec.set_context(sim_time=START, state_version=3)
    rec.emit(Phase.INGEST, "market_event.received", refs=["ME-01"], headline="h")
    rec.emit(Phase.REFINE, "refine.step", op_index=0)
    assert [e.seq for e in rec.events] == [1, 2] and rec.events[0].state_version == 3
    assert len((tmp_path / "run-t.jsonl").read_text().splitlines()) == 2
    assert [e.kind for e in rec.since(1)] == ["refine.step"]

    async def run() -> dict:
        bt = BroadcastTracer("run-b")
        q: asyncio.Queue = asyncio.Queue()
        bt.subscribe(asyncio.get_running_loop(), q)
        bt.emit(Phase.FOLD, "fold.edge", refs=["e08"])
        return await asyncio.wait_for(q.get(), 1.0)

    msg = asyncio.run(run())
    assert msg["type"] == "trace" and msg["event"]["kind"] == "fold.edge" and msg["event"]["refs"] == ["e08"]
    json.dumps(msg)                      # JSON-ready for the /ws stream
