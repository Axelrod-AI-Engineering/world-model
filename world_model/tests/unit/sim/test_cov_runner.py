"""The scenario runner (§11.3) on a mini scripted scenario: the init cache, the session storage, stepping (driven,
undriven, paused for review), each step action, play and pause, sessions, and build_runner's choices."""

from __future__ import annotations

import gzip
import json
import sys
from datetime import UTC, datetime

import pytest

from axelrod_wm.control.updates import UpdateState
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.review import ProposalStatus
from axelrod_wm.repo.snapshots import FilesBackend, MemoryBackend, state_hash
from axelrod_wm.sim import runner as runner_mod
from axelrod_wm.sim.runner import ScenarioRunner, StepReport, _hash_files, build_runner

CAPTION = {"at": "2026-01-26T00:00:00Z", "caption": "The starting picture."}
FED = {"at": "2026-01-28T20:00:00Z", "update": {}, "caption": "The Fed raises rates."}
OPEC = {"at": "2026-02-02T14:00:00Z", "update": {}, "caption": "OPEC+ cuts output."}


def test_load_builds_the_init_cache_once_and_reset_reuses_it(mini_runner, mini_paths, monkeypatch):
    r = mini_runner()
    st = r.load()
    assert st.loaded and st.state == "idle" and st.step_index == 0 and st.total_steps == 0
    assert r.init_info["days"] == 7 and r.init_info["history_events"] == 6
    meta = json.loads(gzip.decompress((mini_paths["cache"] / "init_snapshot.json.gz").read_bytes()))
    assert meta["version"] == r.init_version and meta["format"] == runner_mod.INIT_FORMAT
    eng = r.controller.engine
    assert eng.wm.deviations.date_of(int(eng.wm.last_processed_day)).isoformat() == "2026-01-25"
    # the session's ledger starts with the scenario's "loaded" entry, numbered after the history's entries
    (loaded,) = eng.ledger.of_kind(LedgerKind.UPDATE)
    assert loaded.payload["state"] == "loaded" and loaded.seq > r.init_seq
    # a second load (reset) reads the cache instead of building it
    loaded_version = eng.version                     # the init version plus the scenario's hypotheses
    assert loaded_version > r.init_version and set(eng.wm.hypotheses) >= {"H-fed-hold"}
    built = []
    monkeypatch.setattr(ScenarioRunner, "_build_init", lambda self, *a: built.append(1))
    r.reset()
    assert not built and r.controller.engine.version == loaded_version


def test_a_corrupt_or_stale_cache_is_rebuilt(mini_script, tmp_path):
    r = ScenarioRunner(None, None, mini_script(), False, storage=MemoryBackend(), cache_dir=tmp_path)
    r.load()
    path = tmp_path / "init_snapshot.json.gz"
    path.write_bytes(b"not gzip")
    r.load()                                           # an unreadable cache is rebuilt
    assert json.loads(gzip.decompress(path.read_bytes()))["version"] == r.init_version
    meta = json.loads(gzip.decompress(path.read_bytes()))
    path.write_bytes(gzip.compress(json.dumps({**meta, "key": "stale"}).encode()))
    r.load()                                           # a cache under another key is rebuilt too
    assert json.loads(gzip.decompress(path.read_bytes()))["key"] == meta["key"]
    # without the cache, the init is built every time
    r2 = ScenarioRunner(None, None, mini_script(), False, storage=MemoryBackend(), cache_dir=tmp_path, use_cache=False)
    r2.load()
    assert r2.init_version == r.init_version


def test_the_init_lock_runs_unlocked_without_posix_locks(mini_runner, monkeypatch):
    r = mini_runner()
    monkeypatch.setitem(sys.modules, "fcntl", None)        # importing it raises ImportError
    with r._init_lock():
        assert (r.cache_dir / "init.lock").exists()


def test_a_history_replay_that_does_not_finish_is_an_error(mini_script, tmp_path, monkeypatch):
    from axelrod_wm.control.controller import WorldModelController

    real = WorldModelController.request_update

    def failing(self, request, **kw):
        run = real(self, request, **kw)
        run.state, run.error = UpdateState.FAILED, "boom"
        return run

    monkeypatch.setattr(WorldModelController, "request_update", failing)
    r = ScenarioRunner(None, None, mini_script(), False, storage=MemoryBackend(), cache_dir=tmp_path)
    with pytest.raises(RuntimeError, match="the history replay ended in state failed: boom"):
        r.load()


def test_a_given_config_is_copied_and_the_seed_flag_wins(mini_script, mini_paths):
    from tests.conftest import make_config

    cfg = make_config()
    seed = cfg.seed
    r = ScenarioRunner(None, None, mini_script(), False, config=cfg, seed=5, cache_dir=mini_paths["cache"])
    eff = r.effective_config()
    assert eff is not cfg and eff.seed == 5 and cfg.seed == seed
    r2 = ScenarioRunner(None, None, mini_script(), False, config=cfg, cache_dir=mini_paths["cache"])
    assert r2.effective_config().seed == 11            # the script's seed when no flag is given


def test_hash_files_skips_caches_and_hashes_files_outside_the_repo(tmp_path):
    d = tmp_path / "pkg"
    (d / "__pycache__").mkdir(parents=True)
    (d / "examples").mkdir()
    (d / "a.py").write_text("x = 1\n")
    (d / "__pycache__" / "a.pyc").write_text("junk")
    (d / "examples" / "e.py").write_text("y = 2\n")
    lone = tmp_path / "lone.txt"
    lone.write_text("hi")
    base = _hash_files([d, lone, tmp_path / "missing.txt"], skip=("examples",))
    (d / "__pycache__" / "a.pyc").write_text("other junk")
    (d / "examples" / "e.py").write_text("y = 3\n")
    assert _hash_files([d, lone], skip=("examples",)) == base     # caches and skipped folders do not count
    (d / "a.py").write_text("x = 2\n")
    assert _hash_files([d, lone], skip=("examples",)) != base


def test_a_files_session_copies_the_history(mini_runner, tmp_path, monkeypatch):
    storage = FilesBackend(path=tmp_path / "session")
    r = mini_runner(storage=storage)
    r.load()
    names = {p.name for p in (tmp_path / "session" / "snapshots").glob("v*.json.gz")}
    init_names = {p.name for p in (r._init_dir() / "snapshots").glob("v*.json.gz")}
    assert init_names and init_names <= names
    eng = r.controller.engine
    # every version is restorable from the copied ledger and snapshots
    meta = json.loads(gzip.decompress(r._init_cache_path().read_bytes()))
    wm, ltm = eng.restore(r.init_version)
    assert state_hash(wm, ltm) == meta["state_hash"]
    # where hard links fail (another file system), the snapshots are copied
    monkeypatch.setattr(runner_mod.os, "link", lambda *a: (_ for _ in ()).throw(OSError("cross-device")))
    r2 = mini_runner(storage=FilesBackend(path=tmp_path / "session2"))
    r2.load()
    assert {p.name for p in (tmp_path / "session2" / "snapshots").glob("v*.json.gz")} >= init_names


def test_headless_steps_run_every_action(mini_runner):
    steps = [
        CAPTION,
        FED,
        {"at": "2026-01-28T21:00:00Z", "thesis": ["T-00", "T-01"], "pin": ["T-00"],
         "structure": [{"group": {"name": "Rates and funding", "members": ["interest_rates", "credit_availability"],
                                  "id": "SE-T"}},
                       {"dissolve": {"pattern": "S1", "reason": "test"}},
                       {"retire": {"interaction": "e01", "reason": "test"}}],
         "caption": "Pose and edit."},
        {"at": "2026-01-28T21:00:00Z", "pose_hypothesis": {"hypothesis": "H-fed-hold", "base_thesis": "T-01"}},
        {"at": "2026-01-28T21:00:00Z", "pose_hypothesis": {"hypothesis": "H-fed-hold"}},
        {"at": "2026-01-28T21:30:00Z", "decision": "D-01"},
        {"at": "2026-01-28T22:00:00Z",
         "evaluate": {"freeze_at": "2026-01-26T23:59:59Z", "market_event_ids": ["ME-01"], "horizon_days": 2}},
        {"at": "2026-04-28T00:00:00Z", "resolve_decision": "D-01"},
    ]
    seen = []
    r = mini_runner(steps)
    r.listeners.append(lambda kind, report: seen.append((kind, report.step_index)))
    rep0 = r.step()                                    # loads on demand
    assert r.loaded and rep0.update_id is None and rep0.notes == [] and r.controller.now == datetime(2026, 1, 26,
                                                                                                         tzinfo=UTC)
    rep1 = r.step()
    assert rep1.update_id and "ME-01" in rep1.market_event_ids and rep1.notes[-1].startswith(f"{rep1.update_id}: done")
    rep2 = r.step()
    ctl = r.controller
    assert [n.split(" ")[0] for n in rep2.notes] == ["superentity_admission", "superentity_dissolution",
                                                     "graph_update", "pinned"]
    assert set(r.forecasts_by_thesis) == {"T-00", "T-01"} and len(rep2.forecast_ids) == 2
    assert "T-00" in ctl.engine.wm.forecast_layer.pinned
    rep3 = r.step()
    fc = ctl.forecast(rep3.forecast_ids[0])
    assert fc.thesis_id == "T-01+H-fed-hold" and r.forecasts_by_thesis["T-02"] == fc.id
    assert r.thesis_aliases == {"T-02": "T-01+H-fed-hold"}
    rep4 = r.step()                                    # a second hypothesis gets the next alias
    assert r.thesis_aliases["T-03"] == "T-base+H-fed-hold" and ctl.forecast(rep4.forecast_ids[0]).thesis_id == \
        "T-base+H-fed-hold"
    rep5 = r.step()
    (rec,) = ctl.decisions.values()
    assert rep5.notes == [f"decision D-01 at version {rec.state_version}"]
    assert rec.state_version == ctl.forecast(r.forecasts_by_thesis["T-00"]).based_on_version
    rep6 = r.step()
    assert rep6.notes[0].startswith("evaluation ")
    rep7 = r.step()
    assert rep7.notes[0].startswith("outcome crps ") and rec.outcome is not None
    assert r.state == "done" and r.status().state == "done" and r.status().next_step_at is None
    # past the end: the last report again, and the state stays done
    assert r.step() is rep7 and r.state == "done"
    assert [k for k, _ in seen] == ["step"] * 8 and [i for _, i in seen] == list(range(8))
    assert len(r.reports) == 8


def test_a_decision_without_a_posed_baseline_is_recorded_at_the_current_version(mini_runner):
    from axelrod_wm.inference.decisions import DecisionError

    r = mini_runner([{"at": "2026-01-26T00:00:00Z", "thesis": "T-01"}, {"at": "2026-01-26T00:00:00Z",
                                                                         "decision": "D-01"}])
    r.step()
    with pytest.raises(DecisionError, match="baseline"):
        r.step()                                       # T-00 was never posed: the record has no baseline to cite


def test_a_structure_action_needs_one_edit(mini_runner):
    from types import SimpleNamespace

    r = mini_runner()
    r.load()
    with pytest.raises(ValueError, match="needs group, dissolve, or retire"):
        r._structure_action(SimpleNamespace(group=None, dissolve=None, retire=None, by="x"))


def test_unknown_user_market_events_are_refused_and_drawn_events_are_built(mini_runner):
    r = mini_runner([{"at": "2026-02-16T12:00:00Z", "update": {"user_market_events": ["ME-99"]}}])
    r.load()
    with pytest.raises(KeyError, match="ME-99"):
        r.step()
    r2 = mini_runner([{"at": "2026-01-27T12:00:00Z",
                       "update": {"user_market_events": ["ME-04"], "user_graph_update_events": ["UG-01"]}}])
    r2.load()
    req = r2._update_request(r2.script.steps[0])
    assert [e.id for e in req.user_market_events] == ["ME-04"]
    (gue,) = req.user_graph_update_events
    assert gue.id == "UG-01" and gue.recorded_at == r2.script.steps[0].at


def test_an_interactive_step_waits_for_review_and_finishes_after_it(mini_runner):
    r = mini_runner([OPEC, {"at": "2026-02-03T00:00:00Z", "caption": "after"}], interactive=True)
    r.load()
    rep = r.step()
    assert rep.notes == ["awaiting review"] and r.state == "awaiting_review"
    assert r.pending_update() == rep.update_id
    ctl = r.controller
    run = ctl.get_update(rep.update_id)
    assert run.state == UpdateState.AWAITING_REVIEW
    # stepping again while the review is open shows the same placeholder
    assert r.step().notes == ["awaiting review"]
    # resume_after_review does nothing while the run still waits
    assert r.resume_after_review().state == "awaiting_review" and r.pending_step is not None
    # deciding every pending item lets the run finish; resume_after_review then runs the step's action
    ctl.auto_resume = True
    while run.state == UpdateState.AWAITING_REVIEW:
        ctl.reject(run.waiting_on, "kim", "not now")      # each rejection resumes the run
    assert run.state == UpdateState.DONE and run.report.rejected >= 1
    st = r.resume_after_review()
    assert r.pending_step is None and r.step_index == 1 and r.reports[-1].update_id == rep.update_id
    assert st.state == ("awaiting_review" if ctl.pending_proposals() else "idle")


def test_an_undriven_step_is_finished_by_the_next_call(mini_runner):
    r = mini_runner([FED])
    r.load()
    rep = r.step(drive=False)
    assert rep.notes == ["updating"] and r.state == "running" and r.pending_update() == rep.update_id
    assert r.controller.get_update(rep.update_id).state == UpdateState.RUNNING
    # a review decision while the run is still processing days leaves the step pending
    assert r.resume_after_review().update_id == rep.update_id and r.pending_step is not None
    # an undriven resume of a running update keeps it pending
    assert r._resume_pending(drive=False).notes == ["updating"]
    done = r.step()
    assert done.update_id == rep.update_id and r.pending_step is None and r.state == "done"
    assert r.controller.get_update(rep.update_id).state == UpdateState.DONE


def test_a_headless_resume_of_a_paused_step_defers_what_waits(mini_runner):
    r = mini_runner([OPEC], interactive=True)
    r.load()
    r.step()
    assert r.state == "awaiting_review"
    r.interactive = False                              # the same step, now driven headless
    rep = r.step()
    assert r.pending_step is None and rep.update_id
    run = r.controller.get_update(rep.update_id)
    assert run.state == UpdateState.DONE and run.report.deferred >= 1


def test_a_headless_step_defers_what_needs_review(mini_runner):
    r = mini_runner([OPEC])
    r.load()
    rep = r.step()
    ctl = r.controller
    run = ctl.get_update(rep.update_id)
    assert run.state == UpdateState.DONE and run.report.deferred >= 1
    assert any(p.status == ProposalStatus.DEFERRED for p in ctl.proposals.values())


def test_play_stops_at_a_review_and_at_the_end(mini_runner):
    r = mini_runner([CAPTION, OPEC, {"at": "2026-02-03T00:00:00Z"}], interactive=True)
    r.load()
    st = r.play(until_step=1)
    assert st.step_index == 1 and st.state == "idle" and not r.playing
    st = r.play()
    assert st.step_index == 1 and st.state == "awaiting_review"
    # while the step's review is open, play does not step again
    assert r.play().step_index == 1
    # the paused update is driven to its end elsewhere (each review deferred): play then finishes the step and
    # goes on to the end
    ctl = r.controller
    ctl.auto_resume = False
    uid = r.pending_update()
    while ctl.get_update(uid).state == UpdateState.AWAITING_REVIEW:
        ctl.continue_update(uid)
    assert r.state == "awaiting_review" and r.pending_step is not None
    st = r.play()
    assert r.pending_step is None and r.reports[1].update_id == uid
    assert st.step_index == 3 and st.state == "done"


def test_a_step_whose_update_failed_finishes_without_its_report(mini_runner):
    r = mini_runner([FED])
    r.load()
    rep = r.step(drive=False)
    run = r.controller.get_update(rep.update_id)
    r.controller.cycle._fail(run, RuntimeError("the feed went away"))
    done = r.step()
    assert run.state == UpdateState.FAILED and run.report is None
    assert done.update_id == rep.update_id and done.notes == [] and r.pending_step is None


def test_auto_approve_and_a_broadcasting_tracer(mini_runner, tmp_path):
    import asyncio

    from axelrod_wm.trace import BroadcastTracer

    tracer = BroadcastTracer(run_id="b")
    loop = asyncio.new_event_loop()
    queue: asyncio.Queue = asyncio.Queue()
    tracer.subscribe(loop, queue)
    r = mini_runner([OPEC], tracer=tracer, auto_approve=True, storage=FilesBackend(path=tmp_path / "s"))
    r.load()
    assert r.controller.config.review.policy == "auto_approve_all"
    rep = r.step()
    run = r.controller.get_update(rep.update_id)
    assert run.report.deferred == 0 and run.report.approved + run.report.auto_applied >= 1
    loop.run_until_complete(asyncio.sleep(0))
    statuses = []
    while not queue.empty():
        m = queue.get_nowait()
        if m["type"] == "status":
            statuses.append(m["status"])
    loop.close()
    assert statuses and statuses[-1]["step_index"] == 1 and statuses[-1]["state"] == "done"
    r.controller.engine.storage.flush()
    r2 = mini_runner([OPEC], auto_approve=True, storage=FilesBackend(path=tmp_path / "s"))
    r2.resume(r.session_record())
    assert r2.controller.config.review.policy == "auto_approve_all"


def test_resume_after_review_without_a_paused_step(mini_runner):
    r = mini_runner([CAPTION])
    r.load()
    assert r.resume_after_review().state == "idle" and r.step_index == 0


def test_pause_stops_play_and_status_settles_a_stale_review_state(mini_runner):
    r = mini_runner([CAPTION, {"at": "2026-01-27T00:00:00Z"}])
    st = r.status()                                    # before loading: no controller
    assert not st.loaded and st.version == 0 and st.sim_time == datetime(2026, 1, 26, tzinfo=UTC)
    r.load()
    r.state = "running"
    assert r.pause().state == "idle"
    # a pause during play stops it after the step in progress
    r.listeners.append(lambda kind, report: r.pause())
    st = r.play()
    assert st.step_index == 1 and st.state == "idle" and not r.playing
    r.state = "awaiting_review"                        # nothing pending, no paused step
    assert r.status().state == "idle"
    r.step_index = 2
    r.state = "awaiting_review"
    assert r.status().state == "done"
    assert r.pause().state == "done"


def test_finishing_a_step_with_pending_proposals_waits_for_review(mini_runner):
    r = mini_runner([{"at": "2026-01-26T00:00:00Z",
                      "structure": [{"group": {"name": "G", "members": ["interest_rates", "credit_availability"]}}]},
                     {"at": "2026-01-27T00:00:00Z"}], interactive=True)
    r.load()
    r.controller.set_review_policy("review_all")
    r.step()
    assert r.controller.pending_proposals() and r.state == "awaiting_review"
    r.playing = True                                   # a play in progress keeps a headless state "running"
    r.interactive = False
    r.state = "idle"
    r.step_index = 0
    r.step()
    assert r.state == "running"


def test_sessions_resume_from_the_files_backend(mini_runner, tmp_path):
    path = tmp_path / "s"
    r = mini_runner([FED, OPEC], storage=FilesBackend(path=path), interactive=True)
    r.load()
    r.step()
    r.step()                                           # paused on OPEC's review: later days' events are queued
    rec = r.session_record()
    assert rec["scenario"] == "oil_shock_demo" and rec["step_index"] == 1 and rec["storage"] == str(path)
    assert rec["config"] is None and rec["version"] == r.controller.engine.version
    r.controller.engine.storage.flush()
    r2 = mini_runner([FED, OPEC], storage=FilesBackend(path=path), interactive=True)
    st = r2.resume(rec)
    ctl = r2.controller
    assert st.loaded and st.step_index == 1 and ctl.engine.version == r.controller.engine.version
    assert ctl.now == datetime.fromisoformat(rec["now"])
    assert ctl.market_status["ME-01"] == "applied"
    last = int(ctl.engine.wm.last_processed_day)
    unprocessed = [m for m in ctl.market_events.values() if ctl.engine.wm.deviations.day_of(m.published_at) > last]
    assert unprocessed and all(ctl.market_status[m.id] == "queued" for m in unprocessed)
    # without a recorded time, the session continues at the model's clock
    r3 = mini_runner(storage=FilesBackend(path=path))
    st3 = r3.resume({k: v for k, v in rec.items() if k != "now"})
    assert st3.sim_time == r3.controller.engine.wm.clock


def test_resume_needs_a_session(mini_runner, tmp_path):
    r = mini_runner(storage=FilesBackend(path=tmp_path / "empty"))
    with pytest.raises(RuntimeError, match="axelrod init"):
        r.resume({})


def test_the_checklist_is_empty_without_a_recorder(mini_runner):
    r = mini_runner()
    assert r.checklist() == []

    class Recorder:
        def attach(self, runner):
            self.runner = runner

        def evaluate(self, runner):
            return [("1. ok", True)]

    r.recorder = Recorder()
    r.load()
    assert r.recorder.runner is r and r.checklist() == [("1. ok", True)]


def test_a_placeholder_report_names_its_step():
    rep = StepReport(step_index=0, at=datetime(2026, 1, 1, tzinfo=UTC), update_id=None, market_event_ids=[],
                     proposal_ids=[], forecast_ids=[])
    assert rep.notes == [] and rep.caption is None


def test_build_runner_chooses_the_runner_and_reads_a_config_file(tmp_path):
    from axelrod_wm.sim.examples.session import ProdDemoRunner, SmallDemoRunner
    from axelrod_wm.sim.imports import ImportRunner

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("seed: 99\n")
    r = build_runner("oil_shock_demo", config_path=str(cfg), storage=MemoryBackend())
    assert type(r) is ScenarioRunner and r.config.seed == 99 and r.config_path == str(cfg)
    assert r.recorder is not None                       # the oil demo keeps a checklist
    assert build_runner("oil_shock_demo", record_checklist=False).recorder is None
    prod = build_runner("prod_demo")
    assert type(prod) is ProdDemoRunner and prod.script.id == "oil_shock_demo" and prod.recorder is None
    assert type(build_runner("small_demo")) is SmallDemoRunner
    assert type(build_runner("acme_demo")) is ImportRunner
