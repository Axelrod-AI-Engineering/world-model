# Architecture: diagrams

The overview diagrams, in Mermaid, so they render on GitHub and a coding agent can read them as text. Each box reads `Stage (package) · module`. Parallelograms are data; rectangles are processing. The detail diagrams, such as each stage's own flowchart, the sequences, and object lifecycles, live in the module spec they describe ([index below](#detail-diagrams)).

## 1. System map

Learning writes; inference only reads committed versions.

```mermaid
flowchart TD
  subgraph SRC["Sources (intake.sources) · M05"]
    direction LR
    S1["News · scraper"]
    S2["Data releases · data feed"]
    S3["Import bundle<br/>axelrod.import/v1"]
    S4["Backend user<br/>draw · own knowledge · structure edits"]
  end
  RA["Research agent (optional)<br/>Cognee-backed research memory"] -.-> S3
  S1 & S2 & S3 & S4 --> ME[/"Market events"/]

  ME --> INT["Intake (intake) · M05<br/>Translator · EntityResolver · Refiner"]
  INT --> GUE[/"Graph update event<br/>operations with concrete or hedged ends"/]

  GUE --> SR["Shared read (shared) · M06<br/>parse · classify · recall · bind · prefill · analyze"]
  SR --> LWM["Learning · working memory · M08<br/>Folder · hedges · ripple judgments"]
  SR --> LLTM["Learning · long-term memory · M09<br/>kinds · Entity memories · correlation frontier · inducer"]
  DYN["Dynamics (dynamics) · M07<br/>Propagator · DailyPropagator · kernels"] -.-> SR & LWM

  LWM & LLTM --> STG[/"Staged change<br/>structure · moves · ripple by order · lessons"/]
  STG --> REV{"Human review · M13<br/>approve all, some, or none"}
  REV -- "approved selection" --> REPO["Commit (repo) · M04<br/>GraphMutator · ChangeSet · Ledger · Snapshots"]
  REV -- "rejected" --> LOG[/"Logged, nothing changes"/]
  REPO --> MEM[/"Committed version<br/>working memory + long-term memory (memory · M03)"/]

  MEM --> BR["Branch of a committed version<br/>never merged"]
  TH[/"Thesis (Pose a thesis)"/] --> BR
  BR --> INF["Inference (inference) · M10<br/>isolate · predict · couple · weigh · unify"]
  SR -.-> INF
  INF --> FC[/"Forecast<br/>values by order and transmission path · brief"/]
  FC --> EVAL["Evaluation (evaluation) · M11<br/>Scorer · track records · decisions"]
  EVAL -- "track records only" --> MEM

  MEM & FC & STG --> VIEWS["Views (views) · M14"]
  VIEWS --> API["API and CLI · M14<br/>REST · /ws · CLI"]
  VIEWS --> CTX["Context layer (context) · M15<br/>MCP: recall · ask · trace · propose · feedback"]
  API --> WEB["Web · M16<br/>Learn · Predict"]
  CTX --> AG["Agents and analysts"]
  CTX -. "propose: staged like an article" .-> S4
```

## 2. Module layers

Arrows point from a module to what it imports. Nothing points upward, so there are no cycles (the code today has several: [migration.md](migration.md#current-cycles)).

```mermaid
flowchart BT
  subgraph L0["Layer 0 · Foundation"]
    F["M01 foundation<br/>core: ids · serialization · rng · trace bus · registry<br/>ports: slot ABCs · records · contracts"]
  end
  subgraph L1["Layer 1 · Domain"]
    MODEL["M02 model<br/>entities · interactions · superentities · events · thesis"]
  end
  subgraph L2["Layer 2 · State"]
    MEMORY["M03 memory<br/>WorkingMemory · LongTermMemory"]
    REPO["M04 repo<br/>mutator · ledger · snapshots · branches"]
  end
  subgraph L3["Layer 3 · Engines (slot implementations)"]
    INTAKE["M05 intake"]
    SHARED["M06 shared read"]
    DYN["M07 dynamics"]
    LWM["M08 learning · WM"]
    LLTM["M09 learning · LTM"]
    INF["M10 inference"]
    EVAL["M11 evaluation"]
  end
  subgraph L4["Layer 4 · Runtime"]
    RT["M12 runtime<br/>composition root · orchestrators · day loop · sandbox"]
    SVC["M13 services<br/>review · update · thesis · structure · sources"]
  end
  subgraph L5["Layer 5 · Interfaces"]
    API["M14 views · API · CLI"]
    CTX["M15 context layer"]
    WEB["M16 web"]
  end
  DEMO["M17 demo (side)<br/>synthetic world · scenarios · examples"]

  MODEL --> F
  MEMORY --> MODEL
  REPO --> MEMORY
  INTAKE & SHARED & DYN & LWM & LLTM & INF & EVAL --> MEMORY
  SHARED --> DYN
  LWM & LLTM & INF --> SHARED
  RT --> INTAKE & LWM & LLTM & INF & EVAL & REPO
  SVC --> RT
  API --> SVC
  CTX --> SVC & API
  WEB -. "HTTP · /ws" .-> API
  DEMO --> SVC
```

- **Algorithms never take the engine.** A slot gets its inputs, a `ProcessContext`, and a `MutationTxn` (or `None` for a read). It never looks up `engine.components[...]`.
- **Algorithms return proposals; services create them.**
- **State never imports algorithms.**
- **Nothing below layer 5 imports views, the API, or the demo.**

## 3. Learning: five stages

Generated from `flows/` ([../flowchart.svg](../flowchart.svg) is the same picture). Each stage's own flowchart is in its module.

```mermaid
flowchart TD
  A[/"Market event or backend user's edit"/] --> I["1 · Intake · M05<br/>translate → refine"]
  I --> G[/"Graph update event"/]
  G --> W["2 · Learning · working memory · M08<br/>apply → classify → recall → bind → prefill → ripple → fold → hedges"]
  W --> L["3 · Learning · long-term memory · M09<br/>kinds → Entity memories → frontier → superentity support → explain"]
  L --> S[/"Staged change: structure, moves, ripple by order, lessons"/]
  S --> R{"4 · Human review · M13<br/>does every change make sense?"}
  R -- "deselect some" --> W
  R -- "defer" --> Q[/"Waits; folds in late once approved"/]
  R -- "reject" --> X[/"Nothing changes (logged)"/]
  R -- "approve selection" --> C["5 · Commit · M04<br/>WM commit · LTM commit"]
  C --> V[/"New version · inference reads committed versions only"/]
```

## 4. Inference: six stages

Nothing here writes to either memory.

```mermaid
flowchart TD
  Q[/"A what-if question, in Predict (Pose a thesis)"/] --> RD["1 · Pose a thesis<br/>read into a hypothetical event: a shock, or a decision held (do())"]
  RD --> ONE{"Does every end name one value?"}
  ONE -- no --> ASK[/"Ask the asker to pick (nothing runs)"/]
  ONE -- yes --> BR["Branch a committed version; apply the event<br/>(the branch is never merged)"]
  BR --> ISO["2 · Isolate the networks<br/>superentities the shock reaches; residual network;<br/>context network for watched names; rivals marked<br/>(slot: isolator, rival_detector)"]
  ISO --> ALONE["3 · Simulate and couple<br/>each network alone (slot: network_predictor)"]
  ALONE --> SCN["Scenarios: one per choice among rivals ×<br/>each valuable, undecided hypothesis (slot: hypothesis_scorer)"]
  SCN --> CPL["Couple per scenario, with and without the shock,<br/>on the same draws (slot: coupler)"]
  CPL --> W["4 · Weigh and unify<br/>support × fit × track record × p(hypothesis)<br/>(slot: scenario_weighter)"]
  W --> MIX["Mix scenarios by weight into one forecast (slot: unifier)"]
  MIX --> RO["5 · Read out and explain<br/>each value: order, path, arrival, peak;<br/>groups draw by draw; binding constraints;<br/>ablate key interactions; brief (slot: explainer)"]
  RO --> FC[/"Forecast + brief (nothing learned)"/]
  FC --> ACT{"Does someone act on it?"}
  ACT -- no --> END[/"Stays in the forecast layer"/]
  ACT -- yes --> REC["6 · Score against outcomes<br/>record the decision with the version it read"]
  REC --> HZ{"Horizon passed?"}
  HZ -- no --> WAIT["Wait; learning goes on"] --> HZ
  HZ -- yes --> SC["Score (CRPS); superentities used gain track record<br/>(slot: scorer)"]
```

## 5. The day loop

The system's step: one update run, paused on a day while a proposal waits.

```mermaid
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
        Note over U,RS: the user stages and approves (see §10)
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

Modeled on Semantica's decision lifecycle. Every write takes this path.

```mermaid
flowchart LR
  subgraph S1["1 · Record"]
    ME["Market event<br/>MARKET_EVENT"]
    PR["Proposal<br/>PROPOSAL"]
  end
  subgraph S2["2 · Stage"]
    SB["Sandbox branch<br/>throwaway ledger"]
  end
  subgraph S3["3 · Govern"]
    RV["Review decision<br/>REVIEW_DECISION<br/>who · confidence · selection"]
  end
  subgraph S4["4 · Commit"]
    CS["ChangeSet<br/>CHANGESET<br/>process · memory · proposal · vetted_by"]
    SV["StateVersion<br/>hash · seq"]
  end
  subgraph S5["5 · Audit and restore"]
    LOG["log · show · diff"]
    RST["restore = snapshot + change sets<br/>(hash verified)"]
    ASOF["as_of(t)"]
    PROV["PROV export<br/>entity · activity · agent"]
  end
  ME -- "proposal_id" --> PR --> SB -- "staged change sets" --> RV
  RV -- "approved selection" --> CS --> SV
  SV --> LOG & RST & ASOF & PROV
```

Ledger kinds: construction, update, market_event, proposal, review_decision, changeset, thesis, forecast, evaluation, decision, outcome, consolidation. Commit processes: construction, history, intake, day.predict, learn.working, learn.long_term, day.record, day.distill, day.close, structural, review, hypothesis, forecast (no version bump), evaluation, other.

## 7. Data model

```mermaid
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

Memory, as state:

```mermaid
flowchart LR
  subgraph WM["WorkingMemory (M03) — what the world is like now"]
    G["graph: CausalGraph"]
    DV["deviations (z per value per day)"]
    CH["channels (kernel recursion states)"]
    HY["hypotheses — the hypothesis frontier"]
    PRF["pending refinements (hedges)"]
    RJ["ripple judgments"]
    FL["forecast layer (outside the hash)"]
    AUX["activity log · episode buffer · late queue · source cursors · clock"]
  end
  subgraph LTM["LongTermMemory (M03) — what generalizes"]
    OG["Object generalizations<br/>kinds + superentity patterns"]
    IG["Interaction generalizations"]
    EMM["Entity memories<br/>decisions by context"]
    CF["Correlation frontier<br/>co-movements with no interaction"]
    PS["Prior states<br/>episodes · explanations"]
  end
  WM -- "day.distill" --> LTM
  LTM -- "priors · analogs · patterns" --> WM
```

## 8. Deployment

```mermaid
flowchart LR
  B["Browser"] -- "HTTPS · cookie session" --> RW
  AGT["Agent (MCP)"] -. "planned" .-> RW
  subgraph RW["Railway dev · service world-model (one replica)"]
    APP["FastAPI app<br/>/api · /ws · /login · static web/"]
    ENG["One engine per login<br/>(var/axelrod/demo-‹user›)"]
    APP --> ENG
  end
  ENG --> VOL[("Volume /app/var<br/>ledger.jsonl · versions.jsonl<br/>snapshots/*.json.gz · traces · init cache")]
  GH["GitHub main"] -- "push = release" --> RW
```

## Detail diagrams

| Diagram | In |
|---|---|
| Intake, from an article to a graph update event; a fuzzy end's lifecycle | [M05 intake](modules/M05-intake.md) |
| Learning · working memory, step by step; a hypothesis's lifecycle | [M08 learning · WM](modules/M08-learning-working.md) |
| Learning · long-term memory, per event and per day; a superentity's lifecycle | [M09 learning · LTM](modules/M09-learning-long-term.md) |
| Pose a thesis, as a sequence | [M10 inference](modules/M10-inference.md) |
| Human review and commit; staged review as a sequence; a proposal's lifecycle | [M13 services](modules/M13-services.md) |
| An agent through the context layer | [M15 context layer](modules/M15-context-layer.md) |
| The two memories and their commits | [M03 memory](modules/M03-memory.md) |
| The shared read | [M06 shared read](modules/M06-shared-read.md) |
| Cognee and Semantica around the model | [frameworks.md](frameworks.md#recommendation) |
| The standard retrieval stack vs the model's memory | [cognition.md](cognition.md#the-difference-in-one-picture) |
