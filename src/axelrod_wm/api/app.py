"""The FastAPI app (§12): the browser demo at `/` and the API under `/api`."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import anyio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from axelrod_wm.control.controller import ControllerError
from axelrod_wm.events.graph_update import EventValidationError
from axelrod_wm.inference.decisions import DecisionError
from axelrod_wm.inference.task import UnboundThesis
from axelrod_wm.intake.translators import LLMNotConfigured
from axelrod_wm.repo.snapshots import RestoreError, StorageBackend
from axelrod_wm.sim.runner import ScenarioRunner, build_runner
from axelrod_wm.sim.scenario import REPO_ROOT
from axelrod_wm.trace import BroadcastTracer

T = TypeVar("T")

WEB_DIR = REPO_ROOT / "web"


# The demos the top bar's menu switches between (docs/guides/demos.md), in menu order: (scenario id, label, note).
DEMOS: list[tuple[str, str, str]] = [
    ("small_demo", "Small demo", "A blank canvas, built one example at a time"),
    ("prod_demo", "Production demo", "The same examples after three years of synthetic history"),
    ("oil_shock_demo", "Full demo", "The oil-shock scenario: 53 actors and ideas, 18 scripted steps"),
    ("emily_demo", "Emily's demo", "A PM's model brought up to date by importing research"),
    ("sally_demo", "Sally's demo", "Eleven names from daily research, with forecasts as context for agents"),
]
DEMO_IDS = {d[0] for d in DEMOS}


class AppState:
    """One process, one engine per login. Every engine call holds `lock` (§12.4).

    DECISION (demo menu): the engine keeps one runner per demo it has opened. Switching builds the new demo's runner
    in a worker thread, outside the lock, while the current one keeps serving; it then swaps in under the lock. A demo
    opened before is kept as it was left, with its own storage and trace stream."""

    def __init__(self, scenario: str, config_path: str | None, *, storage: StorageBackend | None = None,
                 trace_dir: str | Path | None = None, play_delay: float = 0.4,
                 cache_dir: str | Path | None = None) -> None:
        self.scenario = scenario
        self.first_scenario = scenario
        self.config_path = config_path
        self.storage = storage
        self.cache_dir = cache_dir
        self.trace_dir = trace_dir
        self.lock = threading.RLock()
        self.stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        self.tracers: dict[str, BroadcastTracer] = {}
        self.storages: dict[str, StorageBackend | None] = {scenario: storage}
        self.runners: dict[str, ScenarioRunner] = {}
        self.runner: ScenarioRunner | None = None
        self.interactive = True
        self.play_task: asyncio.Task | None = None
        self.update_task: asyncio.Task | None = None
        self.schedule_task: asyncio.Task | None = None
        self.switch_task: asyncio.Task | None = None
        self.switching: dict[str, Any] | None = None     # the switch under way, or the last one that failed
        self.play_requested = False             # /sim/play was pressed and not paused since
        # DECISION: play mode waits this long between steps so the canvas can animate each one
        self.play_delay = play_delay

    # -- each demo's trace stream and storage ------------------------------------------------------
    def tracer_for(self, scenario: str) -> BroadcastTracer:
        if scenario not in self.tracers:
            suffix = "" if scenario == self.first_scenario else f"-{scenario}"
            self.tracers[scenario] = BroadcastTracer(run_id=f"run-{self.stamp}{suffix}", directory=self.trace_dir)
        return self.tracers[scenario]

    @property
    def tracer(self) -> BroadcastTracer:
        return self.tracer_for(self.scenario)

    def storage_for(self, scenario: str) -> StorageBackend | None:
        """The first demo uses the storage it was given; another demo gets a sibling of it (files) or a fresh one of
        the same kind (memory), so no two demos write the same ledger."""
        if scenario not in self.storages:
            from axelrod_wm.repo.snapshots import FilesBackend

            base = self.storage
            if base is None:
                self.storages[scenario] = None
            elif isinstance(base, FilesBackend):
                self.storages[scenario] = FilesBackend(path=base.path.parent / f"{base.path.name}-{scenario}")
            else:
                self.storages[scenario] = type(base)()
        return self.storages[scenario]

    def new_runner(self, scenario: str, interactive: bool = True) -> ScenarioRunner:
        return build_runner(scenario, interactive=interactive, config_path=self.config_path,
                            storage=self.storage_for(scenario), tracer=self.tracer_for(scenario),
                            record_checklist=False, cache_dir=self.cache_dir)

    def build(self, scenario: str | None = None, interactive: bool = True) -> ScenarioRunner:
        self.scenario = scenario or self.scenario
        self.interactive = interactive
        self.runner = self.new_runner(self.scenario, interactive)
        self.runners[self.scenario] = self.runner
        return self.runner

    def _announce_switch(self, old: str, new: str) -> None:
        """Tell every page still streaming the old demo that this engine now serves another (they reload)."""
        if old != new and old in self.tracers:
            self.tracers[old].broadcast({"type": "switched", "scenario": new})

    def load(self, scenario: str | None = None, interactive: bool = True) -> Any:
        """Load (or reload, from its start) a demo, and make it the one served."""
        with self.lock:
            old = self.scenario
            target = scenario or self.scenario
            kept = self.runners.get(target)
            if kept is None or kept.interactive != interactive:
                self.build(target, interactive)
            else:
                self.scenario, self.runner, self.interactive = target, kept, interactive
            status = self.runner.load()
            # the API drives update runs itself, one day per lock acquisition (§12.4)
            self.runner.controller.auto_resume = False
            self.runner.progress = {"phase": "ready"}
            self._announce_switch(old, target)
            return status

    def reset_all(self) -> Any:
        """Every demo this login has opened back to its original state (Oct 15): the runners kept in memory are dropped
        (each demo is built fresh, from its initial snapshot, the next time it opens), and the login's first demo is
        rebuilt and served. Every page on this engine reloads."""
        with self.lock:
            if self.switch_task is not None and not self.switch_task.done():
                raise ControllerError("a demo is still opening: wait for it, then reset")
            old = self.scenario
            self.switching = None
            self.runners.clear()
            self.build(self.first_scenario, True)
            status = self.runner.load()
            self.runner.controller.auto_resume = False
            self.runner.progress = {"phase": "ready"}
            for tracer in self.tracers.values():
                tracer.broadcast({"type": "switched", "scenario": self.first_scenario, "reset": True, "from": old})
            return status

    # -- the demo menu: switch to another demo, building it on first use -----------------------------
    def demos(self) -> dict:
        """The demos this engine can serve: which is current, which are open in memory, which need their history
        replayed first (minutes), and the switch under way."""
        from axelrod_wm.sim.scenario import ScenarioScript

        out = []
        for sid, label, note in DEMOS:
            ready = sid in self.runners and self.runners[sid].loaded
            cold = False
            if not ready:
                try:
                    script = ScenarioScript.load(sid)
                    base = ScenarioScript.load(script.base) if script.base else script
                    if base.initialization.history is not None:
                        cache = Path(self.cache_dir) if self.cache_dir is not None else REPO_ROOT / "var" / base.id
                        cold = not (cache / "init_snapshot.json.gz").exists()
                except Exception:          # a demo whose files are missing is still listed; switching says why
                    pass
            out.append({"id": sid, "label": label, "note": note, "current": sid == self.scenario,
                        "ready": ready, "cold": cold})
        return {"current": self.scenario, "demos": out, "switching": self.switch_progress()}

    def switch_progress(self) -> dict | None:
        sw = self.switching
        if sw is None:
            return None
        out = {k: v for k, v in sw.items() if k not in ("runner", "t0")}
        if out.get("phase") not in ("done", "error"):
            prog = dict(getattr(sw.get("runner"), "progress", None) or {})
            out["phase"] = prog.get("phase") or out.get("phase", "starting")
            if out["phase"] == "replay" and prog.get("engine") is not None and prog.get("days"):
                day = int(getattr(prog["engine"].wm, "last_processed_day", -1)) + 1
                out["days"] = [day, int(prog["days"])]
                out["fraction"] = round(max(0.0, min(1.0, day / int(prog["days"]))), 3)
        out["elapsed_s"] = round(time.monotonic() - sw["t0"], 1)
        return out

    def prepare(self, scenario: str) -> ScenarioRunner:
        """Build and load a demo's runner (worker thread, outside the lock: the current demo keeps serving)."""
        kept = self.runners.get(scenario)
        if kept is not None and kept.loaded:
            return kept
        runner = self.new_runner(scenario, True)
        if self.switching is not None:
            self.switching["runner"] = runner
        runner.load()
        runner.controller.auto_resume = False
        runner.progress = {"phase": "ready"}
        with self.lock:
            self.runners[scenario] = runner
        return runner

    def activate(self, scenario: str) -> Any:
        """Serve a demo whose runner is prepared."""
        with self.lock:
            old = self.scenario
            self.scenario, self.runner, self.interactive = scenario, self.runners[scenario], True
            self._announce_switch(old, scenario)
            return self.runner.status()

    async def switch(self, scenario: str) -> dict:
        """Switch to a demo. One already open swaps in at once; another is built in the background, with its progress
        in `switching` (GET /api/demos), and swaps in when it is ready."""
        if scenario not in DEMO_IDS:
            raise KeyError(scenario)
        if scenario == self.scenario and self.runner is not None and self.runner.loaded:
            return self.demos()
        if self.switch_task is not None and not self.switch_task.done():
            if self.switching and self.switching.get("demo") == scenario:
                return self.demos()
            raise ControllerError(f"already opening {self.switching.get('demo') if self.switching else 'a demo'}")
        self.switching = {"demo": scenario, "phase": "starting", "t0": time.monotonic()}

        async def go() -> None:
            from axelrod_wm.api.routes import _stop_play

            try:
                await anyio.to_thread.run_sync(lambda: self.prepare(scenario))
                # what runs on the current demo stops first: play pauses, and an update run rests (it pauses at its
                # next review, or finishes)
                self.play_requested = False
                await _stop_play(self)
                if self.update_task is not None and not self.update_task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(self.update_task), timeout=120)
                    except TimeoutError:
                        pass
                await anyio.to_thread.run_sync(lambda: self.activate(scenario))
                self.switching = None
            except Exception as exc:               # reported by GET /api/demos; the current demo keeps serving
                sw = {k: v for k, v in (self.switching or {}).items() if k != "runner"}
                self.switching = {**sw, "phase": "error", "error": f"{type(exc).__name__}: {exc}"}

        ready = self.runners.get(scenario) is not None and self.runners[scenario].loaded
        self.switch_task = asyncio.create_task(go())
        if ready:
            await self.switch_task                 # already open: the swap is immediate
        else:
            await asyncio.sleep(0)
        return self.demos()

    def ensure_loaded(self) -> ScenarioRunner:
        with self.lock:
            if self.runner is None or not self.runner.loaded:
                self.load()
            return self.runner

    @property
    def controller(self) -> Any:
        return self.ensure_loaded().controller

    def locked(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        with self.lock:
            return fn(*args, **kwargs)

    async def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run an engine call in a worker thread, under the lock."""
        return await anyio.to_thread.run_sync(lambda: self.locked(fn, *args, **kwargs))

    # -- update runs in the background (§12.4) ---------------------------------------------
    def _one_day(self, run_id: str) -> str:
        from axelrod_wm.control.updates import UpdateState

        ctl = self.runner.controller
        run = ctl.updates.get(run_id)
        if run is None:                    # the model was reloaded (a rewind, a reset): nothing left to drive
            return "done"
        if run.state == UpdateState.RUNNING:
            try:
                ctl.cycle.run_days(run, max_days=1)
            except Exception as exc:
                ctl.cycle._fail(run, exc)
        if self.runner is not None:
            self.runner._broadcast()
        return str(run.state)

    async def drive(self, run_id: str) -> str:
        """Process an update run one day at a time, releasing the lock between days, until it is done
        or pauses for review. A scenario step waiting on the run then finishes its action."""
        runner = self.runner

        def mark(state: str) -> None:
            # the scenario's status follows its step's run: waiting on review, or running again
            if runner is not None and runner.pending_update() == run_id and runner.state != state:
                runner.state = state
                runner._broadcast()

        def defer_and_go_on() -> str:
            # DECISION: a non-interactive load (headless play through the API) defers what waits for
            # review and keeps going, as the headless runner does; deferred events can still fold in late
            run = self.runner.controller.updates.get(run_id)
            if run is None:
                return "done"
            self.runner.controller.cycle.resume(run, run_to_end=False)
            return str(run.state)

        await self.call(mark, "running")
        state = "running"
        while state == "running" or (state == "awaiting_review" and not self.interactive):
            if state == "awaiting_review":
                state = await self.call(defer_and_go_on)
                continue
            state = await self.call(self._one_day, run_id)
            await asyncio.sleep(0)
        if state == "awaiting_review":
            await self.call(mark, "awaiting_review")
        elif runner is not None and runner.pending_update() == run_id:
            await self.call(runner.step, False)
        return state

    def start_drive(self, run_id: str) -> None:
        """Drive a run in a background task; if play was requested, keep playing afterwards."""
        async def go() -> None:
            state = await self.drive(run_id)
            if state not in ("running", "awaiting_review") and self.play_requested and \
                    (self.play_task is None or self.play_task.done()):
                from axelrod_wm.api.routes import _play_loop

                self.play_task = asyncio.create_task(_play_loop(self, None))

        if self.update_task is not None and not self.update_task.done():
            return
        self.update_task = asyncio.create_task(go())


def _error(status: int, detail: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


async def _daily_schedule(state: AppState) -> None:
    """With update.auto_daily, request an update every day at update.daily_at in update.timezone
    (§7.8). A run that is still active (for example paused for review) skips that day's request."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo

    from axelrod_wm.control.updates import UpdateRequest

    cfg = state.runner.controller.config
    tz = ZoneInfo(cfg.update.timezone)
    hh, mm = (int(x) for x in cfg.update.daily_at.split(":"))
    while True:
        now = datetime.now(tz)
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        ctl = state.runner.controller
        if ctl.active_update is not None:
            continue

        def start(ctl=ctl, nxt=nxt) -> str:
            run = ctl.request_update(UpdateRequest(requested_by="schedule", until=nxt.date(),
                                                   requested_at=nxt.astimezone(UTC)), run_to_end=False)
            return run.id

        run_id = await state.call(start)
        state.start_drive(run_id)


def state_for(app: Any, scope: Any) -> AppState:
    """The engine a request's login opens (api/auth.py): its own, or the main one."""
    return app.state.axelrod_by_login.get(scope.get("axelrod_login"), app.state.axelrod)


def create_app(config_path: str | None = None, scenario: str = "oil_shock_demo", *,
               storage: StorageBackend | None = None, trace_dir: str | Path | None = "var/axelrod/traces",
               load_on_startup: bool = True, play_delay: float = 0.4,
               cache_dir: str | Path | None = None, start_example: str | None = None,
               lake_dir: str | Path | None = None) -> FastAPI:
    from axelrod_wm.api.auth import extra_logins
    from axelrod_wm.repo.snapshots import FilesBackend

    if storage is None:
        # DECISION: the demo server keeps its state under var/axelrod/demo, so it never overwrites the
        # session that `axelrod init` and `axelrod update` keep under var/axelrod.
        storage = FilesBackend(path=Path("var/axelrod/demo"))
    state = AppState(scenario, config_path, storage=storage, trace_dir=trace_dir, play_delay=play_delay,
                     cache_dir=cache_dir)
    # DECISION (Oct 11): a login from WORLD_MODEL_LOGINS gets an engine of its own, on its own scenario, storage, and
    # trace stream (api/auth.py), so Emily's login opens her demo while the main login keeps the shared demo. Each
    # engine is still one shared session for everyone who signs in with that login.
    by_login: dict[str, AppState] = {}
    for login in extra_logins():
        by_login[login.username] = AppState(
            login.scenario, config_path, storage=FilesBackend(path=Path(f"var/axelrod/demo-{login.username}")),
            trace_dir=Path(trace_dir) / login.username if trace_dir is not None else None, play_delay=play_delay,
            cache_dir=cache_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # the MCP server's session manager runs for the app's lifetime (api/mcp.py)
        async with app.state.mcp.session_manager.run():
            async with _engines(app):
                yield

    @asynccontextmanager
    async def _engines(app: FastAPI):
        if load_on_startup:
            await anyio.to_thread.run_sync(state.ensure_loaded)
            for other in by_login.values():
                await anyio.to_thread.run_sync(other.ensure_loaded)
            if start_example and hasattr(state.runner, "run_example"):
                # a demo opened at an example: the examples before it are played, and it waits for review
                await state.call(state.runner.run_example, start_example)
            cfg = state.runner.controller.config if state.runner is not None and state.runner.loaded else None
            if cfg is not None and cfg.update.auto_daily:
                state.schedule_task = asyncio.create_task(_daily_schedule(state))
        yield
        for st in (state, *by_login.values()):
            for task in (st.play_task, st.update_task, st.schedule_task):
                if task is not None and not task.done():
                    task.cancel()
            if st.runner is not None:
                st.runner.pause()

    app = FastAPI(title="Axelrod World Model", version="0.1.0", lifespan=lifespan)
    from axelrod_wm.api.auth import BasicAuthMiddleware

    app.add_middleware(BasicAuthMiddleware)
    # forecasts' views are large JSON with repeated keys; compressed, they arrive several times faster (Oct 15)
    from starlette.middleware.gzip import GZipMiddleware

    app.add_middleware(GZipMiddleware, minimum_size=2048, compresslevel=5)
    app.state.axelrod = state
    app.state.axelrod_by_login = by_login
    # the lakehouse and the ingestion pipeline behind the outward service (Oct 17): one store, partitioned by login
    from axelrod_wm.ingest.llm import provider_from_env
    from axelrod_wm.ingest.pipeline import Ingestor
    from axelrod_wm.lake.embed import LazyEmbedder
    from axelrod_wm.lake.sqlite import SQLiteLake

    app.state.lake = SQLiteLake(Path(lake_dir or os.environ.get("WORLD_MODEL_LAKE_DIR") or "var/lake"))
    app.state.ingestor = Ingestor(app.state.lake, LazyEmbedder(), provider=provider_from_env())

    @app.exception_handler(UnboundThesis)
    async def _unbound(request: Request, exc: UnboundThesis) -> JSONResponse:
        return JSONResponse(status_code=422, content={"unbound": exc.unbound})

    @app.exception_handler(KeyError)
    async def _missing(request: Request, exc: KeyError) -> JSONResponse:
        return _error(404, f"not found: {exc.args[0] if exc.args else exc}")

    @app.exception_handler(ControllerError)
    async def _controller(request: Request, exc: ControllerError) -> JSONResponse:
        return _error(409, str(exc))

    @app.exception_handler(DecisionError)
    async def _decision(request: Request, exc: DecisionError) -> JSONResponse:
        return _error(409, str(exc))

    @app.exception_handler(RestoreError)
    async def _restore(request: Request, exc: RestoreError) -> JSONResponse:
        return _error(404, str(exc))

    @app.exception_handler(EventValidationError)
    async def _invalid_event(request: Request, exc: EventValidationError) -> JSONResponse:
        return _error(422, str(exc))

    @app.exception_handler(ValidationError)
    async def _invalid(request: Request, exc: ValidationError) -> JSONResponse:
        return _error(422, exc.errors(include_url=False, include_context=False))

    @app.exception_handler(LLMNotConfigured)
    async def _llm(request: Request, exc: LLMNotConfigured) -> JSONResponse:
        return _error(501, str(exc))

    from axelrod_wm.api import v1
    from axelrod_wm.api.routes import router
    from axelrod_wm.api.ws import ws_router

    v1.install(app)
    app.include_router(router)
    from axelrod_wm.api.mcp import build_mcp, install_mcp

    app.state.mcp = build_mcp(app)
    install_mcp(app, app.state.mcp)
    app.include_router(ws_router)
    if WEB_DIR.exists():
        app.mount("/", _RevalidatedFiles(directory=WEB_DIR, html=True), name="web")
    return app


class _RevalidatedFiles(StaticFiles):
    """The demo's files, which the browser must revalidate on every load. DECISION: without this a browser can keep
    running an old module (ES modules are cached heuristically) after the code changes under a running demo."""

    def file_response(self, *args: Any, **kwargs: Any) -> Any:
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp
