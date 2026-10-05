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
            return self.runner.load()

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


def _error(status: int, detail: Any) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


def create_app(config_path: str | None = None, scenario: str = "oil_shock_demo", *,
               storage: StorageBackend | None = None, trace_dir: str | Path | None = "var/axelrod/traces",
               load_on_startup: bool = True, play_delay: float = 0.4,
               cache_dir: str | Path | None = None) -> FastAPI:
    state = AppState(scenario, config_path, storage=storage, trace_dir=trace_dir, play_delay=play_delay,
                     cache_dir=cache_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if load_on_startup:
            await anyio.to_thread.run_sync(state.ensure_loaded)
        yield
        if state.play_task is not None:
            if state.runner is not None:
                state.runner.pause()
            state.play_task.cancel()

    app = FastAPI(title="Axelrod World Model", version="0.1.0", lifespan=lifespan)
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
