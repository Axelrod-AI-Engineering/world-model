"""The scenario runner (§11.3): load (with a cached init snapshot), step, play, pause, reset."""

from __future__ import annotations

import gzip
import json
import threading
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from axelrod_wm.control.controller import WorldModelController
from axelrod_wm.core.hypothesis import Hypothesis
from axelrod_wm.core.serialization import canonical_json, sha256_text
from axelrod_wm.engine.config import EngineConfig, load_config
from axelrod_wm.engine.engine import build_engine, make_storage
from axelrod_wm.engine.initialize import REPO_ROOT, ConstructionSpec, Initializer, SeedFile, resolve_path
from axelrod_wm.evaluation.backtest import EvaluationRequest
from axelrod_wm.events.ledger import LedgerEntry
from axelrod_wm.ingest.sources import JsonlReplaySource
from axelrod_wm.memory.snapshots import MemoryBackend, StateVersion, StorageBackend, dump_state, load_state
from axelrod_wm.sim.scenario import ScenarioScript, load_decisions, load_theses, thesis_from_spec
from axelrod_wm.sim.world import SyntheticWorld, TruthSpec
from axelrod_wm.trace import NullTracer, Phase, Tracer

INIT_FORMAT = 3


class RunnerStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    step_index: int
    total_steps: int
    sim_time: datetime
    state: Literal["idle", "running", "awaiting_review", "done"]
    pending_proposals: int
    caption: str | None = None
    version: int = 0
    loaded: bool = False
    error: str | None = None


class StepReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_index: int
    at: datetime
    market_event_ids: list[str]
    proposal_ids: list[str]
    forecast_ids: list[str]
    caption: str | None = None
    consolidations: list[str] = []
    notes: list[str] = []


def _hash_files(paths: list[Path]) -> str:
    parts = []
    for p in sorted(paths):
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and "__pycache__" not in f.parts:
                    parts.append(f"{f.relative_to(REPO_ROOT) if f.is_relative_to(REPO_ROOT) else f}:{sha256_text(f.read_text())}")
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
        self.playing = False          # a play loop is running; between steps the state stays "running"
        self.error: str | None = None

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
                 resolve_path(hist.regimes), resolve_path(self.script.world.truth)]
        # DECISION: the key also covers the package's engine source, so a code change rebuilds the cache.
        src = Path(__file__).resolve().parents[1]
        code = [src / d for d in ("core", "memory", "events", "ingest", "control", "engine", "evaluation", "sim")]
        # DECISION: the history replay always auto-approves, so the review policy is left out of the key
        # (otherwise a headless --auto-approve run and the interactive demo rebuild each other's cache)
        keyed = cfg.model_copy(deep=True)
        keyed.review.policy = "default"
        keyed.components.pop("review_policy", None)
        payload = {"format": INIT_FORMAT, "files": _hash_files(files), "code": _hash_files(code),
                   "config": keyed.config_hash(), "seed": cfg.seed,
                   "history": [hist.from_.isoformat(), hist.to.isoformat()]}
        return sha256_text(canonical_json(payload))

    # -- initialization ------------------------------------------------------------------------
    def _build_world(self, cfg: EngineConfig) -> tuple[SyntheticWorld, list]:
        ini = self.script.initialization
        hist = ini.history_spec()
        spec = ConstructionSpec.load(ini.construction_dir)
        truth = TruthSpec.load(self.script.world.truth)
        world = SyntheticWorld(spec, truth, cfg.seed, origin=datetime.combine(hist.from_, time(0), tzinfo=UTC),
                               step_days=float(cfg.time.propagation_step_days),
                               window=int(cfg.propagation.kernel_window_steps))
        regimes = (yaml.safe_load(resolve_path(hist.regimes).read_text()) or {}).get("regimes", [])
        history = world.generate_history(hist.from_, hist.to, regimes)
        return world, history

    def _build_init(self, cfg: EngineConfig, history: list) -> dict:
        ini = self.script.initialization
        hist = ini.history_spec()
        eng = build_engine(cfg, MemoryBackend(), NullTracer())
        init = Initializer(eng)
        start = datetime.combine(hist.from_, time(0), tzinfo=UTC)
        spec = ConstructionSpec.load(ini.construction_dir)
        init.construct(spec, ini.taxonomy_dir, start=start)
        seeds = SeedFile.load(ini.seeds)
        init.load_seeds(seeds, now=start)
        ctl = WorldModelController(eng, scenario_dir=self.scenario_dir)
        init.replay_history(ctl, history)
        end = datetime.combine(hist.to, time(23, 59, 59), tzinfo=UTC)
        ctl.set_time(end)
        init.load_frontier_seeds(seeds, now=end)
        sv = eng.version_info()
        return {"format": INIT_FORMAT, "version": eng.version,
                "control_ids": dict(ctl.ids.counters),
                "ledger": [e.model_dump(mode="json") for e in eng.ledger.entries],
                "versions": [v.model_dump(mode="json") for v in eng.storage.versions()],
                "state": json.loads(gzip.decompress(dump_state(eng.wm, eng.ltm)).decode("utf-8")),
                "state_hash": sv.state_hash if sv else eng.state_hash,
                "history_events": len(history)}

    def _init_cache_path(self) -> Path:
        return self.cache_dir / "init_snapshot.json.gz"

    def _load_or_build_init(self, cfg: EngineConfig, history: list) -> dict:
        key = self._init_key(cfg)
        path = self._init_cache_path()
        if self.use_cache and path.exists():
            try:
                data = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
                if data.get("key") == key and data.get("format") == INIT_FORMAT:
                    return data
            except (OSError, ValueError):
                pass
        data = self._build_init(cfg, history)
        data["key"] = key
        if self.use_cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(json.dumps(data).encode("utf-8"), compresslevel=5, mtime=0))
        return data

    def load(self) -> RunnerStatus:
        """Initialization, using the cached init snapshot."""
        with self.lock:
            cfg = self.effective_config()
            if self.auto_approve:
                cfg.review.policy = "auto_approve_all"
            world, history = self._build_world(cfg)
            data = self._load_or_build_init(cfg, history)
            storage = self.storage if self.storage is not None else make_storage(cfg)
            storage.reset()
            eng = build_engine(cfg, storage, self.tracer)
            entries = [LedgerEntry.model_validate(e) for e in data["ledger"]]
            eng.ledger.adopt(entries)
            for v in data["versions"]:
                storage.append_version(StateVersion.model_validate(v))
            blob = gzip.compress(json.dumps(data["state"]).encode("utf-8"), mtime=0)
            wm, ltm = load_state(blob)
            eng.load_state(wm, ltm, int(data["version"]))
            info = eng.version_info()
            if info is not None:
                storage.save_snapshot(info, dump_state(wm, ltm))
            ctl = WorldModelController(eng, scenario_dir=self.scenario_dir, control_ids=data.get("control_ids"))
            ctl.set_review_policy(cfg.review.policy)
            self.controller = ctl
            self.world = world
            self.init_version = int(data["version"])
            self.init_info = {"history_events": data.get("history_events"), "version": self.init_version}
            self.market_source = JsonlReplaySource(self.scenario_dir / "market_events.jsonl")
            self.theses_spec, self.hypotheses_spec = load_theses(self.scenario_dir)
            self.decisions_spec = load_decisions(self.scenario_dir)
            self.step_index = 0
            self.state = "idle"
            self.forecasts_by_thesis = {}
            self.thesis_aliases = {}
            self.reports = []
            self.loaded = True
            start = datetime.combine(self.script.start, time(0), tzinfo=UTC)
            ctl.set_time(start)
            for h in self.hypotheses_spec.values():
                hyp = Hypothesis.model_validate({**h, "probability": h.get("probability", 0.5),
                                                 "scored_at": start.isoformat()})
                ctl.add_hypothesis(hyp)
            if self.recorder is not None:
                self.recorder.attach(self)
            self.tracer.emit(Phase.INIT, "scenario.loaded", refs=[self.script.id], scenario_id=self.script.id,
                             version=eng.version, steps=len(self.script.steps))
            self._broadcast()
            return self.status()

    def reset(self) -> RunnerStatus:
        """Back to the init snapshot."""
        return self.load()

    # -- stepping ------------------------------------------------------------------------------
    def _advance(self, at: datetime, scripted: list[Any]) -> list[str]:
        ctl = self.controller
        world = self.world
        for ev in scripted:
            extra = self.market_source.extras.get(ev.id, {})
            world.inject_native(extra.get("world_shocks", []), ev.occurred_at)
        events = world.poll(at) + [e for e in scripted if e.published_at <= at]
        ids = []
        for ev in sorted(events, key=lambda e: (e.published_at, e.id)):
            ctl.ingest(ev)
            ids.append(ev.id)
        ctl.set_time(at)
        return ids

    def step(self) -> StepReport:
        with self.lock:
            if not self.loaded:
                self.load()
            if self.step_index >= len(self.script.steps):
                self.state = "done"
                return self.reports[-1] if self.reports else StepReport(step_index=self.step_index, at=self.controller.now,
                                                                         market_event_ids=[], proposal_ids=[], forecast_ids=[])
            self.state = "running"
            ctl = self.controller
            st = self.script.steps[self.step_index]
            scripted = [self.market_source.get(i) for i in st.market_events]
            missing = [i for i, e in zip(st.market_events, scripted) if e is None]
            if missing:
                raise KeyError(f"unknown market events {missing}")
            at = max([st.at] + [e.published_at for e in scripted])
            before_props = set(ctl.proposals)
            before_fc = set(ctl.forecasts)
            before_cons = len(ctl.consolidations)
            self.caption = st.caption
            if st.caption:
                self.tracer.emit(Phase.SCENARIO, "scenario.caption", refs=[], text=st.caption, step_index=self.step_index)
            ids = self._advance(at, scripted)
            notes: list[str] = []
            for tid in st.theses():
                spec = self.theses_spec[tid]
                fc = ctl.pose_thesis(thesis_from_spec(spec, ctl.now))
                self.forecasts_by_thesis[tid] = fc.id
            if st.pose_hypothesis is not None:
                fc = ctl.pose_hypothesis(st.pose_hypothesis.hypothesis, st.pose_hypothesis.base_thesis)
                self.forecasts_by_thesis[fc.thesis_id] = fc.id
                # the demo calls the first posed decision hypothesis T-02 (§14.6 step 13)
                alias = "T-02" if "T-02" not in self.thesis_aliases else f"T-{len(self.thesis_aliases) + 2:02d}"
                self.forecasts_by_thesis[alias] = fc.id
                self.thesis_aliases[alias] = fc.thesis_id
            if st.evaluate is not None:
                req = EvaluationRequest.model_validate(st.evaluate)
                rep = ctl.evaluate(req)
                notes.append(f"evaluation {rep.id}")
            if st.decision is not None:
                rec = self._record_decision(st.decision)
                notes.append(f"decision {rec.id} at version {rec.state_version}")
            if st.resolve_decision is not None:
                out = ctl.resolve_decision(st.resolve_decision)
                notes.append(f"outcome crps {out.crps:.3f}")
            if st.consolidate:
                days = self.controller.engine.wm.touched_days()
                if days:
                    ctl.consolidate(days[-1])
            report = StepReport(step_index=self.step_index, at=at, market_event_ids=ids,
                                proposal_ids=[p for p in ctl.proposals if p not in before_props],
                                forecast_ids=[f for f in ctl.forecasts if f not in before_fc], caption=st.caption,
                                consolidations=[str(r.day) for r in ctl.consolidations[before_cons:]], notes=notes)
            self.reports.append(report)
            self.step_index += 1
            pending = len(ctl.pending_proposals())
            if self.step_index >= len(self.script.steps):
                self.state = "done"
            elif self.interactive and pending and (st.pause_for_review is None or st.pause_for_review):
                self.state = "awaiting_review"
            else:
                self.state = "running" if self.playing and not self._pause.is_set() else "idle"
            for fn in list(self.listeners):
                fn("step", report=report)
            self._broadcast()
            return report

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
                if self.state == "awaiting_review" and self.controller.pending_proposals():
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
        if state == "awaiting_review" and pending == 0:
            state = "idle" if self.step_index < len(self.script.steps) else "done"
            self.state = state
        return RunnerStatus(scenario_id=self.script.id, step_index=self.step_index, total_steps=len(self.script.steps),
                            sim_time=ctl.now if ctl is not None else datetime.combine(self.script.start, time(0), tzinfo=UTC),
                            state=state, pending_proposals=pending, caption=self.caption,
                            version=ctl.engine.version if ctl is not None else 0, loaded=self.loaded,
                            error=self.error)

    def _broadcast(self) -> None:
        fn = getattr(self.tracer, "broadcast", None)
        if fn is not None:
            fn({"type": "status", "status": json.loads(self.status().model_dump_json())})

    # -- checklist -----------------------------------------------------------------------------
    def checklist(self) -> list[tuple[str, bool]]:
        if self.recorder is None:
            return []
        return self.recorder.evaluate(self)


def build_runner(scenario: str = "oil_shock_demo", *, interactive: bool = False, auto_approve: bool = False,
                 seed: int | None = None, config_path: str | None = None, storage: StorageBackend | None = None,
                 tracer: Tracer | None = None, record_checklist: bool = True, use_cache: bool = True,
                 config: EngineConfig | None = None, cache_dir: str | Path | None = None) -> ScenarioRunner:
    script = ScenarioScript.load(scenario)
    cfg = config
    if cfg is None and config_path is not None:
        overrides = [script.config_overrides] if script.config_overrides else []
        cfg = load_config(config_path, overrides=overrides)
    runner = ScenarioRunner(None, None, script, interactive, config=cfg, storage=storage, tracer=tracer,
                            auto_approve=auto_approve, seed=seed, use_cache=use_cache, cache_dir=cache_dir)
    if record_checklist:
        from axelrod_wm.sim.checklist import ChecklistRecorder

        runner.recorder = ChecklistRecorder()
    return runner

