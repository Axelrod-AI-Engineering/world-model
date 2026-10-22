"""The engine: state, components, and wiring (§8.1, §8.3)."""

from __future__ import annotations

import inspect
from datetime import datetime
from typing import Any

from axelrod_wm.engine.config import DEFAULT_COMPONENTS, EngineConfig
from axelrod_wm.engine.context import ProcessContext
from axelrod_wm.engine.registry import REGISTRIES, registry
from axelrod_wm.engine.rng import make_rng
from axelrod_wm.memory.long_term import LongTermMemory
from axelrod_wm.memory.working import WorkingMemory
from axelrod_wm.model.taxonomy import AttributeVocabulary
from axelrod_wm.repo.ledger import EventLedger, LedgerKind
from axelrod_wm.repo.mutator import ChangeSet, GraphMutator, MutationTxn
from axelrod_wm.repo.snapshots import (
    FilesBackend,
    MemoryBackend,
    SnapshotStore,
    StateHasher,
    StateVersion,
    StorageBackend,
    empty_state,
    state_hash,
)
from axelrod_wm.trace import NullTracer, Phase, Tracer


class Engine:
    config: EngineConfig
    vocab: AttributeVocabulary
    wm: WorkingMemory
    ltm: LongTermMemory
    storage: StorageBackend
    snapshots: SnapshotStore
    ledger: EventLedger
    mutator: GraphMutator
    tracer: Tracer
    components: dict[str, Any]                 # slot name -> component

    def __init__(self, config: EngineConfig, storage: StorageBackend, tracer: Tracer,
                 vocab: AttributeVocabulary | None = None) -> None:
        self.config = config
        self.storage = storage
        self.tracer = tracer
        self.vocab = vocab or AttributeVocabulary(kinds={})
        self.wm, self.ltm = empty_state()
        self.version = 0
        self.ledger = EventLedger(storage, clock=lambda: self.wm.clock, version=lambda: self.version)
        self.snapshots = SnapshotStore(storage, self.ledger, empty_state)
        self.mutator = GraphMutator(self)
        self.hasher = StateHasher()
        self.state_hash = self.hasher.full(self.wm, self.ltm)
        self.components = {}
        self.initializing = False
        self.shared: Any = None
        self.learning: Any = None
        self.inference: Any = None
        self.structural: Any = None

    # -- context ---------------------------------------------------------------------------
    def context(self, *, learn: bool, now: datetime, processing_day: int | None = None) -> ProcessContext:
        self.tracer.set_context(sim_time=now, state_version=self.version)
        return ProcessContext(config=self.config, rng=make_rng(self.config.seed, self.version, "ctx"),
                              tracer=self.tracer, now=now, state_version=self.version, mutator=self.mutator,
                              vocab=self.vocab, learn=learn, processing_day=processing_day,
                              initializing=self.initializing, engine=self)

    def component(self, slot: str) -> Any:
        return self.components[slot]

    # -- commits ---------------------------------------------------------------------------
    def on_commit(self, cs: ChangeSet, txn: MutationTxn, bumped: bool) -> None:
        entry = self.ledger.append(LedgerKind.CHANGESET, cs, recorded_at=cs.recorded_at,
                                   state_version=cs.version_after)
        if not bumped:
            return
        self.version = cs.version_after
        self.state_hash = self.hasher.update(self.wm, self.ltm, txn.dirty)
        sv = StateVersion(version=self.version, seq=entry.seq, state_hash=self.state_hash,
                          recorded_at=cs.recorded_at, cause=cs.cause, process=cs.process, memory=cs.memory)
        self.storage.append_version(sv)
        self.tracer.set_context(state_version=self.version)
        if cs.process in ("day.distill", "day.close"):
            phase = Phase.CONSOLIDATE
        elif cs.process in ("day.predict", "day.record"):
            phase = Phase.DAILY
        elif self.initializing or cs.process == "construction":
            phase = Phase.INIT
        elif cs.process == "learn.long_term":
            phase = Phase.GENERALIZE
        else:
            phase = Phase.FOLD
        self.tracer.emit(phase, "state.version", refs=[cs.id], version=self.version, cause=cs.cause,
                         changes=len(cs.changes), process=cs.process, memory=cs.memory, message=cs.message)

    def version_info(self, version: int | None = None) -> StateVersion | None:
        return self.snapshots.version_info(self.version if version is None else version)

    def save_snapshot(self) -> StateVersion | None:
        sv = self.version_info()
        if sv is not None:
            self.snapshots.save(self.wm, self.ltm, sv)
        return sv

    def full_state_hash(self) -> str:
        return state_hash(self.wm, self.ltm)

    def restore(self, version: int) -> tuple[WorkingMemory, LongTermMemory]:
        """A read-only copy of the state at `version` (the live state is untouched)."""
        return self.snapshots.restore(version)

    def load_state(self, wm: WorkingMemory, ltm: LongTermMemory, version: int) -> None:
        """Replace the live state (after loading a snapshot)."""
        self.wm, self.ltm = wm, ltm
        self.version = version
        self.state_hash = self.hasher.full(wm, ltm)
        self.tracer.set_context(sim_time=wm.clock, state_version=version)


# ---------------------------------------------------------------------------------------------
# build_engine
# ---------------------------------------------------------------------------------------------

STORAGE_BACKENDS = {"files": FilesBackend, "memory": MemoryBackend}


def make_storage(config: EngineConfig) -> StorageBackend:
    cls = STORAGE_BACKENDS.get(config.storage.backend)
    if cls is None:
        raise KeyError(f"unknown storage backend {config.storage.backend!r}")
    return cls(path=config.storage.path)


def all_slots(config: EngineConfig) -> list[str]:
    return list(dict.fromkeys(list(DEFAULT_COMPONENTS) + list(config.components)))


def _create(slot: str, config: EngineConfig, engine: Engine, made: dict[str, Any], stack: list[str]) -> Any:
    if slot in made:
        return made[slot]
    if slot in stack:
        raise RuntimeError(f"component dependency cycle: {' -> '.join(stack + [slot])}")
    name, params = config.component(slot)
    cls = registry(slot).get(name)
    kwargs: dict[str, Any] = {}
    slots = set(all_slots(config))
    sig = inspect.signature(cls.__init__)
    for pname, p in list(sig.parameters.items())[1:]:
        if p.kind in (p.VAR_KEYWORD, p.VAR_POSITIONAL):
            continue
        if pname in params:
            kwargs[pname] = params[pname]
        elif pname == "config":
            kwargs[pname] = config
        elif pname == "engine":
            kwargs[pname] = engine
        elif pname in slots:
            kwargs[pname] = _create(pname, config, engine, made, stack + [slot])
    extra = {k: v for k, v in params.items() if k not in kwargs}
    if extra and any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values()):
        kwargs.update(extra)
    elif extra:
        raise TypeError(f"{cls.__name__} ({slot}) does not accept params {sorted(extra)}")
    obj = cls(**kwargs)
    made[slot] = obj
    return obj


def build_engine(config: EngineConfig, storage: StorageBackend | None = None,
                 tracer: Tracer | None = None, vocab: AttributeVocabulary | None = None) -> Engine:
    """Create the components in dependency order and wire the tasks."""
    from axelrod_wm.engine import load_defaults

    load_defaults()
    from axelrod_wm.inference.task import InferenceTask
    from axelrod_wm.learning.structural import StructuralApplier
    from axelrod_wm.learning.task import LearningTask
    from axelrod_wm.shared.process import SharedProcess

    storage = storage if storage is not None else make_storage(config)
    engine = Engine(config, storage, tracer or NullTracer(), vocab=vocab)
    made: dict[str, Any] = {}
    for slot in all_slots(config):
        _create(slot, config, engine, made, [])
    engine.components = made
    engine.shared = SharedProcess(engine, parser=made["parser"], classifier=made["classifier"],
                                  recaller=made["recaller"], inducer=made["inducer"],
                                  prefiller=made["prefiller"], analyzer=made["analyzer"])
    engine.learning = LearningTask(engine)
    engine.inference = InferenceTask(engine)
    engine.structural = StructuralApplier(engine)
    return engine


def registered_components() -> dict[str, list[str]]:
    from axelrod_wm.engine import load_defaults

    load_defaults()
    return {slot: reg.names() for slot, reg in sorted(REGISTRIES.items())}
