"""A login's compartment, served as a view onto the main engine (Oct 25; world_model/docs/design/unified-model.md).

Each login used to open an engine of its own, so what one client's documents taught the model stayed with that client.
A login whose scenario is a focus over the main engine's scenario (`focus.base`) now opens a `ViewState` instead: the
same read surface as `AppState` (api/app.py), on the one engine. Every route family reads through it, so none has a
branch of its own for compartments:

- **Reads** (the browser's `/api/*`, `/v1` through the registry, search, `/mcp` through `/v1`, the WebSocket) call
  `view.controller.engine.wm` and `.ltm`, which are the main engine's state narrowed to the compartment
  (`narrow` and `narrow_ltm`, api/v1/compartments.py), rebuilt whenever the main engine commits. What the model holds
  outside the graph (hypotheses, forecasts, episodes, stored explanations, the ledger, the trace) is cut or kept apart,
  so nothing outside the compartment reaches an answer, an explanation, a graph payload, or an error.
- **Forecasts and theses** run on a `GraphOverlay` over the narrowed memory with `learn=False`, as a thesis does on
  any engine (inference/task.py). Their forecasts, theses, annotations, ledger, and trace are the view's own, in memory;
  nothing is written to the main engine's forecast layer.
- **Writes** go to the main engine, through the one writer: a document or bundle import narrows the bundle to the
  compartment (`FocusResult.narrow_bundle`), then the main runner imports it; the review decisions the login makes
  are on the proposals its own imports raised (and that name nothing outside), and are made on the main controller.
  Every other change (an edit, a structure change, a rewind, an update run, the review policy, a demo switch) is
  refused with a 409: the view's mutator is read-only.
- **The lake tenant** is the login's organization (`org_of`), as before.

One lock serves the main engine and every view, so a view read never sees a half-applied change."""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from axelrod_wm.api.v1.compartments import Compartment, narrow, narrow_ltm
from axelrod_wm.clients import find_scenario
from axelrod_wm.control.controller import ControllerError, WorldModelController
from axelrod_wm.control.updates import UpdateState
from axelrod_wm.engine.engine import Engine
from axelrod_wm.engine.focus import focus_result
from axelrod_wm.inference.task import InferenceTask
from axelrod_wm.memory.working import ForecastLayer, ForecastStateView
from axelrod_wm.repo.ledger import EventLedger
from axelrod_wm.repo.review import ProposalStatus
from axelrod_wm.repo.snapshots import MemoryBackend
from axelrod_wm.shared.process import SharedProcess
from axelrod_wm.sim.imports import ImportRunner
from axelrod_wm.sim.runner import RunnerStatus
from axelrod_wm.sim.scenario import ScenarioScript, load_theses
from axelrod_wm.trace import BroadcastTracer


class CompartmentError(ControllerError, AttributeError):
    """Something a compartment does not do: it reads and asks, and its changes go through the main engine's review.
    An AttributeError too, so a route that probes the runner (`getattr(runner, "x", None)`) sees it as absent."""


class ReadOnlyMutator:
    """A compartment's engine commits nothing: its memory is a narrowed copy of the main engine's."""

    def begin(self, *_a: Any, **_k: Any) -> Any:
        raise CompartmentError("a compartment cannot change the model directly: its changes are documents imported "
                               "into the unified model, and reviewed there")


class Versions:
    """The main engine's committed versions as a compartment may list them: the numbers, hashes, and times, with each
    cause cut to its kind (the part before `:`), which can name an item the compartment does not hold."""

    def __init__(self, storage: Any) -> None:
        self.storage = storage

    def versions(self) -> list[Any]:
        return [v.model_copy(update={"cause": v.cause.partition(":")[0]}) for v in self.storage.versions()]

    def __getattr__(self, name: str) -> Any:
        raise CompartmentError(f"{name}: the commit storage of the unified model is not open to a compartment")


class Snapshots:
    """The main engine's snapshots, restored narrowed."""

    def __init__(self, engine: NarrowedEngine) -> None:
        self.engine = engine

    @property
    def storage(self) -> Versions:
        return Versions(self.engine.main.snapshots.storage)

    def version_info(self, version: int | None = None) -> Any:
        info = self.engine.main.snapshots.version_info(version)
        return None if info is None else info.model_copy(update={"cause": info.cause.partition(":")[0]})

    def restore(self, version: int) -> tuple[Any, Any]:
        return self.engine.narrowed(*self.engine.main.snapshots.restore(version))


class ViewInference(InferenceTask):
    """Inference on a compartment: the forecast layer it writes is the view's own."""

    def update_state(self, thesis: Any, forecast: Any, explanation: Any, ctx: Any) -> None:
        layer = self.engine.layer
        layer.by_thesis[thesis.id] = ForecastStateView(thesis_id=thesis.id, forecast=forecast, explanation=explanation,
                                                       thesis=thesis.model_dump(mode="json"))
        layer.pose_counts[thesis.id] = layer.pose_counts.get(thesis.id, 0) + 1
        layer.order = [t for t in layer.order if t != thesis.id] + [thesis.id]
        if thesis.pinned:
            layer.pinned = set(layer.pinned) | {thesis.id}


class NarrowedEngine:
    """The main engine as a compartment sees it: `wm` and `ltm` narrowed (and rebuilt when the main engine commits),
    its own forecast layer, ledger, and tracer, and no mutator. Everything else (configuration, components, version,
    state hash, vocabulary) is the main engine's."""

    def __init__(self, main: Engine, comp: Compartment, tracer: Any, lock: Any) -> None:
        self.main = main
        self.comp = comp
        self.lock = lock
        self.tracer = tracer
        self.layer = ForecastLayer()
        self.mutator = ReadOnlyMutator()
        self.snapshots = Snapshots(self)
        self.storage = self.snapshots.storage
        self.ledger = EventLedger(MemoryBackend(), clock=lambda: self.wm.clock, version=lambda: self.main.version)
        shared = main.shared
        self.shared = SharedProcess(self, parser=shared.parser, classifier=shared.classifier, recaller=shared.recaller,
                                    inducer=shared.inducer, prefiller=shared.prefiller, analyzer=shared.analyzer)
        self.inference = ViewInference(self)
        self._cache: tuple[tuple, Any, Any] | None = None

    def narrowed(self, wm: Any, ltm: Any) -> tuple[Any, Any]:
        wm = narrow(wm, self.comp)
        return wm, narrow_ltm(ltm, self.comp, wm)

    def _state(self) -> tuple[Any, Any]:
        main = self.main
        key = (id(main.wm), id(main.ltm), main.ledger.next_seq)
        if self._cache is None or self._cache[0] != key:
            with self.lock:                      # narrow a state no other thread is changing
                wm, ltm = self.narrowed(main.wm, main.ltm)
                self._cache = (key, wm.model_copy(update={"forecast_layer": self.layer}), ltm)
        return self._cache[1], self._cache[2]

    @property
    def wm(self) -> Any:
        return self._state()[0]

    @property
    def ltm(self) -> Any:
        return self._state()[1]

    def context(self, *, learn: bool, now: datetime, processing_day: int | None = None) -> Any:
        return Engine.context(self, learn=learn, now=now, processing_day=processing_day)   # type: ignore[arg-type]

    def restore(self, version: int) -> tuple[Any, Any]:
        return self.snapshots.restore(version)

    def __getattr__(self, name: str) -> Any:
        if name in ("learning", "structural"):
            raise CompartmentError("a compartment does not learn: the unified model learns from what is imported into it")
        return getattr(self.main, name)


class OwnController(WorldModelController):
    """The part of a compartment's controller that is its own: forecasts, theses, annotations, decisions. Simulated
    time is the main controller's."""

    def __init__(self, engine: NarrowedEngine, main: WorldModelController, **kw: Any) -> None:
        self.main = main
        super().__init__(engine, **kw)

    @property
    def now(self) -> datetime:
        return self.main.now

    @now.setter
    def now(self, _value: datetime) -> None:
        return None


class ViewController:
    """The controller a compartment's routes call: forecasts, theses, and views on the narrowed state are its own
    (`own`); the review surface is the main controller's, limited to what the view's imports raised and that names
    nothing outside the compartment."""

    def __init__(self, view: ViewState, engine: NarrowedEngine) -> None:
        self.view = view
        self.own = OwnController(engine, view.main_controller(), scenario_dir=view.scenario_dir())

    @property
    def main(self) -> WorldModelController:
        return self.view.main_controller()

    @property
    def engine(self) -> NarrowedEngine:
        return self.own.engine

    def __getattr__(self, name: str) -> Any:
        return getattr(self.own, name)

    # -- what the view started on the main engine -----------------------------------------------------------------
    def mine(self, p: Any) -> bool:
        return p.update_id in self.view.runs and not self.view.focus_result().leaks(p.model_dump(mode="json"))

    def proposal(self, proposal_id: str) -> Any:
        p = self.main.proposals.get(proposal_id)
        if p is None or not self.mine(p):
            raise ControllerError(f"unknown proposal {proposal_id}")
        return p

    @property
    def proposals(self) -> dict[str, Any]:
        return {k: p for k, p in self.main.proposals.items() if self.mine(p)}

    def pending_proposals(self) -> list[Any]:
        return [p for p in self.proposals.values() if p.status == ProposalStatus.PENDING and p.needs_review]

    @property
    def updates(self) -> dict[str, Any]:
        return {k: r for k, r in self.main.updates.items() if k in self.view.runs}

    @property
    def active_update(self) -> str | None:
        return self.main.active_update if self.main.active_update in self.view.runs else None

    @property
    def market_events(self) -> dict[str, Any]:
        return {k: e for k, e in self.main.market_events.items() if e.update_id in self.view.runs}

    @property
    def market_status(self) -> dict[str, str]:
        return {k: v for k, v in self.main.market_status.items() if k in self.market_events}

    @property
    def translations(self) -> dict[str, Any]:
        return {k: v for k, v in self.main.translations.items() if k in self.market_events}

    @property
    def cycle(self) -> Any:
        return self.main.cycle

    def get_update(self, update_id: str) -> Any:
        if update_id not in self.view.runs:
            raise ControllerError(f"unknown update {update_id}")
        return self.main.get_update(update_id)

    # -- the review decisions, made on the main engine -------------------------------------------------------------
    def approve(self, proposal_id: str, *args: Any, **kw: Any) -> Any:
        self.proposal(proposal_id)
        return self.main.approve(proposal_id, *args, **kw)

    def reject(self, proposal_id: str, *args: Any, **kw: Any) -> Any:
        self.proposal(proposal_id)
        return self.main.reject(proposal_id, *args, **kw)

    def defer(self, proposal_id: str, *args: Any, **kw: Any) -> Any:
        self.proposal(proposal_id)
        return self.main.defer(proposal_id, *args, **kw)

    def edit(self, proposal_id: str, *args: Any, **kw: Any) -> Any:
        self.proposal(proposal_id)
        return self.main.edit(proposal_id, *args, **kw)

    def set_confidence(self, proposal_id: str, *args: Any, **kw: Any) -> Any:
        self.proposal(proposal_id)
        return self.main.set_confidence(proposal_id, *args, **kw)

    def continue_update(self, update_id: str) -> Any:
        self.get_update(update_id)
        return self.main.continue_update(update_id)

    def cancel_update(self, update_id: str) -> Any:
        self.get_update(update_id)
        return self.main.cancel_update(update_id)

    # -- what a compartment does not do -----------------------------------------------------------------------------
    def evaluate(self, *_a: Any, **_k: Any) -> Any:
        raise CompartmentError("a backtest runs on the whole unified model, not on a compartment")

    def set_review_policy(self, *_a: Any, **_k: Any) -> Any:
        raise CompartmentError("the review policy belongs to the unified model")


class ViewRunner:
    """The runner a compartment's routes call: what the loaded scenario is (its title, ready-made questions, import
    state), the status the top bar shows, and the imports, which the main runner takes after narrowing the bundle.
    Anything else a runner does (steps, play, examples, library, reset) is refused."""

    loaded = True
    state = "idle"
    step_index = 0
    error: str | None = None
    playing = False
    market_source = None
    hypotheses_spec: dict = {}
    decisions_spec: dict = {}
    event_id = staticmethod(ImportRunner.event_id)

    def __init__(self, view: ViewState) -> None:
        self.view = view
        self.reports: list = []
        self._pause = threading.Event()
        self._script: ScenarioScript | None = None

    @property
    def controller(self) -> ViewController:
        return self.view.controller

    @property
    def script(self) -> ScenarioScript:
        """The compartment's scenario, without the base's drawn layout (it places every entity of the whole model)."""
        if self._script is None:
            script = ScenarioScript.load(self.view.focus.id)
            ini = script.initialization.model_copy(update={"layout": None})
            self._script = script.model_copy(update={"initialization": ini})
        return self._script

    @property
    def scenario_dir(self) -> Any:
        return self.view.scenario_dir()

    @property
    def theses_spec(self) -> dict:
        return load_theses(self.scenario_dir)[0]

    @property
    def imported(self) -> dict:
        mine = self.controller.market_events
        return {k: v for k, v in self.view.unified_runner().imported.items() if k in mine}

    def pending_update(self) -> None:
        return None

    def status(self) -> RunnerStatus:
        ctl = self.controller
        pending = ctl.pending_proposals()
        run = ctl.updates.get(ctl.active_update) if ctl.active_update else None
        state = "awaiting_review" if pending else (
            "running" if run is not None and run.state == UpdateState.RUNNING else "idle")
        main = self.view.main_controller()
        return RunnerStatus(scenario_id=self.view.focus.id, step_index=0, total_steps=0, sim_time=main.now, state=state,
                            update_id=ctl.active_update, pending_proposals=len(pending),
                            caption=f"Your compartment of the world model, as of {main.now:%b %-d, %Y}.",
                            version=main.engine.version, loaded=True, error=None, canvas="seeded", imports=True)

    def _broadcast(self) -> None:
        self.view.tracer.broadcast({"type": "status", "status": self.status().model_dump(mode="json")})

    def pause(self) -> RunnerStatus:
        return self.status()

    # -- imports: the bundle narrowed to the compartment, then the main runner's -------------------------------------
    def local_bundles(self) -> list[dict]:
        return []

    def local_bundle(self, name: str) -> dict:
        raise ControllerError(f"no bundle {name!r} here")

    def narrow(self, bundle: Any) -> dict:
        raw = bundle if isinstance(bundle, dict) else bundle.model_dump(mode="json")
        return self.view.focus_result().narrow_bundle(raw)[0]

    def preview(self, bundle: Any) -> dict:
        out = self.view.unified_runner().preview(self.narrow(bundle))
        return {**out, "overlaps": [w for w in out["overlaps"] if not self.view.focus_result().leaks(w)]}

    def import_items(self, bundle: Any, ids: list[str] | None = None) -> dict:
        out = self.view.unified_runner().import_items(self.narrow(bundle), ids)
        self.view.runs.add(out["update_id"])
        return {**out, "overlaps": [w for w in out["overlaps"] if not self.view.focus_result().leaks(w)]}

    def __getattr__(self, name: str) -> Any:
        raise CompartmentError(f"{name}: a compartment cannot do this; it reads and asks the unified model")


class ViewState:
    """One login's compartment: the surface of `AppState` (api/app.py) on the main engine, narrowed. See the module."""

    is_view = True

    def __init__(self, main: Any, comp: Compartment, login: str, org: str) -> None:
        self.main = main
        self.focus = comp
        self.login = login
        self.org = org
        self.scenario = self.first_scenario = comp.id
        self.runs: set[str] = set()                 # the update runs this view's imports started on the main engine
        self.tracer = BroadcastTracer(run_id=f"view-{login}")
        self.interactive = True
        self.play_task = self.update_task = self.schedule_task = self.switch_task = None
        self.play_requested = False
        self.switching = None
        self._engine: Engine | None = None
        self._controller: ViewController | None = None
        self._runner = ViewRunner(self)

    # -- the compartment and the main engine ------------------------------------------------------------------------
    def focus_result(self) -> Any:
        return focus_result(self.focus.spec)

    def scenario_dir(self) -> Any:
        return find_scenario(self.focus.id)

    @property
    def lock(self) -> Any:
        return self.main.lock

    @property
    def play_delay(self) -> float:
        return self.main.play_delay

    def unified_runner(self) -> Any:
        """The main engine's own scenario (the one the compartments are over), whichever demo its login has open."""
        runner = self.main.runners.get(self.main.first_scenario)
        if runner is None or not runner.loaded:
            self.main.ensure_loaded()
            runner = self.main.runners[self.main.first_scenario]
        return runner

    def main_controller(self) -> WorldModelController:
        return self.unified_runner().controller

    # -- the surface AppState has ------------------------------------------------------------------------------------
    def ensure_loaded(self) -> ViewRunner:
        engine = self.main_controller().engine
        if self._engine is not engine:            # the main engine was rebuilt (a reset): the view starts again with it
            with self.main.lock:                  # the controller reads the narrowed state once, as it is built
                self._controller = ViewController(self, NarrowedEngine(engine, self.focus, self.tracer, self.main.lock))
                self._engine = engine
                self.runs.clear()
        return self._runner

    @property
    def runner(self) -> ViewRunner:
        return self.ensure_loaded()

    @property
    def controller(self) -> ViewController:
        self.ensure_loaded()
        assert self._controller is not None
        return self._controller

    def locked(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return self.main.locked(fn, *args, **kwargs)

    async def call(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        return await self.main.call(fn, *args, **kwargs)

    def start_drive(self, run_id: str) -> None:
        self.main.start_drive(run_id)

    async def drive(self, run_id: str) -> str:
        return await self.main.drive(run_id)

    def demos(self) -> dict:
        """The one demo a compartment has: itself. The whole model and the other demos are not on its menu."""
        label, _, note = self.focus.title.partition(": ")
        return {"current": self.focus.id, "demos": [{"id": self.focus.id, "label": label, "note": note, "current": True,
                                                     "ready": True, "cold": False}], "switching": None}

    def scenarios(self) -> list[dict]:
        script = self.runner.script
        return [{"id": script.id, "title": script.title, "canvas": script.canvas, "examples": None, "imports": True}]

    async def switch(self, scenario: str) -> dict:
        raise KeyError(scenario)

    def load(self, *_a: Any, **_k: Any) -> Any:
        raise CompartmentError("a compartment's world is its own focus of the unified model: there is nothing to load")

    reset_all = load

    def require_main(self, what: str) -> None:
        raise CompartmentError(f"{what} is for the unified model, not a compartment")
