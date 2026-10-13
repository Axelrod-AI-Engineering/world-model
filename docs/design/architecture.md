# Architecture: diagrams

Seven overview diagrams. The detail diagrams (each stage's own flowchart, the sequences, and the object lifecycles) live in the module spec they describe; [the index](#detail-diagrams) at the bottom lists them.

**Key:**
- **Thick purple arrows** are the happy path.
- 🟪 **Purple:** where a flow starts.
- 🟨 **Yellow:** a yes/no check.
- 🟧 **Peach:** a commit or stored data.
- 🟩 **Green:** working memory.
- 🟦 **Blue:** long-term memory.
- **Dashed:** runs only sometimes.

The colors match the app's own flowcharts and the README's overview ([../flowchart.svg](../flowchart.svg)). `scripts/docs/style_mermaid.py` applies them.

## 1. System map

Learning writes; inference only reads committed versions.

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart TD
  S1["News"]:::start & S2["Data releases"]:::start & S3["Import bundle<br/>axelrod.import/v1"]:::start & S4["Backend user<br/>draw · own knowledge"]:::start ==> INT["Intake · M05<br/>translate → refine"]:::step
  INT ==> SR["Shared read · M06<br/>parse · classify · recall · bind · prefill · analyze"]:::step
  SR ==> LWM["Learning · working memory · M08<br/>fold · hedges · ripple"]:::wm
  LWM ==> LLTM["Learning · long-term memory · M09<br/>kinds · Entity memories · frontier · superentities"]:::ltm
  LLTM ==> REV{"Human review · M13<br/>approve all, some, or none?"}:::check
  REV ==>|approved| REPO[("Commit · M04<br/>ledger · snapshots · versions")]:::store
  REPO ==> BR["Branch of a committed version<br/>never merged"]:::step
  BR ==> INF["Inference · M10<br/>isolate · predict · couple · weigh · unify"]:::both
  INF ==> FC["Forecast by order and path + brief"]:::done
  RA["Research agent (optional)"]:::ext -.-> S3
  DYN["Dynamics · M07<br/>kernels · propagation · daily filter"]:::step -.-> SR
  REV -->|rejected| LOG["Logged; nothing changes"]:::done
  TH["Pose a thesis"]:::start --> BR
  FC -.->|outcome at horizon| EVAL["Evaluation · M11<br/>track records"]:::opt
  REPO --> API["Views · API · CLI · M14"]:::step
  API --> WEB["Web · M16"]:::step
  API --> CTX["Context layer · M15"]:::step
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef step fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25
  classDef opt fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25
  classDef check fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600
  classDef store fill:#F7E1D3,stroke:#E0B092,stroke-width:1.3px,color:#2F2A25
  classDef done fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25
  classDef wm fill:#E1ECDF,stroke:#A9C6A9,stroke-width:1.3px,color:#3E6A46
  classDef ltm fill:#DCE6F0,stroke:#A9BFD6,stroke-width:1.3px,color:#3B5B7C
  classDef both fill:#F5E4E9,stroke:#D9A9B8,stroke-width:1.3px,color:#93465F
  classDef ext fill:#FBF8F2,stroke:#7C64C4,stroke-width:1.3px,stroke-dasharray:2 3,color:#2F2A25
  linkStyle 0,1,2,3,4,5,6,7,8,9,10,11 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

## 2. Module layers

Arrows point from a module to what it imports. Nothing points upward, so there are no cycles (the code today has several: [migration.md](migration.md#current-cycles)).

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart BT
  subgraph L0["Layer 0 · Foundation"]
    F["M01 foundation · core, ports"]:::start
  end
  subgraph L1["Layer 1 · Domain"]
    MODEL["M02 model"]:::step
  end
  subgraph L2["Layer 2 · State"]
    MEMORY["M03 memory"]:::store
    REPO["M04 repo"]:::store
  end
  subgraph L3["Layer 3 · Engines"]
    INTAKE["M05 intake"]:::step
    EVAL["M11 evaluation"]:::step
    LWM["M08 learning · WM"]:::wm
    LLTM["M09 learning · LTM"]:::ltm
    INF["M10 inference"]:::both
    SHARED["M06 shared read"]:::step
    DYN["M07 dynamics"]:::step
  end
  subgraph L4["Layer 4 · Runtime"]
    SVC["M13 services"]:::check
    RT["M12 runtime"]:::check
  end
  subgraph L5["Layer 5 · Interfaces"]
    WEB["M16 web"]:::step
    CTX["M15 context layer"]:::step
    API["M14 views · API · CLI"]:::step
  end
  L1 ==> L0
  L2 ==> L1
  L3 ==> L2
  L4 ==> L3
  L5 ==> L4
  REPO --> MEMORY
  LWM & LLTM & INF --> SHARED
  SHARED --> DYN
  SVC --> RT
  CTX --> API
  WEB -.->|HTTP · /ws| API
  DEMO["M17 demo (side)"]:::ext -.-> L4
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef step fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25
  classDef check fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600
  classDef store fill:#F7E1D3,stroke:#E0B092,stroke-width:1.3px,color:#2F2A25
  classDef wm fill:#E1ECDF,stroke:#A9C6A9,stroke-width:1.3px,color:#3E6A46
  classDef ltm fill:#DCE6F0,stroke:#A9BFD6,stroke-width:1.3px,color:#3B5B7C
  classDef both fill:#F5E4E9,stroke:#D9A9B8,stroke-width:1.3px,color:#93465F
  classDef ext fill:#FBF8F2,stroke:#7C64C4,stroke-width:1.3px,stroke-dasharray:2 3,color:#2F2A25
  linkStyle 0,1,2,3,4 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

Rules:
- **Algorithms never take the engine.** A slot gets its inputs, a context, and a transaction (or `None` for a read).
- **Algorithms return proposals; services create them.**
- **State never imports algorithms.**
- **Nothing below layer 5 imports views, the API, or the demo.**

## 3. Learning: five stages

Each stage's own flowchart is in its module: [M05](modules/M05-intake.md), [M08](modules/M08-learning-working.md), [M09](modules/M09-learning-long-term.md), [M13](modules/M13-services.md).

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart TD
  A["Market event, or a backend user's edit"]:::start ==> I["1 · Intake<br/>translate → refine"]:::step
  I ==> W["2 · Learning · working memory<br/>apply → classify → recall → ripple → fold → hedges"]:::wm
  W ==> L["3 · Learning · long-term memory<br/>kinds → Entity memories → frontier → superentities"]:::ltm
  L ==> R{"4 · Human review<br/>does every change make sense?"}:::check
  R ==>|approve selection| C[("5 · Commit<br/>learn.working · learn.long_term")]:::store
  C ==> V["New version<br/>inference reads committed versions only"]:::done
  R -->|deselect some: re-stage| W
  R -.->|defer| Q["Folds in late, once approved"]:::opt
  R -->|reject| X["Nothing changes (logged)"]:::done
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef step fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25
  classDef opt fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25
  classDef check fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600
  classDef store fill:#F7E1D3,stroke:#E0B092,stroke-width:1.3px,color:#2F2A25
  classDef done fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25
  classDef wm fill:#E1ECDF,stroke:#A9C6A9,stroke-width:1.3px,color:#3E6A46
  classDef ltm fill:#DCE6F0,stroke:#A9BFD6,stroke-width:1.3px,color:#3B5B7C
  linkStyle 0,1,2,3,4,5 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

## 4. Inference: six stages

Nothing here writes to either memory. The sequence is in [M10](modules/M10-inference.md).

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart TD
  Q["A what-if question<br/>Pose a thesis"]:::start ==> ONE{"1 · Does every end name one value?"}:::check
  ONE -->|no| ASK["Ask the asker to pick; nothing runs"]:::done
  ONE ==>|yes| BR["Branch a committed version; apply the event"]:::step
  BR ==> ISO["2 · Isolate the networks<br/>superentities reached · residual · watched names · rivals"]:::both
  ISO ==> SIM["3 · Simulate each network alone,<br/>then couple per scenario, ± shock on the same draws"]:::both
  SIM ==> MIX["4 · Weigh and unify<br/>mix scenarios by support × fit × track record"]:::both
  MIX ==> RO["5 · Read out and explain<br/>order · path · arrival · peak · groups · brief"]:::step
  RO ==> FC["Forecast + brief"]:::done
  FC -.->|someone acts on it| SC["6 · Score against outcomes<br/>CRPS; track records update"]:::opt
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef step fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25
  classDef opt fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25
  classDef check fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600
  classDef done fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25
  classDef both fill:#F5E4E9,stroke:#D9A9B8,stroke-width:1.3px,color:#93465F
  linkStyle 0,2,3,4,5,6,7 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

## 5. The day loop

The system's step: one update run, which pauses on a day while a proposal waits.

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "actorBkg": "#DAD0F4", "actorBorder": "#7C64C4", "actorLineColor": "#C9BFAF", "signalColor": "#857C70", "labelBoxBkgColor": "#F5EAC6", "labelBoxBorderColor": "#D2BB72", "noteBkgColor": "#F5EAC6", "noteBorderColor": "#D2BB72", "activationBkgColor": "#E1ECDF", "sequenceNumberColor": "#FFFDF8"}}}%%
%% style: end
sequenceDiagram
  autonumber
  participant U as Backend user / scheduler
  participant US as UpdateService (M13)
  participant SRC as Sources (M05)
  participant IP as IngestionPipeline (M05)
  participant RS as ReviewService (M13)
  participant LT as LearningTask (M12)
  participant R as Repo (M04)

  U->>US: request_update(until, sources)
  US->>SRC: poll(since=cursor, until)
  SRC-->>US: market events (deduped, queued by day)
  loop each day d
    US->>LT: open_day(d)  [day.predict]
    US->>LT: fold the late queue
    loop each market event on d
      US->>IP: ingest(event)  translate → refine
      IP->>RS: propose(graph_update, world=true)
      RS->>RS: review_policy.assess
      alt auto-approved
        RS->>LT: run(event)  [learn.working, learn.long_term]
      else needs review
        RS-->>US: AWAITING_REVIEW (run pauses)
        Note over U,RS: the user stages and approves (see M13)
        RS->>US: resume(run)
        US->>LT: run(approved selection)
      end
    end
    US->>LT: close_day(d)  [day.record, day.distill, day.close]
    LT-->>RS: proposal events (collapse, promotion, resolution)
    US->>R: snapshot every N days
  end
  US-->>U: UpdateReport
```

## 6. The ledger lifecycle

Every write takes this path. It is modeled on Semantica's decision lifecycle.

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart LR
  ME["Market event<br/>MARKET_EVENT"]:::start ==> PR["Proposal<br/>PROPOSAL"]:::step
  PR ==> SB["Staged on a branch<br/>throwaway ledger"]:::opt
  SB ==> RV{"Review decision<br/>REVIEW_DECISION"}:::check
  RV ==>|approved selection| CS[("ChangeSet<br/>process · memory · proposal · vetted_by")]:::store
  CS ==> SV[("StateVersion<br/>hash · seq")]:::store
  SV --> AUD["log · show · diff · restore · as_of · PROV export"]:::done
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef step fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25
  classDef opt fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25
  classDef check fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600
  classDef store fill:#F7E1D3,stroke:#E0B092,stroke-width:1.3px,color:#2F2A25
  classDef done fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25
  linkStyle 0,1,2,3,4 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

- **Ledger kinds:** construction, update, market_event, proposal, review_decision, changeset, thesis, forecast, evaluation, decision, outcome, consolidation.
- **Commit processes:** construction, history, intake, day.predict, learn.working, learn.long_term, day.record, day.distill, day.close, structural, review, hypothesis, forecast (no version bump), evaluation, other.

## 7. Data model

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2"}}}%%
%% style: end
classDiagram
  direction LR
  class Entity {
    id
    name
    kind: company|agency|market|macro_factor|...
    aliases
    subentity_ids
    generalization_id
    origin
  }
  class Subentity {
    id = entity.slug
    attribute_kind
    unit · scale · anchor · link
    prior · posterior
    constraints (soft bounds)
  }
  class Interaction {
    id
    source_id → Subentity
    target_id → Subentity
    label · edge_type
    existence: Beta
    forward/reverse: EdgeDynamics(effect, kernel)
    parameters (moderators)
    evidence
    time_states (bitemporal)
  }
  class KernelSpec {
    delay · lag · duration
  }
  class SuperentityPattern {
    roles · relations
    sub_pattern_ids
    support · status
    rival_ids · track_record
  }
  class SuperentityInstance {
    pattern_id
    bindings role → entity
    interaction_ids
    child_instance_ids
  }
  class Evidence {
    source_type · source_ref
    excerpt · observed_at
    strength · market_event_id
  }
  class MarketEvent {
    id · kind · channel
    published_at · occurred_at
    headline · body · url
  }
  class GraphUpdateEvent {
    id · kind: real|hypothetical
    ops: AddEntity|AddSubentity|ObserveValue|ChangeValue|
    AddInteraction|Reweight|Annotate|ProposeHypothesis|
    ProposeSuperentity|DissolveSuperentity|RetireEntity|RetireInteraction
    specificity
  }
  class Thesis {
    question · mode · horizon_days
    event: GraphUpdateEvent
    targets · target_groups
  }
  class Proposal {
    kind · status
    event · refinement steps
    review requirement
  }
  class ChangeSet {
    process · memory
    changes
    proposal_id · vetted_by
  }
  class Forecast {
    based_on_version · seed · config_hash
    scenarios · densities
    transmission paths
  }
  class Hypothesis {
    claim · probability · voi
  }
  Entity "1" *-- "many" Subentity
  Interaction --> Subentity : source
  Interaction --> Subentity : target
  Interaction *-- KernelSpec
  Interaction o-- Evidence
  SuperentityInstance --> SuperentityPattern
  SuperentityInstance --> Entity : binds
  SuperentityPattern --> SuperentityPattern : sub-patterns
  MarketEvent --> GraphUpdateEvent : translated into
  GraphUpdateEvent --> Proposal : wrapped by
  Proposal --> ChangeSet : approved into
  Thesis --> GraphUpdateEvent : hypothetical
  Thesis --> Forecast : answered by
  Hypothesis --> Interaction : about
```

How the two memories feed each other is drawn in [M03](modules/M03-memory.md).

## Detail diagrams

| Diagram | In |
|---|---|
| Intake, step by step; a fuzzy end's lifecycle | [M05 intake](modules/M05-intake.md) |
| The shared read | [M06 shared read](modules/M06-shared-read.md) |
| Learning · working memory, step by step; a hypothesis's lifecycle | [M08 learning · WM](modules/M08-learning-working.md) |
| Learning · long-term memory, per event and per day; a superentity's lifecycle | [M09 learning · LTM](modules/M09-learning-long-term.md) |
| Pose a thesis, as a sequence | [M10 inference](modules/M10-inference.md) |
| Review and commit; a staged review as a sequence; a proposal's lifecycle | [M13 services](modules/M13-services.md) |
| An agent through the context layer | [M15 context layer](modules/M15-context-layer.md) |
| The two memories and their commits | [M03 memory](modules/M03-memory.md) |
| The standard retrieval stack vs the model's memory | [cognition.md](cognition.md#the-difference-in-one-picture) |
| Cognee and Semantica around the model | [frameworks.md](frameworks.md#recommendation) |
| The hosted deployment | [../deployment.md](../deployment.md) |
