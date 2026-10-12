# Module specs

One file per module. Every spec has the same sections, so each one can be handed to an engineer or a coding agent on its own:

| Section | What it says |
|---|---|
| **Header** | Layer, status (exists, split, merge, or new), the code today, and the target package |
| **Purpose** | One or two sentences |
| **Owns** | The types and state this module is the only home of |
| **Interface** | The public signatures other modules may call. Anything not listed is private. |
| **Slots** | The swappable algorithms it implements, with the default and the alternatives (see [M02](M02-ports.md)) |
| **Depends on / used by** | Allowed imports, by module number. Anything else is a layering violation. |
| **Flow** | A diagram, where one helps. The pipelines are in [../architecture.md](../architecture.md). |
| **Invariants** | What must always hold. Tests check each one. |
| **Known issues and planned** | Links to [../../ml-stack.md](../../ml-stack.md) findings and [../../ml-roadmap.md](../../ml-roadmap.md) items (R#) |
| **Done when** | The tests that define the module as built |

| Layer | Modules |
|---|---|
| 0 Foundation | [M01 core](M01-core.md) · [M02 ports](M02-ports.md) |
| 1 Domain | [M03 model](M03-model.md) |
| 2 State | [M04 memory](M04-memory.md) · [M05 repo](M05-repo.md) |
| 3 Engines | [M06 intake](M06-intake.md) · [M07 shared read](M07-shared-read.md) · [M08 dynamics](M08-dynamics.md) · [M09 learning · WM](M09-learning-working.md) · [M10 learning · LTM](M10-learning-long-term.md) · [M11 inference](M11-inference.md) · [M12 evaluation](M12-evaluation.md) |
| 4 Runtime | [M13 runtime](M13-runtime.md) · [M14 services](M14-services.md) |
| 5 Interfaces | [M15 views](M15-views.md) · [M16 context layer](M16-context-layer.md) · [M17 api and cli](M17-api-cli.md) · [M18 web](M18-web.md) |
| Side | [M19 demo](M19-demo.md) |

**Signatures** use the code's names. `ctx` is a `ProcessContext` (config, rng substreams, tracer, clock, overlay). `txn` is a `MutationTxn` from [M05](M05-repo.md); `txn=None` means a read that writes nothing.
