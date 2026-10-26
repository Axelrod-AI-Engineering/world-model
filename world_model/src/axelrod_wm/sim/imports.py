"""A world model fed by imports (Oct 11): the ordinary way a client uses the product.

The model starts seeded with the client's view of their world (construction files and superentities, no synthetic
history). New information arrives as an import bundle (intake/bundle.py): dated items a research agent has already
read and categorized. Importing folds each selected item in on its own date, through one update run that pauses at
each item's review; nothing changes the model until a person approves it. Predict then forecasts on what was
approved.

Any scenario with `imports: true` uses this runner (a client's, in the client root). Bundles come from the person's own
file (the Import dialog's file picker) or, when the scenario names an `imports_dir` that exists on the server, from
that folder; the folder is never committed.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from axelrod_ingest.contract.bundle import ImportBundle, ImportItem
from axelrod_wm.control.controller import ControllerError, WorldModelController
from axelrod_wm.control.updates import UpdateRequest, UpdateRun, UpdateState
from axelrod_wm.engine.engine import build_engine, make_storage
from axelrod_wm.engine.focus import focus_result
from axelrod_wm.engine.initialize import (
    ConstructionSpec,
    Initializer,
    SeedFile,
    as_paths,
    load_vocabulary,
    read_construction,
    resolve_path,
)
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.market import MarketEvent, MarketEventKind
from axelrod_wm.intake.overlap import RULE as OVERLAP_RULE
from axelrod_wm.intake.overlap import overlap_guard
from axelrod_wm.intake.structured import (
    StructuredTranslator,
    market_event_of,
    signal_conversion,
    translate_item,
)
from axelrod_wm.repo.ledger import LedgerKind
from axelrod_wm.repo.review import ImportContext, ProposalStatus
from axelrod_wm.repo.snapshots import RestoreError
from axelrod_wm.sim.import_state import (
    batch_entries,
    changed_files,
    construction_digest,
    construction_files,
    counters_from,
    decisions,
    loaded_record,
    policy_at,
    restore_proposals,
)
from axelrod_wm.sim.runner import RunnerStatus, ScenarioRunner
from axelrod_wm.sim.scenario import load_theses
from axelrod_wm.trace import Phase

DEFAULT_POLICY = "standards"          # an imported model's review policy until a person chooses another


class ImportRunner(ScenarioRunner):
    canvas_kind = "seeded"

    # -- load, resume ------------------------------------------------------------------------------
    def _construction_dirs(self) -> list[Path]:
        return as_paths(self.script.initialization.construction_dir)       # one folder, or a unified scenario's several

    def _inputs(self, cfg: Any) -> dict[str, str]:
        """SHA-256 of everything the base model is built from (sim/import_state.py): a stored model built from other
        inputs is stale."""
        ini = self.script.initialization
        focus = ini.focus.model_dump(mode="json") if ini.focus is not None else None
        settings = {"scenario": self.script.id, "start": str(self.script.start), "seed": int(cfg.seed), "focus": focus}
        return construction_files([*self._construction_dirs(), resolve_path(ini.taxonomy_dir)],
                                  as_paths(ini.seeds), settings)

    def _origin(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for d in self._construction_dirs():
            out.update(read_construction(d)[1])
        return out

    def load(self) -> RunnerStatus:
        """Open the model. A storage that holds versions is resumed, not rebuilt: the model keeps its imports, review
        policy and pending reviews across restarts. Only a storage that is empty (or none given, a throwaway session)
        is built from the construction files; one built from other files is rebuilt and the recorded imports are
        replayed on it (`_replay`)."""
        with self.lock:
            cfg = self.effective_config()
            storage = self.storage if self.storage is not None else make_storage(cfg)
            inputs = self._inputs(cfg)
            self._origin_map = self._origin()
            if self.storage is None or not storage.versions():
                storage.reset()
                return self._load_fresh(cfg, storage, inputs)
            entries = list(storage.read_ledger(0))
            rec = loaded_record(entries)
            if rec is not None and rec["digest"] == construction_digest(inputs):
                return self._resume_stored(cfg, storage, entries)
            return self._replay(cfg, storage, entries, inputs, rec)

    def discard_saved(self) -> None:
        """Forget the stored model, so the next load builds from the construction files (an explicit reset)."""
        with self.lock:
            if self.storage is not None:         # without one, every load starts from the files anyway
                self.storage.reset()

    def _load_fresh(self, cfg: Any, storage: Any, inputs: dict[str, str]) -> RunnerStatus:
        ini = self.script.initialization
        vocab = load_vocabulary(ini.taxonomy_dir)
        eng = build_engine(cfg, storage, self.tracer, vocab=vocab)
        init = Initializer(eng)
        spec = ConstructionSpec.load(ini.construction_dir, ini.taxonomy_dir, focus=ini.focus)
        init.construct(spec, ini.taxonomy_dir, start=self.script.start, vocab=vocab)
        if ini.seeds:
            init.load_seeds(SeedFile.load(ini.seeds, focus=ini.focus), now=eng.wm.clock)
        eng.save_snapshot()
        eng.ledger.append(LedgerKind.UPDATE, {"state": "import_loaded", "scenario": self.script.id,
                                              "digest": construction_digest(inputs), "files": inputs},
                          recorded_at=eng.wm.clock)
        ctl = WorldModelController(eng, scenario_dir=self.scenario_dir)
        ctl.set_review_policy(DEFAULT_POLICY, by="system", record=True)
        self._adopt(ctl, eng.version, eng.ledger.next_seq - 1)
        ctl.advance_now(datetime.combine(self.script.start, time(0), tzinfo=UTC))
        self.caption = ("Your world model, as of " + f"{self.script.start:%b %-d, %Y}" +
                        ". Import research to bring it up to date: items that meet the standards apply, "
                        "the rest wait for your review.")
        self.tracer.emit(Phase.INIT, "scenario.loaded", refs=[self.script.id], scenario_id=self.script.id,
                         version=eng.version, steps=0)
        self._broadcast()
        return self.status()

    def resume(self, session: dict | None = None) -> RunnerStatus:
        """Reopen the stored model. It refuses a model built from other construction files (`load` replays instead)."""
        with self.lock:
            cfg = self.effective_config()
            storage = self.storage if self.storage is not None else make_storage(cfg)
            if not storage.versions():
                raise ControllerError("there is no stored imported model to resume; load it first")
            entries = list(storage.read_ledger(0))
            rec = loaded_record(entries)
            inputs = self._inputs(cfg)
            self._origin_map = self._origin()
            if rec is None:
                raise ControllerError("the stored model holds no record of its construction inputs")
            if rec["digest"] != construction_digest(inputs):
                raise ControllerError("the stored model was built from other construction files, changed: "
                                      + ", ".join(changed_files(rec["files"], inputs)))
            return self._resume_stored(cfg, storage, entries)

    def _resume_stored(self, cfg: Any, storage: Any, entries: list) -> RunnerStatus:
        """The stored model as it stopped: latest version (its hash checked), imported items, review policy, id counters,
        pending proposals, and a run paused for review."""
        vocab = load_vocabulary(self.script.initialization.taxonomy_dir)
        eng = build_engine(cfg, storage, self.tracer, vocab=vocab)
        latest = storage.versions()[-1]
        try:
            wm, ltm = eng.restore(latest.version)           # verifies the state hash recorded for the version
        except RestoreError as exc:
            raise ControllerError(f"the stored model cannot be restored, so it is not resumed: {exc}") from exc
        eng.load_state(wm, ltm, latest.version)
        ctl = WorldModelController(eng, scenario_dir=self.scenario_dir, control_ids=counters_from(entries))
        ctl.set_review_policy(policy_at(entries) or DEFAULT_POLICY, record=False)
        self._adopt(ctl, latest.version, eng.ledger.next_seq - 1)
        self._restore_imports(ctl, entries)
        ctl.advance_now(max(wm.clock, entries[-1].recorded_at))
        waiting = len(ctl.pending_proposals())
        self.caption = (f"Reopened at version {latest.version}, as it was left: {len(self.imported)} imported item"
                        f"{'s' * (len(self.imported) != 1)}, {waiting} waiting for review.")
        self.tracer.emit(Phase.INIT, "scenario.resumed", refs=[self.script.id], scenario_id=self.script.id,
                         version=eng.version, steps=0)
        self._broadcast()
        return self.status()

    def _restore_imports(self, ctl: WorldModelController, entries: list) -> None:
        for e in batch_entries(entries):
            pl = e.payload
            items = [ImportItem.model_validate(d) for d in pl["items"]]
            for it in items:
                me_id = self.event_id(it)
                self.imported[me_id] = it
                if it.id in pl["skips"]:
                    self.import_skips[me_id] = {int(k): v for k, v in pl["skips"][it.id].items()}
            self.import_log.append({"title": pl["title"], "items": [i.id for i in items], "update_id": pl["update_id"],
                                    "at": pl["at"], "closed": True})
            if pl.get("origin") is not None:
                self.batch_origin[pl["update_id"]] = pl["origin"]
        for e in entries:
            if e.kind == LedgerKind.MARKET_EVENT:
                me = MarketEvent.model_validate(e.payload)
                ctl.remember_market_event(me)
                ctl.market_status[me.id] = "applied"
        ctl.proposals.update(restore_proposals(entries))
        graph = ctl.engine.wm.graph
        waiting = {p.market_event_id for p in ctl.pending_proposals()}
        for me_id, item in self.imported.items():
            if me_id in waiting:
                ctl.market_status[me_id] = "awaiting review"
                ctl.translations[me_id] = translate_item(item, ctl.market_events[me_id], graph,
                                                         self.import_skips.get(me_id))[0]
        self._restore_run(ctl, entries)

    @staticmethod
    def _restore_run(ctl: WorldModelController, entries: list) -> None:
        """A run that paused for review continues where it paused. A run the restart cut off mid-day is not resumed:
        its proposals stay as they were decided, and its model changes are in the stored version."""
        last: dict[str, Any] = {}
        for e in entries:
            if e.kind == LedgerKind.UPDATE and e.payload.get("update_id"):
                last[e.payload["update_id"]] = e
        paused = [e for e in last.values() if e.payload["state"] == "awaiting_review"]
        if not paused:
            return
        run = UpdateRun.model_validate(paused[-1].payload["run_state"])
        ctl.updates[run.id] = run
        ctl.active_update = run.id
        for day, ids in run.proposals.items():
            for pid in ids:
                ctl.proposals[pid].due_day = day
        if ctl.proposals[run.waiting_on].status not in (ProposalStatus.PENDING, ProposalStatus.DEFERRED):
            ctl.cycle.resume(run)           # it was decided just before the restart: go on from there

    def _replay(self, cfg: Any, storage: Any, entries: list, inputs: dict[str, str], rec: dict | None) -> RunnerStatus:
        """The construction files changed since the stored model was built (or it holds no record of them): rebuild
        from the files and fold the recorded import batches in again, in their order, each under the review policy it
        was imported under and with the decisions people recorded on it. The same bundles in the same order give the
        same model as before, on the new base. The old storage is kept beside the new one
        (`<storage>.before-<digest>`), so nothing is lost. If the new base asks for a decision nobody recorded, the
        replay stops with an error naming the item. A storage that another scenario built is only archived and
        rebuilt: its imports belong to a different world."""
        if rec is None or rec["scenario"] != self.script.id:
            entries = []                # another scenario's storage (or none recorded): nothing of it is replayed
        path = getattr(storage, "path", None)
        archive = None
        if path is not None:
            archive = Path(f"{path}.before-{(rec['digest'] if rec else 'unrecorded')[:10]}")
            storage.close()
            if archive.exists():
                shutil.rmtree(archive)
            shutil.copytree(path, archive)
        storage.reset()
        self._load_fresh(cfg, storage, inputs)
        ctl = self.controller
        was, ctl.auto_resume = ctl.auto_resume, True
        try:
            old = restore_proposals(entries)
            recorded = decisions(entries)
            by_key: dict[tuple, list] = {}
            for pid in sorted(old):
                by_key.setdefault((old[pid].market_event_id, str(old[pid].kind)), []).append(recorded.get(pid, []))
            batches = batch_entries(entries)
            for batch in batches:
                pl = batch.payload
                name = policy_at(entries, batch.seq) or DEFAULT_POLICY
                if name != ctl.config.review.policy:
                    ctl.set_review_policy(name, by="replay")
                bundle = ImportBundle(title=pl["title"], synthetic=pl["synthetic"],
                                      items=[ImportItem.model_validate(d) for d in pl["items"]])
                self.import_items(bundle)
                self._replay_decisions(ctl, pl["title"], by_key)
        finally:
            ctl.auto_resume = was
        final = policy_at(entries)
        if final and final != ctl.config.review.policy:
            ctl.set_review_policy(final, by="replay")
        for entry in self.import_log[:len(self.import_log) - bool(ctl.pending_proposals())]:
            entry["closed"] = True                  # their reviews are done: the status need not announce them again
        self.caption = (f"The construction files changed, so the model was rebuilt from them and "
                        f"{len(self.import_log)} import{'s' * (len(self.import_log) != 1)} replayed. "
                        f"The earlier version is kept as {archive.name if archive else 'a copy'}.")
        self._broadcast()
        return self.status()

    @staticmethod
    def _replay_decisions(ctl: WorldModelController, title: str, by_key: dict) -> None:
        """Apply the recorded decisions to the proposals the replay raised, in order. A proposal left undecided in the old
        model too stays pending, as it was (a run that does not pause leaves them; the last one may be a run paused for
        review). Raises when the new base raised a proposal the old one did not, or one that was applied by policy and
        now needs a person."""
        left: set[str] = set()
        while todo := [q for q in ctl.pending_proposals() if q.id not in left]:
            p = todo[0]
            key = (p.market_event_id, str(p.kind))
            n = [q.id for q in ctl.proposals.values() if (q.market_event_id, str(q.kind)) == key].index(p.id)
            todo = by_key.get(key, [])
            recs = todo[n] if n < len(todo) else None
            decided = recs is not None and any(e.payload["action"] in ("approved", "rejected") for e in recs)
            if recs is not None and not decided and not any(e.payload["action"] == "auto_applied" for e in recs):
                left.add(p.id)
                continue
            if not decided:
                raise ControllerError(f"replaying “{title}” on the new construction stopped at {p.id} "
                                      f"({p.market_event_id}): it now waits for a decision nobody recorded. "
                                      "Review it, or restore the earlier construction files.")
            for e in recs:
                pl = e.payload
                if pl["action"] == "edited":
                    ctl.edit(p.id, GraphUpdateEvent.model_validate(pl["diff"]["after"]), pl["by"])
                elif pl["action"] == "confidence":
                    after = pl["diff"]["after"]
                    ctl.set_confidence(p.id, after["confidence"], {int(i): v for i, v in after["ops"].items()},
                                       after["ripple"], by=pl["by"])
                elif pl["action"] == "approved":
                    ctl.approve(p.id, pl["by"], pl["note"])
                elif pl["action"] == "rejected":
                    ctl.reject(p.id, pl["by"], pl["note"] or "")
        return True

    def _adopt(self, ctl: WorldModelController, version: int, seq: int) -> None:
        self.controller = ctl
        self.world = None
        self.market_source = None
        self.user_events = {}
        # the scenario's ready-made questions (theses.yaml), offered in Predict's Ask tab
        self.theses_spec, _ = load_theses(self.scenario_dir)
        self.hypotheses_spec, self.decisions_spec = {}, {}
        self.init_version = version
        self.init_seq = seq
        self.init_info = {"history_events": 0, "version": version, "days": 0}
        self.step_index = 0
        self.state = "idle"
        self.forecasts_by_thesis, self.thesis_aliases, self.reports = {}, {}, []
        self.pending_step = None
        self.update_ids = []
        self.loaded = True
        self.error = None
        self.imported: dict[str, ImportItem] = {}     # market event id -> the item it came from
        self.import_skips: dict[str, dict[int, str]] = {}   # market event id -> signals not folded (intake/overlap.py)
        self.import_log: list[dict] = []
        self.batch_origin: dict[str, str] = {}      # update id -> the compartment whose login imported it (if any)
        ctl.import_context = self._import_context
        tr = StructuredTranslator(ctl.config, runner=self)
        for kind in MarketEventKind:
            ctl._translators[str(kind)] = [tr]

    def _import_context(self, market_event_id: str) -> ImportContext | None:
        """What the standards gate reads about an imported item (repo/review.py)."""
        item = self.imported.get(market_event_id)
        if item is None:
            return None
        others = {k: i for k, i in self.imported.items() if k != market_event_id}
        held = {others[eid].id: s for eid, s in self.import_skips.items() if eid in others}
        return ImportContext(item=item, folded=list(others.values()), held=held, origin=self._origin_map)

    # -- bundles -----------------------------------------------------------------------------------
    @staticmethod
    def parse(bundle: dict | ImportBundle) -> ImportBundle:
        if isinstance(bundle, ImportBundle):
            return bundle
        try:
            return ImportBundle.model_validate(bundle)
        except ValidationError as exc:
            first = exc.errors()[0]
            where = ".".join(str(x) for x in first["loc"])
            raise ControllerError(f"not an import bundle: {where}: {first['msg']}") from exc

    def narrow(self, bundle: dict | ImportBundle) -> dict | ImportBundle:
        """A focused scenario's import leaves out the items about removed companies and the signals on removed
        values (engine/focus.narrow_bundle); any other scenario's is unchanged."""
        focus = self.script.initialization.focus
        if focus is None:
            return bundle
        raw = bundle.model_dump(mode="json") if isinstance(bundle, ImportBundle) else bundle
        return focus_result(focus).narrow_bundle(raw)[0]

    @staticmethod
    def event_id(item: ImportItem) -> str:
        return f"IM-{item.id}"

    def _held(self) -> dict[str, dict[int, str]]:
        """Item id -> the signals of an imported item the overlapping-views guard held back."""
        return {self.imported[eid].id: s for eid, s in self.import_skips.items()}

    def local_bundles(self) -> list[dict]:
        """Bundles in the scenario's imports folder, when it exists on this server (a local checkout)."""
        folder = self.script.imports_dir
        if not folder:
            return []
        p = resolve_path(folder)
        if not p.is_dir():
            return []
        out = []
        for f in sorted(p.glob("*.json")):
            try:
                b = self.parse(json.loads(f.read_text()))
            except (ControllerError, ValueError):
                continue
            out.append({"name": f.name, "title": b.title, "items": len(b.items), "collected_by": b.collected_by})
        return out

    def local_bundle(self, name: str) -> dict:
        folder = self.script.imports_dir
        p = resolve_path(folder) / Path(name).name if folder else None
        if p is None or not p.is_file():
            raise ControllerError(f"no bundle {name!r} here")
        return json.loads(p.read_text())

    def preview(self, bundle: dict | ImportBundle) -> dict:
        """What importing would do, item by item: what each signal changes, what it cannot, and whether the item is
        already in, or older than the model's last processed day (it is then folded in late). Per-share values a split
        converts are listed under `conversions`; parts of overlapping views the guard holds back under `dropped`, with
        the overlaps found under `overlaps` (intake/overlap.py)."""
        b = self.parse(self.narrow(bundle))
        ctl = self.controller
        graph = ctl.engine.wm.graph
        done_day = ctl.engine.wm.deviations.date_of(int(ctl.engine.wm.last_processed_day))
        fresh = [i for i in b.items if self.event_id(i) not in self.imported]
        skips, overlaps = overlap_guard(graph, fresh, self.imported.values(), self._held())
        rows = []
        for item in sorted(b.items, key=lambda x: x.published_at):
            me = market_event_of(item, self.event_id(item), b.synthetic)
            done = me.id in self.imported
            res, dropped = translate_item(item, me, graph, self.import_skips.get(me.id) if done else skips.get(item.id))
            ops = res.events[0].ops if res.events else []
            status = "imported" if done else "late" if item.published_at.date() <= done_day else "new"
            conversions = [c for s in item.signals if (c := signal_conversion(s, graph, item.published_at))]
            rows.append({**item.model_dump(mode="json", exclude={"signals"}), "status": status,
                         "signals": len(item.signals), "changes": len(ops),
                         "change_kinds": sorted({op.op for op in ops}), "dropped": dropped,
                         "conversions": conversions})
        return {"title": b.title, "collected_by": b.collected_by,
                "collected_at": b.collected_at.isoformat() if b.collected_at else None,
                "description": b.description, "items": rows, "model_date": ctl.now.isoformat(),
                "overlaps": overlaps, "overlap_rule": OVERLAP_RULE}

    def import_items(self, bundle: dict | ImportBundle, ids: list[str] | None = None, *, origin: str | None = None) -> dict:
        """Fold the chosen items in, in date order, through one update run that pauses at each one's review. `origin` names
        the compartment whose login imports them; it is kept in the batch's ledger entry, so it survives a restart."""
        b = self.parse(self.narrow(bundle))
        with self.lock:
            ctl = self.controller
            if ctl.active_update and ctl.updates[ctl.active_update].state not in (UpdateState.DONE,
                                                                                  UpdateState.CANCELLED,
                                                                                  UpdateState.FAILED):
                raise ControllerError("an update is still running: finish its reviews first")
            chosen = [i for i in b.items if (ids is None or i.id in ids) and self.event_id(i) not in self.imported]
            if not chosen:
                raise ControllerError("nothing new to import")
            chosen.sort(key=lambda x: x.published_at)
            skips, overlaps = overlap_guard(ctl.engine.wm.graph, chosen, self.imported.values(), self._held())
            events = []
            for item in chosen:
                me = market_event_of(item, self.event_id(item), b.synthetic)
                self.imported[me.id] = item
                if item.id in skips:
                    self.import_skips[me.id] = skips[item.id]
                events.append(me)
            ctl.engine.ledger.append(LedgerKind.UPDATE, {
                "state": "import_batch", "title": b.title, "synthetic": b.synthetic,
                "items": [i.model_dump(mode="json") for i in chosen], "update_id": ctl.ids.peek("UPD"),
                "skips": {i.id: {str(k): v for k, v in skips[i.id].items()} for i in chosen if i.id in skips},
                "at": datetime.now(UTC).isoformat(), "origin": origin}, recorded_at=ctl.now)
            last = max(chosen[-1].published_at, ctl.now)
            # Oct 17: when every item is older than the model's last processed day, the run would have no day to
            # process and would end before collecting them; it runs through the next day instead, so they queue
            # onto it as late items (folded in late, each still reviewed) rather than being dropped
            wm = ctl.engine.wm
            lp = int(wm.last_processed_day)
            if wm.deviations.day_of(last) <= lp:
                last = datetime.combine(wm.deviations.date_of(lp + 1), datetime.max.time().replace(microsecond=0), UTC)
            # one rule: a run pauses for review only under a policy that reviews everything in order (review_all);
            # otherwise it goes on to the end and what needs a person waits as a pending proposal
            on_review = None if ctl.engine.components["review_policy"].pauses_run else "queue"
            run = ctl.request_update(UpdateRequest(requested_by="import", until=last.date(), requested_at=last,
                                                   user_market_events=events, sources=[], on_review=on_review),
                                     run_to_end=True)
            self.update_ids.append(run.id)
            if origin is not None:
                self.batch_origin[run.id] = origin
            if run.state == UpdateState.DONE:
                ctl.engine.save_snapshot()          # a finished import is a restart point: a resume replays few change sets
            self.import_log.append({"title": b.title, "items": [i.id for i in chosen], "update_id": run.id,
                                    "at": datetime.now(UTC).isoformat()})
            first, end = chosen[0].published_at, chosen[-1].published_at
            what = f"Imported {len(chosen)} item{'s' * (len(chosen) != 1)} from “{b.title}”, {first:%b %-d} to {end:%b %-d}."
            self.caption = (what + (" Each waits for your review, in date order." if on_review is None else
                                    f" {run.report.pending} wait{'s' * (run.report.pending == 1)} for your decision; "
                                    "the rest applied."))
            self._broadcast()
            return {"update_id": run.id, "imported": [i.id for i in chosen], "waiting_on": run.waiting_on,
                    "state": str(run.state), "overlaps": overlaps}

    # -- status ------------------------------------------------------------------------------------
    def status(self) -> RunnerStatus:
        ctl = self.controller
        if ctl is None:
            return super().status()
        run = ctl.updates.get(ctl.active_update) if ctl.active_update else None
        state = "awaiting_review" if ctl.pending_proposals() else (
            "running" if run is not None and run.state == UpdateState.RUNNING else "idle")
        # the last import's reviews are all done: say so, and point to what comes next
        last = self.import_log[-1] if self.import_log else None
        done = ctl.updates.get(last["update_id"]) if last else None
        if state == "idle" and done is not None and done.state == UpdateState.DONE and not last.get("closed"):
            last["closed"] = True
            ctl.engine.save_snapshot()
            report = done.report
            kept = f"{report.approved} approved, {report.rejected} rejected" if report else "all reviewed"
            self.caption = (f"Up to date through {ctl.now:%b %-d}: “{last['title']}” is in ({kept}). "
                            "Switch to Predict to ask what happens next.")
        return RunnerStatus(scenario_id=self.script.id, step_index=0, total_steps=0, sim_time=ctl.now, state=state,
                            update_id=ctl.active_update, pending_proposals=len(ctl.pending_proposals()),
                            caption=self.caption, version=ctl.engine.version, loaded=self.loaded, error=self.error,
                            canvas=self.canvas_kind, imports=True)


def load_bundle_file(path: str | Path) -> ImportBundle:
    return ImportRunner.parse(json.loads(Path(path).read_text()))


__all__ = ["ImportRunner", "load_bundle_file"]
