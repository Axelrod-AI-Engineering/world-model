# M01 · Foundation (core and ports)

**Layer** 0 · **Package** `core/`, `ports/` · **Status** split out: the pieces exist but are scattered.
**Code today:**
- core: `model/ids.py`, `model/serialization.py`, `engine/rng.py`, `engine/registry.py`, `trace.py`;
- ports: `engine/interfaces.py` (seven slots), `engine/contracts.py`, and ABCs in about fifteen implementation files.

<!-- toc -->
**Contents**

- [Purpose](#purpose)
- [Owns](#owns)
- [Interface: the slots](#interface-the-slots)
- [Depends on](#depends-on)
- [Invariants](#invariants)
- [Planned](#planned)
- [Done when](#done-when)
<!-- /toc -->

## Purpose

What every module needs, and what needs nothing in return: ids, canonical bytes, reproducible randomness, the trace bus, the slot registry, and **every slot's ABC and contract in one place**. Making this layer a leaf removes most of today's import cycles.

## Owns

- **core:**
  - `IdFactory`, `entity_of`;
  - **new** `identity_key(kind, **fields)`, a uuid5 over declared identity fields such as a ticker or LEI (from Cognee);
  - `canonical_json`, `sha256_text`, `substream(seed, *names)`;
  - `Tracer` with `NullTracer`, `RecordingTracer`, `BroadcastTracer`;
  - `registry(slot, ABC)` and `register(slot, name)`.
- **ports:** each slot's ABC, the records that cross slot boundaries (`ParsedEvent`, `SharedResult`, `FoldResult`, `Network`, `ForecastScenario`, `TranslationResult`, `RefinementResult`, `PropagationResult`, …), and `CONTRACTS[slot]` (process, cadence, inputs, outputs, reads, writes, condition).

## Interface: the slots

Every slot, with its signature, default, and alternatives, is in [interfaces.md](../interfaces.md#slots-where-algorithms-plug-in), grouped by stage. `uv run axelrod contracts` prints the contracts.

## Depends on

Nothing inside `axelrod_wm`, except that `ports/` uses [M02](M02-model.md)'s and [M03](M03-memory.md)'s types.

## Invariants

- `core/` is a leaf.
- Every slot ABC is defined in `ports/` and nowhere else.
- **Registry, contracts, and flowcharts agree.** Every slot has a contract, and every flowchart node names a slot. A test for this exists today.
- **Writes are declared.** A slot writes only the collections in its contract's `writes`.
- **Explicit randomness.** Every draw comes from a named substream, so the same seed and names give the same draws.

## Planned

- Generate the contracts' signature column from the ABCs, so the two cannot drift.
- `posterior_updater` is registered but never called (ml-stack §12). Wire it into the folder, or drop it.

## Done when

- `world_model/tests/unit/ports/test_layers.py` builds the import graph with `ast` and fails on an upward import or a cycle.
- Each slot has a conformance test: every registered implementation takes the same inputs, returns outputs of the right type, and writes only what its contract allows.
