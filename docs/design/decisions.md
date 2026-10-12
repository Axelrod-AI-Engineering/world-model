# Decisions

Each design decision records the choice, the alternatives, and the reason. Where older documents disagree with each other, the settled answer is here, and the document that needs a fix is named. Add a new entry rather than editing an old one; mark a replaced entry **Superseded by D-nn**.

Status: **Accepted** (the code does this), **Proposed** (this design; for the review call), **Superseded**.

---

### D-01 · Own the causal core; borrow for the context layer — Proposed

- **Choice:** build the world model ourselves. Build the context layer ourselves on Cognee's verb shape and Semantica's provenance and time model. Optionally run Cognee upstream as research memory behind the import bundle.
- **Alternatives:** Cognee as the store (no quantitative interactions, no review of facts); Semantica as the store (pre-1.0; qualitative causal edges only); a custom framework from scratch with no borrowing.
- **Why:** [frameworks.md](frameworks.md#what-neither-provides).

### D-02 · Modules in layers, with slots — Proposed

- **Choice:** 19 modules in six layers; every algorithm behind a slot; imports only downward.
- **Alternatives:** keep today's packages and fix only the cycles.
- **Why:** each module can be specified, built, and tested on its own, by a person or a coding agent. Today's cycles are tolerated only through lazy imports ([migration.md](migration.md#current-cycles)).

### D-03 · Review at the end of learning, on a staged copy — Accepted

- **Choice:** the event's whole learning (WM, LTM, and the day's distillation) runs on a copy. The reviewer sees everything it would commit, ripple included, and approves all, some, or none. Deselecting re-stages.
- **Replaces:** plan.md §7.6, review-before-apply per proposal.
- **Fix in docs:** plan.md (archived).

### D-04 · Inference never learns; theses run on a branch — Accepted

- **Choice:** a thesis reads a branch that is never merged. Only outcomes feed back, through track records.
- **Replaces:** plan.md D5 (a forecast layer in WM) and §8.12 step 3 (moving forecast explanations into LTM). The code still moves forecast explanations in `consolidate.py`; [migration.md](migration.md) task T-12 removes that.

### D-05 · One branch mechanism — Proposed

- **Choice:** `repo.Branch`, copy-on-write over a committed version with its own ledger, for both staging and theses.
- **Alternatives:** today's two mechanisms (a JSON copy plus attribute swaps for staging; an overlay on live WM for theses).
- **Why:** one tested way to read without writing; no attribute swapping on a live engine.

### D-06 · Bitemporal facts and PROV-shaped change sets — Proposed

- **Choice:** valid time and recorded time on time states, interactions, and evidence; entity, activity, and agent on change sets; PROV export.
- **Why:** leak-free backtests, "what did we believe then", audit export. From Semantica.

### D-07 · Cobweb proposes; the hierarchical likelihood decides — Accepted (as plan)

- **Choice:** the code classifies by signature descent today. The plan (ml-roadmap R5, methods briefing) is:
  - Cobweb trees, one per data structure plus composition trees, over structured embeddings with an acuity cutoff and no whitening, **propose** structure;
  - a measurement-error hierarchy **decides** it.
- **Settles:** `web/literature.md` §3.4 and §4.1–4.2 describe Cobweb trees as built. ml-stack §8.1 says "signature descent (not Cobweb)".
- **Fix in docs:** literature.md should say "planned" for the Cobweb trees.

### D-08 · Read events as surprises — Proposed (R13)

- **Choice:** add expectation nodes (consensus, whisper, OIS or futures-implied) and read a release as its surprise.
- **Settles:** literature.md §5.3 says events are already read as surprises. ml-stack §5 says releases are read as levels (F-C1).
- **Fix in docs:** literature.md §5.3 should say "planned".

### D-09 · Scenario weights — Accepted as built, Proposed to change (R7)

- **As built:** support × in-sample fit × track record × p(hypothesis).
- **Settles:** literature.md §3.3 and §5.5 say "weighted by their track records" (only one factor). implementation.html says "BMA". R7 prefers stacking or pseudo-BMA+ over BMA.
- **Fix in docs:** literature.md and implementation.html.

### D-10 · Evaluate against raw observations — Proposed (R0)

- **Choice:** score forecasts against raw observations or the true state, never against filtered values.
- **Settles:** literature.md §5.6 calls evaluation out of sample. ml-stack §10 calls it circular (S-C1).

### D-11 · Stage counts — Accepted

- **Choice:** learning has five stages (intake, learning · WM, learning · LTM, human review, commit). Inference has six (pose, isolate, simulate and couple, weigh and unify, read out and explain, score). These come from `flows/`, which tests check.
- **Settles:** literature.md §3.2 (five different steps), §3.3 (seven), and §5.5 (four).
- **Fix in docs:** align literature.md with `flows/`.

### D-12 · No forget; supersede — Proposed

- **Choice:** nothing is deleted. Retiring is a reviewed structural change; a corrected fact carries `superseded_by`.
- **Alternatives:** Cognee's `forget`; newest-wins resolution.
- **Why:** the ledger is the audit trail, and in finance a newer claim is not automatically truer.

### D-13 · Agents write only by proposal — Proposed

- **Choice:** the context layer's `propose` creates a market event that a person reviews. No agent verb commits.
- **Why:** vetted learning is an invariant (D-03).

### D-14 · Hedge, don't guess — Accepted

- **Choice:** an end binds only when the article names it. Otherwise it is hedged across its candidates plus an open share, and resolved by review once one candidate passes the bound.
- **Replaces:** plan.md §7.5's score and margin binding (`bind_score` and `evidence_bonus`, now unread).

### D-15 · Learn internal, Predict external — Accepted

- **Choice:** Learn (imports, reviews, edits) is for Axelrod's backend users. Predict is for clients. It opens blank, and a forecast brings forward only what it reaches. The whole model can still be viewed as of the forecast's version.

---

## Smaller conflicts settled

| Topic | Says | Settled as | Fix |
|---|---|---|---|
| Reviewer confidence | literature §4.6: Jeffrey conditioning | It tempers writes and is not calibrated, and it is not Jeffrey conditioning in the strict sense (ml-stack §5) | literature |
| Hedge weights | literature §5.4a: "by its posterior" | Dirichlet counts, not posteriors (S-M8); R18 plans responsibilities | literature |
| Frontier confounding | literature §5.4: known drivers are removed | The slope is fit on raw change and absorbs common drivers (ml-stack §8.2); R2 | literature |
| Translation | literature §3.2: a language model translates | Templates and fixtures; the LLM translator is a stub | literature |
| Pattern scoring | literature §4.3: connectedness (Diebold–Yılmaz) | Explained share − 0.05 per interaction (ml-stack §8.3) | literature |
| Episode retrieval | literature §4.3: two-stage, from trees | Signature Jaccard (ml-stack §8.4); two-stage is the production plan | literature |
| `max_networks` | plan: 6 | yaml 8, code 6: one source of truth in config ([M13](modules/M13-runtime.md)) | code |
| Explainer | implementation.html: sampled Shapley | R12: path-specific effects; Shapley only for nonlinear parts | implementation.html |
| Hypothesis scorer | implementation.html: expected information gain | R8: EVPI under CRPS; information gain only under the log score | implementation.html |
| Frontier test | implementation.html: PCMCI + a sequential test | R2: LPCMCI/PCMCI+ and e-values with online FDR | implementation.html |
| Kernel updater | implementation.html prototype: a grid on delay and lag every few days | A joint 3-point rescale, weekly (ml-stack §4.3); R4 for the grid posterior | implementation.html |
