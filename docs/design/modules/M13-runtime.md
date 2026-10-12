# M13 · Runtime

| | |
|---|---|
| Layer | 4 · Runtime |
| Status | **Split**: today `engine/` is both the kernel that everything imports and the composition root that imports everything |
| Code today | `engine/engine.py` (`Engine`, `build_engine`), `engine/config.py`, `engine/context.py`, `engine/defaults.py`, `engine/initialize.py`; `learning/task.py` (`LearningTask`), `inference/task.py` (`InferenceTask.run`); the day loop in `control/updates.py`; the staging sandbox in `control/stage.py` |
| Target | `axelrod_wm/runtime/`: `config.py`, `context.py`, `plugins.py` (the module list to import), `build.py` (the composition root), `tasks.py` (`LearningTask`, `InferenceTask`), `day.py` (the day loop), `bootstrap.py` (construction, seeds, history replay) |

## Purpose

This is where the system is assembled and run. The module:

- loads the config;
- imports the plugin modules;
- builds one instance per slot, injecting each component's dependencies through its constructor;
- wires the orchestrators that sequence the slots;
- defines **the day**, which is the system's step.

Nothing below this layer knows how it is assembled.

## Owns

- `EngineConfig`, `load_config(path, overrides)` (deep merge of `configs/default.yaml`, a scenario's yaml, and its `config_overrides`).
- `ProcessContext` (config, rng substreams, tracer, clock, scope, branch or live).
- `build_engine(config, storage) -> Engine`. The constructor resolves each parameter by name, in this order:
  1. a configured param;
  2. `config`;
  3. another slot, built recursively with cycle detection.

  It **never** passes `engine`. Today components take `engine: Any` and look up `engine.components[...]` at run time; that is the service-locator pattern this design removes.
- The orchestrators, which are not slots:
  - `SharedProcess` (in [M07](M07-shared-read.md), wired here);
  - `LearningTask` = WM learning, then LTM learning;
  - `InferenceTask` = a branch, the shared read, then `inference.forecast`;
  - `StructuralApplier`.
- `DayLoop`: predict → late folds → events → record → distill → close.
- `Sandbox`, a thin wrapper over `repo.Branch`, which runs learning on a copy and returns the staged change sets.
- `Initializer`: construction from a world's files, seeds, the history replay, and the init cache keyed by a hash of config, data, and code.

## Interface

```python
def build_engine(config: EngineConfig, storage: StorageBackend, tracer: Tracer) -> Engine

class Engine:                      # a plain container; holds state and built slots, no behavior beyond on_commit
    wm: WorkingMemory; ltm: LongTermMemory; repo: Repo; slots: Slots
    learning: LearningTask; inference: InferenceTask; structural: StructuralApplier
    def context(self, *, learn: bool, scope: str, branch: Branch | None = None) -> ProcessContext

class LearningTask:
    def run(self, event, now, day, *, confidence=None, ripple=None) -> LearningResult   # learn.working + learn.long_term
    def open_day(self, day) -> None
    def close_day(self, day, end) -> list[ProposalEvent]                                # record, distill, close

class InferenceTask:
    def run(self, thesis, version, *, watch) -> tuple[Forecast, Explanation]           # pure read on a branch

class Sandbox:
    def stage(self, event, *, keep, confidences, ripple) -> StagedChange               # on a Branch; live untouched
```

## Depends on / used by

- Depends on: every engine ([M06](M06-intake.md)–[M12](M12-evaluation.md)) and [M05](M05-repo.md).
- Used by: [M14](M14-services.md), and the CLI ([M17](M17-api-cli.md)) for `init`, `contracts`, and `flows`.

## Flow

[architecture.md §8](../architecture.md#8-the-day-loop-an-update-run) for the day; [§10](../architecture.md#staged-review-of-one-event) for staging.

## Invariants

- **The composition root is the only place that names implementations.** Engines name slots; config names implementations.
- **Orchestrators sequence slots and own no math.**
- **Sandboxes never swap attributes on the live engine.** Today `control/stage.py` replaces `engine.wm`, `engine.ltm`, the ledger, and the tracer in place, then restores them. Here a sandbox is a separate `Branch`.
- **The init cache rebuilds itself** when data, config, or engine code changes.

## Known issues and planned

- `max_networks` and `top_k_superentities` disagree between yaml and code. `bind_score`, `evidence_bonus`, and `step_days` are never read (ml-stack §12). A config test should fail on unread keys.

## Done when

- `build_engine` builds every slot alternative (the slow test exists).
- A test fails if any slot implementation's constructor takes `engine`.
- Staging the same event twice gives the same `StagedChange`, and the live hash never moves.
