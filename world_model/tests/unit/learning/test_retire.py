"""Deleting structure (restructure): retiring an interaction, and an entity with everything that touches it.
Like `git rm`, a retirement leaves the current graph and the forecasts, and the ledger keeps the history."""

from __future__ import annotations

import pytest

from axelrod_wm.events.graph_update import EventValidationError, GraphUpdateEvent
from axelrod_wm.repo.ledger import LedgerKind
from tests.conftest import real_event


def test_retiring_an_interaction_takes_it_out_of_the_active_graph(warm_engine):
    eng = warm_engine
    assert eng.wm.graph.interactions["e08"].retired_at is None
    res = eng.learning.run(real_event([{"op": "retire_interaction", "interaction_id": "e08",
                                        "reason": "energy weighs less in the basket"}], "GUE-R1"), eng.wm.clock, 0)
    inter = eng.wm.graph.interactions["e08"]
    assert inter.retired_at is not None and inter.time_states[-1].note.startswith("retired:")
    assert "e08" not in {i.id for i in eng.wm.graph.active_interactions()}
    assert res.shared.parsed.retired_interaction_ids == ["e08"]
    assert "e08" not in eng.ltm.interaction_generalizations.taxonomy.nodes[inter.generalization_id].instance_ids


def test_retiring_an_entity_removes_its_values_and_retires_its_interactions(warm_engine):
    eng = warm_engine
    g = eng.wm.graph
    subs = list(g.entities["united_airlines"].subentity_ids)
    touching = [i.id for i in g.active_interactions() if i.source_id in subs or i.target_id in subs]
    insts = [iid for iid, inst in g.instances.items() if "united_airlines" in inst.bindings.values()]
    assert touching and insts
    res = eng.learning.run(real_event([{"op": "retire_entity", "entity_id": "united_airlines",
                                        "reason": "illustrative: the carrier leaves the model"}], "GUE-R2"), eng.wm.clock, 0)
    assert "united_airlines" not in g.entities and not any(s in g.subentities for s in subs)
    assert all(g.interactions[i].retired_at is not None for i in touching)
    assert not any(i in g.instances for i in insts)
    assert set(res.shared.parsed.retired_subentity_ids) == set(subs)
    tax = eng.ltm.object_generalizations.taxonomy
    assert not any("united_airlines" in n.instance_ids for n in tax.nodes.values())
    # the working-memory commit removed the entity; history keeps it
    wm_commit = res.working.commit
    assert wm_commit.process == "learn.working" and wm_commit.memory == "working"
    assert any(c.action == "remove" and c.collection == "wm.graph.entities" and c.id == "united_airlines"
               for c in wm_commit.changes)
    assert any(e.payload["cause"] == "GUE-R2" for e in eng.ledger.of_kind(LedgerKind.CHANGESET))


def test_a_day_runs_after_an_entity_is_retired(warm_engine):
    from tests.conftest import close_day, predict_day

    eng = warm_engine
    eng.learning.run(real_event([{"op": "retire_entity", "entity_id": "delta", "reason": "illustrative"}],
                                "GUE-R3"), eng.wm.clock, 0)
    d = eng.wm.last_processed_day + 1
    predict_day(eng, d)
    _moves, report = close_day(eng, d)
    assert report.version == eng.version and "delta" not in eng.wm.graph.entities


def test_a_thesis_cannot_retire_structure():
    ev = {"id": "GUE-H", "kind": "hypothetical", "occurred_at": "2026-02-01T00:00:00Z",
          "recorded_at": "2026-02-01T00:00:00Z", "produced_by": "human",
          "ops": [{"op": "retire_interaction", "interaction_id": "e08", "reason": "x"}]}
    from axelrod_wm.events.graph_update import validate_event

    with pytest.raises(EventValidationError):
        validate_event(GraphUpdateEvent.model_validate(ev))


def test_retirement_needs_review(warm_engine):
    from axelrod_wm.repo.review import DefaultReviewPolicy, Proposal, ProposalKind

    p = Proposal(id="PR-X", kind=ProposalKind.GRAPH_UPDATE,
                 event=real_event([{"op": "retire_interaction", "interaction_id": "e08", "reason": "x"}], "GUE-R4",
                                  produced_by="hand_drawn"),
                 created_at=warm_engine.wm.clock)
    req = DefaultReviewPolicy(warm_engine.config).assess(p, warm_engine.wm)
    assert req.needs_review and "deletes structure" in req.reasons
