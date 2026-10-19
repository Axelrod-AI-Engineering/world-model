# AIB Group: business construction

<!-- toc -->
**Contents**

- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Validation](#validation)
- [Completion report](#completion-report)
- [What the method could not express for this bank](#what-the-method-could-not-express-for-this-bank)
- [Conversion to the extended method (Oct 18, second pass)](#conversion-to-the-extended-method-oct-18-second-pass)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Identities](#identities)
  - [Stocks and flows](#stocks-and-flows)
  - [Operating and financial paths](#operating-and-financial-paths)
<!-- /toc -->

The second bank after [JPMorgan](jpmorgan.md), built in the company's own reporting: an Irish retail and commercial bank
(IFRS, EUR, fiscal year = calendar year; Ireland and the UK) whose net interest income follows the ECB through a large
current-account base, cash at the central bank, tracker and floating loans and low deposit betas, partly locked in by
a structural hedge; whose credit costs follow the Irish economy and house prices; and whose capital is returned
through dividends and buybacks, including directed buybacks while the State sells down its stake. Before this build AIB
had a single value (`aib_group.net_interest_income`) and the share price.

The construction lives in `data/worlds/sally_demo/construction/aib_group.yaml` (two new macro entities, 68 new values on
`aib_group`, 57 causal links with transitions, 47 accounting links, 13 named paths, 15 compositions) plus two light
edits to shared files: `features` on `aib_group.net_interest_income` in entities.yaml, and a transition on s32 in
interactions.yaml (size kept). This page is structure only. The client-derived side (passages, dated levels, broker
figures) stays local under `data/sally_data/construction/aib_group/` (`gap_evidence.md`, `sources.json`,
`citations.json`, `baselines.json`, `estimates.json`, `input_search.json`/`.md`, `reconciliation.md`, and the view with
levels and traces in `view/`).

**The material.** The supplied material holds no AIB company workbook, results, annual report or broker note on AIB.
AIB appears only in a peer valuation sheet and a coverage list inside notes on another bank. Every parsable file under
`spreadsheets/` and `unpacked/sell_side/` (115 files) was parsed and searched. So every mechanism here rests on
public business knowledge and euro-peer analogy. In the first pass no new link carried a size; the [conversion](#conversion-to-the-extended-method-oct-18-second-pass)
made the structure exact with identities and stock-flows and sized one link from a named peer.

Source ids (each resolves locally in `sources.json`; material claims resolve to a page and passage in `citations.json`):
`aib.r1` a broker's European banks valuation sheet with an AIB row; `aib.r2` a broker note whose coverage list carries
AIB; `aib.peer` a euro-area peer bank's company workbook (deposit pass-through, structural-hedge roll, the deposit rate
as a Euribor proxy); `aib.peer2` peer broker notes on deposit betas and replicating portfolios; `aib.macro` the shared
macro dataset carried in the supplied workbooks; `aib.pub` public business, accounting and regulatory knowledge
(IFRS 9, CRR, Irish mortgage products, directed buybacks), never used for a material claim.

**New macro values** (other companies may need them; one definition each at merge): `ireland_economy`
(`.domestic_demand_growth`, `.unemployment_rate`, `.house_price_growth`, `.mortgage_drawdowns`) and
`bank_of_england.policy_rate`. Existing ids reused: `ecb.policy_rate`, `bunds.yield_10y` (it stands in for the
medium-term euro swap rate, as the peer workbook does), `euro_economy.headline_cpi`,
`europe_capital_markets.equity_index`. Every new macro link is uncalibrated, so no other company's output moves.

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack (036, 2026-10-16). Categories: **MC** missing construction, **CAL** missing calibration, **MAP** incorrect mapping,
**EXP** export omission, **RET** retrieval omission. Outcomes are in the [completion report](#completion-report).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | No business composition: the pack jumps from the ECB to NII and from NII to the share price | Internal: `aib_group.net_interest_income`, the kind-default share price; s32, s69, s80, s82; no compositions. Export: N_AIB, one company edge (NII to share price), one step on a shared ECB path | The driven line view of total operating income (`aib.comp.income_by_line`), the P&L bridge (`aib.comp.pbt`, `aib.comp.profit_after_tax`), expenses, impairment, NII by balance-sheet line, loans and deposits | AIB income statement and notes | Any revenue or earnings conclusion; "ECB cuts hurt AIB" taken whole | `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links`, `test_priors_reconcile_within_half_a_percent` | MC |
| G02 | NII has no basis (IFRS? incl. hedge interest? group or Ireland?) | Internal: no features. Export: metric named by id suffix | `features.view/basis/metric` on NII and every new value; EUR units throughout | none | Comparing NII with a peer's or a guided figure | `test_values_name_their_basis` | MAP |
| G03 | s32 (ECB to NII) has no scope; its size is not tied to a disclosure | Internal: calibrated 0.65, no transition | Keep id and size; add a transition naming it the reduced form of `aib.path.rates_nii`, magnitude "assumption" | AIB's NII sensitivity to a parallel and a short-end move | Size of any ECB-driven NII change | `test_reduced_form_is_never_a_step_of_its_structural_path` | MAP / CAL |
| G04 | NII drivers absent: central bank cash, tracker and floating loans, deposit beta, current-account migration, swapped wholesale debt | Internal: none | Operating states and `aib.path.rates_nii` (parallel branches of one ECB move) into the NII views | Cash at the central bank, tracker and fixed shares, beta, current-account share | Whether and when a cut lowers NII | `test_shared_driver_responses_are_parallel_branches`, `test_deposit_beta_lags_and_migration_shrinks_the_hedgeable_base` | MC |
| G05 | Deposit-beta size | Internal: none | Calibrate if a disclosure is found | AIB deposit pass-through | NII path size and timing | `test_no_new_link_carries_a_size` (the gap stays visible) | CAL |
| G06 | Structural hedge and the long end: the hedge pays floating (offsets a cut) and rolls at swap rates (years); securities reinvest; FVOCI marks reach CET1 | Internal: none | Hedge values, `aib.path.structural_hedge`, the counter-path `aib-c-ecb-hedgefloat`, `aib-c-bund-fvoci` | Hedge notional, yield and life; euro swap curve; FVOCI duration | "Rate cuts hurt NII one for one"; "higher long rates are good" | `test_the_structural_hedge_is_a_counter_path_to_the_ecb`, `test_marks_reach_capital_not_income` | MC / CAL |
| G07 | Mortgage book: Irish housing, drawdowns, market share, fixed-rate pricing off swaps, redemptions | Internal: none; no Irish value in the world | `ireland_economy` values; `aib.path.mortgage_lending` | Drawdowns, market share, redemptions, fixed/tracker mix | Loan growth and NII from volume | `test_required_paths_exist` | MC |
| G08 | Cost of risk and the Irish economy (IFRS 9: allowance on the outlook now, write-offs later) | Internal: none | Impairment views by portfolio and by roll-forward; `aib.path.credit_cycle`, `aib.path.house_prices_credit` | IFRS 9 scenarios and weights; ECL sensitivity to unemployment and house prices | Any downturn conclusion | `test_two_credit_clocks` | MC / CAL |
| G09 | Rates also stress property and variable-rate borrowers (credit counter-path to the NII gain) | Internal: none | `aib-c-ecb-property`, `aib-c-ecb-npe` as branches of the rate path | Property and variable-rate exposure | Net effect of a hike | `test_rates_have_a_credit_counter_path` | MC |
| G10 | Fees: activity, cards and payments, wealth | Internal: none | `aib.path.fees`, `aib.path.wealth_fees` | Fee split by product | Non-NII income | `test_required_paths_exist` | MC |
| G11 | Costs: wage agreements, levies, restricted variable pay | Internal: none | `aib.comp.expenses`, `aib.path.cost_inflation` | Cost guidance, levy | Operating leverage | `test_required_paths_exist` | MC |
| G12 | AIB UK: Bank Rate and the GBP translation | Internal: none; no UK rate or EUR/GBP in the world | `bank_of_england.policy_rate`, `aib.path.uk_rates` | UK NII sensitivity, EUR/GBP | UK contribution | `test_required_paths_exist` | MC |
| G13 | Capital and distributions: CET1 capital, RWA, requirement, dividends, buybacks | Internal: none | Capital values, `aib.path.capital_distributions`, `aib.path.capital_requirements`, `aib.path.balance_sheet_growth`; non-additive `aib.comp.capital_roll_forward` | CET1 target, payout policy, risk weights | Distribution capacity | `test_capital_is_a_stock_with_flows_not_an_additive_view` | MC |
| G14 | The State's sell-down (placings, trading plan, directed buybacks; the overhang) | Internal: none | `state_shareholding`, `state_share_sales`, `aib.path.state_selldown` | The State's current stake and method | Buybacks, the share price | `test_state_selldown_is_represented` | MC |
| G15 | Reporting segments (Retail Banking, Capital Markets, AIB UK, Group): income and profit before tax | Internal: none | `aib.comp.income_by_segment`, `aib.comp.pbt_by_segment` (Group as residual) | Segment note; confirmation of the current segment set | Segment mix | `test_required_compositions_exist` | MC |
| G16 | New objects absent from the export | Export: none | Transitions in relationship properties, `financial_bridge`, `business_construction` paths | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G17 | New node ids not retrievable | API: none | `/v1/world-models/sally_demo/graph`, `…/entities/aib_group/construction` and its traces | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G18 | No dated AIB levels to bind or reconcile at | Local: none | Baselines from the supplied material | AIB results (income statement, segment note, balance sheet) | Every level; reconciliation at actuals | listed as blocked | CAL |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, kind, memberships, share-price kind default (`aib_group`) | Already owned | entities.yaml `aib_group` | untouched |
| s32 (ECB to NII; a statistical record Sally's paths use) | Already owned, Modify lightly | interactions.yaml | id, size and kernel kept; transition added (reduced form, magnitude "assumption", unresolved input searched) |
| s69, s80, s82 (to the share price) | Do not touch | interactions.yaml | untouched |
| `aib_group.net_interest_income` definition | Modify lightly | entities.yaml | `features.view/basis/metric` added; id and prior kept |
| Compositions, operating states, connected paths, financial mappings, Irish and UK macro values, bindings | Missing | construction/aib_group.yaml; local sources, citations, baselines | built |
| Shared macro links (m03, m10, s05, s06, s66, s67) and the other banks' objects | Do not touch | interactions.yaml, entities.yaml | untouched; AIB paths start below them |

## Definitions and bases

- **Basis**: IFRS as adopted in the EU, EUR, fiscal year = calendar year. AIB UK is translated from GBP.
- **The line view** (`aib.comp.income_by_line`, the driven view): total operating income = NII + net fees and
  commissions + other income (residual). **The segment view** (`aib.comp.income_by_segment`): Retail Banking + Capital
  Markets + AIB UK + Group (residual). Both total the same income; they are never added to each other. Only the line
  view is driven, except AIB UK, which has its own uncalibrated driver (`aib-c-boe-ukincome`). The segment set is the
  one AIB has used in recent annual reports; it is not confirmed against a current report (none was supplied).
- **NII** includes the net interest on the structural hedge: fixed received less floating paid, a separate part of
  interest income (`aib_group.structural_hedge_income`). A lower policy rate raises it.
- **Costs and charges are negative values** (expenses, impairment, interest expense, tax), so every part adds to its
  total with a positive weight. A cost link's sign "-" means "a larger charge".
- **Credit**: impairment = net write-offs + allowance change, by portfolio (IFRS 9). Allowances follow the
  forward-looking scenarios and stage migration (early). Write-offs follow realised losses (late).
- **Capital**: CET1 capital is a stock fed by flows (profit in; dividends, buybacks and AT1 coupons out; FVOCI marks);
  the CET1 ratio is capital over RWA. Under the EU rules FVOCI marks are in CET1, and the cash-flow hedge reserve (the
  structural hedge's swap marks) is filtered out.
- **Conversion tags**: steps that are identities, stock-flows or state-dependent are uncalibrated links whose `note`
  reads `identity: product of <a> and <b>`, `identity: ratio <a> / <b>`, `stock-flow: <stock> += <flows>` or
  `state: <rule>`, ready to convert when the method has those forms. 15 identity, 6 stock-flow and 4 state tags; the
  identity itself is never listed as an unresolved input.
- All priors are synthetic, round levels set to reconcile; dated levels are local.

## Validation

`tests/scenario/test_construction_aib_group.py` loads sally_demo once and reads no client data (it reads the tracked
construction file for the conversion tags):

- **Structure**: no `validate_construction` problems for the company. The fifteen compositions and thirteen paths
  exist. Every path step has a transition, and every uncalibrated step has a sign and an "unknown" magnitude. The
  parallel responses of one ECB move are branches from the policy rate: cash, loans, beta, migration, hedge, wholesale,
  credit. The long-end responses are branches from the Bund, and house prices' two responses are branches too. s32 is
  never a step of its structural path.
- **Financial integrity**: every part of an additive view has a fixed-weight accounting link equal to its native sd
  over the total's. Each view has one unit. Views that leave something out keep a residual. The priors of every
  additive view reconcile within 0.5% (exactly). FVOCI marks reach CET1 and never income. Capital is a stock with
  signed, tagged flows, not an additive view.
- **A deposit-rich euro bank**: the structural hedge is a counter-path to the ECB, and its roll takes years. The
  deposit beta lags. Migration out of current accounts shrinks the hedgeable base and raises interest paid. Rates have
  a credit counter-path. There are two credit clocks (the IFRS 9 allowance on unemployment at once, write-offs only
  through defaults). The State sell-down's three parallel responses are represented.
- **Calibration**: no new causal link carries a size. The quantified non-accounting links are exactly s32, s69, s80
  and s82. s32 keeps 0.65 with magnitude "assumption". Every missing input says the material was searched (no
  `not_yet_reviewed`).
- **Generalization**: an oil-price shock, for which no AIB path was written (below).
- **Delivery**: compositions are in `financial_bridge` and paths are `business_construction` transmission paths.
  Accounting links export as `accounting_identity` and uncalibrated links as `represented_uncalibrated` with their
  sign. s32's transition is in the export. New node ids are returned by `/v1/world-models/sally_demo/graph`, the construction
  endpoint and the trace endpoint.

Sally's expected paths, and the Toyota, Tokio Marine and JPMorgan construction tests, pass unchanged.

**Generalization trace (oil-price shock).** `trace(g, "oil.brent", "aib_group")` finds 45 routes, and 36 reach a
financial endpoint. One route is calibrated end to end: oil to euro inflation to the ECB to NII (m03, m10, s32). The
rest are represented with sign but no size:
- the ECB's seven parallel branches into interest income and expense;
- migration into deposit expense and the hedge notional;
- inflation into staff and administrative costs (`aib-c-cpi-staff`, `aib-c-cpi-admin`);
- the ECB through domestic demand and unemployment into the mortgage allowance (first clock) and, through defaults,
  into write-offs (second clock), plus business and property impairment;
- the ECB into mortgage drawdowns and the book;
- the ECB to the Bund (s05) into the hedge roll, securities yield, FVOCI marks and CET1 capital, and new lending;
- the US curve's inflation response through the Bund (m01, m05, m06, m11, m12, s06).

Where it stops: at the share price (nothing leads on from it). It also stops at the trace depth of eight links inside
the hedge, securities, mortgage and fee chains that start in the US curve. The trace reaches the bank through rates,
the hedge, credit, costs, lending and capital.

## Completion report

Outcomes: built and verified (**BV**), built but uncalibrated (**BU**), blocked by a named input (**BL**), not built (**NB**).

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | Line view, P&L bridge, expenses, impairment, NII, loans and deposits views; 47 accounting links with sd-ratio weights | levels are synthetic (G18) |
| G02 | BV | Basis and export metric on every AIB value; EUR units | — |
| G03 | BL | s32 scoped as the reduced form, magnitude "assumption" | AIB's disclosed NII sensitivity (not in the material) |
| G04 | BU | `aib.path.rates_nii` with seven parallel branches into the NII accounts | cash at the central bank, tracker and fixed shares, current-account share (not disclosed) |
| G05 | BL | `aib-c-ecb-depcost` with sign, lag and state tag | AIB's deposit beta (peer betas only) |
| G06 | BU | `aib.path.structural_hedge`, the hedge counter-path, FVOCI marks to CET1 | hedge notional, yield and life; euro swap curve; FVOCI duration |
| G07 | BU | `ireland_economy` values, `aib.path.mortgage_lending` | drawdowns, market share, redemptions, fixed/tracker mix |
| G08 | BU | Impairment views (portfolio and roll-forward), `aib.path.credit_cycle`, `aib.path.house_prices_credit` | IFRS 9 scenarios, weights and sensitivities |
| G09 | BU | `aib-c-ecb-property`, `aib-c-ecb-npe` | property and variable-rate exposure |
| G10 | BU | `aib.path.fees`, `aib.path.wealth_fees` | fee split by product |
| G11 | BU | `aib.comp.expenses`, `aib.path.cost_inflation` | cost guidance, levy |
| G12 | BU | `bank_of_england.policy_rate`, `aib.path.uk_rates` | UK sensitivity; EUR/GBP (no value in the world) |
| G13 | BU | Capital values, three capital paths, the non-additive roll-forward | CET1 target and payout policy (the CET1 level and the broker's path are bound locally) |
| G14 | BU / BL | `aib.path.state_selldown` | the State's current stake and method (not in the material; the prior is synthetic and wide, zero if the sell-down is complete) |
| G15 | BV (structure; undriven) | Segment income and PBT views, Group as residual | segment levels; confirmation of the segment set |
| G16 | BV | Objects present in the v4.1.4 export | — |
| G17 | BV | Node ids served by the query, construction and trace endpoints | — |
| G18 | BL | Baselines bind the FY2025 CET1 ratio and two share prices | AIB results: income statement, segment note, balance sheet |

Counts: 18 gaps. By category (a gap can carry two): MC 12, CAL 5, MAP 2, EXP 1, RET 1. By outcome: BV 5 (G01, G02,
G15, G16, G17), BU 9 (G04, G06–G13) plus G14 in part, BL 4 (G03, G05, G18, and G14's stake), NB 0.

**Links.** 104 links touch AIB's values:
- 47 accounting (fixed weights);
- 4 calibrated causal (s32, s69, s80, s82, all pre-existing);
- 53 uncalibrated (mechanism and sign).

The four new macro links (ECB to domestic demand and drawdowns; house prices to drawdowns; domestic demand to
unemployment) are uncalibrated too. 101 links carry a transition (all except s69, s80 and s82).

**Reconciliation.**
- At the priors, all fourteen additive views add up exactly (0.0%; `check.py --reconcile --statistic median`: 0 flags).
- At the baselines, nothing is computable. All fourteen views flag "no level", because the material holds no AIB P&L
  or balance-sheet figure.
- The unexplained difference cannot be computed. The blocking input is AIB's results. Units are one per view (tested).

**Sources and citations.** `check.py --sources`: 0 source ids unresolved; 9 links and 2 values are cited; 0 material
claims without a citation. Only two claims are material: the existence of excess-capital buybacks and of a payout,
from the broker sheet. Everything else rests on inferred or assumed support and says so.

**Inputs by status** (distinct inputs, after `scripts/construction/inputs.py` searched all 115 files):
- 1 found and connected: the CET1 path and distribution yields, bound as a baseline and a citation.
- 0 found but not connected.
- 20 not disclosed in the reviewed sources. Where the keyword search returned candidates (5 inputs), they were read and
  were about peer banks.
- 0 not yet reviewed.

**Calculation coverage by path.** "Calculated" means the step contributes a size. Accounting links carry a size to the
endpoint at fixed weights. Uncalibrated steps carry a sign only, and any forecast that reaches them lists them as
unquantified. Blocking inputs are all `not_disclosed_in_reviewed_sources` unless stated.

| Path | Calculated (calibrated causal) | Accounting | Excluded: uncalibrated, with sign | Inputs blocking a size |
|---|---|---|---|---|
| `aib.path.rates_nii` | none on the path; s32 is the reduced form beside it | 12 | `aib-c-ecb-cashincome` (+), `aib-c-ecb-loanyield` (+), `aib-c-ecb-depcost` (+), `aib-c-ecb-migration` (−), `aib-c-ecb-hedgefloat` (−), `aib-c-ecb-debtcost` (−), `aib-c-ecb-property` (−), `aib-c-loanyield-income` (+), `aib-c-depcost-expense` (−), `aib-c-ca-ibdep` (−), `aib-c-ibdep-expense` (−), `aib-c-ca-expense` (+), `aib-c-ca-hedgenotional` (+), `aib-c-hedgenotional-income` (+) | cash at central banks, tracker/fixed mix, deposit beta, current-account share, hedge, swapped debt share, IFRS 9 sensitivity (7) |
| `aib.path.structural_hedge` | none | 8 | `aib-c-bund-hedgeyield` (+), `aib-c-bund-secyield` (+), `aib-c-bund-fvoci` (−), `aib-c-bund-newlending` (−), `aib-c-hedgeyield-income` (+), `aib-c-secyield-income` (+), `aib-c-newlending-book` (+), `aib-c-loans-income` (+), `aib-c-fvoci-cet1` (+), `aib-c-pat-cet1` (+), `aib-c-cet1cap-ratio` (+) | hedge, swap curve, securities ladder, FVOCI duration, drawdowns/share, redemptions (6) |
| `aib.path.mortgage_lending` | none | 6 | `aib-c-hpi-drawdowns` (+), `aib-c-drawdowns-newlending` (+), `aib-c-newlending-book` (+), `aib-c-loans-income` (+), `aib-c-loans-rwa` (+) | drawdowns/share, redemptions, risk weights (3) |
| `aib.path.house_prices_credit` | none | 9 | `aib-c-hpi-mortallow` (+), `aib-c-hpi-drawdowns` (+), `aib-c-drawdowns-newlending` (+), `aib-c-newlending-book` (+), `aib-c-loans-income` (+) | IFRS 9 sensitivity, drawdowns/share, redemptions (3) |
| `aib.path.credit_cycle` | none | 9 | `aib-c-dd-unemp` (−), `aib-c-dd-busallow` (+), `aib-c-dd-property` (+), `aib-c-unemp-mortallow` (−), `aib-c-unemp-npe` (+), `aib-c-npe-mortwo` (−), `aib-c-npe-buswo` (−) | IFRS 9 scenarios, weights and sensitivity (1) |
| `aib.path.fees` | none | 7 | `aib-c-dd-fees` (+), `aib-c-dd-business` (+), `aib-c-loans-income` (+) | fee split (1) |
| `aib.path.wealth_fees` | none | 3 | `aib-c-equity-fees` (+) | fee split (1) |
| `aib.path.cost_inflation` | none | 4 | `aib-c-cpi-staff` (−), `aib-c-cpi-admin` (−) | cost guidance, wage terms, levy (1) |
| `aib.path.uk_rates` | none | 3 | `aib-c-boe-ukincome` (+) | UK sensitivity and EUR/GBP, segment results (2) |
| `aib.path.capital_distributions` | none | 0 | `aib-c-pat-cet1` (+), `aib-c-pat-dividends` (+), `aib-c-cet1cap-ratio` (+), `aib-c-ratio-buybacks` (+), `aib-c-buyback-cet1` (−), `aib-c-dividends-cet1` (−) | CET1 target and payout policy (1); the CET1 path (found, connected) |
| `aib.path.capital_requirements` | none | 0 | `aib-c-req-buybacks` (−), `aib-c-buyback-cet1` (−), `aib-c-cet1cap-ratio` (+) | CET1 target and policy (1) |
| `aib.path.balance_sheet_growth` | none | 8 | `aib-c-loans-income` (+), `aib-c-loans-rwa` (+), `aib-c-loans-allowance` (−), `aib-c-pat-cet1` (+), `aib-c-rwa-ratio` (−), `aib-c-cet1cap-ratio` (+) | risk weights, IFRS 9 sensitivity (2) |
| `aib.path.state_selldown` | none on the path; s69, s80 and s82 move the share price beside it | 0 | `aib-c-statesales-stake` (−), `aib-c-statesales-buyback` (+), `aib-c-statesales-price` (−), `aib-c-stake-price` (−), `aib-c-buyback-cet1` (−), `aib-c-cet1cap-ratio` (+) | the State's stake and method (1) |
| Generalization (oil) | m03, m10 (shared), then s32: 1 of 36 routes that reach an endpoint is fully calibrated | the line and P&L views beyond NII | every rate-branch, hedge, credit, cost, lending and capital step | as for the paths above |

**What a downstream agent can now trace or calculate.** It can calculate:
- total operating income as NII plus fees plus other income, and on to profit before and after tax through expenses,
  impairment and exceptional items;
- the same income and profit by reporting segment (reconciled, not driven);
- NII by earning asset (loans, central bank cash, securities, the structural hedge) and by funding source;
- impairment by portfolio, and as write-offs plus allowance change;
- loans by portfolio and deposits by type;
- one calculated size: an ECB move on group NII (s32, an assumption-grade record), carried at fixed weights through
  the accounting views.

It can trace, as signed mechanisms with conditions, timing, evidence and breakers:
- immediate repricing of central bank cash, trackers and floating loans;
- the lagged deposit beta and current-account migration;
- the hedge's floating-leg offset and its slow roll at swap rates;
- securities reinvestment and FVOCI marks into CET1;
- Irish housing into drawdowns, new lending and the book;
- the two IFRS 9 clocks on unemployment and house prices, and the credit cost of higher rates;
- fees on activity and markets, and wage and vendor inflation;
- AIB UK on Bank Rate;
- capital as profit in and distributions out, with the requirement as a floor;
- the State's sell-down (stake, directed buyback, placing overhang).

**What remains unsupported.** Any AIB-specific size: no new link is calibrated, and the supplied material holds no AIB
disclosure. Any dated AIB level beyond the FY2025 CET1 ratio and the share price, and with it reconciliation at
actuals. The State's current stake. EUR/GBP translation (no value in the world). A Sally thesis reaching AIB gets its
NII number from s32 alone, and every structural step is listed as unquantified.

## What the method could not express for this bank

1. **No company material, no calibration.** The method assumes a company workbook and research on the company. For a
   name with none (AIB appears only in peer tables), the build can be complete in structure and still have no
   calibrated step and no baseline to reconcile at. Calibrating from peers (a euro bank's beta, hedge roll and
   pass-through are in the material) needs a "peer-transferred" evidence grade with an explicit similarity condition.
   The evidence vocabulary has none, so those sizes were left out rather than borrowed.
2. **A hedge whose sign depends on the state.** Net hedge interest is notional times (fixed yield minus floating
   rate). Its response to the notional flips sign when the floating rate rises above the hedge yield. A link has one
   sign. The rule is a `state:` tag.
3. **Products and ratios again** (as for JPMorgan): cash income = balance × deposit rate, loan income = balance ×
   yield, new lending = market × share, CET1 ratio = capital / RWA. 15 links carry `identity:` tags.
4. **Slow roll-overs.** The hedge and the securities book reprice by the share that matures each year: a distributed
   lag over years, not one kernel. Uncalibrated timing is text, so the model cannot show that a cut hits NII now and a
   lower swap rate hits it over five years.
5. **Stock-flows for the mortgage book, the State's stake and CET1** (6 `stock-flow:` tags). A placing and a directed
   buyback move both the stake and the bank's capital.
6. **Two reporting views of the same income, plus a driver on one segment.** AIB UK is driven in the segment view,
   while euro NII is driven in the line view. Calibrating the UK link would double count unless the line view's NII is
   split by currency. A matrix composition (segment × line) is needed (`matrix:` would be the tag).
7. **Prudential filters.** The cash-flow hedge reserve is in equity but not in CET1, and FVOCI is in both. The method
   has no way to say "this OCI component is excluded from this capital measure" except by leaving a link out.
8. **Proxies for missing market values.** The Bund 10Y stands in for euro swap rates and the deposit rate for Euribor.
   The world has neither series, and there is no proxy relation (basis spread) object.
9. **A dormant path.** If the State's sell-down is complete, the path is structurally right but inactive. The method
   has no way to mark a path as conditional on a state (stake > 0) other than in text.
10. **Smaller frictions.** The interaction model drops a link's `note` at load, so conversion tags live only in the
    YAML (the test reads them there). There is no `share` value in pct with a Gaussian prior (the kind is Beta), so
    shares are held as structural levels. The trace stops at the first composition total and at eight links. A
    new macro entity changes what the ingest gazetteer resolves: the shared test `tests/ingest/test_gazetteer.py`
    treats a "BoE rate hike" as an unmodelled bank's, so `bank_of_england` carries no "BoE" alias (it is found by
    "Bank of England", "Bank Rate" and "UK base rate") until that test is updated.

## Conversion to the extended method (Oct 18, second pass)

The method gained identities, stock-flows, reconciling views and matrices, state-dependent responses, scenario
calibration, `peer` support, new input statuses (`found_proxy`, `disclosed_not_supplied`), `features.proxy_for` and
`paths[].active_when` ([README](README.md)). This pass converts AIB to those forms. It supersedes the counts in the
completion report above where they differ.

**One driving view per total.**

| Total | Driving view | Reconciling view (`drives: false`) |
|---|---|---|
| `aib_group.total_operating_income` | `aib.comp.income_by_line` (rates, fees and other income act on lines) | `aib.comp.income_by_segment` |
| `aib_group.profit_before_tax` | `aib.comp.pbt` (income, expenses, impairment) | `aib.comp.pbt_by_segment` |

- The reconciling views' accounting links are now uncalibrated (sign "+", no size), so they cannot double count.
- The AIB UK driver (`aib-c-boe-ukincome`) stays uncalibrated in the segment view, so it never adds to the total.
- No matrix was declared, because no segment-by-line cells are available.

**Converted links, by form.**

*10 identities* (each written term link keeps its transition):

| Identity | Formula | Converted from |
|---|---|---|
| `aib.id.cash_income` | 0.01 × cash at central banks × short rate | the ECB-to-cash-income step |
| `aib.id.hedge_spread` | hedge yield − short rate | the hedge's floating leg and fixed yield |
| `aib.id.hedge_income` | 0.01 × hedge notional × hedge spread | replaces the sign-flip `state:` tag (see below) |
| `aib.id.loan_income` | 0.01 × gross loans × loan yield | `aib-c-loanyield-income`, `aib-c-loans-income` |
| `aib.id.deposit_expense` | −0.01 × interest-bearing deposits × deposit cost | the coefficient carries the charge's sign |
| `aib.id.securities_income` | 0.01 × securities × securities yield | `aib-c-secyield-income` |
| `aib.id.new_lending` | 0.01 × Irish mortgage drawdowns × market share | `aib-c-drawdowns-newlending`, `aib-c-share-newlending` |
| `aib.id.rwa` | 0.01 × gross loans × RWA density | `aib-c-loans-rwa` |
| `aib.id.cet1_ratio` | 100 × CET1 capital / RWA | `aib-c-cet1cap-ratio`, `aib-c-rwa-ratio` |
| `aib.id.dividends` | 0.01 × profit after tax × payout ratio | `aib-c-pat-dividends` |

*2 stock-flows* (period 365 days, flows per year):
- `aib.sf.mortgage_book`: book += new lending − redemptions.
- `aib.sf.cet1`: CET1 += profit after tax − dividends − buybacks.

*New supporting values*:
- `aib_group.short_rate`, with `features.proxy_for` (€STR and 3M Euribor: the deposit rate stands in);
- `aib_group.hedge_spread`, `aib_group.payout_ratio`, `aib_group.rwa_density`, `aib_group.mortgage_redemptions`.

*Restructured links*:
- `aib-c-ecb-cashincome` and `aib-c-ecb-hedgefloat` became one entry, `aib-c-ecb-shortrate` (ECB to short rate), plus
  the identity terms.
- `aib-c-ca-expense` was removed. The mix effect now runs through interest-bearing balances in `aib.id.deposit_expense`.
- The allowance values were renamed `*_allowance_build`, so their head word is no longer a common English word
  (check.py `KEYWORD`).

**Steps left uncalibrated, and why** (each link's `note` says so):
- *The ECB entries* (ECB to the short rate, loan yield, deposit cost, current accounts and swapped debt) stay unsized by
  design. s32 carries the ECB's net effect on NII, and every step below these entries is now an exact identity into
  NII. Sizing an entry would count the move twice. Once AIB's own sensitivity is supplied, the entries should be sized
  (the beta as a rises/falls asymmetry) and s32 retired, together.
- *Deposit beta asymmetry*: not converted, because an asymmetric link must carry sizes.
- *Loan-yield response* falls as fixed-rate lending grows. That is a moving share, not a threshold, asymmetry or sign
  flip.
- *Buyback threshold*: needs the management CET1 target (not supplied) and a sized link.
- *The State's stake*: a percentage of shares, while the sales are in euros. Its roll-forward needs the share price and
  the share count.
- *FVOCI reserve into CET1*: the reserve is a level inside CET1, not a flow.

**New calibration.** `aib-c-bund-hedgeyield` is sized from a named comparable (support `peer`):
- the effect is 0.2 sd/sd, with sigma 0.1 (half the effect, since no range was given) and a 365-day lag;
- the basis is a euro peer's structural hedge, which rolls about one fifth a year at the long-end rate;
- `calibrate.py --support peer` reproduces the size, and the citation is in the local `citations.json`.

The full pass-through builds over the hedge's life, which one kernel cannot hold. Scenario calibration (`--disclosure`)
was not usable, because no AIB scenario disclosure is in the material.

**Input statuses (22 distinct).**

| Status | Count | What |
|---|---|---|
| found and connected | 1 | |
| found as a proxy | 3 | hedge notional, yield and life (peer); deposit beta (peer); medium-term swap rates (the Bund stands in) |
| disclosed but not supplied | 17 | AIB publishes these in its annual report, results and Pillar 3, or they are public market statistics; each lists what was searched |
| not disclosed in the reviewed sources | 0 | |
| not yet reviewed | 0 | |

Existence claims for AIB-specific structure (the hedge, the tracker book, the State's stake, AIB UK, the ECB entries)
are now `public_not_supplied` rather than `inferred`.

**Links, before and after** (links touching AIB's values):

| | Before | After |
|---|---|---|
| Total | 104 | 110 |
| Accounting (sized) | 47 | 39 |
| Accounting (reconciling, unsized) | 0 | 8 |
| Identity | 0 | 20 |
| Stock-flow | 0 | 5 |
| Calibrated causal | 4 (s32, s69, s80, s82) | 5 (+ `aib-c-bund-hedgeyield`, peer) |
| Uncalibrated causal | 53 | 33 |

**Reconciliation now.**
- `check.py --reconcile --statistic median`: 14 additive views, 0 flags (both reconciling views are checked too).
- The 10 identities all reconcile within 0.1% at the priors (`reconcile_identities`). Cash income, loan income and
  new lending miss by 0.05–0.1% because of rounding in the round priors.
- At the baselines, all 14 views and both stock-flows are `blocked`, not flagged: the material has no AIB P&L,
  balance-sheet or capital roll-forward levels.
- `bundles.py check` on the baselines passes.

**Coverage now.** For the forecast "the ECB cuts by 25bp" (API `coverage`):

*Contributed* (sized):
- s32, s69, s80, s82;
- the long end: ECB to Bund (s05), then `aib-c-bund-hedgeyield`, then `aib-c-hedgeyield-spread`, then
  `aib.id.hedge_income`;
- the accounting and P&L links up to profit after tax;
- the CET1 stock-flow and the CET1 ratio and dividend identities.

*Excluded as uncalibrated, with sign*: the ECB entries (short rate +, loan yield +, deposit cost +, migration −,
swapped debt −, property −, NPE +), the ECB's effect on domestic demand and drawdowns, the Bund's effect on securities
yield, FVOCI marks and new lending, equity markets to fees, and the ratio-to-buybacks link.

One accounting link (hedge income into interest income) is listed as `outside_the_forecast_networks`. The hedge
income it carries is therefore not added to NII in this forecast: a gap in the forecast's network isolation, not in
the construction.

*Per target*:
- NII: 1 quantified route, through a summary link only (s32); 2 of its 21 own steps are quantified.
- Profit after tax: 1 quantified route through own steps (3 of 15).
- CET1 ratio: 1 route through own steps (5 of 13).
- Dividends: 1 route through own steps (4 of 7).

The structure is now exact below the ECB entries. Sizing those entries is the single input that would turn the rates
path from summary-link to own-step coverage.

**Paths.**
- `aib.path.state_selldown` has `active_when: "while the State holds AIB shares (state_shareholding above zero);
  dormant once the sell-down is complete"`.
- The rates path's parallel branches are now short_rate, loans, beta, migration, wholesale and credit.

**What still cannot be expressed.**
1. **A reduced form beside an exact structure.** The method has no rule for when a summary link (s32) and the
   structure under it may both carry sizes. The only safe choice was to leave the structure's entry links unsized.
   Needed: a declared "reduced form of path X" relation that the forecast uses *instead of* the path's entries, not
   alongside them.
2. **A sign that flips with a level, inside an identity.** Net hedge interest is now an exact product, but it is
   linearized at a positive spread. When the short rate rises above the hedge yield, the response does not flip,
   because a `state:` block cannot sit on an identity link.
3. **Multi-year roll-overs.** The hedge and securities books reprice by the share maturing each year. One kernel (a
   year-one size) understates the eventual effect five-fold.
4. **Proxy on the use, not the value.** The Bund 10Y stands in for the euro swap rate only on AIB's hedge-roll link.
   `features.proxy_for` belongs to a value, and the Bund is a real series for other companies. So the substitution is
   stated on the link and in a `found_proxy` input, not as a feature.
5. **Unit-changing stock-flows.** The State's stake (percent of shares) is driven by sales in euros through the share
   price and share count.
6. **A level inside a stock.** The FVOCI reserve is part of CET1, but it is neither a flow nor a same-period part of a
   composition the method can drive.
7. **Moving-share responses.** The ECB-to-loan-yield response depends on a floating share that falls over time. That
   is a product with a slowly moving factor, not one of the three state forms.
8. **Two forms in one link.** The deposit beta needs an asymmetry and an identity-consistent entry at once.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities aib_group` from the loaded model (the
same objects the API serves at `/v1/world-models/sally_demo/entities/aib_group/construction`). A `?` marks a step whose size is unknown
(uncalibrated). Levels are left out here; the local copy adds them (`view/levels.md`).

110 links touch its values: 69 calibrated, 41 uncalibrated (represented, size unknown), 47 accounting, 20 identity, 5 stock-flow; 0 state-dependent; 107 carry a transition.

### Business composition

#### credit: non-property business impairment: net write-offs plus allowance change (IFRS 9 roll-forward) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB business lending net write-offs | `aib_group.business_write_offs` |
| AIB business lending ECL allowance build | `aib_group.business_allowance_build` |
| **Total: AIB non-property business impairment** | `aib_group.business_ecl` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity of the allowance roll-forward.

#### capital: CET1 capital roll-forward: profit in, distributions out, FVOCI marks (not an additive partition: flows into a stock) (€bn)

| Part | Value |
|---|---|
| AIB profit after tax | `aib_group.profit_after_tax` |
| AIB ordinary dividends | `aib_group.ordinary_dividends` |
| AIB share buybacks | `aib_group.buybacks` |
| AIB FVOCI reserve | `aib_group.fvoci_reserve` |
| **Total: AIB CET1 capital** | `aib_group.cet1_capital` |

A non-additive view: its parts overlap.
Capital accumulates: next period's CET1 is this period's plus profit less dividends, buybacks and AT1 coupons, plus the change in the FVOCI reserve and in deductions. The method has no stock-flow link, so these are signed causal links (aib-c-pat-cet1, aib-c-dividends-cet1, aib-c-buyback-cet1, aib-c-fvoci-cet1).

#### liabilities: customer accounts: current accounts plus interest-bearing deposits (€bn)

| Part | Value |
|---|---|
| AIB current accounts | `aib_group.current_accounts` |
| AIB interest-bearing deposits | `aib_group.interest_bearing_deposits` |
| **Total: AIB customer accounts** | `aib_group.customer_deposits` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
A two-way split of the deposit base by whether it pays a market-linked rate (an exact split by construction). The current-account share is what makes the bank rate-sensitive and what the structural hedge is sized against.

#### credit: net credit impairment charge by portfolio (negative values) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB residential mortgage impairment | `aib_group.mortgage_ecl` |
| AIB personal lending impairment | `aib_group.personal_ecl` |
| AIB property and construction impairment | `aib_group.property_ecl` |
| AIB non-property business impairment | `aib_group.business_ecl` |
| Residual: AIB other impairment | `aib_group.other_ecl` |
| **Total: AIB net credit impairment charge** | `aib_group.ecl_charge` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Mortgages are the largest book but a small charge in a rising housing market; property and business lending are smaller and lumpier.

#### reporting segments: operating expenses by type (negative values) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB staff costs | `aib_group.staff_costs` |
| AIB depreciation and amortisation | `aib_group.depreciation` |
| AIB bank levies and regulatory fees | `aib_group.bank_levies` |
| Residual: AIB other general and administrative expenses | `aib_group.other_admin_expenses` |
| **Total: AIB operating expenses** | `aib_group.operating_expenses` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Staff costs follow wage agreements; variable pay is restricted, so costs do not flex with income (little operating-leverage offset).

#### product: total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB net interest income | `aib_group.net_interest_income` |
| AIB net fee and commission income | `aib_group.fee_income` |
| Residual: AIB other operating income | `aib_group.other_income` |
| **Total: AIB total operating income** | `aib_group.total_operating_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driven view: rates enter through NII, activity and markets through fees. Other income is the residual (trading, hedge ineffectiveness, disposal gains). Not the segment view (aib.comp.income_by_segment): never added to it.

#### reporting segments: total operating income by reporting segment (IFRS, EUR) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB Retail Banking operating income | `aib_group.retail_banking_income` |
| AIB Capital Markets operating income | `aib_group.capital_markets_income` |
| AIB UK operating income | `aib_group.aib_uk_income` |
| Residual: AIB Group segment operating income | `aib_group.group_segment_income` |
| **Total: AIB total operating income** | `aib_group.total_operating_income` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reported view, reconciled but driven only through AIB UK (aib-c-boe-ukincome, uncalibrated): the euro rate, fee and cost drivers act on lines that cut across segments. Segment NII includes funds-transfer-pricing credits for deposits; Group is the residual and holds what is not allocated. No intersegment eliminations line is represented: internal charges net to zero inside the segments.

#### liabilities: interest expense by funding source (negative values) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB interest expense on customer deposits | `aib_group.deposit_interest_expense` |
| AIB interest expense on debt securities in issue | `aib_group.debt_interest_expense` |
| Residual: AIB other interest expense | `aib_group.other_interest_expense` |
| **Total: AIB interest expense** | `aib_group.interest_expense` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Deposits reprice by the deposit beta with a lag; MREL and covered bonds are mostly swapped to floating, so they reprice with money-market rates.

#### investment assets: interest income by earning asset, incl. net interest on the structural hedge (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB interest income on loans | `aib_group.loan_interest_income` |
| AIB interest income on central bank placements | `aib_group.cash_interest_income` |
| AIB interest income on investment securities | `aib_group.securities_interest_income` |
| AIB net interest on the structural hedge | `aib_group.structural_hedge_income` |
| Residual: AIB other interest income | `aib_group.other_interest_income` |
| **Total: AIB interest income** | `aib_group.interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Balances and yields are operating states; income is balance times yield, which no fixed weight represents. The hedge line is net (fixed received less floating paid), so a lower policy rate raises it while it lowers cash and floating-loan income.

#### investment assets: gross loans to customers by portfolio (€bn)

| Part | Value |
|---|---|
| AIB residential mortgages | `aib_group.mortgage_book` |
| AIB personal lending | `aib_group.personal_loans` |
| AIB property and construction lending | `aib_group.property_loans` |
| AIB non-property business lending | `aib_group.business_loans` |
| Residual: AIB other lending | `aib_group.other_loans` |
| **Total: AIB gross loans to customers** | `aib_group.gross_loans` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The asset portfolios that carry the yield and credit mechanisms; balances, not flows.

#### credit: mortgage impairment: net write-offs plus allowance change (IFRS 9 roll-forward) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB mortgage net write-offs | `aib_group.mortgage_write_offs` |
| AIB mortgage ECL allowance build | `aib_group.mortgage_allowance_build` |
| **Total: AIB residential mortgage impairment** | `aib_group.mortgage_ecl` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity of the allowance roll-forward (other movements are negligible at this level). Write-offs follow realised losses, late; the allowance change follows the forward-looking scenarios and stage migration, early.

#### investment assets: net interest income: interest income less interest expense (IFRS) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB interest income | `aib_group.interest_income` |
| AIB interest expense | `aib_group.interest_expense` |
| **Total: AIB net interest income** | `aib_group.net_interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity.

#### reporting segments: profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB total operating income | `aib_group.total_operating_income` |
| AIB operating expenses | `aib_group.operating_expenses` |
| AIB net credit impairment charge | `aib_group.ecl_charge` |
| Residual: AIB exceptional and other items | `aib_group.exceptional_items` |
| **Total: AIB profit before tax** | `aib_group.profit_before_tax` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity: expenses and impairment are negative values. The residual holds exceptional items and associates, so underlying profit (before exceptional items) is the three members.

#### reporting segments: profit before tax by reporting segment (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB Retail Banking profit before tax | `aib_group.retail_banking_pbt` |
| AIB Capital Markets profit before tax | `aib_group.capital_markets_pbt` |
| AIB UK profit before tax | `aib_group.aib_uk_pbt` |
| Residual: AIB Group segment profit before tax | `aib_group.group_segment_pbt` |
| **Total: AIB profit before tax** | `aib_group.profit_before_tax` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reported view, reconciled but undriven; never added to aib.comp.pbt. Group (residual) holds central costs and exceptional items.

#### reporting segments: profit after tax: profit before tax less income tax (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| AIB profit before tax | `aib_group.profit_before_tax` |
| AIB income tax | `aib_group.income_tax` |
| **Total: AIB profit after tax** | `aib_group.profit_after_tax` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity. The tax charge is below the trading rate times profit while deferred tax assets on past losses are used; AT1 coupons are a distribution below this line.

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `aib.id.cash_income` (product) | AIB interest income on central bank placements = 0.01 x AIB cash at central banks x AIB euro short rate earned and paid | AIB cash at central banks (factor, +0.667); AIB euro short rate earned and paid (factor, +0.741) | €bn/yr = €bn x % x 0.01 |
| `aib.id.cet1_ratio` (ratio) | AIB CET1 ratio = 100 x AIB CET1 capital / AIB risk-weighted assets | AIB CET1 capital (numerator, +1.389); AIB risk-weighted assets (denominator, -1.163) | pct = 100 x €bn / €bn |
| `aib.id.deposit_expense` (product) | AIB interest expense on customer deposits = -0.01 x AIB interest-bearing deposits x AIB cost of interest-bearing deposits | AIB interest-bearing deposits (factor, -0.562); AIB cost of interest-bearing deposits (factor, -0.844) | €bn/yr (negative) = -0.01 x €bn x % |
| `aib.id.dividends` (product) | AIB ordinary dividends = 0.01 x AIB profit after tax x AIB ordinary dividend payout ratio | AIB profit after tax (factor, +0.420); AIB ordinary dividend payout ratio (factor, +0.600) | €bn/yr = €bn/yr x % x 0.01 |
| `aib.id.hedge_income` (product) | AIB net interest on the structural hedge = 0.01 x AIB structural hedge notional x AIB structural hedge net spread | AIB structural hedge notional (factor, +0.133); AIB structural hedge net spread (factor, +1.000) | €bn/yr = €bn x % x 0.01 |
| `aib.id.hedge_spread` (difference) | AIB structural hedge net spread = AIB structural hedge fixed yield - AIB euro short rate earned and paid | AIB structural hedge fixed yield (total, +0.500); AIB euro short rate earned and paid (deduction, -0.833) | pct = pct - pct |
| `aib.id.loan_income` (product) | AIB interest income on loans = 0.01 x AIB gross loans to customers x AIB loan yield | AIB gross loans to customers (factor, +0.750); AIB loan yield (factor, +0.794) | €bn/yr = €bn x % x 0.01 |
| `aib.id.new_lending` (product) | AIB new mortgage lending = 0.01 x Ireland mortgage drawdowns x AIB share of Irish mortgage drawdowns | ireland_economy.mortgage_drawdowns (factor, +0.667); AIB share of Irish mortgage drawdowns (factor, +0.500) | €bn/yr = €bn/yr x % x 0.01 |
| `aib.id.rwa` (product) | AIB risk-weighted assets = 0.01 x AIB gross loans to customers x AIB RWA density on loans | AIB gross loans to customers (factor, +1.000); AIB RWA density on loans (factor, +1.000) | €bn = €bn x % x 0.01 |
| `aib.id.securities_income` (product) | AIB interest income on investment securities = 0.01 x AIB investment securities x AIB investment securities yield | AIB investment securities (factor, +0.833); AIB investment securities yield (factor, +0.769) | €bn/yr = €bn x % x 0.01 |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `aib.sf.cet1` | AIB CET1 capital (closing) = AIB CET1 capital (opening) + AIB profit after tax - AIB ordinary dividends - AIB share buybacks, per 365 days | AIB profit after tax (inflow, +0.315); AIB ordinary dividends (outflow, -0.375); AIB share buybacks (outflow, -0.750) |
| `aib.sf.mortgage_book` | AIB residential mortgages (closing) = AIB residential mortgages (opening) + AIB new mortgage lending - AIB mortgage redemptions, per 365 days | AIB new mortgage lending (inflow, +0.526); AIB mortgage redemptions (outflow, -0.439) |

### Operating and financial paths

#### AIB loan growth to income and capital

**Trigger:** the loan book grows. **Endpoint:** AIB CET1 ratio.

AIB gross loans to customers → [income] AIB interest income on loans → [capital] AIB risk-weighted assets → [allowance] AIB business lending ECL allowance build? → AIB interest income → AIB net interest income → AIB total operating income → AIB profit before tax → AIB non-property business impairment → AIB net credit impairment charge → AIB profit before tax → AIB profit after tax → AIB CET1 capital → AIB CET1 ratio → AIB CET1 ratio  (? marks a step whose size is unknown)

Loan growth earns interest at the loan yield, needs a day-one IFRS 9 allowance, and consumes RWA; earnings rebuild capital, RWA dilutes the ratio.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [income] `aib-c-loans-income` | A larger average loan book earns more interest at the prevailing yield (AIB (lending)) | bilinear: balance times yield; growth funded from deposits (the loan-to-deposit ratio is low); observable: average gross loans and loan interest income | onset same quarter; build as loans are drawn; persists while held; recognized interest income each quarter | inferred / inferred / inferred / inferred | growth in low-margin lending adds less | interest income on loans | +0.75 sd/sd (identity) |
| 2 [capital] `aib-c-loans-rwa` | More loans add risk-weighted assets at their risk weights (mortgages low under internal models, business and property lending high) (AIB (capital management)) | risk weights as they are; mix of growth; observable: RWA, quarterly | onset same quarter; build none; persists while held; recognized RWA at each reporting date | inferred / inferred / inferred / inferred | model changes and regulatory floors (the output floor phases in) | risk-weighted assets | +1.00 sd/sd (identity) |
| 3 [allowance] `aib-c-loans-allowance` | Under IFRS 9 each new loan carries a stage-1 twelve-month expected loss at origination, so lending growth adds to the allowance charge before any loss (AIB credit risk) | growth in loans with material expected loss; observable: allowance by stage | onset at origination; build none; persists while the book grows; recognized impairment charge at each reporting date | inferred / inferred / unknown / inferred | growth concentrated in low-loss mortgages | business ECL allowance change | unknown |
| 4 `aib-a-ii-loan-interest-income` | AIB interest income on loans is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.64 sd/sd (accounting) |
| 5 `aib-a-nii-interest-income` | AIB interest income is one part of AIB net interest income (net interest income: interest income less interest expense (IFRS)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net interest income | +1.15 sd/sd (accounting) |
| 6 `aib-a-inc-net-interest-income` | AIB net interest income is one part of AIB total operating income (total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB total operating income | +1.00 sd/sd (accounting) |
| 7 `aib-a-pbt-total-operating-income` | AIB total operating income is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +1.25 sd/sd (accounting) |
| 8 `aib-a-becl-business-allowance-build` | AIB business lending ECL allowance build is one part of AIB non-property business impairment (non-property business impairment: net write-offs plus allowance change (IFRS 9 roll-forward)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB non-property business impairment | +0.80 sd/sd (accounting) |
| 9 `aib-a-ecl-business-ecl` | AIB non-property business impairment is one part of AIB net credit impairment charge (net credit impairment charge by portfolio (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net credit impairment charge | +0.42 sd/sd (accounting) |
| 10 `aib-a-pbt-ecl-charge` | AIB net credit impairment charge is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +0.82 sd/sd (accounting) |
| 11 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |
| 12 `aib-c-pat-cet1` | Profit after tax adds to CET1 capital, less the foreseeable dividend and AT1 coupons deducted as accrued (AIB (capital management)) | profit recognized by the regulator; deferred tax on losses is deducted from CET1 as it is used, so recognized profit adds close to one for one; observable: CET1 capital roll-forward, quarterly | onset each quarter; build none; persists accumulates; recognized CET1 at each reporting date | inferred / inferred / inferred / inferred | foreseeable distributions deducted at once | CET1 capital | +0.32 sd/sd (stock-flow, accumulates per 365 days) |
| 13 `aib-c-rwa-ratio` | The CET1 ratio is CET1 capital over RWA; RWA growth dilutes it (AIB) | capital unchanged; observable: CET1 ratio and RWA | onset same reporting date; build none; persists identity; recognized Pillar 3 and results | inferred / inferred / inferred / inferred | capital growth | CET1 ratio | -1.16 sd/sd (identity) |
| 14 `aib-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (AIB) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized Pillar 3 and results | inferred / inferred / inferred / inferred | RWA growth | CET1 ratio | +1.39 sd/sd (identity) |

Unresolved inputs: IFRS 9 scenario weights and the ECL sensitivity to unemployment and house prices (disclosed not supplied); risk weights by portfolio (disclosed not supplied).

#### AIB profit to capital and distributions

**Trigger:** profit after tax rises. **Endpoint:** AIB CET1 ratio.

AIB profit after tax → [capital] AIB CET1 capital → [dividend] AIB ordinary dividends → AIB CET1 ratio → AIB share buybacks? → AIB CET1 capital → AIB CET1 capital  (? marks a step whose size is unknown)

Profit builds CET1; the dividend is a payout share of profit; capital above the management target is returned through buybacks; both distributions consume CET1. Capital is a stock fed by flows (stock-flow tags on the links).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [capital] `aib-c-pat-cet1` | Profit after tax adds to CET1 capital, less the foreseeable dividend and AT1 coupons deducted as accrued (AIB (capital management)) | profit recognized by the regulator; deferred tax on losses is deducted from CET1 as it is used, so recognized profit adds close to one for one; observable: CET1 capital roll-forward, quarterly | onset each quarter; build none; persists accumulates; recognized CET1 at each reporting date | inferred / inferred / inferred / inferred | foreseeable distributions deducted at once | CET1 capital | +0.32 sd/sd (stock-flow, accumulates per 365 days) |
| 2 [dividend] `aib-c-pat-dividends` | The ordinary dividend is set as a share of profit under the distribution policy (AIB board) | the payout policy as it is; observable: dividend per share and payout ratio | onset at results; build none; persists annual; recognized foreseeable dividend deducted from CET1 as accrued | broker / inferred / inferred / inferred | a policy change; a supervisory restriction | ordinary dividends | +0.42 sd/sd (identity) |
| 3 `aib-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (AIB) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized Pillar 3 and results | inferred / inferred / inferred / inferred | RWA growth | CET1 ratio | +1.39 sd/sd (identity) |
| 4 `aib-c-ratio-buybacks` | Capital above the management target is returned through buybacks (and directed buybacks from the State) once the regulator approves, so the ratio is run down toward the target over time and total distributions exceed the dividend (AIB board; the ECB/SSM (approval)) | CET1 above the management target; supervisory approval; observable: announced buybacks and the CET1 path | onset at full-year or half-year results; build annual programmes; persists while excess capital lasts; recognized equity reduced as shares are bought | broker / broker / unknown / inferred | supervisory refusal; M&A or organic growth that consumes the excess; a stress-test result | share buybacks | unknown |
| 5 `aib-c-buyback-cet1` | Shares bought back reduce CET1 capital by the amount spent (deducted when approved) (AIB board) | approved programme; observable: CET1 roll-forward | onset at approval (deducted); build none; persists permanent; recognized CET1 at each reporting date | inferred / inferred / inferred / inferred | none | CET1 capital | -0.75 sd/sd (stock-flow, accumulates per 365 days) |
| 6 `aib-c-dividends-cet1` | Foreseeable dividends are deducted from CET1 as profit accrues (AIB board) | the accrual policy; observable: CET1 roll-forward | onset as accrued; build none; persists permanent; recognized CET1 at each reporting date | inferred / inferred / inferred / inferred | none | CET1 capital | -0.38 sd/sd (stock-flow, accumulates per 365 days) |

Unresolved inputs: management CET1 target and distribution policy (payout ratio, buyback approval) (disclosed not supplied); the CET1 ratio path and total distribution yields the broker expects (found connected).

#### AIB capital requirement to buybacks

**Trigger:** the CET1 requirement rises (Pillar 2, a buffer). **Endpoint:** AIB CET1 ratio.

AIB CET1 requirement → AIB share buybacks? → AIB CET1 capital → AIB CET1 ratio  (? marks a step whose size is unknown)

A higher requirement raises the floor under the management target and leaves less capital to return.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `aib-c-req-buybacks` | A higher requirement (Pillar 2, buffers, a countercyclical buffer increase) raises the floor under the target and cuts the capital available for buybacks (Central Bank of Ireland and the ECB/SSM; AIB board) | the management target moves with the requirement; observable: SREP decision and buffer announcements | onset at the next distribution decision; build none; persists while the requirement holds; recognized buyback approval | inferred / inferred / unknown / inferred | a large excess over target | share buybacks | unknown |
| 2 `aib-c-buyback-cet1` | Shares bought back reduce CET1 capital by the amount spent (deducted when approved) (AIB board) | approved programme; observable: CET1 roll-forward | onset at approval (deducted); build none; persists permanent; recognized CET1 at each reporting date | inferred / inferred / inferred / inferred | none | CET1 capital | -0.75 sd/sd (stock-flow, accumulates per 365 days) |
| 3 `aib-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (AIB) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized Pillar 3 and results | inferred / inferred / inferred / inferred | RWA growth | CET1 ratio | +1.39 sd/sd (identity) |

Unresolved inputs: management CET1 target and distribution policy (payout ratio, buyback approval) (disclosed not supplied).

#### AIB inflation to operating expenses

**Trigger:** euro-area inflation rises. **Endpoint:** AIB profit after tax.

Euro area inflation → [wages] AIB staff costs? → [vendors] AIB other general and administrative expenses? → AIB operating expenses → AIB operating expenses → AIB profit before tax → AIB profit after tax  (? marks a step whose size is unknown)

Inflation feeds the next wage agreement and vendor and property contracts; variable pay is restricted, so costs do not flex down with income.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [wages] `aib-c-cpi-staff` | Higher inflation feeds the next wage agreement and pension costs, raising staff costs (more negative) with a lag (AIB (management and staff unions)) | wage agreements indexed to or negotiated on inflation; observable: staff costs per employee | onset at the next wage round; build a year; persists permanent (a level shift); recognized operating expenses | inferred / inferred / unknown / inferred | headcount reductions; automation | staff costs | unknown |
| 2 [vendors] `aib-c-cpi-admin` | Technology contracts, property and professional services are repriced with inflation (AIB procurement; vendors) | contracts indexed or renegotiated; observable: general and administrative expenses | onset at contract renewal; build a year; persists permanent; recognized operating expenses | inferred / inferred / unknown / inferred | cost programmes; fixed-price contracts | other general and administrative expenses | unknown |
| 3 `aib-a-opex-staff-costs` | AIB staff costs is one part of AIB operating expenses (operating expenses by type (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB operating expenses | +0.62 sd/sd (accounting) |
| 4 `aib-a-opex-other-admin-expenses` | AIB other general and administrative expenses is one part of AIB operating expenses (operating expenses by type (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB operating expenses | +0.62 sd/sd (accounting) |
| 5 `aib-a-pbt-operating-expenses` | AIB operating expenses is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +0.54 sd/sd (accounting) |
| 6 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |

Unresolved inputs: cost guidance, wage agreement terms and the bank levy (disclosed not supplied).

#### AIB Irish economy to impairment (two clocks)

**Trigger:** Irish domestic demand weakens. **Endpoint:** AIB profit after tax.

Ireland modified domestic demand growth → [labour] Ireland unemployment rate? → [outlook] AIB business lending ECL allowance build? → [property] AIB property and construction impairment? → [mortgage_outlook] AIB mortgage ECL allowance build? → [defaults] AIB non-performing exposure ratio? → [mortgage_losses] AIB mortgage net write-offs? → [business_losses] AIB business lending net write-offs? → AIB residential mortgage impairment → AIB residential mortgage impairment → AIB non-property business impairment → AIB non-property business impairment → AIB net credit impairment charge → AIB net credit impairment charge → AIB net credit impairment charge → AIB profit before tax → AIB profit after tax  (? marks a step whose size is unknown)

Weaker demand raises unemployment; IFRS 9 builds allowances when the outlook changes (the first clock: business allowances at once, mortgage allowances on the unemployment path), while arrears and stage-3 defaults turn into realised write-offs quarters later (the second clock). Property credit weakens with demand. Each portfolio's charge adds to the impairment line and on to profit.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [labour] `aib-c-dd-unemp` | Weaker domestic demand cuts hiring and raises unemployment with a lag (Irish employers) | ordinary labour-market response; observable: monthly unemployment | onset 1-2 quarters; build several quarters; persists while demand is weak; recognized monthly labour data | inferred / inferred / unknown / inferred | multinational hiring and labour-force growth | Irish unemployment | unknown |
| 2 [outlook] `aib-c-dd-busallow` | A stronger domestic outlook lowers forward-looking default probabilities for SMEs and corporates, releasing allowances; a weaker one builds them (AIB credit risk) | scenarios updated; observable: business allowance build or release | onset at the next reporting date; build none; persists until the outlook changes; recognized impairment charge at each reporting date | inferred / inferred / unknown / inferred | single-name defaults dominate in corporate books | business ECL allowance change | unknown |
| 3 [property] `aib-c-dd-property` | Stronger domestic demand supports rents, occupancy and development sales, lowering property impairment (a smaller negative charge) (property borrowers) | the cycle in commercial property; observable: property loans in stage 2 and 3 | onset 2-4 quarters; build several quarters; persists while demand holds; recognized impairment charge | inferred / inferred / unknown / inferred | office-specific weakness; refinancing at higher rates | property and construction impairment | unknown |
| 4 [mortgage_outlook] `aib-c-unemp-mortallow` | IFRS 9 weights the forward-looking scenarios: a higher unemployment path raises probabilities of default and moves loans to stage 2 (lifetime loss), so the allowance builds when the outlook changes, before arrears appear (AIB credit risk (IFRS 9 models and post-model adjustments)) | the macro scenarios are updated; staging thresholds as they are; observable: allowance build, stage 2 share, scenario weights | onset at the next reporting date; build none; persists until the outlook improves; recognized impairment charge at each reporting date | inferred / inferred / unknown / inferred | post-model overlays already held absorb it; management judgement in scenario weights | mortgage ECL allowance change | unknown |
| 5 [defaults] `aib-c-unemp-npe` | Unemployment pushes households and small firms into arrears and, after the cure period, into stage 3; realised losses follow later, because Irish mortgage arrears resolve slowly (borrowers) | household debt service as it is; observable: arrears and stage-3 inflows, half-yearly | onset 2-3 quarters; build several quarters; persists while unemployment stays high; recognized stage migration at each reporting date | inferred / inferred / unknown / inferred | forbearance and payment breaks; low household leverage | non-performing exposure ratio | unknown |
| 6 [mortgage_losses] `aib-c-npe-mortwo` | Defaulted mortgages are written off, net of recoveries, after workout or sale, typically quarters to years after default (the second clock) (AIB workout units) | workout and repossession timelines; observable: write-offs net of recoveries | onset several quarters after default; build years; persists until resolved; recognized write-offs charged against the allowance | inferred / inferred / unknown / inferred | allowances already held absorb the loss (a write-off against an existing allowance does not hit profit again) | mortgage net write-offs | unknown |
| 7 [business_losses] `aib-c-npe-buswo` | Defaulted business loans are written off net of recoveries after restructuring or enforcement (AIB workout units) | enforcement timelines; observable: business write-offs | onset 2-4 quarters after default; build several quarters; persists until resolved; recognized write-offs | inferred / inferred / unknown / inferred | recoveries from collateral and guarantees | business net write-offs | unknown |
| 8 `aib-a-mecl-mortgage-allowance-build` | AIB mortgage ECL allowance build is one part of AIB residential mortgage impairment (mortgage impairment: net write-offs plus allowance change (IFRS 9 roll-forward)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB residential mortgage impairment | +0.80 sd/sd (accounting) |
| 9 `aib-a-mecl-mortgage-write-offs` | AIB mortgage net write-offs is one part of AIB residential mortgage impairment (mortgage impairment: net write-offs plus allowance change (IFRS 9 roll-forward)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB residential mortgage impairment | +0.40 sd/sd (accounting) |
| 10 `aib-a-becl-business-allowance-build` | AIB business lending ECL allowance build is one part of AIB non-property business impairment (non-property business impairment: net write-offs plus allowance change (IFRS 9 roll-forward)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB non-property business impairment | +0.80 sd/sd (accounting) |
| 11 `aib-a-becl-business-write-offs` | AIB business lending net write-offs is one part of AIB non-property business impairment (non-property business impairment: net write-offs plus allowance change (IFRS 9 roll-forward)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB non-property business impairment | +0.40 sd/sd (accounting) |
| 12 `aib-a-ecl-mortgage-ecl` | AIB residential mortgage impairment is one part of AIB net credit impairment charge (net credit impairment charge by portfolio (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net credit impairment charge | +0.42 sd/sd (accounting) |
| 13 `aib-a-ecl-business-ecl` | AIB non-property business impairment is one part of AIB net credit impairment charge (net credit impairment charge by portfolio (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net credit impairment charge | +0.42 sd/sd (accounting) |
| 14 `aib-a-ecl-property-ecl` | AIB property and construction impairment is one part of AIB net credit impairment charge (net credit impairment charge by portfolio (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net credit impairment charge | +0.42 sd/sd (accounting) |
| 15 `aib-a-pbt-ecl-charge` | AIB net credit impairment charge is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +0.82 sd/sd (accounting) |
| 16 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |

Unresolved inputs: IFRS 9 scenario weights and the ECL sensitivity to unemployment and house prices (disclosed not supplied).

#### AIB activity to fee income

**Trigger:** Irish domestic activity strengthens. **Endpoint:** AIB profit after tax.

Ireland modified domestic demand growth → [fees] AIB net fee and commission income? → [lending] AIB non-property business lending? → AIB total operating income → AIB gross loans to customers → AIB interest income on loans → AIB interest income → AIB net interest income → AIB total operating income → AIB profit before tax → AIB profit after tax  (? marks a step whose size is unknown)

Card spend, payments and lending activity raise fees, and stronger demand lifts business borrowing (balance growth into loan interest). Fees are a small share of income and politically constrained.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [fees] `aib-c-dd-fees` | Card spend, payments, current-account and lending fees rise with domestic activity (AIB customers (households, SMEs)) | fee tariffs unchanged (fees are politically constrained); observable: net fee and commission income, half-yearly | onset same quarter; build none; persists while activity holds; recognized fees each quarter | inferred / inferred / unknown / inferred | fee waivers or caps under public pressure | net fee and commission income | unknown |
| 2 [lending] `aib-c-dd-business` | Stronger domestic demand raises SME and corporate investment and working-capital borrowing (SMEs and corporates) | firms borrow rather than use cash; credit standards unchanged; observable: business loan balances and new lending | onset 2-4 quarters; build several quarters; persists while demand holds; recognized average balances | inferred / inferred / unknown / inferred | cash-rich firms repay; competition from non-bank lenders | non-property business lending | unknown |
| 3 `aib-a-inc-fee-income` | AIB net fee and commission income is one part of AIB total operating income (total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB total operating income | +0.24 sd/sd (accounting) |
| 4 `aib-a-loans-business-loans` | AIB non-property business lending is one part of AIB gross loans to customers (gross loans to customers by portfolio); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB gross loans to customers | +0.39 sd/sd (accounting) |
| 5 `aib-c-loans-income` | A larger average loan book earns more interest at the prevailing yield (AIB (lending)) | bilinear: balance times yield; growth funded from deposits (the loan-to-deposit ratio is low); observable: average gross loans and loan interest income | onset same quarter; build as loans are drawn; persists while held; recognized interest income each quarter | inferred / inferred / inferred / inferred | growth in low-margin lending adds less | interest income on loans | +0.75 sd/sd (identity) |
| 6 `aib-a-ii-loan-interest-income` | AIB interest income on loans is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.64 sd/sd (accounting) |
| 7 `aib-a-nii-interest-income` | AIB interest income is one part of AIB net interest income (net interest income: interest income less interest expense (IFRS)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net interest income | +1.15 sd/sd (accounting) |
| 8 `aib-a-inc-net-interest-income` | AIB net interest income is one part of AIB total operating income (total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB total operating income | +1.00 sd/sd (accounting) |
| 9 `aib-a-pbt-total-operating-income` | AIB total operating income is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +1.25 sd/sd (accounting) |
| 10 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |

Unresolved inputs: fee income by product and its sensitivity to activity and markets (disclosed not supplied).

#### AIB house prices to mortgage impairment and lending

**Trigger:** Irish house prices rise. **Endpoint:** AIB profit after tax.

Ireland residential property price growth → [collateral] AIB mortgage ECL allowance build? → [volume] Ireland mortgage drawdowns? → AIB residential mortgage impairment → AIB net credit impairment charge → AIB profit before tax → AIB new mortgage lending → AIB residential mortgages → AIB gross loans to customers → AIB interest income on loans → AIB interest income → AIB net interest income → AIB total operating income → AIB profit before tax → AIB profit after tax  (? marks a step whose size is unknown)

A shared driver with two parallel responses: collateral values lower loss given default (allowances release), and drawdowns rise (lending grows). A price fall reverses both.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [collateral] `aib-c-hpi-mortallow` | Higher collateral values lower loss given default on mortgages, so IFRS 9 allowances release (a positive change) when house prices rise and build when they fall (AIB credit risk) | house prices in the scenarios; loan-to-value distribution; observable: mortgage allowance and indexed loan-to-value | onset at the next reporting date; build none; persists while prices hold; recognized impairment charge at each reporting date | inferred / inferred / unknown / inferred | overlays; a price fall concentrated in high-LTV vintages | mortgage ECL allowance change | unknown |
| 2 [volume] `aib-c-hpi-drawdowns` | Higher house prices raise the average loan size and, with completions rising, the value of mortgage drawdowns (home buyers) | loan-to-value and loan-to-income limits leave room for larger loans; observable: average mortgage size and drawdowns | onset 1-2 quarters; build several quarters; persists while prices rise; recognized drawdowns as completed | inferred / inferred / unknown / inferred | affordability limits bind; completions fall | Irish mortgage drawdowns | unknown |
| 3 `aib-a-mecl-mortgage-allowance-build` | AIB mortgage ECL allowance build is one part of AIB residential mortgage impairment (mortgage impairment: net write-offs plus allowance change (IFRS 9 roll-forward)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB residential mortgage impairment | +0.80 sd/sd (accounting) |
| 4 `aib-a-ecl-mortgage-ecl` | AIB residential mortgage impairment is one part of AIB net credit impairment charge (net credit impairment charge by portfolio (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net credit impairment charge | +0.42 sd/sd (accounting) |
| 5 `aib-a-pbt-ecl-charge` | AIB net credit impairment charge is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +0.82 sd/sd (accounting) |
| 6 `aib-c-drawdowns-newlending` | The bank writes its market share of the market's drawdowns (AIB (mortgage brands)) | market share as it is; observable: AIB new lending against market drawdowns | onset same quarter; build none; persists while share holds; recognized loan balances as drawn | inferred / inferred / inferred / inferred | share lost to other lenders and non-bank lenders | AIB new mortgage lending | +0.67 sd/sd (identity) |
| 7 `aib-c-newlending-book` | The mortgage book grows by new lending less redemptions and amortisation; when new lending exceeds redemptions the book grows (AIB) | redemptions and switching as they are; observable: gross mortgage balances, half-yearly | onset as drawn; build years (the book turns over slowly); persists the life of the loans; recognized average balances | inferred / inferred / inferred / inferred | redemptions and switching to other lenders; loan sales | residential mortgages | +0.53 sd/sd (stock-flow, accumulates per 365 days) |
| 8 `aib-a-loans-mortgage-book` | AIB residential mortgages is one part of AIB gross loans to customers (gross loans to customers by portfolio); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB gross loans to customers | +0.53 sd/sd (accounting) |
| 9 `aib-c-loans-income` | A larger average loan book earns more interest at the prevailing yield (AIB (lending)) | bilinear: balance times yield; growth funded from deposits (the loan-to-deposit ratio is low); observable: average gross loans and loan interest income | onset same quarter; build as loans are drawn; persists while held; recognized interest income each quarter | inferred / inferred / inferred / inferred | growth in low-margin lending adds less | interest income on loans | +0.75 sd/sd (identity) |
| 10 `aib-a-ii-loan-interest-income` | AIB interest income on loans is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.64 sd/sd (accounting) |
| 11 `aib-a-nii-interest-income` | AIB interest income is one part of AIB net interest income (net interest income: interest income less interest expense (IFRS)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net interest income | +1.15 sd/sd (accounting) |
| 12 `aib-a-inc-net-interest-income` | AIB net interest income is one part of AIB total operating income (total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB total operating income | +1.00 sd/sd (accounting) |
| 13 `aib-a-pbt-total-operating-income` | AIB total operating income is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +1.25 sd/sd (accounting) |
| 14 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |

Unresolved inputs: IFRS 9 scenario weights and the ECL sensitivity to unemployment and house prices (disclosed not supplied); Irish mortgage drawdowns and AIB's market share (disclosed not supplied); mortgage redemptions and switching rates (disclosed not supplied).

#### AIB Irish housing to the mortgage book and NII

**Trigger:** Irish house prices and housing demand rise. **Endpoint:** AIB profit after tax.

Ireland residential property price growth → Ireland mortgage drawdowns? → AIB new mortgage lending → AIB residential mortgages → AIB gross loans to customers → [income] AIB interest income on loans → [capital] AIB risk-weighted assets → AIB interest income → AIB net interest income → AIB total operating income → AIB profit before tax → AIB profit after tax  (? marks a step whose size is unknown)

Rising prices lift the market's drawdowns, the bank writes its share as new lending, the book grows by new lending less redemptions, and loan interest follows the balance at the loan yield; the larger book adds RWA. Most new lending is fixed-rate, so the yield on the growth is set by swap rates at origination.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `aib-c-hpi-drawdowns` | Higher house prices raise the average loan size and, with completions rising, the value of mortgage drawdowns (home buyers) | loan-to-value and loan-to-income limits leave room for larger loans; observable: average mortgage size and drawdowns | onset 1-2 quarters; build several quarters; persists while prices rise; recognized drawdowns as completed | inferred / inferred / unknown / inferred | affordability limits bind; completions fall | Irish mortgage drawdowns | unknown |
| 2 `aib-c-drawdowns-newlending` | The bank writes its market share of the market's drawdowns (AIB (mortgage brands)) | market share as it is; observable: AIB new lending against market drawdowns | onset same quarter; build none; persists while share holds; recognized loan balances as drawn | inferred / inferred / inferred / inferred | share lost to other lenders and non-bank lenders | AIB new mortgage lending | +0.67 sd/sd (identity) |
| 3 `aib-c-newlending-book` | The mortgage book grows by new lending less redemptions and amortisation; when new lending exceeds redemptions the book grows (AIB) | redemptions and switching as they are; observable: gross mortgage balances, half-yearly | onset as drawn; build years (the book turns over slowly); persists the life of the loans; recognized average balances | inferred / inferred / inferred / inferred | redemptions and switching to other lenders; loan sales | residential mortgages | +0.53 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `aib-a-loans-mortgage-book` | AIB residential mortgages is one part of AIB gross loans to customers (gross loans to customers by portfolio); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB gross loans to customers | +0.53 sd/sd (accounting) |
| 5 [income] `aib-c-loans-income` | A larger average loan book earns more interest at the prevailing yield (AIB (lending)) | bilinear: balance times yield; growth funded from deposits (the loan-to-deposit ratio is low); observable: average gross loans and loan interest income | onset same quarter; build as loans are drawn; persists while held; recognized interest income each quarter | inferred / inferred / inferred / inferred | growth in low-margin lending adds less | interest income on loans | +0.75 sd/sd (identity) |
| 6 [capital] `aib-c-loans-rwa` | More loans add risk-weighted assets at their risk weights (mortgages low under internal models, business and property lending high) (AIB (capital management)) | risk weights as they are; mix of growth; observable: RWA, quarterly | onset same quarter; build none; persists while held; recognized RWA at each reporting date | inferred / inferred / inferred / inferred | model changes and regulatory floors (the output floor phases in) | risk-weighted assets | +1.00 sd/sd (identity) |
| 7 `aib-a-ii-loan-interest-income` | AIB interest income on loans is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.64 sd/sd (accounting) |
| 8 `aib-a-nii-interest-income` | AIB interest income is one part of AIB net interest income (net interest income: interest income less interest expense (IFRS)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net interest income | +1.15 sd/sd (accounting) |
| 9 `aib-a-inc-net-interest-income` | AIB net interest income is one part of AIB total operating income (total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB total operating income | +1.00 sd/sd (accounting) |
| 10 `aib-a-pbt-total-operating-income` | AIB total operating income is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +1.25 sd/sd (accounting) |
| 11 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |

Unresolved inputs: Irish mortgage drawdowns and AIB's market share (disclosed not supplied); mortgage redemptions and switching rates (disclosed not supplied); risk weights by portfolio (disclosed not supplied).

#### AIB ECB deposit rate to net interest income

**Trigger:** the ECB raises or cuts the deposit rate. **Endpoint:** AIB profit after tax.

ECB deposit rate → [short_rate] AIB euro short rate earned and paid? → [loans] AIB loan yield? → [beta] AIB cost of interest-bearing deposits? → [migration] AIB current accounts? → [wholesale] AIB interest expense on debt securities in issue? → [credit] AIB property and construction impairment? → AIB interest income on central bank placements → AIB structural hedge net spread → AIB net interest on the structural hedge → AIB interest income on loans → AIB interest expense on customer deposits → AIB interest-bearing deposits? → AIB interest expense on customer deposits → AIB structural hedge notional? → AIB net interest on the structural hedge → AIB interest income → AIB interest income → AIB interest income → AIB interest expense → AIB interest expense → AIB net interest income → AIB net interest income → AIB net credit impairment charge → AIB profit before tax → AIB total operating income → AIB profit before tax → AIB profit after tax  (? marks a step whose size is unknown)

Parallel responses of one rate move: central bank cash and floating loans reprice at once, deposit costs follow by the beta with a lag, balances migrate out of current accounts (shrinking the hedgeable base), the structural hedge's floating leg offsets part of the move, swapped debt reprices, and property and variable-rate borrowers feel the cost (the credit counter-path). s32 is the reduced form on NII and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [short_rate] `aib-c-ecb-shortrate` | The deposit facility rate is what the bank's central bank placements earn and, through €STR and Euribor fixings, what the structural hedge pays on its floating leg; it moves with the ECB on the effective date (ECB (deposit facility); money markets) | no reserve tiering; €STR and Euribor track the deposit rate; observable: the deposit facility rate and €STR fixings | onset same day; build none; persists while the rate holds; recognized interest each period | public_not_supplied / inferred / unknown / inferred | a tiering or remuneration change by the ECB; a Euribor basis to the deposit rate | the euro short rate the bank earns and pays | unknown |
| 2 [loans] `aib-c-ecb-loanyield` | Tracker mortgages reset with the ECB rate at once, floating-rate business and corporate loans with Euribor at their next fixing, and standard variable rates at the bank's discretion; fixed-rate mortgages (most new Irish lending) reprice only at the end of their fixed period, so the yield moves by the floating share of the book first and the rest over years (AIB (lending pricing); borrowers on trackers and floating loans) | the tracker and floating share of the book; Euribor following the deposit rate (the deposit rate stands in for Euribor here); observable: loan yield against the ECB rate and 3M Euribor, half-yearly | onset within the month for trackers and floating loans; build fixed-rate expiries over 1-5 years; persists while the rate holds; recognized interest income each quarter | public_not_supplied / inferred / unknown / inferred | competition on mortgage pricing (variable rates need not follow); a shift of new lending to fixed rates lowers the floating share; receive-fixed swaps on loans | loan yield | unknown |
| 3 [beta] `aib-c-ecb-depcost` | The bank reprices interest-bearing savings, notice and term deposits by a fraction of an ECB move (the deposit beta); current accounts pay close to nothing, and in a concentrated deposit market with few competitors the fraction is low and slow, which is why the bank's NII responds strongly to the ECB (AIB (deposit pricing); competitors, State savings products and money funds) | a concentrated deposit market and excess liquidity keep pass-through low; corporate and treasury deposits reprice closer to the market; observable: rate paid on interest-bearing deposits against the ECB deposit rate, half-yearly | onset within the quarter for corporate deposits; build 2-4 quarters for retail term rates; persists while the rate holds; recognized interest expense each quarter | public_not_supplied / inferred / unknown / inferred | a deposit-price contest (a new entrant, State savings rates) raises the beta; caps at the policy rate; on the way down, rates near zero floor the fall | cost of interest-bearing deposits | unknown |
| 4 [migration] `aib-c-ecb-migration` | Higher rates make idle balances costly, so customers move money from current accounts into savings and term deposits or out to State savings and funds; lower rates slow or reverse the migration (depositors (households, SMEs, corporates)) | rates high enough for the opportunity cost to be noticed; transaction balances are sticky; observable: current accounts as a share of customer accounts, half-yearly | onset 1-2 quarters; build several quarters; persists while the gap lasts; recognized average balances and interest each quarter | inferred / inferred / unknown / inferred | operating balances customers cannot move; deposit inflows from a growing economy | current accounts | unknown |
| 5 [wholesale] `aib-c-ecb-debtcost` | Senior MREL and covered bonds are mostly swapped to floating, so their cost moves with money-market rates (expense more negative when rates rise) (AIB Treasury (funding)) | the swapped share of debt; issuance volume set by the MREL requirement; observable: interest expense on debt securities in issue | onset at the next fixing; build as debt rolls; persists while the rate holds; recognized interest expense each quarter | inferred / inferred / unknown / inferred | unswapped fixed coupons; new issuance at wider or tighter spreads | interest expense on debt securities | unknown |
| 6 [credit] `aib-c-ecb-property` | Counter-path to the NII gain: higher rates raise property borrowers' debt service and cut property values, which raises stage migration and impairment on property and construction lending (a larger, negative charge); lower rates ease it (property borrowers; AIB credit risk) | floating-rate or refinancing property borrowers; valuations sensitive to yields; observable: property and construction loans in stage 2 and 3; impairment charge | onset 2-4 quarters; build over the refinancing cycle; persists while rates stay high; recognized impairment charge at each reporting date | inferred / inferred / unknown / inferred | interest-rate hedges held by borrowers; low leverage after the post-2010 deleveraging | property and construction impairment | unknown |
| 7 `aib-c-shortrate-cashincome` | Cash placed at the deposit facility earns the short rate: interest income on central bank placements is the balance times the rate; a deposit-rich, loan-light balance sheet holds a large share of its assets there, so this is the most direct channel from the ECB to NII (AIB Treasury) | liquidity held at the central bank rather than lent or invested; observable: cash and balances at central banks and their yield, half-yearly | onset same day; build none; persists while the rate holds; recognized interest income each quarter | public_not_supplied / inferred / inferred / inferred | the bank moves liquidity into securities or the hedge | interest income on central bank placements | +0.74 sd/sd (identity) |
| 8 `aib-c-shortrate-spread` | Counter-path: the structural hedge receives fixed and pays floating, so a lower short rate widens the hedge's net spread and raises its net interest, offsetting part of the fall in cash and floating-loan income; a higher rate does the opposite (AIB Treasury (asset and liability management)) | a receive-fixed hedge in place against stable deposits and equity; observable: net hedge interest | onset at the next floating fixing; build none; persists while the rate holds; recognized interest income each quarter | public_not_supplied / inferred / inferred / inferred | the bank changes the hedge notional or tenor; hedge accounting puts the swaps' mark in OCI, not income | structural hedge net spread | -0.83 sd/sd (identity) |
| 9 `aib.id.hedge_income:aib_group.hedge_spread` | AIB net interest on the structural hedge = 0.01 x AIB structural hedge notional x AIB structural hedge net spread: AIB structural hedge net spread is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +1.00 sd/sd (identity) |
| 10 `aib-c-loanyield-income` | Interest income on loans is the average loan balance times the loan yield (AIB (lending)) | bilinear: balance times yield; observable: loan yield and loan interest income | onset same quarter; build none; persists while the state holds; recognized interest income and expense each quarter | inferred / inferred / inferred / inferred | loan balances shrink | interest income on loans | +0.79 sd/sd (identity) |
| 11 `aib-c-depcost-expense` | Interest expense on deposits is the interest-bearing balance times the deposit cost; a higher cost makes the (negative) expense larger (AIB (deposit pricing)) | bilinear: balance times rate; observable: interest expense on customer accounts | onset same quarter; build none; persists while the state holds; recognized interest income and expense each quarter | inferred / inferred / inferred / inferred | a falling interest-bearing balance | interest expense on customer deposits | -0.84 sd/sd (identity) |
| 12 `aib-c-ca-ibdep` | Money that migrates out of current accounts mostly stays with the bank in savings and term deposits, so the rate-paying balance rises as current accounts fall (depositors) | the migration stays inside the bank rather than leaving for State savings or funds; observable: current accounts and interest-bearing deposits, half-yearly | onset 1-2 quarters; build several quarters; persists while the gap lasts; recognized average balances and interest each quarter | inferred / inferred / unknown / inferred | outflows to State savings, funds or other banks | interest-bearing deposits | unknown |
| 13 `aib-c-ibdep-expense` | More of the deposit base in rate-paying accounts means more interest paid at a given deposit rate (the expense is more negative) (depositors) | bilinear: balance times rate; observable: interest-bearing deposits and interest expense on customer accounts | onset same quarter; build none; persists while the state holds; recognized interest income and expense each quarter | inferred / inferred / inferred / inferred | a lower deposit rate | interest expense on customer deposits | -0.56 sd/sd (identity) |
| 14 `aib-c-ca-hedgenotional` | Treasury hedges the stable, rate-insensitive part of current accounts (and equity) with receive-fixed swaps; when that base shrinks the hedge is resized down as tranches mature, when it grows more is hedged (AIB Treasury (asset and liability management)) | the behavioural model of stable balances; the board's hedge policy; observable: structural hedge notional against current accounts | onset at the next hedge decision; build tranches over years; persists while balances hold; recognized net hedge interest as swaps are added | public_not_supplied / inferred / unknown / inferred | a policy decision to change the hedged share or tenor | structural hedge notional | unknown |
| 15 `aib-c-hedgenotional-income` | Net hedge interest is the notional times the fixed rate received less the floating rate paid; a larger notional adds income while the fixed rate is above the floating rate (AIB Treasury) | the hedge yield above the floating rate (the sign flips when the floating rate is above it); observable: hedge notional and net hedge interest | onset same quarter; build none; persists while the state holds; recognized interest income and expense each quarter | public_not_supplied / inferred / inferred / inferred | the floating rate rising above the hedge yield | net interest on the structural hedge | +0.13 sd/sd (identity) |
| 16 `aib-a-ii-cash-interest-income` | AIB interest income on central bank placements is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.53 sd/sd (accounting) |
| 17 `aib-a-ii-loan-interest-income` | AIB interest income on loans is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.64 sd/sd (accounting) |
| 18 `aib-a-ii-structural-hedge-income` | AIB net interest on the structural hedge is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.57 sd/sd (accounting) |
| 19 `aib-a-ie-deposit-interest-expense` | AIB interest expense on customer deposits is one part of AIB interest expense (interest expense by funding source (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest expense | +0.80 sd/sd (accounting) |
| 20 `aib-a-ie-debt-interest-expense` | AIB interest expense on debt securities in issue is one part of AIB interest expense (interest expense by funding source (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest expense | +0.50 sd/sd (accounting) |
| 21 `aib-a-nii-interest-income` | AIB interest income is one part of AIB net interest income (net interest income: interest income less interest expense (IFRS)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net interest income | +1.15 sd/sd (accounting) |
| 22 `aib-a-nii-interest-expense` | AIB interest expense is one part of AIB net interest income (net interest income: interest income less interest expense (IFRS)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net interest income | +0.54 sd/sd (accounting) |
| 23 `aib-a-ecl-property-ecl` | AIB property and construction impairment is one part of AIB net credit impairment charge (net credit impairment charge by portfolio (negative values)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net credit impairment charge | +0.42 sd/sd (accounting) |
| 24 `aib-a-pbt-ecl-charge` | AIB net credit impairment charge is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +0.82 sd/sd (accounting) |
| 25 `aib-a-inc-net-interest-income` | AIB net interest income is one part of AIB total operating income (total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB total operating income | +1.00 sd/sd (accounting) |
| 26 `aib-a-pbt-total-operating-income` | AIB total operating income is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +1.25 sd/sd (accounting) |
| 27 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |

Unresolved inputs: IFRS 9 scenario weights and the ECL sensitivity to unemployment and house prices (disclosed not supplied); average cash at central banks and the share held at the Central Bank of Ireland (disclosed not supplied); current-account share of deposits and its migration elasticity (disclosed not supplied); deposit beta (pass-through of ECB moves to AIB deposit rates), by product (found proxy); share of wholesale debt swapped to floating (disclosed not supplied); structural hedge notional, average fixed yield and average life (found proxy); tracker, variable and fixed shares of the mortgage book and the fixed-rate maturity profile (disclosed not supplied).

#### AIB State sell-down to distributions and the share price

**Trigger:** the Minister for Finance sells AIB shares. **Endpoint:** AIB CET1 ratio.

Irish State sales of AIB shares → [stake] Irish State shareholding in AIB? → [directed_buyback] AIB share buybacks? → [placing] AIB share price? → AIB share price? → AIB CET1 capital → AIB CET1 ratio  (? marks a step whose size is unknown)

One sale, three parallel responses: the State's stake falls, a directed buyback (if used) consumes the bank's excess capital, and a placing weighs on the price briefly; a smaller stake removes the overhang. Once the stake is zero the path is dormant.

**Dormant unless:** while the State holds AIB shares (aib_group.state_shareholding above zero); dormant once the sell-down is complete.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [stake] `aib-c-statesales-stake` | Each placing, trading-plan sale or directed buyback lowers the Minister for Finance's percentage holding (Minister for Finance (via the State's investment manager)) | the State chooses to sell (price and market conditions); observable: the State's holding in each disclosure | onset on settlement; build per transaction; persists permanent; recognized shareholder register | public_not_supplied / inferred / unknown / inferred | the stake reaches zero (then the path is dormant) | Irish State shareholding | unknown |
| 2 [directed_buyback] `aib-c-statesales-buyback` | Part of the State's sales can be a directed buyback, approved by shareholders, in which the bank buys shares from the State with its excess capital; it counts in the bank's buybacks and consumes CET1 (AIB board; Minister for Finance; shareholders (AGM authority)) | excess capital and shareholder authority for a directed buyback; observable: announced directed buybacks | onset on announcement; build per transaction; persists permanent; recognized equity reduced as bought | public_not_supplied / inferred / unknown / inferred | the State sells in the market instead; capital needed elsewhere | share buybacks | unknown |
| 3 [placing] `aib-c-statesales-price` | A placing is priced at a discount and adds supply, which weighs on the share price around the sale; the effect fades as the stock is absorbed (Minister for Finance; investors) | a placing or trading-plan sale rather than a directed buyback; observable: price around placings | onset on announcement; build days; persists short-lived; recognized share price | inferred / inferred / unknown / inferred | strong demand (index inclusion, higher free float) absorbs the supply | AIB share price | unknown |
| 4 `aib-c-stake-price` | A remaining State stake is an overhang (more sales to come) and limits free float and index weight; as it falls, the overhang lifts (investors) | investors expect further sales; observable: free float and index weights | onset as the stake falls; build months; persists permanent once the stake is gone; recognized share price | public_not_supplied / inferred / unknown / inferred | the sell-down already complete | AIB share price | unknown |
| 5 `aib-c-buyback-cet1` | Shares bought back reduce CET1 capital by the amount spent (deducted when approved) (AIB board) | approved programme; observable: CET1 roll-forward | onset at approval (deducted); build none; persists permanent; recognized CET1 at each reporting date | inferred / inferred / inferred / inferred | none | CET1 capital | -0.75 sd/sd (stock-flow, accumulates per 365 days) |
| 6 `aib-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (AIB) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized Pillar 3 and results | inferred / inferred / inferred / inferred | RWA growth | CET1 ratio | +1.39 sd/sd (identity) |

Unresolved inputs: the State's remaining shareholding and the sell-down method (placing, trading plan, directed buyback) (disclosed not supplied).

#### AIB euro long end to the structural hedge, securities and capital

**Trigger:** medium- and long-term euro rates rise (a steeper curve). **Endpoint:** AIB CET1 ratio.

Bund 10Y yield → [hedge_roll] AIB structural hedge fixed yield → [securities] AIB investment securities yield? → [marks] AIB FVOCI reserve? → [mortgage_pricing] AIB new mortgage lending? → AIB structural hedge net spread → AIB net interest on the structural hedge → AIB interest income on investment securities → AIB residential mortgages → AIB interest income → AIB interest income → AIB gross loans to customers → AIB interest income on loans → AIB interest income → AIB net interest income → AIB total operating income → AIB profit before tax → AIB profit after tax → AIB CET1 capital? → AIB CET1 capital → AIB CET1 ratio  (? marks a step whose size is unknown)

One move, four parallel responses: maturing hedge tranches roll at the higher swap rate (slowly, over the hedge's life), maturing securities reinvest higher, FVOCI bonds mark down into CET1, and dearer fixed mortgages slow new lending. The hedge is what makes a bank with a large current-account base less sensitive to the ECB and more to the medium-term curve.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [hedge_roll] `aib-c-bund-hedgeyield` | Each year a slice of the hedge (about one over its average life) matures and is replaced at the prevailing medium-term swap rate; higher long-end rates lift the average fixed yield slowly, lower ones drag it down slowly (AIB Treasury) | the hedge rolls rather than shrinks; medium-term swap rates follow the Bund (the Bund 10Y stands in for the 5-7 year swap rate here); observable: average hedge yield against the swap rate | onset at each tranche's maturity; build over the hedge's average life (years); persists years; recognized net hedge interest each quarter | public_not_supplied / peer / peer / peer | a decision to shorten or stop rolling; a gap between swap rates and Bunds | structural hedge fixed yield | +0.20 sd/sd |
| 2 [securities] `aib-c-bund-secyield` | Maturing securities are reinvested at current yields, so the book yield moves toward market yields at the rate the portfolio turns over (AIB Treasury (liquid asset portfolio)) | maturities reinvested in like assets; the liquidity buffer requirement holds the portfolio size; observable: securities book yield against the Bund 10Y | onset as securities mature; build over the portfolio's life; persists years; recognized interest income each quarter | inferred / inferred / unknown / inferred | cash kept at the central bank instead (the ECB rate is then the reinvestment rate) | investment securities yield | unknown |
| 3 [marks] `aib-c-bund-fvoci` | Higher yields lower the fair value of fixed-rate securities held at FVOCI; the loss goes to OCI and, under the EU rules, into CET1 (the swaps' cash-flow hedge reserve is filtered out of CET1, so the hedge's mark does not reach capital) (AIB Treasury) | fixed-rate FVOCI holdings not swapped to floating; observable: FVOCI reserve, half-yearly | onset same day; build none; persists pulls to par as bonds mature; recognized OCI at each reporting date | inferred / inferred / unknown / inferred | asset swaps on the bonds; amortised-cost classification (no mark) | FVOCI reserve | unknown |
| 4 [mortgage_pricing] `aib-c-bund-newlending` | Fixed mortgage rates are priced off medium-term swap rates; higher long-end rates raise them and slow new mortgage lending (AIB (mortgage pricing); home buyers) | fixed-rate products dominate new lending; observable: new mortgage lending and fixed-rate pricing | onset 1-2 quarters; build several quarters; persists while rates hold; recognized drawdowns as completed | inferred / inferred / unknown / inferred | competitors hold prices; supply-constrained housing | AIB new mortgage lending | unknown |
| 5 `aib-c-hedgeyield-spread` | The hedge's net spread is the fixed yield received less the floating rate paid (AIB Treasury) | the hedge in place; observable: hedge yield and net hedge interest | onset same quarter; build none; persists while the state holds; recognized interest income and expense each quarter | inferred / inferred / inferred / inferred | a smaller notional | structural hedge net spread | +0.50 sd/sd (identity) |
| 6 `aib.id.hedge_income:aib_group.hedge_spread` | AIB net interest on the structural hedge = 0.01 x AIB structural hedge notional x AIB structural hedge net spread: AIB structural hedge net spread is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +1.00 sd/sd (identity) |
| 7 `aib-c-secyield-income` | Interest income on securities is the average portfolio times the book yield (AIB Treasury) | bilinear: balance times yield; observable: securities yield and income | onset same quarter; build none; persists while the state holds; recognized interest income and expense each quarter | inferred / inferred / inferred / inferred | a smaller portfolio | interest income on investment securities | +0.77 sd/sd (identity) |
| 8 `aib-c-newlending-book` | The mortgage book grows by new lending less redemptions and amortisation; when new lending exceeds redemptions the book grows (AIB) | redemptions and switching as they are; observable: gross mortgage balances, half-yearly | onset as drawn; build years (the book turns over slowly); persists the life of the loans; recognized average balances | inferred / inferred / inferred / inferred | redemptions and switching to other lenders; loan sales | residential mortgages | +0.53 sd/sd (stock-flow, accumulates per 365 days) |
| 9 `aib-a-ii-structural-hedge-income` | AIB net interest on the structural hedge is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.57 sd/sd (accounting) |
| 10 `aib-a-ii-securities-interest-income` | AIB interest income on investment securities is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.18 sd/sd (accounting) |
| 11 `aib-a-loans-mortgage-book` | AIB residential mortgages is one part of AIB gross loans to customers (gross loans to customers by portfolio); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB gross loans to customers | +0.53 sd/sd (accounting) |
| 12 `aib-c-loans-income` | A larger average loan book earns more interest at the prevailing yield (AIB (lending)) | bilinear: balance times yield; growth funded from deposits (the loan-to-deposit ratio is low); observable: average gross loans and loan interest income | onset same quarter; build as loans are drawn; persists while held; recognized interest income each quarter | inferred / inferred / inferred / inferred | growth in low-margin lending adds less | interest income on loans | +0.75 sd/sd (identity) |
| 13 `aib-a-ii-loan-interest-income` | AIB interest income on loans is one part of AIB interest income (interest income by earning asset, incl. net interest on the structural hedge); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB interest income | +0.64 sd/sd (accounting) |
| 14 `aib-a-nii-interest-income` | AIB interest income is one part of AIB net interest income (net interest income: interest income less interest expense (IFRS)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB net interest income | +1.15 sd/sd (accounting) |
| 15 `aib-a-inc-net-interest-income` | AIB net interest income is one part of AIB total operating income (total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB total operating income | +1.00 sd/sd (accounting) |
| 16 `aib-a-pbt-total-operating-income` | AIB total operating income is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +1.25 sd/sd (accounting) |
| 17 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |
| 18 `aib-c-fvoci-cet1` | FVOCI gains and losses are part of CET1 under the EU rules (the cash-flow hedge reserve is filtered out) (AIB (capital management)) | no transitional filter on FVOCI; observable: FVOCI reserve and CET1 | onset same reporting date; build none; persists pulls to par; recognized CET1 at each reporting date | inferred / inferred / unknown / inferred | small FVOCI book | CET1 capital | unknown |
| 19 `aib-c-pat-cet1` | Profit after tax adds to CET1 capital, less the foreseeable dividend and AT1 coupons deducted as accrued (AIB (capital management)) | profit recognized by the regulator; deferred tax on losses is deducted from CET1 as it is used, so recognized profit adds close to one for one; observable: CET1 capital roll-forward, quarterly | onset each quarter; build none; persists accumulates; recognized CET1 at each reporting date | inferred / inferred / inferred / inferred | foreseeable distributions deducted at once | CET1 capital | +0.32 sd/sd (stock-flow, accumulates per 365 days) |
| 20 `aib-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (AIB) | RWA unchanged; observable: CET1 ratio, quarterly | onset same reporting date; build none; persists identity; recognized Pillar 3 and results | inferred / inferred / inferred / inferred | RWA growth | CET1 ratio | +1.39 sd/sd (identity) |

Unresolved inputs: FVOCI holdings, their duration and the swapped share (disclosed not supplied); Irish mortgage drawdowns and AIB's market share (disclosed not supplied); medium-term euro swap rates (found proxy); mortgage redemptions and switching rates (disclosed not supplied); securities maturity ladder and reinvestment yields (disclosed not supplied); structural hedge notional, average fixed yield and average life (found proxy).

#### AIB Bank Rate to AIB UK

**Trigger:** the Bank of England raises Bank Rate. **Endpoint:** AIB profit after tax.

Bank of England Bank Rate → AIB UK operating income? → AIB total operating income? → AIB profit before tax → AIB profit after tax  (? marks a step whose size is unknown)

AIB UK's deposit-funded book widens its margin when Bank Rate rises; the segment's income is translated from sterling. This is the only driver of the segment view, and it is uncalibrated, so it never adds to the line view's NII change.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `aib-c-boe-ukincome` | AIB UK is funded by business and Northern Ireland retail deposits; a higher Bank Rate widens its deposit margin and reprices its floating business loans, raising segment income in sterling (translated at EUR/GBP) (Bank of England; AIB UK) | deposit-funded, asset-sensitive UK book; EUR/GBP as it is; observable: AIB UK net interest income in GBP | onset within the quarter; build 2-4 quarters as deposit rates follow; persists while the rate holds; recognized segment income each half-year | public_not_supplied / inferred / unknown / inferred | UK deposit competition; a weaker sterling lowers the euro value | AIB UK operating income | unknown |
| 2 `aib-a-seg-aib-uk-income` | AIB UK operating income is one part of AIB total operating income (total operating income by reporting segment (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / unknown / inferred | unknown | AIB total operating income | unknown (accounting) |
| 3 `aib-a-pbt-total-operating-income` | AIB total operating income is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +1.25 sd/sd (accounting) |
| 4 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |

Unresolved inputs: AIB UK NII sensitivity to Bank Rate and the EUR/GBP translation (disclosed not supplied); segment income and profit before tax (Retail Banking, Capital Markets, AIB UK, Group) and the current segment set (disclosed not supplied).

#### AIB equity markets to wealth fees

**Trigger:** European equity markets rise. **Endpoint:** AIB profit after tax.

Europe equity index (Euro Stoxx 50) → AIB net fee and commission income? → AIB total operating income → AIB profit before tax → AIB profit after tax  (? marks a step whose size is unknown)

Wealth, broking and asset-management fees follow asset values.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `aib-c-equity-fees` | Wealth, broking and asset-management fees are charged on asset values and activity, so higher equity markets raise them (wealth and broking clients) | fees on assets under management and transactions; observable: wealth fees and assets under management | onset same quarter; build none; persists while markets hold; recognized fees each quarter | inferred / inferred / unknown / inferred | outflows; fee compression | net fee and commission income | unknown |
| 2 `aib-a-inc-fee-income` | AIB net fee and commission income is one part of AIB total operating income (total operating income by line: net interest income, net fees and commissions, other income (IFRS, EUR)); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB total operating income | +0.24 sd/sd (accounting) |
| 3 `aib-a-pbt-total-operating-income` | AIB total operating income is one part of AIB profit before tax (profit before tax: total operating income less operating expenses less net credit impairment, plus exceptional and other items); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit before tax | +1.25 sd/sd (accounting) |
| 4 `aib-a-pat-profit-before-tax` | AIB profit before tax is one part of AIB profit after tax (profit after tax: profit before tax less income tax); weight is its scale over the total's | IFRS, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized half-yearly results | inferred / inferred / inferred / inferred | unknown | AIB profit after tax | +1.17 sd/sd (accounting) |

Unresolved inputs: fee income by product and its sensitivity to activity and markets (disclosed not supplied).
