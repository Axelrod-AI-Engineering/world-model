"""A better read of a document lets a pending change pass (sim/imports.py `_regate`, control/controller.py `regate`): items
imported again under ids already in the model refresh the attribution behind a change still waiting for a person, and
the review policy assesses it again. It applies as a fresh passing change does; a change a person already decided, or one
whose signals differ, is left alone. The re-read is logged, so a restart and a replay reach the same model."""

from __future__ import annotations

import pytest

from axelrod_wm.control.controller import ControllerError
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend
from tests.unit.sim.test_import_persistence import (
    bare,
    bundle,
    decisions_by,
    good,
    kept,
    runner,
    world,
)

A = "2026-08-04T09:00:00Z"
B = "2026-08-05T09:00:00Z"
C = "2026-08-06T09:00:00Z"


def waiting(r):
    return {p.market_event_id: p for p in r.controller.pending_proposals()}


def test_a_pending_change_passes_on_a_better_read_and_is_applied_by_the_policy():
    r = runner(MemoryBackend())
    r.import_items(bundle(bare("A", A, 0.5)))
    (p,) = r.controller.pending_proposals()
    assert p.queued and p.review_reasons
    version = r.controller.engine.version
    out = r.import_items(bundle(good("A", A, 0.5)))
    assert out["regated"] == [p.id] and out["imported"] == [] and out["update_id"] is None
    assert not r.controller.pending_proposals()
    done = r.controller.proposals[p.id]
    assert done.status == "auto_applied" and done.decided_by == "policy:standards" and done.review_reasons == []
    assert decisions_by(r) == ["policy:standards"] and r.controller.engine.version > version
    assert r.imported["IM-A"].document == "Statement A" and r.controller.market_status["IM-A"] == "applied"
    assert "assessed again" in r.caption
    with pytest.raises(ControllerError, match="nothing new"):
        r.import_items(bundle(good("A", A, 0.5)))             # a third read finds nothing pending: nothing to do


def test_a_change_that_still_fails_keeps_waiting_with_its_reasons_updated():
    r = runner(MemoryBackend())
    r.import_items(bundle(bare("A", A, 0.5)))
    (p,) = r.controller.pending_proposals()
    before = list(p.review_reasons)
    assert any("source document" in x for x in before) and any("coverage" in x for x in before)
    r.import_items(bundle(good("A", A, 0.5, coverage=None, plausible=False)))      # names its document, still not enough
    assert p.status == "pending" and p.review_reasons != before
    assert not any("source document" in x for x in p.review_reasons)
    assert any("coverage" in x for x in p.review_reasons) and any("plausibility" in x for x in p.review_reasons)
    assert r.imported["IM-A"].document == "Statement A"        # the refreshed read is kept for the next one


def test_decided_changes_and_changed_signals_are_left_alone():
    r = runner(MemoryBackend())
    r.import_items(bundle(bare("A", A, 0.5), bare("B", B, 0.75), bare("C", C, 1.0)))
    ctl = r.controller
    p = waiting(r)
    ctl.reject(p["IM-A"].id, "eve", "no")
    ctl.approve(p["IM-B"].id, "eve")
    with pytest.raises(ControllerError, match="nothing new"):
        r.import_items(bundle(good("A", A, 0.5), good("B", B, 0.75)))
    assert r.imported["IM-A"].document == "" and ctl.proposals[p["IM-A"].id].status == "rejected"
    assert ctl.proposals[p["IM-B"].id].decided_by == "eve"
    before = kept(r)
    with pytest.raises(ControllerError, match="nothing new"):
        r.import_items(bundle(good("C", C, 1.5)))          # another rate: the change would differ
    assert kept(r) == before and r.imported["IM-C"].document == "" and p["IM-C"].status == "pending"


def test_ids_not_asked_for_and_reads_that_change_nothing_are_not_assessed():
    r = runner(MemoryBackend())
    r.import_items(bundle(bare("A", A, 0.5), bare("B", B, 0.75)))
    with pytest.raises(ControllerError, match="nothing new"):
        r.import_items(bundle(bare("A", A, 0.5)))          # the same read: nothing to refresh
    out = r.import_items(bundle(good("A", A, 0.5), good("B", B, 0.75)), ["B"])
    assert len(out["regated"]) == 1 and [p.market_event_id for p in r.controller.pending_proposals()] == ["IM-A"]


def test_a_new_item_and_a_re_read_come_in_one_import():
    r = runner(MemoryBackend())
    r.import_items(bundle(bare("A", A, 0.5)))
    out = r.import_items(bundle(good("A", A, 0.5), good("N", B, 0.75)))
    assert len(out["regated"]) == 1 and out["imported"] == ["N"] and out["update_id"]
    assert not r.controller.pending_proposals()


def test_a_change_that_no_longer_applies_stays_pending_and_says_so():
    r = runner(MemoryBackend())
    r.import_items(bundle(bare("A", A, 0.5)))
    (p,) = r.controller.pending_proposals()
    del r.controller.engine.wm.graph.subentities["central_bank.policy_rate"]
    r.import_items(bundle(good("A", A, 0.5)))
    assert p.status == "pending" and p.needs_review and "no longer applies to the model" in p.review_reasons[-1]


def test_a_restart_comes_back_to_the_same_model(tmp_path):
    first = runner(FilesBackend(path=tmp_path / "s"))
    first.import_items(bundle(bare("A", A, 0.5), bare("B", B, 0.75)))
    first.import_items(bundle(good("A", A, 0.5), good("B", B, 0.75, plausible=False)))
    before = kept(first)
    assert len(before["queue"]) == 1 and any("plausib" in x for x in before["reasons"][0])
    assert sum(e.payload.get("state") == "import_regate"
               for e in first.controller.engine.ledger.of_kind(LedgerKind.UPDATE)) == 1
    first.controller.engine.storage.close()
    again = runner(FilesBackend(path=tmp_path / "s"))
    assert kept(again) == before
    assert again.imported["IM-A"].document == "Statement A"
    (a,) = [p for p in again.controller.proposals.values() if p.market_event_id == "IM-A"]
    assert a.status == "auto_applied" and a.decided_by == "policy:standards"
    again.controller.engine.storage.close()


def test_a_replay_on_a_changed_base_reproduces_the_re_read(tmp_path):
    w = world(tmp_path)
    first = runner(FilesBackend(path=tmp_path / "s"), w)
    first.import_items(bundle(bare("A", A, 0.5), bare("B", B, 0.75), title="first read"))
    first.import_items(bundle(good("A", A, 0.5), good("B", B, 0.75, plausible=False), title="better read"))
    before = kept(first)
    first.controller.engine.storage.close()
    (w / "entities.yaml").write_text((w / "entities.yaml").read_text() + "# a comment\n")
    again = runner(FilesBackend(path=tmp_path / "s"), w)
    assert "replayed" in again.caption
    after = kept(again)
    keys = ("version", "hash", "queue", "reasons", "imported")
    assert {k: after[k] for k in keys} == {k: before[k] for k in keys}
    assert decisions_by(again) == ["policy:standards"]
    again.controller.engine.storage.close()
