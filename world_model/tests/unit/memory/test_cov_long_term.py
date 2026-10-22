"""Long-term memory: prior-state indexes and the super-interaction builder's edge cases."""

from __future__ import annotations

from datetime import UTC, date, datetime

from axelrod_wm.memory.long_term import Episode, PriorStates, SuperInteractionBuilder, _descendants
from axelrod_wm.model.explanation import Explanation
from axelrod_wm.model.superentity import SuperentityInstance, SuperLinkKind
from tests.conftest import constructed_engine

AT = datetime(2024, 1, 1, tzinfo=UTC)


def _episode(eid: str, signature: set[str], tags: list[str]) -> Episode:
    return Episode(id=eid, day=date(2024, 1, 1), trigger_event_ids=[], routine=False, tags=tags,
                   signature=signature, key_signature=signature, deltas={}, edge_effects={},
                   active_interaction_ids=[], active_pattern_ids=[])


def _explanation(xid: str, keys: set[str]) -> Explanation:
    return Explanation(id=xid, subject_kind="learning", subject_id="E", state_version=1, created_at=AT,
                       key_interactions=[], top_paths=[], analogs=[], networks=[], scenarios=[], assumptions=[],
                       notes=[], text="", index_keys=keys)


def test_prior_state_indexes():
    ps = PriorStates(
        episodes={"EP-2": _episode("EP-2", {"g1", "g2"}, ["energy-shock-like"]),
                  "EP-1": _episode("EP-1", {"g1"}, []),
                  "EP-3": _episode("EP-3", {"g3"}, ["energy-shock-like"])},
        explanations={"EX-1": _explanation("EX-1", {"k1", "k2"}), "EX-2": _explanation("EX-2", {"k2"})})
    assert ps.by_generalization("g1") == ["EP-1", "EP-2"]
    assert ps.by_generalization("none") == []
    assert ps.by_tag("energy-shock-like") == ["EP-2", "EP-3"]
    assert ps.by_index_key("k2") == ["EX-1", "EX-2"]
    assert ps.by_index_key("k1") == ["EX-1"]
    assert ps.index_keys_of(["EX-2", "EX-missing", "EX-1"]) == {"k1", "k2"}
    assert ps.index_keys_of([]) == set()


def test_descendants_tolerates_cycles_and_missing_children():
    eng = constructed_engine()
    g = eng.wm.graph.model_copy(deep=True)
    g.instances["A"] = SuperentityInstance(id="A", pattern_id="S1", bindings={}, interaction_ids=[],
                                           child_instance_ids=["B", "ghost"])
    g.instances["B"] = SuperentityInstance(id="B", pattern_id="S1", bindings={}, interaction_ids=[],
                                           child_instance_ids=["A"])
    assert _descendants(g, "A") == {"A", "B"}
    assert _descendants(g, "nope") == set()


def test_compute_skips_channels_whose_values_are_gone():
    eng = constructed_engine()
    g = eng.wm.graph.model_copy(deep=True)
    objects = eng.ltm.object_generalizations
    base = SuperInteractionBuilder().compute(g, objects)
    # every interaction now points at a value that no longer exists: no causal super-interactions remain
    for iid, inter in list(g.interactions.items()):
        g.interactions[iid] = inter.model_copy(update={"source_id": "ghost.value"})
    out = SuperInteractionBuilder().compute(g, objects)
    assert any(s["kind"] == SuperLinkKind.CAUSAL for s in base)
    assert not any(s["kind"] == SuperLinkKind.CAUSAL for s in out)
    assert ([s for s in out if s["kind"] == SuperLinkKind.SHARES_MEMBERS]
            == [s for s in base if s["kind"] == SuperLinkKind.SHARES_MEMBERS])
