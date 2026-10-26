"""The default review policy without an engine config, and the reasons it gives."""

from __future__ import annotations

from datetime import UTC, datetime

from axelrod_wm.repo.review import (
    AutoApproveAllPolicy,
    DefaultReviewPolicy,
    Proposal,
    ProposalKind,
    ReviewAllPolicy,
    ReviewQueuePolicy,
)
from axelrod_wm.repo.snapshots import empty_state
from tests.conftest import real_event

AT = datetime(2024, 1, 1, tzinfo=UTC)


def _proposal(ops, kind=ProposalKind.GRAPH_UPDATE, **ev) -> Proposal:
    return Proposal(id="P-1", kind=kind, event=real_event(ops, **ev), created_at=AT)


def test_without_config_the_built_in_translators_count_as_text():
    pol = DefaultReviewPolicy()
    assert pol.text_translators == {"llm", "hand_drawn", "template"}
    assert pol.min_conf == 0.8 and pol.auto_human is True
    req = pol.assess(_proposal([], produced_by="template"), empty_state()[0])
    assert req.needs_review and req.reasons == ["translated from text"]


def test_a_structural_proposal_from_a_person_still_needs_review():
    req = DefaultReviewPolicy().assess(_proposal([], kind=ProposalKind.REFINEMENT), empty_state()[0])
    assert req.needs_review and req.reasons == ["model structure"]


def test_a_small_reweighting_of_an_unknown_interaction_needs_no_review():
    wm = empty_state()[0]
    ops = [{"op": "reweight_interaction", "interaction_id": "e-missing", "supports": True, "strength": 0.4},
           {"op": "reweight_interaction", "interaction_id": "e-other", "supports": False, "strength": 0.5}]
    req = DefaultReviewPolicy().assess(_proposal(ops, produced_by="engine"), wm)
    assert not req.needs_review and req.reasons == []
    big = [{"op": "reweight_interaction", "interaction_id": "e-missing", "supports": True, "strength": 0.9}]
    assert DefaultReviewPolicy().assess(_proposal(big, produced_by="engine"), wm).reasons == ["large reweighting"]


def test_the_fixed_policies():
    p = _proposal([])
    wm = empty_state()[0]
    assert AutoApproveAllPolicy().assess(p, wm).needs_review is False
    req = ReviewAllPolicy().assess(p, wm)
    assert req.needs_review and req.reasons == ["every change is reviewed"]
    queue = ReviewQueuePolicy().assess(p, wm)                       # every change waits, and the run does not stop
    assert queue == req and ReviewAllPolicy.pauses_run and not ReviewQueuePolicy.pauses_run
