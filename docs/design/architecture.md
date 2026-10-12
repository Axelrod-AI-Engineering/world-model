# Architecture: diagrams

Every diagram is Mermaid, so it renders on GitHub and coding agents can read it as text. Boxes name the module they belong to, in the form `Stage (package)`, with their main classes or slots under the name. Parallelogram nodes are data; rectangles are processing. Module numbers (M01–M19) link to the specs in [modules/](modules/).

1. [System map](#1-system-map)
2. [Module layers and dependencies](#2-module-layers-and-dependencies)
3. [Learning: the five stages](#3-learning-the-five-stages)
4. [Intake](#4-intake)
5. [Learning · working memory](#5-learning--working-memory)
6. [Learning · long-term memory](#6-learning--long-term-memory)
7. [Human review and commit](#7-human-review-and-commit)
8. [The day loop (an update run)](#8-the-day-loop-an-update-run)
9. [Inference: the six stages](#9-inference-the-six-stages)
10. [Sequences: review, thesis, agent](#10-sequences)
11. [The ledger lifecycle](#11-the-ledger-lifecycle)
12. [Lifecycles of model objects](#12-lifecycles-of-model-objects)
13. [Data model](#13-data-model)
14. [Deployment](#14-deployment)

---

## 1. System map

The whole system, from sources to interfaces. Learning writes; inference only reads committed versions.

```mermaid
flowchart TD
  subgraph SRC["Sources (intake.sources) · M06"]
    direction LR
    S1["News · scraper"]
    S2["Data releases · data feed"]
    S3["Import bundle<br/>axelrod.import/v1"]
    S4["Backend user<br/>draw · own knowledge · structure edits"]
  end
  RA["Research agent (optional)<br/>Cognee-backed research memory"] -.-> S3
  S1 & S2 & S3 & S4 --> ME[/"Market events"/]

  ME --> INT["Intake (intake) · M06<br/>Translator · EntityResolver · Refiner"]
  INT --> GUE[/"Graph update event<br/>operations with concrete or hedged ends"/]

  GUE --> SR["Shared read (shared) · M07<br/>parse · classify · recall · bind · prefill · analyze"]
  SR --> LWM["Learning · working memory · M09<br/>Folder · hedges · ripple judgments"]
  SR --> LLTM["Learning · long-term memory · M10<br/>kinds · Entity memories · correlation frontier · inducer"]
  DYN["Dynamics (dynamics) · M08<br/>Propagator · DailyPropagator · kernels"] -.-> SR & LWM

  LWM & LLTM --> STG[/"Staged change<br/>structure · moves · ripple by order · lessons"/]
  STG --> REV{"Human review · M14<br/>approve all, some, or none"}
  REV -- "approved selection" --> REPO["Commit (repo) · M05<br/>GraphMutator · ChangeSet · Ledger · Snapshots"]
  REV -- "rejected" --> LOG[/"Logged, nothing changes"/]
  REPO --> MEM[/"Committed version<br/>working memory + long-term memory (memory · M04)"/]

  MEM --> BR["Branch of a committed version<br/>never merged"]
  TH[/"Thesis (Pose a thesis)"/] --> BR
  BR --> INF["Inference (inference) · M11<br/>isolate · predict · couple · weigh · unify"]
  SR -.-> INF
  INF --> FC[/"Forecast<br/>values by order and transmission path · brief"/]
  FC --> EVAL["Evaluation (evaluation) · M12<br/>Scorer · track records · decisions"]
  EVAL -- "track records only" --> MEM

  MEM & FC & STG --> VIEWS["Views (views) · M15"]
  VIEWS --> API["API and CLI · M17<br/>REST · /ws · CLI"]
  VIEWS --> CTX["Context layer (context) · M16<br/>MCP: recall · ask · trace · propose · feedback"]
  API --> WEB["Web · M18<br/>Learn · Predict"]
  CTX --> AG["Agents and analysts"]
  CTX -. "propose: staged like an article" .-> S4
```

---

## 2. Module layers and dependencies

Arrows point from a module to what it imports. No arrow points upward, so there are no cycles. The code today has several cycles; [migration.md](migration.md#current-cycles) lists them and the cuts that remove them.

```mermaid
flowchart BT
  subgraph L0["Layer 0 · Foundation"]
    CORE["M01 core<br/>ids · serialization · rng · trace bus · registry"]
    PORTS["M02 ports<br/>slot ABCs · record types · contracts"]
  end
  subgraph L1["Layer 1 · Domain"]
    MODEL["M03 model<br/>entities · interactions · superentities · events · thesis"]
  end
  subgraph L2["Layer 2 · State"]
    MEMORY["M04 memory<br/>WorkingMemory · LongTermMemory"]
    REPO["M05 repo<br/>mutator · ledger · snapshots · branches"]
  end
  subgraph L3["Layer 3 · Engines (slot implementations)"]
    INTAKE["M06 intake"]
    SHARED["M07 shared read"]
    DYN["M08 dynamics"]
    LWM["M09 learning · WM"]
    LLTM["M10 learning · LTM"]
    INF["M11 inference"]
    EVAL["M12 evaluation"]
  end
  subgraph L4["Layer 4 · Runtime"]
    RT["M13 runtime<br/>composition root · orchestrators · day loop · sandbox"]
    SVC["M14 services<br/>review · update · thesis · structure · sources"]
  end
  subgraph L5["Layer 5 · Interfaces"]
    VIEWS["M15 views"]
    CTX["M16 context layer"]
    API["M17 api · cli"]
    WEB["M18 web"]
  end
  DEMO["M19 demo (side)<br/>synthetic world · scenarios · examples"]

  PORTS --> CORE
  MODEL --> CORE
  PORTS --> MODEL
  MEMORY --> MODEL
  REPO --> MEMORY
  INTAKE & SHARED & DYN & LWM & LLTM & INF & EVAL --> PORTS
  INTAKE & SHARED & DYN & LWM & LLTM & INF & EVAL --> MEMORY
  SHARED --> DYN
  LWM & LLTM --> SHARED
  INF --> SHARED
  RT --> INTAKE & LWM & LLTM & INF & EVAL & REPO
  SVC --> RT
  VIEWS --> SVC
  CTX --> SVC & VIEWS
  API --> SVC & VIEWS
  WEB -. "HTTP · /ws" .-> API
  DEMO --> SVC
```

Rules that keep the layers honest:

- **Algorithms never take the engine.** A slot gets its inputs, a `ProcessContext`, and a `MutationTxn` (or `None` for a read). It never looks up `engine.components[...]` at run time.
- **Algorithms return proposals; they don't create them.** Creating a proposal is a service's job (M14).
- **State never imports algorithms.** `memory/` holds pydantic state; kernels' recursion state and the `Forecast` record live in `model/`.
- **Nothing below layer 5 imports `api/`, `views/`, or `demo/`.**

---

## 3. Learning: the five stages

Learning's overview. It is generated from `flows/__init__.py`; [../flowchart.svg](../flowchart.svg) is the same picture.

```mermaid
flowchart TD
  A[/"Market event or backend user's edit"/] --> I["1 · Intake · M06<br/>translate → refine"]
  I --> G[/"Graph update event"/]
  G --> W["2 · Learning · working memory · M09<br/>apply → classify → recall → bind → prefill → ripple → fold → hedges"]
  W --> L["3 · Learning · long-term memory · M10<br/>kinds → Entity memories → frontier → superentity support → explain"]
  L --> S[/"Staged change: structure, moves, ripple by order, lessons"/]
  S --> R{"4 · Human review · M14<br/>does every change make sense?"}
  R -- "deselect some" --> W
  R -- "defer" --> Q[/"Waits; folds in late once approved"/]
  R -- "reject" --> X[/"Nothing changes (logged)"/]
  R -- "approve selection" --> C["5 · Commit · M05<br/>WM commit · LTM commit"]
  C --> V[/"New version · inference reads committed versions only"/]
```

---

## 4. Intake

From an article to a graph update event. An end binds only when the article names it; otherwise it stays hedged.

```mermaid
flowchart TD
  A[/"Article, data release, filing, or imported item"/] --> D{"Seen before?<br/>same address, or same site and title"}
  D -- yes --> DROP[/"Drop the duplicate (logged)"/]
  D -- no --> T{"A reviewed translation exists?"}
  T -- yes --> F["Use the reviewed fixture<br/>(translator: hand_drawn)"]
  T -- no --> TR["Translate<br/>template · data_feed · structured · llm<br/>(slot: translator)"]
  F & TR --> OPS{"Any operations?"}
  OPS -- no --> UN[/"Nothing to learn (logged as untranslated)"/]
  OPS -- yes --> NEXT["Take the next operation"]
  NEXT --> K{"Does an end name a kind<br/>(an airline) rather than a value?"}
  K -- no --> MORE
  K -- yes --> N["Narrow one level: kind → entity → subentity<br/>names, aliases, taxonomy (slot: refiner, entity_resolver)"]
  N --> NAMED{"Does the article name<br/>one candidate outright?"}
  NAMED -- yes --> BIND["Bind the end"]
  NAMED -- no --> HEDGE["Hedge: a probability per candidate<br/>+ an open share; soft interactions as strong as they are probable"]
  BIND --> VAL{"Is the end a value now?"}
  VAL -- no --> N
  VAL -- yes --> MORE{"More operations?"}
  HEDGE --> MORE
  MORE -- yes --> NEXT
  MORE -- no --> OUT[/"Graph update event<br/>operations whose ends are values, plus hedged ends"/]
```

---

## 5. Learning · working memory

What the world is like now. It runs on a staged copy during review, and on the live state once approved.

```mermaid
flowchart TD
  IN[/"Graph update event, on its day"/] --> OPEN["The day opens: yesterday's moves ripple forward<br/>(slot: daily_propagator, once per day)"]
  OPEN --> P["Apply each operation<br/>add or retire structure; a change becomes a shock;<br/>a report becomes an observation (slot: parser)"]
  P --> NEW{"New items?"}
  NEW -- yes --> CL["Sort each down its taxonomy; inherit the kind's priors<br/>(slot: classifier)"]
  NEW -- no --> RC
  CL --> RC["Recall superentities and past days with a matching signature<br/>(slot: recaller, attention)"]
  RC --> FIT{"Does a recalled superentity fit?"}
  FIT -- yes --> BD["Bind it as an instance;<br/>a relation it predicts but the graph lacks → proposal (slot: binder)"]
  FIT -- no --> PF
  BD --> PF["Build the working set: interactions near the event,<br/>adjusted by similar past days (slot: prefiller)"]
  PF --> MV{"Does the event move a value?"}
  MV -- yes --> AN["Simulate with and without the move on the same draws;<br/>each reached value gets an order, a path, a peak (slot: analyzer → propagator)"]
  MV -- no --> RP
  AN --> RP{"Does the event report a value?"}
  RP -- yes --> FO["Surprise = report − prediction;<br/>update the level and each incoming interaction by its share (slot: folder)"]
  RP -- no --> HG
  FO --> HG{"Hedged ends waiting?"}
  HG -- yes --> WH["Weigh each candidate by this event × your confidence<br/>(refiner.weigh_hedges)"]
  WH --> PASS{"One candidate past the bound?"}
  PASS -- yes --> RES["Propose the resolution (waits for review)"]
  PASS -- no --> OUT
  HG -- no --> OUT
  RES --> OUT[/"Staged working memory: structure, moves, ripple by order,<br/>updated values and effects, hedges' new odds"/]
```

---

## 6. Learning · long-term memory

What generalizes across time and entities. Per event and then per day.

```mermaid
flowchart TD
  subgraph PE["Per event"]
    I[/"What working memory learned"/] --> RT{"Retired anything?"}
    RT -- yes --> FG["Retired items leave their kinds; frontier entries decay"]
    RT -- no --> GU
    FG --> GU["New items join their kinds; statistics update along the path<br/>(slot: generalization_updater)"]
    GU --> CR{"Is a kind crowded?"}
    CR -- yes --> SP["Split: a new child kind (slot: taxonomy_grower)"]
    CR -- no --> DC
    SP --> DC{"Did an actor decide?"}
    DC -- yes --> EM["Record it in the actor's Entity memory, by context"]
    DC -- no --> UX
    EM --> UX{"A move the graph did not explain?"}
    UX -- yes --> FR["Pair it with earlier unexplained moves,<br/>after removing known drivers (slot: frontier)"]
    UX -- no --> EX
    FR --> HOLD{"Has a pair held at enough spaced checks?<br/>(slot: promotion_test)"}
    HOLD -- yes --> PP["Propose the pair as an interaction (waits for review)"]
    HOLD -- no --> EX
    PP --> EX["Explain what was learned; keep it in Prior states (slot: explainer)"]
  end
  subgraph PD["Per day (distillation)"]
    EP["Summarize the day as an episode (slot: consolidator)"] --> CT["Count which interactions were active together (slot: inducer)"]
    CT --> KN{"Matches a known superentity?"}
    KN -- yes --> SUP["It gains support"]
    KN -- no --> CAND["Record a candidate"]
    SUP & CAND --> ADM{"Candidate above the admission threshold?"}
    ADM -- yes --> COL["Propose a collapse into a superentity"]
    ADM -- no --> FADE
    COL --> FADE{"Admitted superentity below its floor?"}
    FADE -- yes --> EXP["Propose an expansion back into its members"]
    FADE -- no --> DONE
    EXP --> DONE[/"Staged lessons and the proposals they raise"/]
  end
  EX --> EP
```

---

## 7. Human review and commit

The review happens at the end of learning, on a staged copy of the whole event, ripple included. Deselecting re-stages.

```mermaid
flowchart TD
  ST[/"Every staged change: items, moves, ripple by order, lessons"/] --> SH["Show each change with the phrase that asked for it"]
  SH --> CONF["Set confidence: the article's and any change's own<br/>(re-stages; goes into the data written)"]
  CONF --> CHK["Check the event's own move, then each further order:<br/>sign follows from the path? size and timing plausible?"]
  CHK --> OK{"Does every change make sense?"}
  OK -- "no: deselect" --> RS["Re-stage without them<br/>on a fresh copy"] --> SH
  OK -- "not yet" --> DEF[/"Defer: approved later, it folds in late"/]
  OK -- "none" --> REJ[/"Reject with a note: nothing changes (logged)"/]
  OK -- "yes" --> AP["Approve the selection<br/>(deselected operations are edited out)"]
  AP --> EFF{"Does approval store anything?<br/>(pending ends, soft support, ripple judgments)"}
  EFF -- yes --> C0["▣ commit: review"]
  EFF -- no --> SE
  C0 --> SE{"A structural edit?"}
  SE -- yes --> C1["▣ commit: structural"]
  SE -- no --> C2["▣ commit: learn.working"]
  C2 --> C3["▣ commit: learn.long_term"]
  C1 & C3 --> LAST{"Day's last event?"}
  LAST -- yes --> C4["▣ day.record → ▣ day.distill → ▣ day.close"]
  LAST -- no --> PR
  C4 --> PR{"Proposals raised?<br/>(promoted pair, collapse, resolved end)"}
  PR -- yes --> QUEUE[/"Join the review queue; same review"/]
  PR -- no --> VER[/"New version in the log"/]
  QUEUE --> VER
```

---

## 8. The day loop (an update run)

There is no `Engine.step`. The day loop in the update service is the step. One run is active at a time, and it pauses on a day while a proposal waits.

```mermaid
sequenceDiagram
  autonumber
  participant U as Backend user / scheduler
  participant US as UpdateService (M14)
  participant SRC as Sources (M06)
  participant IP as IngestionPipeline (M06)
  participant RS as ReviewService (M14)
  participant LT as LearningTask (M13)
  participant R as Repo (M05)

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

---

## 9. Inference: the six stages

How the model answers a what-if question. Nothing here writes to either memory.

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

---

## 10. Sequences

### Staged review of one event

```mermaid
sequenceDiagram
  autonumber
  actor P as Reviewer
  participant W as Web (M18)
  participant RS as ReviewService (M14)
  participant SB as Sandbox (M13)
  participant LT as LearningTask (M13)
  participant V as Views (M15)
  participant R as Repo (M05)

  P->>W: open Review
  W->>RS: stage(proposal, keep=all, confidence)
  RS->>SB: branch(current version) — copy-on-write, throwaway ledger
  SB->>LT: open_day · review effects · run(event) · close_day
  LT-->>SB: staged change sets
  SB-->>RS: StagedChange (ops, ripple by order, lessons, hedges, recall)
  RS->>V: staged_review_view(StagedChange)
  V-->>W: grouped by stage: Intake · WM · LTM · Your review
  P->>W: deselect a change / weigh a ripple / set confidence
  W->>RS: stage(proposal, keep=subset, ripple weights)
  Note over RS,SB: re-staged on a fresh copy
  P->>W: Approve
  W->>RS: approve(proposal, keep, confidence, ripple, by)
  RS->>R: commit review effects · REVIEW_DECISION
  RS->>LT: run(selection) on live state
  LT->>R: commits learn.working, learn.long_term
  R-->>W: /ws state.version
```

### Pose a thesis

```mermaid
sequenceDiagram
  autonumber
  actor A as Asker (Predict)
  participant TS as ThesisService (M14)
  participant RF as Refiner (M06)
  participant R as Repo (M05)
  participant IT as InferenceTask (M13)
  participant SR as Shared read (M07)
  participant INF as Inference slots (M11)
  participant EX as Explainer (M07)

  A->>TS: pose(question, version=latest, watch)
  TS->>RF: refine(thesis.event)
  alt an end is not one value
    RF-->>A: candidates (nothing runs)
  end
  TS->>R: branch(version) — read-only overlay
  TS->>IT: forecast(thesis, branch, watch)
  IT->>SR: read(event, txn=None)
  IT->>INF: isolate → predict each network → plan scenarios → couple (± shock) → weigh → combine
  IT->>EX: explain_forecast (ablation, top paths)
  IT-->>TS: Forecast + Explanation
  TS->>R: ledger THESIS, FORECAST (no version bump)
  TS-->>A: forecast, transmission grid, brief
```

### An agent through the context layer

```mermaid
sequenceDiagram
  autonumber
  actor AG as Agent (MCP client)
  participant CX as Context layer (M16)
  participant V as Views (M15)
  participant TS as ThesisService (M14)
  participant RS as ReviewService (M14)
  participant EV as Evaluation (M12)

  AG->>CX: recall("yen carry exposure of Tokio Marine", as_of)
  CX->>V: find + entity view + provenance at version
  V-->>AG: facts with evidence, version, valid time
  AG->>CX: ask(thesis: "USD/JPY −8% in 30 days", watch)
  CX->>TS: pose(...)
  TS-->>AG: forecast by order and path + brief
  AG->>CX: trace(value or interaction id)
  CX->>V: lineage: change sets → proposal → evidence → source
  V-->>AG: PROV chain (entity · activity · agent)
  AG->>CX: propose(article or claim with quotes)
  CX->>RS: submit as a market event (never applied directly)
  RS-->>AG: proposal id, status pending (a person reviews it)
  AG->>CX: feedback(forecast id, outcome or rating)
  CX->>EV: record outcome → scored at horizon
```

---

## 11. The ledger lifecycle

Modeled on Semantica's decision lifecycle (record → link → query → govern → audit). Every write takes this path.

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

Ledger kinds (`repo/ledger.LedgerKind`): construction, update, market_event, proposal, review_decision, changeset, thesis, forecast, evaluation, decision, outcome, consolidation.

Commit processes (`repo/mutator.PROCESSES`): construction, history, intake, day.predict, learn.working, learn.long_term, day.record, day.distill, day.close, structural, review, hypothesis, forecast (no version bump), evaluation (track records), other.

---

## 12. Lifecycles of model objects

### Proposal

```mermaid
stateDiagram-v2
  [*] --> pending: propose() and the policy wants review
  [*] --> auto_applied: the policy auto-approves
  pending --> pending: re-staged with a new selection or confidence
  pending --> approved: approve(selection)
  pending --> rejected: reject(note)
  pending --> deferred: defer
  deferred --> approved: approved later (folds in late)
  deferred --> rejected
  approved --> [*]
  rejected --> [*]
  auto_applied --> [*]
```

Kinds: graph_update, refinement, frontier_promotion, superentity_admission, superentity_dissolution, missing_relation.

### A fuzzy end (hedge)

```mermaid
stateDiagram-v2
  [*] --> abstract: an end names a kind
  abstract --> entity: narrowed one level
  entity --> bound: the article names one candidate
  abstract --> hedged: no candidate named
  entity --> hedged: no candidate named
  hedged --> hedged: later events reweigh candidates × confidence
  hedged --> resolution_proposed: one candidate passes the bound with enough checks
  resolution_proposed --> bound: approved (rivals' soft interactions retired)
  resolution_proposed --> hedged: rejected
  hedged --> expired: too old
  bound --> [*]
  expired --> [*]
```

### A superentity pattern

```mermaid
stateDiagram-v2
  [*] --> candidate: a group of interactions fires together
  candidate --> candidate: support grows (+1 per spaced day) or decays
  candidate --> admitted: support > admission threshold and the collapse is approved
  [*] --> admitted: a backend user groups items (approved)
  admitted --> admitted: bound as instances; gains track record from forecasts
  admitted --> dissolved: support < floor and the expansion is approved, or the user dissolves it
  dissolved --> [*]
```

### A hypothesis (the hypothesis frontier)

```mermaid
stateDiagram-v2
  [*] --> open: proposed by intake, the frontier, or a person
  open --> open: rescored when its entities are touched (VOI, 14-day half-life)
  open --> branched: valuable and undecided in a thesis → scenarios with and without it
  branched --> open
  open --> supported: marked, or evidence passes the bound
  open --> refuted
  open --> expired
  supported --> [*]
  refuted --> [*]
  expired --> [*]
```

---

## 13. Data model

The main types and how they refer to each other. Field lists are in [M03](modules/M03-model.md) and [M04](modules/M04-memory.md).

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
  subgraph WM["WorkingMemory (M04) — what the world is like now"]
    G["graph: CausalGraph"]
    DV["deviations (z per value per day)"]
    CH["channels (kernel recursion states)"]
    HY["hypotheses — the hypothesis frontier"]
    PRF["pending refinements (hedges)"]
    RJ["ripple judgments"]
    FL["forecast layer (outside the hash)"]
    AUX["activity log · episode buffer · late queue · source cursors · clock"]
  end
  subgraph LTM["LongTermMemory (M04) — what generalizes"]
    OG["Object generalizations<br/>kinds + superentity patterns"]
    IG["Interaction generalizations"]
    EMM["Entity memories<br/>decisions by context"]
    CF["Correlation frontier<br/>co-movements with no interaction"]
    PS["Prior states<br/>episodes · explanations"]
  end
  WM -- "day.distill" --> LTM
  LTM -- "priors · analogs · patterns" --> WM
```

---

## 14. Deployment

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
