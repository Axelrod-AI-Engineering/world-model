"""An imported model is kept between sessions (sim/imports.py, sim/import_state.py): a runner built on the storage of
an earlier one resumes it, with the same version and hash, imported items, review policy and pending reviews;
importing the same bundle again changes nothing. A changed construction file rebuilds the base and replays the
recorded imports on it."""

from __future__ import annotations

import json
import shutil
from types import SimpleNamespace as NS

import pytest

from axelrod_wm.clients import load_scenario_yaml
from axelrod_wm.control.controller import ControllerError
from axelrod_wm.control.updates import UpdateState
from axelrod_wm.engine.config import load_config
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend
from axelrod_wm.sim.import_state import changed_files, construction_digest, counters_from, policy_at
from axelrod_wm.sim.imports import ImportRunner
from axelrod_wm.sim.scenario import ScenarioScript
from axelrod_wm.trace import RecordingTracer
from tests.where import ACME_SCENARIO, ACME_WORLD


def good(iid: str, at: str, rate: float, **kw) -> dict:
    """An item that meets every standard: attributed, labelled, plausible, confident, and not structural."""
    return {"id": iid, "published_at": at, "source": "Synthetic central bank", "source_type": "central_bank",
            "document": f"Statement {iid}", "coverage": "full", "plausible": True, "confidence": 0.8,
            "headline": f"The central bank sets its policy rate at {rate}%", "entities": ["central_bank"],
            "signals": [{"type": "observe", "value_of": "central_bank.policy_rate", "value": rate}], **kw}


def bare(iid: str, at: str, rate: float) -> dict:
    """The same item without its attribution: it waits for a person."""
    return {k: v for k, v in good(iid, at, rate).items() if k not in ("document", "coverage", "plausible")}


def bundle(*items: dict, title: str = "Test bundle") -> dict:
    return {"title": title, "collected_by": "a test", "synthetic": True, "items": list(items)}


def world(tmp_path):
    """A copy of the synthetic client's world, so a test can change a construction file."""
    dst = tmp_path / "world"
    shutil.copytree(ACME_WORLD, dst)
    return dst


def runner(storage, world_dir=None, config=None) -> ImportRunner:
    raw = load_scenario_yaml(str(ACME_SCENARIO))
    raw["imports_dir"] = None
    if world_dir is not None:
        raw["initialization"]["construction_dir"] = str(world_dir)
        raw["initialization"]["taxonomy_dir"] = str(world_dir / "taxonomy")
    r = ImportRunner(None, None, ScenarioScript.model_validate(raw), True, storage=storage, config=config,
                     tracer=RecordingTracer(run_id="persist"))
    r.load()
    return r


def kept(r: ImportRunner) -> dict:
    """What a resumed model must hold exactly as it was."""
    ctl = r.controller
    return {"version": ctl.engine.version, "hash": ctl.engine.state_hash, "queue": [p.id for p in ctl.pending_proposals()],
            "reasons": [p.review_reasons for p in ctl.pending_proposals()],
            "policy": ctl.config.review.policy, "imported": sorted(r.imported), "skips": r.import_skips,
            "log": [(e["title"], e["items"], e["update_id"]) for e in r.import_log], "active": ctl.active_update,
            "ids": dict(ctl.ids.counters)}


def decisions_by(r: ImportRunner) -> list[str]:
    return [e.payload["by"] for e in r.controller.engine.ledger.of_kind(LedgerKind.REVIEW_DECISION)
            if e.payload["action"] == "auto_applied"]


def approve_all(r: ImportRunner, by: str = "eve") -> None:
    ctl = r.controller
    while ctl.pending_proposals():
        ctl.approve(ctl.pending_proposals()[0].id, by)


def test_a_resumed_model_is_the_one_that_stopped_and_an_import_repeated_changes_nothing(tmp_path):
    first = runner(FilesBackend(path=tmp_path / "s"))
    b = bundle(good("A", "2026-08-04T09:00:00Z", 0.5), good("B", "2026-08-05T09:00:00Z", 0.75))
    first.import_items(b)
    before = kept(first)
    assert before["policy"] == "standards" and not before["queue"] and before["imported"] == ["IM-A", "IM-B"]
    assert decisions_by(first) == ["policy:standards", "policy:standards"]       # the gate applied both, as itself
    assert first.controller.engine.storage.snapshot_versions()[-1] == before["version"]    # a snapshot after the run
    first.controller.engine.storage.close()

    again = runner(FilesBackend(path=tmp_path / "s"))
    assert kept(again) == before
    assert "Reopened at version" in again.caption and again.status().state == "idle"
    with pytest.raises(ControllerError, match="nothing new to import"):
        again.import_items(b)
    assert kept(again) == before
    assert again.resume().loaded and kept(again) == before                       # resume() is the same as load()


def test_pending_reviews_and_the_review_policy_survive_and_the_run_goes_on(tmp_path):
    def history(r):
        r.import_items(bundle(good("A", "2026-08-04T09:00:00Z", 0.5), bare("B", "2026-08-05T09:00:00Z", 0.75),
                              good("C", "2026-08-06T09:00:00Z", 1.0)))

    control = runner(MemoryBackend())
    history(control)
    first = runner(FilesBackend(path=tmp_path / "s"))
    history(first)
    before = kept(first)
    assert len(before["queue"]) == 1 and first.status().state == "awaiting_review"
    reasons = before["reasons"][0]
    assert any("source document" in r for r in reasons) and any("coverage is not labelled" in r for r in reasons)
    first.controller.set_review_policy("standards", by="eve", record=True)
    first.controller.engine.storage.close()

    again = runner(FilesBackend(path=tmp_path / "s"))
    assert {**kept(again), "ids": None} == {**before, "ids": None} and again.status().state == "awaiting_review"
    assert again.controller.translations["IM-B"].events and again.controller.market_status["IM-B"] == "awaiting review"
    assert again.controller.active_update == before["active"]
    approve_all(again)                      # approving the awaited item resumes the run, which folds C
    approve_all(control)
    assert again.controller.updates[before["active"]].state == UpdateState.DONE
    assert again.status().state == "idle"
    assert (again.controller.engine.version, again.controller.engine.state_hash) == (
        control.controller.engine.version, control.controller.engine.state_hash)


def test_a_policy_change_is_logged_with_who_made_it_and_comes_back(tmp_path):
    first = runner(FilesBackend(path=tmp_path / "s"))
    first.controller.set_review_policy("review_all", by="eve")
    first.controller.set_review_policy("review_all", by="eve")           # unchanged: not logged again
    first.controller.engine.storage.close()
    entries = list(FilesBackend(path=tmp_path / "s").read_ledger(0))
    assert [e.payload for e in entries if e.kind == LedgerKind.REVIEW_POLICY] == [
        {"policy": "standards", "by": "system"}, {"policy": "review_all", "by": "eve"}]
    assert policy_at(entries) == "review_all" and policy_at(entries, 0) is None
    again = runner(FilesBackend(path=tmp_path / "s"))
    assert again.controller.config.review.policy == "review_all"
    assert len([e for e in again.controller.engine.ledger.of_kind(LedgerKind.REVIEW_POLICY)]) == 2


def test_the_overlap_guards_held_signals_come_back(tmp_path, monkeypatch):
    first = runner(FilesBackend(path=tmp_path / "s"))
    both = good("O", "2026-08-04T09:00:00Z", 0.5, signals=[
        {"type": "observe", "value_of": "central_bank.policy_rate", "value": 0.5},
        {"type": "observe", "value_of": "crude_oil.price", "value": 90.0}])
    # the fixture world has no two driving views of one total, so the guard is told what to hold back
    monkeypatch.setattr("axelrod_wm.sim.imports.overlap_guard", lambda graph, items, folded, held: (
        {i.id: {1: "overlapping view: held"} for i in items}, []))
    first.import_items(bundle(both))
    assert first.import_skips == {"IM-O": {1: "overlapping view: held"}}
    first.controller.engine.storage.close()
    assert kept(runner(FilesBackend(path=tmp_path / "s")))["skips"] == first.import_skips


def test_a_run_decided_just_before_the_restart_goes_on(tmp_path):
    first = runner(FilesBackend(path=tmp_path / "s"))
    first.import_items(bundle(bare("B", "2026-08-05T09:00:00Z", 0.75)))
    first.controller.auto_resume = False
    first.controller.approve(first.controller.pending_proposals()[0].id, "eve")      # decided; the run did not go on
    first.controller.engine.storage.close()
    again = runner(FilesBackend(path=tmp_path / "s"))
    assert again.controller.updates[first.controller.active_update].state == UpdateState.DONE
    assert not again.controller.pending_proposals()


def test_a_model_whose_hash_does_not_match_its_record_is_not_resumed(tmp_path):
    first = runner(FilesBackend(path=tmp_path / "s"))
    first.controller.engine.storage.close()
    path = tmp_path / "s" / "versions.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    rows[-1]["state_hash"] = "0" * 64
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ControllerError, match="cannot be restored, so it is not resumed: hash mismatch"):
        runner(FilesBackend(path=tmp_path / "s"))


def test_resume_needs_a_stored_model_and_refuses_a_stale_one(tmp_path):
    raw = load_scenario_yaml(str(ACME_SCENARIO))
    empty = ImportRunner(None, None, ScenarioScript.model_validate(raw), True, storage=MemoryBackend())
    with pytest.raises(ControllerError, match="no stored imported model"):
        empty.resume()
    w = world(tmp_path)
    first = runner(FilesBackend(path=tmp_path / "s"), w)
    first.controller.engine.storage.close()
    with (w / "entities.yaml").open("a") as fh:
        fh.write("# a changed file\n")
    stale = ImportRunner(None, None, first.script, True, storage=FilesBackend(path=tmp_path / "s"))
    with pytest.raises(ControllerError, match="other construction files, changed: world/entities.yaml"):
        stale.resume()
    stale.storage.close()
    ledger = tmp_path / "s" / "ledger.jsonl"
    ledger.write_text("".join(x for x in ledger.read_text().splitlines(keepends=True) if "import_loaded" not in x))
    unrecorded = ImportRunner(None, None, first.script, True, storage=FilesBackend(path=tmp_path / "s"))
    with pytest.raises(ControllerError, match="no record of its construction inputs"):
        unrecorded.resume()


def test_a_changed_construction_file_rebuilds_the_base_and_replays_the_imports(tmp_path):
    w = world(tmp_path)
    first = runner(FilesBackend(path=tmp_path / "s"), w)
    first.import_items(bundle(good("A", "2026-08-04T09:00:00Z", 0.5), title="auto"))
    first.controller.set_review_policy("review_all", by="eve")
    two = good("P", "2026-08-05T09:00:00Z", 0.75, signals=[
        {"type": "observe", "value_of": "central_bank.policy_rate", "value": 0.75},
        {"type": "observe", "value_of": "crude_oil.price", "value": 90.0}])
    first.import_items(bundle(two, good("Q", "2026-08-05T10:00:00Z", 1.0), title="reviewed"))
    ctl = first.controller
    ctl.approve(ctl.pending_proposals()[0].id, "eve", keep=[0], confidence=0.9)      # a confidence, an edit, an approval
    ctl.reject(ctl.pending_proposals()[0].id, "eve", "not this one")
    first.import_items(bundle(good("R", "2026-08-06T09:00:00Z", 1.25), title="left"))   # left waiting
    ctl.set_review_policy("standards", by="eve")                      # chosen after the last import
    before = kept(first)
    assert len(before["queue"]) == 1 and before["policy"] == "standards"
    old_digest = construction_digest_of(first)
    first.controller.engine.storage.close()

    with (w / "entities.yaml").open("a") as fh:
        fh.write("# a comment: the files differ, the model does not\n")
    again = runner(FilesBackend(path=tmp_path / "s"), w)
    assert "rebuilt from them and 3 imports replayed" in again.caption
    assert (tmp_path / f"s.before-{old_digest[:10]}").is_dir()
    after = kept(again)
    assert {k: after[k] for k in ("version", "hash", "queue", "policy", "imported", "log")} == {
        k: before[k] for k in ("version", "hash", "queue", "policy", "imported", "log")}
    assert [p.status for p in again.controller.proposals.values()].count("rejected") == 1
    # and it is a model like any other now: the pending review is approved, then it resumes unchanged
    approve_all(again)
    done = kept(again)
    again.controller.engine.storage.close()
    assert kept(runner(FilesBackend(path=tmp_path / "s"), w)) == done


def construction_digest_of(r: ImportRunner) -> str:
    rec = next(e.payload for e in r.controller.engine.ledger.of_kind(LedgerKind.UPDATE)
               if e.payload.get("state") == "import_loaded")
    return rec["digest"]


def test_a_replay_in_memory_and_without_a_record_keeps_no_copy(tmp_path):
    w = world(tmp_path)
    store = MemoryBackend()
    first = runner(store, w)
    first.import_items(bundle(good("A", "2026-08-04T09:00:00Z", 0.5)))
    (w / "interactions.yaml").write_text((w / "interactions.yaml").read_text() + "\n# changed\n")
    again = runner(store, w)
    assert again.imported.keys() == {"IM-A"} and "kept as a copy" in again.caption
    assert policy_at(list(store.read_ledger(0))) == "standards"
    # a file-backed storage that holds no record of its construction is rebuilt the same way
    f = runner(FilesBackend(path=tmp_path / "f"), w)
    f.controller.engine.storage.close()
    ledger = tmp_path / "f" / "ledger.jsonl"
    ledger.write_text("".join(x for x in ledger.read_text().splitlines(keepends=True) if "import_loaded" not in x))
    runner(FilesBackend(path=tmp_path / "f"), w)
    assert (tmp_path / "f.before-unrecorded").is_dir()
    f2 = runner(FilesBackend(path=tmp_path / "f"), w)           # a second archive of the same name replaces the first
    f2.controller.engine.storage.close()
    ledger.write_text("".join(x for x in ledger.read_text().splitlines(keepends=True) if "import_loaded" not in x))
    runner(FilesBackend(path=tmp_path / "f"), w)
    assert (tmp_path / "f.before-unrecorded").is_dir()


def test_another_scenarios_storage_is_archived_and_rebuilt_without_its_imports(tmp_path):
    first = runner(FilesBackend(path=tmp_path / "s"))
    first.import_items(bundle(good("A", "2026-08-04T09:00:00Z", 0.5)))
    first.controller.engine.storage.close()
    raw = load_scenario_yaml(str(ACME_SCENARIO))
    raw["id"] = "another_demo"
    other = ImportRunner(None, None, ScenarioScript.model_validate(raw), True, storage=FilesBackend(path=tmp_path / "s"))
    other.load()
    assert other.imported == {} and "0 imports replayed" in other.caption
    assert any(p.name.startswith("s.before-") for p in tmp_path.iterdir())


def test_a_replay_stops_when_the_new_base_asks_for_a_decision_nobody_recorded(tmp_path):
    r = runner(MemoryBackend())
    r.controller.set_review_policy("review_all", by="eve")
    r.import_items(bundle(good("A", "2026-08-04T09:00:00Z", 0.5)))
    ctl = r.controller
    key = ("IM-A", "graph_update")
    with pytest.raises(ControllerError, match=r"stopped at PR-\d+ \(IM-A\): it now waits for a decision nobody recorded"):
        ImportRunner._replay_decisions(ctl, "t", {}, last=True)
    undecided = {key: [[NS(payload={"action": "deferred", "by": "x"})]]}
    assert ImportRunner._replay_decisions(ctl, "t", undecided, last=True) is False         # pending then too: stays
    with pytest.raises(ControllerError, match="nobody recorded"):
        ImportRunner._replay_decisions(ctl, "t", undecided, last=False)
    by_policy = {key: [[NS(payload={"action": "auto_applied", "by": "policy:standards"})]]}
    with pytest.raises(ControllerError, match="nobody recorded"):
        ImportRunner._replay_decisions(ctl, "t", by_policy, last=True)       # applied by policy, now needs a person
    assert ImportRunner._replay_decisions(ctl, "t", {key: [[NS(payload={
        "action": "approved", "by": "eve", "note": None})]]}, last=True)
    assert not ctl.pending_proposals()


def test_an_explicit_reset_forgets_the_stored_model_and_a_throwaway_session_is_never_kept(tmp_path):
    first = runner(FilesBackend(path=tmp_path / "s"))
    first.import_items(bundle(good("A", "2026-08-04T09:00:00Z", 0.5)))
    first.discard_saved()
    fresh = runner(FilesBackend(path=tmp_path / "s"))
    assert not fresh.imported and fresh.controller.engine.version < kept(first)["version"]
    cfg = load_config()
    cfg.storage.backend = "memory"
    throwaway = runner(None, config=cfg)
    throwaway.import_items(bundle(good("A", "2026-08-04T09:00:00Z", 0.5)))
    throwaway.discard_saved()                 # nothing kept, nothing to forget
    assert runner(None, config=cfg).imported == {}


def test_the_gate_reads_nothing_for_a_market_event_that_was_not_imported():
    r = runner(MemoryBackend())
    assert r._import_context("ME-U-000001") is None
    r.import_items(bundle(good("A", "2026-08-04T09:00:00Z", 0.5), good("B", "2026-08-05T09:00:00Z", 0.75)))
    ctx = r._import_context("IM-A")
    assert ctx.item.id == "A" and [i.id for i in ctx.folded] == ["B"] and ctx.origin is r._origin_map


def test_the_state_helpers():
    assert changed_files({"a": "1", "b": "2"}, {"a": "1", "b": "3", "c": "4"}) == ["b", "c"]
    assert construction_digest({"a": "1"}) != construction_digest({"a": "2"})
    entries = [NS(payload={"id": "PR-000007", "update_id": "UPD-000002"}), NS(payload={"proposal_id": "PR-000009"}),
               NS(payload={"id": "ME-U-000003"}), NS(payload={"id": "not-an-id"})]
    assert counters_from(entries) == {"PR": 9, "UPD": 2, "ME-U": 3}
