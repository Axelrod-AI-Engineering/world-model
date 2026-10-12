# M01 · Core

| | |
|---|---|
| Layer | 0 · Foundation |
| Status | **Split out**: these pieces exist, scattered |
| Code today | `model/ids.py`, `model/serialization.py`, `engine/rng.py`, `engine/registry.py`, `trace.py` |
| Target | `axelrod_wm/core/` |

## Purpose

The few things every other module needs and that need nothing in return: ids, canonical serialization and hashing, reproducible randomness, the trace bus, and the slot registry. Moving them out of `engine/` and `model/` removes most of today's import cycles ([migration.md](../migration.md#current-cycles)).

## Owns

- `IdFactory`, `entity_of(id)`: deterministic ids. A subentity's id is `<entity>.<slug>`.
- `canonical_json(obj)`, `sha256_text(s)`: byte-stable JSON for hashing and snapshots.
- `substream(seed, *names) -> np.random.Generator`: named random substreams.
- `Phase`, `TraceEvent`, `Tracer` (port), `NullTracer`, `RecordingTracer`, `BroadcastTracer`.
- `Registry`, `registry(slot, interface)`, `register(slot, name)`, `REGISTRIES`.
- **New:** `identity_key(kind, **fields) -> str`, a uuid5 over declared identity fields (a ticker, an LEI, or a name and kind), so the same real actor resolves to the same id across imports. This is borrowed from Cognee's `identity_fields` ([frameworks.md](../frameworks.md#borrow-from-cognee)).

## Interface

```python
# ids
class IdFactory:
    def new(self, prefix: str) -> str
def entity_of(subentity_id: str) -> str
def identity_key(kind: str, **fields: str) -> str                       # new

# serialization
def canonical_json(obj: BaseModel | dict) -> str
def sha256_text(s: str) -> str

# randomness
def substream(seed: int, *names: str | int) -> np.random.Generator      # same names → same draws

# trace
class Tracer(ABC):
    def emit(self, phase: Phase, kind: str, /, refs: list[str] | None = None, **payload) -> None
    def scoped(self, scope: str) -> "Tracer"
class RecordingTracer(Tracer):
    def since(self, seq: int) -> list[TraceEvent]
class BroadcastTracer(RecordingTracer):
    def subscribe(self, loop, queue) -> Callable[[], None]

# registry
def registry(slot: str, interface: type | None = None) -> Registry
def register(slot: str, name: str) -> Callable[[type], type]            # class decorator
```

## Depends on / used by

- Depends on: nothing inside `axelrod_wm` (pydantic and numpy only).
- Used by: every module.

## Invariants

- **No internal imports.** A test fails if `core/` imports any other `axelrod_wm` package.
- **Explicit randomness.** Every draw in the system comes from `substream`. Same seed and same names give the same draws. Analyses run with and without a shock on the same draws (common random numbers).
- **Canonical bytes.** `canonical_json` is stable across runs and platforms, so state hashes are too.
- **Trace scope.** Every trace event is scoped to a market event, a thesis, or a day.

## Known issues and planned

- Registration is an import-time side effect: a plugin exists only if its module was imported. Keep that, but make the list explicit (`runtime.plugins.DEFAULT_MODULES`, [M13](M13-runtime.md)).
- `identity_key` is new. It closes the gap where an imported actor's id depends on its spelling.

## Done when

- `tests/unit/core/` covers id stability, canonical JSON round-trips, substream reproducibility, tracer scoping and replay, and `register` rejecting a class that does not implement its slot's interface.
- The import-graph test ([M02](M02-ports.md#done-when)) passes with `core/` as a leaf.
