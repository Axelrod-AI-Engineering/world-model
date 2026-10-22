---
name: world-model-construction
description: Build a company's business construction in an Axelrod world model at the specificity a buy-side analyst expects - compositions that reconcile, named operating and financial paths with explicit transitions, evidence-backed sizes, cited sources, searched inputs and calculation coverage. Use when adding or upgrading a company in a world (e.g. worlds/sally_demo in the client root), or when a reviewer says the model jumps from a macro driver to profit.
---

# Building a company's business construction

This is the method behind the Toyota, Tokio Marine and JPMorgan builds, and the eight that followed. The standard it
enforces is [docs/design/specificity.md](../../docs/design/specificity.md), rules R1–R17. The tools and forms are in
[docs/construction/README.md](../../docs/construction/README.md). Reference builds are in
[docs/construction/](../../docs/construction/).

## The standard in one paragraph

A change in the world must reach a company's accounts the way it does in reality:

- through the exposed business;
- then the actor's response;
- then the operating outcome;
- then the account.

Each step is a model object that says what it means, when it acts, what proves it, what breaks it, and what supports
it. A size comes from evidence or not at all: an unknown size is uncalibrated, never zero and never a guess. The
numbers must satisfy the structure. Every claim resolves to a document, location and passage. "Missing" is declared
only after a search. A forecast says what it could not calculate.

## Inputs

- The world: `world_model/examples/worlds/<world>/`, or `worlds/<world>/` in the client root for a client's (`WORLD_MODEL_CLIENT_DIR`, default `data/clients`: entities, interactions, taxonomy, `construction/`).
- The client's material for the company, local and gitignored: workbooks, research, filings, transcripts and
  presentations.
- The reviewer's feedback, if any.

## Steps

Build in this order: composition → operating paths → mapping into the accounts → calibration.

1. **Audit before modifying.** Read the company's current values and links, and the export a reviewer saw. An object
   missing from the export may still exist internally. Classify each existing requirement as already owned, missing,
   modify lightly, or do not touch (existing ids, valid statistical records, shared governance). Flag concepts the
   schema cannot represent.
2. **Gap register first** (`docs/construction/<company>.md`, in the client root for a client's company: local, not tracked). Write one entry per gap:
   - what is missing or wrong, and what exists now, with object ids;
   - what to add;
   - the evidence needed;
   - the conclusions it affects;
   - the test that will show it done;
   - its category: missing construction, missing calibration, incorrect mapping, export omission, or retrieval
     omission.

   The evidence side stays local.
3. **Define the values (R2).** Give every new value its view, accounting basis, unit and period. Add currency and
   geography where they matter. Keep statutory, adjusted and segment-profit definitions as separate values, and make
   every link's label match its target. Use synthetic, round priors that add up. Check that no name or alias makes a common
   word an extraction keyword (`check.py` warns `KEYWORD`).
4. **Compositions (R5).** Build each view the company reports (segments, regions, customer location, production
   location, products, business lines, investment assets, capital):
   - one basis per view;
   - an explicit residual and eliminations;
   - accounting links whose weight is the part's scale over the total's.

   **One view drives each total; the others reconcile (`drives: false`).** Segments × lines with cells form a
   `matrices:` entry.
5. **Exact structure, not signs.** Products, ratios, differences and weighted averages are `identities:`. Their
   weights are derived, never written. Stocks with their flows are `stock_flows:`. Asymmetric, threshold and
   sign-flipping responses carry a `state:` block.
6. **Named paths (R1, R3).** Write the operating and financial chains:
   - each step is a link with a full transition (mechanism and actor, condition and observable, timing by part,
     evidence by claim, breaker, next state, unresolved inputs);
   - parallel responses are branches;
   - counter-paths and offsets are included where material;
   - a reduced form (macro → total) is kept beside its path and labelled, never added to its steps.
7. **Sizes (R4, R14, R15).** Calibrate only from evidence, and only with evidence for the value's own definition (a
   sales series is not a customs base; a sales share is not a margin; a combined walk line stays aggregate). Before
   binding a workbook row, check that it feeds a live formula; a display-only row is not a sensitivity. Calibrate
   from a multi-period history (eight quarters where available), with standalone quarters derived from cumulative
   figures and accounting changes kept as breaks:
   - `scripts/construction/calibrate.py` turns a disclosed sensitivity into a size, in log space for lognormal values;
   - `--disclosure scenarios.yaml` solves several disclosed scenarios or a netted sensitivity jointly;
   - `--side rises|falls` gives an asymmetric response its two sizes;
   - a size borrowed from a peer is `peer`, with a citation.

   Everything else stays uncalibrated, with its sign.
8. **Kinds of statement (R8).** Keep these apart:
   - reported actuals (`documented`);
   - management guidance;
   - broker estimates;
   - workbook models;
   - your assumptions;
   - inferences.

   A forecast is not an observation, and a revision is news.
9. **Projects, plans and scope (R17).** Give each announced project, plan or capacity claim its own record:
   - its stage (announced, converted, commissioned, qualified, usable), dated facts and sources;
   - what it is not: a sales target is not capacity, a conversion is not expansion, a production move is not demand;
   - its unknowns kept unknown (net capacity, downtime, allocation, ramp, costs, tariff eligibility);
   - the OP and cash rules it would follow once sized, with capex, depreciation and working capital apart.

   Keep a statement with its own scope (one country, one denominator), keep a part inside its whole (hybrids inside
   electrified), and keep a line's two reported scopes as two records. Each effect has one driver; the company's own
   figure for it is a comparison. A value of another node that the company's links read follows the same observed
   rule.
10. **Baselines.** Make an `axelrod.import/v1` bundle of dated actuals from the company's own material, and keep
   estimates in a separate file. Validate it: `scripts/imports/bundles.py check <world> <bundle>`.
11. **Sources and citations (R6).** Keep two local files:
    - `sources.json`: source id → document, kind, date, period, basis, read state, proof limits;
    - `citations.json`: link or value id → source id, location (sheet!cell, table/row, page and paragraph), and passage.

    Tracked files hold **neutral ids only**: never a firm, broker, vendor or file name, and never a client figure.
12. **Inputs (R7).** Run `scripts/construction/inputs.py <world> --entities <company> --corpus <client folder>`. Read
    the candidates, then set each input's status:
    - found and connected;
    - found but not connected;
    - found as a proxy;
    - disclosed but not supplied;
    - not disclosed in the reviewed sources, listing what was searched.

    Leave none "not yet reviewed".
13. **Check and reconcile.** Run:

    ```
    scripts/construction/check.py <world> --entities <company> --sources <client>/construction --reconcile --statistic median [--baselines <bundle>]
    ```

    The run must end with no problems, no unresolved ids, no uncited material claims, and no reconciliation flags
    at medians or at baselines. Report any unexplained difference as an explicit residual.
14. **Generalization trace (R10).** Trace a development no path was written for, using `context.construction.trace`.
    Show that it reaches a financial endpoint, or where and why it stops.
15. **Calculation coverage (R9).** For each path, and for the client's theses, record from a forecast's `coverage`:
    - which links contribute a size;
    - which are excluded, and why;
    - which inputs block a size;
    - the company's own steps, counted apart from summary links.
16. **Validation test** (`tests/scenario/test_construction_<company>.py`):
    - no construction problems;
    - the required compositions and paths exist;
    - every step has a transition, and every uncalibrated step a sign;
    - views reconcile;
    - the trace reaches an endpoint;
    - the objects appear in the export and the API.

    Tests that need the client's files skip without them.
17. **Validation cases (R16).** Run the company's named validation cases, plus one development outside them, through
    the internal model, the export and the context an agent retrieves.
18. **Completion report: four reviewable parts (R16).** A before/after audit by canonical id; the compositions and
    connected paths; evidence and calibration; the end-to-end checks. For each gap: built and verified, built but
    uncalibrated, blocked by a named input, or not built. Then say what a downstream agent can now trace or calculate,
    and what the method could not express.

    Start with the reviewer's small checks before rerunning any long question set. Each check returns: run, blocked or
    not run; changed ids; the selected baseline; source period and passages; assumptions; intermediate values; the
    reconciliation; unresolved endpoints. Report model correctness, runtime access and answer quality as three
    separate states. Keep expected answers out of any retrieval scope, and never hard-code a test's answer into the
    model. When a reviewer's figure disagrees with the records, check the source and record the disagreement rather
    than overwrite either.

## Do not

- Jump from a macro driver to a company total, except as a labelled reduced form.
- Guess a size, or let "unknown" become zero.
- Add two views of one total together.
- Mix guidance or estimates into actuals.
- Declare an input missing without a search.
- Use a series as evidence for a concept it does not measure, or bind a workbook row that feeds no live formula.
- Apply a new market yield to a whole portfolio rather than the money reinvested at it.
- Put client figures, quotes, firm names or file names in tracked files.
- Edit another company's files. Make shared-file edits exact and minimal.
- Call a plan capacity, a conversion an expansion, an announcement a result, or a survey observed behaviour.
- Relabel a category's total as one of its parts, or spread one country's statement over a region.
- Size the same effect twice: once through its driver and again from the company's own figure.
- Mark a value observed, or a stipulated zero reported, without a dated source observation.

## Done means

`check.py` is clean with `--sources --reconcile` (and with baselines). The company test and the world's
expected-paths test pass. The gap register, the readable view and the completion report are in
`docs/construction/<company>.md`.
