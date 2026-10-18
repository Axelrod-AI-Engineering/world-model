# Citigroup: business construction

<!-- toc -->
**Contents**

- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Identities](#identities)
  - [Stocks and flows](#stocks-and-flows)
  - [Matrix `cit.mx.revenue`: cit.comp.revenue_by_segment x cit.comp.revenue_by_type (the rows drive the total; cit.comp.revenue_by_type reconciles)](#matrix-citmxrevenue-citcomprevenuebysegment-x-citcomprevenuebytype-the-rows-drive-the-total-citcomprevenuebytype-reconciles)
  - [Operating and financial paths](#operating-and-financial-paths)
- [Validation](#validation)
- [Completion report](#completion-report)
  - [Gaps](#gaps)
  - [What was built](#what-was-built)
  - [Reconciliation](#reconciliation)
  - [Inputs by status](#inputs-by-status)
  - [Calculation coverage](#calculation-coverage)
  - [What a downstream agent can now trace or calculate, and what remains unsupported](#what-a-downstream-agent-can-now-trace-or-calculate-and-what-remains-unsupported)
- [Conversion (Oct 18): one driving view per total, identities, a stock-flow, states](#conversion-oct-18-one-driving-view-per-total-identities-a-stock-flow-states)
- [What the method could not express for Citi](#what-the-method-could-not-express-for-citi)
<!-- /toc -->

The fourth build of the method and the second bank, after [JPMorgan](jpmorgan.md). It reuses JPMorgan's bank structure
(the P&L bridge, credit as charge-offs plus reserve build, capital as a stock fed by flows, reduced forms kept apart from
their paths) but follows Citi's own reporting: five businesses (Services, Markets, Banking, Wealth, U.S. Consumer Cards)
plus All Other (Legacy Franchises, of which Banamex, and Corporate/Other), each with its net interest income and
non-interest revenue; a firm NII whose rate sensitivity is mostly outside the dollar; a large international footprint
translated into dollars; a card book whose losses and partner payments move together; a multi-year transformation and
expense program; and capital, buybacks and the Banamex exit. The construction lives in
`data/worlds/sally_demo/construction/citigroup.yaml` plus light edits to the `citigroup` block of entities.yaml
(features on three values) and to m26, s16 and s19 in interactions.yaml (transitions; sizes kept). This page is
structure only: object ids, bases, categories, tests. The client-derived side (workbook cells, broker passages, guidance,
dated baselines) stays local under `data/sally_data/construction/citigroup/`.

Source ids used in transitions (each resolves locally in `sources.json` to a file, and in `citations.json` to the cell
or the page and line with the passage): `cit.v1` the client's macro-transmission company model (segment history on the
recast basis to 3Q26, guidance, broker consensus, transmission map; its own assumptions are not used as evidence);
`cit.wb` sell-side company model workbook (history to Q2-2026 and the analyst's forecast); `cit.co` company statements
as recorded in `cit.v1` and relayed by the brokers (the call, supplement and 10-Q were not read directly); `cit.r1`–`cit.r6`
broker notes (a management-meeting note, two company previews, bank cheat sheets with the rate-sensitivity and capital
tables, two sector previews with deposit, loan and sensitivity tables); `cit.x1`, `cit.x2` expert calls on treasury
services and on cards (no names recorded; `cit.x3`, on credit bureaus, was read and not used); `cit.peer` a peer
dashboard (searched, not used); `cit.pub` public business and accounting knowledge (CECL, AOCI in CET1 for the largest
banks, FX translation, private-label partner economics).

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack (036, state 432). Citi was not one of the reviewer's worked companies, so the export side is "not represented in
the inspected export" throughout. Categories: **MC** missing construction, **CAL** missing calibration, **MAP**
incorrect mapping, **EXP** export omission, **RET** retrieval omission. Outcomes are in the
[completion report](#completion-report).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | No business composition: the pack jumps from the Fed to NII, from GDP to Services revenue, from volatility to Markets revenue | Internal: three values (`citigroup.net_interest_income`, `citigroup.services_revenue`, `citigroup.markets_revenue`), links m26, s16, s19, s25, s26 and the NII kind default to the share price; no compositions. Export: the same broad relations | The reporting-segment tree of net revenue to its businesses and their NII and non-interest revenue (`cit.comp.revenue_by_segment` and one view per segment), the P&L bridge (`cit.comp.pretax`, `cit.comp.net_income`), expense and credit views | Segment tables (supplement as transcribed in the client model; vendor workbook) | Any group revenue or earnings conclusion | `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links`, `test_priors_reconcile_within_half_a_percent` | MC |
| G02 | Undefined bases: NII (firm, incl. Markets NII, versus the guided NII ex-Markets), Services revenue (TTS plus Securities Services), Markets revenue (incl. Markets NII) | Internal: values without features. Export: metrics named by id suffix | `features.view/basis/metric` on the three values and every new one; an NII ex-Markets view of firm NII | Supplement definitions | Reading the NII guide against firm NII; adding Markets revenue to NII | `test_values_name_their_basis`, `test_nii_ex_markets_is_its_own_view_of_firm_nii` | MAP |
| G03 | Segment perimeter out of date: the 2026 recast moved Retail Banking from U.S. Personal Banking into Wealth and left U.S. Consumer Cards (USCC) as the consumer segment | Internal: no segment values. Export: none | Segments on the recast basis; USPB named only as a former perimeter (alias and basis text); history restated | Recast segment history (found in the client model and vendor workbook) | Any USPB-based number or comparison | `test_segments_follow_the_recast_perimeter` | MAP |
| G04 | m26 (Fed → firm NII, calibrated) says a higher US rate widens margins; the company says its USD NII is roughly neutral within twelve months and its sensitivity is mostly non-USD | Internal: calibrated, no transition. Export: one relation | Keep id and size (Sally's expected paths); add a transition naming it a reduced form, magnitude "assumption", with the company statement as breaker; build the USD branches that net out | USD-only NII sensitivity (the 10-Q currency split) | Size and sign of any Fed-driven NII change | `test_reduced_forms_are_never_steps_of_their_structural_paths`, `test_existing_records_keep_their_sizes_and_are_scoped` | MAP / CAL |
| G05 | No non-USD rate exposure: Services deposits in many currencies earn local short rates; no Citi link from the ECB, BoJ or PBoC | Internal: none | A Citi non-USD rate state fed by the three policy rates, `cit.path.non_usd_rates` into TTS and Securities Services NII; a calibrated reduced form on firm NII from the disclosed parallel-rate sensitivity | Disclosed all-currency sensitivity and its currency split | Whether a global hiking cycle helps Citi more than a Fed hike | `test_non_usd_rates_reach_services_nii_and_the_reduced_form_is_calibrated_from_the_disclosure` | MC / CAL |
| G06 | USD rate paths absent: deposit cost and its lag, floating loans, card APRs, Treasury cash, Markets NII funding with its offset | Internal: m26 only | `cit.path.usd_rates`: parallel branches of one Fed move into the segment cells, with the Markets NII offset as a counter-path | Deposit beta, floating share (found: broker), card APR repricing | "Rates up is good for Citi" | `test_usd_rate_branches_are_parallel_and_include_the_offsets` | MC |
| G07 | Securities reinvestment and AOCI: maturities → reinvestment → book yield → Treasury revenue; AFS marks to AOCI and CET1 | Internal: none | `cit.path.securities_reinvestment`, `cit.path.long_end` | Maturity ladder, AFS duration, AOCI sensitivity | Long-end moves on earnings versus capital | `test_marks_reach_capital_not_income` | MC |
| G08 | Services fees on cross-border flows; s19 (US GDP → Services revenue) unscoped | Internal: s19 only | Cross-border volume and Services deposits as operating states; `cit.path.cross_border`; s19 scoped as the reduced form | Fee elasticity to trade volumes | Services growth | `test_required_paths_exist` | MC / MAP |
| G09 | Markets products and volatility; s16 unscoped | Internal: s16 only | `cit.comp.markets`, `cit.comp.fixed_income`; `cit.path.markets` with incentive-pay and RWA counter-paths; s16 scoped | Revenue sensitivity to volatility | "Volatility is good for Citi" | `test_required_paths_exist` | MC / CAL |
| G10 | Banking: IB fees on deal activity; Corporate Lending and its CDS loan hedges, which gain when spreads widen while provisions rise | Internal: none | `cit.comp.banking`; `cit.path.deals_banking`, `cit.path.wholesale_credit` (hedge gains as a counter-path to provisions) | Hedge notional and sensitivity | Credit-spread shocks on Banking | `test_loan_hedges_offset_wholesale_provisions` | MC |
| G11 | Wealth and Securities Services fees on market levels (client assets, assets under custody) | Internal: none; equity index values exist | `cit.path.market_levels_fees` | Market-linked share of fee bases | Equity-market moves on fees | `test_required_paths_exist` | MC |
| G12 | USCC: NII on card balances, interchange net of rewards and partner payments (a contra-revenue), partner loss-sharing in private label | Internal: none | `cit.comp.uscc`, `cit.comp.uscc_nir`; `cit.path.card_spend`, `cit.path.card_growth` | Rewards rate, partner-payment terms | Card growth as pure upside | `test_card_fees_are_net_of_rewards_and_partner_payments` | MC |
| G13 | Card credit cycle: CECL reserve now, losses after delinquencies; general-purpose versus private-label loss rates; underwriting response | Internal: none | `cit.comp.uscc_provision`, `cit.path.card_credit` (two clocks; partner payments and underwriting as counter-paths) | Unemployment-to-loss sensitivity, roll rates | Any recession conclusion | `test_two_credit_clocks` | MC / CAL |
| G14 | International footprint and FX translation: no regions view, no non-USD revenue, no Mexican peso | Internal: none; no USD/MXN value in the world | `cit.comp.revenue_by_region`, a translation FX basket, `usd_mxn.rate`; `cit.path.fx_translation`, `cit.path.mexico` (revenue, expense natural hedge, CTA in AOCI, RWA) | Currency mix of revenue (not disclosed since 2022), peso revenue share | Dollar moves on revenue and capital | `test_translation_hits_revenue_expenses_and_capital` | MC |
| G15 | Transformation and expense program: transformation spend, stranded costs, the investment program and its productivity payback; efficiency ratio | Internal: none | `cit.comp.expense`; `cit.path.transformation`, `cit.path.investment_program`; efficiency ratio as a ratio state | Program sizes (found: guidance relayed by brokers) | Operating leverage, the efficiency guide | `test_expense_program_has_a_payback_counter_path` | MC |
| G16 | Capital and payout: CET1 capital, RWA, a rising requirement, management target, buybacks, dividends, disallowed-DTA utilization | Internal: none | Capital values; non-additive `cit.comp.capital_sources_uses`; `cit.path.capital_payout`, `cit.path.capital_requirement` | Requirement path and target (found), AOCI sensitivity | Buyback capacity | `test_capital_is_a_stock_with_flows_not_an_additive_view` | MC |
| G17 | Banamex separation: deconsolidation, CTA recycled through earnings (capital-neutral), RWA released, stranded costs | Internal: none | `cit.path.legacy_exits` | Separation timing, CTA size (found: guidance) | Earnings and capital in the exit year | `test_banamex_exit_hits_earnings_not_capital` | MC |
| G18 | All Other: Mexico, Asia consumer exits, Legacy Holdings, Corporate/Other; divestiture-related reconciling items | Internal: none | `cit.comp.all_other`; reconciling items as the segment view's residual | Supplement (found) | Group results in exit quarters | `test_required_compositions_exist` | MC |
| G19 | Segment by income type is a matrix: each segment reports NII and NIR, and firm NII is the column total | Internal: none | Cells where the drivers act (TTS, Securities Services and USCC split by type); firm NII by balance sheet and by NII ex-Markets; the matrix noted for conversion | A matrix composition (method) | Firm NII from segment drivers | listed as blocked by the method | MC |
| G20 | New objects absent from the export | Export: none | Transitions in relationship properties, `financial_bridge`, `business_construction` paths | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G21 | New node ids not retrievable | Internal API: none | `/v1/world-models/sally_demo/graph`, `…/entities/citigroup/construction` and its traces | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G22 | A results release reports segment, type and region views of one total on the same day; the import guard folds one view per total and day | Import: `intake/overlap.py` | Not built here (shared code) | A matrix reconciliation in the guard | Importing a full set of actuals | listed as blocked | RET |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, kind, memberships, share-price kind default (`citigroup`) | Already owned | entities.yaml `citigroup` | untouched |
| m26, s16, s19 (statistical records on Citi's values) | Already owned → Modify lightly | interactions.yaml | ids, sizes and kernels kept; transitions added (scope, reduced form, evidence, unresolved inputs) |
| s25, s26 and the NII → share price kind default | Do not touch | interactions.yaml, taxonomy | untouched |
| `net_interest_income`, `services_revenue`, `markets_revenue` definitions | Modify lightly | entities.yaml | `features.view/basis/metric` added; ids and priors kept for Sally's expected paths |
| Compositions, operating states, connected paths, financial mappings, FX and capital values, bindings | Missing | construction/citigroup.yaml; local sources, citations, baselines | built |
| Shared macro values and links (m01–m33, s08–s11; JPMorgan's unemployment, credit spread and equity index values and their macro links) | Do not touch | interactions.yaml, construction/jpmorgan.yaml | reused by id; Citi paths start below them |
| Other banks' objects (JPMorgan, Morgan Stanley) | Do not touch | entities.yaml, construction/jpmorgan.yaml | untouched |
| Import overlap guard | Do not touch (shared code) | `src/axelrod_wm/intake/overlap.py` | finding reported, not edited |

## Definitions and bases

- **Segments** follow Citi's managed basis as recast in 2026: Services (Treasury and Trade Solutions, Securities
  Services), Markets (Fixed Income, Equity), Banking (Investment Banking, Corporate Lending, gain or loss on loan hedges),
  Wealth (Citigold and Retail Banking, Private Bank, Wealth at Work), U.S. Consumer Cards (USCC) and All Other (Legacy
  Franchises: Mexico Consumer/SBMM, Asia Consumer, Legacy Holdings Assets; and Corporate/Other). U.S. Personal Banking
  no longer exists: its cards are USCC and its Retail Banking sits in Wealth. Divestiture-related impacts are reconciling
  items outside All Other's managed basis.
- **Views of net revenue, never added to each other.** The segment rows of the revenue matrix (`cit.mx.revenue`,
  rows `cit.comp.revenue_by_segment`) drive net revenue: rates, activity and credit enter its cells and businesses. The
  type view (firm NII plus non-interest revenue) is the matrix's columns: every segment's NII and non-interest revenue
  is a cell, so firm NII is the sum of the NII cells, and the columns reconcile without driving. The regions view
  (North America, International, and All Other with reconciling items) reconciles (`drives: false`); the dollar reaches
  the driving segments through summary links, since the currency mix per segment is not disclosed.
- **Firm NII** (`citigroup.net_interest_income`) is reported NII incl. Markets NII, driven by the matrix's NII column.
  NII ex-Markets, the guided measure, is a `difference` identity (firm NII − Markets NII); interest income less interest
  expense is a reconciling view.
- **Costs and charges are negative values** (expenses, provisions, interest expense, tax, rewards and partner payments),
  so every part adds to its total with a positive weight. A cost link's sign "−" means "a larger charge".
- **Credit**: USCC provision = net credit losses + reserve build (the allowance roll-forward). Reserves follow the CECL
  outlook (and growth, a day-one reserve); losses follow delinquencies, faster in private label than in general-purpose
  cards.
- **Capital**: CET1 capital is a stock fed by flows (net income, dividends, buybacks, AOCI incl. the currency translation
  adjustment, disallowed-DTA utilization); the CET1 ratio is capital over RWA. Neither is an additive composition.
- **Priors** are synthetic and round, and add up in every view at the medians. The three existing values keep their
  priors (Sally's expected paths depend on them), so the Services, Markets and type views are scaled to them; levels
  near the reported ones are in the local baselines, never here.
- **Exact steps.** Products, ratios, a difference, a weighted average and the CET1 roll-forward are `identities:` and
  `stock_flows:` with derived weights (see [Conversion](#conversion-oct-18-one-driving-view-per-total-identities-a-stock-flow-states));
  steps that fit no form stay uncalibrated, and their `note` says why.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities citigroup` from the loaded model (the
same objects the API serves at `/v1/world-models/sally_demo/entities/citigroup/construction`). A `?` marks a step whose size is unknown
(uncalibrated). Levels are left out here; the local copy adds them.

189 links touch its values: 92 calibrated, 97 uncalibrated (represented, size unknown), 73 accounting, 18 identity, 4 stock-flow; 6 state-dependent; 186 carry a transition.

### Business composition

#### reporting segments: All Other revenue by business, managed basis ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi Mexico Consumer/SBMM (Banamex) revenue | `citigroup.mexico_consumer_revenue` |
| Citi Asia Consumer revenue | `citigroup.asia_consumer_revenue` |
| Citi Legacy Holdings Assets revenue | `citigroup.legacy_holdings_revenue` |
| Residual: Citi Corporate/Other revenue | `citigroup.corporate_other_revenue` |
| **Total: Citi All Other revenue** | `citigroup.all_other_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Legacy Franchises (Mexico, Asia consumer, Legacy Holdings Assets) plus Corporate/Other as the residual.

#### reporting segments: Banking revenue by business, incl. gain or loss on loan hedges ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi Investment Banking revenue | `citigroup.investment_banking_revenue` |
| Citi Corporate Lending revenue | `citigroup.corporate_lending_revenue` |
| Citi gain or loss on loan hedges | `citigroup.loan_hedges` |
| **Total: Citi Banking revenue** | `citigroup.banking_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual. Loan hedges gain when spreads widen, before the provision for the same loans.

#### capital: CET1 capital roll-forward: earnings in, distributions out, AOCI marks and DTA utilization (not an additive partition: flows into a stock) ($bn)

| Part | Value |
|---|---|
| Citi net income | `citigroup.net_income` |
| Citi common dividends | `citigroup.common_dividends` |
| Citi share buybacks | `citigroup.buybacks` |
| Citi AOCI | `citigroup.aoci` |
| Citi disallowed DTA utilization | `citigroup.dta_utilization` |
| **Total: Citi CET1 capital** | `citigroup.cet1_capital` |

A non-additive view: its parts overlap.
Capital accumulates. The method has no stock-flow link, so these are signed causal links (cit-c-ni-cet1, cit-c-div-cet1, cit-c-buyback-cet1, cit-c-aoci-cet1, cit-c-dta-cet1).

#### capital: CET1 management target: the requirement plus a management buffer (pct, fiscal year ending December)

| Part | Value |
|---|---|
| Citi CET1 requirement | `citigroup.cet1_requirement` |
| Citi CET1 management buffer | `citigroup.cet1_management_buffer` |
| **Total: Citi CET1 management target** | `citigroup.cet1_target` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity of management's stated policy.

#### credit: provisions by segment (negative values) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi U.S. Consumer Cards provision | `citigroup.uscc_provision` |
| Citi Banking provision | `citigroup.banking_provision` |
| Citi All Other provision | `citigroup.all_other_provision` |
| Residual: Citi Services, Markets and Wealth provision | `citigroup.other_segment_provision` |
| **Total: Citi provisions for credit losses** | `citigroup.provision_for_credit_losses` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Cards are most of the provision; Mexico consumer most of All Other's.

#### reporting segments: operating expenses by type (negative values) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi compensation and benefits | `citigroup.compensation_expense` |
| Citi technology and communication expense | `citigroup.technology_expense` |
| Residual: Citi other operating expense | `citigroup.other_operating_expense` |
| **Total: Citi operating expenses** | `citigroup.operating_expenses` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Transformation spending lands mostly in technology; the investment program in compensation (severance, talent) and marketing (in other).

#### product: Fixed Income Markets revenue by product ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi rates and currencies revenue | `citigroup.rates_currencies` |
| Citi spread products revenue | `citigroup.spread_products` |
| **Total: Citi Fixed Income Markets revenue** | `citigroup.fixed_income_markets` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual.

#### product: Markets revenue by product (incl. Markets NII) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi Fixed Income Markets revenue | `citigroup.fixed_income_markets` |
| Citi Equity Markets revenue | `citigroup.equity_markets` |
| **Total: Citi markets revenue** | `citigroup.markets_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual.

#### reporting segments: net income: pretax income less tax, noncontrolling interests and discontinued operations ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi pretax income | `citigroup.pretax_income` |
| Citi income tax | `citigroup.income_tax` |
| Residual: Citi noncontrolling interests and discontinued operations | `citigroup.nci_and_discontinued` |
| **Total: Citi net income** | `citigroup.net_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity; the residual holds NCI and discontinued operations.

#### reporting segments: net income by reporting segment ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi Services net income | `citigroup.services_net_income` |
| Citi Markets net income | `citigroup.markets_net_income` |
| Citi Banking net income | `citigroup.banking_net_income` |
| Citi Wealth net income | `citigroup.wealth_net_income` |
| Citi U.S. Consumer Cards net income | `citigroup.uscc_net_income` |
| Residual: Citi All Other and reconciling net income | `citigroup.all_other_net_income` |
| **Total: Citi net income** | `citigroup.net_income` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
A reconciling view (drives: false) of net income; the P&L bridge (cit.comp.net_income) drives it. The residual is All Other plus reconciling items.

#### investment assets: firm NII: interest income less interest expense ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi interest income | `citigroup.interest_income` |
| Citi interest expense | `citigroup.interest_expense` |
| **Total: Citi net interest income** | `citigroup.net_interest_income` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
A reconciling view of firm NII (drives: false): interest income less interest expense, observed and reconciled, never driving firm NII (the matrix column does).

#### reporting segments: pretax income: revenue less operating expenses less provisions ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi total revenues, net of interest expense | `citigroup.net_revenue` |
| Citi operating expenses | `citigroup.operating_expenses` |
| Citi provisions for credit losses | `citigroup.provision_for_credit_losses` |
| **Total: Citi pretax income** | `citigroup.pretax_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity: expenses and provisions are negative values.

#### regions: total revenues by region: North America, International (four businesses), and All Other with reconciling items ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi North America revenue | `citigroup.north_america_revenue` |
| Citi international revenue | `citigroup.international_revenue` |
| Residual: Citi All Other and reconciling revenue (regions view) | `citigroup.legacy_corporate_revenue` |
| **Total: Citi total revenues, net of interest expense** | `citigroup.net_revenue` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
A reconciling view (drives: false): observed and reconciled, never driving net revenue. The dollar's translation reaches the driving segments through summary links (the currency mix per segment is not disclosed). The residual is All Other (incl. Mexico) and reconciling items, not split by region.

#### reporting segments: total revenues, net of interest expense, by reporting segment (managed) plus reconciling items ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi services revenue | `citigroup.services_revenue` |
| Citi markets revenue | `citigroup.markets_revenue` |
| Citi Banking revenue | `citigroup.banking_revenue` |
| Citi Wealth revenue | `citigroup.wealth_revenue` |
| Citi U.S. Consumer Cards revenue | `citigroup.uscc_revenue` |
| Citi All Other revenue | `citigroup.all_other_revenue` |
| Residual: Citi revenue reconciling items | `citigroup.reconciling_items_revenue` |
| **Total: Citi total revenues, net of interest expense** | `citigroup.net_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driven view: rates, activity and credit enter through the segment cells below it. Not the type view (cit.comp.revenue_by_type) or the regions view (cit.comp.revenue_by_region): never added to them. Reconciling items are divestiture-related impacts outside All Other's managed basis.

#### product: total revenues, net of interest expense: net interest income plus non-interest revenue ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi net interest income | `citigroup.net_interest_income` |
| Citi non-interest revenue | `citigroup.noninterest_revenue` |
| **Total: Citi total revenues, net of interest expense** | `citigroup.net_revenue` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
The passive view of the revenue matrix (cit.mx.revenue): firm NII and non-interest revenue are column totals reached from the segment cells, and reconcile to net revenue without driving it. m26 and cit-c-nonusd-nii size firm NII (summary links).

#### reporting segments: Services revenue by business and income type ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi Services net interest income | `citigroup.services_nii` |
| Citi Services non-interest revenue | `citigroup.services_nir` |
| **Total: Citi services revenue** | `citigroup.services_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Services by income type: the two cells of the revenue matrix (cit.mx.revenue). An exact split.

#### reporting segments: Services NII by business ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi TTS net interest income | `citigroup.tts_nii` |
| Citi Securities Services net interest income | `citigroup.ss_nii` |
| **Total: Citi Services net interest income** | `citigroup.services_nii` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: rates drive these lines.

#### reporting segments: Services non-interest revenue by business ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi TTS non-interest revenue | `citigroup.tts_nir` |
| Citi Securities Services non-interest revenue | `citigroup.ss_nir` |
| **Total: Citi Services non-interest revenue** | `citigroup.services_nir` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: flows and asset levels drive these lines.

#### reporting segments: U.S. Consumer Cards revenue by income type ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi U.S. Consumer Cards net interest income | `citigroup.uscc_nii` |
| Citi U.S. Consumer Cards non-interest revenue | `citigroup.uscc_nir` |
| **Total: Citi U.S. Consumer Cards revenue** | `citigroup.uscc_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual. NIR is negative: rewards and partner payments exceed the fees.

#### product: U.S. Consumer Cards non-interest revenue by line ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi card interchange fees | `citigroup.card_interchange` |
| Citi card rewards and partner payments | `citigroup.card_rewards_partner` |
| Residual: Citi USCC other fees | `citigroup.uscc_other_fees` |
| **Total: Citi U.S. Consumer Cards non-interest revenue** | `citigroup.uscc_nir` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Interchange less rewards and partner payments; the residual holds other fees.

#### credit: USCC provision: net credit losses plus reserve build (allowance roll-forward) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi U.S. Consumer Cards net credit losses | `citigroup.uscc_net_credit_losses` |
| Citi U.S. Consumer Cards reserve build | `citigroup.uscc_reserve_build` |
| **Total: Citi U.S. Consumer Cards provision** | `citigroup.uscc_provision` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity of the allowance roll-forward (other items are negligible). Losses follow delinquencies; the reserve follows the CECL outlook and growth.

#### reporting segments: Wealth revenue by business ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Citi Citigold and Retail Banking revenue | `citigroup.citigold_retail_banking` |
| Citi Private Bank revenue | `citigroup.private_bank` |
| Citi Wealth at Work revenue | `citigroup.wealth_at_work` |
| **Total: Citi Wealth revenue** | `citigroup.wealth_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual.

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `cit.id.cet1_ratio` (ratio) | Citi CET1 ratio = 100 x Citi CET1 capital / Citi risk-weighted assets | Citi CET1 capital (numerator, +1.365); Citi risk-weighted assets (denominator, -1.310) | % = 100 x $bn / $bn |
| `cit.id.efficiency` (ratio) | Citi efficiency ratio = -100 x Citi operating expenses / Citi total revenues, net of interest expense | Citi operating expenses (numerator, -1.163); Citi total revenues, net of interest expense (denominator, -1.675) | % = -100 x (negative expenses $bn/yr) / $bn/yr |
| `cit.id.interchange` (product) | Citi card interchange fees = 0.01 x Citi U.S. card purchase volume x Citi card interchange rate | Citi U.S. card purchase volume (factor, +0.800); Citi card interchange rate (factor, +0.377) | $bn/yr = $bn/yr x % x 0.01 |
| `cit.id.mexico` (ratio) | Citi Mexico Consumer/SBMM (Banamex) revenue = Citi Mexico Consumer/SBMM revenue in pesos / USD/MXN | Citi Mexico Consumer/SBMM revenue in pesos (numerator, +1.000); usd_mxn.rate (denominator, -0.750) | $bn/yr = MXN bn/yr / (MXN per $) |
| `cit.id.nii_ex_markets` (difference) | Citi NII ex-Markets = Citi net interest income - Citi Markets net interest income | Citi net interest income (total, +1.482); Citi Markets net interest income (deduction, -0.694) | $bn/yr = $bn/yr - $bn/yr |
| `cit.id.rewards` (product) | Citi card rewards and partner payments = -0.01 x Citi U.S. card purchase volume x Citi card rewards and partner payment rate | Citi U.S. card purchase volume (factor, -0.833); Citi card rewards and partner payment rate (factor, -0.526) | $bn/yr (negative) = -0.01 x $bn/yr x % |
| `cit.id.uscc_ncl` (product) | Citi U.S. Consumer Cards net credit losses = -0.01 x Citi U.S. card net credit loss rate x Citi U.S. Consumer Cards loans | Citi U.S. card net credit loss rate (factor, -1.050); Citi U.S. Consumer Cards loans (factor, -0.420) | $bn/yr (negative) = -0.01 x % x $bn |
| `cit.id.uscc_nco` (weighted_average) | Citi U.S. card net credit loss rate = 0.8 x Citi general-purpose card net credit loss rate + 0.2 x Citi private-label card net credit loss rate | Citi general-purpose card net credit loss rate (weight 0.8, +0.800); Citi private-label card net credit loss rate (weight 0.2, +0.267) | % = weights x % |
| `cit.id.uscc_nii` (product) | Citi U.S. Consumer Cards net interest income = 0.01 x Citi U.S. Consumer Cards loans x Citi U.S. card NII yield | Citi U.S. Consumer Cards loans (factor, +0.750); Citi U.S. card NII yield (factor, +0.595) | $bn/yr = $bn x % x 0.01 |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `cit.sf.cet1` | Citi CET1 capital (closing) = Citi CET1 capital (opening) + Citi net income + Citi disallowed DTA utilization - Citi common dividends - Citi share buybacks, per 365 days | Citi net income (inflow, +0.330); Citi disallowed DTA utilization (inflow, +0.060); Citi common dividends (outflow, -0.060); Citi share buybacks (outflow, -0.800) |

### Matrix `cit.mx.revenue`: cit.comp.revenue_by_segment x cit.comp.revenue_by_type (the rows drive the total; cit.comp.revenue_by_type reconciles)

| | Citi net interest income | Citi non-interest revenue |
|---|---|---|
| Citi All Other revenue | `citigroup.all_other_nii` | `citigroup.all_other_nir` |
| Citi Banking revenue | `citigroup.banking_nii` | `citigroup.banking_nir` |
| Citi markets revenue | `citigroup.markets_nii` | `citigroup.markets_nir` |
| Citi revenue reconciling items | `citigroup.reconciling_nii` | `citigroup.reconciling_nir` |
| Citi services revenue | `citigroup.services_nii` | `citigroup.services_nir` |
| Citi U.S. Consumer Cards revenue | `citigroup.uscc_nii` | `citigroup.uscc_nir` |
| Citi Wealth revenue | `citigroup.wealth_nii` | `citigroup.wealth_nir` |

Citi reports each segment's NII and non-interest revenue. Rows (segments) drive net revenue; firm NII and non-interest revenue are column totals reached from the cells. Services and USCC rows are made of their cells; the other rows are driven by their businesses or products, so their cells' row links carry no number (they reconcile only).

### Operating and financial paths

#### Citi capital and payout

**Trigger:** earnings accrue. **Endpoint:** Citi CET1 ratio.

Citi net income → [retained] Citi CET1 capital → [dta] Citi disallowed DTA utilization? → [payout] Citi common dividends? → Citi CET1 capital → Citi CET1 capital → Citi CET1 ratio → Citi share buybacks? → Citi CET1 capital  (? marks a step whose size is unknown)

Earnings add to CET1 and free deducted DTA; dividends and buybacks return the excess over the target.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [retained] `cit-c-ni-cet1` | Retained earnings add to common equity and so to CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | +0.33 sd/sd (stock-flow, accumulates per 365 days) |
| 2 [dta] `cit-c-ni-dta` | US taxable profits let Citi use net operating loss and tax-credit carry-forwards, reducing the disallowed DTA (Citi tax; regulation) | profits in the US tax group; observable: disallowed DTA, quarterly | onset same year; build years; persists until used up; recognized quarter-end capital | guidance / guidance / unknown / inferred | losses; foreign-source income that does not use the credits | disallowed DTA utilization | unknown |
| 3 [payout] `cit-c-ni-div` | The board sets the dividend with earnings capacity; a higher earnings base supports increases (Citi board) | capital above target; observable: dividend per share | onset annual review; build years; persists sticky; recognized declaration | documented / inferred / unknown / inferred | capital below target; stress-test results | common dividends | unknown |
| 4 `cit-c-dta-cet1` | Using carried-forward tax assets against US profits shrinks the DTA deducted from CET1, adding capital (a Citi-specific source) (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | +0.06 sd/sd (stock-flow, accumulates per 365 days) |
| 5 `cit-c-div-cet1` | Dividends reduce common equity and CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | -0.06 sd/sd (stock-flow, accumulates per 365 days) |
| 6 `cit-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (accounting) | RWA unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | +1.36 sd/sd (identity) |
| 7 `cit-c-ratio-buyback` | Capital above the management target is returned through buybacks (Citi management and board) | the ratio above target; growth needs met first; observable: buybacks against the CET1 ratio and target, quarterly | onset next quarter; build the year; persists while excess lasts; recognized capital actions | guidance / guidance / unknown / guidance | growth opportunities absorb capital; AOCI volatility makes management cautious | share buybacks | unknown; acts only while Citi CET1 ratio is above 12.6 |
| 8 `cit-c-buyback-cet1` | Buybacks reduce common equity and CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | -0.80 sd/sd (stock-flow, accumulates per 365 days) |

Unresolved inputs: DTA utilization schedule (found not connected).

#### Citi capital requirement to buybacks

**Trigger:** the CET1 requirement rises (stress buffer, G-SIB surcharge, a scheduled step-up). **Endpoint:** Citi CET1 ratio.

Citi CET1 requirement → Citi CET1 management target → Citi share buybacks? → Citi CET1 capital → Citi CET1 ratio  (? marks a step whose size is unknown)

A higher requirement raises the management target and leaves less excess to buy back.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `cit-a-tgt-cet1-requirement` | Citi CET1 requirement is one part of Citi CET1 management target (CET1 management target: the requirement plus a management buffer); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | CET1 management target | +1.00 sd/sd (accounting) |
| 2 `cit-c-target-buyback` | A higher target raises the capital that must be kept (Citi management) | ratio near target; observable: buybacks | onset next quarter; build the year; persists while it holds; recognized capital actions | guidance / guidance / unknown / guidance | excess far above target | share buybacks | unknown; acts only while Citi CET1 ratio is above 12.6 |
| 3 `cit-c-buyback-cet1` | Buybacks reduce common equity and CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | -0.80 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `cit-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (accounting) | RWA unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | +1.36 sd/sd (identity) |

#### Citi consumer credit cycle (cards)

**Trigger:** US unemployment rises. **Endpoint:** Citi net income.

US unemployment rate → [cecl] Citi U.S. Consumer Cards reserve build? → [losses] Citi U.S. card 30-89 day delinquency rate? → [gpcc] Citi general-purpose card net credit loss rate? → [plcc] Citi private-label card net credit loss rate? → [underwriting] Citi U.S. Consumer Cards loans? → Citi U.S. card net credit loss rate → Citi U.S. card net credit loss rate → Citi U.S. Consumer Cards net credit losses → Citi card rewards and partner payments? → Citi U.S. Consumer Cards provision → Citi U.S. Consumer Cards provision → Citi provisions for credit losses → Citi U.S. Consumer Cards non-interest revenue → Citi U.S. Consumer Cards revenue → Citi total revenues, net of interest expense → Citi pretax income → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

Two clocks: CECL reserves build at once on the outlook; losses arrive after delinquencies roll, faster in private label. Counter-paths: retail partners share private-label losses through lower partner payments, and Citi tightens underwriting.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [cecl] `cit-c-unemp-usccreserve` | CECL reserves lifetime expected losses on today's book: a worse unemployment outlook raises the allowance at once (a larger negative reserve build), before any loss occurs; Citi weights its reserve to an unemployment path above the consensus (Citi risk management (CECL)) | the unemployment forecast in the reserve scenarios moves; observable: card allowance and reserve build, quarterly | onset the quarter the outlook changes; build none; persists until losses are charged off; recognized provision each quarter | documented / documented / unknown / documented | a release when the outlook improves | USCC reserve build | unknown |
| 2 [losses] `cit-c-unemp-delinq` | Job losses make revolving cardholders miss payments (cardholders) | job losses among revolving borrowers; observable: 30-89 day delinquencies, monthly | onset 1-2 quarters; build several quarters; persists while unemployment holds; recognized delinquency reports | documented / documented / unknown / inferred | income support; tighter underwriting | card delinquency rate | unknown |
| 3 [gpcc] `cit-c-delinq-gpcc` | Delinquent general-purpose balances roll through the buckets and are charged off at 180 days past due; private-label borrowers roll faster (cardholders; Citi collections) | roll rates hold; observable: general-purpose net credit loss rate, quarterly | onset about two quarters; build 1-2 quarters; persists while delinquencies hold; recognized net credit losses each quarter | documented / documented / unknown / documented | collections recoveries; forbearance | general-purpose loss rate | unknown |
| 4 [plcc] `cit-c-delinq-plcc` | Delinquent private-label balances roll through the buckets and are charged off at 180 days past due; private-label borrowers roll faster (cardholders; Citi collections) | roll rates hold; observable: private-label net credit loss rate, quarterly | onset about two quarters; build 1-2 quarters; persists while delinquencies hold; recognized net credit losses each quarter | documented / documented / unknown / documented | collections recoveries; forbearance | private-label loss rate | unknown |
| 5 [underwriting] `cit-c-delinq-loans` | Feedback: when delinquencies rise, Citi tightens card underwriting reactively, slowing balance growth (Citi card risk management) | rising delinquencies; observable: new account acquisitions and card loans | onset 1-2 quarters; build several quarters; persists until losses ease; recognized average balances | broker / broker / unknown / unknown | a growth push (marketing investment) | USCC loans | unknown |
| 6 `cit-c-gpcc-usccnco` | The USCC loss rate is the loan-weighted average of the general-purpose and the other card loss rates (accounting) | loan mix unchanged; observable: USCC net credit loss rate | onset same quarter; build none; persists identity; recognized net credit losses each quarter | documented / documented / inferred / documented | a mix shift between the books | USCC net credit loss rate | +0.80 sd/sd (identity) |
| 7 `cit-c-plcc-usccnco` | The USCC loss rate is the loan-weighted average of the private-label and the other card loss rates (accounting) | loan mix unchanged; observable: USCC net credit loss rate | onset same quarter; build none; persists identity; recognized net credit losses each quarter | documented / documented / inferred / documented | a mix shift between the books | USCC net credit loss rate | +0.27 sd/sd (identity) |
| 8 `cit-c-nco-ncl` | Net credit losses are the loss rate times average loans (larger, more negative) (accounting) | loans unchanged; observable: USCC net credit losses | onset same quarter; build none; persists identity; recognized provision each quarter | documented / documented / inferred / documented | loan run-off | USCC net credit losses | -1.05 sd/sd (identity) |
| 9 `cit-c-plcc-partner` | Counter-path: retail-services contracts share economics with the retail partner; higher losses reduce the payments due to the partner (the contra-revenue shrinks), cushioning the card segment (Citi Retail Services and its retail partners) | loss-sharing terms in the partner contract; observable: partner payments against private-label losses | onset next settlement period; build 1-2 quarters; persists contract term; recognized non-interest revenue each quarter | inferred / inferred / unknown / unknown | contracts without loss sharing; renegotiation at renewal | card rewards and partner payments | unknown |
| 10 `cit-a-usccprov-uscc-net-credit-losses` | Citi U.S. Consumer Cards net credit losses is one part of Citi U.S. Consumer Cards provision (USCC provision: net credit losses plus reserve build (allowance roll-forward)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards provision | +0.83 sd/sd (accounting) |
| 11 `cit-a-usccprov-uscc-reserve-build` | Citi U.S. Consumer Cards reserve build is one part of Citi U.S. Consumer Cards provision (USCC provision: net credit losses plus reserve build (allowance roll-forward)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards provision | +0.83 sd/sd (accounting) |
| 12 `cit-a-prov-uscc-provision` | Citi U.S. Consumer Cards provision is one part of Citi provisions for credit losses (provisions by segment (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | provisions for credit losses | +0.50 sd/sd (accounting) |
| 13 `cit-a-usccnir-card-rewards-partner` | Citi card rewards and partner payments is one part of Citi U.S. Consumer Cards non-interest revenue (U.S. Consumer Cards non-interest revenue by line); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards non-interest revenue | +1.50 sd/sd (accounting) |
| 14 `cit-a-uscc-uscc-nir` | Citi U.S. Consumer Cards non-interest revenue is one part of Citi U.S. Consumer Cards revenue (U.S. Consumer Cards revenue by income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards revenue | +0.50 sd/sd (accounting) |
| 15 `cit-a-seg-uscc-revenue` | Citi U.S. Consumer Cards revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.23 sd/sd (accounting) |
| 16 `cit-a-pretax-provision-for-credit-losses` | Citi provisions for credit losses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.55 sd/sd (accounting) |
| 17 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 18 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: card loss sensitivity to unemployment (not disclosed in reviewed sources); partner loss-sharing terms (not disclosed in reviewed sources); reserve sensitivity to the unemployment scenario (not disclosed in reviewed sources); roll rates (not disclosed in reviewed sources).

#### Citi card balance growth and its reserve cost

**Trigger:** card balances grow (acquisition marketing, a purchased portfolio). **Endpoint:** Citi net income.

Citi U.S. Consumer Cards loans → [nii] Citi U.S. Consumer Cards net interest income → [day_one] Citi U.S. Consumer Cards reserve build? → [losses] Citi U.S. Consumer Cards net credit losses → [capital] Citi risk-weighted assets? → Citi U.S. Consumer Cards revenue → Citi total revenues, net of interest expense → Citi U.S. Consumer Cards provision → Citi U.S. Consumer Cards provision → Citi provisions for credit losses → Citi pretax income → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

Balances earn NII but need a day-one reserve, season into losses, and consume capital.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [nii] `cit-c-loans-usccnii` | USCC NII is average card loans times the card NII yield (accounting) | revolving share holds; observable: USCC NII as a share of average loans | onset same quarter; build as promotional balances convert; persists while held; recognized interest income each quarter | documented / documented / inferred / documented | promotional (zero-rate) balances; transactors | USCC NII | +0.75 sd/sd (identity) |
| 2 [day_one] `cit-c-loans-reserve` | Counter-path: each new card balance needs a lifetime-loss reserve on day one, so balance growth (or a purchased portfolio) costs provision before it earns (accounting (CECL)) | growth or a portfolio purchase; observable: reserve build against loan growth | onset the quarter of growth; build none; persists until the loans season; recognized provision each quarter | documented / documented / unknown / documented | run-off releases reserves | USCC reserve build | unknown |
| 3 [losses] `cit-c-loans-ncl` | At a given loss rate, a larger book charges off more (accounting) | loss rate unchanged; observable: USCC net credit losses | onset 1-2 years for new vintages; build seasoning; persists while held; recognized provision each quarter | documented / documented / inferred / inferred | prime-only growth | USCC net credit losses | -0.42 sd/sd (identity) |
| 4 [capital] `cit-c-uscc-rwa` | Card loans carry credit risk weights, so balance growth consumes capital (regulation) | standardized weights; observable: RWA, quarterly | onset same quarter; build none; persists while held; recognized quarter-end capital | inferred / inferred / unknown / inferred | securitization; portfolio sales | risk-weighted assets | unknown |
| 5 `cit-a-uscc-uscc-nii` | Citi U.S. Consumer Cards net interest income is one part of Citi U.S. Consumer Cards revenue (U.S. Consumer Cards revenue by income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards revenue | +1.10 sd/sd (accounting) |
| 6 `cit-a-seg-uscc-revenue` | Citi U.S. Consumer Cards revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.23 sd/sd (accounting) |
| 7 `cit-a-usccprov-uscc-reserve-build` | Citi U.S. Consumer Cards reserve build is one part of Citi U.S. Consumer Cards provision (USCC provision: net credit losses plus reserve build (allowance roll-forward)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards provision | +0.83 sd/sd (accounting) |
| 8 `cit-a-usccprov-uscc-net-credit-losses` | Citi U.S. Consumer Cards net credit losses is one part of Citi U.S. Consumer Cards provision (USCC provision: net credit losses plus reserve build (allowance roll-forward)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards provision | +0.83 sd/sd (accounting) |
| 9 `cit-a-prov-uscc-provision` | Citi U.S. Consumer Cards provision is one part of Citi provisions for credit losses (provisions by segment (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | provisions for credit losses | +0.50 sd/sd (accounting) |
| 10 `cit-a-pretax-provision-for-credit-losses` | Citi provisions for credit losses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.55 sd/sd (accounting) |
| 11 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 12 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

#### Citi card spend to card fees, net of rewards

**Trigger:** consumer card spending rises (prices or growth). **Endpoint:** Citi net income.

US headline CPI → Citi U.S. card purchase volume? → [interchange] Citi card interchange fees → [rewards] Citi card rewards and partner payments → Citi U.S. Consumer Cards non-interest revenue → Citi U.S. Consumer Cards non-interest revenue → Citi U.S. Consumer Cards revenue → Citi total revenues, net of interest expense → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

Interchange and rewards with partner payments move with the same purchases; the net is small and can be negative.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `cit-c-cpi-spend` | Higher prices raise nominal card spend (cardholders) | Citi's share of card spend holds; observable: card purchase volume, quarterly | onset same month; build none; persists while it holds; recognized fees each quarter | documented / inferred / unknown / inferred | cash or debit substitution; share loss | card purchase volume | unknown |
| 2 [interchange] `cit-c-spend-interchange` | Interchange is charged on every purchase, so it rises with purchase volume (merchants (via the networks)) | interchange rates unchanged; observable: interchange fees against card spend | onset same month; build none; persists while volume holds; recognized fees each quarter | documented / documented / inferred / documented | regulatory caps or merchant litigation | interchange fees | +0.80 sd/sd (identity) |
| 3 [rewards] `cit-c-spend-rewards` | Counter-path: rewards and co-brand partner payments are earned on the same purchases, so they rise with volume (a larger negative) and absorb most of the interchange (Citi USCC; co-brand and retail partners) | reward and partner terms unchanged; observable: rewards and partner payments against card spend | onset same month; build none; persists while volume holds; recognized non-interest revenue each quarter | documented / documented / inferred / documented | renegotiated partner contracts; reward devaluations | card rewards and partner payments | -0.83 sd/sd (identity) |
| 4 `cit-a-usccnir-card-interchange` | Citi card interchange fees is one part of Citi U.S. Consumer Cards non-interest revenue (U.S. Consumer Cards non-interest revenue by line); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards non-interest revenue | +1.25 sd/sd (accounting) |
| 5 `cit-a-usccnir-card-rewards-partner` | Citi card rewards and partner payments is one part of Citi U.S. Consumer Cards non-interest revenue (U.S. Consumer Cards non-interest revenue by line); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards non-interest revenue | +1.50 sd/sd (accounting) |
| 6 `cit-a-uscc-uscc-nir` | Citi U.S. Consumer Cards non-interest revenue is one part of Citi U.S. Consumer Cards revenue (U.S. Consumer Cards revenue by income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards revenue | +0.50 sd/sd (accounting) |
| 7 `cit-a-seg-uscc-revenue` | Citi U.S. Consumer Cards revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.23 sd/sd (accounting) |
| 8 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 9 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: rewards and partner payment rate per dollar of spend (found connected).

#### Citi cross-border flows to Services

**Trigger:** world growth and trade pick up (US growth as the represented driver). **Endpoint:** Citi net income.

US real GDP growth → Citi cross-border transaction value? → [fees] Citi TTS non-interest revenue? → [deposits] Citi Services average deposits? → Citi TTS net interest income? → Citi Services non-interest revenue → Citi Services net interest income → Citi services revenue → Citi services revenue → Citi total revenues, net of interest expense → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

More cross-border activity earns payment and FX fees and brings operating deposits that earn the deposit spread. s19 (US GDP to Services revenue) is the reduced form and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `cit-c-usgdp-xborder` | Faster US growth raises trade, investment and payment flows between countries, which Citi's global network clears (Citi's corporate clients (multinationals, trade)) | Citi's share of its clients' flows holds; observable: cross-border transaction value, quarterly | onset 1 quarter; build several quarters; persists while growth holds; recognized fees each quarter | documented / inferred / unknown / unknown | trade barriers and sanctions reroute flows; share loss to fintechs and local banks | cross-border transaction value | unknown |
| 2 [fees] `cit-c-xborder-ttsnir` | Cross-border payments earn transaction and FX fees, so TTS non-interest revenue rises with the value processed (Citi TTS) | fee rates hold; observable: TTS NIR against cross-border transaction value | onset same quarter; build none; persists while volumes hold; recognized fees each quarter | documented / documented / unknown / documented | price competition (wire fees cut to compete) compresses the fee rate | TTS non-interest revenue | unknown |
| 3 [deposits] `cit-c-xborder-svcdeps` | Clients that run payments and liquidity through Citi leave operating balances behind; more flow brings more deposits (Citi's corporate clients (treasurers)) | Citi stays the clients' operating bank; observable: Services average deposits, quarterly | onset 1 quarter; build several quarters; persists while the relationship holds; recognized average balances | documented / inferred / unknown / unknown | clients move excess balances to money funds or other banks | Services deposits | unknown |
| 4 `cit-c-svcdeps-ttsnii` | TTS NII is operating deposits times the deposit spread; more balances earn more at the prevailing spread (Citi TTS) | spread positive; observable: TTS NII and Services deposits | onset same quarter; build none; persists while held; recognized interest income each quarter | documented / documented / unknown / documented | spread compression | TTS NII | unknown |
| 5 `cit-a-svcnir-tts-nir` | Citi TTS non-interest revenue is one part of Citi Services non-interest revenue (Services non-interest revenue by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Services non-interest revenue | +0.48 sd/sd (accounting) |
| 6 `cit-a-svcnii-tts-nii` | Citi TTS net interest income is one part of Citi Services net interest income (Services NII by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Services net interest income | +0.81 sd/sd (accounting) |
| 7 `cit-a-svc-services-nir` | Citi Services non-interest revenue is one part of Citi services revenue (Services revenue by business and income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | services revenue | +0.40 sd/sd (accounting) |
| 8 `cit-a-svc-services-nii` | Citi Services net interest income is one part of Citi services revenue (Services revenue by business and income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | services revenue | +0.67 sd/sd (accounting) |
| 9 `cit-a-seg-services-revenue` | Citi services revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 10 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 11 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: TTS fee rate on cross-border value (not disclosed in reviewed sources); cross-border volume elasticity to GDP and trade (not disclosed in reviewed sources); deposit growth elasticity to client activity (not disclosed in reviewed sources).

#### Citi deal activity to Banking

**Trigger:** deal and issuance activity rises. **Endpoint:** Citi net income.

Deal and issuance activity → Citi Investment Banking revenue? → Citi Banking revenue → Citi compensation and benefits? → Citi operating expenses → Citi total revenues, net of interest expense → Citi pretax income → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

The fee wallet times Citi's share, with banker incentive pay as the offset.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `cit-c-deals-ib` | Investment Banking fees are the industry fee wallet (deals and issuance) times Citi's share (Citi Banking; issuers and acquirers) | deal closings; share holds; observable: Investment Banking revenue; third-party league-table fee data | onset at deal close; build 1-2 quarters; persists while activity holds; recognized fees at completion | documented / documented / unknown / documented | deal delays; share loss | Investment Banking revenue | unknown |
| 2 `cit-a-bank-investment-banking-revenue` | Citi Investment Banking revenue is one part of Citi Banking revenue (Banking revenue by business, incl. gain or loss on loan hedges); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Banking revenue | +0.89 sd/sd (accounting) |
| 3 `cit-c-ib-comp` | Counter-path: banker incentive pay accrues with fees (Citi) | revenue-linked accrual; observable: compensation against IB revenue | onset same quarter; build none; persists through year end; recognized compensation expense | inferred / inferred / unknown / inferred | fixed pay of new hires | compensation and benefits | unknown |
| 4 `cit-a-exp-compensation-expense` | Citi compensation and benefits is one part of Citi operating expenses (operating expenses by type (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating expenses | +0.67 sd/sd (accounting) |
| 5 `cit-a-seg-banking-revenue` | Citi Banking revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.16 sd/sd (accounting) |
| 6 `cit-a-pretax-operating-expenses` | Citi operating expenses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.68 sd/sd (accounting) |
| 7 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 8 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: IB fee sensitivity to deal activity (not disclosed in reviewed sources).

#### Citi dollar strength to revenue, expenses and capital

**Trigger:** the dollar strengthens against Citi's international currencies. **Endpoint:** Citi CET1 ratio.

USD/EUR → Citi translation FX basket? → [international] Citi international revenue? → [services] Citi services revenue? → [markets] Citi markets revenue? → [banking] Citi Banking revenue? → [wealth] Citi Wealth revenue? → [expenses] Citi operating expenses? → [cta] Citi AOCI? → [rwa] Citi risk-weighted assets? → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi pretax income → Citi pretax income → Citi net income → Citi CET1 capital? → Citi CET1 capital → Citi CET1 ratio → Citi CET1 ratio  (? marks a step whose size is unknown)

One move, four parallel responses: international revenue and expenses translate into fewer dollars (a natural hedge), the CTA lowers AOCI and CET1, and non-USD RWA shrink (the ratio is hedged).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `cit-c-eur-fxbasket` | A stronger dollar against the euro raises the translation basket by the euro's weight in Citi's international revenue (market) | weight of the currency in international revenue; observable: exchange rates | onset same day; build none; persists while rates hold; recognized translation at period-average rates | documented / inferred / unknown / documented | other currencies moving the other way | translation FX basket | unknown |
| 2 [international] `cit-c-fxbasket-intlrev` | International revenue is earned in local currencies and translated at period-average rates; a stronger dollar lowers its dollar value one for one with the currency's weight (accounting (translation)) | revenue earned in local currency (USD-denominated international revenue does not move); observable: international revenue and the company's FX-translation remarks | onset same quarter; build none; persists while rates hold; recognized each quarter at average rates | documented / documented / unknown / documented | USD-denominated international business; revenue hedges | international revenue | unknown |
| 3 [services] `cit-c-fxbasket-services` | Summary link: the international part of the services segment is earned in local currencies and translates into fewer dollars when the dollar strengthens; the segment's currency mix is not disclosed, so the share (and the size) is unknown (accounting (translation)) | revenue earned in local currency; observable: segment North America / International revenue | onset same quarter; build none; persists while rates hold; recognized each quarter at average rates | documented / documented / unknown / documented | USD-denominated international business; revenue hedges | services revenue | unknown |
| 4 [markets] `cit-c-fxbasket-markets` | Summary link: the international part of the markets segment is earned in local currencies and translates into fewer dollars when the dollar strengthens; the segment's currency mix is not disclosed, so the share (and the size) is unknown (accounting (translation)) | revenue earned in local currency; observable: segment North America / International revenue | onset same quarter; build none; persists while rates hold; recognized each quarter at average rates | documented / documented / unknown / documented | USD-denominated international business; revenue hedges | markets revenue | unknown |
| 5 [banking] `cit-c-fxbasket-banking` | Summary link: the international part of the banking segment is earned in local currencies and translates into fewer dollars when the dollar strengthens; the segment's currency mix is not disclosed, so the share (and the size) is unknown (accounting (translation)) | revenue earned in local currency; observable: segment North America / International revenue | onset same quarter; build none; persists while rates hold; recognized each quarter at average rates | documented / documented / unknown / documented | USD-denominated international business; revenue hedges | banking revenue | unknown |
| 6 [wealth] `cit-c-fxbasket-wealth` | Summary link: the international part of the wealth segment is earned in local currencies and translates into fewer dollars when the dollar strengthens; the segment's currency mix is not disclosed, so the share (and the size) is unknown (accounting (translation)) | revenue earned in local currency; observable: segment North America / International revenue | onset same quarter; build none; persists while rates hold; recognized each quarter at average rates | documented / documented / unknown / documented | USD-denominated international business; revenue hedges | wealth revenue | unknown |
| 7 [expenses] `cit-c-fxbasket-opex` | Counter-path: international expenses are also in local currency, so a stronger dollar shrinks them (less negative), a natural hedge on the revenue effect (accounting (translation)) | local-currency cost base; observable: operating expenses and the company's FX-translation remarks | onset same quarter; build none; persists while rates hold; recognized each quarter | inferred / inferred / unknown / inferred | costs in US hubs | operating expenses | unknown |
| 8 [cta] `cit-c-fxbasket-aoci` | A stronger dollar lowers the dollar value of net investments in foreign subsidiaries; the loss, net of net-investment hedges, goes to the CTA in AOCI and so to CET1 (accounting; Citi Treasury (net-investment hedges)) | unhedged share of net investments; observable: CTA in AOCI, quarterly | onset immediate; build none; persists while rates hold; recognized quarter-end capital | documented / documented / unknown / documented | net-investment hedges designed to keep the CET1 ratio flat | AOCI | unknown |
| 9 [rwa] `cit-c-fxbasket-rwa` | Counter-path: non-USD RWA also translate into fewer dollars, so the CET1 ratio moves less than CET1 capital (Citi hedges the ratio) (accounting; Citi Treasury) | non-USD assets; observable: RWA, quarterly | onset immediate; build none; persists while rates hold; recognized quarter-end capital | documented / inferred / unknown / documented | USD-denominated assets abroad | risk-weighted assets | unknown |
| 10 `cit-a-seg-services-revenue` | Citi services revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 11 `cit-a-seg-markets-revenue` | Citi markets revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.43 sd/sd (accounting) |
| 12 `cit-a-seg-banking-revenue` | Citi Banking revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.16 sd/sd (accounting) |
| 13 `cit-a-seg-wealth-revenue` | Citi Wealth revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.17 sd/sd (accounting) |
| 14 `cit-a-pretax-operating-expenses` | Citi operating expenses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.68 sd/sd (accounting) |
| 15 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 16 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |
| 17 `cit-c-aoci-cet1` | AOCI is part of common equity and is not filtered out of CET1 for the largest banks, so a fall in AOCI lowers CET1 capital one for one (regulation) | AOCI included in CET1; observable: CET1 capital and AOCI, quarterly | onset immediate; build none; persists until marks reverse; recognized quarter-end capital | documented / documented / unknown / documented | a rule change filtering AOCI | CET1 capital | unknown |
| 18 `cit-c-ni-cet1` | Retained earnings add to common equity and so to CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | +0.33 sd/sd (stock-flow, accumulates per 365 days) |
| 19 `cit-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (accounting) | RWA unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | +1.36 sd/sd (identity) |
| 20 `cit-c-rwa-ratio` | More RWA at the same capital lowers the CET1 ratio (accounting) | capital unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | -1.31 sd/sd (identity) |

Unresolved inputs: CET1 ratio sensitivity to a USD move (disclosed not supplied); currency mix of international revenue (not disclosed in reviewed sources); non-USD share of international revenue (not disclosed in reviewed sources).

#### Citi investment program and its payback

**Trigger:** Citi pulls forward or adds growth investment. **Endpoint:** Citi net income.

Citi growth investment program → [severance] Citi compensation and benefits? → [marketing] Citi other operating expense? → [payback] Citi productivity savings? → [cards] Citi U.S. Consumer Cards loans? → Citi compensation and benefits? → Citi U.S. Consumer Cards net interest income → Citi operating expenses → Citi operating expenses → Citi U.S. Consumer Cards revenue → Citi total revenues, net of interest expense → Citi pretax income → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

Investment raises compensation (severance, talent) and marketing now, adds card balances, and pays back in productivity savings later (a counter-path).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [severance] `cit-c-invest-comp` | The investment program pulls forward severance and hires bankers and wealth advisors (Citi management) | investment pace; observable: compensation; severance disclosed by quarter | onset same quarter; build the program's years; persists temporary (severance) and lasting (hires); recognized operating expenses | guidance / guidance / unknown / guidance | slower hiring | compensation and benefits | unknown |
| 2 [marketing] `cit-c-invest-other` | Marketing in card, wealth and retail banking is a large share of the investment program (Citi management) | investment pace; observable: advertising and marketing expense | onset same quarter; build program years; persists while the program runs; recognized operating expenses | guidance / guidance / unknown / guidance | part of card investment runs through contra-revenue instead | other operating expense | unknown |
| 3 [payback] `cit-c-invest-productivity` | Counter-path: automation and severance pay back as lower run-rate costs; management cites a short payback on automated processes (relayed by a broker) (Citi management) | programs delivered; observable: run-rate savings (company statements) | onset 6-12 months; build years; persists lasting; recognized operating expenses | guidance / guidance / unknown / guidance | savings reinvested | productivity savings | unknown |
| 4 [cards] `cit-c-invest-loans` | Card acquisition marketing (part of the investment program) and portfolio purchases add balances (Citi USCC (marketing)) | acquisition offers convert; observable: new account acquisitions and card loans | onset 1-2 quarters; build several quarters; persists while marketing continues; recognized average balances | guidance / guidance / unknown / unknown | tightening when delinquencies rise (cit-c-delinq-loans) | USCC loans | unknown |
| 5 `cit-c-productivity-comp` | Productivity savings show mostly as lower compensation (a smaller negative) (Citi management) | savings not reinvested; observable: compensation; headcount | onset as realized; build years; persists lasting; recognized operating expenses | guidance / inferred / unknown / inferred | wage inflation | compensation and benefits | unknown |
| 6 `cit-c-loans-usccnii` | USCC NII is average card loans times the card NII yield (accounting) | revolving share holds; observable: USCC NII as a share of average loans | onset same quarter; build as promotional balances convert; persists while held; recognized interest income each quarter | documented / documented / inferred / documented | promotional (zero-rate) balances; transactors | USCC NII | +0.75 sd/sd (identity) |
| 7 `cit-a-exp-compensation-expense` | Citi compensation and benefits is one part of Citi operating expenses (operating expenses by type (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating expenses | +0.67 sd/sd (accounting) |
| 8 `cit-a-exp-other-operating-expense` | Citi other operating expense is the residual of Citi operating expenses: what the named parts leave out, stated in its basis (operating expenses by type (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating expenses | +0.67 sd/sd (accounting) |
| 9 `cit-a-uscc-uscc-nii` | Citi U.S. Consumer Cards net interest income is one part of Citi U.S. Consumer Cards revenue (U.S. Consumer Cards revenue by income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards revenue | +1.10 sd/sd (accounting) |
| 10 `cit-a-seg-uscc-revenue` | Citi U.S. Consumer Cards revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.23 sd/sd (accounting) |
| 11 `cit-a-pretax-operating-expenses` | Citi operating expenses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.68 sd/sd (accounting) |
| 12 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 13 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: balance growth per marketing dollar (not disclosed in reviewed sources); productivity savings by year (found not connected).

#### Citi Banamex separation and legacy exits

**Trigger:** Citi deconsolidates Banamex (its ownership falls below control). **Endpoint:** Citi CET1 ratio.

Citi ownership of Banamex → [revenue] Citi Mexico Consumer/SBMM revenue in pesos? → [rwa] Citi risk-weighted assets? → [cta_recycling] Citi revenue reconciling items? → [cta_release] Citi AOCI? → [stranded] Citi stranded costs? → Citi Mexico Consumer/SBMM (Banamex) revenue → Citi other operating expense? → Citi All Other revenue → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi operating expenses → Citi pretax income → Citi pretax income → Citi net income → Citi CET1 capital → Citi CET1 capital? → Citi CET1 ratio → Citi CET1 ratio  (? marks a step whose size is unknown)

Deconsolidation removes Banamex revenue and RWA, recycles the CTA through earnings as a divestiture-related loss while releasing it from AOCI (capital roughly unchanged), and leaves stranded costs until they are cut.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [revenue] `cit-c-banamex-mexico` | While Citi controls Banamex its revenue is consolidated in full; deconsolidation removes the line (an equity stake remains) (Citi management; buyers and IPO investors) | control held; observable: Mexico revenue; ownership share | onset at deconsolidation; build none; persists permanent; recognized from the deconsolidation date | guidance / guidance / unknown / guidance | separation delayed | Mexico revenue in pesos | unknown; acts only while Citi ownership of Banamex is above 50 |
| 2 [rwa] `cit-c-banamex-rwa` | Consolidated Banamex assets carry RWA; deconsolidation releases them (regulation) | control held; observable: RWA | onset at deconsolidation; build none; persists permanent; recognized quarter-end capital | inferred / inferred / unknown / guidance | retained stake still risk-weighted | risk-weighted assets | unknown; acts only while Citi ownership of Banamex is above 50 |
| 3 [cta_recycling] `cit-c-banamex-recon` | On deconsolidation the accumulated translation loss on Banamex is recycled through earnings as a divestiture-related loss (a reconciling item), lowering reported net income (accounting) | deconsolidation; observable: divestiture-related impacts in the quarter of deconsolidation | onset at deconsolidation; build none; persists one-time; recognized earnings in the quarter | guidance / guidance / unknown / guidance | a sale structure that keeps control | revenue reconciling items | unknown |
| 4 [cta_release] `cit-c-banamex-aoci` | Counter-path: the recycled translation loss leaves AOCI as it enters earnings, so CET1 capital is roughly unchanged (management expects it slightly accretive); the hit is to earnings, not capital (accounting) | deconsolidation; observable: AOCI and CET1 at deconsolidation | onset at deconsolidation; build none; persists one-time; recognized quarter-end capital | guidance / guidance / unknown / guidance | none | AOCI | unknown |
| 5 [stranded] `cit-c-banamex-stranded` | Exiting a franchise leaves shared costs behind until they are cut (stranded costs) (Citi management) | costs not yet removed; observable: Legacy Franchises expenses | onset at exit; build years; persists until removed; recognized operating expenses | guidance / inferred / unknown / inferred | cost actions at exit (transitional service agreements reimburse some) | stranded costs | unknown |
| 6 `cit-c-mxnrev-mexico` | Mexico revenue in dollars is peso revenue divided by USD/MXN (accounting) | same period; weight linearized at the construction levels | onset same period; build none; persists identity; recognized quarterly results | documented / documented / inferred / documented | unknown | Citi Mexico Consumer/SBMM (Banamex) revenue | +1.00 sd/sd (identity) |
| 7 `cit-c-stranded-other` | Shared costs that served exited consumer franchises remain until removed (Citi management) | exits closed but costs not yet cut; observable: Legacy Franchises expenses | onset as exits close; build years; persists until removed; recognized operating expenses | guidance / guidance / unknown / guidance | cost actions | other operating expense | unknown |
| 8 `cit-a-ao-mexico-consumer-revenue` | Citi Mexico Consumer/SBMM (Banamex) revenue is one part of Citi All Other revenue (All Other revenue by business, managed basis); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | All Other revenue | +0.56 sd/sd (accounting) |
| 9 `cit-a-seg-all-other-revenue` | Citi All Other revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 10 `cit-a-seg-reconciling-items-revenue` | Citi revenue reconciling items is the residual of Citi total revenues, net of interest expense: what the named parts leave out, stated in its basis (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.09 sd/sd (accounting) |
| 11 `cit-a-exp-other-operating-expense` | Citi other operating expense is the residual of Citi operating expenses: what the named parts leave out, stated in its basis (operating expenses by type (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating expenses | +0.67 sd/sd (accounting) |
| 12 `cit-a-pretax-operating-expenses` | Citi operating expenses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.68 sd/sd (accounting) |
| 13 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 14 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |
| 15 `cit-c-ni-cet1` | Retained earnings add to common equity and so to CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | +0.33 sd/sd (stock-flow, accumulates per 365 days) |
| 16 `cit-c-aoci-cet1` | AOCI is part of common equity and is not filtered out of CET1 for the largest banks, so a fall in AOCI lowers CET1 capital one for one (regulation) | AOCI included in CET1; observable: CET1 capital and AOCI, quarterly | onset immediate; build none; persists until marks reverse; recognized quarter-end capital | documented / documented / unknown / documented | a rule change filtering AOCI | CET1 capital | unknown |
| 17 `cit-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (accounting) | RWA unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | +1.36 sd/sd (identity) |
| 18 `cit-c-rwa-ratio` | More RWA at the same capital lowers the CET1 ratio (accounting) | capital unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | -1.31 sd/sd (identity) |

Unresolved inputs: separation steps and timing beyond the deconsolidation guide (not disclosed in reviewed sources).

#### Citi long-end yields to Treasury income and capital

**Trigger:** long-end Treasury yields rise. **Endpoint:** Citi CET1 ratio.

UST 10Y yield → [yield] Citi securities new-purchase yield? → [marks] Citi AOCI? → Citi investment securities yield? → Citi Corporate/Other revenue? → Citi All Other revenue → Citi total revenues, net of interest expense → Citi pretax income → Citi net income → Citi CET1 capital? → Citi CET1 capital → Citi CET1 ratio  (? marks a step whose size is unknown)

One move, two parallel responses: new purchases earn more (income builds over years) and AFS securities mark down into AOCI and CET1 at once.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [yield] `cit-c-ust10-npy` | Treasury buys securities at market yields, so a higher long-end yield raises the yield on new purchases (Citi Treasury (investment portfolio)) | purchases continue at the usual tenor mix; observable: yield on securities bought | onset same day; build none; persists while yields hold; recognized interest income as bought | documented / documented / unknown / inferred | a shorter tenor mix; purchases paused for liquidity | securities new-purchase yield | unknown |
| 2 [marks] `cit-c-ust10-aoci` | Higher long-end yields lower the market value of available-for-sale securities; the after-tax loss sits in AOCI, which counts in CET1 for this bank (market; regulation (AOCI in CET1)) | AFS duration after hedges; observable: AOCI each quarter | onset immediate; build none; persists pulls to par as securities mature; recognized quarter-end capital | documented / documented / unknown / documented | short AFS duration, swaps, HTM classification | AOCI | unknown |
| 3 `cit-c-npy-secyield` | The book yield blends in new purchases as old securities mature: the pickup is the gap between new and old yields times the share reinvested each year (Citi Treasury) | maturities reinvested; new yield above the book yield; observable: investment yield and income, quarterly | onset next quarter; build years, as the book turns over; persists until the book has turned over; recognized interest income each quarter | documented / documented / unknown / inferred | no maturities to reinvest; a new yield below the book yield | investment securities yield | unknown |
| 4 `cit-c-secyield-corpother` | Investment income in excess of the funds-transfer charges allocated to the businesses stays in Corporate/Other; a higher book yield raises it (Citi Treasury) | FTP charges to the businesses fixed in the short run; observable: Corporate/Other revenue, quarterly | onset same quarter; build years; persists while held; recognized interest income each quarter | documented / inferred / unknown / inferred | FTP passes the benefit to the businesses (then it shows in their NII) | Corporate/Other revenue | unknown |
| 5 `cit-a-ao-corporate-other-revenue` | Citi Corporate/Other revenue is the residual of Citi All Other revenue: what the named parts leave out, stated in its basis (All Other revenue by business, managed basis); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | All Other revenue | +0.50 sd/sd (accounting) |
| 6 `cit-a-seg-all-other-revenue` | Citi All Other revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 7 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 8 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |
| 9 `cit-c-aoci-cet1` | AOCI is part of common equity and is not filtered out of CET1 for the largest banks, so a fall in AOCI lowers CET1 capital one for one (regulation) | AOCI included in CET1; observable: CET1 capital and AOCI, quarterly | onset immediate; build none; persists until marks reverse; recognized quarter-end capital | documented / documented / unknown / documented | a rule change filtering AOCI | CET1 capital | unknown |
| 10 `cit-c-ni-cet1` | Retained earnings add to common equity and so to CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | +0.33 sd/sd (stock-flow, accumulates per 365 days) |
| 11 `cit-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (accounting) | RWA unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | +1.36 sd/sd (identity) |

Unresolved inputs: AFS duration and AOCI sensitivity per 100bp (disclosed not supplied); maturity ladder of the investment portfolio (disclosed not supplied).

#### Citi market levels to custody and wealth fees

**Trigger:** equity markets rise. **Endpoint:** Citi net income.

US equity market level → [custody] Citi assets under custody and administration? → [wealth] Citi Wealth client investment assets? → [prime] Citi Equity Markets revenue? → Citi Securities Services non-interest revenue? → Citi Private Bank revenue? → Citi Citigold and Retail Banking revenue? → Citi Wealth at Work revenue? → Citi Services non-interest revenue → Citi services revenue → Citi Wealth revenue → Citi Wealth revenue → Citi Wealth revenue → Citi markets revenue → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

Assets under custody and client investment assets mark up and earn fees; prime balances grow.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [custody] `cit-c-eq-auc` | Assets under custody and administration are valued at market, so they rise with equity prices (market) | the equity share of AUC/AUA; observable: AUC/AUA, quarterly | onset same day; build none; persists while prices hold; recognized quarter-end balances | documented / documented / unknown / documented | bond-price falls; client outflows | assets under custody | unknown |
| 2 [wealth] `cit-c-eq-clientassets` | Client investment assets are valued at market (market) | equity share of client assets; observable: client investment assets, quarterly | onset same day; build none; persists while prices hold; recognized quarter-end balances | documented / documented / unknown / documented | net outflows; a bond-heavy mix | Wealth client investment assets | unknown |
| 3 [prime] `cit-c-eq-equities` | Prime-brokerage balances and financing scale with equity levels, a growth area for Citi Markets (Citi Markets (prime services)) | clients keep leverage; observable: prime balances; Equity Markets revenue | onset same quarter; build several quarters; persists while levels hold; recognized fees and NII each quarter | documented / inferred / unknown / inferred | deleveraging in a sell-off | Equity Markets revenue | unknown |
| 4 `cit-c-auc-ssnir` | Custody and fund-administration fees are charged on assets held, so Securities Services fees rise with AUC/AUA (Citi Securities Services) | basis-point fee schedules; observable: Securities Services NIR against AUC/AUA | onset same quarter; build none; persists while assets hold; recognized fees each quarter | documented / documented / unknown / documented | fee compression; flat-fee mandates | Securities Services NIR | unknown |
| 5 `cit-c-clientassets-pb` | Advisory, managed-account and transaction fees in Private Bank scale with client investment assets (Citi Wealth) | fee-based share of client assets; observable: Private Bank revenue against client assets | onset same quarter; build none; persists while assets hold; recognized fees each quarter | documented / inferred / unknown / inferred | lower client activity; a move to deposits | Private Bank revenue | unknown |
| 6 `cit-c-clientassets-citigold` | Advisory, managed-account and transaction fees in Citigold and Retail Banking scale with client investment assets (Citi Wealth) | fee-based share of client assets; observable: Citigold and Retail Banking revenue against client assets | onset same quarter; build none; persists while assets hold; recognized fees each quarter | documented / inferred / unknown / inferred | lower client activity; a move to deposits | Citigold and Retail Banking revenue | unknown |
| 7 `cit-c-clientassets-waw` | Advisory, managed-account and transaction fees in Wealth at Work scale with client investment assets (Citi Wealth) | fee-based share of client assets; observable: Wealth at Work revenue against client assets | onset same quarter; build none; persists while assets hold; recognized fees each quarter | documented / inferred / unknown / inferred | lower client activity; a move to deposits | Wealth at Work revenue | unknown |
| 8 `cit-a-svcnir-ss-nir` | Citi Securities Services non-interest revenue is one part of Citi Services non-interest revenue (Services non-interest revenue by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Services non-interest revenue | +0.56 sd/sd (accounting) |
| 9 `cit-a-svc-services-nir` | Citi Services non-interest revenue is one part of Citi services revenue (Services revenue by business and income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | services revenue | +0.40 sd/sd (accounting) |
| 10 `cit-a-wealth-private-bank` | Citi Private Bank revenue is one part of Citi Wealth revenue (Wealth revenue by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Wealth revenue | +0.30 sd/sd (accounting) |
| 11 `cit-a-wealth-citigold-retail-banking` | Citi Citigold and Retail Banking revenue is one part of Citi Wealth revenue (Wealth revenue by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Wealth revenue | +0.67 sd/sd (accounting) |
| 12 `cit-a-wealth-wealth-at-work` | Citi Wealth at Work revenue is one part of Citi Wealth revenue (Wealth revenue by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Wealth revenue | +0.13 sd/sd (accounting) |
| 13 `cit-a-mkts-equity-markets` | Citi Equity Markets revenue is one part of Citi markets revenue (Markets revenue by product (incl. Markets NII)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | markets revenue | +0.34 sd/sd (accounting) |
| 14 `cit-a-seg-services-revenue` | Citi services revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 15 `cit-a-seg-wealth-revenue` | Citi Wealth revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.17 sd/sd (accounting) |
| 16 `cit-a-seg-markets-revenue` | Citi markets revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.43 sd/sd (accounting) |
| 17 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 18 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: equity share of AUC/AUA (not disclosed in reviewed sources); market-linked share of Wealth fees (not disclosed in reviewed sources).

#### Citi volatility to Markets revenue

**Trigger:** rate and FX volatility rises. **Endpoint:** Citi net income.

Rates and FX volatility → [rates_fx] Citi rates and currencies revenue? → [equities] Citi Equity Markets revenue? → [spreads] US high-yield credit spread? → [levels] US equity market level? → [capital] Citi risk-weighted assets? → Citi spread products revenue? → Citi Equity Markets revenue? → Citi Fixed Income Markets revenue → Citi Fixed Income Markets revenue → Citi markets revenue → Citi markets revenue → Citi compensation and benefits? → Citi operating expenses → Citi total revenues, net of interest expense → Citi pretax income → Citi pretax income → Citi net income → Citi CET1 ratio  (? marks a step whose size is unknown)

Volatility lifts rates and FX flow and equity derivatives, but the same shock widens credit spreads (inventory marks), lowers equity levels (prime balances) and raises market-risk RWA; incentive pay takes a share. s16 is the reduced form on Markets revenue and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [rates_fx] `cit-c-vol-ratesfx` | Rate and currency volatility makes clients hedge and reposition; FX is Citi's largest fixed income line and its corporate FX franchise earns on the flow (Citi's corporate and institutional clients; Citi Markets) | orderly markets (flow, not inventory losses); observable: rates and currencies revenue, quarterly | onset same quarter; build none; persists fades as volatility normalizes; recognized principal transactions daily | documented / documented / unknown / documented | disorderly markets turn flow into inventory losses | rates and currencies revenue | unknown |
| 2 [equities] `cit-c-vol-equities` | Volatility raises equity-derivatives hedging demand (Citi Markets (equity derivatives)) | orderly markets; observable: Equity Markets revenue, quarterly | onset same quarter; build none; persists fades; recognized principal transactions daily | documented / inferred / unknown / inferred | deleveraging cuts prime balances | Equity Markets revenue | unknown |
| 3 [spreads] `jpm-c-vol-spread` | A volatility shock (a forced deleveraging) widens credit spreads as investors demand more compensation for risk (credit investors) | the shock is broad rather than rates-only; observable: high-yield spread against volatility indices | onset days; build weeks; persists while risk-off lasts; recognized market prices | inferred / inferred / unknown / unknown | central-bank liquidity | US high-yield credit spread | unknown |
| 4 [levels] `jpm-c-vol-equityindex` | A volatility shock usually comes with falling equity prices (investors) | a risk-off shock rather than an upside repricing; observable: equity index against volatility | onset days; build weeks; persists while risk-off lasts; recognized market prices | inferred / inferred / unknown / unknown | volatility from a melt-up | US equity market level | unknown |
| 5 [capital] `cit-c-vol-rwa` | Market-risk RWA rise with volatility (value-at-risk and stressed measures) (regulation) | trading positions held; observable: market-risk RWA, quarterly | onset same quarter; build 60-day averaging; persists while volatility holds; recognized quarter-end capital | inferred / inferred / unknown / inferred | smaller positions | risk-weighted assets | unknown |
| 6 `cit-c-spread-spreadprod` | Wider credit spreads mark down credit and securitized inventory and slow new issuance flow (market; Citi Markets) | inventory held long; observable: spread products revenue, quarterly | onset same day; build none; persists until spreads retrace; recognized principal transactions daily | documented / documented / unknown / documented | hedged inventory; flow gains as clients reposition | spread products revenue | unknown |
| 7 `cit-c-eq-equities` | Prime-brokerage balances and financing scale with equity levels, a growth area for Citi Markets (Citi Markets (prime services)) | clients keep leverage; observable: prime balances; Equity Markets revenue | onset same quarter; build several quarters; persists while levels hold; recognized fees and NII each quarter | documented / inferred / unknown / inferred | deleveraging in a sell-off | Equity Markets revenue | unknown |
| 8 `cit-a-fi-rates-currencies` | Citi rates and currencies revenue is one part of Citi Fixed Income Markets revenue (Fixed Income Markets revenue by product); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Fixed Income Markets revenue | +0.69 sd/sd (accounting) |
| 9 `cit-a-fi-spread-products` | Citi spread products revenue is one part of Citi Fixed Income Markets revenue (Fixed Income Markets revenue by product); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Fixed Income Markets revenue | +0.45 sd/sd (accounting) |
| 10 `cit-a-mkts-fixed-income-markets` | Citi Fixed Income Markets revenue is one part of Citi markets revenue (Markets revenue by product (incl. Markets NII)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | markets revenue | +0.76 sd/sd (accounting) |
| 11 `cit-a-mkts-equity-markets` | Citi Equity Markets revenue is one part of Citi markets revenue (Markets revenue by product (incl. Markets NII)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | markets revenue | +0.34 sd/sd (accounting) |
| 12 `cit-c-markets-comp` | Counter-path: incentive compensation accrues with Markets revenue, so a share of any revenue gain is paid away (Citi (compensation committee)) | revenue-linked accrual; observable: compensation against Markets revenue | onset same quarter; build none; persists through the year-end bonus; recognized compensation expense | documented / inferred / unknown / inferred | a return-focused payout policy | compensation and benefits | unknown |
| 13 `cit-a-exp-compensation-expense` | Citi compensation and benefits is one part of Citi operating expenses (operating expenses by type (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating expenses | +0.67 sd/sd (accounting) |
| 14 `cit-a-seg-markets-revenue` | Citi markets revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.43 sd/sd (accounting) |
| 15 `cit-a-pretax-operating-expenses` | Citi operating expenses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.68 sd/sd (accounting) |
| 16 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 17 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |
| 18 `cit-c-rwa-ratio` | More RWA at the same capital lowers the CET1 ratio (accounting) | capital unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | -1.31 sd/sd (identity) |

Unresolved inputs: Markets revenue sensitivity to volatility (not disclosed in reviewed sources); compensation ratio of Markets (not disclosed in reviewed sources).

#### Citi peso to Banamex revenue and capital

**Trigger:** the peso weakens (USD/MXN rises). **Endpoint:** Citi CET1 ratio.

USD/MXN → [revenue] Citi Mexico Consumer/SBMM (Banamex) revenue → [cta] Citi AOCI? → Citi All Other revenue → Citi total revenues, net of interest expense → Citi pretax income → Citi net income → Citi CET1 capital? → Citi CET1 capital → Citi CET1 ratio  (? marks a step whose size is unknown)

Peso revenue translates into fewer dollars and the Banamex CTA deepens.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [revenue] `cit-c-mxn-mexico` | Banamex earns in pesos; a weaker peso (higher USD/MXN) lowers its revenue in dollars one for one (accounting (translation)) | consolidated while control is held; observable: Mexico revenue and the peso, quarterly | onset same quarter; build none; persists while the rate holds; recognized each quarter at average rates | documented / documented / inferred / documented | deconsolidation of Banamex | Mexico Consumer/SBMM revenue | -0.75 sd/sd (identity) |
| 2 [cta] `cit-c-mxn-aoci` | A weaker peso lowers the dollar value of the Banamex net investment; the unrealized loss sits in the CTA (in AOCI) (accounting) | net investment not hedged; observable: CTA in AOCI | onset immediate; build none; persists until the CTA is recycled; recognized quarter-end capital | documented / documented / unknown / documented | net-investment hedges; deconsolidation recycles the CTA | AOCI | unknown |
| 3 `cit-a-ao-mexico-consumer-revenue` | Citi Mexico Consumer/SBMM (Banamex) revenue is one part of Citi All Other revenue (All Other revenue by business, managed basis); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | All Other revenue | +0.56 sd/sd (accounting) |
| 4 `cit-a-seg-all-other-revenue` | Citi All Other revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 5 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 6 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |
| 7 `cit-c-aoci-cet1` | AOCI is part of common equity and is not filtered out of CET1 for the largest banks, so a fall in AOCI lowers CET1 capital one for one (regulation) | AOCI included in CET1; observable: CET1 capital and AOCI, quarterly | onset immediate; build none; persists until marks reverse; recognized quarter-end capital | documented / documented / unknown / documented | a rule change filtering AOCI | CET1 capital | unknown |
| 8 `cit-c-ni-cet1` | Retained earnings add to common equity and so to CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | +0.33 sd/sd (stock-flow, accumulates per 365 days) |
| 9 `cit-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over RWA (accounting) | RWA unchanged; observable: CET1 ratio | onset same quarter; build none; persists identity; recognized quarter-end capital | documented / documented / inferred / documented | none (an identity) | CET1 ratio | +1.36 sd/sd (identity) |

#### Citi non-USD short rates to Services NII

**Trigger:** non-USD policy rates rise (the ECB as the largest leg; the BoJ and PBoC links feed the same basket). **Endpoint:** Citi net income.

ECB deposit rate → Citi non-USD short-rate basket? → [tts] Citi TTS net interest income? → [custody] Citi Securities Services net interest income? → [funding] Citi interest-bearing deposit cost? → Citi TTS net interest income? → Citi Services net interest income → Citi Services net interest income → Citi services revenue → Citi total revenues, net of interest expense → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

Parallel responses of one move in Citi's non-USD rate basket: the TTS and Securities Services deposit spreads widen, and non-USD deposit costs follow at a low beta. cit-c-nonusd-nii (calibrated from the disclosed all-currency sensitivity) is the reduced form on firm NII and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `cit-c-ecb-basket` | A move in the ECB deposit rate (euro, the largest non-USD leg) moves the short rate earned on Citi's deposits and placements in that currency, one leg of the non-USD basket (central bank; Citi Treasury (local placements)) | Citi holds deposits in that currency; the basket weight is that currency's share of non-USD balances; observable: local policy and interbank rates; Citi's non-USD rate disclosures (none by currency in the sources read) | onset same day; build none; persists while the policy rate holds; recognized interest income each quarter | documented / inferred / unknown / inferred | a small weight for that currency; other currencies (Latin America, other Asia) move the basket too and are not represented | non-USD short-rate basket | unknown |
| 2 [tts] `cit-c-basket-ttsnii` | Treasury and Trade Solutions holds large operating deposits in many currencies at low betas; when local short rates rise, the spread earned on them widens and TTS NII rises (the company describes its rate sensitivity as mainly non-USD, driven by Services) (Citi TTS (deposit pricing) and its corporate clients) | operating balances are sticky and priced at low betas; the currency is one where Citi has deposits; observable: TTS NII and Services average deposits, quarterly | onset within the quarter; build 1-2 quarters as placements reprice; persists while local rates hold; recognized interest income each quarter | documented / documented / unknown / inferred | local deposit competition raises betas; balance outflows; currency controls; a cut reverses it (and the disclosed down-move sensitivity is larger than the up-move) | TTS NII | unknown |
| 3 [custody] `cit-c-basket-ssnii` | Custody clients leave cash balances in many currencies; a higher local short rate raises the spread earned on them (Securities Services and its custody clients) | client cash held with Citi, priced at low betas; observable: Securities Services NII, quarterly | onset within the quarter; build 1-2 quarters; persists while rates hold; recognized interest income each quarter | documented / inferred / unknown / inferred | clients sweep cash into money funds; betas rise | Securities Services NII | unknown |
| 4 [funding] `cit-c-basket-depcost` | Interest-bearing non-USD deposits reprice by a fraction of the local rate move (a low beta), raising the firmwide deposit cost and offsetting part of the spread gain (Citi deposit pricing (Services, Wealth outside the US)) | interest-bearing share of non-USD balances; observable: interest-bearing deposit cost, quarterly | onset within the quarter; build 2-4 quarters; persists while rates hold; recognized interest expense each quarter | documented / documented / unknown / inferred | operating balances that pay little or nothing | interest-bearing deposit cost | unknown |
| 5 `cit-c-depcost-ttsnii` | A higher deposit cost narrows the spread TTS earns on its interest-bearing operating deposits (Citi TTS) | interest-bearing share of TTS deposits; observable: TTS NII against deposit cost | onset same quarter; build none; persists while the cost holds; recognized interest income each quarter | documented / documented / unknown / documented | a growing noninterest-bearing share | TTS NII | unknown |
| 6 `cit-a-svcnii-tts-nii` | Citi TTS net interest income is one part of Citi Services net interest income (Services NII by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Services net interest income | +0.81 sd/sd (accounting) |
| 7 `cit-a-svcnii-ss-nii` | Citi Securities Services net interest income is one part of Citi Services net interest income (Services NII by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Services net interest income | +0.26 sd/sd (accounting) |
| 8 `cit-a-svc-services-nii` | Citi Services net interest income is one part of Citi services revenue (Services revenue by business and income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | services revenue | +0.67 sd/sd (accounting) |
| 9 `cit-a-seg-services-revenue` | Citi services revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 10 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 11 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: Securities Services NII sensitivity to non-USD rates (not disclosed in reviewed sources); TTS NII sensitivity to non-USD rates (not disclosed in reviewed sources); currency weights of non-USD deposits and NII (not disclosed in reviewed sources); deposit beta (non-USD) (not disclosed in reviewed sources); non-USD share of Services deposits (not disclosed in reviewed sources).

#### Citi securities reinvestment

**Trigger:** securities mature while new-purchase yields differ from the book yield. **Endpoint:** Citi CET1 capital.

Citi securities maturities → Citi securities purchases? → Citi investment securities yield? → Citi Corporate/Other revenue? → Citi All Other revenue → Citi total revenues, net of interest expense → Citi pretax income → Citi net income → Citi CET1 capital  (? marks a step whose size is unknown)

Existing securities -> cash released -> Treasury's reinvestment decision -> book yield -> Corporate/Other revenue -> All Other -> revenue -> earnings -> capital. The maturity ladder is not disclosed, so no new yield is applied to the whole book.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `cit-c-maturities-purchases` | Maturing securities release cash that Treasury reinvests (or holds as cash at the central bank, or lends) (Citi Treasury) | loan demand below deposit growth; liquidity rules favour high-quality assets; observable: proceeds from maturities against purchases (cash flow statement) | onset same quarter; build none; persists while held; recognized cash flow statement | documented / inferred / unknown / inferred | cash kept at the central bank or lent instead | securities purchases | unknown |
| 2 `cit-c-purchases-secyield` | More purchases at a new yield above the book yield raise the book yield faster (Citi Treasury) | new-purchase yield above the book yield; observable: investment yield, quarterly | onset next quarter; build years; persists while held; recognized interest income each quarter | documented / inferred / unknown / inferred | new yield below the book yield turns the sign | investment securities yield | unknown; sign as stated while Citi securities new-purchase yield is above 3.7, reversed otherwise |
| 3 `cit-c-secyield-corpother` | Investment income in excess of the funds-transfer charges allocated to the businesses stays in Corporate/Other; a higher book yield raises it (Citi Treasury) | FTP charges to the businesses fixed in the short run; observable: Corporate/Other revenue, quarterly | onset same quarter; build years; persists while held; recognized interest income each quarter | documented / inferred / unknown / inferred | FTP passes the benefit to the businesses (then it shows in their NII) | Corporate/Other revenue | unknown |
| 4 `cit-a-ao-corporate-other-revenue` | Citi Corporate/Other revenue is the residual of Citi All Other revenue: what the named parts leave out, stated in its basis (All Other revenue by business, managed basis); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | All Other revenue | +0.50 sd/sd (accounting) |
| 5 `cit-a-seg-all-other-revenue` | Citi All Other revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 6 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 7 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |
| 8 `cit-c-ni-cet1` | Retained earnings add to common equity and so to CET1 capital (accounting; regulation) | the flow occurs in the period; observable: CET1 roll-forward, quarterly | onset same quarter; build none; persists accumulates; recognized quarter-end capital | documented / documented / inferred / documented | other CET1 items (goodwill, other deductions) | CET1 capital | +0.33 sd/sd (stock-flow, accumulates per 365 days) |

#### Citi transformation spending to expenses

**Trigger:** transformation spending changes (programs reach target state). **Endpoint:** Citi net income.

Citi transformation spending → [technology] Citi technology and communication expense? → [consultants] Citi other operating expense? → Citi operating expenses → Citi operating expenses → Citi efficiency ratio → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

About half of transformation spending is temporary; as programs complete it falls away from technology and professional-services costs.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [technology] `cit-c-transform-tech` | Transformation work (risk and control infrastructure, data, regulatory reporting) is mostly technology spend; as programs reach target state, the temporary half falls away (Citi management; regulators (consent orders)) | program completion; regulators' review; observable: technology expense; transformation spend | onset same quarter; build programs run for years; persists a temporary part falls away as programs complete; recognized operating expenses | guidance / guidance / unknown / guidance | regulators require more work before closing the consent orders | technology expense | unknown |
| 2 [consultants] `cit-c-transform-other` | Part of transformation spending is professional services (Citi management) | program phase; observable: professional services expense | onset same quarter; build years; persists temporary; recognized operating expenses | inferred / inferred / unknown / inferred | insourcing | other operating expense | unknown |
| 3 `cit-a-exp-technology-expense` | Citi technology and communication expense is one part of Citi operating expenses (operating expenses by type (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating expenses | +0.33 sd/sd (accounting) |
| 4 `cit-a-exp-other-operating-expense` | Citi other operating expense is the residual of Citi operating expenses: what the named parts leave out, stated in its basis (operating expenses by type (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating expenses | +0.67 sd/sd (accounting) |
| 5 `cit-c-opex-effratio` | The efficiency ratio is operating expenses over revenue: a larger (more negative) expense raises it (accounting) | revenue unchanged; observable: efficiency ratio (the guided measure) | onset same quarter; build none; persists identity; recognized quarterly results | documented / documented / inferred / documented | none (an identity) | efficiency ratio | -1.16 sd/sd (identity) |
| 6 `cit-a-pretax-operating-expenses` | Citi operating expenses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.68 sd/sd (accounting) |
| 7 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: transformation spend by expense line (not disclosed in reviewed sources).

#### Citi policy rate to the segment cells

**Trigger:** the Fed raises the policy rate. **Endpoint:** Citi net income.

Fed funds rate (midpoint) → [beta] Citi interest-bearing deposit cost? → [tts_spread] Citi TTS net interest income? → [wealth_spread] Citi Citigold and Retail Banking revenue? → [loans] Citi loan yield? → [cards] Citi U.S. card NII yield? → [treasury] Citi Corporate/Other revenue? → [markets] Citi Markets net interest income? → [markets_offset] Citi non-interest revenue? → Citi TTS net interest income? → Citi Citigold and Retail Banking revenue? → Citi Corporate Lending revenue? → Citi Services net interest income → Citi services revenue → Citi Wealth revenue → Citi Banking revenue → Citi U.S. Consumer Cards net interest income → Citi U.S. Consumer Cards revenue → Citi All Other revenue → Citi net interest income → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi total revenues, net of interest expense → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

Parallel responses of one Fed move: USD deposit spreads widen in TTS and Wealth while deposit costs catch up by the beta (the company calls its USD book roughly neutral within twelve months), floating loans and card APRs reprice, Treasury cash earns more, and Markets NII falls while the desks earn it back in principal transactions (a counter-path that moves NII and NII ex-Markets apart, not revenue). m26 is the reduced form on firm NII and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [beta] `cit-c-fed-depcost` | Citi reprices interest-bearing USD deposits by a fraction of a policy-rate move (the deposit beta); its deposits are mostly large corporate and wealth balances (a high uninsured share), so the beta is above a retail bank's (Citi deposit pricing (Services, Wealth)) | deposit competition and Citi's funding needs; the corporate and wealth mix; observable: interest-bearing deposit cost against the fed funds rate, quarterly | onset within the quarter; build 2-4 quarters to the cumulative beta; persists while the policy rate holds; recognized interest expense each quarter | documented / documented / unknown / broker | excess liquidity holds betas down; a deposit contest or quantitative tightening pushes them up; caps at the policy rate | interest-bearing deposit cost | unknown |
| 2 [tts_spread] `cit-c-fed-ttsnii` | USD operating deposits fund short-duration assets that reprice with the policy rate, widening the spread; within twelve months the deposit-cost catch-up offsets it (the company calls its USD book roughly neutral in year one, asset-sensitive in year two) (Citi TTS and Treasury) | short-duration assets against USD operating deposits; observable: TTS NII and USD deposit cost, quarterly | onset within the quarter; build year two as hedges roll off; persists while the rate holds; recognized interest income each quarter | documented / documented / unknown / guidance | the deposit-cost catch-up (cit-c-fed-depcost, cit-c-depcost-ttsnii) roughly offsets it within twelve months | TTS NII | unknown |
| 3 [wealth_spread] `cit-c-fed-citigold` | Wealth deposits are credited at market rates through funds transfer pricing while paying a sub-one beta, so a higher policy rate widens their spread (Citi Wealth) | deposit beta below one; observable: Wealth NII and deposits, quarterly | onset within the quarter; build 1-2 quarters; persists while the rate holds; recognized interest income each quarter | documented / documented / unknown / inferred | deposit competition in Wealth (cit-c-depcost-citigold) | Citigold and Retail Banking revenue | unknown |
| 4 [loans] `cit-c-fed-loanyield` | Much of Citi's loan book floats (corporate on SOFR, cards on prime) and reprices within weeks; fixed-rate loans reprice only as they are made (Citi lending (Banking, USCC, Wealth)) | the floating share of loans and any receive-fixed swaps; observable: loan yield against SOFR and prime, quarterly | onset within the month; build one reset cycle; persists while the rate holds; recognized interest income each quarter | documented / documented / unknown / inferred | receive-fixed swaps; loan-spread competition | loan yield | unknown |
| 5 [cards] `cit-c-fed-usccnii` | Card APRs float with the prime rate and reprice within a billing cycle, while card funding reprices at the deposit beta, so a hike adds modestly to card NII (Citi USCC) | prime-linked APRs; promotional balances at fixed rates; observable: USCC NII as a share of average loans, quarterly | onset within a billing cycle; build 1 quarter; persists while the rate holds; recognized interest income each quarter | documented / inferred / unknown / inferred | promotional and fixed-rate balances; APR caps; higher revolver losses at high rates | USCC NII yield | unknown |
| 6 [treasury] `cit-c-fed-corpother` | Treasury holds a large cash balance with central banks earning the policy rate, and keeps the residual of funds-transfer pricing; a higher rate raises that income before hedges (Citi Treasury and ALM) | cash balances not invested; hedges of the residual position; observable: deposits with banks: balance and yield; Corporate/Other revenue | onset same day; build none; persists while the rate holds; recognized interest income each quarter | documented / inferred / unknown / inferred | receive-fixed hedges and FTP allocation can reverse the sign of the residual | Corporate/Other revenue | unknown |
| 7 [markets] `cit-c-fed-mktsnii` | Counter-path: repo and other Markets funding reprices at money-market rates, so Markets NII falls when the policy rate rises; the desks earn it back in principal transactions, so Markets revenue is managed as a whole and roughly unchanged (Citi Markets (financing desks)) | inventory funded short; trades priced on funding; observable: Markets NII (memo line) and firm NII less NII ex-Markets | onset within weeks; build none; persists while the rate holds; recognized quarterly results | documented / inferred / unknown / inferred | a funding shock the desks cannot pass on | Markets NII | unknown |
| 8 [markets_offset] `cit-c-fed-nir-offset` | Counter-path to cit-c-fed-mktsnii: the Markets desks price funding into client trades, so the lost Markets NII returns in principal transactions (non-interest revenue); total revenue is roughly unchanged while NII and NII ex-Markets diverge (Citi Markets) | Markets revenue managed as NII plus NIR; observable: principal transactions against Markets NII | onset within weeks; build none; persists while the rate holds; recognized quarterly results | documented / inferred / unknown / inferred | a disorderly market in which the desks cannot reprice | non-interest revenue | unknown |
| 9 `cit-c-depcost-ttsnii` | A higher deposit cost narrows the spread TTS earns on its interest-bearing operating deposits (Citi TTS) | interest-bearing share of TTS deposits; observable: TTS NII against deposit cost | onset same quarter; build none; persists while the cost holds; recognized interest income each quarter | documented / documented / unknown / documented | a growing noninterest-bearing share | TTS NII | unknown |
| 10 `cit-c-depcost-citigold` | A higher deposit cost narrows the spread on Citigold and retail deposits (deposit competition in Wealth is high) (Citi Wealth (deposit pricing)) | interest-bearing share of wealth deposits; observable: Wealth NII and average deposits, quarterly | onset same quarter; build 2-4 quarters; persists while the cost holds; recognized interest income each quarter | documented / documented / unknown / inferred | a shift into noninterest-bearing balances | Citigold and Retail Banking revenue | unknown |
| 11 `cit-c-loanyield-corplending` | Corporate Lending earns loan balances times the loan spread; a higher floating loan yield raises its NII before funding (Citi Banking (Corporate Lending)) | funds-transfer charge rises by less than the loan yield; observable: Corporate Lending revenue and Banking NII, quarterly | onset same quarter; build none; persists while the yield holds; recognized interest income each quarter | documented / inferred / unknown / inferred | funds-transfer pricing passes most of the rate to funding; loan balances shrink | Corporate Lending revenue | unknown |
| 12 `cit-a-svcnii-tts-nii` | Citi TTS net interest income is one part of Citi Services net interest income (Services NII by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Services net interest income | +0.81 sd/sd (accounting) |
| 13 `cit-a-svc-services-nii` | Citi Services net interest income is one part of Citi services revenue (Services revenue by business and income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | services revenue | +0.67 sd/sd (accounting) |
| 14 `cit-a-wealth-citigold-retail-banking` | Citi Citigold and Retail Banking revenue is one part of Citi Wealth revenue (Wealth revenue by business); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Wealth revenue | +0.67 sd/sd (accounting) |
| 15 `cit-a-bank-corporate-lending-revenue` | Citi Corporate Lending revenue is one part of Citi Banking revenue (Banking revenue by business, incl. gain or loss on loan hedges); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Banking revenue | +0.29 sd/sd (accounting) |
| 16 `cit-c-yield-usccnii` | USCC NII is average card loans times the card NII yield (accounting) | same period; weight linearized at the construction levels | onset same period; build none; persists identity; recognized quarterly results | documented / documented / inferred / documented | unknown | Citi U.S. Consumer Cards net interest income | +0.60 sd/sd (identity) |
| 17 `cit-a-uscc-uscc-nii` | Citi U.S. Consumer Cards net interest income is one part of Citi U.S. Consumer Cards revenue (U.S. Consumer Cards revenue by income type); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | U.S. Consumer Cards revenue | +1.10 sd/sd (accounting) |
| 18 `cit-a-ao-corporate-other-revenue` | Citi Corporate/Other revenue is the residual of Citi All Other revenue: what the named parts leave out, stated in its basis (All Other revenue by business, managed basis); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | All Other revenue | +0.50 sd/sd (accounting) |
| 19 `cit-a-mx-markets-nii-col` | Citi Markets net interest income is a cell of the revenue matrix (cit.mx.revenue) in Citi net interest income | same basis, period and currency (USD) | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net interest income | +0.47 sd/sd (accounting) |
| 20 `cit-a-seg-services-revenue` | Citi services revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 21 `cit-a-seg-wealth-revenue` | Citi Wealth revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.17 sd/sd (accounting) |
| 22 `cit-a-seg-banking-revenue` | Citi Banking revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.16 sd/sd (accounting) |
| 23 `cit-a-seg-uscc-revenue` | Citi U.S. Consumer Cards revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.23 sd/sd (accounting) |
| 24 `cit-a-seg-all-other-revenue` | Citi All Other revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.29 sd/sd (accounting) |
| 25 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 26 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: Citi deposit beta (not disclosed in reviewed sources); Markets NII rate sensitivity (not disclosed in reviewed sources); Treasury residual rate position (not disclosed in reviewed sources); USCC NII sensitivity to rates (not disclosed in reviewed sources); USD-only NII sensitivity (disclosed not supplied); Wealth NII rate sensitivity (not disclosed in reviewed sources); floating share of loans (found connected); swap hedges of the loan book (not disclosed in reviewed sources); uninsured share of deposits (found connected).

#### Citi credit spreads to Banking and Markets

**Trigger:** corporate credit spreads widen. **Endpoint:** Citi net income.

US high-yield credit spread → [hedges] Citi gain or loss on loan hedges? → [reserves] Citi Banking provision? → [pricing] Citi Corporate Lending revenue? → [inventory] Citi spread products revenue? → Citi Banking revenue → Citi Banking revenue → Citi total revenues, net of interest expense → Citi Fixed Income Markets revenue → Citi markets revenue → Citi total revenues, net of interest expense → Citi provisions for credit losses → Citi pretax income → Citi pretax income → Citi net income  (? marks a step whose size is unknown)

One move, four parallel responses: CDS loan hedges gain at once, wholesale reserves build, loan spreads reprice at renewal, and credit inventory marks down. The hedge gain and the provision are a gross effect and its offset, both kept.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [hedges] `cit-c-spread-hedges` | Counter-path: Citi hedges its corporate loan book with credit-default swaps marked to market; wider spreads produce hedge gains now, while the provision for the same loans comes later (Citi Banking (loan portfolio management)) | hedge notional in place; observable: gain or loss on loan hedges, quarterly | onset same day; build none; persists until spreads retrace; recognized revenue each quarter | documented / documented / unknown / documented | hedges rolled off; basis between CDS and loans | gain or loss on loan hedges | unknown |
| 2 [reserves] `cit-c-spread-bankprov` | Wider credit spreads signal a weaker corporate outlook; CECL reserves for corporate loans and commitments build (a larger negative provision), and downgrades follow (Citi risk management (CECL)) | spreads widen on fundamentals, not technicals; observable: Banking provisions, quarterly | onset same quarter; build 1-2 quarters; persists until the outlook improves; recognized provision each quarter | documented / inferred / unknown / inferred | investment-grade book; hedges (cit-c-spread-hedges) | Banking provision | unknown |
| 3 [pricing] `cit-c-spread-corplending` | Corporate loans reprice to wider market spreads as they are renewed (Citi Banking) | loans reach renewal; observable: Corporate Lending revenue | onset at renewal; build 2-3 years; persists while spreads hold; recognized interest income each quarter | inferred / inferred / unknown / inferred | clients refinance in bond markets | Corporate Lending revenue | unknown |
| 4 [inventory] `cit-c-spread-spreadprod` | Wider credit spreads mark down credit and securitized inventory and slow new issuance flow (market; Citi Markets) | inventory held long; observable: spread products revenue, quarterly | onset same day; build none; persists until spreads retrace; recognized principal transactions daily | documented / documented / unknown / documented | hedged inventory; flow gains as clients reposition | spread products revenue | unknown |
| 5 `cit-a-bank-loan-hedges` | Citi gain or loss on loan hedges is one part of Citi Banking revenue (Banking revenue by business, incl. gain or loss on loan hedges); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Banking revenue | +0.27 sd/sd (accounting) |
| 6 `cit-a-bank-corporate-lending-revenue` | Citi Corporate Lending revenue is one part of Citi Banking revenue (Banking revenue by business, incl. gain or loss on loan hedges); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Banking revenue | +0.29 sd/sd (accounting) |
| 7 `cit-a-seg-banking-revenue` | Citi Banking revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.16 sd/sd (accounting) |
| 8 `cit-a-fi-spread-products` | Citi spread products revenue is one part of Citi Fixed Income Markets revenue (Fixed Income Markets revenue by product); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Fixed Income Markets revenue | +0.45 sd/sd (accounting) |
| 9 `cit-a-mkts-fixed-income-markets` | Citi Fixed Income Markets revenue is one part of Citi markets revenue (Markets revenue by product (incl. Markets NII)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | markets revenue | +0.76 sd/sd (accounting) |
| 10 `cit-a-seg-markets-revenue` | Citi markets revenue is one part of Citi total revenues, net of interest expense (total revenues, net of interest expense, by reporting segment (managed) plus reconciling items); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total revenues, net of interest expense | +0.43 sd/sd (accounting) |
| 11 `cit-a-prov-banking-provision` | Citi Banking provision is one part of Citi provisions for credit losses (provisions by segment (negative values)); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | provisions for credit losses | +0.25 sd/sd (accounting) |
| 12 `cit-a-pretax-provision-for-credit-losses` | Citi provisions for credit losses is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +0.55 sd/sd (accounting) |
| 13 `cit-a-pretax-net-revenue` | Citi total revenues, net of interest expense is one part of Citi pretax income (pretax income: revenue less operating expenses less provisions); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income | +1.56 sd/sd (accounting) |
| 14 `cit-a-ni-pretax-income` | Citi pretax income is one part of Citi net income (net income: pretax income less tax, noncontrolling interests and discontinued operations); weight is its scale over the total's | same basis, period and currency (USD); never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.33 sd/sd (accounting) |

Unresolved inputs: loan hedge notional and spread sensitivity (not disclosed in reviewed sources); wholesale CECL sensitivity (not disclosed in reviewed sources).

## Validation

`tests/scenario/test_construction_citigroup.py` (31 tests, incl. `test_one_driving_view_per_total` and
`test_identities_and_the_capital_stock_flow_hold_with_derived_weights` from the conversion; Sally's world loads once; no client data is read):

| Test | What it shows |
|---|---|
| `test_no_construction_problems_for_citigroup` | `validate_construction` and the view report no problem |
| `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links`, `test_priors_reconcile_within_half_a_percent` | the 20 views exist with their totals, residuals where the business has them, one unit per view, fixed accounting weights (part sd over total sd), and priors that add up |
| `test_views_of_net_revenue_are_never_added` | the segment, type and regions views share no part; no segment cell sits in the type or regions view |
| `test_required_paths_exist`, `test_every_path_step_has_a_transition_and_every_uncalibrated_step_a_sign` | 19 paths, one or more per piece of Citi's economics; every step a transition; every uncalibrated step a sign and no claimed size |
| `test_shared_driver_responses_are_parallel_branches`, `test_reduced_forms_are_never_steps_of_their_structural_paths` | one driver's effects are branches (Fed, 10Y, credit spreads, the dollar, the non-USD basket); m26, `cit-c-nonusd-nii`, s16 and s19 are never steps of their paths |
| `test_values_name_their_basis`, `test_segments_follow_the_recast_perimeter`, `test_nii_ex_markets_is_its_own_view_of_firm_nii` | bases on every value; the recast perimeter; the guided KPI as its own view with the Markets NII offset |
| `test_non_usd_rates_reach_services_nii_and_the_reduced_form_is_calibrated_from_the_disclosure`, `test_usd_book_nets_out_within_the_year` | the non-USD path and its calibrated reduced form (a percent or two of NII per 100bp, built over the year); the USD branches that offset, and m26 scoped |
| `test_marks_reach_capital_not_income`, `test_loan_hedges_offset_wholesale_provisions`, `test_card_fees_are_net_of_rewards_and_partner_payments`, `test_two_credit_clocks` | AFS marks reach CET1, never earnings; hedge gains against provisions; interchange net of rewards and partner loss-sharing; CECL now, losses after delinquency, underwriting feedback |
| `test_translation_hits_revenue_expenses_and_capital`, `test_expense_program_has_a_payback_counter_path`, `test_capital_is_a_stock_with_flows_not_an_additive_view`, `test_banamex_exit_hits_earnings_not_capital` | the dollar enters revenue through the regions view and Mexico only, with the expense, CTA and RWA counter-paths; investment and its payback; capital as stock and flows; the CTA recycled to earnings and released from AOCI |
| `test_only_evidenced_links_carry_new_sizes`, `test_existing_records_keep_their_sizes_and_are_scoped`, `test_missing_inputs_say_whether_the_material_was_searched`, `test_conversion_tags_name_the_missing_link_forms` | one new size, from the disclosure; m26, s16, s19, s25, s26 unchanged; every missing input searched; the tags in place |
| `test_generalization_trace_an_oil_shock` | an oil shock, which no Citi path was written for, reaches Citi's endpoints (below) |
| `test_new_objects_reach_the_export`, `test_new_objects_reach_the_api` | the compositions in `financial_bridge`, the paths in `transmission_paths`, transitions in the relationships; `/query`, `…/entities/citigroup/construction` and its traces |

Checks run: `check.py sally_demo --entities citigroup` (no problems; with `--sources`: 12 source ids resolve, 0 do not;
157 links and 82 values cited; 0 material claims without a citation; inputs: 0 not yet reviewed); `--reconcile
--statistic median` and `--reconcile --baselines` (0 flags); `bundles.py check` on the local baselines (schema, ids and
quotes clean; 10 observations held back by the overlap rule, G22); the Toyota, Tokio Marine, JPMorgan and Sally
expected-paths tests and `tests/unit tests/ingest tests/lake` pass; ruff clean.

## Completion report

This is the first build's report (before the conversion); [the conversion section](#conversion-oct-18-one-driving-view-per-total-identities-a-stock-flow-states)
gives the current counts, reconciliation and coverage.

### Gaps

| # | Outcome | What a downstream agent can now do, or what blocks it |
|---|---|---|
| G01 | built and verified | follow any change into the segment cell it hits, up to revenue, pretax and net income; segment net income as a reported view |
| G02 | built and verified | read every value's view, basis and metric; NII ex-Markets is a separate view of firm NII |
| G03 | built and verified | segments on the recast perimeter; USPB named only as the former perimeter |
| G04 | built but uncalibrated | m26 keeps its size as an assumption and says why it may overstate; the USD branches carry signs only. Blocked by: USD-only NII sensitivity (not disclosed in reviewed sources) |
| G05 | built and verified (reduced form); steps uncalibrated | `cit-c-nonusd-nii` calibrated from the disclosed sensitivity; the ECB/BoJ/PBoC → basket legs and the TTS and Securities Services cells have signs only. Blocked by: currency weights, TTS NII sensitivity, non-USD share of Services deposits (not disclosed) |
| G06 | built but uncalibrated | Blocked by: Citi deposit beta, Wealth and USCC NII rate sensitivity, Treasury position (not disclosed); floating share and uninsured share found and cited |
| G07 | built but uncalibrated | Blocked by: maturity ladder, AFS duration and AOCI sensitivity (not disclosed) |
| G08 | built but uncalibrated; s19 scoped | Blocked by: cross-border volume elasticity, TTS fee rate, deposit growth elasticity (not disclosed) |
| G09 | built but uncalibrated; s16 scoped | Blocked by: Markets revenue sensitivity to volatility, Markets compensation ratio (not disclosed) |
| G10 | built but uncalibrated | Blocked by: IB fee sensitivity, loan-hedge notional, wholesale CECL sensitivity (not disclosed) |
| G11 | built but uncalibrated | Blocked by: equity share of custody assets, market-linked share of Wealth fees (not disclosed; the client model's own assumption is not used) |
| G12 | built but uncalibrated | the rewards rate is found and bound (its two lines are baselines); the products (spend times rates) await the identity form. Blocked by: partner loss-sharing terms (not disclosed) |
| G13 | built but uncalibrated | Blocked by: reserve and loss sensitivity to unemployment, roll rates (not disclosed; the reserve scenario level is found and cited) |
| G14 | built but uncalibrated | Blocked by: currency mix of international revenue, CET1 sensitivity to a USD move (not disclosed); translation itself awaits the ratio identity |
| G15 | built but uncalibrated | program sizes are found as guidance (cited; productivity savings found, not connected). Blocked by: transformation spend by expense line (not disclosed) |
| G16 | built but uncalibrated | the requirement path and target are found and cited; the roll-forward awaits the stock-flow form. DTA schedule found, not connected |
| G17 | built but uncalibrated | the CTA size and timing are guidance (cited, in local estimates); deconsolidation is a one-time event the method has no form for |
| G18 | built and verified | All Other and its businesses reconcile at the priors and at FY2025 |
| G19 | blocked by the method | the segment × income-type matrix cannot be two additive views (a part may sit in one additive view only) |
| G20 | built and verified | the export carries every composition, path and transition (tested) |
| G21 | built and verified | the API serves the new ids, the view and traces (tested) |
| G22 | blocked (shared code) | a same-day import of segment, type and region actuals folds one view per total: 10 of 82 baseline observations are held back (correct under the rule; a matrix-aware guard would keep them) |

Counts. Category (primary): missing construction 16 (G01, G05–G19), incorrect mapping 3 (G02–G04), export omission 1,
retrieval omission 2; missing calibration also applies to G04, G05, G09 and G13. Outcome: built and verified 7 (G01–G03,
G05 reduced form, G18, G20, G21), built but uncalibrated 13 (G04, G06–G17), blocked 2 (G19 by the method, G22 by shared
code), not built 0.

### What was built

- **20 compositions**: 19 additive (the segment tree with Services, Markets, Fixed Income, Banking, Wealth, USCC, USCC
  NIR and All Other; the type and regions views of revenue; two views of firm NII; pretax and net income bridges; net
  income by segment; expenses by type; provisions by segment; the USCC allowance roll-forward) and one non-additive
  (CET1 sources and uses).
- **19 named paths** (non-USD rates, USD rates, securities reinvestment, long end, cross-border, Markets, deals, wholesale
  credit, card credit, card growth, card spend, market-level fees, FX translation, Mexico, transformation, investment
  program, legacy exits, capital payout, capital requirement).
- **Links touching Citi's values: 167** — 60 accounting (fixed weights), 7 calibrated causal (the new
  `cit-c-nonusd-nii`; the existing m26, s16, s19, s25, s26 and the NII → share price kind default), 100 uncalibrated
  with a sign; 164 carry a transition (s25, s26 and the kind default do not: do not touch). One new macro value,
  `usd_mxn.rate` (USD/MXN), named plainly for other companies' use; JPMorgan's unemployment, credit-spread and
  equity-index values and two of its macro links are reused by id.

### Reconciliation

At the priors (medians), all 19 additive views add up exactly (0.00%). At the FY2025 baselines (recast basis), all 19
add up within 0.5%; 18 exactly, and the USCC allowance roll-forward leaves an unexplained difference of 0.13% of its
total (benefits and claims and other-asset provisions that the two named parts leave out; reported, no residual added).
No part is backed out as a plug: the residual-like parts are sums of reported lines (other operating expense, the other
segments' provisions, NCI with discontinued operations, the regions view's North America and International, All Other
with reconciling items), each cited cell by cell locally. Units match within every view. Local detail:
`reconciliation.md`.

### Inputs by status

3 found and connected (floating share of loans, uninsured share of deposits, the rewards and partner payment rate), 2
found and not connected (DTA utilization schedule, productivity savings by year), 37 not disclosed in the reviewed
sources (each with the files and corpus queries searched, and a note where keyword candidates were read and rejected),
0 not yet reviewed. The full list is in the local `coverage.md` and in the readable view's transitions.

### Calculation coverage

No named path is calculable step by step: its causal steps are uncalibrated (sign known, size not), so its accounting
steps carry nothing. The sizes Citi's forecasts use come from four calibrated reduced forms, each kept off its path:
m26 (Fed → firm NII, an assumption), `cit-c-nonusd-nii` (non-USD basket → firm NII, from the disclosure), s16
(volatility → Markets revenue) and s19 (US growth → Services revenue); from there the accounting links carry the size
to net revenue, pretax and net income.

| Path | Calculated (calibrated causal) | Accounting (fixed weights) | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|
| `cit.path.capital_payout` | none | 0 links | `cit-c-ni-cet1` (+), `cit-c-ni-dta` (+), `cit-c-ni-div` (+), `cit-c-dta-cet1` (+), `cit-c-div-cet1` (-), `cit-c-cet1cap-ratio` (+), `cit-c-ratio-buyback` (+), `cit-c-buyback-cet1` (-) | DTA utilization schedule (found not connected) |
| `cit.path.capital_requirement` | none | 0 links | `cit-c-req-target` (+), `cit-c-target-buyback` (-), `cit-c-buyback-cet1` (-), `cit-c-cet1cap-ratio` (+) | future requirement under rule changes (not disclosed in reviewed sources) |
| `cit.path.card_credit` | none | 9 links | `cit-c-unemp-usccreserve` (-), `cit-c-unemp-delinq` (+), `cit-c-delinq-gpcc` (+), `cit-c-delinq-plcc` (+), `cit-c-delinq-loans` (-), `cit-c-gpcc-usccnco` (+), `cit-c-plcc-usccnco` (+), `cit-c-nco-ncl` (-), `cit-c-plcc-partner` (+) | card loss sensitivity to unemployment (not disclosed in reviewed sources); partner loss-sharing terms (not disclosed in reviewed sources); reserve sensitivity to the unemployment scenario (not disclosed in reviewed sources); roll rates (not disclosed in reviewed sources) |
| `cit.path.card_growth` | none | 8 links | `cit-c-loans-usccnii` (+), `cit-c-loans-reserve` (-), `cit-c-loans-ncl` (-), `cit-c-uscc-rwa` (+) | none named |
| `cit.path.card_spend` | none | 6 links | `cit-c-cpi-spend` (+), `cit-c-spend-interchange` (+), `cit-c-spend-rewards` (-) | rewards and partner payment rate per dollar of spend (found connected) |
| `cit.path.cross_border` | none | 5 links | `cit-c-usgdp-xborder` (+), `cit-c-xborder-ttsnir` (+), `cit-c-xborder-svcdeps` (+), `cit-c-svcdeps-ttsnii` (+) | TTS fee rate on cross-border value (not disclosed in reviewed sources); cross-border volume elasticity to GDP and trade (not disclosed in reviewed sources); deposit growth elasticity to client activity (not disclosed in reviewed sources) |
| `cit.path.deals_banking` | none | 6 links | `cit-c-deals-ib` (+), `cit-c-ib-comp` (-) | IB fee sensitivity to deal activity (not disclosed in reviewed sources) |
| `cit.path.fx_translation` | none | 4 links | `cit-c-eur-fxbasket` (+), `cit-c-fxbasket-intlrev` (-), `cit-c-fxbasket-opex` (+), `cit-c-fxbasket-aoci` (-), `cit-c-fxbasket-rwa` (-), `cit-c-aoci-cet1` (+), `cit-c-ni-cet1` (+), `cit-c-cet1cap-ratio` (+), `cit-c-rwa-ratio` (-) | CET1 ratio sensitivity to a USD move (not disclosed in reviewed sources); currency mix of international revenue (not disclosed in reviewed sources); non-USD share of international revenue (not disclosed in reviewed sources) |
| `cit.path.investment_program` | none | 7 links | `cit-c-invest-comp` (-), `cit-c-invest-other` (-), `cit-c-invest-productivity` (+), `cit-c-invest-loans` (+), `cit-c-productivity-comp` (+), `cit-c-loans-usccnii` (+) | balance growth per marketing dollar (not disclosed in reviewed sources); productivity savings by year (found not connected) |
| `cit.path.legacy_exits` | none | 7 links | `cit-c-banamex-mexico` (+), `cit-c-banamex-rwa` (+), `cit-c-banamex-recon` (+), `cit-c-banamex-aoci` (-), `cit-c-banamex-stranded` (-), `cit-c-stranded-other` (-), `cit-c-ni-cet1` (+), `cit-c-aoci-cet1` (+), `cit-c-cet1cap-ratio` (+), `cit-c-rwa-ratio` (-) | separation steps and timing beyond the deconsolidation guide (not disclosed in reviewed sources) |
| `cit.path.long_end` | none | 4 links | `cit-c-ust10-npy` (+), `cit-c-ust10-aoci` (-), `cit-c-npy-secyield` (+), `cit-c-secyield-corpother` (+), `cit-c-aoci-cet1` (+), `cit-c-ni-cet1` (+), `cit-c-cet1cap-ratio` (+) | AFS duration and AOCI sensitivity per 100bp (not disclosed in reviewed sources); maturity ladder of the investment portfolio (not disclosed in reviewed sources) |
| `cit.path.market_levels_fees` | none | 10 links | `cit-c-eq-auc` (+), `cit-c-eq-clientassets` (+), `cit-c-eq-equities` (+), `cit-c-auc-ssnir` (+), `cit-c-clientassets-pb` (+), `cit-c-clientassets-citigold` (+), `cit-c-clientassets-waw` (+) | equity share of AUC/AUA (not disclosed in reviewed sources); market-linked share of Wealth fees (not disclosed in reviewed sources) |
| `cit.path.markets` | none | 9 links | `cit-c-vol-ratesfx` (+), `cit-c-vol-equities` (+), `jpm-c-vol-spread` (+), `jpm-c-vol-equityindex` (-), `cit-c-vol-rwa` (+), `cit-c-spread-spreadprod` (-), `cit-c-eq-equities` (+), `cit-c-markets-comp` (-), `cit-c-rwa-ratio` (-) | Markets revenue sensitivity to volatility (not disclosed in reviewed sources); compensation ratio of Markets (not disclosed in reviewed sources) |
| `cit.path.mexico` | none | 4 links | `cit-c-mxn-mexico` (-), `cit-c-mxn-aoci` (-), `cit-c-aoci-cet1` (+), `cit-c-ni-cet1` (+), `cit-c-cet1cap-ratio` (+) | none named |
| `cit.path.non_usd_rates` | none | 5 links | `cit-c-ecb-basket` (+), `cit-c-basket-ttsnii` (+), `cit-c-basket-ssnii` (+), `cit-c-basket-depcost` (+), `cit-c-depcost-ttsnii` (-) | Securities Services NII sensitivity to non-USD rates (not disclosed in reviewed sources); TTS NII sensitivity to non-USD rates (not disclosed in reviewed sources); currency weights of non-USD deposits and NII (not disclosed in reviewed sources); deposit beta (non-USD) (not disclosed in reviewed sources); non-USD share of Services deposits (not disclosed in reviewed sources) |
| `cit.path.securities_reinvestment` | none | 4 links | `cit-c-maturities-purchases` (+), `cit-c-purchases-secyield` (+), `cit-c-secyield-corpother` (+), `cit-c-ni-cet1` (+) | none named |
| `cit.path.transformation` | none | 4 links | `cit-c-transform-tech` (-), `cit-c-transform-other` (-), `cit-c-opex-effratio` (-) | transformation spend by expense line (not disclosed in reviewed sources) |
| `cit.path.usd_rates` | none | 13 links | `cit-c-fed-depcost` (+), `cit-c-fed-ttsnii` (+), `cit-c-fed-citigold` (+), `cit-c-fed-loanyield` (+), `cit-c-fed-usccnii` (+), `cit-c-fed-corpother` (+), `cit-c-fed-mktsnii` (-), `cit-c-fed-nir-offset` (+), `cit-c-depcost-ttsnii` (-), `cit-c-depcost-citigold` (-), `cit-c-loanyield-corplending` (+) | Citi deposit beta (not disclosed in reviewed sources); Markets NII rate sensitivity (not disclosed in reviewed sources); Treasury residual rate position (not disclosed in reviewed sources); USCC NII sensitivity to rates (not disclosed in reviewed sources); USD-only NII sensitivity (not disclosed in reviewed sources); Wealth NII rate sensitivity (not disclosed in reviewed sources); floating share of loans (found connected); swap hedges of the loan book (not disclosed in reviewed sources); uninsured share of deposits (found connected) |
| `cit.path.wholesale_credit` | none | 10 links | `cit-c-spread-hedges` (+), `cit-c-spread-bankprov` (-), `cit-c-spread-corplending` (+), `cit-c-spread-spreadprod` (-) | loan hedge notional and spread sensitivity (not disclosed in reviewed sources); wholesale CECL sensitivity (not disclosed in reviewed sources) |

Most of these steps are identities the method cannot yet compute (products, ratios, weighted averages, stock-flows): when
those forms land, the tagged steps become calculable without new inputs (NII = balance × spread, losses = rate × loans,
translation = local revenue / FX, CET1 ratio = capital / RWA). The rest need a sensitivity Citi does not disclose.

**Generalization trace (oil shock; no Citi path starts there).** 179 routes, 149 reach a Citi endpoint, 8 are fully
calibrated: m01 → m05 → m06 → m26 and m04 → m07 → m26 (to firm NII through the Fed), m04 → s19 (to Services through
growth), and five routes to Markets revenue through volatility (s10, s11, s73 → s16). Uncalibrated, it also reaches the
card reserve (m04 → `jpm-c-gdp-unemp` → `cit-c-unemp-usccreserve`), card fees through nominal spend
(`cit-c-cpi-spend`), compensation through wage inflation (`cit-c-corecpi-comp`), CET1 capital through the long-end mark
(m12 → `cit-c-ust10-aoci`), and the translation basket through the yen. Endpoints reached: firm NII, net revenue,
Services, Markets, Fixed Income, Banking, Wealth, USCC revenue and NIR, All Other, operating expenses, provisions, USCC
provision, CET1 capital and ratio. It stops only at the trace depth (eight links), inside the FX, custody, wealth and
wholesale-credit chains; the share price is not reached because firm NII and the segment totals are endpoints first.

**Sally's theses that reach Citi** (forecast coverage): S-T2 (the Fed) gets a calculated size on firm NII (m26) and
Markets revenue (s16), carried to pretax and net income; 22 Citi links are excluded as uncalibrated, blocked by 12
not-disclosed inputs. S-T1 and S-T3 get Markets revenue through s16. S-T4 (China) and S-T5 (the ECB) reach Citi only
through uncalibrated links (`cit-c-pboc-basket`, `cit-c-ecb-basket`, the FX basket): the calibrated non-USD reduced
form does not fire, because the basket's currency weights are not disclosed.

### What a downstream agent can now trace or calculate, and what remains unsupported

- **Trace**: from any of the Fed, the ECB, BoJ or PBoC, the 10Y, credit spreads, volatility, equity levels, US growth,
  CPI, unemployment, the dollar or the peso, into the Citi cell it hits, its counter-paths, and the accounts (segment,
  pretax, net income, CET1); and the company's own levers (transformation, investment, Banamex exit, requirement).
- **Calculate**: firm NII from a Fed move (assumption-sized) and from a move in the non-USD basket (disclosure-sized);
  Markets and Services revenue from volatility and growth (assumption-sized); every composition's arithmetic and its
  reconciliation at FY2025.
- **Unsupported**: sizes for any segment cell, card credit, FX translation, capital and payout, and for ECB-, BoJ- or
  PBoC-driven NII (the basket weights). The USD-only NII effect is represented by m26 with a stated likely overstatement.

## Conversion (Oct 18): one driving view per total, identities, a stock-flow, states

After the method gained identities, stock-flows, matrices, reconciling views and state-dependent responses
(see [the methods](README.md)), the build was converted. Nothing below changed a size Sally's expected paths rely on
(m26, s16, s19, s25, s26 keep theirs).

**Driving view per total.**

| Total | Driving | Reconciling (observed and reconciled, never driving) |
|---|---|---|
| net revenue | the segment rows of the revenue matrix `cit.mx.revenue` (`cit.comp.revenue_by_segment`) | the type view (`cit.comp.revenue_by_type`, the matrix's columns); the regions view (`cit.comp.revenue_by_region`, `drives: false`) |
| firm NII | the matrix's NII column: the segment NII cells | interest income less interest expense (`cit.comp.nii_balance_sheet`, `drives: false`); NII ex-Markets is now a `difference` identity, not a view |
| net income | the P&L bridge (`cit.comp.net_income`) | net income by segment (`cit.comp.net_income_by_segment`, `drives: false`) |

The revenue matrix holds every segment × income-type cell (14 values: Services, Markets, Banking, Wealth, USCC, All
Other and reconciling items, each split into NII and non-interest revenue). Services and USCC rows are made of their
cells (Services NII = TTS NII + Securities Services NII), so a non-USD rate move now reaches both the Services row and
the firm NII column. The other rows are driven by their businesses or products; their cells' row links are
uncalibrated accounting links (they reconcile, they never count twice). At FY2025 every row and both columns reconcile
exactly. The reconciling views' accounting links were removed, so m26 and the non-USD reduced form now size firm NII
(and the share price) but no longer net revenue: their routes into earnings run through the driving segments only.

**Converted links.**

| Form | Object | Links |
|---|---|---|
| product | `cit.id.uscc_nii` (card loans × NII yield), `cit.id.uscc_ncl` (loss rate × loans, negative), `cit.id.interchange`, `cit.id.rewards` (spend × rate) | `cit-c-loans-usccnii`, `cit-c-yield-usccnii` (new), `cit-c-nco-ncl`, `cit-c-loans-ncl`, `cit-c-spend-interchange`, `cit-c-rate-interchange` (new), `cit-c-spend-rewards`, `cit-c-rate-rewards` (new) |
| ratio | `cit.id.mexico` (peso revenue / USD/MXN), `cit.id.efficiency`, `cit.id.cet1_ratio` | `cit-c-mxn-mexico`, `cit-c-mxnrev-mexico` (new), `cit-c-opex-effratio`, `cit-c-rev-effratio`, `cit-c-cet1cap-ratio`, `cit-c-rwa-ratio` |
| difference | `cit.id.nii_ex_markets` (firm NII − Markets NII) | two generated links |
| weighted average | `cit.id.uscc_nco` (general-purpose and private-label loss rates; synthetic round weights, the loan mix bound locally) | `cit-c-gpcc-usccnco`, `cit-c-plcc-usccnco` |
| stock-flow | `cit.sf.cet1` (annual: net income and DTA utilization in, dividends and buybacks out) | `cit-c-ni-cet1`, `cit-c-dta-cet1`, `cit-c-div-cet1`, `cit-c-buyback-cet1` |
| accounting | `cit.comp.cet1_target` (requirement + management buffer) | replaces `cit-c-req-target` |
| state: asymmetry | `cit-c-nonusd-nii`, sized with `calibrate.py --disclosure` over the disclosed rise and fall scenarios (a cut moves NII more than a hike) | 1 |
| state: threshold / sign flip | buybacks only above the target level (`cit-c-ratio-buyback`, `cit-c-target-buyback`); Banamex revenue and RWA only while control is held; reinvestment lifts the book yield only while new yields exceed it (`cit-c-purchases-secyield`) | 5 (uncalibrated, so they record the condition only) |
| new values | the 14 cells, the card NII yield, interchange and rewards rates, Mexico revenue in pesos, the CET1 management buffer | |
| summary links | `cit-c-fxbasket-services`, `-markets`, `-banking`, `-wealth`: translation reaches the driving segments (the regions view no longer drives) | 4 (uncalibrated) |

Not converted, each with its reason in the link's `note`: the non-USD and translation baskets (a weighted average
needs stated weights; Citi's currency mixes are not disclosed), the deposit-spread products in TTS (no spread level is
disclosed), Corporate Lending and Corporate/Other (funds-transfer pricing, not balance × yield), fee rates on
cross-border value and custody assets, the IB fee wallet, the day-one reserve rate and card risk weight, translation of
international revenue and expenses (no local-currency levels), the securities book-yield blend, AOCI as a level part of
CET1, the Banamex CTA recycling and release (one-time events), and partner loss-sharing.

**Links touching Citi's values, before → after:** 167 → 189. Accounting 60 → 73 (63 quantified, 10 uncalibrated matrix
row links); identity 0 → 18; stock-flow 0 → 4; calibrated causal 7 → 7 (`cit-c-nonusd-nii` now asymmetric); uncalibrated
causal 100 → 87; state-dependent 0 → 6.

**Inputs.** 5 inputs moved from "not disclosed in reviewed sources" to `disclosed_not_supplied` (the currency split of
the rate sensitivity, the USD-only sensitivity, the CET1 effect of a USD move, the AOCI sensitivity: the 10-Q discloses
them; the maturity ladder: the annual report does; none is in the supplied material). Now: 3 found and connected, 2
found and not connected, 5 disclosed but not supplied, 32 not disclosed, 0 not yet reviewed.

**Reconciliation now.** At the priors (medians): 21 additive views, the matrix (7 rows, 2 columns) and 9 identities all
hold (identities within 0.25%). At FY2025: 0 flags; the USCC allowance roll-forward keeps its −0.13% unexplained
difference; blocked (a level not in the material, not a discrepancy): the CET1 target view (no target or buffer level for
FY2025), the Mexico translation (no peso revenue or average rate) and the card loss-rate average (book rates are
quarterly only). `bundles.py check` on the baselines now passes (94 items): reconciling views fold whole.

**Coverage now.**

| Path | Calculated (identity, stock-flow, calibrated) | Accounting (fixed weights) | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|
| `cit.path.capital_payout` | `cit-c-ni-cet1`, `cit-c-dta-cet1`, `cit-c-div-cet1`, `cit-c-cet1cap-ratio`, `cit-c-buyback-cet1` | 0 links | `cit-c-ni-dta` (+), `cit-c-ni-div` (+), `cit-c-ratio-buyback` (+) | DTA utilization schedule (found not connected) |
| `cit.path.capital_requirement` | `cit-c-buyback-cet1`, `cit-c-cet1cap-ratio` | 1 links | `cit-c-target-buyback` (-) | none named |
| `cit.path.card_credit` | `cit-c-gpcc-usccnco`, `cit-c-plcc-usccnco`, `cit-c-nco-ncl` | 9 links | `cit-c-unemp-usccreserve` (-), `cit-c-unemp-delinq` (+), `cit-c-delinq-gpcc` (+), `cit-c-delinq-plcc` (+), `cit-c-delinq-loans` (-), `cit-c-plcc-partner` (+) | card loss sensitivity to unemployment (not disclosed in reviewed sources); partner loss-sharing terms (not disclosed in reviewed sources); reserve sensitivity to the unemployment scenario (not disclosed in reviewed sources); roll rates (not disclosed in reviewed sources) |
| `cit.path.card_growth` | `cit-c-loans-usccnii`, `cit-c-loans-ncl` | 8 links | `cit-c-loans-reserve` (-), `cit-c-uscc-rwa` (+) | none named |
| `cit.path.card_spend` | `cit-c-spend-interchange`, `cit-c-spend-rewards` | 6 links | `cit-c-cpi-spend` (+) | rewards and partner payment rate per dollar of spend (found connected) |
| `cit.path.cross_border` | none | 7 links | `cit-c-usgdp-xborder` (+), `cit-c-xborder-ttsnir` (+), `cit-c-xborder-svcdeps` (+), `cit-c-svcdeps-ttsnii` (+) | TTS fee rate on cross-border value (not disclosed in reviewed sources); cross-border volume elasticity to GDP and trade (not disclosed in reviewed sources); deposit growth elasticity to client activity (not disclosed in reviewed sources) |
| `cit.path.deals_banking` | none | 6 links | `cit-c-deals-ib` (+), `cit-c-ib-comp` (-) | IB fee sensitivity to deal activity (not disclosed in reviewed sources) |
| `cit.path.fx_translation` | `cit-c-ni-cet1`, `cit-c-cet1cap-ratio`, `cit-c-rwa-ratio` | 7 links | `cit-c-eur-fxbasket` (+), `cit-c-fxbasket-intlrev` (-), `cit-c-fxbasket-services` (-), `cit-c-fxbasket-markets` (-), `cit-c-fxbasket-banking` (-), `cit-c-fxbasket-wealth` (-), `cit-c-fxbasket-opex` (+), `cit-c-fxbasket-aoci` (-), `cit-c-fxbasket-rwa` (-), `cit-c-aoci-cet1` (+) | CET1 ratio sensitivity to a USD move (disclosed not supplied); currency mix of international revenue (not disclosed in reviewed sources); non-USD share of international revenue (not disclosed in reviewed sources) |
| `cit.path.investment_program` | `cit-c-loans-usccnii` | 7 links | `cit-c-invest-comp` (-), `cit-c-invest-other` (-), `cit-c-invest-productivity` (+), `cit-c-invest-loans` (+), `cit-c-productivity-comp` (+) | balance growth per marketing dollar (not disclosed in reviewed sources); productivity savings by year (found not connected) |
| `cit.path.legacy_exits` | `cit-c-mxnrev-mexico`, `cit-c-ni-cet1`, `cit-c-cet1cap-ratio`, `cit-c-rwa-ratio` | 7 links | `cit-c-banamex-mexico` (+), `cit-c-banamex-rwa` (+), `cit-c-banamex-recon` (+), `cit-c-banamex-aoci` (-), `cit-c-banamex-stranded` (-), `cit-c-stranded-other` (-), `cit-c-aoci-cet1` (+) | separation steps and timing beyond the deconsolidation guide (not disclosed in reviewed sources) |
| `cit.path.long_end` | `cit-c-ni-cet1`, `cit-c-cet1cap-ratio` | 4 links | `cit-c-ust10-npy` (+), `cit-c-ust10-aoci` (-), `cit-c-npy-secyield` (+), `cit-c-secyield-corpother` (+), `cit-c-aoci-cet1` (+) | AFS duration and AOCI sensitivity per 100bp (disclosed not supplied); maturity ladder of the investment portfolio (disclosed not supplied) |
| `cit.path.market_levels_fees` | none | 11 links | `cit-c-eq-auc` (+), `cit-c-eq-clientassets` (+), `cit-c-eq-equities` (+), `cit-c-auc-ssnir` (+), `cit-c-clientassets-pb` (+), `cit-c-clientassets-citigold` (+), `cit-c-clientassets-waw` (+) | equity share of AUC/AUA (not disclosed in reviewed sources); market-linked share of Wealth fees (not disclosed in reviewed sources) |
| `cit.path.markets` | `cit-c-rwa-ratio` | 9 links | `cit-c-vol-ratesfx` (+), `cit-c-vol-equities` (+), `jpm-c-vol-spread` (+), `jpm-c-vol-equityindex` (-), `cit-c-vol-rwa` (+), `cit-c-spread-spreadprod` (-), `cit-c-eq-equities` (+), `cit-c-markets-comp` (-) | Markets revenue sensitivity to volatility (not disclosed in reviewed sources); compensation ratio of Markets (not disclosed in reviewed sources) |
| `cit.path.mexico` | `cit-c-mxn-mexico`, `cit-c-ni-cet1`, `cit-c-cet1cap-ratio` | 4 links | `cit-c-mxn-aoci` (-), `cit-c-aoci-cet1` (+) | none named |
| `cit.path.non_usd_rates` | none | 6 links | `cit-c-ecb-basket` (+), `cit-c-basket-ttsnii` (+), `cit-c-basket-ssnii` (+), `cit-c-basket-depcost` (+), `cit-c-depcost-ttsnii` (-) | Securities Services NII sensitivity to non-USD rates (not disclosed in reviewed sources); TTS NII sensitivity to non-USD rates (not disclosed in reviewed sources); currency weights of non-USD deposits and NII (not disclosed in reviewed sources); deposit beta (non-USD) (not disclosed in reviewed sources); non-USD share of Services deposits (not disclosed in reviewed sources) |
| `cit.path.securities_reinvestment` | `cit-c-ni-cet1` | 4 links | `cit-c-maturities-purchases` (+), `cit-c-purchases-secyield` (+), `cit-c-secyield-corpother` (+) | none named |
| `cit.path.transformation` | `cit-c-opex-effratio` | 4 links | `cit-c-transform-tech` (-), `cit-c-transform-other` (-) | transformation spend by expense line (not disclosed in reviewed sources) |
| `cit.path.usd_rates` | `cit-c-yield-usccnii` | 14 links | `cit-c-fed-depcost` (+), `cit-c-fed-ttsnii` (+), `cit-c-fed-citigold` (+), `cit-c-fed-loanyield` (+), `cit-c-fed-usccnii` (+), `cit-c-fed-corpother` (+), `cit-c-fed-mktsnii` (-), `cit-c-fed-nir-offset` (+), `cit-c-depcost-ttsnii` (-), `cit-c-depcost-citigold` (-), `cit-c-loanyield-corplending` (+) | Citi deposit beta (not disclosed in reviewed sources); Markets NII rate sensitivity (not disclosed in reviewed sources); Treasury residual rate position (not disclosed in reviewed sources); USCC NII sensitivity to rates (not disclosed in reviewed sources); USD-only NII sensitivity (disclosed not supplied); Wealth NII rate sensitivity (not disclosed in reviewed sources); floating share of loans (found connected); swap hedges of the loan book (not disclosed in reviewed sources); uninsured share of deposits (found connected) |
| `cit.path.wholesale_credit` | none | 10 links | `cit-c-spread-hedges` (+), `cit-c-spread-bankprov` (-), `cit-c-spread-corplending` (+), `cit-c-spread-spreadprod` (-) | loan hedge notional and spread sensitivity (not disclosed in reviewed sources); wholesale CECL sensitivity (not disclosed in reviewed sources) |

Paths that were sign-only are now partly or wholly calculable: card spend (interchange and rewards), card credit from
the loss rates to provision, card growth to NII and losses, Mexico translation, capital payout (the CET1 roll-forward and
ratio), and the efficiency ratio. Sally's S-T2 (the Fed): firm NII is sized by m26 only (a summary link); its own steps
into firm NII (the cells) are unquantified, so the share of quantified own steps is 0; Markets revenue (s16) reaches
net revenue through the driving segments (and pretax and net income in S-T3). S-T4 and S-T5 still reach Citi only through uncalibrated links (the
basket weights).

**Oil-shock trace now.** 227 routes, 186 reach a Citi endpoint (identity targets count), 8 fully calibrated as before;
short routes stop only at the parts of reconciling views (international revenue, non-interest revenue), by design.

## What the method could not express for Citi

After the conversion (Oct 18), these remain:

1. **Weighted averages with undisclosed weights.** The non-USD rate basket and the translation basket are weighted
   averages whose weights are Citi's currency mixes, which are not disclosed; the form needs stated weights, so the
   ECB, BoJ and PBoC legs stay sign-only and an ECB or BoJ move sizes nothing at Citi (S-T4, S-T5).
2. **Translation by segment.** Translation is a ratio of local-currency revenue to the rate, but no segment's
   local-currency revenue is disclosed; a segment × currency matrix would hold it. The dollar reaches the driving
   segments only through four uncalibrated summary links.
3. **Products whose factor is not a disclosed level.** TTS NII is deposits × spread, IB fees are wallet × share, custody
   fees are assets × fee rate, the day-one reserve is growth × reserve rate; with no level for the second factor, they
   stay sign-only.
4. **Funds-transfer pricing.** Treasury results are allocated to the businesses by internal prices that net to zero;
   Corporate Lending and Corporate/Other are not balance × yield, and no form holds a transfer that nets to zero.
5. **A yield blend.** The securities book yield moves toward the new-purchase yield at the reinvested share each period
   (a stock of yield, not of value); the stock-flow form takes value flows only.
6. **A level part of a stock.** AOCI is part of CET1's level, not a flow into it; the CET1 roll-forward holds the flows,
   and AOCI stays a causal link.
7. **One-time events.** Banamex deconsolidation recycles the CTA through earnings and releases it from AOCI at once
   (capital roughly unchanged); a threshold on ownership states when revenue and RWA leave, but the recycling and
   release are an event, not a response.
8. **Thresholds against a moving level.** Buybacks act above the target, but the threshold is a fixed level (the target's
   construction level), not the running target; and thresholds on uncalibrated links record the condition only.
9. **Matrix row links that cannot carry numbers.** Rows driven by their businesses (Markets, Banking, Wealth, All Other)
   hold their cells with uncalibrated row links, so a driver of a cell (the Fed on Markets NII) reaches firm NII but not
   the row; a cell-level and a business-level breakdown of one row cannot both drive it.
10. **Contra-revenue tied to credit.** Partner payments fall when private-label losses rise: an offset across provisions
    and revenue that only a causal link expresses.
