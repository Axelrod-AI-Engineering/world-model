# Module specs

One file per module, 17 in all. Each can be handed to an engineer or a coding agent on its own, together with [../architecture.md §2](../architecture.md#dependency-graph) (the layer rules). Every spec has the same sections:

<!-- toc -->
<!-- /toc -->

- **Purpose:** one or two sentences.
- **Owns:** the types and state only this module defines.
- **Interface:** the signatures other modules may call. Anything else is private.
- **Slots:** the swappable algorithms it implements: default → alternatives → planned.
- **Depends on:** the only modules it may import.
- **Diagrams:** the module's own flowcharts, sequences, and lifecycles.
- **Invariants:** what must always hold; a test checks each one.
- **Planned:** known issues and their fixes, citing [ml-stack](../../ml-stack.md) findings (S-, F-) and [ml-roadmap](../../ml-roadmap.md) items (R#).
- **Done when:** the tests that define the module as built.

The module list, by layer, is on the [design front page](../README.md#12-modules).

**Conventions in signatures:**
- `ctx` is a `ProcessContext`: config, rng substreams, tracer, clock, and scope.
- `txn` is a `MutationTxn` from [M04](M04-repo.md); `txn=None` means a read that writes nothing.
