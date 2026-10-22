"""The history read as version control: empty ranges, forecast-only commits, filters, missing versions, and
names of removed records."""

from __future__ import annotations

from datetime import UTC, date, datetime

from axelrod_wm.engine.engine import Engine
from axelrod_wm.memory.long_term import Episode
from axelrod_wm.memory.working import DeviationPoint, point_key
from axelrod_wm.repo import history
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.trace import NullTracer
from tests.conftest import VOCAB, constructed_engine, make_config

AT = datetime(2024, 1, 1, tzinfo=UTC)


def _episode(eid: str) -> Episode:
    return Episode(id=eid, day=date(2024, 1, 1), trigger_event_ids=[], routine=True, signature=set(),
                   key_signature=set(), deltas={}, edge_effects={}, active_interaction_ids=[], active_pattern_ids=[])


def test_an_empty_or_reversed_range_has_no_commits():
    eng = constructed_engine()
    d = history.diff(eng, eng.version, eng.version - 1)
    assert d["commits"] == 0 and d["changes"] == [] and d["by_process"] == {}


def test_forecast_only_commits_are_not_versions():
    eng = constructed_engine()
    v0 = eng.version
    with eng.mutator.begin("pose:T-1", at=AT) as txn:
        txn.set("wm.forecast_layer.pose_counts", {"T-1": 1})
    assert eng.version == v0                           # forecast layer only: no new version
    with eng.mutator.begin("record:2024-01-01", at=AT) as txn:
        txn.add("wm.deviations.points", DeviationPoint(z=0.1, var=0.1, level=0.0), key=point_key("inflation.headline_cpi", 0))
    d = history.diff(eng, v0)
    assert d["commits"] == 1 and d["by_process"] == {"day.record": 1} and d["by_memory"] == {"working": 1}
    assert [c.version for c in history.log(eng, limit=10)] == [v0 + 1, v0, v0 - 1]


def test_log_filters_by_memory():
    eng = constructed_engine()
    with eng.mutator.begin("record:a", at=AT) as txn:
        txn.add("wm.deviations.points", DeviationPoint(z=0.1, var=0.1, level=0.0), key=point_key("inflation.headline_cpi", 0))
    with eng.mutator.begin("distill:a", at=AT) as txn:
        txn.add("ltm.prior_states.episodes", _episode("EP-1"))
    lt = history.log(eng, memory="long_term")
    assert [c.version for c in lt] == [eng.version]
    assert lt[0].memory == "long_term" and lt[0].process == "day.distill"
    assert lt[0].counts == {"episodes": {"added": 1}} and lt[0].touched == {}
    assert [c.version for c in history.log(eng, memory="working")] == [eng.version - 1]


def test_log_stops_where_the_ledger_starts_after_a_cached_history():
    eng = Engine(make_config(), MemoryBackend(), NullTracer(), vocab=VOCAB)
    eng.version = 5                                    # versions 1..5 live in a history this ledger does not hold
    assert history.log(eng) == []


def test_show_an_unknown_version_is_none():
    eng = constructed_engine()
    assert history.show(eng, eng.version + 10) is None


def test_a_removed_interaction_is_named_from_what_the_log_kept():
    eng = constructed_engine()
    inter = eng.wm.graph.interactions["e01"]
    with eng.mutator.begin("retire-e01", at=AT, process="structural", message="drop e01") as txn:
        txn.remove("wm.graph.interactions", "e01")
    shown = history.show(eng, eng.version)
    assert shown["commit"]["message"] == "drop e01" and shown["commit"]["process"] == "structural"
    [row] = shown["changes"]
    assert row["kind"] == "interactions" and row["action"] == "removed" and "was" not in row
    assert row["name"] == f"{inter.source_id} → {inter.target_id} ({inter.label})"
