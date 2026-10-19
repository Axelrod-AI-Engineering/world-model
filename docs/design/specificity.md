# Specific enough: rules for the world model

<!-- toc -->
**Contents**

- [The rules](#the-rules)
- [Where each rule is enforced](#where-each-rule-is-enforced)
- [Ingestion](#ingestion)
- [Learning and review](#learning-and-review)
- [Prediction](#prediction)
- [What is not yet enforced](#what-is-not-yet-enforced)
- [Decisions](#decisions)
<!-- /toc -->

The client's reviewer said, in two rounds, that our world model was not specific enough. A third document (Oct 18)
set out how to build Toyota and Tokio Marine to her standard. The reviewer said:

- it jumped from a macro driver straight to a company's sales or profit;
- it did not say how;
- its sources could not be resolved;
- its numbers did not add up;
- it did not say what it could not calculate.

These rules distill that feedback into one standard. The same standard applies to:

- what we build by hand;
- what ingestion reads from a document;
- what learning may change;
- what a forecast may claim.

They are written to be checked, not admired. Each rule has a test and names the places that enforce it.

**Build order.** Composition, then operating paths, then the mapping into the accounts, then calibration. A size is
never fitted to a structure that has not been laid out. Before adding anything, audit what the internal model already
owns. An object missing from an export is not necessarily missing from the model. Classify each proposed change:

- already owned;
- missing;
- modify lightly;
- do not touch: existing ids, valid statistical records, shared governance.

Flag any concept the schema cannot represent rather than forcing it in.


## The rules

**R1. No jumps.** A change reaches a company's accounts through what it acts on: the exposed business, the actor's
response, the operating outcome, and then the account. A link from a macro value straight to a company total is
allowed only as a *reduced form*. A reduced form says so in its transition and names the path it summarizes, and it
is never added to that path's steps.
*Test:* every causal link into a company total either has a transition naming a path, or is an accounting or
identity step.

**R2. Every value is defined.** A value states:

- its view (segment, region, customer location, product, operating state, …);
- its accounting basis;
- its unit and period;
- its currency and geography where they matter.

Two values that differ in basis are different values: adjusted against statutory, retail against consolidated,
constant FX against current. A link's label and its target agree: a link that says "adjusted net income" never
targets operating profit. Where a company reports several profit definitions (statutory, adjusted, segment profit),
each is its own value, and a composition or identity reconciles them.
*Test:* `features.view` and `features.basis` are present, the unit is set, and no transition names a metric other than
its target's.

**R3. Every link says what it means.** A link carries a transition with these parts:

- the mechanism and the actor;
- the condition, and the observable that proves it;
- timing: onset, build, persistence, and when the accounts recognize it;
- evidence for existence, direction, magnitude and timing, kept apart;
- the breaker;
- the next state;
- the inputs still missing.

Unknown parts say "unknown".
*Test:* a transition is present, and `validate_construction` passes.

**R4. A size comes from evidence or not at all.**

- A link is calibrated only from a disclosed sensitivity, a scenario disclosure, a supported estimate, or an exact
  identity.
- Otherwise it is *uncalibrated*: its sign is known, its size is not, it carries no number, and it is never read as
  zero.
- Accounting and identity weights are fixed, and learning never refits them. Identity weights are derived from the
  terms' levels, never written by hand.
- When the company discloses several scenarios (a parallel shift and a steepener, a rise and a fall), they are
  solved jointly (`calibrate.py --disclosure`). They are not read one at a time.
- A response that differs by direction gets two sizes (`--side rises|falls`), and only when both sides are evidenced.
  With one side known, the link keeps one linear size or stays uncalibrated, and says why.
- A size solved as the remainder after netting represented channels is graded `inferred`. A size whose split was
  derived rather than disclosed is graded `model`.
- A size borrowed from a named peer is graded `peer` and cited. A sector or peer figure that only stands in for the
  company's own makes the input `found_proxy`; it does not give the link a size unless the link is graded `peer`.

*Test:* every calibrated causal link's `evidence.magnitude` is documented, public_not_supplied, guidance, broker,
model, peer, or inferred (labelled as such).

**R5. The numbers satisfy the structure.**

- Every additive view reconciles: parts plus residual plus eliminations equal the total. It must hold at the model's
  levels and against reported actuals, within 0.5%.
- A difference the material cannot explain goes to an explicit residual, and its size is reported.
- Views of the same total are never added together. Exactly one view drives each total. The others are marked
  `drives: false`: they reconcile, and their links into the total carry no size. Two views with disclosed cells
  (segments × lines) form a matrix. Without cells, the second view only reconciles.
- **Choose the driving view by where the paths land and what the client forecasts.** It is not chosen by which view
  is most detailed. A path that lands on a reconciling view cannot carry a size into the total, and that limit is
  reported (R9).
- Identities (products, ratios, differences, weighted averages) and stock roll-forwards are checked the same way, at
  the model's levels and against actuals.
- **A check that lacks a level is `blocked`, not passed and not flagged.** It names the missing level. A level is
  never derived from the identity it is meant to test (circular); a reported figure on another basis stays in the
  estimates file.
- A roll-forward is checked only against two dated stock levels. With one date, the check is blocked and the test
  uses a synthetic year.

*Test:* `check.py --reconcile --statistic median`, run with and without `--baselines`, shows no driving-view
PROBLEM and 0 flags.

**R6. Every claim resolves to its source.** Each material claim names a source id that resolves, locally, to:

- the document;
- the location: sheet and cell, table and row, or page and paragraph;
- the passage;
- the publication date, the period covered, the units, the currency and the accounting basis.

Tracked files hold neutral ids only. Firm and file names stay with the client's data. A table in a non-English filing
keeps its original labels beside the translation.
*Test:* `check.py --sources` shows 0 unresolved ids and 0 uncited claims.

**R7. "Missing" is declared only after a search.** Each input a transition needs has one of six statuses:

- found and connected;
- found but not connected;
- found as a proxy: only a sector or peer figure was found, and the note says what it stands in for;
- disclosed but not supplied: the company publishes it, in a document outside the supplied material;
- not yet reviewed;
- not disclosed in the reviewed sources, which lists what was searched.

When new material arrives, the search is re-run over it, and statuses move. "Not supplied" and "not disclosed" are
not permanent. The company's own primary documents come first: filings, results and its own sensitivities. A
rating agency's or a broker's view is a third-party statement (R8), not a disclosure.

*Test:* no input is "not yet reviewed" at release, and every "not disclosed" or "not supplied" names its search.

**R8. Kinds of statement stay apart.** These are different things and are never merged:

- a reported actual;
- management guidance;
- a broker estimate;
- a model output;
- the builder's assumption;
- an inference.

A forecast or guidance figure is not an observation. A revision of one is news. A past figure is history, not the
present. Each is judged relative to the document's publication date, not today's.
*Test:* the evidence grade is set per claim, and ingestion's precision rules hold (see below).

**R9. A forecast says what it could not calculate.** Every forecast reports its calculation coverage:

- which links contributed a size;
- which were excluded, and why;
- which inputs, by status, block a size;
- for each target, the share of routes that are fully quantified.

*Test:* `Forecast.coverage` is present, and the brief shows it.

**R10. The structure generalizes.** A company's construction is validated on a development no path was written for:
a trace must reach a financial endpoint or say where and why it stops.
*Test:* each company's scenario test includes a generalization trace.

**R11. The most specific value the evidence supports.**

- A claim about a part (a region, a segment, a product, a line) is recorded on that part, not on the company total.
- A claim about the total is recorded on the total. It is not spread over the parts without a rule.

*Test:* ingestion maps each signal to the narrowest value whose definition matches the text.

**R12. Exact structure, not signs.** Where the relationship is arithmetic, it is written as arithmetic, never as a
signed causal link:

- a product, ratio, difference or weighted average is an identity (loans × yield, capital / RWA);
- a stock with its flows is a stock-flow (inflows in, outflows out, over a stated period);
- a response that is asymmetric, has a threshold, or flips sign carries a `state:` block. An uncalibrated link may
  carry the state as a condition.

A candidate left signed says why in its `note` (a factor not disclosed, a stock held as a ratio, a one-factor
product). Exact steps carry a size only when the step upstream of them is sized. Their value is that, once that step
is sized, nothing below it is a guess.
*Test:* `check.py` lists conversion candidates. Each is converted, or its note starts with the reason it stays
signed.

**R13. One number per effect.** A disclosed sensitivity is often a reduced form, such as a rate move into net
interest income. It sits beside the structural path it summarizes. Only one of the two carries the number:

- while only the reduced form is evidenced, it carries the size, and the path's entry steps stay unsized, with signs;
- when the company's own step sizes become available, the entries are sized and the reduced form is retired, in the
  same change;
- when a represented channel is exact (an identity), it is netted out of the disclosed total first. The reduced form
  then carries only the remainder, graded `inferred`, and the netting is recorded.

*Test:* no forecast route counts the same disclosed effect through both a reduced form and its path's entries.

**R14. A measure proves only what it measures.** A series is evidence for its own definition, not for a neighbouring
concept:

- sales in a market are not the customs base of an import tariff, and exports alone do not establish customs value;
- a share of sales is not a margin;
- a walk line that combines volume, price and mix stays one aggregate unless a supported split exists;
- a table for one subsidiary is not the group's exposure;
- a new market yield applies to the money reinvested at it, not to the whole portfolio.

Missing data limits a size; it never removes the mechanism.
*Test:* every input bound to a value names the value's own definition; anything else is `found_proxy` or
`found_not_connected`.

**R15. Bind to the working calculation.** A workbook binding names the workbook version, the tab and cell or named
input, and the downstream formula it feeds, checked to be live. A row the model only displays is not a working
sensitivity. Calibration from history uses a multi-period series, eight quarters where available: regional units,
segment results, FX assumptions and walk components, each matched to management's explanation. Standalone quarters
are derived from cumulative figures, never mixed with them. An accounting change is kept as a break, not smoothed
over.
*Test:* each workbook binding records version, location and the formula it feeds; each historical series states
whether it is cumulative or standalone.

**R16. Validation is end to end and reviewable.** A company is delivered in four parts:

1. a before/after audit: what was reused, added, corrected or is still missing, by canonical id;
2. readable compositions and connected paths, each mapped to model objects and financial endpoints;
3. evidence and calibration: extracted tables, dated baselines, workbook bindings, reconciliations and unresolved
   inputs;
4. end-to-end checks: a new development reaches the right business and accounts in the internal model, in the export,
   and in the context an agent retrieves.

Each company has named validation cases, plus one development outside them, because the model must handle
developments nobody wrote a path for (R10). A reviewer must be able to follow what changes, which business responds,
what happens operationally, and where the result enters earnings, cash or capital. Unsupported numerical steps must
be visible.
*Test:* the company's scenario test runs each validation case through the model, the export and the context reads.

## Where each rule is enforced

| Rule | Build (check.py, tests) | Ingestion | Learning and review | Prediction |
|---|---|---|---|---|
| R1 No jumps | `validate_construction`; company tests | proposes a new link's transition stub; flags a proposed macro → total link | review flags a proposal that skips an existing path | reduced forms never add to path steps |
| R2 Defined values | check.py; tests | maps only to a value whose basis and period match | — | — |
| R3 Transitions | `validate_construction` | a proposed link carries mechanism, sign, and quote | review shows the transition | the brief quotes mechanisms |
| R4 Sizes from evidence | calibrate.py refusals | a new link enters uncalibrated unless the text states a size | accounting and identity weights are never refit | uncalibrated links add nothing and are listed |
| R5 Reconciliation | `check.py --reconcile` | the overlap guard: one driving view per total | — | — |
| R6 Sources | `check.py --sources`; export `citation_gaps` | every signal keeps its document, chunk, and quote | review shows the quote | the brief cites |
| R7 Searched inputs | `inputs.py`; tests | — | — | coverage lists blocking inputs by status |
| R8 Kinds of statement | evidence grades | precision rules: observations are current reported levels; forecasts are not moves; revisions are | — | — |
| R9 Coverage | — | — | — | `Forecast.coverage` in the API, brief, and export |
| R10 Generalization | company tests' traces | — | — | — |
| R11 Most specific value | company tests | maps to the narrowest matching value | review flags a total-level observation when its parts were reported | — |
| R12 Exact structure | `check.py` conversion candidates; `reconcile_identities`, `reconcile_stock_flows`; company tests | — | identity and stock-flow weights are derived, never refit | identity and stock-flow steps pass a size through exactly |
| R14 A measure proves only what it measures | input statuses; company tests | maps only to a value whose definition matches (R2, R11) | review shows the input's definition beside the value's | coverage lists proxies as not sizing |
| R15 Working calculations | local bindings record version, location, formula | — | — | — |
| R16 End-to-end validation | company tests: validation cases through model, export and context | — | — | the brief separates calculated from direction-only steps |
| R13 One number per effect | company docs record the netting; company tests | — | — | not yet checked mechanically (see below) |

## Ingestion

What a document may contribute, in order:

1. **Recognize against definitions (R2, R11).** Map a phrase to the value whose name, basis and period match. Choose
   the narrowest value the text names, and refuse a mismatch of basis (adjusted against statutory, for example).
2. **Classify the statement (R8).** Classify it relative to the document's publication date: an actual, a revision, a
   forecast, or history. Only actuals become observations, and only reported changes or revisions become moves.
3. **Keep the source (R6).** Every signal carries the document, the chunk or table row, and the quote, so it resolves
   the way a hand-built claim does.
4. **Propose structure honestly (R1, R3, R4).** A new causal link is proposed with its mechanism (from the text), its
   sign, and its condition if stated. It enters uncalibrated unless the text states a size. A link from a macro value
   straight to a company total is flagged when a path for it exists.

## Learning and review

- **Accounting and identity links never learn (R4).** Fold and process noise skip them. This is implemented and
  tested end to end.
- **An uncalibrated link is not given a size by co-movement alone.** A statistical estimate may propose a size. The
  proposal is labelled "model", needs review, and shows how many observations support it.
- **Review shows the rules.** A proposed change shows its transition, its quote and source, and any rule it breaks,
  so the reviewer approves a specific claim, not a number.

## Prediction

- **Uncalibrated links contribute nothing and are listed (R4, R9).** A forecast's coverage names every excluded link
  with its sign and mechanism, and the inputs that block it.
- **Reduced forms never add to their paths (R1, R13).** The structural steps they summarize are shown beside the
  number.
- **Coverage counts the company's own steps apart from summary links (R9).** A target sized only through a reduced
  form says so.
- **The brief cites (R6),** and says which part of a target's movement is calculated and which is direction only.

## What is not yet enforced

| Gap | Where it will live |
|---|---|
| Ingestion mapping to the narrowest matching value, refusing basis mismatches (R2, R11) | ingest/extract.py and gazetteer, with a definition match on `features.basis` |
| A proposed link's transition stub (mechanism, sign, condition from the text) and a flag on macro → total proposals (R1, R3) | ingest/extract.py, intake/bundle.py, and the review view |
| Review flags for rule breaks (R1, R11) | control/review and the demo's review panel |
| A label and observation count on statistically proposed sizes | learning and review |
| A declared link between a reduced form and its path's entries, so a forecast uses one *instead of* the other (R13) | model/construction.py (`reduced_form_of`), engine forecast |
| A "change of a level" term: AOCI or an FVOCI reserve into capital, an overlay release (R12) | stock-flow form |
| Thresholds that follow a moving level (a running capital target), and the minimum of two constraints (R12) | `state:` form |
| Weighted averages whose weights are themselves values (deposit mix, currency baskets) (R12) | identity form |
| A driver on a matrix cell when the cells are not disclosed (R5) | matrices |
| A constant inside an identity, such as (1 − tax rate) (R12) | identity form |
| Dated one-off events (a certification halt, a plant restart, a price increase) as events, not links. They are recorded locally for Toyota; the engine cannot replay them yet | events and scenarios |
| Japanese query terms in the input search (R7) | scripts/construction/inputs.py |

The identity, stock-flow, matrix, state and driving-view forms were added on Oct 18. All eleven companies in the
Sally world were converted to them, so products, ratios and stocks are no longer sign-only.

## Decisions

Generalizations from building the eleven companies, kept here so the next company starts from them.

| Date | Decision | Rule |
|---|---|---|
| Oct 18 | The driving view is chosen by where paths land and what the client forecasts. Business-view paths that end on a reconciling view are reported as unable to reach the total | R5, R9 |
| Oct 18 | A check that lacks a level is `blocked`; a level is never derived from the identity it tests | R5 |
| Oct 18 | Several disclosed scenarios are solved jointly; asymmetric sizes need evidence on both sides | R4 |
| Oct 18 | A reduced form and its path never both carry a number. Represented exact channels are netted out first, and the remainder is `inferred` | R13 |
| Oct 18 | Peer figures make an input `found_proxy`; they size a link only as `peer`, cited | R4, R7 |
| Oct 18 | Value ids avoid common words ("other", "change", "level") so they cannot become extraction keywords | R2 |
| Oct 18 | Each new document pack re-runs the input search, and statuses move. Primary filings rank above third-party views | R7, R8 |
| Oct 18 | In one results deck, walk pages are actuals; forecast pages and Q&A revisions are guidance or news. Forecast walks never enter a calibration | R8, R4 |
| Oct 18 | A company's multi-period walk is a set of disclosed scenarios: each period's line against its driver's change. Partial periods are annualized and solved jointly | R4 |
| Oct 18 | R13 netting applies when a reduced form cannot be retired (a client's must-have channel): size the own step, re-size the reduced form to the remainder, graded `inferred` | R13 |
| Oct 18 | A documented group total placed on one part, when the split is undisclosed, is graded `model` (`calibrate.py --support model`) | R4, R11 |
| Oct 18 | A subsidiary's figures are another basis (a US finance arm against a consolidated segment). They are `found_not_connected`, or tested out of sample in estimates, and never observed into baselines | R2, R7 |
| Oct 18 | One-off developments (a certification halt, an authorization) are dated events with a computed effect, its method stated, graded `inferred`. They are not link sizes. An authorization is a resolution, not an actual | R4, R8 |
| Oct 18 | Monthly data on another basis (brand, unconsolidated) serves events and splits, not baselines. A sum of months states its window | R2 |
| Oct 18 | A flow in a roll-forward is dated by the window it occurred in, not by its notice's publication date | R5 |
| Oct 18 | A stock's definition is fixed. For example, shares outstanding is issued less treasury, so retirements leave it unchanged | R2, R5 |
| Oct 18 | Rating-agency views are searched and recorded, and never used as a size | R8 |
| Oct 18 | Asset valuation and liability valuation are parallel branches, with separate routes into profit, other comprehensive income, equity and solvency. They are connected only where the evidence supports it | R12, R1 |
| Oct 18 | Toyota's validation cases: tariff absorption against price recovery, and financing pressure. Tokio Marine's: gradual reinvestment uplift against underwriting deterioration, and asset marks against solvency. Each also has one development outside these | R16 |
| Oct 18 | A link that used a neighbouring measure is re-routed, not deleted: add the true value (a customs base), point the proxy at it with an R14 note, and leave the product with the true value unsized while the reduced form carries the number | R14, R13 |
| Oct 18 | Every management response is its own branch from the same cost (absorb, reprice, incentives, resource, transfer price), so a forecast shows which response it calculated | R1, R9 |
| Oct 18 | A size that follows from a value's definition (a withheld unit is a unit not built) may be `documented`. A size that rests on an inferred booking (which region bears a cost) is `model` | R4 |
| Oct 18 | History comes from the company's own standalone quarterly tables, checked by differencing the cumulative ones: every derived quarter must equal the reported one. Breaks (deconsolidation, walk-definition change, GAAP switch) are recorded | R15 |
| Oct 18 | A workbook binding is a level unless a live formula shows otherwise. A displayed row that the model backs out is never a sensitivity | R15 |
| Oct 18 | Cash and capital: dividends are per share × shares (an identity); an authorization is a value apart from completed purchases; a finance book is funded from its own debt, outside industrial cash; free cash flow stays blocked unless reported | R12, R8 |
| Oct 18 | A validation case is a forecast. Its coverage is read beside the export and the trace. A case whose steps are all direction only is a valid result if it says why | R16, R9 |
| Oct 18 | The focused world (`sally_focus`) is a second test world: every focus company's test runs on both worlds | R16 |
| Oct 18 | Scope before binding: a maturity table may be group, subsidiary or business scope, and may include coupons. Each is held as its own reconciling view, never as one business's ladder | R14 |
| Oct 18 | A hedge note is not a hedge slice: forwards hedging a net investment act on translation through OCI, not on the income cost of hedged bonds | R14, R12 |
| Oct 18 | Read the company's own breakdown before writing an identity: if a metric's breakdown has no line for an effect, the effect goes elsewhere | R12, R2 |
| Oct 18 | The holding structure decides cash routes: remittances that pass through an intermediate subsidiary are one inflow to the parent, not two | R13, R5 |
| Oct 18 | An accounting-basis switch changes what a metric contains (under IFRS, FVOCI equity gains leave net income). The switch is a dated break in the series | R2, R15 |
| Oct 18 | A disclosed sensitivity sizes a link only when the shock and the link measure the same thing. A net or market-wide sensitivity is an end-to-end check, and the forecast lists the branches left unsized | R4, R16 |
| Oct 18 | A disclosure that reverses intuition sets the sign, with the reason recorded, and each direction is sized separately | R4 |
| Oct 18 | Ratios over cumulative periods are derived from cumulative numerators and denominators, never by differencing ratios. A quarterly series is kept apart from the annual level set | R15 |
| Oct 18 | A reported level replaces one an earlier round derived, and the before and after are recorded | R5, R16 |
| Oct 18 | A per-share identity states whether its share count is average or period-end. A stock split is a dated corporate action, and series are not converted across it silently | R2 |
| Oct 18 | Validation figures stay local: tests read the client's disclosures from the local folder and check only directions on CI | R6, R16 |
| Oct 18 | A golden test bank checks the model directly. A responder that can read only the model (v1 reads, plus a fixture in model ids) answers; a separate grader holds the expected answer. Evidence, mechanism, calculation and timing are scored separately, and critical sign, scope, unit or accounting failures are listed on their own | R16 |
| Oct 18 | Exact arithmetic belongs in identities (market × share, net income / shares, local profit × rate). Calibrated slopes are for behavioural responses | R12 |
| Oct 18 | Unknown is a state. An unsized step leaves its target unknown, never zero. Measured zero, held constant, not applicable and unknown stay distinct | R4, R9 |
| Oct 18 | Reconciling views are solved to check the driving view and are never summed into it | R5 |
| Oct 18 | An observation records when its fact occurred (the reported period's end), apart from when it was published and when it was recorded | R8, R2 |
| Oct 18 | A measure on another perimeter (US retail against consolidated units) is its own value, with no link onward without a scope mapping | R14 |
| Oct 18 | A feedback loop within a period is cut and listed, never iterated silently | R9 |
| Oct 18 | A rate shock reprices balance × reset share × the fraction of the period active, with separate clocks for assets and funding | R12 |
| Oct 18 | A workbook's labels are not provenance: formula literals, allocations and zeros are builder assumptions however a ledger labels them, and a sensitivity that reads zero because a cell is text is unknown coverage | R8, R15 |
| Oct 18 | Calibration windows do not overlap: an annual actual and the quarters inside it are not independent observations, and forecasts and revisions stay out of an actual-only fit | R4, R15 |
| Oct 18 | A broker mean is a comparison view with its contributor set. Mean net income and mean EPS are never forced into one identity | R8 |
| Oct 18 | A baseline is chosen and labelled (dated actual, guidance or model state), and a difference between the export's state and an actual is reported, never plugged | R5, R8 |
| Oct 18 | Toyota's paths are operational: each says which flows are covered and when the cost falls due, who bears it, the management response (absorb, reprice, resource, or a mix), how customers, dealers and production respond, and which regional accounts change and how they reconcile to the group | R1, R3 |
| Oct 18 | The same figure in a Japanese and an English filing is one fact: cite the English primary filing. The input search needs Japanese terms too | R6, R7 |
