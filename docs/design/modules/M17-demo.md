# M17 · Demo

**Layer** side: it uses the product, and nothing in the product uses it. **Package** `demo/` (today `sim/`). **Status** split; the product paths leave.
**Code today:** `sim/world.py`, `scenario.py`, `runner.py`, `checklist.py`, `imports.py` (moves to M05/M13), `examples/`.

<!-- toc -->
**Contents**

- [Purpose](#purpose)
- [Owns](#owns)
- [Depends on](#depends-on)
- [Invariants](#invariants)
- [Done when](#done-when)
<!-- /toc -->

## Purpose

The demos and their synthetic world. The user guide is [../../demos.md](../../demos.md).
- **Small:** a blank canvas, built by 24 examples.
- **Production:** the same examples in the oil-shock world.
- **Full:** 53 actors and ideas, 18 scripted steps.
- **Emily's:** a PM's model, brought up to date by imports.

The data stays synthetic. Real names make the graph concrete, but nothing in it is a claim about any company.

## Owns

- `SyntheticWorld` and its truth, the scenario script, and the oil demo's checklist.
- The tutorial: examples and their articles, with a chain that rewinds and replays your decisions, plus "more like this".
- `DemoSession`, which implements [M14](M14-interfaces.md)'s `Session` and declares its capabilities.
- The fixture plugins it registers: the `synthetic_data_feed` source and the `example` translator.
- `data/worlds/`, `data/scenarios/`, `data/taxonomy/`; `configs/demo.yaml`, `small_demo.yaml`, `emily_demo.yaml`.

## Depends on

[M12](M12-runtime.md), [M13](M13-services.md).

## Invariants

- **Nothing in layers 0–5 imports `demo/`.**
- **Small demo first.** A feature is shown and tested there before the oil demo and its slow tests change.

## Done when

- The small demo (example by example, with rewind), production demo, and oil checklist tests pass.
