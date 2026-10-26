"""An import run pauses for review only under review_all (repo/review.py `pauses_run`). Under any other policy it goes to
the end: what the policy approves applies, what needs a person stays pending (`Proposal.queued`, a `queued` ledger
entry), and the next import can start. A pending proposal is decided later on the model as it is then: approved, it
applies as a new version (and is refused, staying pending, when what it names is gone); rejected, it closes. Decisions
and the queue survive a restart, and the same bundles in the same order give the same hashes."""

from __future__ import annotations

import pytest

from axelrod_wm.control.controller import ControllerError, stale_reason
from axelrod_wm.control.updates import UpdateState
from axelrod_wm.events.graph_update import ConcreteTarget, ObserveValue, RetireEntity, ReweightInteraction
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend
from tests.unit.sim.test_import_persistence import bare, bundle, good, kept, runner

HISTORY = [bundle(good("A", "2026-08-04T09:00:00Z", 0.5), bare("B", "2026-08-05T09:00:00Z", 0.75),
                  good("C", "2026-08-06T09:00:00Z", 1.0), title="one"),
           bundle(bare("D", "2026-08-07T09:00:00Z", 1.25), good("E", "2026-08-08T09:00:00Z", 1.5), title="two"),
           bundle(good("F", "2026-08-09T09:00:00Z", 1.75), title="three")]


def run_history(r) -> list[dict]:
    return [r.import_items(b) for b in HISTORY]


def test_a_run_under_standards_completes_and_leaves_what_needs_a_person_pending():
    r = runner(MemoryBackend())
    outs = run_history(r)
    ctl = r.controller
    assert [o["state"] for o in outs] == ["done"] * 3 and all(o["waiting_on"] is None for o in outs)
    assert ctl.active_update is None
    pending = ctl.pending_proposals()
    assert [p.market_event_id for p in pending] == ["IM-B", "IM-D"] and all(p.queued for p in pending)
    assert all(p.review_reasons for p in pending) and all(p.update_id and p.due_day is not None for p in pending)
    assert [str(p.status) for p in ctl.proposals.values()].count("auto_applied") == 4
    assert ctl.updates[outs[0]["update_id"]].report.pending == 1
    assert r.status().state == "awaiting_review" and r.status().update_id is None
    assert "0 wait for your decision; the rest applied." in r.caption               # the last run left none of its own
    queued = [e.payload for e in ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION) if e.payload["action"] == "queued"]
    assert [q["proposal_id"] for q in queued] == [p.id for p in pending]


def test_under_review_queue_every_change_waits_and_no_run_stops():
    r = runner(MemoryBackend())
    r.controller.set_review_policy("review_queue", by="eve")
    outs = run_history(r)
    ctl = r.controller
    assert [o["state"] for o in outs] == ["done"] * 3 and ctl.active_update is None     # each import went to the end
    pending = ctl.pending_proposals()
    assert [p.market_event_id for p in pending] == ["IM-A", "IM-B", "IM-C", "IM-D", "IM-E", "IM-F"]
    assert all(p.queued and p.review_reasons == ["every change is reviewed"] for p in pending)
    assert "auto_applied" not in [str(p.status) for p in ctl.proposals.values()]


def test_a_decision_later_is_a_new_version_on_the_model_as_it_is_and_a_rejection_just_closes():
    r = runner(MemoryBackend())
    run_history(r)
    ctl = r.controller
    b, d = ctl.pending_proposals()
    version, state = ctl.engine.version, ctl.engine.state_hash
    ctl.approve(b.id, "eve", "checked")
    assert ctl.engine.version > version and ctl.engine.state_hash != state
    assert str(b.status) == "approved" and b.folded_day is not None and b.version_after == ctl.engine.version
    assert b.id not in ctl.engine.wm.late_queue
    version = ctl.engine.version
    ctl.reject(d.id, "eve", "not for the model")
    assert str(d.status) == "rejected" and ctl.engine.version == version and not ctl.pending_proposals()
    with pytest.raises(ControllerError, match="already"):
        ctl.approve(b.id, "eve")
    assert r.status().state == "idle"
    r.import_items(bundle(good("G", "2026-08-10T09:00:00Z", 2.0), title="four"))        # nothing is in its way


def test_the_same_bundles_in_the_same_order_give_the_same_hashes_and_a_restart_changes_nothing(tmp_path):
    def decided(r):
        b, d = r.controller.pending_proposals()
        r.controller.approve(b.id, "eve")
        r.controller.reject(d.id, "eve", "no")
        return r.controller.engine.version, r.controller.engine.state_hash

    one, two = runner(MemoryBackend()), runner(MemoryBackend())
    run_history(one)
    run_history(two)
    assert kept(one) == kept(two)                                   # before any decision: identical
    want = decided(one)
    assert decided(two) == want                                     # and after the same decisions

    first = runner(FilesBackend(path=tmp_path / "s"))
    run_history(first)
    before = kept(first)
    first.controller.engine.storage.close()
    again = runner(FilesBackend(path=tmp_path / "s"))
    assert kept(again) == before and again.status().state == "awaiting_review"
    pend = again.controller.pending_proposals()
    assert [p.market_event_id for p in pend] == ["IM-B", "IM-D"] and all(p.queued and p.due_day for p in pend)
    assert decided(again) == want                                   # decided after the restart: the same model
    again.controller.engine.storage.close()
    final = runner(FilesBackend(path=tmp_path / "s"))               # and the decisions stay decided
    assert not final.controller.pending_proposals()
    assert [str(p.status) for p in final.controller.proposals.values()].count("rejected") == 1
    assert (final.controller.engine.version, final.controller.engine.state_hash) == want


def test_under_review_all_a_run_still_pauses_and_blocks_the_next_import():
    r = runner(MemoryBackend())
    r.controller.set_review_policy("review_all", by="eve")
    out = r.import_items(HISTORY[0])
    assert out["state"] == "awaiting_review" and out["waiting_on"] and r.controller.active_update
    assert not any(p.queued for p in r.controller.proposals.values())
    with pytest.raises(ControllerError, match="still running"):
        r.import_items(HISTORY[1])
    assert "Each waits for your review" in r.caption


@pytest.mark.parametrize("policy", ["default", "auto_approve_all"])
def test_the_other_policies_never_pause_a_run_either(policy):
    r = runner(MemoryBackend())
    r.controller.set_review_policy(policy, by="eve")
    out = r.import_items(HISTORY[0])
    assert out["state"] == "done" and r.controller.active_update is None
    r.import_items(HISTORY[1])
    assert r.controller.updates[out["update_id"]].state == UpdateState.DONE


def test_a_proposal_whose_targets_are_gone_is_refused_and_stays_pending():
    r = runner(MemoryBackend())
    r.import_items(bundle({"id": "S", "published_at": "2026-08-10T00:00:00Z", "source": "agent",
                           "headline": "A stronger dollar trims Acme Motors",
                           "signals": [{"type": "support", "source": "dollar.index", "target": "acme_motors.operating_profit",
                                        "strength": 0.6, "quote": "A stronger dollar trims Acme Motors"}]}))
    ctl = r.controller
    (p,) = ctl.pending_proposals()
    op = p.event.ops[0]
    assert isinstance(op, ReweightInteraction)
    retire = ctl.propose_retire(interaction_id=op.interaction_id, reason="no longer true")
    ctl.approve(retire.id, "eve")
    version = ctl.engine.version
    with pytest.raises(ControllerError, match=rf"{p.id} no longer applies to the model: interaction .* no longer active"):
        ctl.approve(p.id, "eve")
    assert ctl.engine.version == version and str(p.status) == "pending" and p in ctl.pending_proposals()
    ctl.reject(p.id, "eve", "stale")
    assert not ctl.pending_proposals()


def test_what_makes_an_operation_stale():
    r = runner(MemoryBackend())
    r.import_items(HISTORY[0])
    ctl = r.controller
    graph = ctl.engine.wm.graph
    ev = ctl.pending_proposals()[0].event
    observe = ev.ops[0]
    assert isinstance(observe, ObserveValue) and stale_reason(ev, graph) is None
    gone = ObserveValue(target=ConcreteTarget(subentity_id="nobody.nothing"), value=1.0, observed_at=observe.observed_at)
    assert stale_reason(ev.model_copy(update={"ops": [gone]}), graph) == "nobody.nothing is no longer in the model"
    fresh = ObserveValue(target=ConcreteTarget(subentity_id="new:central_bank.x"), value=1.0, observed_at=observe.observed_at)
    assert stale_reason(ev.model_copy(update={"ops": [fresh]}), graph) is None          # a new thing is not looked up
    unknown = ReweightInteraction(interaction_id="I-nope", supports=True)
    assert stale_reason(ev.model_copy(update={"ops": [unknown]}), graph) == "interaction I-nope is no longer active"
    retire = RetireEntity(entity_id="nobody", reason="x")
    assert stale_reason(ev.model_copy(update={"ops": [retire]}), graph) == "entity nobody is no longer in the model"


# -- a run stored as paused, under a policy that no longer pauses runs ---------------------------------------------------

def legacy(path):
    """A run paused for review at IM-B, stored under a policy that does not pause (as one stored before the rule)."""
    r = runner(FilesBackend(path=path))
    r.controller.set_review_policy("review_all", by="eve")
    out = r.import_items(HISTORY[0])
    assert out["state"] == "awaiting_review"
    ctl = r.controller
    ctl.engine.ledger.append(LedgerKind.REVIEW_POLICY, {"policy": "standards", "by": "legacy"}, recorded_at=ctl.now)
    ctl.engine.storage.close()
    return out


def test_a_paused_run_stored_under_a_policy_that_does_not_pause_is_released_on_resume(tmp_path):
    out = legacy(tmp_path / "s")
    r = runner(FilesBackend(path=tmp_path / "s"))
    ctl = r.controller
    assert ctl.active_update is None and ctl.updates[out["update_id"]].state == UpdateState.DONE
    first, b = ctl.pending_proposals()                              # the awaited one, then IM-B under the policy now in force
    assert first.id == out["waiting_on"] and first.market_event_id == "IM-A" and first.queued and first.review_reasons
    assert b.market_event_id == "IM-B" and b.queued and str(b.status) == "pending"
    assert "IM-C" in r.imported                                      # the rest of the run was processed
    states = [e.payload["state"] for e in ctl.engine.ledger.of_kind(LedgerKind.UPDATE)
              if e.payload.get("update_id") == out["update_id"]]
    assert "released" in states and states[-1] == "done"
    assert any(e.payload["action"] == "queued" and e.payload["proposal_id"] == first.id
               for e in ctl.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION))
    r.import_items(HISTORY[1])                                      # nothing is in its way


def test_a_released_proposal_is_decided_later_as_a_new_version_and_a_restart_changes_nothing(tmp_path):
    legacy(tmp_path / "s")
    r = runner(FilesBackend(path=tmp_path / "s"))
    ctl = r.controller
    first, b = ctl.pending_proposals()
    ctl.engine.storage.close()
    again = runner(FilesBackend(path=tmp_path / "s"))               # a second restart: the same state
    assert again.controller.engine.state_hash == ctl.engine.state_hash and again.controller.active_update is None
    assert [p.id for p in again.controller.pending_proposals()] == [first.id, b.id]
    ctl = again.controller
    version = ctl.engine.version
    ctl.approve(first.id, "eve", "checked")                         # applied as a new version
    assert ctl.engine.version > version and [p.id for p in ctl.pending_proposals()] == [b.id]
    ctl.reject(b.id, "eve", "no")
    want = (ctl.engine.version, ctl.engine.state_hash)
    ctl.engine.storage.close()
    final = runner(FilesBackend(path=tmp_path / "s"))
    assert (final.controller.engine.version, final.controller.engine.state_hash) == want
    assert not final.controller.pending_proposals()


def test_a_paused_run_under_review_all_stays_paused_on_resume(tmp_path):
    r = runner(FilesBackend(path=tmp_path / "s"))
    r.controller.set_review_policy("review_all", by="eve")
    out = r.import_items(HISTORY[0])
    r.controller.engine.storage.close()
    again = runner(FilesBackend(path=tmp_path / "s"))
    ctl = again.controller
    assert ctl.active_update == out["update_id"] and ctl.updates[ctl.active_update].state == UpdateState.AWAITING_REVIEW
    assert not any(p.queued for p in ctl.proposals.values())
    assert ctl.release_paused() is None                             # the policy pauses runs: nothing to release


def test_switching_the_policy_releases_a_paused_run():
    r = runner(MemoryBackend())
    ctl = r.controller
    ctl.set_review_policy("review_all", by="eve")
    out = r.import_items(HISTORY[0])
    assert ctl.release_paused() is None and ctl.active_update == out["update_id"]
    ctl.set_review_policy("standards", by="eve")
    assert ctl.active_update is None and ctl.updates[out["update_id"]].state == UpdateState.DONE
    assert [p.queued for p in ctl.pending_proposals()] == [True, True]
    r.import_items(HISTORY[1])
    assert ctl.release_paused() is None                             # no run waits


def test_switching_the_policy_without_driving_leaves_the_released_run_running_for_the_caller():
    r = runner(MemoryBackend())
    ctl = r.controller
    ctl.set_review_policy("review_all", by="eve")
    out = r.import_items(HISTORY[0])
    ctl.auto_resume = False
    ctl.set_review_policy("standards", by="eve")
    run = ctl.updates[out["update_id"]]
    assert run.state == UpdateState.RUNNING and run.request.on_review == "queue"
    ctl.cycle.run_days(run)
    assert run.state == UpdateState.DONE and ctl.pending_proposals()[0].queued
    assert ctl.cycle.release(run) is run                            # a run that is not paused is left alone


def test_a_released_run_that_fails_is_marked_failed_and_frees_the_model(monkeypatch):
    r = runner(MemoryBackend())
    ctl = r.controller
    ctl.set_review_policy("review_all", by="eve")
    out = r.import_items(HISTORY[0])
    monkeypatch.setattr(ctl.engine.learning, "close_day", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    with pytest.raises(RuntimeError, match="disk"):
        ctl.set_review_policy("standards", by="eve")
    assert ctl.updates[out["update_id"]].state == UpdateState.FAILED and ctl.active_update is None
