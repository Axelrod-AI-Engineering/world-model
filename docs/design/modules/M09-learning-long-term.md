# M09 · Learning · long-term memory

**Layer** 3 · **Package** `learning/long_term/` · **Status** exists; this gathers pieces now scattered across `learning/`, `memory/`, and `shared/`.

**Code today:**
- `learning/long_term.py`, `generalize.py`, `frontier_test.py`, `consolidate.py`, `abduction.py:count`, `structural.py`;
- `memory/long_term.py:SuperInteractionBuilder`;
- the incorporate half of `shared/classify.py`.

## Purpose

What an event teaches across time and entities:

- **Kinds** learn from their members and pass priors to newcomers.
- **Entity memories** remember each actor's decisions by context.
- The **correlation frontier** pairs unexplained moves, and proposes an interaction once a pair keeps holding.
- **Superentity induction** proposes a collapse when a group of interactions keeps firing together, and an expansion when one fades.
- **Distillation** turns each day into an episode.

[cognition.md](../cognition.md) gives the reasons for this organization (F2–F9).

## Interface

```python
LongTermLearning.register(wm_result, ctx, txn) -> LTMResult      # learn.long_term: incorporate → kinds → decisions → frontier → explain
LongTermLearning.distill(day, ctx, txn) -> ConsolidationReport   # day.distill: episode → analogs → induction → entity memories → decay → splits
StructuralApplier.apply(event, ctx, txn)                         # structural: approved collapse, expand, retire, drawn edits
GeneralizationUpdater.update(classifications, ltm, ctx, txn)
TaxonomyGrower.maybe_split(taxonomy, gen_id, ctx, txn) -> list[str]
FrontierTester.test(fold, wm, ltm, ctx, txn) -> FrontierResult
PromotionTest.passes(co, recognition, cfg) -> bool
SuperentityInducer.count(day, wm, ltm, ctx, txn) -> InductionResult
Consolidator.run(day, ctx) -> ConsolidationReport
```

## Slots

| Slot | Default | Planned |
|---|---|---|
| `generalization_updater` | path_stats | R5: a measurement-error hierarchy, one entry per item |
| `taxonomy_grower` | shared_feature_split | Cobweb/Classit with an acuity cutoff **proposes**; the hierarchical likelihood decides |
| `frontier`, `promotion_test` | residual_comovement, threshold (support > 3, \|r\| ≥ 0.3, 75% consistency) | R2: residualize on the graph and factors; online FDR; PCMCI+ |
| `inducer` (count) | co_activation | Frequent-subgraph mining; Trellis-style chunks |
| `consolidator` | daily | |

## Depends on

[M01](M01-foundation.md)–[M03](M03-memory.md), [M06](M06-shared-read.md), [M07](M07-dynamics.md).

## Diagrams

Per event and per day:

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart TD
  subgraph PE["Per event · learn.long_term"]
    I["What working memory learned"]:::start ==> RT{"Retired anything?"}:::check
    RT ==>|no| GU["New items join their kinds;<br/>statistics update along the path"]:::ltm
    GU ==> CR{"Is a kind crowded?"}:::check
    CR ==>|no| DC{"Did an actor decide?"}:::check
    DC ==>|no| UX{"A move the graph did not explain?"}:::check
    UX ==>|no| EX["Explain what was learned; keep it in Prior states"]:::ltm
    RT -->|yes| FG["Retired items leave their kinds;<br/>frontier entries decay"]:::opt
    FG --> GU
    CR -->|yes| SP["Split: a new child kind"]:::opt
    SP --> DC
    DC -->|yes| EM["Record it in the actor's Entity memory"]:::opt
    EM --> UX
    UX -->|yes| FR["Pair it with earlier unexplained moves;<br/>propose an interaction once a pair holds"]:::opt
    FR --> EX
  end
  subgraph PD["Per day · day.distill"]
    EP["Summarize the day as an episode"]:::ltm ==> CT["Count which interactions fired together"]:::ltm
    CT ==> ADM{"A group's support above the admission threshold?"}:::check
    ADM ==>|no| FADE{"An admitted superentity below its floor?"}:::check
    FADE ==>|no| DONE["Staged lessons, and the proposals they raise"]:::done
    ADM -->|yes| COL["Propose a collapse into a superentity"]:::opt
    COL --> FADE
    FADE -->|yes| EXP["Propose an expansion back into its members"]:::opt
    EXP --> DONE
  end
  EX ==> EP
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef opt fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25
  classDef check fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600
  classDef done fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25
  classDef ltm fill:#DCE6F0,stroke:#A9BFD6,stroke-width:1.3px,color:#3B5B7C
  linkStyle 0,1,2,3,4,5,14,15,16,17,22 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

A superentity's lifecycle:

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "transitionColor": "#857C70", "transitionLabelColor": "#665E54", "compositeBackground": "#F7F2EA"}}}%%
%% style: end
stateDiagram-v2
  [*] --> candidate: a group of interactions fires together
  candidate --> candidate: support grows (+1 per spaced day) or decays
  candidate --> admitted: support > admission threshold and the collapse is approved
  [*] --> admitted: a backend user groups items (approved)
  admitted --> admitted: bound as instances; gains track record from forecasts
  admitted --> dissolved: support < floor and the expansion is approved, or the user dissolves it
  dissolved --> [*]
```

## Invariants

- **One commit per event** (`learn.long_term`) and one per day (`day.distill`).
- **Structure changes only through review.** Promotion, collapse, and expansion are all proposals. Splitting a kind changes only the taxonomy, and is logged.
- **Thresholds.** Support > 3 to admit or promote; support > 4 to supply priors or analogs.
- **The frontier is never propagated.** It runs on live vetted events only.
- **Forecasts don't enter long-term memory.** Today `consolidate.py` keeps forecast explanations; task T-12 removes that.

## Planned

- S-C4: kinds' priors collapse → R5.
- S-C2: induction confirms itself → R2.
- S-M6: the frontier has no valid inference → R2.
- Analog over-counting → R18.

## Done when

- Unit tests pass for kinds, splits, promotion after spaced checks, admission and dissolution, and decision profiles.
- Tutorial examples 8, 10, 11, and 15–22 pass.
