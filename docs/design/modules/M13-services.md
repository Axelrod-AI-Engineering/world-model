# M13 · Services

**Layer** 4 · **Package** `control/` · **Status** split the god object.

**Code today:**
- `control/controller.py`: `WorldModelController`, 940 lines with about 47 `self.engine` references;
- `control/updates.py`;
- `control/stage.py`: 972 lines, about 600 of them view assembly;
- `repo/review.py`.

## Purpose

The product's commands. Each service owns one workflow, persists its records through the ledger, and emits trace events. Services alone call `propose()`, and they alone decide when learning runs.

## Owns

| Service | Commands | Records |
|---|---|---|
| `ReviewService` | propose, stage(pid, keep, confidences, ripple) → `StagedChange`, approve(pid, by, note, keep, confidence, op_confidence, ripple), reject, defer, edit, set_review_policy | `Proposal {kind, status, event, refinement, conflicts, requirement, decided_by, note}` |
| `UpdateService` | request_update, continue, cancel, import_items(bundle, ids) | `UpdateRun`, `UpdateReport` |
| `ThesisService` | pose(question or thesis, version, watch), pin, record_decision, resolve_decision, add_hypothesis, mark_hypothesis | `Thesis`, `Forecast`, `DecisionRecord` |
| `StructureService` | propose_group, propose_dissolve, propose_retire, submit_graph_update (drawn edits; world ops refused), add_from_knowledge | proposals |
| `SourceRegistry` | register_source, source, translator_chain | |

A thin `WorldModelController` facade keeps today's callers working.

**Slot:** `review_policy` (default, auto_approve_all, review_all): `ReviewPolicy.assess(proposal, wm) -> ReviewRequirement`.

## Depends on

[M12](M12-runtime.md), [M04](M04-repo.md), [M05](M05-intake.md), [M11](M11-evaluation.md). Not the API, views, or demo.

## Diagrams

Human review and commit:

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "edgeLabelBackground": "#F7F2EA", "clusterBkg": "#F7F2EA", "clusterBorder": "#E4DACB", "titleColor": "#665E54"}}}%%
%% style: end
flowchart TD
  ST["Every staged change: items, moves, ripple by order, lessons"]:::start ==> SH["Show each change with the phrase that asked for it"]:::step
  SH ==> CONF["Set confidence: the article's, and any change's own"]:::step
  CONF ==> CHK["Check the event's own move, then each further order"]:::step
  CHK ==> OK{"Does every change make sense?"}:::check
  OK ==>|yes| AP["Approve the selection"]:::step
  AP ==> C1[("commit · review effects<br/>pending ends, soft support, ripple judgments")]:::store
  C1 ==> C2[("commit · learn.working")]:::store
  C2 ==> C3[("commit · learn.long_term")]:::store
  C3 ==> LAST{"The day's last event?"}:::check
  LAST ==>|no| PR{"Proposals raised?"}:::check
  PR ==>|no| VER["A new version in the log"]:::done
  OK -->|deselect some| RS["Re-stage without them, on a fresh copy"]:::opt
  RS --> SH
  OK -.->|not yet| DEF["Defer: approved later, it folds in late"]:::opt
  OK -->|none| REJ["Reject with a note; nothing changes"]:::done
  LAST -->|yes| C4[("day.record → day.distill → day.close")]:::store
  C4 --> PR
  PR -->|yes| QUEUE["They join the review queue"]:::opt
  QUEUE --> VER
  %% style: classes and happy path
  classDef start fill:#DAD0F4,stroke:#7C64C4,stroke-width:1.5px,color:#2F2A25
  classDef step fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,color:#2F2A25
  classDef opt fill:#FFFDF8,stroke:#C9BFAF,stroke-width:1.3px,stroke-dasharray:5 4,color:#2F2A25
  classDef check fill:#F5EAC6,stroke:#D2BB72,stroke-width:1.3px,color:#2F2A25,font-weight:600
  classDef store fill:#F7E1D3,stroke:#E0B092,stroke-width:1.3px,color:#2F2A25
  classDef done fill:#FBF8F2,stroke:#93897C,stroke-width:1.6px,color:#2F2A25
  linkStyle 0,1,2,3,4,5,6,7,8,9,10 stroke:#7C64C4,stroke-width:2.6px,color:#5B4A99
  %% style: end
```

A staged review, as a sequence:

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "actorBkg": "#DAD0F4", "actorBorder": "#7C64C4", "actorLineColor": "#C9BFAF", "signalColor": "#857C70", "labelBoxBkgColor": "#F5EAC6", "labelBoxBorderColor": "#D2BB72", "noteBkgColor": "#F5EAC6", "noteBorderColor": "#D2BB72", "activationBkgColor": "#E1ECDF", "sequenceNumberColor": "#FFFDF8"}}}%%
%% style: end
sequenceDiagram
  autonumber
  actor P as Reviewer
  participant W as Web (M16)
  participant RS as ReviewService (M13)
  participant SB as Sandbox (M12)
  participant LT as LearningTask (M12)
  participant V as Views (M14)
  participant R as Repo (M04)

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

A proposal's lifecycle. Its kinds are graph_update, refinement, frontier_promotion, superentity_admission, superentity_dissolution, and missing_relation.

```mermaid
%% style: begin (scripts/docs/style_mermaid.py)
%%{init: {"theme": "base", "themeVariables": {"fontSize": "14px", "primaryColor": "#FFFDF8", "primaryBorderColor": "#C9BFAF", "primaryTextColor": "#2F2A25", "lineColor": "#857C70", "textColor": "#2F2A25", "secondaryColor": "#F7F2EA", "tertiaryColor": "#FBF8F2", "transitionColor": "#857C70", "transitionLabelColor": "#665E54", "compositeBackground": "#F7F2EA"}}}%%
%% style: end
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

## Invariants

- **Vetted learning.** Nothing that needs review is learned before approval, and what is approved is what was staged. Rejecting changes nothing. A deferred event folds in late.
- **Review at the end.** Staging runs the event's whole learning, including the day's distillation.
- **Deselecting re-stages.** A partial approval also drops the operations that depend on what was removed.
- **Every decision is logged** with who made it and at what confidence.
- **Learn is internal; Predict is external.** External users reach only `ThesisService`.
- **Records survive a restart.**

## Done when

- The review, ripple, import, and API integration tests pass against the facade unchanged.
- The proposal lifecycle and restart tests pass.
- `control/` imports neither `api/` nor `sim/`.
