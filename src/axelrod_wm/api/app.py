"""The FastAPI app (§12): the browser demo at `/` and the API under `/api`."""

from __future__ import annotations

import asyncio
import threading
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
from axelrod_wm.control.decisions import DecisionError
from axelrod_wm.engine.performance.task import UnboundThesis
from axelrod_wm.events.graph_update import EventValidationError
from axelrod_wm.ingest.translators import LLMNotConfigured
from axelrod_wm.memory.snapshots import RestoreError, StorageBackend
from axelrod_wm.sim.runner import ScenarioRunner, build_runner
from axelrod_wm.sim.scenario import REPO_ROOT
from axelrod_wm.trace import BroadcastTracer

T = TypeVar("T")

WEB_DIR = REPO_ROOT / "web"


class AppState:
    """One process, one engine. Every engine call holds `lock` (§12.4)."""

    def __init__(self, scenario: str, config_path: str | None, *, storage: StorageBackend | None = None,
                 trace_dir: str | Path | None = None, play_delay: float = 0.4,
                 cache_dir: str | Path | None = None) -> None:
        self.scenario = scenario
        self.config_path = config_path
        self.storage = storage
        self.cache_dir = cache_dir
        self.lock = threading.RLock()
        self.tracer = BroadcastTracer(run_id=f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
                                      directory=trace_dir)
        self.runner: ScenarioRunner | None = None
        self.interactive = True
        self.play_task: asyncio.Task | None = None
        self.update_task: asyncio.Task | None = None
        self.schedule_task: asyncio.Task | None = None
        self.play_requested = False             # /sim/play was pressed and not paused since
        # DECISION: play mode waits this long between steps so the canvas can animate each one
        self.play_delay = play_delay

    def build(self, scenario: str | None = None, interactive: bool = True) -> ScenarioRunner:
        self.scenario = scenario or self.scenario
        self.interactive = interactive
        self.runner = build_runner(self.scenario, interactive=interactive, config_path=self.config_path,
                                   storage=self.storage, tracer=self.tracer, record_checklist=False,
                                   cache_dir=self.cache_dir)
        return self.runner

    def load(self, scenario: str | None = None, interactive: bool = True) -> Any:
        with self.lock:
            if self.runner is None or (scenario and scenario != self.scenario) or interactive != self.interactive:
                self.build(scenario, interactive)
            status = self.runner.load()
            # the API drives update runs itself, one day per lock acquisition (§12.4)
            self.runner.controller.auto_resume = False
            return status

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
        run = ctl.get_update(run_id)
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

        await self.call(mark, "running")
        state = "running"
        while state == "running":
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


def create_app(config_path: str | None = None, scenario: str = "oil_shock_demo", *,
               storage: StorageBackend | None = None, trace_dir: str | Path | None = "var/axelrod/traces",
               load_on_startup: bool = True, play_delay: float = 0.4,
               cache_dir: str | Path | None = None) -> FastAPI:
    if storage is None:
        # DECISION: the demo server keeps its state under var/axelrod/demo, so it never overwrites the
        # session that `axelrod init` and `axelrod update` keep under var/axelrod.
        from axelrod_wm.memory.snapshots import FilesBackend

        storage = FilesBackend(path=Path("var/axelrod/demo"))
    state = AppState(scenario, config_path, storage=storage, trace_dir=trace_dir, play_delay=play_delay,
                     cache_dir=cache_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if load_on_startup:
            await anyio.to_thread.run_sync(state.ensure_loaded)
            cfg = state.runner.controller.config if state.runner is not None and state.runner.loaded else None
            if cfg is not None and cfg.update.auto_daily:
                state.schedule_task = asyncio.create_task(_daily_schedule(state))
        yield
        for task in (state.play_task, state.update_task, state.schedule_task):
            if task is not None and not task.done():
                task.cancel()
        if state.runner is not None:
            state.runner.pause()

    app = FastAPI(title="Axelrod World Model", version="0.1.0", lifespan=lifespan)
    from axelrod_wm.api.auth import BasicAuthMiddleware

    app.add_middleware(BasicAuthMiddleware)
    app.state.axelrod = state

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

    from axelrod_wm.api.routes import router
    from axelrod_wm.api.ws import ws_router

    app.include_router(router)
    app.include_router(ws_router)
    if WEB_DIR.exists():
        app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app
