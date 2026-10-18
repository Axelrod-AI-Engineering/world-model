# SoftBank Corp: business construction

<!-- toc -->
**Contents**

- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Identities](#identities)
  - [Stocks and flows](#stocks-and-flows)
  - [Operating and financial paths](#operating-and-financial-paths)
- [Validation](#validation)
- [Conversion to the new forms (Oct 18, second round)](#conversion-to-the-new-forms-oct-18-second-round)
- [Completion report (first round)](#completion-report-first-round)
- [What the method could not express for a telecom](#what-the-method-could-not-express-for-a-telecom)
<!-- /toc -->

The fourth build of the method, after an automaker ([Toyota](toyota.md)), an insurer ([Tokio Marine](tokio_marine.md))
and a bank ([JPMorgan](jpmorgan.md)): SoftBank Corp (9434, the Japanese telecom operator; not SoftBank Group), whose
economics are subscribers times ARPU, churn against price competition and regulation, network and AI capex turning
into depreciation, interest on a leveraged balance sheet in a rising yen rate environment, listed subsidiaries (LY
Corporation, PayPay) whose profit is shared with minorities, and a progressive dividend. The construction lives in
`data/worlds/sally_demo/construction/softbank_corp.yaml` (72 values, four new market and regulator entities, links
with their transitions, named paths, compositions, identities and stock-flows) plus light edits to the `softbank_corp` block of entities.yaml
(features on two values) and to m33, s47, s48, s49 in interactions.yaml (transitions; sizes kept). This page is
structure only: object ids, bases, categories, tests. The client-derived side (broker tables, guidance, dated
baselines, passages) stays local under `data/sally_data/construction/softbank_corp/` (`gap_evidence.md`,
`sources.json`, `citations.json`, `baselines.json`, `estimates.json`, `input_search.json`, `reconciliation.md`,
`coverage.md`, and the readable view with levels in `view/`).

Source ids used in transitions (each resolves locally in `sources.json` to a file, and in `citations.json` to the page
and line with the passage): `sbk.r1` broker company note (consolidated and segment P&L, KPIs, balance sheet, cash
flow, the company's guidance as cited); `sbk.r2` broker note on an AI-strategy event with management; `sbk.r3` broker
sector note (subscriber, ARPU and churn KPIs, competition, network quality and capex, payments); `sbk.r4` broker note
on a rival's roaming change; `sbk.co` company guidance and shareholder-return policy as cited in the broker notes (not
read directly); `sbk.macro` BoJ, JGB and yen research; `sbk.pub` public business, accounting and regulatory knowledge
(IFRS 15 contract costs, IFRS 16 leases, the Telecommunications Business Act's handset-discount and switching rules,
fuel-cost adjustment in electricity tariffs). **No company workbook was supplied**: `spreadsheets/` holds none for
SoftBank Corp and its sell-side folder holds four PDFs, so baselines are FY3/26 actuals as a broker tabulates them.

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack (036, state 432), where SoftBank Corp is `N_SOFTBANK_CORP` with six relationships (E62 share price, E75 JGB to
operating profit, E67 GDP to operating profit, E69 AI capex to operating profit, E75 JGB to AI capex, E60 TOPIX to
share price) and `PATH_SOFTBANK_CORP_JAPAN_RATES_AND_DOMESTIC_GROWTH`, six string steps that group parallel drivers
rather than a sequence. Categories: **MC** missing construction, **CAL** missing calibration, **MAP** incorrect
mapping, **EXP** export omission, **RET** retrieval omission. Outcomes are in the [completion report](#completion-report-first-round).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | No business composition: the pack jumps from JGB yields, GDP and AI capex straight to operating profit | Internal: `operating_profit`, `ai_capex`, `share_price`; m33, s47, s48, s49, s65 and the OP kind default. Export: the six relationships and the grouped path above | Revenue and operating income by reporting segment (`sbk.comp.revenue_by_segment`, `sbk.comp.op_by_segment`) with the Other segment and eliminations; the bridge to profit before tax and net income | Segment revenue and income (`sbk.r1`) | Any group earnings conclusion; which business a driver hits | `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links`, `test_priors_reconcile_within_half_a_percent` | MC |
| G02 | Undefined bases: operating profit (IFRS operating income incl. one-off items, before finance costs and minorities); AI capex (no accounting home) | Internal: values without features. Export: metrics named by id suffix | `features.view/basis/metric` on both and on every new value | Broker tables (`sbk.r1`) | Reading OP as profit to shareholders; treating AI capex as the capex line | `test_values_name_their_basis` | MAP |
| G03 | Consumer mobile economics absent: subscribers x ARPU, churn, tariffs, plan mix | Internal: none | Operating states (subscribers, ARPU, churn, tariff level, network quality) and `sbk.path.price_hike` into the Consumer revenue lines | Subscriber and ARPU KPIs (found); churn level, gross additions (not disclosed / chart only) | Whether a price increase raises revenue; churn offsets | `test_mobile_revenue_is_subscribers_times_arpu`, `test_price_increase_trades_arpu_against_churn_and_funds_the_network` | MC |
| G04 | Price competition: rivals' low-price plans, promotions (handset discounts, sales-related expenses), down-trading to the cheaper brands | Internal: none | `japan_mobile_market` (competitor price pressure, promotion intensity, data traffic per user); `sbk.path.price_competition` with three parallel responses | Churn sensitivity, brand ARPU, promotion amounts (not disclosed) | "Competition is easing" as a profit call | `test_shared_driver_responses_are_parallel_branches` | MC |
| G05 | Regulation: pressure on charges, the handset-discount cap, switching rules | Internal: none | `mic` (the regulator) and `sbk.path.regulation` with offsetting branches (ARPU down, promotion costs down, churn up) | A regulatory scenario (not in the material) | The regulatory tail risk on ARPU | `test_regulation_cuts_both_ways` | MC |
| G06 | Consumer profit bridge: revenue lines (mobile, broadband, electricity, handsets), cash costs, D&A | Internal: none | `sbk.comp.consumer_revenue`, `sbk.comp.consumer_profit` (EBITDA less D&A); revenue and cash costs to EBITDA as links | Segment opex and D&A (found) | Margin effect of a revenue change; handset revenue's low margin | `test_segment_views_cross_to_profit_bridges_only_by_matrix_links` | MC |
| G07 | Enterprise and the AI build: communications, solutions, cloud and AI; capacity x utilization; commissioning timing | Internal: `ai_capex`, s48 only | `sbk.comp.enterprise_revenue`, `sbk.comp.enterprise_profit`; AI compute capacity and utilization; `japan_it_services_market.ai_compute_demand`; `sbk.path.ai_compute` | Capacity, utilization, price per GPU-hour, asset lives (not disclosed); data-centre sites and dates (found) | "AI is the growth driver" vs "AI depreciation weighs first" | `test_required_paths_exist` | MC / CAL |
| G08 | Capex and depreciation: network (5G, quality) and AI investment as stocks that depreciate; s48 unscoped | Internal: s48 (`ai_capex` to OP) | Network capex, capex, segment D&A; stock-flow links; s48 scoped as the reduced form | Capex split by purpose, useful lives (not disclosed) | Margin path of the build | `test_reduced_forms_are_never_steps_of_their_structural_paths` | MC / MAP |
| G09 | m33 maps the AI build's funding cost into operating income; the cost is an interest charge below it | Internal: m33 (JGB 10Y to OP, -0.2). Export: E75 to operating profit | Keep m33's id, sign and size (Sally's expected path BoJ -> JGB 10Y -> SoftBank OP); scope it as the reduced form; build the structural route borrowing cost -> interest expense -> profit before tax | Maturity ladder and coupons (not disclosed) to size the structural route | The JGB conclusion for SoftBank (her research's "?" on operating profit) | `test_funding_costs_land_below_operating_income` | MAP |
| G10 | Interest costs, leverage and the yen rate environment: short-end and long-end repricing, debt, leverage; PayPay Bank as a counter-path | Internal: none | Debt, average borrowing cost, interest expense, leverage; `sbk.path.policy_rate` (funding up, bank margin up), `sbk.path.long_end` | Floating share and short-term debt (found), ladder, bank rate sensitivity (not disclosed) | "Higher yen rates hurt SoftBank" without the bank offset | `test_a_hike_is_a_counter_path_inside_the_group` | MC / CAL |
| G11 | PayPay: GMV = users x frequency x ticket; fees; operating leverage; SB Payment Service | Internal: none | PayPay MTU and GMV, `sbk.comp.financial_profit`, `sbk.path.paypay_growth` | Merchant fee rate (not disclosed) | Financial segment growth | `test_required_paths_exist` | MC |
| G12 | Media & EC (LY Corporation): advertising and commerce demand; one-off items; s47 unscoped | Internal: s47 (GDP to OP) | `sbk.comp.media_ec_profit` (recurring + one-offs); `sbk.path.domestic_demand`; s47 scoped | Media vs commerce split, AI search substitution (not disclosed) | Reading one-offs as trend | `test_reduced_forms_are_never_steps_of_their_structural_paths` | MC |
| G13 | Minorities: operating income is not what the parent's owners receive from LY Corporation and PayPay | Internal: none | `sbk.comp.net_income` with non-controlling interests; segment income to minorities | Economic ownership (found, cited) | Attributable earnings from the growth segments | `test_minorities_take_part_of_the_listed_subsidiaries_profit` | MC / MAP |
| G14 | Dividend policy and capital allocation: the net-income ladder for DPS, dividends against free cash flow, debt and leverage | Internal: none | DPS, total dividends, free cash flow, capex; `sbk.path.dividend_policy`, `sbk.path.capital_allocation`; non-additive `sbk.comp.debt_sources_uses` | The company's stated ladder (found); leverage threshold (not disclosed) | Dividend growth while the AI build is debt-funded | `test_dividend_ladder_is_calibrated_from_guidance`, `test_debt_is_a_stock_with_flows_not_an_additive_view` | MC / CAL |
| G15 | Distribution: IT product distribution on corporate refresh cycles, thin margin | Internal: none | `japan_it_services_market.it_spending`, `sbk.path.enterprise_it` | Volumes (not disclosed) | Revenue growth that adds little profit | `test_required_paths_exist` | MC |
| G16 | Power prices: electricity retail pass-through against procurement, network and data-centre power | Internal: none | `japan_power_market.wholesale_price`, `sbk.path.power_prices` (offsetting branches) | Pass-through formula, procurement, DC power (not disclosed) | Energy shocks on margins | `test_shared_driver_responses_are_parallel_branches` | MC |
| G17 | Group EBITDA and D&A (the brokers' valuation basis) | Internal: none | `sbk.comp.op_ebitda_bridge`, reconciled but undriven | EBITDA (found) | EV/EBITDA reasoning | `test_ebitda_view_is_reconciled_but_undriven` | MC |
| G18 | New objects absent from the export | Export: the six relationships only | Transitions in relationship properties, `financial_bridge`, `business_construction` paths | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G19 | New node ids not retrievable | Internal API: none | `/v1/world-models/sally_demo/graph`, `…/entities/softbank_corp/construction` and its traces | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G20 | A results release reports the segment view and the EBITDA bridge of operating income on the same day; the import guard folds one view per total and day | Import: `intake/overlap.py` | Not built here (shared code): see the completion report | A two-way (matrix) reconciliation | Importing a full set of actuals | listed as blocked | RET |
| G21 | No company workbook: baselines rest on a broker's tabulation of company data | Supplied material: four PDFs | Baselines from the broker tables, derived parts marked | The company's own results file or a model workbook | Precision of every baseline | `check.py --reconcile --baselines` (0 flags) | CAL |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, kind, memberships, share-price kind default (`softbank_corp`) | Already owned | entities.yaml `softbank_corp`, taxonomy | untouched |
| m33, s47, s48, s49 (statistical records on SoftBank's values) | Already owned → Modify lightly | interactions.yaml | ids, sizes and kernels kept (m33 is on Sally's expected path); transitions added (scope, reduced form, evidence, unresolved inputs) |
| s65 (TOPIX to the share price) and the operating-profit kind default | Do not touch | interactions.yaml, taxonomy | untouched |
| `operating_profit`, `ai_capex` definitions | Modify lightly | entities.yaml | `features.view/basis/metric` added; ids and priors kept |
| Compositions, operating states, connected paths, financial mappings, market and regulator values, bindings | Missing | construction/softbank_corp.yaml; local sources, citations, baselines | built |
| Shared macro links (m02, m08, m13, m16-m18, s01, s62-s64, s72) and other companies' objects | Do not touch | interactions.yaml, entities.yaml | untouched; SoftBank's paths start at their values (BoJ, JGB 10Y, Japan CPI and GDP, USD/JPY) |
| Import overlap guard | Do not touch (shared code) | `src/axelrod_wm/intake/overlap.py` | behaviour reported (G20), not edited |

New values another company may also need (named by market and measure, uncalibrated so no other output moves):
`japan_mobile_market.competitor_price_pressure`, `.promotion_intensity`, `.data_traffic_per_user` (the other Japanese
operators), `mic.mobile_pricing_regulation`, `japan_it_services_market.it_spending`, `.ai_compute_demand` (Japanese IT
services and data-centre names), `japan_power_market.wholesale_price` (utilities, data centres, energy-intensive
industry). One macro link was added: `sbk-c-oil-power` (oil to Japanese wholesale power prices).

## Definitions and bases

- **IFRS, fiscal year ending March, JPY bn.** Segment revenue includes internal sales; the Other segment and
  intersegment eliminations are reported together in the sources read, so they are one net elimination
  (`revenue_other_and_eliminations`). Operating income (`operating_profit`) is segment income plus a residual for
  the Other segment and corporate adjustments.
- **One driving view of operating income.** By segment (`sbk.comp.op_by_segment`) drives it: the paths and the
  reduced forms feed the segments. The EBITDA bridge (`sbk.comp.op_ebitda_bridge`, the valuation basis) is
  reconciling (`drives: false`): checked by `reconcile`, no link from its parts into the total.
- **Nested segment bridges.** Consumer and Enterprise EBITDA = segment revenue + cash operating costs
  (`sbk.comp.consumer_ebitda`, `sbk.comp.enterprise_ebitda`), and segment income = EBITDA + D&A. Segment revenue is a
  part of group revenue and of its own EBITDA bridge (different totals, now allowed).
- **Mobile service revenue** = 0.012 x ARPU x subscribers x the consumer share of the base (`sbk.id.mobile_revenue`).
  Subscribers are a stock (`sbk.sf.subscribers`, quarterly, `period_average`): gross additions in, cancellations out,
  and cancellations = churn x subscribers (`sbk.id.cancellations`).
- **Costs, charges and deductions are negative values** (cash costs, D&A, interest, tax, minorities), so every part adds
  with a positive weight; a cost link's sign "−" means "a larger charge".
- **Interest expense** is cash interest paid, standing in for the IFRS finance cost, which the sources read do not give.
  Debt excludes banking deposits (PayPay Bank). Average borrowing cost and leverage are derived (interest over debt;
  net debt over EBITDA).
- **What reaches the parent's owners**: net income = profit before tax + tax + non-controlling interests (both
  negative). LY Corporation and PayPay are listed or partly owned; their minorities take a large share of Media & EC
  and Financial profit.
- **Identities and stocks.** Interest = -0.01 x borrowing cost x debt; tax = -0.01 x pretax x effective rate;
  minorities by subsidiary = -1 x segment income x the outside shareholders' share; net debt = debt - cash; leverage =
  net debt / EBITDA; dividends = DPS x shares; free cash flow = operating cash flow - capex; Distribution income =
  revenue x margin; PayPay GMV = users x GMV per user. Debt is a stock (`sbk.sf.debt`, annual): dividends in, free cash
  flow out. Weights are derived at the construction levels.
- **The dividend ladder** is a ratchet approximation: an asymmetry about the construction level, rises sized from the
  company's stated ladder, falls 0.
- **Steps that fit no form** stay uncalibrated, and their note starts "kept uncalibrated:" with the reason.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities softbank_corp` from the loaded model
(the same objects the API serves at `/v1/world-models/sally_demo/entities/softbank_corp/construction`). A `?` marks a step whose size is
unknown (uncalibrated). Levels are left out here; the local copy adds them.

123 links touch its values: 76 calibrated, 47 uncalibrated (represented, size unknown), 40 accounting, 25 identity, 4 stock-flow; 1 state-dependent; 121 carry a transition.

### Business composition

#### reporting segments: Consumer EBITDA: Consumer revenue less cash operating costs (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Consumer revenue | `softbank_corp.consumer_revenue` |
| SoftBank Corp Consumer cash operating costs | `softbank_corp.consumer_cash_costs` |
| **Total: SoftBank Corp Consumer EBITDA** | `softbank_corp.consumer_ebitda` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
A nested bridge: Consumer revenue is also a part of revenue by segment (a different total). Cash costs are negative.

#### reporting segments: Consumer segment income: EBITDA less depreciation and amortization (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Consumer EBITDA | `softbank_corp.consumer_ebitda` |
| SoftBank Corp Consumer depreciation and amortization | `softbank_corp.consumer_depreciation` |
| **Total: SoftBank Corp Consumer segment income** | `softbank_corp.consumer_op` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity. EBITDA is revenue plus cash costs (negative), held as links (sbk-c-consrev-consebitda, sbk-c-conscosts-consebitda) because Consumer revenue is already a part of the segment revenue view.

#### product: Consumer revenue by line: mobile service, broadband, electricity, handsets and merchandise (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Consumer mobile service revenue | `softbank_corp.consumer_mobile_revenue` |
| SoftBank Corp Consumer broadband revenue | `softbank_corp.consumer_broadband_revenue` |
| SoftBank Corp Consumer electricity revenue | `softbank_corp.consumer_electricity_revenue` |
| SoftBank Corp Consumer handset and merchandise revenue | `softbank_corp.consumer_merchandise_revenue` |
| **Total: SoftBank Corp Consumer revenue** | `softbank_corp.consumer_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported (services = mobile + broadband + electricity; plus merchandise). Mobile service revenue is subscribers x ARPU; handsets are low margin.

#### reporting segments: Enterprise EBITDA: Enterprise revenue less cash operating costs (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Enterprise revenue | `softbank_corp.enterprise_revenue` |
| SoftBank Corp Enterprise cash operating costs | `softbank_corp.enterprise_cash_costs` |
| **Total: SoftBank Corp Enterprise EBITDA** | `softbank_corp.enterprise_ebitda` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
A nested bridge: Enterprise revenue is also a part of revenue by segment (a different total).

#### reporting segments: Enterprise segment income: EBITDA less depreciation and amortization (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Enterprise EBITDA | `softbank_corp.enterprise_ebitda` |
| SoftBank Corp Enterprise depreciation and amortization | `softbank_corp.enterprise_depreciation` |
| **Total: SoftBank Corp Enterprise segment income** | `softbank_corp.enterprise_op` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity. The AI build reaches income twice: capacity and utilization raise revenue (EBITDA), the assets raise D&A first.

#### product: Enterprise revenue by line: communications, solutions, cloud and AI (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Enterprise communications revenue | `softbank_corp.enterprise_communications_revenue` |
| SoftBank Corp Enterprise solutions revenue | `softbank_corp.enterprise_solutions_revenue` |
| SoftBank Corp Enterprise cloud and AI revenue | `softbank_corp.enterprise_cloud_ai_revenue` |
| **Total: SoftBank Corp Enterprise revenue** | `softbank_corp.enterprise_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as the company now reports it. Cloud and AI holds AI computing capacity rental, AI solutions, cybersecurity and cloud; its growth carries the segment.

#### reporting segments: Financial segment income: SB Payment Service and PayPay with the other financial businesses (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp SB Payment Service income | `softbank_corp.sbps_op` |
| Residual: SoftBank Corp PayPay and other financial income | `softbank_corp.paypay_and_other_op` |
| **Total: SoftBank Corp Financial segment income** | `softbank_corp.financial_op` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
SB Payment Service is wholly owned and valued with the core businesses; PayPay (incl. card and bank) is the residual and is shared with minorities.

#### reporting segments: Media & EC segment income: recurring income plus one-off items (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Media & EC recurring segment income | `softbank_corp.media_ec_recurring_op` |
| SoftBank Corp Media & EC one-off items | `softbank_corp.media_ec_one_offs` |
| **Total: SoftBank Corp Media & EC segment income** | `softbank_corp.media_ec_op` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity. One-off items (business-combination remeasurement gains, a system-incident loss) are kept apart so a year-on-year comparison does not read them as trend.

#### capital: non-controlling interests by subsidiary: LY Corporation, PayPay, other (negative values) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp minorities' share of Media & EC income | `softbank_corp.nci_lycorp` |
| SoftBank Corp minorities' share of Financial income | `softbank_corp.nci_paypay` |
| Residual: SoftBank Corp other non-controlling interests | `softbank_corp.nci_remaining` |
| **Total: SoftBank Corp profit attributable to non-controlling interests** | `softbank_corp.noncontrolling_interests` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The by-subsidiary split is not disclosed in the sources read: at the baselines it is blocked, not flagged.

#### reporting segments: net income attributable to owners: profit before tax less tax less non-controlling interests (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp profit before tax | `softbank_corp.pretax_income` |
| SoftBank Corp income tax | `softbank_corp.income_tax` |
| SoftBank Corp profit attributable to non-controlling interests | `softbank_corp.noncontrolling_interests` |
| **Total: SoftBank Corp net income** | `softbank_corp.net_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity (tax and minorities are negative). Minorities take a large share of Media & EC and Financial profit, so operating income overstates what the parent's owners get from those segments.

#### reporting segments: IFRS operating income by reporting segment (segment income) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Consumer segment income | `softbank_corp.consumer_op` |
| SoftBank Corp Enterprise segment income | `softbank_corp.enterprise_op` |
| SoftBank Corp Distribution segment income | `softbank_corp.distribution_op` |
| SoftBank Corp Media & EC segment income | `softbank_corp.media_ec_op` |
| SoftBank Corp Financial segment income | `softbank_corp.financial_op` |
| Residual: SoftBank Corp other segment income and adjustments | `softbank_corp.op_other_and_adjustments` |
| **Total: SoftBank Corp operating income** | `softbank_corp.operating_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driven view of operating income: telecom pricing, subscribers and costs enter through Consumer; AI compute and IT demand through Enterprise; payments and the bank through Financial. Not the EBITDA bridge (sbk.comp.op_ebitda_bridge): never added to it.

#### reporting segments: operating income as EBITDA less depreciation and amortization (group) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp EBITDA | `softbank_corp.ebitda` |
| SoftBank Corp depreciation and amortization | `softbank_corp.depreciation` |
| **Total: SoftBank Corp operating income** | `softbank_corp.operating_profit` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling view (drives: false): the brokers value the core on EV/EBITDA, so EBITDA and D&A are held and reconciled; the drivers act through the segments (sbk.comp.op_by_segment), so its parts carry no link into the total.

#### reporting segments: profit before tax: operating income less interest plus other non-operating items (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp operating income | `softbank_corp.operating_profit` |
| SoftBank Corp interest expense | `softbank_corp.interest_expense` |
| Residual: SoftBank Corp other non-operating income | `softbank_corp.other_nonoperating` |
| **Total: SoftBank Corp profit before tax** | `softbank_corp.pretax_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Interest expense is negative. The funding cost of the AI build and of the yen rate environment lands here, below operating income.

#### reporting segments: IFRS revenue by reporting segment (segment revenue incl. internal sales) (¥bn/yr, fiscal year ending March)

| Part | Value |
|---|---|
| SoftBank Corp Consumer revenue | `softbank_corp.consumer_revenue` |
| SoftBank Corp Enterprise revenue | `softbank_corp.enterprise_revenue` |
| SoftBank Corp Distribution revenue | `softbank_corp.distribution_revenue` |
| SoftBank Corp Media & EC revenue | `softbank_corp.media_ec_revenue` |
| SoftBank Corp Financial revenue | `softbank_corp.financial_revenue` |
| Eliminations: SoftBank Corp other segments and revenue eliminations | `softbank_corp.revenue_other_and_eliminations` |
| **Total: SoftBank Corp revenue** | `softbank_corp.revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Five reporting segments; the Other segment and intersegment eliminations are reported together in the sources read, so they are one net elimination. Media & EC is LY Corporation and Financial is PayPay and SB Payment Service: listed or partly owned subsidiaries whose profit is shared with minorities (see sbk.comp.net_income).

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `sbk.id.cancellations` (product) | SoftBank Corp mobile cancellations = 0.03 x SoftBank Corp mobile churn rate x SoftBank Corp mobile main subscribers | SoftBank Corp mobile churn rate (factor, +1.000); SoftBank Corp mobile main subscribers (factor, +0.100) | mn/quarter = %/month x mn x 0.01 x 3 months |
| `sbk.id.distribution_margin` (product) | SoftBank Corp Distribution segment income = 0.01 x SoftBank Corp Distribution revenue x SoftBank Corp Distribution segment margin | SoftBank Corp Distribution revenue (factor, +0.667); SoftBank Corp Distribution segment margin (factor, +1.190) | ¥bn/yr = ¥bn/yr x % x 0.01 |
| `sbk.id.dividends` (product) | SoftBank Corp total dividends = SoftBank Corp dividend per share x SoftBank Corp shares outstanding | SoftBank Corp dividend per share (factor, +0.960); SoftBank Corp shares outstanding (factor, +0.176) | ¥bn/yr = ¥/share x bn shares |
| `sbk.id.fcf` (difference) | SoftBank Corp free cash flow = SoftBank Corp operating cash flow - SoftBank Corp capital expenditure | SoftBank Corp operating cash flow (total, +0.667); SoftBank Corp capital expenditure (deduction, -0.542) | ¥bn/yr = ¥bn/yr - ¥bn/yr |
| `sbk.id.interest` (product) | SoftBank Corp interest expense = -0.01 x SoftBank Corp average borrowing cost x SoftBank Corp interest-bearing debt | SoftBank Corp average borrowing cost (factor, -0.975); SoftBank Corp interest-bearing debt (factor, -0.273) | ¥bn/yr = % x ¥bn x 0.01, negative (a charge) |
| `sbk.id.leverage` (ratio) | SoftBank Corp net debt to EBITDA = SoftBank Corp net debt / SoftBank Corp EBITDA | SoftBank Corp net debt (numerator, +0.551); SoftBank Corp EBITDA (denominator, -0.551) | x = ¥bn / ¥bn/yr |
| `sbk.id.mobile_revenue` (product) | SoftBank Corp Consumer mobile service revenue = 0.012 x SoftBank Corp mobile ARPU x SoftBank Corp mobile main subscribers x SoftBank Corp consumer share of mobile service revenue | SoftBank Corp mobile ARPU (factor, +1.000); SoftBank Corp mobile main subscribers (factor, +0.500); SoftBank Corp consumer share of mobile service revenue (factor, +0.570) | ¥bn/yr = ¥/month x mn x fraction x 12 months / 1000 |
| `sbk.id.nci_lycorp` (product) | SoftBank Corp minorities' share of Media & EC income = -1 x SoftBank Corp Media & EC segment income x LY Corporation outside shareholders' after-tax share of segment income | SoftBank Corp Media & EC segment income (factor, -0.817); LY Corporation outside shareholders' after-tax share of segment income (factor, -1.021) | ¥bn/yr = ¥bn/yr x fraction x -1 (a deduction, negative) |
| `sbk.id.nci_paypay` (product) | SoftBank Corp minorities' share of Financial income = -1 x SoftBank Corp Financial segment income x PayPay outside shareholders' after-tax share of segment income | SoftBank Corp Financial segment income (factor, -0.844); PayPay outside shareholders' after-tax share of segment income (factor, -0.562) | ¥bn/yr = ¥bn/yr x fraction x -1 (a deduction, negative) |
| `sbk.id.net_debt` (difference) | SoftBank Corp net debt = SoftBank Corp interest-bearing debt - SoftBank Corp cash and equivalents | SoftBank Corp interest-bearing debt (total, +0.956); SoftBank Corp cash and equivalents (deduction, -0.686) | ¥bn = ¥bn - ¥bn |
| `sbk.id.paypay_gmv` (product) | PayPay payment GMV = PayPay monthly transacting users x PayPay GMV per transacting user | PayPay monthly transacting users (factor, +0.600); PayPay GMV per transacting user (factor, +1.000) | ¥tn/yr = mn users x ¥tn per mn users per year (payments per user x average ticket) |
| `sbk.id.tax` (product) | SoftBank Corp income tax = -0.01 x SoftBank Corp profit before tax x SoftBank Corp effective tax rate | SoftBank Corp profit before tax (factor, -0.728); SoftBank Corp effective tax rate (factor, -0.800) | ¥bn/yr = ¥bn/yr x % x -0.01 (a charge, negative) |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `sbk.sf.debt` | SoftBank Corp interest-bearing debt (closing) = SoftBank Corp interest-bearing debt (opening) + SoftBank Corp total dividends - SoftBank Corp free cash flow, per 365 days | SoftBank Corp total dividends (inflow, +0.077); SoftBank Corp free cash flow (outflow, -0.615) |
| `sbk.sf.subscribers` | SoftBank Corp mobile main subscribers (closing) = SoftBank Corp mobile main subscribers (opening) + SoftBank Corp mobile gross additions - SoftBank Corp mobile cancellations, per 91 days; the stock is a period average | SoftBank Corp mobile gross additions (inflow, +0.240); SoftBank Corp mobile cancellations (outflow, -0.300) |

### Operating and financial paths

#### SoftBank Corp AI compute demand to net income

**Trigger:** enterprise and public-sector demand for AI computing capacity rises. **Endpoint:** SoftBank Corp net income.

Japan demand for AI computing capacity → [utilization] SoftBank Corp AI compute utilization? → [build] SoftBank Corp AI data-center investment? → SoftBank Corp AI compute capacity in service? → SoftBank Corp Enterprise cloud and AI revenue? → SoftBank Corp Enterprise cloud and AI revenue? → SoftBank Corp Enterprise revenue → SoftBank Corp Enterprise EBITDA → SoftBank Corp Enterprise segment income → SoftBank Corp Enterprise depreciation and amortization? → SoftBank Corp Enterprise segment income → SoftBank Corp operating income → SoftBank Corp capital expenditure? → SoftBank Corp free cash flow → SoftBank Corp interest-bearing debt → SoftBank Corp interest expense → SoftBank Corp profit before tax → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Demand fills existing capacity (utilization) and prompts more capacity (investment); capacity arrives at commissioning, revenue is capacity x utilization x price, depreciation arrives first; the build is funded by debt (capex -> free cash flow -> debt -> interest). s48 is the reduced form of the depreciation drag and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [utilization] `sbk-c-aidemand-util` | Demand for domestically hosted (sovereign) AI training and inference fills the GPU capacity already in service (enterprise and public-sector customers) | capacity in service; prices competitive with hyperscalers; observable: contracted share of capacity; rental revenue growth | onset within the quarter; build quarters; persists while demand holds; recognized rental revenue | broker / broker / unknown / broker | slower corporate AI adoption; hyperscaler price competition | AI compute utilization | unknown |
| 2 [build] `sbk-c-aidemand-aicapex` | SoftBank builds AI data centres and buys GPUs ahead of demand; stronger demand brings the next phases forward (SoftBank Corp (investment decision)) | funding available; GPU supply; observable: announced data-centre phases and investment plans | onset a year or more; build multi-year; persists programme length; recognized capex; then depreciation | broker / broker / unknown / broker | funding cost and leverage; demand shortfall | AI investment | unknown |
| 3 `sbk-c-aicapex-capacity` | Investment becomes rentable capacity when a data centre is commissioned; the large new sites start in the second half of one fiscal year and the next, so capacity lags spending by quarters (SoftBank Corp (construction)) | construction, power connection and GPU delivery on schedule; observable: data-centre commissioning dates | onset at commissioning (2-6 quarters after spend); build phase by phase; persists the asset life; recognized capacity, not an account | broker / broker / unknown / broker | construction or power-connection delays | AI compute capacity | unknown |
| 4 `sbk-c-capacity-cloudai` | AI computing revenue is capacity in service times utilization times the rental price: more capacity at the same use raises cloud and AI revenue (none (arithmetic)) | utilization holds as capacity is added; observable: cloud and AI revenue against capacity added | onset same period; build none; persists identity; recognized rental revenue | broker / inferred / unknown / unknown | price declines per GPU-hour as newer chips arrive | cloud and AI revenue | unknown |
| 5 `sbk-c-util-cloudai` | Higher utilization of the same capacity raises cloud and AI revenue (none (arithmetic)) | pricing holds; observable: cloud and AI revenue growth | onset same period; build none; persists identity; recognized rental revenue | broker / inferred / unknown / unknown | none: an identity | cloud and AI revenue | unknown |
| 6 `sbk-a-ent-enterprise-cloud-ai-revenue` | SoftBank Corp Enterprise cloud and AI revenue is one part of SoftBank Corp Enterprise revenue (Enterprise revenue by line: communications, solutions, cloud and AI); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise revenue | +0.60 sd/sd (accounting) |
| 7 `sbk-a-entebitda-enterprise-revenue` | SoftBank Corp Enterprise revenue is one part of SoftBank Corp Enterprise EBITDA (Enterprise EBITDA: Enterprise revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise EBITDA | +2.19 sd/sd (accounting) |
| 8 `sbk-a-entop-enterprise-ebitda` | SoftBank Corp Enterprise EBITDA is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +1.43 sd/sd (accounting) |
| 9 `sbk-c-aicapex-entdep` | GPU servers and data-centre assets are depreciated over short useful lives, so the AI build raises Enterprise depreciation (a larger charge) soon after commissioning, before utilization ramps (none (accounting)) | assets in service; observable: Enterprise D&A | onset at commissioning; build builds with each phase; persists useful life of the servers; recognized depreciation each quarter | broker / documented / unknown / inferred | lease or partner financing that moves cost into opex | Enterprise depreciation | unknown |
| 10 `sbk-a-entop-enterprise-depreciation` | SoftBank Corp Enterprise depreciation and amortization is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +0.75 sd/sd (accounting) |
| 11 `sbk-a-op-enterprise-op` | SoftBank Corp Enterprise segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.24 sd/sd (accounting) |
| 12 `sbk-c-aicapex-capex` | AI data-centre and GPU purchases booked as property, plant and equipment are part of the capex line (none (accounting)) | booked as capex rather than leases or investments; observable: capex in the cash-flow statement | onset same period; build none; persists identity; recognized cash-flow statement | broker / inferred / unknown / unknown | leases, partner vehicles and equity investments keep part of the build off the capex line | capital expenditure | unknown |
| 13 `sbk-c-capex-fcf` | Free cash flow is operating cash flow less capex: more capex lowers it one for one (none (arithmetic)) | operating cash flow unchanged; observable: cash-flow statement | onset same period; build none; persists identity; recognized cash-flow statement | documented / documented / inferred / documented | none: an identity | free cash flow | -0.54 sd/sd (identity) |
| 14 `sbk-c-fcf-debt` | Debt is a stock: free cash flow left after dividends reduces borrowing, a shortfall adds to it (SoftBank Corp (treasury)) | no large acquisitions or disposals; observable: net change in debt | onset same period; build accumulates; persists until repaid; recognized balance sheet | documented / documented / inferred / documented | acquisitions; investments in subsidiaries | interest-bearing debt | -0.62 sd/sd (stock-flow, accumulates per 365 days) |
| 15 `sbk-c-debt-intexp` | More debt at the same average cost raises interest expense (none (arithmetic)) | cost unchanged; observable: interest-bearing debt | onset same period; build none; persists identity; recognized finance costs | documented / documented / inferred / documented | none: an identity | interest expense | -0.27 sd/sd (identity) |
| 16 `sbk-a-pretax-interest-expense` | SoftBank Corp interest expense is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.14 sd/sd (accounting) |
| 17 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 18 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: AI asset useful lives (not disclosed in reviewed sources); AI compute revenue by component (not disclosed in reviewed sources); AI compute utilization and contracted backlog (not disclosed in reviewed sources); AI investment plan by phase (not disclosed in reviewed sources); data-centre capacity by site and date (found connected); how the AI build is financed (capex, leases, partners) (not disclosed in reviewed sources); split of capital expenditure by purpose (not disclosed in reviewed sources).

#### SoftBank Corp AI build to debt, interest and the dividend

**Trigger:** the AI build raises investment. **Endpoint:** SoftBank Corp total dividends.

SoftBank Corp AI data-center investment → SoftBank Corp capital expenditure? → SoftBank Corp free cash flow → SoftBank Corp interest-bearing debt → SoftBank Corp interest expense → SoftBank Corp profit before tax → SoftBank Corp net income → SoftBank Corp dividend per share → SoftBank Corp net debt → SoftBank Corp net debt to EBITDA → SoftBank Corp dividend per share? → SoftBank Corp total dividends  (? marks a step whose size is unknown)

Investment lowers free cash flow; with a high payout the gap is borrowed: debt, interest expense and leverage rise, and leverage limits the dividend. The yen rate environment sets what the added debt costs (sbk.path.policy_rate, sbk.path.long_end).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `sbk-c-aicapex-capex` | AI data-centre and GPU purchases booked as property, plant and equipment are part of the capex line (none (accounting)) | booked as capex rather than leases or investments; observable: capex in the cash-flow statement | onset same period; build none; persists identity; recognized cash-flow statement | broker / inferred / unknown / unknown | leases, partner vehicles and equity investments keep part of the build off the capex line | capital expenditure | unknown |
| 2 `sbk-c-capex-fcf` | Free cash flow is operating cash flow less capex: more capex lowers it one for one (none (arithmetic)) | operating cash flow unchanged; observable: cash-flow statement | onset same period; build none; persists identity; recognized cash-flow statement | documented / documented / inferred / documented | none: an identity | free cash flow | -0.54 sd/sd (identity) |
| 3 `sbk-c-fcf-debt` | Debt is a stock: free cash flow left after dividends reduces borrowing, a shortfall adds to it (SoftBank Corp (treasury)) | no large acquisitions or disposals; observable: net change in debt | onset same period; build accumulates; persists until repaid; recognized balance sheet | documented / documented / inferred / documented | acquisitions; investments in subsidiaries | interest-bearing debt | -0.62 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `sbk-c-debt-intexp` | More debt at the same average cost raises interest expense (none (arithmetic)) | cost unchanged; observable: interest-bearing debt | onset same period; build none; persists identity; recognized finance costs | documented / documented / inferred / documented | none: an identity | interest expense | -0.27 sd/sd (identity) |
| 5 `sbk-a-pretax-interest-expense` | SoftBank Corp interest expense is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.14 sd/sd (accounting) |
| 6 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |
| 7 `sbk-c-ni-dps` | Management links the dividend to net income: it has said it would consider raising the dividend per share at stated net income levels, with a policy of continuous dividend growth (SoftBank Corp (board)) | net income reaches the stated levels; no change in policy; observable: the dividend forecast against the net income forecast | onset at the next dividend decision; build none; persists years (progressive policy); recognized dividend declared | guidance / guidance / guidance / guidance | leverage or investment needs; the ladder is 'would consider', not a commitment | dividend per share | +1.07 sd/sd; +1.07 sd/sd while SoftBank Corp net income is above its construction level, +0.00 below |
| 8 `sbk-c-debt-netdebt` | Net leverage is net debt over EBITDA: more debt on the same EBITDA raises it (none (arithmetic)) | EBITDA unchanged; observable: net debt and EBITDA | onset same period; build none; persists identity; recognized balance sheet | documented / documented / inferred / documented | none: an identity | net leverage | +0.96 sd/sd (identity) |
| 9 `sbk.id.leverage:softbank_corp.net_debt` | SoftBank Corp net debt to EBITDA = SoftBank Corp net debt / SoftBank Corp EBITDA: SoftBank Corp net debt is a numerator; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.55 sd/sd (identity) |
| 10 `sbk-c-leverage-dps` | A rising leverage ratio, from debt-funded investment and payouts, limits room for dividend increases under the company's financial discipline and credit ratings (SoftBank Corp (board)) | leverage near the level management or the rating agencies treat as a ceiling; observable: leverage against the dividend decision | onset at the next dividend decision; build none; persists while leverage is high; recognized dividend declared | inferred / inferred / unknown / unknown | a commitment to continuous dividend growth (cuts are unlikely) | dividend per share | unknown |
| 11 `sbk-c-dps-dividends` | Total dividends are the dividend per share times shares outstanding (none (arithmetic)) | share count unchanged; observable: dividends paid | onset same period; build none; persists identity; recognized dividends declared and paid | documented / documented / inferred / documented | none: an identity | total dividends | +0.96 sd/sd (identity) |

Unresolved inputs: how the AI build is financed (capex, leases, partners) (not disclosed in reviewed sources); leverage target or rating threshold (not disclosed in reviewed sources); split of capital expenditure by purpose (not disclosed in reviewed sources).

#### SoftBank Corp net income to the dividend

**Trigger:** net income moves. **Endpoint:** SoftBank Corp total dividends.

SoftBank Corp net income → SoftBank Corp dividend per share → SoftBank Corp total dividends → SoftBank Corp interest-bearing debt → SoftBank Corp net debt → SoftBank Corp net debt to EBITDA → SoftBank Corp dividend per share?  (? marks a step whose size is unknown)

Net income sets the dividend by the stated ladder (calibrated from guidance); dividends close to free cash flow add to debt, and leverage caps further increases (a feedback).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `sbk-c-ni-dps` | Management links the dividend to net income: it has said it would consider raising the dividend per share at stated net income levels, with a policy of continuous dividend growth (SoftBank Corp (board)) | net income reaches the stated levels; no change in policy; observable: the dividend forecast against the net income forecast | onset at the next dividend decision; build none; persists years (progressive policy); recognized dividend declared | guidance / guidance / guidance / guidance | leverage or investment needs; the ladder is 'would consider', not a commitment | dividend per share | +1.07 sd/sd; +1.07 sd/sd while SoftBank Corp net income is above its construction level, +0.00 below |
| 2 `sbk-c-dps-dividends` | Total dividends are the dividend per share times shares outstanding (none (arithmetic)) | share count unchanged; observable: dividends paid | onset same period; build none; persists identity; recognized dividends declared and paid | documented / documented / inferred / documented | none: an identity | total dividends | +0.96 sd/sd (identity) |
| 3 `sbk-c-dividends-debt` | Dividends close to or above free cash flow are partly funded by borrowing, so a higher payout adds to debt (SoftBank Corp (treasury)) | dividends exceed free cash flow after other uses; observable: dividends paid against free cash flow | onset same period; build accumulates; persists until repaid; recognized balance sheet | documented / inferred / inferred / documented | free cash flow above the dividend | interest-bearing debt | +0.08 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `sbk-c-debt-netdebt` | Net leverage is net debt over EBITDA: more debt on the same EBITDA raises it (none (arithmetic)) | EBITDA unchanged; observable: net debt and EBITDA | onset same period; build none; persists identity; recognized balance sheet | documented / documented / inferred / documented | none: an identity | net leverage | +0.96 sd/sd (identity) |
| 5 `sbk.id.leverage:softbank_corp.net_debt` | SoftBank Corp net debt to EBITDA = SoftBank Corp net debt / SoftBank Corp EBITDA: SoftBank Corp net debt is a numerator; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.55 sd/sd (identity) |
| 6 `sbk-c-leverage-dps` | A rising leverage ratio, from debt-funded investment and payouts, limits room for dividend increases under the company's financial discipline and credit ratings (SoftBank Corp (board)) | leverage near the level management or the rating agencies treat as a ceiling; observable: leverage against the dividend decision | onset at the next dividend decision; build none; persists while leverage is high; recognized dividend declared | inferred / inferred / unknown / unknown | a commitment to continuous dividend growth (cuts are unlikely) | dividend per share | unknown |

Unresolved inputs: leverage target or rating threshold (not disclosed in reviewed sources).

#### SoftBank Corp Japanese growth to Media & EC and enterprise IT

**Trigger:** Japanese growth picks up. **Endpoint:** SoftBank Corp net income.

Japan real GDP growth → [media] SoftBank Corp Media & EC revenue? → [it] Japan corporate IT spending? → SoftBank Corp Media & EC recurring segment income? → SoftBank Corp Media & EC segment income → SoftBank Corp operating income → SoftBank Corp minorities' share of Media & EC income → SoftBank Corp profit attributable to non-controlling interests → SoftBank Corp Enterprise solutions revenue? → SoftBank Corp Enterprise revenue → SoftBank Corp Enterprise EBITDA → SoftBank Corp Enterprise segment income → SoftBank Corp operating income → SoftBank Corp net income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Parallel responses: advertising and commerce at LY Corporation (shared with minorities) and corporate IT budgets. s47 is the reduced form on operating income and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [media] `sbk-c-gdp-mediarev` | Advertising budgets and online shopping move with the economy, so LY Corporation's media and commerce revenue rises with growth (advertisers and shoppers) | no shift of search queries away from its services; observable: advertising revenue and e-commerce transaction value | onset 1-2 quarters; build quarters; persists a cycle; recognized revenue | broker / inferred / unknown / unknown | generative-AI search taking query share from search advertising; system incidents | Media & EC revenue | unknown |
| 2 [it] `sbk-c-gdp-itspend` | Corporate profits and confidence move IT budgets with the economy, with a lag (corporate IT buyers) | budgets set on recent profits; observable: IT services orders | onset 2-4 quarters; build a year; persists a cycle; recognized not an accounting item | inferred / inferred / unknown / unknown | structural modernization demand that holds in downturns | Japan corporate IT spending | unknown |
| 3 `sbk-c-mediarev-mediaop` | Advertising carries high incremental margins, so revenue growth lifts recurring segment income more than proportionately (LY Corporation) | costs (marketing, systems) held; observable: segment margin | onset same period; build none; persists while costs hold; recognized quarterly results | broker / broker / unknown / unknown | higher media and promotion spending | Media & EC recurring income | unknown |
| 4 `sbk-a-media-media-ec-recurring-op` | SoftBank Corp Media & EC recurring segment income is one part of SoftBank Corp Media & EC segment income (Media & EC segment income: recurring income plus one-off items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Media & EC segment income | +0.75 sd/sd (accounting) |
| 5 `sbk-a-op-media-ec-op` | SoftBank Corp Media & EC segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.37 sd/sd (accounting) |
| 6 `sbk-c-mediaop-nci` | LY Corporation is a listed subsidiary: its outside shareholders take their share of Media & EC profit, so a rise in segment income raises the minorities' deduction (a larger deduction) (LY Corporation's outside shareholders) | ownership unchanged; observable: profit attributable to non-controlling interests | onset same period; build none; persists while ownership holds; recognized quarterly results | documented / documented / inferred / documented | buying out minorities; share buybacks at the subsidiary | non-controlling interests | -0.82 sd/sd (identity) |
| 7 `sbk-a-nci-nci-lycorp` | SoftBank Corp minorities' share of Media & EC income is one part of SoftBank Corp profit attributable to non-controlling interests (non-controlling interests by subsidiary: LY Corporation, PayPay, other (negative values)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit attributable to non-controlling interests | +0.60 sd/sd (accounting) |
| 8 `sbk-c-itspend-solutions` | Corporate IT and modernization budgets drive demand for SoftBank's solutions, IoT and security services (corporate customers) | IT budgets growing; observable: solutions revenue; industry IT orders | onset 1-2 quarters; build quarters; persists while budgets hold; recognized revenue as delivered | broker / broker / unknown / unknown | IT budget cuts in a downturn; staffing constraints | solutions revenue | unknown |
| 9 `sbk-a-ent-enterprise-solutions-revenue` | SoftBank Corp Enterprise solutions revenue is one part of SoftBank Corp Enterprise revenue (Enterprise revenue by line: communications, solutions, cloud and AI); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise revenue | +0.30 sd/sd (accounting) |
| 10 `sbk-a-entebitda-enterprise-revenue` | SoftBank Corp Enterprise revenue is one part of SoftBank Corp Enterprise EBITDA (Enterprise EBITDA: Enterprise revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise EBITDA | +2.19 sd/sd (accounting) |
| 11 `sbk-a-entop-enterprise-ebitda` | SoftBank Corp Enterprise EBITDA is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +1.43 sd/sd (accounting) |
| 12 `sbk-a-op-enterprise-op` | SoftBank Corp Enterprise segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.24 sd/sd (accounting) |
| 13 `sbk-a-ni-noncontrolling-interests` | SoftBank Corp profit attributable to non-controlling interests is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.51 sd/sd (accounting) |
| 14 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 15 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: Media & EC incremental margin (found not connected); Media & EC revenue by business (media versus commerce) (not disclosed in reviewed sources); economic ownership of LY Corporation and PayPay (found connected); search advertising exposure to AI substitution (not disclosed in reviewed sources); solutions order intake (not disclosed in reviewed sources).

#### SoftBank Corp corporate IT demand to net income

**Trigger:** corporate IT and modernization spending rises. **Endpoint:** SoftBank Corp net income.

Japan corporate IT spending → [solutions] SoftBank Corp Enterprise solutions revenue? → [distribution] SoftBank Corp Distribution revenue? → SoftBank Corp Enterprise revenue → SoftBank Corp Enterprise EBITDA → SoftBank Corp Enterprise segment income → SoftBank Corp operating income → SoftBank Corp Distribution segment income → SoftBank Corp operating income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Parallel responses: solutions revenue in Enterprise and IT product volumes in Distribution (thin margin).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [solutions] `sbk-c-itspend-solutions` | Corporate IT and modernization budgets drive demand for SoftBank's solutions, IoT and security services (corporate customers) | IT budgets growing; observable: solutions revenue; industry IT orders | onset 1-2 quarters; build quarters; persists while budgets hold; recognized revenue as delivered | broker / broker / unknown / unknown | IT budget cuts in a downturn; staffing constraints | solutions revenue | unknown |
| 2 [distribution] `sbk-c-itspend-distribution` | Corporate PC and software refresh cycles (an operating-system end of support) drive the Distribution segment's volumes (corporate customers and resellers) | a refresh cycle under way; observable: distribution revenue against PC shipments | onset within the quarter; build the refresh cycle; persists ends with the cycle; recognized revenue at shipment | broker / broker / unknown / broker | the end of a refresh cycle | Distribution revenue | unknown |
| 3 `sbk-a-ent-enterprise-solutions-revenue` | SoftBank Corp Enterprise solutions revenue is one part of SoftBank Corp Enterprise revenue (Enterprise revenue by line: communications, solutions, cloud and AI); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise revenue | +0.30 sd/sd (accounting) |
| 4 `sbk-a-entebitda-enterprise-revenue` | SoftBank Corp Enterprise revenue is one part of SoftBank Corp Enterprise EBITDA (Enterprise EBITDA: Enterprise revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise EBITDA | +2.19 sd/sd (accounting) |
| 5 `sbk-a-entop-enterprise-ebitda` | SoftBank Corp Enterprise EBITDA is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +1.43 sd/sd (accounting) |
| 6 `sbk-a-op-enterprise-op` | SoftBank Corp Enterprise segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.24 sd/sd (accounting) |
| 7 `sbk-c-distrev-distop` | Distribution earns a low single-digit margin on its revenue, so income moves with volume at that margin (none (arithmetic)) | the margin holds; observable: segment margin | onset same period; build none; persists while the margin holds; recognized quarterly results | broker / documented / inferred / documented | mix shifts and vendor rebates | Distribution segment income | +0.67 sd/sd (identity) |
| 8 `sbk-a-op-distribution-op` | SoftBank Corp Distribution segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.06 sd/sd (accounting) |
| 9 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 10 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: solutions order intake (not disclosed in reviewed sources).

#### SoftBank Corp Japanese inflation to net income

**Trigger:** Japanese inflation persists. **Endpoint:** SoftBank Corp net income.

Japan core CPI → [pricing] SoftBank Corp existing-plan mobile tariff index? → [consumer_costs] SoftBank Corp Consumer cash operating costs? → [enterprise_costs] SoftBank Corp Enterprise cash operating costs? → [payments] PayPay payment GMV? → SoftBank Corp mobile ARPU? → SoftBank Corp Consumer mobile service revenue → SoftBank Corp Consumer revenue → SoftBank Corp Consumer EBITDA → SoftBank Corp Consumer EBITDA → SoftBank Corp Consumer segment income → SoftBank Corp operating income → SoftBank Corp Enterprise EBITDA → SoftBank Corp Enterprise segment income → SoftBank Corp operating income → SoftBank Corp Financial revenue? → SoftBank Corp PayPay and other financial income? → SoftBank Corp Financial segment income → SoftBank Corp operating income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Parallel responses: pricing power (an existing-plan increase becomes acceptable), costs rise in Consumer and Enterprise, and nominal payment values rise. The BoJ's response (m08) is a separate path (sbk.path.policy_rate).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [pricing] `sbk-c-cpi-tariff` | Sustained inflation gives operators a reason subscribers accept for raising existing-plan prices; a rival's inflation-justified increase did not raise cancellations much, which set a precedent (SoftBank Corp (pricing)) | inflation persists and rivals follow or hold; the regulator tolerates increases; observable: price-increase announcements across operators | onset a year or more after inflation sets in; build a single step; persists years; recognized service revenue after the increase | broker / broker / unknown / unknown | regulatory or political pushback; a rival keeping prices low for share | mobile tariff level | unknown |
| 2 [consumer_costs] `sbk-c-cpi-conscosts` | Inflation raises wages, outsourcing, energy and handset costs in Consumer operating expenses (a larger charge) (suppliers and employees) | costs reprice with inflation (wage rounds, contracts); observable: operating expenses in segment results | onset quarters; build a year; persists persistent; recognized operating expenses | broker / inferred / unknown / unknown | efficiency programmes | Consumer cash costs | unknown |
| 3 [enterprise_costs] `sbk-c-cpi-entcosts` | Inflation raises personnel and subcontracting costs in Enterprise solutions (a larger charge) (suppliers and employees) | costs reprice faster than contracts; observable: Enterprise operating expenses | onset quarters; build a year; persists persistent; recognized operating expenses | inferred / inferred / unknown / unknown | contract repricing | Enterprise cash costs | unknown |
| 4 [payments] `sbk-c-cpi-gmv` | Higher consumer prices raise the yen value of each payment, so PayPay GMV rises with nominal spending (consumers) | real spending holds; observable: average transaction value | onset within the quarter; build none; persists while prices hold; recognized GMV each month | broker / inferred / unknown / unknown | real spending falling | PayPay GMV | unknown |
| 5 `sbk-c-tariff-arpu` | A higher tariff on existing SoftBank and Y!mobile plans raises revenue per subscriber as the new price reaches the base; together with migration to larger-data plans it turned ARPU up after years of decline (SoftBank Corp (pricing)) | the increase applies to the existing base, not only new contracts, and churn stays contained; observable: mobile ARPU, quarterly; the yoy change in ARPU after the increase month | onset the month the new tariff takes effect (July 2026); build one quarter to the full run rate; persists while the tariff holds and is not discounted back; recognized service revenue each month | documented / documented / unknown / broker | discounts or loyalty offers that hand the increase back; down-trading to the cheaper brands; regulatory pressure on charges | mobile ARPU | unknown |
| 6 `sbk-c-arpu-mobile` | Mobile service revenue is ARPU times average subscribers: a higher ARPU on the same base raises consumer mobile revenue (none (arithmetic)) | the consumer share of the main-subscriber base is stable; observable: mobile service revenue against ARPU x average subscribers | onset same period; build none; persists identity; recognized service revenue each month | documented / documented / inferred / documented | none: an identity; a shift of lines between consumer and enterprise changes the share | Consumer mobile service revenue | +1.00 sd/sd (identity) |
| 7 `sbk-a-cons-consumer-mobile-revenue` | SoftBank Corp Consumer mobile service revenue is one part of SoftBank Corp Consumer revenue (Consumer revenue by line: mobile service, broadband, electricity, handsets and merchandise); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer revenue | +0.36 sd/sd (accounting) |
| 8 `sbk-a-consebitda-consumer-revenue` | SoftBank Corp Consumer revenue is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +2.39 sd/sd (accounting) |
| 9 `sbk-a-consebitda-consumer-cash-costs` | SoftBank Corp Consumer cash operating costs is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +1.06 sd/sd (accounting) |
| 10 `sbk-a-consop-consumer-ebitda` | SoftBank Corp Consumer EBITDA is one part of SoftBank Corp Consumer segment income (Consumer segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer segment income | +1.34 sd/sd (accounting) |
| 11 `sbk-a-op-consumer-op` | SoftBank Corp Consumer segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.42 sd/sd (accounting) |
| 12 `sbk-a-entebitda-enterprise-cash-costs` | SoftBank Corp Enterprise cash operating costs is one part of SoftBank Corp Enterprise EBITDA (Enterprise EBITDA: Enterprise revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise EBITDA | +0.88 sd/sd (accounting) |
| 13 `sbk-a-entop-enterprise-ebitda` | SoftBank Corp Enterprise EBITDA is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +1.43 sd/sd (accounting) |
| 14 `sbk-a-op-enterprise-op` | SoftBank Corp Enterprise segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.24 sd/sd (accounting) |
| 15 `sbk-c-gmv-finrev` | Payment revenue is GMV times the merchant fee rate (plus card and bank revenue riding on the same users) (PayPay (merchant pricing)) | the merchant fee rate holds; observable: payment revenue against GMV | onset same period; build none; persists while the fee holds; recognized revenue | broker / inferred / unknown / unknown | fee-free campaigns; regulation of merchant fees | Financial revenue | unknown |
| 16 `sbk-c-finrev-paypayop` | With a largely fixed cost base and point benefits being reviewed, revenue growth lifts PayPay's income more than proportionately (PayPay) | points and promotion costs held; observable: segment margin | onset same period; build none; persists while costs hold; recognized quarterly results | broker / broker / unknown / unknown | point campaigns to defend share; credit costs at the card business | PayPay income | unknown |
| 17 `sbk-a-fin-paypay-and-other-op` | SoftBank Corp PayPay and other financial income is one part of SoftBank Corp Financial segment income (Financial segment income: SB Payment Service and PayPay with the other financial businesses); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Financial segment income | +1.00 sd/sd (accounting) |
| 18 `sbk-a-op-financial-op` | SoftBank Corp Financial segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.20 sd/sd (accounting) |
| 19 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 20 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: Financial incremental margin (found not connected); PayPay merchant fee rate (not disclosed in reviewed sources); average transaction value (found connected); inflation-sensitive share of operating costs (not disclosed in reviewed sources); size of the existing-plan price increase (percent and plans covered) (not disclosed in reviewed sources); tariff response to inflation (found connected).

#### SoftBank Corp JGB yields to net income

**Trigger:** JGB 10-year yields rise. **Endpoint:** SoftBank Corp net income.

JGB 10Y yield → [refinancing] SoftBank Corp average borrowing cost? → [build] SoftBank Corp AI data-center investment → [valuation] SoftBank Corp share price? → SoftBank Corp interest expense → SoftBank Corp profit before tax → SoftBank Corp Enterprise depreciation and amortization? → SoftBank Corp Enterprise segment income → SoftBank Corp AI compute capacity in service? → SoftBank Corp Enterprise cloud and AI revenue? → SoftBank Corp Enterprise revenue → SoftBank Corp Enterprise EBITDA → SoftBank Corp Enterprise segment income → SoftBank Corp operating income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Parallel responses: debt reprices as it is refinanced (interest expense), the build slows (s49: less depreciation now, less capacity later), and the yield stock re-rates. m33 is the reduced form on operating income kept for Sally's expected paths; it is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [refinancing] `sbk-c-jgb-borrowcost` | New bonds and term loans are priced off the yen curve plus a credit spread; as debt matures and the AI build adds debt, the average cost climbs toward current yields (bond investors and banks; SoftBank Corp (treasury)) | debt maturing or added at current yields; the credit spread holds; observable: coupons on new issues; interest paid | onset at each refinancing; build years (the ladder); persists the life of new debt; recognized interest expense | broker / inferred / unknown / unknown | a lower credit spread; hybrid or equity funding | average borrowing cost | unknown |
| 2 [build] `s49` | Higher yields raise the hurdle and the funding cost of the debt-financed AI build, so management paces later phases more slowly (SoftBank Corp (investment decision)) | the build is debt-funded and not yet committed; observable: announced phases and investment plans | onset at the next phase decision; build a year or more; persists while yields stay high; recognized capex as spent | inferred / inferred / assumption / unknown | committed phases and customer contracts; strategic priority on sovereign AI | AI investment | -0.20 sd/sd |
| 3 [valuation] `sbk-c-jgb-shareprice` | A high-yield, stable-dividend telecom trades partly as a bond proxy: higher JGB yields narrow its yield premium and raise the discount rate (equity investors) | the stock held for income; observable: dividend yield against the JGB yield | onset days; build weeks; persists while yields hold; recognized market price | broker / inferred / unknown / unknown | earnings growth from AI and PayPay re-rating the stock as growth rather than yield | share price | unknown |
| 4 `sbk-c-borrowcost-intexp` | Interest expense is the average borrowing cost times debt: a higher cost on the same debt raises the charge (none (arithmetic)) | debt unchanged; observable: interest paid | onset same period; build none; persists identity; recognized finance costs | documented / documented / inferred / documented | none: an identity | interest expense | -0.97 sd/sd (identity) |
| 5 `sbk-a-pretax-interest-expense` | SoftBank Corp interest expense is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.14 sd/sd (accounting) |
| 6 `sbk-c-aicapex-entdep` | GPU servers and data-centre assets are depreciated over short useful lives, so the AI build raises Enterprise depreciation (a larger charge) soon after commissioning, before utilization ramps (none (accounting)) | assets in service; observable: Enterprise D&A | onset at commissioning; build builds with each phase; persists useful life of the servers; recognized depreciation each quarter | broker / documented / unknown / inferred | lease or partner financing that moves cost into opex | Enterprise depreciation | unknown |
| 7 `sbk-a-entop-enterprise-depreciation` | SoftBank Corp Enterprise depreciation and amortization is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +0.75 sd/sd (accounting) |
| 8 `sbk-c-aicapex-capacity` | Investment becomes rentable capacity when a data centre is commissioned; the large new sites start in the second half of one fiscal year and the next, so capacity lags spending by quarters (SoftBank Corp (construction)) | construction, power connection and GPU delivery on schedule; observable: data-centre commissioning dates | onset at commissioning (2-6 quarters after spend); build phase by phase; persists the asset life; recognized capacity, not an account | broker / broker / unknown / broker | construction or power-connection delays | AI compute capacity | unknown |
| 9 `sbk-c-capacity-cloudai` | AI computing revenue is capacity in service times utilization times the rental price: more capacity at the same use raises cloud and AI revenue (none (arithmetic)) | utilization holds as capacity is added; observable: cloud and AI revenue against capacity added | onset same period; build none; persists identity; recognized rental revenue | broker / inferred / unknown / unknown | price declines per GPU-hour as newer chips arrive | cloud and AI revenue | unknown |
| 10 `sbk-a-ent-enterprise-cloud-ai-revenue` | SoftBank Corp Enterprise cloud and AI revenue is one part of SoftBank Corp Enterprise revenue (Enterprise revenue by line: communications, solutions, cloud and AI); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise revenue | +0.60 sd/sd (accounting) |
| 11 `sbk-a-entebitda-enterprise-revenue` | SoftBank Corp Enterprise revenue is one part of SoftBank Corp Enterprise EBITDA (Enterprise EBITDA: Enterprise revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise EBITDA | +2.19 sd/sd (accounting) |
| 12 `sbk-a-entop-enterprise-ebitda` | SoftBank Corp Enterprise EBITDA is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +1.43 sd/sd (accounting) |
| 13 `sbk-a-op-enterprise-op` | SoftBank Corp Enterprise segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.24 sd/sd (accounting) |
| 14 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 15 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: AI asset useful lives (not disclosed in reviewed sources); AI compute revenue by component (not disclosed in reviewed sources); coupons on recent issues (not disclosed in reviewed sources); data-centre capacity by site and date (found connected); debt maturity ladder (not disclosed in reviewed sources); how the AI build is financed (capex, leases, partners) (not disclosed in reviewed sources); share-price sensitivity to JGB yields (not disclosed in reviewed sources).

#### SoftBank Corp PayPay growth to net income

**Trigger:** PayPay's transacting users grow. **Endpoint:** SoftBank Corp net income.

PayPay monthly transacting users → PayPay payment GMV → SoftBank Corp Financial revenue? → SoftBank Corp PayPay and other financial income? → SoftBank Corp Financial segment income → SoftBank Corp operating income → SoftBank Corp minorities' share of Financial income → SoftBank Corp profit attributable to non-controlling interests → SoftBank Corp net income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Users x frequency x ticket = GMV; GMV x fee rate = revenue; operating leverage to income; a large share goes to minorities.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `sbk-c-mtu-gmv` | PayPay GMV is monthly transacting users times payments per user times the average ticket: more users raise GMV (none (arithmetic)) | frequency and ticket per user hold; observable: MTU and payments per user | onset same period; build none; persists identity; recognized GMV each month | documented / documented / inferred / documented | none: an identity | PayPay GMV | +0.60 sd/sd (identity) |
| 2 `sbk-c-gmv-finrev` | Payment revenue is GMV times the merchant fee rate (plus card and bank revenue riding on the same users) (PayPay (merchant pricing)) | the merchant fee rate holds; observable: payment revenue against GMV | onset same period; build none; persists while the fee holds; recognized revenue | broker / inferred / unknown / unknown | fee-free campaigns; regulation of merchant fees | Financial revenue | unknown |
| 3 `sbk-c-finrev-paypayop` | With a largely fixed cost base and point benefits being reviewed, revenue growth lifts PayPay's income more than proportionately (PayPay) | points and promotion costs held; observable: segment margin | onset same period; build none; persists while costs hold; recognized quarterly results | broker / broker / unknown / unknown | point campaigns to defend share; credit costs at the card business | PayPay income | unknown |
| 4 `sbk-a-fin-paypay-and-other-op` | SoftBank Corp PayPay and other financial income is one part of SoftBank Corp Financial segment income (Financial segment income: SB Payment Service and PayPay with the other financial businesses); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Financial segment income | +1.00 sd/sd (accounting) |
| 5 `sbk-a-op-financial-op` | SoftBank Corp Financial segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.20 sd/sd (accounting) |
| 6 `sbk-c-finop-nci` | PayPay is listed and partly owned through LY Corporation, so much of Financial profit belongs to outside shareholders (PayPay's and LY Corporation's outside shareholders) | ownership unchanged; observable: profit attributable to non-controlling interests | onset same period; build none; persists while ownership holds; recognized quarterly results | documented / documented / inferred / documented | changes in ownership | non-controlling interests | -0.84 sd/sd (identity) |
| 7 `sbk-a-nci-nci-paypay` | SoftBank Corp minorities' share of Financial income is one part of SoftBank Corp profit attributable to non-controlling interests (non-controlling interests by subsidiary: LY Corporation, PayPay, other (negative values)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit attributable to non-controlling interests | +0.40 sd/sd (accounting) |
| 8 `sbk-a-ni-noncontrolling-interests` | SoftBank Corp profit attributable to non-controlling interests is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.51 sd/sd (accounting) |
| 9 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 10 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: Financial incremental margin (found not connected); PayPay merchant fee rate (not disclosed in reviewed sources); economic ownership of LY Corporation and PayPay (found connected).

#### SoftBank Corp BoJ policy rate to net income

**Trigger:** the BoJ raises the policy rate. **Endpoint:** SoftBank Corp net income.

BoJ policy rate → [funding] SoftBank Corp average borrowing cost? → [paypay_bank] SoftBank Corp banking net interest margin? → SoftBank Corp interest expense → SoftBank Corp profit before tax → SoftBank Corp Financial revenue? → SoftBank Corp PayPay and other financial income? → SoftBank Corp Financial segment income → SoftBank Corp operating income → SoftBank Corp minorities' share of Financial income → SoftBank Corp profit attributable to non-controlling interests → SoftBank Corp net income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

A counter-path inside the group: short-term and floating debt reprice (interest expense up, below operating income) while PayPay Bank's margin widens (Financial income up, part of it to minorities).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [funding] `sbk-c-boj-borrowcost` | Short-term borrowings, commercial paper and floating-rate loans reprice with the policy rate within months, raising the average cost of debt (lenders; SoftBank Corp (treasury)) | a share of debt is short-term or floating; observable: short-term debt and interest paid | onset 1-3 months; build quarters; persists while the rate holds; recognized interest expense | documented / inferred / unknown / unknown | fixing the rate (bonds, swaps); paying down short-term debt | average borrowing cost | unknown |
| 2 [paypay_bank] `sbk-c-boj-nim` | PayPay Bank funds itself mostly with low-rate retail deposits that reprice slowly, while loans and securities reprice with market rates: a hike widens its margin (PayPay Bank (treasury)) | deposit rates lag the policy rate (low deposit beta); observable: PayPay Bank net interest income | onset within the quarter; build 2-4 quarters; persists while the rate holds; recognized interest income | inferred / inferred / unknown / unknown | deposit competition raising deposit rates; fixed-rate assets | banking margin | unknown |
| 3 `sbk-c-borrowcost-intexp` | Interest expense is the average borrowing cost times debt: a higher cost on the same debt raises the charge (none (arithmetic)) | debt unchanged; observable: interest paid | onset same period; build none; persists identity; recognized finance costs | documented / documented / inferred / documented | none: an identity | interest expense | -0.97 sd/sd (identity) |
| 4 `sbk-a-pretax-interest-expense` | SoftBank Corp interest expense is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.14 sd/sd (accounting) |
| 5 `sbk-c-nim-finrev` | Bank net interest income is the margin times the balance: a wider margin on the same deposits raises Financial revenue (none (arithmetic)) | balances hold; observable: PayPay Bank results | onset same period; build none; persists identity; recognized interest income | inferred / documented / unknown / documented | none: an identity | Financial revenue | unknown |
| 6 `sbk-c-finrev-paypayop` | With a largely fixed cost base and point benefits being reviewed, revenue growth lifts PayPay's income more than proportionately (PayPay) | points and promotion costs held; observable: segment margin | onset same period; build none; persists while costs hold; recognized quarterly results | broker / broker / unknown / unknown | point campaigns to defend share; credit costs at the card business | PayPay income | unknown |
| 7 `sbk-a-fin-paypay-and-other-op` | SoftBank Corp PayPay and other financial income is one part of SoftBank Corp Financial segment income (Financial segment income: SB Payment Service and PayPay with the other financial businesses); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Financial segment income | +1.00 sd/sd (accounting) |
| 8 `sbk-a-op-financial-op` | SoftBank Corp Financial segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.20 sd/sd (accounting) |
| 9 `sbk-c-finop-nci` | PayPay is listed and partly owned through LY Corporation, so much of Financial profit belongs to outside shareholders (PayPay's and LY Corporation's outside shareholders) | ownership unchanged; observable: profit attributable to non-controlling interests | onset same period; build none; persists while ownership holds; recognized quarterly results | documented / documented / inferred / documented | changes in ownership | non-controlling interests | -0.84 sd/sd (identity) |
| 10 `sbk-a-nci-nci-paypay` | SoftBank Corp minorities' share of Financial income is one part of SoftBank Corp profit attributable to non-controlling interests (non-controlling interests by subsidiary: LY Corporation, PayPay, other (negative values)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit attributable to non-controlling interests | +0.40 sd/sd (accounting) |
| 11 `sbk-a-ni-noncontrolling-interests` | SoftBank Corp profit attributable to non-controlling interests is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.51 sd/sd (accounting) |
| 12 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 13 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: Financial incremental margin (found not connected); PayPay Bank rate sensitivity (asset and deposit repricing) (not disclosed in reviewed sources); debt maturity ladder (not disclosed in reviewed sources); economic ownership of LY Corporation and PayPay (found connected); share of floating-rate and short-term debt (found connected).

#### SoftBank Corp power prices to net income

**Trigger:** Japanese wholesale power prices rise. **Endpoint:** SoftBank Corp net income.

Japan wholesale power price → [passthrough] SoftBank Corp Consumer electricity revenue? → [procurement] SoftBank Corp Consumer cash operating costs? → [datacenters] SoftBank Corp Enterprise cash operating costs? → SoftBank Corp Consumer revenue → SoftBank Corp Consumer EBITDA → SoftBank Corp Consumer EBITDA → SoftBank Corp Enterprise EBITDA → SoftBank Corp Consumer segment income → SoftBank Corp Enterprise segment income → SoftBank Corp operating income → SoftBank Corp operating income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Offsetting branches: electricity retail revenue passes the cost on with a lag, while procurement, network and data-centre power costs rise at once.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [passthrough] `sbk-c-power-elecrev` | SoftBank Denki's retail tariffs carry a fuel-cost adjustment, so higher wholesale and fuel costs raise electricity revenue with a lag (SoftBank Corp (electricity retail)) | the adjustment formula covers the cost increase; observable: electricity revenue against wholesale prices | onset 1-3 months (adjustment lag); build a quarter; persists while prices hold; recognized revenue | inferred / inferred / unknown / unknown | caps on the adjustment; customer losses | electricity revenue | unknown |
| 2 [procurement] `sbk-c-power-conscosts` | Higher wholesale power prices raise SoftBank Denki's procurement cost and the network's power bill (a larger charge), ahead of the pass-through (SoftBank Corp (procurement)) | procurement at market prices; observable: electricity segment margin | onset immediate; build a quarter; persists while prices hold; recognized operating expenses | inferred / inferred / unknown / unknown | hedges and fixed-price procurement | Consumer cash costs | unknown |
| 3 [datacenters] `sbk-c-power-entcosts` | AI data centres are power-intensive: higher power prices raise Enterprise operating costs unless contracts pass them on (SoftBank Corp (data centres)) | power bought at market-linked prices; observable: data-centre operating costs | onset immediate; build grows with capacity; persists while prices hold; recognized operating expenses | inferred / inferred / unknown / unknown | power purchase agreements; pass-through clauses in compute contracts | Enterprise cash costs | unknown |
| 4 `sbk-a-cons-consumer-electricity-revenue` | SoftBank Corp Consumer electricity revenue is one part of SoftBank Corp Consumer revenue (Consumer revenue by line: mobile service, broadband, electricity, handsets and merchandise); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer revenue | +0.33 sd/sd (accounting) |
| 5 `sbk-a-consebitda-consumer-revenue` | SoftBank Corp Consumer revenue is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +2.39 sd/sd (accounting) |
| 6 `sbk-a-consebitda-consumer-cash-costs` | SoftBank Corp Consumer cash operating costs is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +1.06 sd/sd (accounting) |
| 7 `sbk-a-entebitda-enterprise-cash-costs` | SoftBank Corp Enterprise cash operating costs is one part of SoftBank Corp Enterprise EBITDA (Enterprise EBITDA: Enterprise revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise EBITDA | +0.88 sd/sd (accounting) |
| 8 `sbk-a-consop-consumer-ebitda` | SoftBank Corp Consumer EBITDA is one part of SoftBank Corp Consumer segment income (Consumer segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer segment income | +1.34 sd/sd (accounting) |
| 9 `sbk-a-entop-enterprise-ebitda` | SoftBank Corp Enterprise EBITDA is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +1.43 sd/sd (accounting) |
| 10 `sbk-a-op-consumer-op` | SoftBank Corp Consumer segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.42 sd/sd (accounting) |
| 11 `sbk-a-op-enterprise-op` | SoftBank Corp Enterprise segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.24 sd/sd (accounting) |
| 12 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 13 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: data-centre power consumption and contract terms (not disclosed in reviewed sources); electricity pass-through formula and lag (not disclosed in reviewed sources); power procurement cost and hedges (not disclosed in reviewed sources).

#### SoftBank Corp mobile price competition to net income

**Trigger:** rivals cut prices or a low-price challenger gains share. **Endpoint:** SoftBank Corp net income.

Japan mobile competitor price pressure → [churn] SoftBank Corp mobile churn rate? → [promotion] Japan mobile promotion intensity? → [arpu] SoftBank Corp mobile ARPU? → SoftBank Corp mobile cancellations → SoftBank Corp mobile main subscribers → SoftBank Corp Consumer mobile service revenue → SoftBank Corp Consumer mobile service revenue → SoftBank Corp Consumer cash operating costs? → SoftBank Corp Consumer handset and merchandise revenue? → SoftBank Corp Consumer revenue → SoftBank Corp Consumer revenue → SoftBank Corp Consumer EBITDA → SoftBank Corp Consumer EBITDA → SoftBank Corp Consumer segment income → SoftBank Corp operating income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Parallel responses of one competitive move: subscribers leave, the industry promotes harder (sales costs up, more handsets sold at low margin), and SoftBank answers with its cheaper brands (ARPU down).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [churn] `sbk-c-competition-churn` | Rivals' cheaper plans and a low-price challenger's network push price-sensitive subscribers to switch (rival operators and switching subscribers) | the rival's network is good enough and switching is easy; observable: number portability flows; the challenger's net additions | onset 1-2 months; build quarters; persists while the price gap lasts; recognized subscriber count | broker / broker / unknown / broker | the challenger's network quality falling (roaming area shrinking); rivals raising prices too | churn rate | unknown |
| 2 [promotion] `sbk-c-competition-promo` | Operators answer subscriber losses with handset discounts, points and agent incentives rather than list-price cuts (operators (sales strategy)) | operators prioritize share over lifetime value; observable: industry sales promotion costs; gross additions | onset within the quarter; build 1-2 quarters; persists until a strategy shift; recognized sales-related expenses | broker / broker / unknown / broker | a shift to lifetime-value strategies; the cap on handset discounts | promotion intensity | unknown |
| 3 [arpu] `sbk-c-competition-arpu` | SoftBank answers rivals' low prices with its cheaper brands (Y!mobile, LINEMO); subscribers who move down lower ARPU (SoftBank Corp (brand strategy) and subscribers) | the low-price brands are positioned against the challenger; observable: brand migration; ARPU by brand | onset 1-2 quarters; build several quarters; persists persistent once migrated; recognized service revenue | broker / broker / unknown / unknown | plan-mix upgrades to large-data plans | mobile ARPU | unknown |
| 4 `sbk-c-churn-cancellations` | Subscribers are a stock: each month's churn removes a share of the base; with gross additions unchanged a higher churn rate lowers subscribers (subscribers) | gross additions do not rise to offset; observable: quarterly net additions | onset within the month; build accumulates while churn stays high; persists until churn normalizes; recognized period-end subscriber count | documented / documented / inferred / inferred | gross additions (promotions, Y!mobile, MNP); bundles that lower churn | main subscribers | +1.00 sd/sd (identity) |
| 5 `sbk-c-cancellations-subs` | Subscribers are a stock: cancellations each quarter drain the base, gross additions refill it; revenue uses the period average (subscribers) | gross additions unchanged; observable: quarterly net additions | onset within the quarter; build accumulates; persists until reversed by additions; recognized period-end and average subscriber counts | documented / documented / inferred / inferred | gross additions (promotions, the cheaper brands, number portability in) | main subscribers | -0.30 sd/sd (stock-flow, accumulates per 91 days) |
| 6 `sbk-c-subs-mobile` | Mobile service revenue is ARPU times average subscribers: more subscribers at the same ARPU raise consumer mobile revenue (none (arithmetic)) | ARPU of added or lost lines near the average (short-term users have lower ARPU); observable: net additions and their mix by brand | onset same period; build none; persists identity; recognized service revenue each month | documented / documented / inferred / documented | none: an identity | Consumer mobile service revenue | +0.50 sd/sd (identity) |
| 7 `sbk-c-arpu-mobile` | Mobile service revenue is ARPU times average subscribers: a higher ARPU on the same base raises consumer mobile revenue (none (arithmetic)) | the consumer share of the main-subscriber base is stable; observable: mobile service revenue against ARPU x average subscribers | onset same period; build none; persists identity; recognized service revenue each month | documented / documented / inferred / documented | none: an identity; a shift of lines between consumer and enterprise changes the share | Consumer mobile service revenue | +1.00 sd/sd (identity) |
| 8 `sbk-c-promo-costs` | Handset discounts, purchase programmes and agent commissions raise Consumer sales-related expenses (a larger charge); contract costs are capitalized and amortized, so the charge spreads over the contract (SoftBank Corp (sales)) | SoftBank matches the industry's promotions; observable: sales-related expenses in Consumer results commentary | onset within the quarter; build the amortization period of contract costs; persists while promotions last; recognized operating expenses; capitalized contract costs amortized | broker / broker / unknown / broker | the discount cap; a shift to retention | Consumer cash costs | unknown |
| 9 `sbk-c-promo-merch` | Promotions lift handset sales volumes, raising merchandise revenue; the matching cost of goods sits in cash costs, so the margin effect is small (subscribers (handset upgrades)) | handset supply and upgrade cycle; observable: handset sales volumes | onset within the quarter; build none; persists while promotions last; recognized at sale | broker / inferred / unknown / unknown | handset price increases dampen volumes | merchandise revenue | unknown |
| 10 `sbk-a-cons-consumer-merchandise-revenue` | SoftBank Corp Consumer handset and merchandise revenue is one part of SoftBank Corp Consumer revenue (Consumer revenue by line: mobile service, broadband, electricity, handsets and merchandise); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer revenue | +0.50 sd/sd (accounting) |
| 11 `sbk-a-cons-consumer-mobile-revenue` | SoftBank Corp Consumer mobile service revenue is one part of SoftBank Corp Consumer revenue (Consumer revenue by line: mobile service, broadband, electricity, handsets and merchandise); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer revenue | +0.36 sd/sd (accounting) |
| 12 `sbk-a-consebitda-consumer-revenue` | SoftBank Corp Consumer revenue is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +2.39 sd/sd (accounting) |
| 13 `sbk-a-consebitda-consumer-cash-costs` | SoftBank Corp Consumer cash operating costs is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +1.06 sd/sd (accounting) |
| 14 `sbk-a-consop-consumer-ebitda` | SoftBank Corp Consumer EBITDA is one part of SoftBank Corp Consumer segment income (Consumer segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer segment income | +1.34 sd/sd (accounting) |
| 15 `sbk-a-op-consumer-op` | SoftBank Corp Consumer segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.42 sd/sd (accounting) |
| 16 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 17 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: ARPU by brand and migration rates (not disclosed in reviewed sources); churn sensitivity to rivals' price gap (not disclosed in reviewed sources); gross additions by quarter (found not connected); handset volumes and average selling prices (not disclosed in reviewed sources); sales-related expenses by type (not disclosed in reviewed sources).

#### SoftBank Corp existing-plan price increase to net income

**Trigger:** SoftBank raises tariffs on existing mobile plans (from July 2026). **Endpoint:** SoftBank Corp net income.

SoftBank Corp existing-plan mobile tariff index → [arpu] SoftBank Corp mobile ARPU? → [churn] SoftBank Corp mobile churn rate? → [enterprise] SoftBank Corp Enterprise communications revenue? → [reinvest] SoftBank Corp telecom network investment? → SoftBank Corp Consumer mobile service revenue → SoftBank Corp mobile cancellations → SoftBank Corp mobile main subscribers → SoftBank Corp Consumer mobile service revenue → SoftBank Corp mobile network quality? → SoftBank Corp mobile churn rate? → SoftBank Corp Consumer revenue → SoftBank Corp Consumer EBITDA → SoftBank Corp Consumer segment income → SoftBank Corp Consumer depreciation and amortization? → SoftBank Corp Consumer segment income → SoftBank Corp Enterprise revenue → SoftBank Corp Enterprise EBITDA → SoftBank Corp Enterprise segment income → SoftBank Corp operating income → SoftBank Corp operating income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Parallel responses of one pricing decision: ARPU rises on the base, some subscribers leave, corporate lines reprice, and the extra cash is reinvested in the network (depreciation later; quality lowers churn). Revenue = subscribers x ARPU; EBITDA less D&A to segment income, then to the group.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [arpu] `sbk-c-tariff-arpu` | A higher tariff on existing SoftBank and Y!mobile plans raises revenue per subscriber as the new price reaches the base; together with migration to larger-data plans it turned ARPU up after years of decline (SoftBank Corp (pricing)) | the increase applies to the existing base, not only new contracts, and churn stays contained; observable: mobile ARPU, quarterly; the yoy change in ARPU after the increase month | onset the month the new tariff takes effect (July 2026); build one quarter to the full run rate; persists while the tariff holds and is not discounted back; recognized service revenue each month | documented / documented / unknown / broker | discounts or loyalty offers that hand the increase back; down-trading to the cheaper brands; regulatory pressure on charges | mobile ARPU | unknown |
| 2 [churn] `sbk-c-tariff-churn` | A price increase on existing plans prompts some subscribers to switch carrier or brand; the precedent of a rival's increase suggests cancellations stay limited when the increase is justified by inflation and added services (subscribers (switching decision)) | rivals do not cut prices at the same time; switching costs and bundles hold; observable: monthly smartphone churn against the same month a year earlier | onset within 1-2 months of the increase; build 1-2 quarters; persists fades as the base re-prices; recognized subscriber count each quarter | broker / broker / unknown / broker | rivals following with their own increases (removes the reason to switch); bundled broadband and payment benefits | churn rate | unknown |
| 3 [enterprise] `sbk-c-tariff-entcomms` | Mobile ARPU and subscription KPIs cut across Consumer and Enterprise: corporate lines on the repriced plans carry the increase into Enterprise communications revenue (SoftBank Corp (pricing)) | corporate contracts on the repriced tariffs (not negotiated enterprise pricing); observable: Enterprise communications revenue against corporate line count | onset the increase month; build 1-2 quarters; persists while the tariff holds; recognized service revenue | broker / inferred / unknown / unknown | negotiated enterprise contracts that are not repriced | Enterprise communications revenue | unknown |
| 4 [reinvest] `sbk-c-tariff-netcapex` | Management ties the increase to funding network quality: the extra cash flow from higher tariffs is reinvested in the network from the next fiscal year, which raises depreciation later (SoftBank Corp (capital allocation)) | the reinvestment plan holds; cash flow from the increase materializes; observable: network capex plans in results guidance | onset the next fiscal year; build 1-2 years; persists a multi-year programme; recognized capex as spent; depreciation over asset lives | broker / broker / unknown / broker | capital allocation shifted to the AI build or to dividends | network investment | unknown |
| 5 `sbk-c-arpu-mobile` | Mobile service revenue is ARPU times average subscribers: a higher ARPU on the same base raises consumer mobile revenue (none (arithmetic)) | the consumer share of the main-subscriber base is stable; observable: mobile service revenue against ARPU x average subscribers | onset same period; build none; persists identity; recognized service revenue each month | documented / documented / inferred / documented | none: an identity; a shift of lines between consumer and enterprise changes the share | Consumer mobile service revenue | +1.00 sd/sd (identity) |
| 6 `sbk-c-churn-cancellations` | Subscribers are a stock: each month's churn removes a share of the base; with gross additions unchanged a higher churn rate lowers subscribers (subscribers) | gross additions do not rise to offset; observable: quarterly net additions | onset within the month; build accumulates while churn stays high; persists until churn normalizes; recognized period-end subscriber count | documented / documented / inferred / inferred | gross additions (promotions, Y!mobile, MNP); bundles that lower churn | main subscribers | +1.00 sd/sd (identity) |
| 7 `sbk-c-cancellations-subs` | Subscribers are a stock: cancellations each quarter drain the base, gross additions refill it; revenue uses the period average (subscribers) | gross additions unchanged; observable: quarterly net additions | onset within the quarter; build accumulates; persists until reversed by additions; recognized period-end and average subscriber counts | documented / documented / inferred / inferred | gross additions (promotions, the cheaper brands, number portability in) | main subscribers | -0.30 sd/sd (stock-flow, accumulates per 91 days) |
| 8 `sbk-c-subs-mobile` | Mobile service revenue is ARPU times average subscribers: more subscribers at the same ARPU raise consumer mobile revenue (none (arithmetic)) | ARPU of added or lost lines near the average (short-term users have lower ARPU); observable: net additions and their mix by brand | onset same period; build none; persists identity; recognized service revenue each month | documented / documented / inferred / documented | none: an identity | Consumer mobile service revenue | +0.50 sd/sd (identity) |
| 9 `sbk-c-netcapex-quality` | Investment in base stations and capacity improves coverage, speed and consistency; a rival's base-station programme lifted its rankings within about a year (SoftBank Corp (network engineering)) | investment aimed at congested areas and 5G capacity; observable: third-party network experience rankings, semi-annual | onset 2-4 quarters; build 1-2 years; persists while maintained; recognized not an accounting item | broker / broker / unknown / broker | spectrum limits; rivals investing more | network quality | unknown |
| 10 `sbk-c-quality-churn` | Better network experience reduces quality-driven switching; as traffic per contract grows, connectivity matters more to retention (subscribers) | users notice the difference (urban congestion, video and gaming experience); observable: third-party network experience rankings; churn | onset 1-2 quarters; build several quarters; persists while the quality gap lasts; recognized subscriber count | broker / inferred / unknown / unknown | rivals closing the quality gap | churn rate | unknown |
| 11 `sbk-a-cons-consumer-mobile-revenue` | SoftBank Corp Consumer mobile service revenue is one part of SoftBank Corp Consumer revenue (Consumer revenue by line: mobile service, broadband, electricity, handsets and merchandise); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer revenue | +0.36 sd/sd (accounting) |
| 12 `sbk-a-consebitda-consumer-revenue` | SoftBank Corp Consumer revenue is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +2.39 sd/sd (accounting) |
| 13 `sbk-a-consop-consumer-ebitda` | SoftBank Corp Consumer EBITDA is one part of SoftBank Corp Consumer segment income (Consumer segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer segment income | +1.34 sd/sd (accounting) |
| 14 `sbk-c-netcapex-consdep` | Network assets are depreciated over their useful lives: more investment raises Consumer depreciation (a larger charge) for years after it is spent (none (accounting)) | assets placed in service; observable: depreciation and amortization in segment results | onset when assets enter service; build builds over the investment programme; persists useful lives (years); recognized depreciation each quarter | documented / documented / unknown / inferred | impairments; useful-life changes | Consumer depreciation | unknown |
| 15 `sbk-a-consop-consumer-depreciation` | SoftBank Corp Consumer depreciation and amortization is one part of SoftBank Corp Consumer segment income (Consumer segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer segment income | +0.54 sd/sd (accounting) |
| 16 `sbk-a-ent-enterprise-communications-revenue` | SoftBank Corp Enterprise communications revenue is one part of SoftBank Corp Enterprise revenue (Enterprise revenue by line: communications, solutions, cloud and AI); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise revenue | +0.40 sd/sd (accounting) |
| 17 `sbk-a-entebitda-enterprise-revenue` | SoftBank Corp Enterprise revenue is one part of SoftBank Corp Enterprise EBITDA (Enterprise EBITDA: Enterprise revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise EBITDA | +2.19 sd/sd (accounting) |
| 18 `sbk-a-entop-enterprise-ebitda` | SoftBank Corp Enterprise EBITDA is one part of SoftBank Corp Enterprise segment income (Enterprise segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Enterprise segment income | +1.43 sd/sd (accounting) |
| 19 `sbk-a-op-consumer-op` | SoftBank Corp Consumer segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.42 sd/sd (accounting) |
| 20 `sbk-a-op-enterprise-op` | SoftBank Corp Enterprise segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.24 sd/sd (accounting) |
| 21 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 22 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: churn response to the existing-plan price increase (not disclosed in reviewed sources); churn sensitivity to network quality (not disclosed in reviewed sources); gross additions by quarter (found not connected); network asset base and useful lives (found not connected); network quality response to investment (not disclosed in reviewed sources); network share of capital expenditure (not disclosed in reviewed sources); share of corporate lines on repriced tariffs (not disclosed in reviewed sources); size of the existing-plan price increase (percent and plans covered) (not disclosed in reviewed sources).

#### SoftBank Corp telecom regulation to net income

**Trigger:** the regulator tightens pricing rules or presses for lower charges. **Endpoint:** SoftBank Corp net income.

MIC pressure on mobile pricing → [tariffs] SoftBank Corp existing-plan mobile tariff index? → [discounts] Japan mobile promotion intensity? → [switching] SoftBank Corp mobile churn rate? → SoftBank Corp mobile ARPU? → SoftBank Corp Consumer mobile service revenue → SoftBank Corp Consumer cash operating costs? → SoftBank Corp Consumer handset and merchandise revenue? → SoftBank Corp mobile cancellations → SoftBank Corp mobile main subscribers → SoftBank Corp Consumer mobile service revenue → SoftBank Corp Consumer revenue → SoftBank Corp Consumer revenue → SoftBank Corp Consumer EBITDA → SoftBank Corp Consumer EBITDA → SoftBank Corp Consumer segment income → SoftBank Corp operating income → SoftBank Corp profit before tax → SoftBank Corp net income  (? marks a step whose size is unknown)

Parallel effects of one regulatory stance: pressure on tariffs (ARPU down), the cap on handset discounts (promotion costs and handset sales down: an offset), and easier switching (churn up).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [tariffs] `sbk-c-reg-tariff` | Government pressure on mobile charges pushes operators to cut or hold tariffs; a past round of such pressure cut industry ARPU for years (MIC and the government; SoftBank Corp (pricing)) | political focus on household telecom costs; observable: announcements of new low-price plans; regulator statements | onset months after the pressure begins; build 1-2 years; persists years; recognized service revenue | broker / inferred / unknown / unknown | inflation that makes price increases acceptable; a less interventionist policy stance | mobile tariff level | unknown |
| 2 [discounts] `sbk-c-reg-promo` | Rules capping handset discounts and separating handset from service pricing limit how hard operators can promote (MIC; operators) | rules enforced and not circumvented through points or trade-in; observable: regulator guidelines; promotion costs | onset when the rule takes effect; build quarters; persists while the rule holds; recognized sales-related expenses | documented / documented / unknown / unknown | workarounds (points, trade-in programmes) | promotion intensity | unknown |
| 3 [switching] `sbk-c-reg-churn` | Rules that lower switching costs (number portability fees, contract terms, eSIM) make it easier to leave (MIC; subscribers) | a price gap worth switching for; observable: number portability volumes | onset months; build quarters; persists persistent; recognized subscriber count | documented / inferred / unknown / unknown | bundles and loyalty benefits that keep switching costs economic | churn rate | unknown |
| 4 `sbk-c-tariff-arpu` | A higher tariff on existing SoftBank and Y!mobile plans raises revenue per subscriber as the new price reaches the base; together with migration to larger-data plans it turned ARPU up after years of decline (SoftBank Corp (pricing)) | the increase applies to the existing base, not only new contracts, and churn stays contained; observable: mobile ARPU, quarterly; the yoy change in ARPU after the increase month | onset the month the new tariff takes effect (July 2026); build one quarter to the full run rate; persists while the tariff holds and is not discounted back; recognized service revenue each month | documented / documented / unknown / broker | discounts or loyalty offers that hand the increase back; down-trading to the cheaper brands; regulatory pressure on charges | mobile ARPU | unknown |
| 5 `sbk-c-arpu-mobile` | Mobile service revenue is ARPU times average subscribers: a higher ARPU on the same base raises consumer mobile revenue (none (arithmetic)) | the consumer share of the main-subscriber base is stable; observable: mobile service revenue against ARPU x average subscribers | onset same period; build none; persists identity; recognized service revenue each month | documented / documented / inferred / documented | none: an identity; a shift of lines between consumer and enterprise changes the share | Consumer mobile service revenue | +1.00 sd/sd (identity) |
| 6 `sbk-c-promo-costs` | Handset discounts, purchase programmes and agent commissions raise Consumer sales-related expenses (a larger charge); contract costs are capitalized and amortized, so the charge spreads over the contract (SoftBank Corp (sales)) | SoftBank matches the industry's promotions; observable: sales-related expenses in Consumer results commentary | onset within the quarter; build the amortization period of contract costs; persists while promotions last; recognized operating expenses; capitalized contract costs amortized | broker / broker / unknown / broker | the discount cap; a shift to retention | Consumer cash costs | unknown |
| 7 `sbk-c-promo-merch` | Promotions lift handset sales volumes, raising merchandise revenue; the matching cost of goods sits in cash costs, so the margin effect is small (subscribers (handset upgrades)) | handset supply and upgrade cycle; observable: handset sales volumes | onset within the quarter; build none; persists while promotions last; recognized at sale | broker / inferred / unknown / unknown | handset price increases dampen volumes | merchandise revenue | unknown |
| 8 `sbk-c-churn-cancellations` | Subscribers are a stock: each month's churn removes a share of the base; with gross additions unchanged a higher churn rate lowers subscribers (subscribers) | gross additions do not rise to offset; observable: quarterly net additions | onset within the month; build accumulates while churn stays high; persists until churn normalizes; recognized period-end subscriber count | documented / documented / inferred / inferred | gross additions (promotions, Y!mobile, MNP); bundles that lower churn | main subscribers | +1.00 sd/sd (identity) |
| 9 `sbk-c-cancellations-subs` | Subscribers are a stock: cancellations each quarter drain the base, gross additions refill it; revenue uses the period average (subscribers) | gross additions unchanged; observable: quarterly net additions | onset within the quarter; build accumulates; persists until reversed by additions; recognized period-end and average subscriber counts | documented / documented / inferred / inferred | gross additions (promotions, the cheaper brands, number portability in) | main subscribers | -0.30 sd/sd (stock-flow, accumulates per 91 days) |
| 10 `sbk-c-subs-mobile` | Mobile service revenue is ARPU times average subscribers: more subscribers at the same ARPU raise consumer mobile revenue (none (arithmetic)) | ARPU of added or lost lines near the average (short-term users have lower ARPU); observable: net additions and their mix by brand | onset same period; build none; persists identity; recognized service revenue each month | documented / documented / inferred / documented | none: an identity | Consumer mobile service revenue | +0.50 sd/sd (identity) |
| 11 `sbk-a-cons-consumer-merchandise-revenue` | SoftBank Corp Consumer handset and merchandise revenue is one part of SoftBank Corp Consumer revenue (Consumer revenue by line: mobile service, broadband, electricity, handsets and merchandise); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer revenue | +0.50 sd/sd (accounting) |
| 12 `sbk-a-cons-consumer-mobile-revenue` | SoftBank Corp Consumer mobile service revenue is one part of SoftBank Corp Consumer revenue (Consumer revenue by line: mobile service, broadband, electricity, handsets and merchandise); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer revenue | +0.36 sd/sd (accounting) |
| 13 `sbk-a-consebitda-consumer-revenue` | SoftBank Corp Consumer revenue is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +2.39 sd/sd (accounting) |
| 14 `sbk-a-consebitda-consumer-cash-costs` | SoftBank Corp Consumer cash operating costs is one part of SoftBank Corp Consumer EBITDA (Consumer EBITDA: Consumer revenue less cash operating costs); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer EBITDA | +1.06 sd/sd (accounting) |
| 15 `sbk-a-consop-consumer-ebitda` | SoftBank Corp Consumer EBITDA is one part of SoftBank Corp Consumer segment income (Consumer segment income: EBITDA less depreciation and amortization); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Consumer segment income | +1.34 sd/sd (accounting) |
| 16 `sbk-a-op-consumer-op` | SoftBank Corp Consumer segment income is one part of SoftBank Corp operating income (IFRS operating income by reporting segment (segment income)); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating income | +0.42 sd/sd (accounting) |
| 17 `sbk-a-pretax-operating-profit` | SoftBank Corp operating income is one part of SoftBank Corp profit before tax (profit before tax: operating income less interest plus other non-operating items); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.94 sd/sd (accounting) |
| 18 `sbk-a-ni-pretax-income` | SoftBank Corp profit before tax is one part of SoftBank Corp net income (net income attributable to owners: profit before tax less tax less non-controlling interests); weight is its scale over the total's | IFRS, same fiscal period, JPY; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.79 sd/sd (accounting) |

Unresolved inputs: gross additions by quarter (found not connected); handset volumes and average selling prices (not disclosed in reviewed sources); regulatory scenario and its tariff effect (not disclosed in reviewed sources); sales-related expenses by type (not disclosed in reviewed sources); size of the existing-plan price increase (percent and plans covered) (not disclosed in reviewed sources).

## Validation

`tests/scenario/test_construction_softbank_corp.py` (loads sally_demo once; reads no client data; reads the tracked
construction file for the links' notes):

- Structure: no `validate_construction` problems for the company; the twelve compositions and thirteen paths exist;
  every path step has a transition, every uncalibrated step a sign and an "unknown" magnitude; the parallel responses
  of one driver are branches from it (the tariff level, competitor price pressure, the BoJ rate, the JGB 10Y, the power
  price); the reduced forms (m33, s47, s48) are never steps of their structural paths.
- Financial integrity: every part of an additive view has a fixed-weight accounting link equal to its native sd over
  the total's; one unit per view; the views that leave something out keep a residual or eliminations; the priors of
  every additive view reconcile within 0.5% (exactly); the segment revenue view crosses to the segment profit bridges
  through nested EBITDA compositions; one view drives operating income and the EBITDA bridge reconciles; the twelve
  identities reconcile at the priors; subscribers and debt are stock-flows.
- A telecom's economics: mobile revenue is subscribers x ARPU (`identity:` links) and subscribers a stock drained by
  churn (`stock-flow:`); a price increase raises ARPU, raises churn (the offset) and funds network investment
  (depreciation later, lower churn through quality); regulation cuts both ways (ARPU down, promotion costs down);
  funding costs reach profit before tax and net income but never operating income; a BoJ hike raises the borrowing
  cost and PayPay Bank's margin (a counter-path); minorities take part of Media & EC and Financial income.
- Calibration: the only new causal size is the dividend ladder (`sbk-c-ni-dps`, a ratchet, from the company's stated net-income
  thresholds, magnitude "guidance", ¥0.5 to ¥1.0 of DPS per ¥100bn of net income, lagged to the dividend decision);
  m33, s47, s48 and s49 keep their sizes with magnitude "assumption" and named unresolved inputs; every missing input
  says whether the supplied material was searched (no `not_yet_reviewed` remains); every untranslatable identity names
  its form or, after the conversion, why it was kept.
- Generalization: a yen carry-trade unwind, for which no SoftBank path was written, traced through every link (below).
- Delivery: compositions in `financial_bridge`, named paths as `business_construction` transmission paths, accounting
  links as `accounting_identity`, uncalibrated links as `represented_uncalibrated` with their sign, m33's transition in
  the export; new node ids returned by `/v1/world-models/sally_demo/graph`, the construction and trace endpoints.

Sally's expected paths (`tests/scenario/test_sally_expected_paths.py`) still pass: `operating_profit` and `ai_capex`
keep their ids, m33, s47, s48 and s49 keep their sizes and signs, and no new calibrated link enters operating income
(the new calibrated links are accounting parts and the dividend ladder, all downstream or fed only by uncalibrated
links). The Toyota, Tokio Marine and JPMorgan tests pass unchanged.

**Generalization trace (a yen carry-trade unwind).** `trace(g, "dollar_yen.carry_positioning", "softbank_corp")`: 7
routes, 6 reach a financial endpoint. Carry -> USD/JPY (m18, calibrated) -> the dollar-priced AI build
(`sbk-c-usdjpy-aicapex`) -> s48 -> operating income (calibrated end to end only through the reduced form), and
structurally -> Enterprise depreciation -> Enterprise income, -> capacity -> cloud and AI revenue -> Enterprise revenue,
and -> capex -> free cash flow -> debt; USD/JPY -> handset procurement -> Consumer cash costs -> EBITDA -> Consumer
income, and -> handset retail prices -> merchandise revenue -> Consumer revenue (an offset); USD/JPY -> TOPIX (s62)
-> s65 -> the share price. Where it stops: the share price (nothing leads on from it), and at the first composition
total on each route. What it does not reach: funding costs. Sally's world has no link from the yen to Japanese
inflation or to the BoJ, so a yen move never reprices SoftBank's debt or PayPay Bank's margin; that is a gap in the
shared macro structure, not in this build. A second trace, an oil shock (`oil.brent`), reaches SoftBank through Japan
CPI -> the BoJ -> JGB yields (m02, m08, m13: calibrated to m33 and s49 -> s48), through CPI to tariffs and costs, and
through Japanese power prices to SoftBank Denki and data-centre costs (97 routes, 64 reaching an endpoint).

## Conversion to the new forms (Oct 18, second round)

| | Before | After |
|---|---|---|
| Links touching SoftBank's values | 108 | 123 |
| Accounting | 35 | 40 |
| Identity / stock-flow (derived weights) | 0 / 0 | 25 / 4 |
| Calibrated causal (incl. one state-dependent) | 7 | 7 |
| Uncalibrated | 66 | 47 |
| Driving views of operating income | 2 (a PROBLEM) | 1 (segments); the EBITDA bridge reconciles |

Tagged steps (33, incl. the dividend ladder): 21 converted, 12 kept with a stated reason.
- **identity (18 tagged):** 13 converted to 12 identities: `sbk.id.mobile_revenue` (ARPU x subscribers x consumer
  share), `.distribution_margin`, `.paypay_gmv`, `.tax`, `.nci_lycorp`, `.nci_paypay` (attributable shares),
  `.interest`, `.net_debt`, `.leverage`, `.dividends`, `.fcf`. Kept 5: capacity and utilization into cloud and AI
  revenue (the AI-compute part is not disclosed) and GMV, bank margin and deposits into Financial revenue (several
  businesses, split not disclosed).
- **stock-flow (6):** 3 converted to `sbk.sf.subscribers` (with `sbk.id.cancellations` = churn x subscribers) and
  `sbk.sf.debt`. Kept 3: capex into Consumer and Enterprise D&A, and AI investment into capacity (no asset stock, life,
  or yen-to-capacity rate disclosed).
- **matrix (6):** 4 converted to nested accounting compositions (`sbk.comp.consumer_ebitda`,
  `sbk.comp.enterprise_ebitda`). Kept 2: network and AI investment into capex (bounded weights are not built).
- **state (3):** the dividend ladder converted to a ratchet (asymmetry, falls 0). Kept 2: the inflation-driven price
  increase (a discrete event) and the leverage cap (threshold not disclosed).
- New values the forms need: gross additions, cancellations, cash, net debt, operating cash flow, minorities by
  subsidiary, the outside shareholders' shares, effective tax rate, Distribution margin, GMV per user, shares
  outstanding, consumer share of the mobile base (synthetic priors).
- `mobile_tariff_level` was renamed `mobile_tariff_index` (KEYWORD: "level").

**Reconciliation now.** Priors: 14 additive views and 12 identities reconcile exactly. FY3/26 baselines: 13 views OK
(Consumer revenue lines 0.007%, net income 0.02%), the minorities view blocked (no split by subsidiary); identities
within 0.5% (dividends 0.07%, tax 0.13%, mobile revenue 0.05% with the consumer share derived), three blocked (churn
level and minority shares not disclosed). Stock-flow roll-forwards need two dated stock levels: one period is bound, so
none is checked. `bundles.py check` on the baselines passes (60 items): the reconciling view's items now fold.

**Coverage now (S-T1, BoJ hike).** 8 quantified links (s65, s49, m33, the pretax and net-income accounting links, the
tax identity, the share-price default, s48), 12 excluded. Operating income: 14 routes, 2 quantified (14%); 13 own steps
on those routes, 1 quantified: the quantified answer still comes from the reduced forms; the structural funding route
is now exact from borrowing cost to interest expense and pretax (identity), but its first step (BoJ or JGB to borrowing
cost) has no size. S-T2 (Fed cut): 5 quantified links, 9 excluded.

| Path | Calculated: causal | Calculated: identity and stock-flow | Accounting | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|---|
| `sbk.path.ai_compute` | s48 beside the path | `sbk-c-capex-fcf`, `sbk-c-fcf-debt`, `sbk-c-debt-intexp` | 8 | `sbk-c-aidemand-util` (+), `sbk-c-aidemand-aicapex` (+), `sbk-c-aicapex-capacity` (+), `sbk-c-capacity-cloudai` (+), `sbk-c-util-cloudai` (+), `sbk-c-aicapex-entdep` (-), `sbk-c-aicapex-capex` (+) | data-centre capacity by site and date (found, connected); AI asset useful lives, AI compute revenue by component, AI compute utilization and contracted backlog, AI investment plan by phase, how the AI build is financed (capex, leases, partners), split of capital expenditure by purpose (not disclosed) |
| `sbk.path.capital_allocation` | `sbk-c-ni-dps` | `sbk-c-capex-fcf`, `sbk-c-fcf-debt`, `sbk-c-debt-intexp`, `sbk-c-debt-netdebt`, `sbk.id.leverage:softbank_corp.net_debt`, `sbk-c-dps-dividends` | 2 | `sbk-c-aicapex-capex` (+), `sbk-c-leverage-dps` (-) | how the AI build is financed (capex, leases, partners), leverage target or rating threshold, split of capital expenditure by purpose (not disclosed) |
| `sbk.path.dividend_policy` | `sbk-c-ni-dps` | `sbk-c-dps-dividends`, `sbk-c-dividends-debt`, `sbk-c-debt-netdebt`, `sbk.id.leverage:softbank_corp.net_debt` | 0 | `sbk-c-leverage-dps` (-) | leverage target or rating threshold (not disclosed) |
| `sbk.path.domestic_demand` | s47 beside the path | `sbk-c-mediaop-nci` | 10 | `sbk-c-gdp-mediarev` (+), `sbk-c-gdp-itspend` (+), `sbk-c-mediarev-mediaop` (+), `sbk-c-itspend-solutions` (+) | Media & EC incremental margin (found, not connected); Media & EC revenue by business (media versus commerce), search advertising exposure to AI substitution, solutions order intake (not disclosed) |
| `sbk.path.enterprise_it` | none | `sbk-c-distrev-distop` | 7 | `sbk-c-itspend-solutions` (+), `sbk-c-itspend-distribution` (+) | solutions order intake (not disclosed) |
| `sbk.path.inflation` | none | `sbk-c-arpu-mobile` | 12 | `sbk-c-cpi-tariff` (+), `sbk-c-cpi-conscosts` (-), `sbk-c-cpi-entcosts` (-), `sbk-c-cpi-gmv` (+), `sbk-c-tariff-arpu` (+), `sbk-c-gmv-finrev` (+), `sbk-c-finrev-paypayop` (+) | average transaction value, tariff response to inflation (found, connected); Financial incremental margin (found, not connected); PayPay merchant fee rate, inflation-sensitive share of operating costs, size of the existing-plan price increase (percent and plans covered) (not disclosed) |
| `sbk.path.long_end` | `s49`, m33 beside the path | `sbk-c-borrowcost-intexp` | 8 | `sbk-c-jgb-borrowcost` (+), `sbk-c-jgb-shareprice` (-), `sbk-c-aicapex-entdep` (-), `sbk-c-aicapex-capacity` (+), `sbk-c-capacity-cloudai` (+) | data-centre capacity by site and date (found, connected); AI asset useful lives, AI compute revenue by component, coupons on recent issues, debt maturity ladder, share-price sensitivity to JGB yields (not disclosed) |
| `sbk.path.paypay_growth` | none | `sbk-c-mtu-gmv`, `sbk-c-finop-nci` | 6 | `sbk-c-gmv-finrev` (+), `sbk-c-finrev-paypayop` (+) | Financial incremental margin (found, not connected); PayPay merchant fee rate (not disclosed) |
| `sbk.path.policy_rate` | none | `sbk-c-borrowcost-intexp`, `sbk-c-finop-nci` | 7 | `sbk-c-boj-borrowcost` (+), `sbk-c-boj-nim` (+), `sbk-c-nim-finrev` (+), `sbk-c-finrev-paypayop` (+) | share of floating-rate and short-term debt (found, connected); Financial incremental margin (found, not connected); PayPay Bank rate sensitivity (asset and deposit repricing), debt maturity ladder (not disclosed) |
| `sbk.path.power_prices` | none | none | 10 | `sbk-c-power-elecrev` (+), `sbk-c-power-conscosts` (-), `sbk-c-power-entcosts` (-) | data-centre power consumption and contract terms, electricity pass-through formula and lag, power procurement cost and hedges (not disclosed) |
| `sbk.path.price_competition` | none | `sbk-c-churn-cancellations`, `sbk-c-cancellations-subs`, `sbk-c-subs-mobile`, `sbk-c-arpu-mobile` | 8 | `sbk-c-competition-churn` (+), `sbk-c-competition-promo` (+), `sbk-c-competition-arpu` (-), `sbk-c-promo-costs` (-), `sbk-c-promo-merch` (+) | ARPU by brand and migration rates, churn sensitivity to rivals' price gap, handset volumes and average selling prices, sales-related expenses by type (not disclosed) |
| `sbk.path.price_hike` | none | `sbk-c-arpu-mobile`, `sbk-c-churn-cancellations`, `sbk-c-cancellations-subs`, `sbk-c-subs-mobile` | 11 | `sbk-c-tariff-arpu` (+), `sbk-c-tariff-churn` (+), `sbk-c-tariff-entcomms` (+), `sbk-c-tariff-netcapex` (+), `sbk-c-netcapex-quality` (+), `sbk-c-quality-churn` (-), `sbk-c-netcapex-consdep` (-) | network asset base and useful lives (found, not connected); churn response to the existing-plan price increase, churn sensitivity to network quality, network quality response to investment, network share of capital expenditure, share of corporate lines on repriced tariffs, size of the existing-plan price increase (percent and plans covered) (not disclosed) |
| `sbk.path.regulation` | none | `sbk-c-arpu-mobile`, `sbk-c-churn-cancellations`, `sbk-c-cancellations-subs`, `sbk-c-subs-mobile` | 8 | `sbk-c-reg-tariff` (-), `sbk-c-reg-promo` (-), `sbk-c-reg-churn` (+), `sbk-c-tariff-arpu` (+), `sbk-c-promo-costs` (-), `sbk-c-promo-merch` (+) | handset volumes and average selling prices, regulatory scenario and its tariff effect, sales-related expenses by type, size of the existing-plan price increase (percent and plans covered) (not disclosed) |

## Completion report (first round)

Outcomes map to the release outcomes: built and verified (**BV**), built but uncalibrated (**BU**), blocked by a named
input (**BL**), not built (**NB**).

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | Segment revenue and operating income views, the bridge to profit before tax and net income; 35 accounting links with sd-ratio weights | — |
| G02 | BV | Basis and export metric on every SoftBank value | — |
| G03 | BU | Subscribers, ARPU, churn, tariff level, network quality; `sbk.path.price_hike` | churn response to the increase, the size of the increase, gross additions (chart only) |
| G04 | BU | `japan_mobile_market` values; `sbk.path.price_competition` with three branches | churn sensitivity to the price gap, brand ARPU, promotion amounts |
| G05 | BU | `mic.mobile_pricing_regulation`; `sbk.path.regulation` with three branches | a regulatory scenario |
| G06 | BV (bridge) / BU (revenue and costs to EBITDA) | `sbk.comp.consumer_revenue`, `sbk.comp.consumer_profit`; two `matrix:` links | the cost split (sales-related, network, cost of goods) |
| G07 | BU | Enterprise lines and bridge; capacity, utilization, AI compute demand; `sbk.path.ai_compute` | capacity, utilization, price per GPU-hour, AI asset lives |
| G08 | BU | Network capex, capex, segment D&A, stock-flow links; s48 scoped | capex split by purpose; useful lives |
| G09 | BL | m33 kept and scoped as the reduced form; the structural route to profit before tax built (uncalibrated) | the maturity ladder and coupons, to size the structural route and retire m33's mapping to operating income |
| G10 | BU | Debt, borrowing cost, interest expense, leverage; `sbk.path.policy_rate` and `sbk.path.long_end` (s49 as the build branch) | floating share of long-term debt, maturity ladder, PayPay Bank's rate sensitivity |
| G11 | BU | PayPay MTU and GMV; `sbk.comp.financial_profit`; `sbk.path.paypay_growth` | merchant fee rate |
| G12 | BV (one-offs view) / BU (links) | `sbk.comp.media_ec_profit`; `sbk.path.domestic_demand`; s47 scoped | media vs commerce split; AI search substitution |
| G13 | BV (composition) / BU (links) | non-controlling interests in `sbk.comp.net_income`; segment income to minorities | consolidated economic ownership |
| G14 | BV | `sbk-c-ni-dps` calibrated from guidance; dividends, free cash flow, debt, leverage; two paths; debt roll-forward | a leverage threshold (the cap is uncalibrated) |
| G15 | BU | IT spending, Distribution links in `sbk.path.enterprise_it` | volumes |
| G16 | BU | `japan_power_market.wholesale_price`; `sbk.path.power_prices` with offsetting branches | pass-through formula, procurement, data-centre power |
| G17 | BV (structure; undriven) | `sbk.comp.op_ebitda_bridge` | the company's adjusted EBITDA definition |
| G18 | BV | objects present in the v4.1.4 export | — |
| G19 | BV | node ids served by the query, construction and trace endpoints | — |
| G20 | BL | — | the import guard: see below |
| G21 | BL | baselines from a broker's tabulation, derived parts marked | the company's results file or a model workbook |

Counts: 21 gaps. By category (a gap can carry two): MC 15, CAL 4, MAP 4, EXP 1, RET 2. By outcome: BV 7 (G01, G02,
G06, G14, G17, G18, G19), BV in part 2 (G12, G13), BU 9, BL 3 (G09, G20, G21), NB 0.

**Links.** 108 links touch SoftBank's values: 35 accounting (fixed weights), 7 calibrated causal (m33, s47, s48,
s49, s65, the operating-profit kind default, and one new one from evidence: `sbk-c-ni-dps`), 66 uncalibrated
(mechanism and sign). The build adds 71 causal links in all: 70 uncalibrated (66 touch SoftBank's values, 4 run
between market values) and the dividend ladder. 106 links carry a transition (not s65 and the kind default). 32 of the
uncalibrated links carry a note naming the form that would compute them: 18 `identity:` (products, ratios, sums), 6
`stock-flow:`, 6 `matrix:` (sums across two views, undisclosed splits), 2 `state:` (a discrete pricing decision, a
leverage ceiling); the dividend ladder's `state:` note says how it was linearized.

**Reconciliation.** At the priors, every one of the eleven additive views adds up exactly (0.0%): the synthetic levels
were set to reconcile, and each residual says what it holds. At the FY3/26 baselines (actuals as a broker tabulates
them, local `reconciliation.md`), nine views add up exactly and two leave an unexplained difference, both within 0.5%:
the Consumer revenue lines (0.007% of Consumer revenue, rounding of the tabulated lines) and net income (0.02%, the
tabulated tax and minorities). Eight parts are derived, not read, so their views reconcile by construction: the Other
segment and eliminations, the operating-income residual, Consumer and Enterprise EBITDA, Media & EC recurring income
and one-offs (one-offs from amounts the broker states), PayPay and other financial income, and other non-operating
income. Units are one per view (tested). `check.py --reconcile --statistic median` and `--reconcile --baselines <local
baselines.json>` report 0 flags across the eleven views.

**Sources and citations.** `check.py --sources <local construction folder>`: 7 source ids resolve, 0 do not; 99 links
and 51 values are cited (page and line, with the passage); 0 material claims without a citation. The baselines bundle
validates; the import guard holds back the two EBITDA-bridge items (G20).

**Inputs by status** (42 distinct inputs named in transitions, after `scripts/construction/inputs.py` searched 25
supplied files for each): 5 found and connected (bound as a citation: data-centre sites and dates, the listed
subsidiaries' stakes, short-term debt, the average PayPay ticket, the inflation-driven price increase), 4 found but not
connected (segment margins by year for the incremental margins, gross additions in a chart, the PP&E balance), 33 not
disclosed in the reviewed sources (each with the sources and corpus queries searched; where the keyword search
returned candidates, they were read and found to be qualitative or about other companies, and the note says so), 0
not yet reviewed.

**Forecast coverage (Sally's theses).** The BoJ-hike thesis (S-T1) reaches SoftBank through 7 quantified links (s65,
s49, m33, the pretax and net-income accounting links, the share-price kind default, s48) and excludes 12 (the funding,
bank-margin, JGB valuation, AI-build and yen links, each with its sign; the dividend ladder lies outside the forecast's
networks). Two of 14 routes to operating income are fully quantified, both reduced forms (m13 -> m33; m13 -> s49 ->
s48). 12 inputs block a size (10 not disclosed, 2 found and connected). So the number the model gives for SoftBank
under a BoJ hike is the reduced form's, booked in operating income, while the structural answer (interest expense
below operating income, offset by PayPay Bank) is represented with signs only. The Fed-cut thesis (S-T2) reaches
SoftBank only through the JGB 10Y (s07): 5 quantified links, 9 excluded.

**Calculation coverage by path (first round, before the conversion).** "Calculated" contributes a size; accounting links carry it to the endpoint at fixed
weights; uncalibrated steps carry a sign only and are listed as unquantified by any forecast that reaches them.

| Path | Calculated (calibrated causal) | Accounting | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|
| `sbk.path.ai_compute` | s48 beside the path | 7 | `sbk-c-aidemand-util` (+), `sbk-c-aidemand-aicapex` (+), `sbk-c-aicapex-capacity` (+), `sbk-c-capacity-cloudai` (+), `sbk-c-util-cloudai` (+), `sbk-c-entrev-entebitda` (+), `sbk-c-aicapex-entdep` (-), `sbk-c-aicapex-capex` (+), `sbk-c-capex-fcf` (-), `sbk-c-fcf-debt` (-), `sbk-c-debt-intexp` (-) | data-centre capacity by site and date (found, connected); AI asset useful lives, AI compute revenue by component, AI compute utilization and contracted backlog, AI investment plan by phase, how the AI build is financed (capex, leases, partners), split of capital expenditure by purpose (not disclosed) |
| `sbk.path.capital_allocation` | `sbk-c-ni-dps` | 2 | `sbk-c-aicapex-capex` (+), `sbk-c-capex-fcf` (-), `sbk-c-fcf-debt` (-), `sbk-c-debt-intexp` (-), `sbk-c-debt-leverage` (+), `sbk-c-leverage-dps` (-), `sbk-c-dps-dividends` (+) | how the AI build is financed (capex, leases, partners), leverage target or rating threshold, split of capital expenditure by purpose (not disclosed) |
| `sbk.path.dividend_policy` | `sbk-c-ni-dps` | 0 | `sbk-c-dps-dividends` (+), `sbk-c-dividends-debt` (+), `sbk-c-debt-leverage` (+), `sbk-c-leverage-dps` (-) | leverage target or rating threshold (not disclosed) |
| `sbk.path.domestic_demand` | s47 beside the path | 8 | `sbk-c-gdp-mediarev` (+), `sbk-c-gdp-itspend` (+), `sbk-c-mediarev-mediaop` (+), `sbk-c-mediaop-nci` (-), `sbk-c-itspend-solutions` (+), `sbk-c-entrev-entebitda` (+) | economic ownership of LY Corporation and PayPay (found, connected); Media & EC incremental margin (found, not connected); Media & EC revenue by business (media versus commerce), search advertising exposure to AI substitution, solutions order intake (not disclosed) |
| `sbk.path.enterprise_it` | none | 6 | `sbk-c-itspend-solutions` (+), `sbk-c-itspend-distribution` (+), `sbk-c-entrev-entebitda` (+), `sbk-c-distrev-distop` (+) | solutions order intake (not disclosed) |
| `sbk.path.inflation` | none | 9 | `sbk-c-cpi-tariff` (+), `sbk-c-cpi-conscosts` (-), `sbk-c-cpi-entcosts` (-), `sbk-c-cpi-gmv` (+), `sbk-c-tariff-arpu` (+), `sbk-c-arpu-mobile` (+), `sbk-c-consrev-consebitda` (+), `sbk-c-conscosts-consebitda` (+), `sbk-c-entcosts-entebitda` (+), `sbk-c-gmv-finrev` (+), `sbk-c-finrev-paypayop` (+) | average transaction value, tariff response to inflation (found, connected); Financial incremental margin (found, not connected); PayPay merchant fee rate, inflation-sensitive share of operating costs, size of the existing-plan price increase (percent and plans covered) (not disclosed) |
| `sbk.path.long_end` | `s49`, m33 beside the path | 7 | `sbk-c-jgb-borrowcost` (+), `sbk-c-jgb-shareprice` (-), `sbk-c-borrowcost-intexp` (-), `sbk-c-aicapex-entdep` (-), `sbk-c-aicapex-capacity` (+), `sbk-c-capacity-cloudai` (+), `sbk-c-entrev-entebitda` (+) | data-centre capacity by site and date (found, connected); AI asset useful lives, AI compute revenue by component, coupons on recent issues, debt maturity ladder, share-price sensitivity to JGB yields (not disclosed) |
| `sbk.path.paypay_growth` | none | 5 | `sbk-c-mtu-gmv` (+), `sbk-c-gmv-finrev` (+), `sbk-c-finrev-paypayop` (+), `sbk-c-finop-nci` (-) | economic ownership of LY Corporation and PayPay (found, connected); Financial incremental margin (found, not connected); PayPay merchant fee rate (not disclosed) |
| `sbk.path.policy_rate` | none | 6 | `sbk-c-boj-borrowcost` (+), `sbk-c-boj-nim` (+), `sbk-c-borrowcost-intexp` (-), `sbk-c-nim-finrev` (+), `sbk-c-finrev-paypayop` (+), `sbk-c-finop-nci` (-) | economic ownership of LY Corporation and PayPay, share of floating-rate and short-term debt (found, connected); Financial incremental margin (found, not connected); PayPay Bank rate sensitivity (asset and deposit repricing), debt maturity ladder (not disclosed) |
| `sbk.path.power_prices` | none | 7 | `sbk-c-power-elecrev` (+), `sbk-c-power-conscosts` (-), `sbk-c-power-entcosts` (-), `sbk-c-consrev-consebitda` (+), `sbk-c-conscosts-consebitda` (+), `sbk-c-entcosts-entebitda` (+) | data-centre power consumption and contract terms, electricity pass-through formula and lag, power procurement cost and hedges (not disclosed) |
| `sbk.path.price_competition` | none | 6 | `sbk-c-competition-churn` (+), `sbk-c-competition-promo` (+), `sbk-c-competition-arpu` (-), `sbk-c-churn-subs` (-), `sbk-c-subs-mobile` (+), `sbk-c-arpu-mobile` (+), `sbk-c-promo-costs` (-), `sbk-c-promo-merch` (+), `sbk-c-consrev-consebitda` (+), `sbk-c-conscosts-consebitda` (+) | gross additions by quarter (found, not connected); ARPU by brand and migration rates, churn sensitivity to rivals' price gap, handset volumes and average selling prices, sales-related expenses by type (not disclosed) |
| `sbk.path.price_hike` | none | 9 | `sbk-c-tariff-arpu` (+), `sbk-c-tariff-churn` (+), `sbk-c-tariff-entcomms` (+), `sbk-c-tariff-netcapex` (+), `sbk-c-arpu-mobile` (+), `sbk-c-churn-subs` (-), `sbk-c-subs-mobile` (+), `sbk-c-netcapex-quality` (+), `sbk-c-quality-churn` (-), `sbk-c-consrev-consebitda` (+), `sbk-c-netcapex-consdep` (-), `sbk-c-entrev-entebitda` (+) | gross additions by quarter, network asset base and useful lives (found, not connected); churn response to the existing-plan price increase, churn sensitivity to network quality, network quality response to investment, network share of capital expenditure, share of corporate lines on repriced tariffs, size of the existing-plan price increase (percent and plans covered) (not disclosed) |
| `sbk.path.regulation` | none | 6 | `sbk-c-reg-tariff` (-), `sbk-c-reg-promo` (-), `sbk-c-reg-churn` (+), `sbk-c-tariff-arpu` (+), `sbk-c-arpu-mobile` (+), `sbk-c-promo-costs` (-), `sbk-c-promo-merch` (+), `sbk-c-churn-subs` (-), `sbk-c-subs-mobile` (+), `sbk-c-consrev-consebitda` (+), `sbk-c-conscosts-consebitda` (+) | gross additions by quarter (found, not connected); handset volumes and average selling prices, regulatory scenario and its tariff effect, sales-related expenses by type, size of the existing-plan price increase (percent and plans covered) (not disclosed) |
| Generalization (carry unwind) | m18, s62, s65 (shared macro links), s48 (reduced form) | 4 | `sbk-c-usdjpy-aicapex` (+), `sbk-c-usdjpy-conscosts` (-), `sbk-c-usdjpy-merch` (+), `sbk-c-aicapex-entdep` (-), `sbk-c-aicapex-capacity` (+), `sbk-c-capacity-cloudai` (+), `sbk-c-aicapex-capex` (+), `sbk-c-capex-fcf` (-), `sbk-c-fcf-debt` (-), `sbk-c-conscosts-consebitda` (+) | dollar share of AI investment and of handset procurement, handset volumes and prices (not disclosed) |

**What a downstream agent can now trace or calculate.** Group revenue and operating income as the sum of five
segments with the Other segment and eliminations; operating income again as EBITDA less D&A (the valuation basis);
Consumer and Enterprise revenue by line and their income as EBITDA less D&A; Media & EC income net of one-offs; the
Financial segment with SB Payment Service apart from PayPay; profit before tax and net income after interest, tax and
minorities; a calculated size for the dividend from net income (the company's ladder), for operating income from JGB
yields (m33), GDP (s47) and the AI build (s48), and for the build from JGB yields (s49), all statistical records now
scoped; and, as signed mechanisms with conditions, timing, evidence and breakers: the price increase against churn
and its reinvestment in the network, price competition and promotions, regulation, plan mix, AI compute capacity and
utilization against depreciation, corporate IT demand and distribution, PayPay's users, GMV and fees, the bank's margin
on a BoJ hike, the funding cost of debt on the short and long end, minorities' share, power and inflation in costs and
pricing, the yen's effect on dollar-priced GPUs and handsets, free cash flow, debt and leverage against the dividend.

**What remains unsupported.** Any size along the structural telecom paths (each step is a product, a sum across two
views, a ratio, a stock-flow or a discrete decision; see below); the split of capex by purpose and asset lives; the
maturity ladder and floating share; PayPay Bank's rate sensitivity; churn and ARPU elasticities; a full import of a
results release (G20); and baselines from the company's own files (G21).

## What the method could not express for a telecom

After the conversion, items 1, 2 (approximately: the average lags by half a period), 4 and 7 below are expressed; the
dividend ratchet (3) is approximated about the construction level, not the running maximum. What remains: the size of
every first behavioural step (rates to borrowing cost, tariffs to ARPU and churn, demand to utilization), bounded
accounting weights (6), dated events (the price increase, data-centre commissioning), re-homing m33 (5), a depreciation
stock-flow without a disclosed asset base, a Financial revenue that sums several products, and the shared macro gaps (8).

First-round findings:

This is the feedback the build was for. The method carried over again (gap register, compositions, transitions,
paths with parallel branches, counter-paths, evidence, calibration from a disclosure, generalization trace), and the
bank's findings recur: products (subscribers x ARPU, capacity x utilization x price, GMV x fee rate, debt x rate),
ratios (leverage, tax rate, margins) and stocks (subscribers, PP&E, debt) are all held as uncalibrated links with a
`identity:`/`ratio`/`stock-flow:` note. What is new for a telecom:

1. **A hierarchy of bridges, not a set of partitions.** A segment's revenue is a part of group revenue *and* the top
   line of its own profit bridge (revenue + costs = EBITDA; EBITDA + D&A = segment income; segments = operating
   income). A value may sit in one additive view only, so the step from segment revenue to segment EBITDA, a plain
   sum, had to become two uncalibrated `matrix:` links, and the Consumer and Enterprise bridges are cut at EBITDA.
   The same rule stops segment D&A from adding up to group D&A (a third view), so the EBITDA view of operating income
   is reconciled but undriven. Needed: compositions that nest (a part of one view can be the total of the next, *and*
   a part elsewhere), checked as a tree of identities rather than as disjoint partitions.
2. **Subscriber dynamics are a stock with a rate.** Subscribers += gross additions − churn x subscribers, and revenue
   is ARPU x the *average* of the stock over the period. Churn is a rate applied to a stock; neither a fixed weight nor
   a single effect expresses it, and the period average (not the period end) is what revenue needs. Needed: a
   stock-flow link with a rate-on-stock outflow and a period-average output.
3. **Discrete management decisions.** The existing-plan price increase is a one-off step taken when inflation has
   persisted and a rival has gone first; the dividend follows a ladder of net-income thresholds and is never cut by
   policy; capacity arrives at data-centre commissioning dates. A link has one linear effect; the dividend ladder is
   calibrated as a slope between two stated steps, and the tariff step and commissioning dates sit in text. Needed:
   event and threshold (state) links: a step response at a trigger, a ratchet (no cuts), and a scheduled change.
4. **Minorities are a product with ownership.** What the parent's owners get from LY Corporation and PayPay is
   segment profit after tax times the parent's economic share; ownership changes (buyouts, listing) move it. The model
   holds minorities as one negative value with two signed links. Needed: an attributable-share link (or a matrix of
   segments x owners).
5. **Mapping a statistical record to the wrong account.** m33 (JGB yields to operating income) is on Sally's expected
   path, so its id and size stay; but the mechanism it summarises is an interest charge below operating income. The
   forecast therefore books a funding-cost effect in operating income, and the correct structural route is
   uncalibrated, so no number corrects it. Needed: a way to re-home a reduced form to the right account (or to declare
   which structural endpoint it summarises) without breaking the records that cite it.
6. **The undisclosed split of a disclosed total.** Capex is reported; its split into network, AI and systems is not,
   and the AI build may sit partly in leases or partner vehicles. These are accounting parts with unknown weights,
   held as uncalibrated `matrix:` links. Needed: an accounting part with an unknown weight bounded by its total (a
   share in [0, 1]), so the identity holds while the split is unknown.
7. **Notes do not reach the graph or the export.** The `identity:`/`stock-flow:`/`matrix:`/`state:` tags live only in
   the YAML; the loaded graph drops an interaction's `note`, so the export and the API cannot tell a downstream agent
   which form a link needs (the tests read the file). The tags should become a field the export carries.
8. **The shared macro world lacks the yen's domestic channel.** No link runs from USD/JPY to Japanese inflation or the
   BoJ, so the carry-unwind trace cannot reach SoftBank's funding costs, and no Japanese short-end or swap rate exists
   between the policy rate and the 10Y (the borrowing cost hangs off both). These belong to the shared macro structure,
   not to one company.
9. **Importing a results release.** As for the other companies, the overlap guard folds one view of operating income
   per day; the baseline bundle's EBITDA and D&A items are held back. A results release always reports both, so a
   two-way (matrix) reconciliation is needed before a full set of actuals can be imported.
10. **No company workbook.** Every baseline is a broker's tabulation (derived parts marked); proof limits are wider
    than for the companies with a workbook, and cell-level bindings are page-and-line bindings.
