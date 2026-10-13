# Module specs

One file per module, 17 in all. Each can be handed to an engineer or a coding agent on its own, together with [../architecture.md §2](../architecture.md#2-module-layers) (the layer rules). Every spec has the same sections:

- **Purpose:** one or two sentences.
- **Owns:** the types and state only this module defines.
- **Interface:** the signatures other modules may call. Anything else is private.
- **Slots:** the swappable algorithms it implements: default → alternatives → planned.
- **Depends on:** the only modules it may import.
- **Diagrams:** the module's own flowcharts, sequences, and lifecycles.
- **Invariants:** what must always hold; a test checks each one.
- **Planned:** known issues and their fixes, citing [ml-stack](../../ml-stack.md) findings (S-, F-) and [ml-roadmap](../../ml-roadmap.md) items (R#).
- **Done when:** the tests that define the module as built.

| Layer | Modules |
|---|---|
| 0 Foundation | [M01 foundation](M01-foundation.md) |
| 1 Domain | [M02 model](M02-model.md) |
| 2 State | [M03 memory](M03-memory.md) · [M04 repo](M04-repo.md) |
| 3 Engines | [M05 intake](M05-intake.md) · [M06 shared read](M06-shared-read.md) · [M07 dynamics](M07-dynamics.md) · [M08 learning · WM](M08-learning-working.md) · [M09 learning · LTM](M09-learning-long-term.md) · [M10 inference](M10-inference.md) · [M11 evaluation](M11-evaluation.md) |
| 4 Runtime | [M12 runtime](M12-runtime.md) · [M13 services](M13-services.md) |
| 5 Interfaces | [M14 views, API, CLI](M14-interfaces.md) · [M15 context layer](M15-context-layer.md) · [M16 web](M16-web.md) |
| Side | [M17 demo](M17-demo.md) |

**Conventions in signatures:**
- `ctx` is a `ProcessContext`: config, rng substreams, tracer, clock, and scope.
- `txn` is a `MutationTxn` from [M04](M04-repo.md); `txn=None` means a read that writes nothing.
