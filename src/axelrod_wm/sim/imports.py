"""A world model fed by imports (Oct 11): the ordinary way a client uses the product.

The model starts seeded with the client's view of their world (construction files and superentities, no synthetic
history). New information arrives as an import bundle (intake/bundle.py): dated items a research agent has already
read and categorized. Importing folds each selected item in on its own date, through one update run that pauses at
each item's review; nothing changes the model until a person approves it. Predict then forecasts on what was
approved.

Any scenario with `imports: true` uses this runner (data/scenarios/emily_demo). Bundles come from the person's own
file (the Import dialog's file picker) or, when the scenario names an `imports_dir` that exists on the server, from
that folder; the folder is never committed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from pathlib import Path

from pydantic import ValidationError

from axelrod_wm.control.controller import ControllerError, WorldModelController
from axelrod_wm.control.updates import UpdateRequest, UpdateState
from axelrod_wm.engine.engine import build_engine, make_storage
from axelrod_wm.engine.initialize import (
    ConstructionSpec,
    Initializer,
    SeedFile,
    load_vocabulary,
    resolve_path,
)
from axelrod_wm.events.market import MarketEventKind
from axelrod_wm.intake.bundle import (
    ImportBundle,
    ImportItem,
    StructuredTranslator,
    market_event_of,
    translate_item,
)
from axelrod_wm.sim.runner import RunnerStatus, ScenarioRunner
from axelrod_wm.sim.scenario import load_theses
from axelrod_wm.trace import Phase


class ImportRunner(ScenarioRunner):
    canvas_kind = "seeded"

    def load(self) -> RunnerStatus:
        with self.lock:
            cfg = self.effective_config()
            ini = self.script.initialization
            storage = self.storage if self.storage is not None else make_storage(cfg)
            storage.reset()
            vocab = load_vocabulary(ini.taxonomy_dir)
            eng = build_engine(cfg, storage, self.tracer, vocab=vocab)
            init = Initializer(eng)
            init.construct(ConstructionSpec.load(ini.construction_dir, ini.taxonomy_dir), ini.taxonomy_dir,
                           start=self.script.start, vocab=vocab)
            if ini.seeds:
                init.load_seeds(SeedFile.load(ini.seeds), now=eng.wm.clock)
            eng.save_snapshot()
            ctl = WorldModelController(eng, scenario_dir=self.scenario_dir)
            ctl.set_review_policy("review_all")
            self._adopt(ctl, eng.version, eng.ledger.next_seq - 1)
            ctl.advance_now(datetime.combine(self.script.start, time(0), tzinfo=UTC))
            self.caption = ("Your world model, as of " + f"{self.script.start:%b %-d, %Y}" +
                            ". Import research to bring it up to date: each item waits for your review.")
            self.tracer.emit(Phase.INIT, "scenario.loaded", refs=[self.script.id], scenario_id=self.script.id,
                             version=eng.version, steps=0)
            self._broadcast()
            return self.status()

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
        self.import_log: list[dict] = []
        tr = StructuredTranslator(ctl.config, runner=self)
        for kind in MarketEventKind:
            ctl._translators[str(kind)] = [tr]

    def resume(self, session: dict) -> RunnerStatus:
        raise ControllerError("an imported model is not kept between sessions; load it again")

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

    @staticmethod
    def event_id(item: ImportItem) -> str:
        return f"IM-{item.id}"

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
        already in, or older than the model's last processed day (it is then folded in late)."""
        b = self.parse(bundle)
        ctl = self.controller
        graph = ctl.engine.wm.graph
        done_day = ctl.engine.wm.deviations.date_of(int(ctl.engine.wm.last_processed_day))
        rows = []
        for item in sorted(b.items, key=lambda x: x.published_at):
            me = market_event_of(item, self.event_id(item))
            res, dropped = translate_item(item, me, graph)
            ops = res.events[0].ops if res.events else []
            status = "imported" if me.id in self.imported else "late" if item.published_at.date() <= done_day else "new"
            rows.append({**item.model_dump(mode="json", exclude={"signals"}), "status": status,
                         "signals": len(item.signals), "changes": len(ops),
                         "change_kinds": sorted({op.op for op in ops}), "dropped": dropped})
        return {"title": b.title, "collected_by": b.collected_by,
                "collected_at": b.collected_at.isoformat() if b.collected_at else None,
                "description": b.description, "items": rows, "model_date": ctl.now.isoformat()}

    def import_items(self, bundle: dict | ImportBundle, ids: list[str] | None = None) -> dict:
        """Fold the chosen items in, in date order, through one update run that pauses at each one's review."""
        b = self.parse(bundle)
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
            events = []
            for item in chosen:
                me = market_event_of(item, self.event_id(item))
                self.imported[me.id] = item
                events.append(me)
            last = max(chosen[-1].published_at, ctl.now)
            run = ctl.request_update(UpdateRequest(requested_by="import", until=last.date(), requested_at=last,
                                                   user_market_events=events, sources=[]), run_to_end=True)
            self.update_ids.append(run.id)
            self.import_log.append({"title": b.title, "items": [i.id for i in chosen], "update_id": run.id,
                                    "at": datetime.now(UTC).isoformat()})
            first, end = chosen[0].published_at, chosen[-1].published_at
            self.caption = (f"Imported {len(chosen)} item{'s' * (len(chosen) != 1)} from “{b.title}”, "
                            f"{first:%b %-d} to {end:%b %-d}. Each waits for your review, in date order.")
            self._broadcast()
            return {"update_id": run.id, "imported": [i.id for i in chosen], "waiting_on": run.waiting_on,
                    "state": str(run.state)}

    # -- status ------------------------------------------------------------------------------------
    def status(self) -> RunnerStatus:
        ctl = self.controller
        if ctl is None:
            return super().status()
        run = ctl.updates.get(ctl.active_update) if ctl.active_update else None
        state = "awaiting_review" if ctl.pending_proposals() else (
            "running" if run is not None and run.state == UpdateState.RUNNING else "idle")
        return RunnerStatus(scenario_id=self.script.id, step_index=0, total_steps=0, sim_time=ctl.now, state=state,
                            update_id=ctl.active_update, pending_proposals=len(ctl.pending_proposals()),
                            caption=self.caption, version=ctl.engine.version, loaded=self.loaded, error=self.error,
                            canvas=self.canvas_kind, imports=True)


def load_bundle_file(path: str | Path) -> ImportBundle:
    return ImportRunner.parse(json.loads(Path(path).read_text()))


__all__ = ["ImportRunner", "load_bundle_file"]
