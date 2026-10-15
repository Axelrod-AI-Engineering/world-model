"""The scenario runner (§11.3): load (with a cached init snapshot), step, play, pause, reset.

A step with `update` requests an update run (§7.8) with `until` = the date of `at` and
`requested_at` = `at`; the mock scraper and the synthetic data feed find the step's news and data
on their own, and the world advances as the data feed is polled. When the update finishes, the
step runs its action (a thesis, an evaluation, a decision, ...).

# DECISION: initialization is built once in a files backend under var/<scenario>/init and cached
# with its snapshot (init_snapshot.json.gz), keyed by the specs, config, code, and seed. A files
# session copies the history's ledger, versions, and snapshots, so every version stays restorable;
# a memory session (tests, headless runs) starts from the init snapshot and numbers its ledger after
# the history's entries, so versions before the init snapshot cannot be restored there.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from axelrod_wm.control.controller import WorldModelController
from axelrod_wm.control.updates import UpdateRequest, UpdateState
from axelrod_wm.engine.config import EngineConfig, load_config
from axelrod_wm.engine.engine import build_engine, make_storage
from axelrod_wm.engine.initialize import (
    REPO_ROOT,
    ConstructionSpec,
    Initializer,
    SeedFile,
    load_vocabulary,
    resolve_path,
)
from axelrod_wm.evaluation.backtest import EvaluationRequest
from axelrod_wm.events.graph_update import GraphUpdateEvent
from axelrod_wm.events.market import MarketEventChannel
from axelrod_wm.intake.scrapers import MockWebScraper
from axelrod_wm.intake.sources import HistoryReplaySource, JsonlReplaySource
from axelrod_wm.model.hypothesis import Hypothesis
from axelrod_wm.model.serialization import canonical_json, sha256_text
from axelrod_wm.repo.snapshots import FilesBackend, StateVersion, StorageBackend, load_state
from axelrod_wm.sim.scenario import (
    ScenarioScript,
    load_decisions,
    load_theses,
    load_user_events,
    thesis_from_spec,
)
from axelrod_wm.sim.world import SyntheticDataFeed, SyntheticWorld, TruthSpec
from axelrod_wm.trace import NullTracer, Phase, Tracer

INIT_FORMAT = 4


class RunnerStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    step_index: int
    total_steps: int
    sim_time: datetime
    state: Literal["idle", "running", "awaiting_review", "done"]
    update_id: str | None = None          # the active update run, if any
    pending_proposals: int
    caption: str | None = None
    version: int = 0
    loaded: bool = False
    error: str | None = None
    next_step_at: datetime | None = None  # the next scripted step: the Update dialog's default "until"
    canvas: str = "scripted"              # "blank" for the small demo's empty canvas
    examples: str | None = None           # a demo with examples ("small", "prod"): the UI shows Tutorial, not Step
    imports: bool = False                 # a model fed by import bundles: the UI shows Import (sim/imports.py)


class StepReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int
    at: datetime
    update_id: str | None
    market_event_ids: list[str]
    proposal_ids: list[str]
    forecast_ids: list[str]
    caption: str | None = None
    notes: list[str] = []


def _hash_files(paths: list[Path], skip: tuple[str, ...] = ()) -> str:
    parts = []
    for p in sorted(paths):
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts and not any(k in f.parts for k in skip):
                    rel = f.relative_to(REPO_ROOT) if f.is_relative_to(REPO_ROOT) else f
                    parts.append(f"{rel}:{sha256_text(f.read_text())}")
        elif p.exists():
            parts.append(f"{p.name}:{sha256_text(p.read_text())}")
    return sha256_text("\n".join(parts))


class ScenarioRunner:
    def __init__(self, controller: WorldModelController | None, world: SyntheticWorld | None, script: ScenarioScript,
                 interactive: bool, *, config: EngineConfig | None = None, storage: StorageBackend | None = None,
                 tracer: Tracer | None = None, auto_approve: bool = False, seed: int | None = None,
                 cache_dir: str | Path | None = None, use_cache: bool = True) -> None:
        self.script = script
        self.interactive = interactive
        self.auto_approve = auto_approve
        self.seed_flag = seed
        self.controller = controller
        self.world = world
        self.tracer = tracer or NullTracer()
        self.storage = storage
        self.config = config
        self.cache_dir = Path(cache_dir) if cache_dir is not None else REPO_ROOT / "var" / script.id
        self.use_cache = use_cache
        self.step_index = 0
        self.state: str = "idle"
        self.caption: str | None = None
        self.forecasts_by_thesis: dict[str, str] = {}
        self.thesis_aliases: dict[str, str] = {}
        self.reports: list[StepReport] = []
        self.listeners: list[Any] = []
        self._pause = threading.Event()
        self.lock = threading.RLock()
        self.loaded = False
        self.init_version = 0
        self.init_info: dict[str, Any] = {}
        self.recorder: Any = None
        self.playing = False
        self.error: str | None = None
        self.pending_step: dict[str, Any] | None = None    # a step whose update paused for review
        self.update_ids: list[str] = []
        # what load() is doing, read by the demo menu's progress bar from another thread (api/app.py): its phase
        # ("world", "replay", "session", "ready") and, during the history replay, the engine and how many days it has
        self.progress: dict[str, Any] = {}

    # -- configuration -------------------------------------------------------------------------
    @property
    def scenario_dir(self) -> Path:
        return self.script.directory

    def effective_config(self) -> EngineConfig:
        if self.config is not None:
            cfg = self.config.model_copy(deep=True)
        else:
            overrides = [self.script.config_overrides] if self.script.config_overrides else []
            cfg = load_config(overrides=overrides)
        seed = self.seed_flag if self.seed_flag is not None else (self.script.seed if self.script.seed is not None else cfg.seed)
        cfg.seed = int(seed)
        return cfg

    def _init_key(self, cfg: EngineConfig) -> str:
        ini = self.script.initialization
        hist = ini.history_spec()
        files = [resolve_path(ini.construction_dir), resolve_path(ini.taxonomy_dir), resolve_path(ini.seeds),
                 resolve_path(hist.regimes), resolve_path(self.script.world.truth),
                 self.scenario_dir / "market_events.jsonl"]
        # DECISION: the key also covers the package's source, so a code change rebuilds the cache.
        src = Path(__file__).resolve().parents[1]
        code = sorted(d for d in src.iterdir()
                      if d.is_dir() and not d.name.startswith("__") and d.name not in ("api", "flows"))
        # DECISION: the history replay always auto-approves, so the review policy is left out of the key
        keyed = cfg.model_copy(deep=True)
        keyed.review.policy = "default"
        keyed.components.pop("review_policy", None)
        keyed.storage.backend = "files"
        keyed.storage.path = ""
        # the demos' example catalogs never run during the history replay, so editing them keeps the cache
        payload = {"format": INIT_FORMAT, "files": _hash_files(files), "code": _hash_files(code, skip=("examples",)),
                   "config": keyed.config_hash(), "seed": cfg.seed,
                   "history": [hist.from_.isoformat(), hist.to.isoformat()]}
        return sha256_text(canonical_json(payload))

    # -- the world -----------------------------------------------------------------------------
    def _scripted_events(self) -> JsonlReplaySource:
        return JsonlReplaySource(self.scenario_dir / "market_events.jsonl")

    def _build_world(self, cfg: EngineConfig) -> tuple[SyntheticWorld, list]:
        ini = self.script.initialization
        hist = ini.history_spec()
        spec = ConstructionSpec.load(ini.construction_dir, ini.taxonomy_dir)
        truth = TruthSpec.load(self.script.world.truth)
        vocab = load_vocabulary(ini.taxonomy_dir)
        scripted = self._scripted_events()
        shocks = [(e.occurred_at, scripted.extras.get(e.id, {}).get("world_shocks", [])) for e in scripted.events]
        world = SyntheticWorld(spec, truth, cfg.seed, [s for s in shocks if s[1]], origin=hist.from_, vocab=vocab,
                               min_delay_days=int(cfg.propagation.min_delay_days))
        regimes = (yaml.safe_load(resolve_path(hist.regimes).read_text()) or {}).get("regimes", [])
        history = world.generate_history(hist.from_, hist.to, regimes)
        return world, history

    # -- initialization ------------------------------------------------------------------------
    def _init_dir(self) -> Path:
        return self.cache_dir / "init"

    @contextmanager
    def _init_lock(self):
        """An exclusive lock on the scenario's init cache, across processes (restructure). Without it, two
        processes whose code differs could rebuild the same cache at once and corrupt it."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.cache_dir / "init.lock", "w") as fh:
            try:
                import fcntl
            except ImportError:            # no POSIX locks (Windows): run unlocked
                yield
                return
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _init_cache_path(self) -> Path:
        return self.cache_dir / "init_snapshot.json.gz"

    def _build_init(self, cfg: EngineConfig, history: list, key: str) -> dict:
        """Construction, seeds, the history replay as one long update run (§8.13), frontier seeds,
        and cursors, in a files backend under the cache directory."""
        # the replay approves everything; it runs on its own copy of the config, so the session that
        # loads afterwards keeps the configured review policy
        cfg = cfg.model_copy(deep=True)
        ini = self.script.initialization
        hist = ini.history_spec()
        init_dir = self._init_dir()
        storage = FilesBackend(path=init_dir)
        storage.reset()
        vocab = load_vocabulary(ini.taxonomy_dir)
        eng = build_engine(cfg, storage, NullTracer(), vocab=vocab)
        self.progress = {"phase": "replay", "engine": eng, "days": (hist.to - hist.from_).days + 1}
        init = Initializer(eng)
        spec = ConstructionSpec.load(ini.construction_dir, ini.taxonomy_dir)
        init.construct(spec, ini.taxonomy_dir, start=hist.from_, vocab=vocab)
        seeds = SeedFile.load(ini.seeds)
        init.load_seeds(seeds, now=eng.wm.clock)
        ctl = WorldModelController(eng, scenario_dir=self.scenario_dir)
        ctl.register_source("history_replay", HistoryReplaySource(history))
        ctl.set_review_policy("auto_approve_all")
        eng.initializing = True
        try:
            run = ctl.request_update(UpdateRequest(requested_by="init", until=hist.to, sources=["history_replay"],
                                                   requested_at=datetime.combine(hist.to, time(23, 59, 59), tzinfo=UTC)))
        finally:
            eng.initializing = False
        if run.state != UpdateState.DONE:
            raise RuntimeError(f"the history replay ended in state {run.state}: {run.error}")
        end = eng.wm.clock
        init.load_frontier_seeds(seeds, now=end)
        init.set_cursors(list(cfg.update.sources), end)
        sv = eng.save_snapshot()
        storage.flush()
        return {"format": INIT_FORMAT, "key": key, "version": eng.version, "seq": eng.ledger.next_seq - 1,
                "control_ids": dict(ctl.ids.counters), "version_info": sv.model_dump(mode="json") if sv else None,
                "state_hash": eng.state_hash, "history_events": len(history),
                "days": int(eng.wm.last_processed_day) + 1}

    def _load_or_build_init(self, cfg: EngineConfig, history: list) -> dict:
        key = self._init_key(cfg)
        path = self._init_cache_path()
        if self.use_cache and path.exists() and (self._init_dir() / "ledger.jsonl").exists():
            try:
                meta = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
                if meta.get("key") == key and meta.get("format") == INIT_FORMAT:
                    return meta
            except (OSError, ValueError):
                pass
        meta = self._build_init(cfg, history, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(meta).encode("utf-8"), compresslevel=5, mtime=0))
        return meta

    def _session_storage(self, cfg: EngineConfig, meta: dict) -> StorageBackend:
        """The session's storage, holding the init state: a files session copies the history's
        ledger, versions, and snapshots; a memory session gets only the init snapshot."""
        storage = self.storage if self.storage is not None else make_storage(cfg)
        storage.reset()
        init_dir = self._init_dir()
        version = int(meta["version"])
        sv = StateVersion.model_validate(meta["version_info"])
        blob = (init_dir / "snapshots" / f"v{version:06d}.json.gz").read_bytes()
        if isinstance(storage, FilesBackend):
            storage.flush()
            storage._close()
            shutil.copyfile(init_dir / "ledger.jsonl", storage.ledger_path)
            shutil.copyfile(init_dir / "versions.jsonl", storage.versions_path)
            for snap in sorted((init_dir / "snapshots").glob("v*.json.gz")):
                dst = storage.path / "snapshots" / snap.name
                try:
                    os.link(snap, dst)
                except OSError:
                    shutil.copyfile(snap, dst)
            storage._versions_cache = None
            storage._last_seq = None
        else:
            storage.append_version(sv)
            storage.save_snapshot(sv, blob)
        return storage

    def load(self) -> RunnerStatus:
        """Initialization, using the cached init snapshot."""
        with self.lock:
            cfg = self.effective_config()
            if self.auto_approve:
                cfg.review.policy = "auto_approve_all"
            self.progress = {"phase": "world"}
            world, history = self._build_world(cfg)
            # one builder at a time: a demo server, the CLI, and the tests may share a scenario's init cache
            with self._init_lock():
                meta = self._load_or_build_init(cfg, history)
                self.progress = {"phase": "session"}
                storage = self._session_storage(cfg, meta)
            vocab = load_vocabulary(self.script.initialization.taxonomy_dir)
            eng = build_engine(cfg, storage, self.tracer, vocab=vocab)
            eng.ledger.set_base(int(meta["seq"]))
            version = int(meta["version"])
            wm, ltm = load_state(storage.load_snapshot(version))
            eng.load_state(wm, ltm, version)
            ctl = WorldModelController(eng, scenario_dir=self.scenario_dir, control_ids=meta.get("control_ids"))
            ctl.set_review_policy(cfg.review.policy)
            scripted = self._scripted_events()
            ctl.register_source("mock_web_scraper", MockWebScraper(path=self.scenario_dir / "market_events.jsonl",
                                                                   **cfg.update.source_params.get("mock_web_scraper", {})))
            ctl.register_source("synthetic_data_feed", SyntheticDataFeed(
                world, scripted=[e for e in scripted.events if e.channel == MarketEventChannel.DATA_FEED]))
            self.controller = ctl
            self.world = world
            self.market_source = scripted
            self.user_events = load_user_events(self.scenario_dir)
            self.init_version = version
            self.init_seq = int(meta["seq"])
            self.init_info = {"history_events": meta.get("history_events"), "version": version,
                              "days": meta.get("days")}
            self.theses_spec, self.hypotheses_spec = load_theses(self.scenario_dir)
            self.decisions_spec = load_decisions(self.scenario_dir)
            self.step_index = 0
            self.state = "idle"
            self.forecasts_by_thesis = {}
            self.thesis_aliases = {}
            self.reports = []
            self.pending_step = None
            self.update_ids = []
            self.loaded = True
            self.error = None
            start = datetime.combine(self.script.start, time(0), tzinfo=UTC)
            ctl.advance_now(start)
            for h in self.hypotheses_spec.values():
                hyp = Hypothesis.model_validate({**h, "probability": h.get("probability", 0.5),
                                                 "scored_at": start.isoformat()})
                ctl.add_hypothesis(hyp)
            eng.ledger.append(_ledger_kind("UPDATE"), {"scenario": self.script.id, "seed": cfg.seed,
                                                        "state": "loaded", "init_version": version},
                              recorded_at=ctl.now)
            if self.recorder is not None:
                self.recorder.attach(self)
            self.tracer.emit(Phase.INIT, "scenario.loaded", refs=[self.script.id], scenario_id=self.script.id,
                             version=eng.version, steps=len(self.script.steps))
            self._broadcast()
            return self.status()

    def reset(self) -> RunnerStatus:
        """Back to the init snapshot."""
        return self.load()

    # -- sessions (axelrod init / axelrod update) ---------------------------------------------
    def session_record(self) -> dict:
        """What `axelrod update` needs to continue this runner's state from its files backend."""
        ctl = self.controller
        return {"scenario": self.script.id, "config": getattr(self, "config_path", None),
                "seed": int(ctl.engine.config.seed), "init_version": self.init_version,
                "init_seq": int(getattr(self, "init_seq", 0)),
                "version": ctl.engine.version, "control_ids": dict(ctl.ids.counters), "now": ctl.now.isoformat(),
                "storage": str(getattr(ctl.engine.storage, "path", "")), "step_index": self.step_index}

    def resume(self, session: dict) -> RunnerStatus:
        """Continue a session: restore the latest version from the files backend (its newest snapshot
        plus the change sets after it), rebuild the world (deterministic from the seed), and rebuild
        the controller's view of the market events already collected."""
        from axelrod_wm.repo.snapshots import SnapshotStore  # noqa: F401  (documentation)

        with self.lock:
            cfg = self.effective_config()
            if self.auto_approve:
                cfg.review.policy = "auto_approve_all"
            world, _history = self._build_world(cfg)
            storage = self.storage if self.storage is not None else make_storage(cfg)
            vocab = load_vocabulary(self.script.initialization.taxonomy_dir)
            eng = build_engine(cfg, storage, self.tracer, vocab=vocab)
            versions = storage.versions()
            if not versions:
                raise RuntimeError("the session has no versions; run `axelrod init` first")
            latest = versions[-1].version
            wm, ltm = eng.restore(latest)
            eng.load_state(wm, ltm, latest)
            ctl = WorldModelController(eng, scenario_dir=self.scenario_dir, control_ids=session.get("control_ids"))
            ctl.set_review_policy(cfg.review.policy)
            scripted = self._scripted_events()
            ctl.register_source("mock_web_scraper", MockWebScraper(path=self.scenario_dir / "market_events.jsonl",
                                                                   **cfg.update.source_params.get("mock_web_scraper", {})))
            ctl.register_source("synthetic_data_feed", SyntheticDataFeed(
                world, scripted=[e for e in scripted.events if e.channel == MarketEventChannel.DATA_FEED]))
            from axelrod_wm.events.market import MarketEvent
            from axelrod_wm.repo.ledger import LedgerKind

            last_day = int(wm.last_processed_day)
            for e in eng.ledger.of_kind(LedgerKind.MARKET_EVENT, int(session.get("init_seq", 0))):
                me = MarketEvent.model_validate(e.payload)
                ctl.remember_market_event(me)
                if wm.deviations.day_of(me.published_at) <= last_day:
                    ctl.market_status[me.id] = "applied"
            self.controller = ctl
            self.world = world
            self.market_source = scripted
            self.user_events = load_user_events(self.scenario_dir)
            self.init_version = int(session.get("init_version", 0))
            self.init_seq = int(session.get("init_seq", 0))
            self.theses_spec, self.hypotheses_spec = load_theses(self.scenario_dir)
            self.decisions_spec = load_decisions(self.scenario_dir)
            self.step_index = int(session.get("step_index", 0))
            self.loaded = True
            now = datetime.fromisoformat(session["now"]) if session.get("now") else wm.clock
            ctl.advance_now(max(now, wm.clock))
            return self.status()

    # -- stepping ------------------------------------------------------------------------------
    def _update_request(self, st: Any) -> UpdateRequest:
        spec = st.update
        mes = []
        for mid in spec.user_market_events:
            ev = self.market_source.get(mid)
            if ev is None:
                raise KeyError(f"unknown user market event {mid}")
            mes.append(ev)
        gues = []
        for gid in spec.user_graph_update_events:
            raw = dict(self.user_events[gid])
            raw.setdefault("recorded_at", st.at.isoformat())
            gues.append(GraphUpdateEvent.model_validate(raw))
        return UpdateRequest(requested_by="scenario", until=st.at.date(), requested_at=st.at,
                             user_market_events=mes, user_graph_update_events=gues, sources=spec.sources)

    def _placeholder(self, ctx: dict, note: str) -> StepReport:
        return StepReport(step_index=self.step_index, at=ctx["step"].at, update_id=ctx["update_id"],
                          market_event_ids=[], proposal_ids=[], forecast_ids=[], caption=ctx["step"].caption,
                          notes=[note])

    def step(self, drive: bool = True) -> StepReport:
        """Run the next step. With drive=False (the API), a step's update is only started: the caller
        processes its days (releasing the lock between days) and calls step() again to finish it."""
        with self.lock:
            if not self.loaded:
                self.load()
            if self.pending_step is not None:
                return self._resume_pending(drive)
            if self.step_index >= len(self.script.steps):
                self.state = "done"
                return self.reports[-1] if self.reports else StepReport(
                    step_index=self.step_index, at=self.controller.now, update_id=None, market_event_ids=[],
                    proposal_ids=[], forecast_ids=[])
            self.state = "running"
            ctl = self.controller
            st = self.script.steps[self.step_index]
            self.caption = st.caption
            if st.caption:
                self.tracer.emit(Phase.SCENARIO, "scenario.caption", refs=[], text=st.caption, step_index=self.step_index)
            ctx = {"step": st, "before_props": set(ctl.proposals), "before_fc": set(ctl.forecasts),
                   "before_me": set(ctl.market_events), "update_id": None}
            if st.update is not None:
                run = ctl.request_update(self._update_request(st), run_to_end=drive)
                ctx["update_id"] = run.id
                self.update_ids.append(run.id)
                if run.state == UpdateState.RUNNING and not drive:
                    self.pending_step = ctx
                    self.state = "running"
                    self._broadcast()
                    return self._placeholder(ctx, "updating")
                if run.state == UpdateState.AWAITING_REVIEW:
                    if self.interactive:
                        self.pending_step = ctx
                        self.state = "awaiting_review"
                        self._broadcast()
                        return self._placeholder(ctx, "awaiting review")
                    # DECISION: a headless run without --auto-approve defers what needs review, so the
                    # scenario keeps moving; deferred events can still be approved and fold in late.
                    while run.state == UpdateState.AWAITING_REVIEW:
                        run = ctl.continue_update(run.id)
            else:
                ctl.advance_now(st.at)
            return self._finish_step(ctx)

    def _resume_pending(self, drive: bool = True) -> StepReport:
        ctx = self.pending_step
        ctl = self.controller
        run = ctl.get_update(ctx["update_id"])
        if run.state == UpdateState.RUNNING and drive:
            ctl.continue_update(run.id)
            run = ctl.get_update(run.id)
        if run.state == UpdateState.AWAITING_REVIEW:
            if not self.interactive:
                while run.state == UpdateState.AWAITING_REVIEW:
                    run = ctl.continue_update(run.id)
            else:
                self.state = "awaiting_review"
                return self._placeholder(ctx, "awaiting review")
        if run.state == UpdateState.RUNNING:
            self.state = "running"
            return self._placeholder(ctx, "updating")
        self.pending_step = None
        self.state = "running"
        return self._finish_step(ctx)

    def pending_update(self) -> str | None:
        """The update id of a step that has started but not finished."""
        return self.pending_step["update_id"] if self.pending_step is not None else None

    def resume_after_review(self) -> RunnerStatus:
        """Called after a review decision: if the paused step's update has finished, run its action."""
        with self.lock:
            if self.pending_step is not None:
                run = self.controller.get_update(self.pending_step["update_id"])
                if run.state not in (UpdateState.AWAITING_REVIEW, UpdateState.RUNNING):
                    self._resume_pending()
            return self.status()

    def _finish_step(self, ctx: dict) -> StepReport:
        ctl = self.controller
        st = ctx["step"]
        ctl.advance_now(st.at)
        notes: list[str] = []
        for act in st.structure:
            prop = self._structure_action(act)
            notes.append(f"{prop.kind} {prop.id}: {prop.status}")
        for tid in st.theses():
            spec = self.theses_spec[tid]
            fc = ctl.pose_thesis(thesis_from_spec(spec, ctl.now))
            self.forecasts_by_thesis[tid] = fc.id
        for tid in st.pin:
            ctl.pin_thesis(tid, True)
            notes.append(f"pinned {tid}")
        if st.pose_hypothesis is not None:
            fc = ctl.pose_hypothesis(st.pose_hypothesis.hypothesis, st.pose_hypothesis.base_thesis)
            self.forecasts_by_thesis[fc.thesis_id] = fc.id
            # the demo calls the first posed decision hypothesis T-02 (§14.6 step 14)
            alias = "T-02" if "T-02" not in self.thesis_aliases else f"T-{len(self.thesis_aliases) + 2:02d}"
            self.forecasts_by_thesis[alias] = fc.id
            self.thesis_aliases[alias] = fc.thesis_id
        if st.evaluate is not None:
            rep = ctl.evaluate(EvaluationRequest.model_validate(st.evaluate))
            notes.append(f"evaluation {rep.id}")
        if st.decision is not None:
            rec = self._record_decision(st.decision)
            notes.append(f"decision {rec.id} at version {rec.state_version}")
        if st.resolve_decision is not None:
            out = ctl.resolve_decision(st.resolve_decision)
            notes.append(f"outcome crps {out.crps:.3f}")
        if ctx["update_id"]:
            run = ctl.get_update(ctx["update_id"])
            if run.report is not None:
                notes.append(f"{ctx['update_id']}: {run.state}, {run.report.days} days, "
                             f"collected {sum(run.report.collected.values())}")
        report = StepReport(step_index=self.step_index, at=st.at, update_id=ctx["update_id"],
                            market_event_ids=[m for m in ctl.market_events if m not in ctx["before_me"]],
                            proposal_ids=[p for p in ctl.proposals if p not in ctx["before_props"]],
                            forecast_ids=[f for f in ctl.forecasts if f not in ctx["before_fc"]],
                            caption=st.caption, notes=notes)
        self.reports.append(report)
        self.step_index += 1
        pending = len(ctl.pending_proposals())
        if self.step_index >= len(self.script.steps):
            self.state = "done"
        elif self.interactive and pending:
            self.state = "awaiting_review"
        else:
            self.state = "running" if self.playing and not self._pause.is_set() else "idle"
        for fn in list(self.listeners):
            fn("step", report=report)
        self._broadcast()
        return report

    def _structure_action(self, act: Any) -> Any:
        """A backend user's structural edit: collapse (group), expand (dissolve), or delete (retire)."""
        ctl = self.controller
        if act.group is not None:
            g = act.group
            return ctl.propose_group(g.name, g.members, interactions=g.interactions or None, pattern_id=g.id,
                                     description=g.description, by=act.by)
        if act.dissolve is not None:
            return ctl.propose_dissolve(act.dissolve.pattern, act.dissolve.reason, by=act.by)
        if act.retire is not None:
            r = act.retire
            return ctl.propose_retire(entity_id=r.entity, interaction_id=r.interaction, reason=r.reason, by=act.by)
        raise ValueError("a structure action needs group, dissolve, or retire")

    def _record_decision(self, decision_id: str) -> Any:
        ctl = self.controller
        spec = self.decisions_spec[decision_id]
        fids = [self.forecasts_by_thesis[t] for t in spec.cites if t in self.forecasts_by_thesis]
        fcs = [ctl.forecast(f) for f in fids]
        base = next((f for f in fcs if f is not None and f.is_baseline), None)
        version = base.based_on_version if base is not None else ctl.engine.version
        return ctl.record_decision({"id": spec.id, "agent_id": spec.agent_id, "recommendation": spec.recommendation,
                                    "rationale": spec.rationale, "forecast_ids": fids, "thesis_ids": list(spec.cites),
                                    "state_version": version, "created_at": ctl.now.isoformat(),
                                    "review_after": (ctl.now + timedelta(days=spec.review_after_days)).isoformat()})

    def play(self, until_step: int | None = None) -> RunnerStatus:
        self._pause.clear()
        last = len(self.script.steps) if until_step is None else min(until_step, len(self.script.steps))
        self.playing = True
        try:
            while self.step_index < last and not self._pause.is_set():
                if self.state == "awaiting_review" and (self.pending_step is not None or self.controller.pending_proposals()):
                    if self.pending_step is None or self.controller.get_update(
                            self.pending_step["update_id"]).state == UpdateState.AWAITING_REVIEW:
                        break
                self.step()
                if self.state in ("awaiting_review", "done"):
                    break
        finally:
            self.playing = False
            if self.state == "running":
                self.state = "idle"
        self._broadcast()
        return self.status()

    def pause(self) -> RunnerStatus:
        self._pause.set()
        if self.state == "running":
            self.state = "idle"
        self._broadcast()
        return self.status()

    def status(self) -> RunnerStatus:
        ctl = self.controller
        pending = len(ctl.pending_proposals()) if ctl is not None else 0
        state = self.state
        if state == "awaiting_review" and pending == 0 and self.pending_step is None:
            state = "idle" if self.step_index < len(self.script.steps) else "done"
            self.state = state
        active = ctl.active_update if ctl is not None else None
        return RunnerStatus(scenario_id=self.script.id, step_index=self.step_index, total_steps=len(self.script.steps),
                            sim_time=ctl.now if ctl is not None else datetime.combine(self.script.start, time(0), tzinfo=UTC),
                            state=state, update_id=active, pending_proposals=pending, caption=self.caption,
                            version=ctl.engine.version if ctl is not None else 0, loaded=self.loaded,
                            error=self.error,
                            next_step_at=self.script.steps[self.step_index].at
                            if self.step_index < len(self.script.steps) else None)

    def _broadcast(self) -> None:
        fn = getattr(self.tracer, "broadcast", None)
        if fn is not None:
            fn({"type": "status", "status": json.loads(self.status().model_dump_json())})

    # -- checklist -----------------------------------------------------------------------------
    def checklist(self) -> list[tuple[str, bool]]:
        if self.recorder is None:
            return []
        return self.recorder.evaluate(self)


def _ledger_kind(name: str) -> Any:
    from axelrod_wm.repo.ledger import LedgerKind

    return LedgerKind[name]


def build_runner(scenario: str = "oil_shock_demo", *, interactive: bool = False, auto_approve: bool = False,
                 seed: int | None = None, config_path: str | None = None, storage: StorageBackend | None = None,
                 tracer: Tracer | None = None, record_checklist: bool = True, use_cache: bool = True,
                 config: EngineConfig | None = None, cache_dir: str | Path | None = None) -> ScenarioRunner:
    script = ScenarioScript.load(scenario)
    cfg = config
    if cfg is None and config_path is not None:
        overrides = [script.config_overrides] if script.config_overrides else []
        cfg = load_config(config_path, overrides=overrides)
    cls = ScenarioRunner
    if script.imports:
        from axelrod_wm.sim.imports import ImportRunner

        cls = ImportRunner
        record_checklist = False
    elif script.examples is not None:
        from axelrod_wm.sim.examples.session import ProdDemoRunner, SmallDemoRunner

        if script.base is not None:
            script = ScenarioScript.load(script.base)        # the base's world, history, and init cache
            cls = ProdDemoRunner
        else:
            cls = SmallDemoRunner
        record_checklist = False
    runner = cls(None, None, script, interactive, config=cfg, storage=storage, tracer=tracer,
                 auto_approve=auto_approve, seed=seed, use_cache=use_cache, cache_dir=cache_dir)
    runner.config_path = config_path
    if record_checklist and script.checklist:
        from axelrod_wm.sim.checklist import ChecklistRecorder

        runner.recorder = ChecklistRecorder()
    return runner
