# M12 · Runtime

**Layer** 4 · **Package** `runtime/` · **Status** split. Today `engine/` is both the kernel that everything imports and the composition root that imports everything.

**Code today:**
- `engine/engine.py`, `config.py`, `context.py`, `defaults.py`, `initialize.py`;
- `learning/task.py`, `inference/task.py`;
- the day loop in `control/updates.py`;
- the sandbox in `control/stage.py`.

## Purpose

Assemble the system and run it. Runtime does five things:
- loads the config;
- imports the plugins;
- builds one instance per slot, injecting dependencies through constructors;
- wires the orchestrators that sequence the slots;
- defines **the day**, the system's step.

Nothing below this layer knows how it is assembled.

## Owns

- `EngineConfig`, `load_config` (merges default.yaml, the scenario's yaml, and its overrides), and `ProcessContext`.
- `build_engine`. A constructor parameter resolves, in order, to: a configured param, `config`, then another slot. Never `engine`. Today components take `engine: Any` and look up `engine.components[...]` at run time; that service-locator pattern goes.
- The orchestrators, which own no math:
  - `LearningTask` (WM, then LTM);
  - `InferenceTask` (branch → shared read → forecast);
  - `StructuralApplier`.
- `DayLoop`: predict → late folds → events → record → distill → close.
- `Sandbox`, over `repo.Branch`.
- `Initializer`: construction, seeds, the history replay, and the init cache (keyed by a hash of config, data, and code).

## Interface

```python
build_engine(config, storage, tracer) -> Engine        # a container: wm, ltm, repo, slots, learning, inference, structural
Engine.context(*, learn, scope, branch=None) -> ProcessContext
LearningTask.run(event, now, day, *, confidence=None, ripple=None) -> LearningResult
LearningTask.open_day(day); .close_day(day, end) -> list[ProposalEvent]
InferenceTask.run(thesis, version, *, watch) -> (Forecast, Explanation)
Sandbox.stage(event, *, keep, confidences, ripple) -> StagedChange   # on a Branch; live untouched
```

## Depends on

The engines ([M05](M05-intake.md)–[M11](M11-evaluation.md)) and [M04](M04-repo.md).

## Diagram

The day loop is in [architecture.md §5](../architecture.md#5-the-day-loop).

## Invariants

- **Only the composition root names implementations.**
- **Sandboxes never swap attributes on the live engine.**
- **The init cache rebuilds** when data, config, or code changes.
- **Every config key is read.** Today `bind_score`, `evidence_bonus`, and `step_days` are not.

## Done when

- Every slot alternative builds.
- No slot constructor takes `engine`.
- Staging the same event twice gives the same result, and the live hash never moves.
