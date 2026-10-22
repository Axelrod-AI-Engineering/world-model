"""Persistence (§7.7, §9): the mutator's actions, change sets, the ledger, versions, snapshots, hashes,
frontier seeds, and tracers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta

import pytest

from axelrod_wm.engine.engine import Engine
from axelrod_wm.engine.initialize import ConstructionSpec, Initializer, SeedFile
from axelrod_wm.inference.records import Forecast
from axelrod_wm.memory.long_term import LongTermMemory
from axelrod_wm.memory.working import (
    ActivityRecord,
    DeviationPoint,
    ForecastStateView,
    activity_key,
    point_key,
)
from axelrod_wm.model.distributions import Beta, DistSummary
from axelrod_wm.model.evidence import Origin
from axelrod_wm.model.explanation import Explanation
from axelrod_wm.model.hypothesis import Hypothesis, HypothesisKind
from axelrod_wm.model.temporal import Bitemporal, TimeState
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.snapshots import FilesBackend, RestoreError, state_hash
from axelrod_wm.trace import BroadcastTracer, NullTracer, Phase, RecordingTracer
from tests.conftest import (
    SEEDS,
    START,
    START_DATE,
    VOCAB,
    constructed_engine,
    make_config,
    observe_event,
    run_days,
)

CPI = "inflation.headline_cpi"


def _mixed_changes(eng: Engine, at: datetime) -> None:
    """Every action on every kind of collection, in one transaction."""
    with eng.mutator.begin("test-mixed", at=at) as txn:
        txn.set("wm.clock", at)
        txn.update("wm.graph.subentities", CPI, level_mean=0.5, level_var=0.2)
        ts = [TimeState(at=Bitemporal(valid_at=at, recorded_at=at), values={"mean": 3.0 + k}, source_event_id="X")
              for k in range(3)]
        txn.append_to("wm.graph.subentities", CPI, "history", *ts, keep_last=2)
        txn.add("wm.deviations.points", DeviationPoint(z=0.5, var=0.1, level=0.4), key=point_key(CPI, 3))
        txn.add("wm.deviations.points", DeviationPoint(z=0.7, var=0.1, level=0.6, innovation=1.2, observed=True),
                key=point_key(CPI, 4))
        txn.put("wm.fold_accumulators", "e08", (0.3, 0.9))
        txn.put("wm.channel_phi", "e08|4", 0.25)
        txn.add("wm.activity_log", ActivityRecord(day=4, channel_id="e08", contribution_change=0.4, target_move=0.2),
                key=activity_key(4, "e08"))
        txn.update("wm.graph.interactions", "e08", existence=Beta(alpha=10.0, beta=1.0))
        txn.update("wm.graph.interactions", "e09", **{"forward.effect": eng.wm.graph.interactions["e01"].forward.effect})
        hid = txn.new_id("H")
        txn.add("wm.hypotheses", Hypothesis(id=hid, kind=HypothesisKind.INTERACTION_ABSENT, statement="e43 absent",
                                            interaction_id="e43", source_id=CPI,
                                            target_id="federal_reserve.policy_stance", probability=0.4,
                                            scored_at=at, origin=Origin.HUMAN))
        txn.append("wm.pending_episode_tags", "decision-outcome")
        txn.remove("wm.graph.super_interactions", sorted(eng.wm.graph.super_interactions)[0])


def test_long_term_memory_has_four_parts_plus_prior_states():
    assert list(LongTermMemory.model_fields) == ["object_generalizations", "interaction_generalizations",
                                                 "entity_memories", "correlation_frontier", "prior_states"]


def test_live_hash_matches_full_hash_and_restore():
    eng = constructed_engine()
    v0 = eng.version
    _mixed_changes(eng, START)
    assert eng.version == v0 + 1
    assert eng.state_hash == state_hash(eng.wm, eng.ltm)
    wm, ltm = eng.snapshots.restore(eng.version)          # replays from the empty state
    assert state_hash(wm, ltm) == eng.state_hash
    assert wm.deviations.z(CPI, 4) == 0.7 and wm.deviations.point(CPI, 4).observed
    assert wm.fold_accumulators["e08"] == (0.3, 0.9)
    assert wm.graph.interactions["e09"].forward.effect == eng.wm.graph.interactions["e01"].forward.effect


def test_changesets_record_new_values_only():
    eng = constructed_engine()
    _mixed_changes(eng, START)
    cs = eng.mutator.last_changeset
    actions = {c.action for c in cs.changes}
    assert actions >= {"add", "update", "put", "append", "truncate", "remove"}
    hist = [c for c in cs.changes if c.action == "append" and c.field == "history"]
    assert hist and hist[0].after["values"] == {"mean": 3.0}          # only the appended item
    nested = [c for c in cs.changes if c.collection == "wm.graph.interactions" and c.id == "e09"]
    assert list(nested[0].after) == ["forward.effect"]                 # a nested field, not the whole edge
    assert all(c.before is None for c in cs.changes if c.action != "remove")
    # a removal keeps only enough to name the record in the log (restructure), never a before-image
    naming = {"name", "label", "source_id", "target_id", "pattern_id"}
    assert all(c.before is None or set(c.before) <= naming for c in cs.changes if c.action == "remove")


def test_restore_from_snapshot_plus_ledger():
    eng = constructed_engine()
    eng.save_snapshot()
    snap_version = eng.version
    _mixed_changes(eng, START)
    with eng.mutator.begin("more", at=START + timedelta(days=1)) as txn:
        txn.remove("wm.deviations.points", point_key(CPI, 3))
        txn.add("wm.deviations.points", DeviationPoint(z=1.0, var=0.1, level=1.0), key=point_key(CPI, 5))
        txn.clear("wm.pending_episode_tags")
    assert eng.storage.snapshot_versions() == [snap_version]
    wm, ltm = eng.snapshots.restore(eng.version)
    assert state_hash(wm, ltm) == eng.state_hash
    assert wm.deviations.z_at(CPI, 3) is None and wm.deviations.z(CPI, 5) == 1.0
    wm_mid, ltm_mid = eng.snapshots.restore(eng.version - 1)
    assert state_hash(wm_mid, ltm_mid) == eng.version_info(eng.version - 1).state_hash


def test_as_of_lands_on_the_close_of_a_day():
    eng = constructed_engine(build=True)
    run_days(eng, 3, lambda d: [observe_event(f"GUE-{d}", {CPI: 2.8 + 0.1 * d}, eng.wm.deviations.date_of(d))])
    dev = eng.wm.deviations
    cons = [v for v in eng.storage.versions() if v.cause.startswith("close:")]
    assert len(cons) == 3
    # a time in the middle of day 2 lands on the end of day 1
    _, _, v = eng.snapshots.as_of(dev.day_start(2) + timedelta(hours=12))
    assert v == cons[1].version
    _, _, v = eng.snapshots.as_of(dev.day_end(2))
    assert v == cons[2].version


def test_ledger_grows_linearly_with_days():
    """A processed day's change sets hold only that day's new points, channel_phi values, and list
    appends, so ledger bytes per day stay flat as the history grows."""
    eng = constructed_engine(build=True)
    sizes = []
    for chunk in range(4):
        before = sum(len(json.dumps(e.payload)) for e in eng.ledger.read())
        run_days(eng, 30, lambda d: [observe_event(f"GUE-{d}", {CPI: 2.8 + 0.01 * (d % 7)},
                                                   eng.wm.deviations.date_of(d))])
        sizes.append(sum(len(json.dumps(e.payload)) for e in eng.ledger.read()) - before)
    assert max(sizes[1:]) < 1.25 * min(sizes[1:]), sizes


def test_rollback_on_exception_leaves_no_trace():
    eng = constructed_engine()
    before_hash, before_version = eng.state_hash, eng.version
    before_seq = eng.ledger.next_seq
    with pytest.raises(RuntimeError):
        with eng.mutator.begin("boom", at=START) as txn:
            _ = txn.new_id("int")
            txn.update("wm.graph.subentities", CPI, level_mean=9.0)
            txn.add("wm.deviations.points", DeviationPoint(z=1.0, var=0.1, level=1.0), key=point_key(CPI, 1))
            txn.append_to("wm.graph.interactions", "e01", "time_states",
                          TimeState(at=Bitemporal(valid_at=START, recorded_at=START), values={}))
            txn.remove("wm.graph.interactions", "e02")
            raise RuntimeError("fail")
    assert eng.version == before_version and eng.ledger.next_seq == before_seq
    assert state_hash(eng.wm, eng.ltm) == before_hash
    assert "e02" in eng.wm.graph.interactions
    assert "int" not in eng.wm.ids.counters


def test_nested_transactions_commit_once():
    eng = constructed_engine()
    v = eng.version
    with eng.mutator.begin("outer", at=START) as outer:
        outer.set("wm.clock", START)
        with eng.mutator.begin("inner") as inner:
            assert inner is outer
            inner.update("wm.graph.subentities", "inflation.core_cpi", level_mean=0.1)
    assert eng.version == v + 1
    cs = eng.mutator.last_changeset
    assert cs.cause == "outer" and len(cs.changes) == 2


def _forecast_view(thesis_id: str) -> ForecastStateView:
    s = DistSummary(mean=0, sd=0, q05=0, q10=0, q25=0, q50=0, q75=0, q90=0, q95=0)
    fc = Forecast(id=f"FC-{thesis_id}-1", thesis_id=thesis_id, based_on_version=1, config_hash="x", seed=1,
                  created_at=START, horizon_days=1, targets=["a.b"], summary={"a.b": [s, s]},
                  effect_summary={"a.b": [s, s]}, scenarios=[], isolated={}, decomposition={}, networks=[])
    ex = Explanation(id=f"EX-{fc.id}", subject_kind="forecast", subject_id=fc.id, state_version=1, created_at=START,
                     key_interactions=[], top_paths=[], analogs=[], networks=[], scenarios=[], assumptions=[],
                     notes=[], text="", index_keys=set())
    return ForecastStateView(thesis_id=thesis_id, forecast=fc, explanation=ex)


def test_forecast_layer_changes_do_not_bump_version_or_hash():
    eng = constructed_engine()
    v, h = eng.version, eng.state_hash
    ids_before = dict(eng.wm.ids.counters)
    with eng.mutator.begin("pose:T-01", at=START) as txn:
        txn.add("wm.forecast_layer.by_thesis", _forecast_view("T-01"))
        txn.set("wm.forecast_layer.pose_counts", {"T-01": 1})
    assert eng.version == v
    assert state_hash(eng.wm, eng.ltm) == h
    assert eng.wm.ids.counters == ids_before
    last = eng.ledger.entries[-1]
    assert last.kind == LedgerKind.CHANGESET and last.payload["version_after"] == v
    # and replay skips it
    wm, ltm = eng.snapshots.restore(eng.version)
    assert state_hash(wm, ltm) == h


def test_ids_are_deterministic_and_saved_in_changesets():
    a, b = constructed_engine(), constructed_engine()
    for eng in (a, b):
        with eng.mutator.begin("ids", at=START) as txn:
            ids = [txn.new_id("int"), txn.new_id("int"), txn.new_id("PEND")]
        assert ids == ["int-000001", "int-000002", "PEND-000001"]
        cs = eng.mutator.last_changeset
        assert cs.id_counters_after["int"] == 2 and cs.id_counters_after["CS"] == eng.wm.ids.counters["CS"]
    assert [e.payload for e in a.ledger.entries] == [e.payload for e in b.ledger.entries]


def test_files_backend_round_trip(tmp_path):
    cfg = make_config(storage={"backend": "files", "path": str(tmp_path / "store")})
    store = FilesBackend(tmp_path / "store")
    eng = Engine(cfg, store, NullTracer(), vocab=VOCAB)
    init = Initializer(eng)
    init.construct(ConstructionSpec.load("world_model/examples/worlds/economy"), "world_model/taxonomy", start=START_DATE, vocab=VOCAB)
    init.load_seeds(SeedFile.load(SEEDS), now=eng.wm.clock)
    eng.save_snapshot()
    _mixed_changes(eng, START)
    store.flush()
    # a fresh engine reading the same files restores the live state
    store2 = FilesBackend(tmp_path / "store")
    eng2 = Engine(cfg, store2, NullTracer(), vocab=VOCAB)
    assert len(eng2.ledger.entries) == len(eng.ledger.entries)
    wm, ltm = eng2.snapshots.restore(eng.version)
    assert state_hash(wm, ltm) == eng.state_hash
    assert (tmp_path / "store" / "ledger.jsonl").exists()
    assert list((tmp_path / "store" / "snapshots").glob("v*.json.gz"))


def test_files_backend_commits_are_durable_without_a_flush(tmp_path):
    """The next CLI process (`axelrod update` after `axelrod init`) must see every committed version,
    even if the process that wrote them never flushed or closed its storage."""
    cfg = make_config(storage={"backend": "files", "path": str(tmp_path / "store")})
    store = FilesBackend(tmp_path / "store")
    eng = Engine(cfg, store, NullTracer(), vocab=VOCAB)
    init = Initializer(eng)
    init.construct(ConstructionSpec.load("world_model/examples/worlds/economy"), "world_model/taxonomy", start=START_DATE, vocab=VOCAB)
    init.load_seeds(SeedFile.load(SEEDS), now=eng.wm.clock)
    eng.save_snapshot()
    _mixed_changes(eng, START)
    reader = FilesBackend(tmp_path / "store")      # no flush, no close on the writer
    assert reader.versions()[-1].version == eng.version
    assert reader.last_seq() == eng.ledger.next_seq - 1
    store.close()


def test_a_session_based_on_a_snapshot_cannot_restore_earlier_versions():
    from axelrod_wm.repo.snapshots import MemoryBackend, dump_state

    eng = constructed_engine()
    _mixed_changes(eng, START)
    sv = eng.version_info()
    store = MemoryBackend()
    store.append_version(sv)
    store.save_snapshot(sv, dump_state(eng.wm, eng.ltm))
    eng2 = Engine(eng.config, store, NullTracer(), vocab=VOCAB)
    eng2.ledger.set_base(eng.ledger.next_seq - 1)
    with pytest.raises(RestoreError):
        eng2.snapshots.restore(sv.version - 1)


def test_frontier_seeds_load():
    eng = constructed_engine()
    Initializer(eng).load_frontier_seeds(SeedFile.load(SEEDS), now=eng.wm.clock)
    entries = list(eng.ltm.correlation_frontier.entries.values())
    assert len(entries) == 6                 # the plan's seed plus five more of different kinds (addition)
    co = entries[0]
    assert (co.earlier_id, co.later_id, co.lag_days, co.sign, co.support, co.seeded) == (
        CPI, "confidence.consumer_confidence", 7, -1, 1.0, True)
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
