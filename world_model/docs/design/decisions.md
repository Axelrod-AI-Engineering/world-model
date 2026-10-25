# Decisions

The architecture's decisions, one row each. To change a decision, add a new row and mark the old one *Superseded by
D-nn*; don't edit it. Two other logs sit with what they govern: the API's in [api.md §9](api.md#9-decisions), and
business construction's in [specificity.md, Decisions](specificity.md#decisions).

<!-- toc -->
<!-- /toc -->

**Status:**
- **Accepted:** the code does this.
- **Proposed:** this design; for review.
- **Planned:** accepted, with the R# item that builds it.

| # | Decision | Instead of | Why | Status |
|---|---|---|---|---|
| D-01 | Own the causal core. Build a thin context layer on Cognee's verbs and Semantica's provenance and time model. Optionally run Cognee upstream as research memory. | Cognee or Semantica as the store; or no borrowing | Neither has quantitative interactions, propagation, forecasts, or review of facts ([frameworks.md](frameworks.md)) | Proposed |
| D-02 | 17 modules in six layers; every algorithm behind a slot; imports go only down | Today's packages, with their cycles fixed one at a time | Each module can be specified, built, and tested alone; today's cycles survive only on lazy imports | Proposed |
| D-03 | Review at the end of learning, on a staged copy; select some or all; deselecting re-stages | Review each proposal before it applies (plan §7.6) | The person judges consequences, ripple included ([cognition.md F12](cognition.md#f12--local-incremental-revision-judged-by-a-person)) | Accepted |
| D-04 | Inference never learns. A thesis runs on a branch that is never merged. | A forecast layer in WM (plan D5); forecast explanations moved into LTM (§8.12) | Asking must not change the model. `consolidate.py` still keeps forecast explanations; T-12 removes it. | Accepted |
| D-05 | One `Branch` mechanism for staging and theses | A JSON copy plus attribute swaps, and an overlay on live WM | One tested way to read without writing | Proposed |
| D-06 | Bitemporal facts; PROV-shaped change sets; PROV export | Versions and recording time only | Leak-free backtests; "what did we believe then"; audit | Proposed |
| D-07 | Cobweb trees propose structure; a hierarchical likelihood decides | Signature descent alone (today); Cobweb alone | Incremental concepts with a statistical check ([cognition.md F2–F5](cognition.md)) | Planned (R5) |
| D-08 | Read releases as surprises against expectation nodes | Releases read as levels (today, F-C1) | Prices move on surprises (pricing in) | Planned (R13) |
| D-09 | Scenario weights by leave-future-out stacking | support × in-sample fit × track × p (today) | In-sample fit flatters itself (S-M5) | Planned (R7) |
| D-10 | Score against raw observations or the true state | Scores against filtered values (today, S-C1) | Today's scores are circular | Planned (R0, first) |
| D-11 | Learning has five stages; inference has six (from `flows/`, under test) | literature §3.2 (five other steps), §3.3 (seven), §5.5 (four) | One source of truth | Accepted; inference's count superseded by D-17 |
| D-12 | Nothing is deleted. Retire by review; corrections carry `superseded_by`. | Cognee's `forget`; newest-wins resolution | The ledger is the audit trail, and a newer claim is not automatically truer | Proposed |
| D-13 | Agents write only by proposal | Agents writing facts directly | Vetted learning (D-03) | Accepted (v1: decisions are human-only) |
| D-14 | Bind a mention only when it is named; otherwise hedge it, plus an open share | Score and margin binding (plan §7.5; `bind_score` is now unread) | No false precision ([cognition.md F11](cognition.md#f11--an-open-world)) | Accepted |
| D-15 | Learn is internal; Predict is external, opens blank, and shows only what a forecast reaches | One view for everyone | Clients see their answer and its causal story, not the whole internal graph | Accepted |
| D-16 | Organize memory as a cognitive architecture (F1–F12), each framing behind a slot and tested by ablation | Chunks, embeddings, a vector index, and top-k recall | A forecast needs concepts, schemas, analogs, and known unknowns, not similar text ([cognition.md](cognition.md)) | Proposed |
| D-17 | Inference in seven MECE stages, in the naming guide's terms: Pose a thesis, Isolate, Isolated prediction, Distributed prediction, Unify, Read out, Evaluate. Scenarios are weighed once (distributed prediction); unify only mixes. | Six stages, where "Simulate and couple" bundled two stages and scenario planning, rivals were marked in isolation, and scoring was mixed with deciding | Each stage answers one question with one output; the flows, the code's comments, and the docs say the same thing | Accepted |
| D-18 | Design for the next horizon, build for the current one | Building for scale now; or designing only for today | Interfaces, data shapes, and module boundaries anticipate bigger graphs, better methods, and agents; what sits behind them is the simplest thing that works ([README §4](README.md#4-design-principles)) | Accepted |
| D-19 | Diagrams are SVG files rendered from Mermaid sources, in the app's palette | Mermaid blocks rendered by GitHub; hand-drawn images | They look the same everywhere (GitHub, VS Code, a PDF), and they stay editable as text; `--check` keeps them current | Accepted |
| D-20 | One unified world model, served in compartments: each client's view is a subgraph (as `focus` defines one), learning writes to the unified graph through review, and reads and inference see only the compartment ([architecture-plan.md §4](../archive/architecture-plan.md#4-one-world-model-or-several)) | One world model per client; or one model served whole | Shared knowledge is learned once; a client sees only their use case; the end goal is one model | Planned (Oct 25: [unified-model.md](unified-model.md), P0 being built) |
| D-21 | Only internal staff and backend services reach the world model. Core's backend MCP reads only, to start. Writes come from the web interface and the ingestion pipeline. | Clients or agents calling it directly | Security boundary agreed in the API review | Accepted (API review, Oct 18) |
| D-22 | The audit log is kept forever: no deletion, no expiry | A retention window | Every change stays traceable; storage is negligible | Accepted (API review, Oct 18) |
| D-23 | Idempotency keys are permanent, and creation is also keyed on content | Keys kept for a day | Determinism: the same content always gives the same result | Accepted (API review, Oct 18) |
| D-24 | Search from a question starts at its nearest neighbours in the semantic space, then expands best-first by edge weight | Expanding one hop, or by hop count | The strongest transmission paths come first, whatever their length | Proposed |
| D-25 | Core calls the world model with signed tokens only; each side keeps its secrets in one gitignored `.creds.<stage>` file and its non-secret settings in a checked-in stage profile (core's convention) | Static per-organization keys as a fallback, with variables set by hand in Railway | One secret per core stage (its signing key) and none for core on the world model side; settings are reviewable and survive an infrastructure apply | Decided (Oct 20, with Manav) |

## Where older documents disagree

The settled answer is the one in the third column. These fixes are task T-18 in [migration.md](migration.md).

| Topic | Older claim | Settled | Fix in |
|---|---|---|---|
| Cobweb | Concept trees described as built (literature §3.4, §4.1–4.2) | Planned (D-07) | literature |
| Surprises | Events already read as surprises (literature §5.3) | Planned (D-08) | literature |
| Scenario weights | "By track records" (literature §3.3, §5.5); "BMA" (implementation.html) | D-09 | literature, implementation.html |
| Evaluation | Out of sample (literature §5.6) | Circular today (D-10) | literature |
| Stage counts | 5, 7, and 4 steps | D-11 | literature |
| Reviewer confidence | Jeffrey conditioning (literature §4.6) | It tempers writes; not calibrated (ml-stack §5) | literature |
| Hedge weights | "By its posterior" (literature §5.4a) | Counts, not posteriors (S-M8; R18) | literature |
| Frontier | Known drivers removed (literature §5.4) | The slope absorbs common drivers (ml-stack §8.2; R2) | literature |
| Translation | A language model translates (literature §3.2) | Templates and fixtures; the LLM translator is a stub | literature |
| Pattern scoring | Diebold–Yılmaz connectedness (literature §4.3) | Explained share − 0.05 per interaction (ml-stack §8.3) | literature |
| Episode retrieval | Two-stage, from trees (literature §4.3) | Signature Jaccard; two-stage is planned (F8) | literature |
| Explainer, hypothesis scorer, frontier, kernel updater | Shapley; information gain; PCMCI + sequential test; grid every few days (implementation.html) | R12; R8; R2; a weekly 3-point rescale, then R4 | implementation.html |
| `max_networks` | 6 in plan and code, 8 in the yaml | One source of truth in config | code |
