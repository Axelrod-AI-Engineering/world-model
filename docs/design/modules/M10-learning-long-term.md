# M10 · Learning · long-term memory

| | |
|---|---|
| Layer | 3 · Engines |
| Status | **Exists**; gather the long-term pieces scattered across `memory/` and `learning/` |
| Code today | `learning/long_term.py`, `generalize.py`, `frontier_test.py`, `consolidate.py`, `abduction.py` (`count`), `structural.py`; `memory/long_term.py:SuperInteractionBuilder`; the `classify.incorporate` half in `shared/classify.py` |
| Target | `axelrod_wm/learning/long_term/`: `task.py` (`LongTermLearning`), `kinds.py` (generalize + taxonomy growth + incorporate), `entity_memory.py`, `frontier.py`, `induction.py` (count, admission, dissolution, super-interactions), `distill.py` (consolidator), `structural.py` |

## Purpose

What an event teaches across time and entities:

- **Kinds** (object and interaction generalizations) learn from their members and pass priors to newcomers.
- **Entity memories** remember each actor's decisions by context.
- The **correlation frontier** pairs moves the graph did not explain and proposes an interaction once a pair keeps holding.
- **Superentity induction** proposes a collapse when a group of interactions keeps firing together, and an expansion when one fades.
- **Distillation** turns each day into an episode for recall.

## Owns

- `LongTermLearning` with `register` (per event) and `distill` (per day).
- `GeneralizationUpdater`, `TaxonomyGrower`; `EntityMemory` updates; `FrontierTester`, `PromotionTest`; `SuperentityInducer.count`; `Consolidator`; `StructuralApplier` (approved collapse, expand, retire, and drawn edits).

## Interface

```python
class LongTermLearning:
    def register(self, wm_result: WMResult, ctx, txn) -> LTMResult        # [learn.long_term]
        # forget retired → classifier.incorporate → generalization_updater.update
        # → record decisions → frontier.test → explainer.explain_learning → episode buffer
    def distill(self, day: int, ctx, txn) -> ConsolidationReport          # [day.distill]
        # episode → analog responses → inducer.count → entity memories → frontier decay → taxonomy_grower

class StructuralApplier:
    def apply(self, proposal_event: GraphUpdateEvent, ctx, txn) -> None    # [structural]
```

## Slots

| Slot | Default | Alternatives | Planned |
|---|---|---|---|
| `generalization_updater` | path_stats | — | R5: a measurement-error hierarchy with τ² estimated and one entry per item |
| `taxonomy_grower` | shared_feature_split | none | Cobweb/Classit with an acuity cutoff **proposes** structure; the hierarchical likelihood decides (R5) |
| `frontier` | residual_comovement | — | R2: residualize on the graph and factors; a Freedman–Lane or CRT null; online FDR (LORD, SAFFRON, e-BH); LPCMCI/PCMCI+ |
| `promotion_test` | threshold (support > 3, \|r\| ≥ 0.3, 75% consistency) | — | R2: a sequential test with e-values |
| `inducer` (count half) | co_activation | — | Frequent-subgraph mining; TRELLIS-style chunks |
| `consolidator` | daily | — | |

## Representations (the plan for kinds)

As the methods briefing specifies:

- Embeddings need not be textual. They are built from **structured** inputs: profiles, factor exposures, responses to standard shocks, and position in the graph. Text is used only where the input is text.
- Embeddings go straight into **Cobweb, with no whitening**. An acuity cutoff floors the variance at the prior variance.
- There is **not one tree for everything**: one Cobweb tree per data structure (entities, subentities, interactions, episodes), plus trees over compositions of structures. A composite refers to its parts by the concepts they were sorted into (after Trellis and LABYRINTH).

Until R5 lands, `taxonomy_descent` and `shared_feature_split` remain the defaults, and the Cobweb trees are an alternative behind the same slots.

## Depends on / used by

- Depends on: [M01](M01-core.md)–[M04](M04-memory.md), [M07](M07-shared-read.md), [M08](M08-dynamics.md).
- Used by: [M13](M13-runtime.md).

## Flow

[architecture.md §6](../architecture.md#6-learning--long-term-memory), and the superentity lifecycle in [§12](../architecture.md#a-superentity-pattern).

## Invariants

- **One commit per event** (`learn.long_term`) and one per day (`day.distill`).
- **Structure changes only through review.** A promotion, collapse, expansion, or split into a new superentity is a proposal. Splitting a kind is the exception: it changes only the taxonomy and is logged.
- **Thresholds.** Support must be > 3 to admit or promote, and > 4 to supply priors or analogs (plan §3).
- **The frontier is never propagated.** Co-movements are counted, not used in forecasts.
- **Skipped during history replay**, for the frontier: it runs on live vetted events only.

## Known issues and planned

ml-stack §8 and §13:

- Kinds' statistics are pushed per touch, so priors collapse (S-C4) → R5.
- Superentity induction is self-confirming (S-C2) → R2 item 6.
- The frontier has no valid inference; its slope absorbs common drivers (S-M6) → R2.
- Analog pooling over-counts (plan.md "Oct 9") → R18.

## Done when

- `tests/unit/learning/` covers kind statistics, a split, frontier promotion after spaced checks, admission and dissolution proposals, and entity-memory decision profiles. The tutorial examples 8, 10, 11, 15–22 pass (`tests/scenario/test_small_demo.py`).
