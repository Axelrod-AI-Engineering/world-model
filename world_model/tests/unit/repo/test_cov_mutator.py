"""The mutator's less common paths: guards, singletons through update, list fields of records that are not
field-hashed, and replay of changes that do not fit their collection."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import BaseModel

from axelrod_wm.engine.engine import Engine
from axelrod_wm.memory.long_term import Episode
from axelrod_wm.memory.working import DeviationPoint, point_key
from axelrod_wm.repo.mutator import Change, apply_change, apply_changeset, item_adapter, memory_of
from axelrod_wm.repo.snapshots import MemoryBackend, empty_state, state_hash
from axelrod_wm.trace import NullTracer
from tests.conftest import VOCAB, make_config

AT = datetime(2024, 1, 1, tzinfo=UTC)


def _engine() -> Engine:
    return Engine(make_config(), MemoryBackend(), NullTracer(), vocab=VOCAB)


def _episode(eid: str = "EP-1") -> Episode:
    return Episode(id=eid, day=date(2024, 1, 1), trigger_event_ids=[], routine=True, signature=set(),
                   key_signature=set(), deltas={}, edge_effects={}, active_interaction_ids=[], active_pattern_ids=[])


def test_memory_of_ignores_collections_outside_both_memories():
    assert memory_of([Change(action="put", collection="elsewhere.x", id="k")]) == ""
    assert memory_of([Change(action="put", collection="elsewhere.x", id="k"),
                      Change(action="put", collection="ltm.correlation_frontier.blocked_until", id="k")]) == "long_term"
    assert memory_of([Change(action="put", collection="wm.late_queue", id="k"),
                      Change(action="put", collection="ltm.entity_memories", id="k"),
                      Change(action="put", collection="wm.forecast_layer.order", id="_")]) == "both"


def test_item_adapter_of_an_unparametrized_field_accepts_anything():
    class Bare(BaseModel):
        xs: list = []

    ad = item_adapter(Bare, "xs")
    assert ad.validate_python({"a": 1}) == {"a": 1}
    assert item_adapter(Bare, "xs") is ad          # cached


def test_touched_entities_and_get():
    eng = _engine()
    with eng.mutator.begin("t", at=AT) as txn:
        txn.touch_entities(["fed", "", "ecb"])
        assert txn.touched_entities() == {"fed", "ecb"}
        txn.add("wm.deviations.points", DeviationPoint(z=1.0, var=0.1, level=0.5), key=point_key("fed.rate", 0))
        assert txn.get("wm.deviations.points", point_key("fed.rate", 0)).z == 1.0
        assert txn.get("wm.deviations.points", point_key("fed.rate", 1)) is None


def test_adding_an_existing_record_raises_and_rolls_back():
    eng = _engine()
    key = point_key("fed.rate", 0)
    with pytest.raises(KeyError, match="already exists"):
        with eng.mutator.begin("t", at=AT) as txn:
            txn.add("wm.deviations.points", DeviationPoint(z=1.0, var=0.1, level=0.5), key=key)
            txn.add("wm.deviations.points", DeviationPoint(z=2.0, var=0.1, level=0.5), key=key)
    assert key not in eng.wm.deviations.points
    assert eng.version == 0 and eng.mutator.active is None


def test_update_on_a_singleton_sets_its_value_and_rejects_other_fields():
    eng = _engine()
    with eng.mutator.begin("t", at=AT) as txn:
        txn.update("wm.clock", "_", value=AT)
        with pytest.raises(TypeError, match="takes update"):
            txn.update("wm.clock", "_", when=AT)
    assert eng.wm.clock == AT
    cs = eng.mutator.last_changeset
    assert [(c.action, c.collection, c.id) for c in cs.changes] == [("update", "wm.clock", "_")]


def test_removing_a_missing_record_records_nothing():
    eng = _engine()
    with eng.mutator.begin("t", at=AT) as txn:
        txn.remove("wm.deviations.points", "nope|0")
        assert txn.changes == []
    assert eng.mutator.last_changeset is None and eng.version == 0


def test_append_to_a_record_needs_a_field():
    eng = _engine()
    with pytest.raises(TypeError, match="needs a field"):
        with eng.mutator.begin("t", at=AT) as txn:
            txn.add("ltm.prior_states.episodes", _episode())
            txn.append("ltm.prior_states.episodes", "x", key="EP-1")
    assert eng.ltm.prior_states.episodes == {}


def test_list_field_of_a_plain_record_appends_truncates_and_replays():
    eng = _engine()
    with eng.mutator.begin("t", at=AT) as txn:
        txn.add("ltm.prior_states.episodes", _episode())
        txn.append_to("ltm.prior_states.episodes", "EP-1", "tags", "a", "b", "c", keep_last=2)
        # episodes are hashed whole, so the dirty marks name no field
        assert ("ltm.prior_states.episodes", "EP-1", None) in txn.dirty
        assert not any(d[0] == "ltm.prior_states.episodes" and d[2] for d in txn.dirty)
    assert eng.ltm.prior_states.episodes["EP-1"].tags == ["b", "c"]
    cs = eng.mutator.last_changeset
    assert [c.after for c in cs.changes if c.action == "append"] == [{"value": "a"}, {"value": "b"}, {"value": "c"}]
    # replay: the scalar items come back from their {"value": ...} wrapping
    wm, ltm = empty_state()
    apply_changeset(wm, ltm, cs)
    assert ltm.prior_states.episodes["EP-1"].tags == ["b", "c"]
    assert state_hash(wm, ltm) == state_hash(eng.wm, eng.ltm)


def test_replayed_truncate_that_keeps_everything_changes_nothing():
    wm, ltm = empty_state()
    ltm.prior_states.episodes["EP-1"] = _episode()
    ltm.prior_states.episodes["EP-1"].tags = ["a"]
    apply_change(wm, ltm, Change(action="truncate", collection="ltm.prior_states.episodes", id="EP-1", field="tags",
                                 after={"keep_last": 3}))
    assert ltm.prior_states.episodes["EP-1"].tags == ["a"]


@pytest.mark.parametrize(("change", "error", "match"), [
    (Change(action="put", collection="ltm.prior_states.episodes", id="EP-1", after={"value": 1}),
     ValueError, "not valid on records"),
    (Change(action="append", collection="wm.late_queue", id="P-1", after={"value": 1}),
     ValueError, "not valid on keyed values"),
    (Change(action="put", collection="wm.pending_episode_tags", id="_", after={"value": "x"}),
     ValueError, "not valid on lists"),
    (Change(action="put", collection="wm.nowhere", id="_", after={"value": 1}), KeyError, "unknown collection"),
])
def test_replay_rejects_changes_that_do_not_fit_their_collection(change, error, match):
    wm, ltm = empty_state()
    ltm.prior_states.episodes["EP-1"] = _episode()
    with pytest.raises(error, match=match):
        apply_change(wm, ltm, change)
