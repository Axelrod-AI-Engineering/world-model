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

A staged review, as a sequence:

```mermaid
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
