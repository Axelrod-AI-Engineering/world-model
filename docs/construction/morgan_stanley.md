# Morgan Stanley: business construction

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
- [Completion report](#completion-report)
- [Conversion to the new method forms (Oct 18)](#conversion-to-the-new-method-forms-oct-18)
- [What the method could not express for an investment bank and wealth manager](#what-the-method-could-not-express-for-an-investment-bank-and-wealth-manager)
<!-- /toc -->

The fourth build of the method, after an automaker ([Toyota](toyota.md)), an insurer ([Tokio Marine](tokio_marine.md))
and a universal bank ([JPMorgan](jpmorgan.md)): an investment bank and wealth manager. Its economics are three
businesses with different drivers. Institutional Securities earns on activity: deals (advisory at completion,
underwriting at pricing), volatility and client flow (equity execution, FICC), and financing balances (prime
brokerage). Wealth Management earns asset-based fees on client assets (market levels and net new assets), transactional
revenue, and net interest on client cash swept into its banks (deposit betas and cash sorting). Investment Management
earns fees on AUM and performance fees on fund marks. Revenue-linked compensation (incentive accruals, the advisor
payout, carried interest) absorbs part of every revenue move, and capital is bound by the CET1 ratio and, per the
research, the supplementary leverage ratio. Unlike JPMorgan's, its reporting segments follow its drivers, so the
segment view is the driven one.

The construction lives in `data/worlds/sally_demo/construction/morgan_stanley.yaml` (values, links with their
transitions, named paths, compositions) plus light edits to the `morgan_stanley` block of entities.yaml (features on
three values) and to s13, s15, s17 and s75 in interactions.yaml (transitions; s75 resized from a disclosure, the others'
sizes kept). This page is structure only: object ids, bases, categories, tests. The client-derived side (workbook cells,
broker passages, dated baselines, estimates) stays local under `data/sally_data/construction/morgan_stanley/`
(`gap_evidence.md`, `sources.json`, `citations.json`, `baselines.json`, `baselines_reported_views.json`,
`estimates.json`, `reconciliation.md`, `coverage.json`, `input_search.md`, and the readable view with levels in `view/`).

Source ids used in transitions (each resolves locally in `sources.json` to a file, and in `citations.json` to the cell
or the page and line with the passage): `ms.wb` the client's company model workbook (history, segment build with broker
means, a transmission map, the disclosed WM NII sensitivity, capital); `ms.vm` a vendor company model workbook in the
sell-side folder; `ms.co` company filings as transcribed in `ms.wb` (not read directly); `ms.r1`–`ms.r5` broker and
research notes (three sector previews with Morgan Stanley pages, a company report, a company model update); `ms.x1` an
expert call on wealth platforms (no names recorded; `ms.x2`, a post-trade operations call, was read and not used);
`ms.pub` public business and accounting knowledge. Shared market values come from the JPMorgan build
(`us_capital_markets.equity_index`, `us_capital_markets.credit_spread`, `us_economy.unemployment_rate`) and its shared
macro links (`jpm-c-vol-equityindex`, `jpm-c-vol-spread`, `jpm-c-spread-deals`, `jpm-c-gdp-unemp`); no new macro value
was added.

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack (036, state 432). Morgan Stanley was not one of the reviewer's worked companies, so the export side is "not
represented in the inspected export" throughout. Categories: **MC** missing construction, **CAL** missing calibration,
**MAP** incorrect mapping, **EXP** export omission, **RET** retrieval omission. Outcomes are in the
[completion report](#completion-report).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | No business composition: the pack jumps from deals to IB fees (s13), from volatility to trading (s15) and to wealth revenue (s17), from the Fed to wealth revenue (s75) | Internal: three values (`trading_revenue`, `ib_fees`, `wealth_revenue`), links s13, s15, s17, s23, s24, s75 and the share-price kind default; no net revenues, no ISG or IM total, no compositions. Export: the same broad relations | The segment view with intersegment eliminations (`ms.comp.revenue_by_segment`, driven), ISG, trading, Equity, IB, WM and IM views, the P&L bridge to pretax and net income | Segment tables (`ms.wb`, `ms.vm`) | Any group revenue or earnings conclusion | `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links`, `test_priors_reconcile_within_half_a_percent` | MC |
| G02 | Undefined bases: "trading revenue" (ISG sales and trading incl. fees and net interest, or the trading line?), "IB revenue" (ISG, or the firm line that adds WM's distribution?), "wealth revenue" (incl. intersegment amounts) | Internal: values without features. Export: metrics named by id suffix | `features.view/basis/metric` on the three values and every new one | Workbook definitions (`ms.wb`, `ms.vm`) | Adding a line to a segment total double counts | `test_values_name_their_basis` | MAP |
| G03 | s75 (Fed → WM revenue) has no scope, and its size is not the company's disclosed WM NII sensitivity | Internal: calibrated (statistical record), no transition | Transition naming it the reduced form of `ms.path.rates_wm_nii`; resized with `calibrate.py` from the disclosed 12-month WM NII sensitivity to a +100bp parallel shock (magnitude "documented") | WM NII sensitivity (found); the beta inside it (not disclosed) | Size of any Fed-driven WM revenue change | `test_wm_nii_is_balances_times_rates_and_the_disclosed_sensitivity_sizes_the_reduced_form` | MAP / CAL |
| G04 | WM NII drivers absent: sweep and savings deposits, cost of deposits and the beta, cash sorting, floating securities-based loans | Internal: none | Deposit view (`ms.comp.wm_deposits`), rate and balance states, `ms.path.rates_wm_nii` (parallel branches of one rate move) | Beta by product, sweep and savings sensitivities, floating share | Whether and when a hike helps WM; cash sorting | `test_shared_driver_responses_are_parallel_branches` | MC / CAL |
| G05 | Asset-based fees: fee-based assets times the fee rate, billed a month later; s17 unscoped | Internal: s17 only | `ms.path.market_levels`; reduced form `ms-c-equity-amfees` calibrated from management's stated asset mix; s17 scoped | Equity share of the fee base and the billing lag (found) | WM fee forecasts; "volatility hurts wealth" | `test_asset_based_fees_follow_markets_with_a_month_lag` | MC / CAL |
| G06 | Net new assets and the workplace funnel (IPO liquidity into stock-plan accounts, conversion to fee-based, cash into sweep) | Internal: none | NNA, fee-based flows, client assets as stocks fed by flows; `ms.path.net_new_assets` | NNA sensitivity to IPOs, conversion rate (not disclosed) | WM growth beyond markets | `test_required_paths_exist`, stock-flow tags | MC |
| G07 | Investment Management: AUM times fee rate, flows, performance fees on fund marks (and reversals) | Internal: none | IM view, AUM and fee-rate states, `ms.path.investment_management`, market and long-end branches | Performance-fee sensitivities (not disclosed) | IM revenue, carry reversals | `test_required_paths_exist` | MC |
| G08 | Investment banking as volume times fee rate; advisory booked at completion; the IPO window; spreads and yields on DCM | Internal: s13 only | `ms.comp.ib`, completed-M&A state, `ms.path.deals_ib`; s13 scoped | Fee elasticities (not disclosed); completed volume and implied fee rates (found) | IB fee timing | `test_deferred_pay_offsets_its_hedge_and_pay_follows_revenue` (completion lag) | MC / CAL |
| G09 | Sales and trading: Equity financing (prime balances) versus execution (volumes), FICC (volatility, spreads, commodities); s15 unscoped | Internal: s15 only | `ms.comp.trading`, `ms.comp.equity`, prime-balance state, `ms.path.volatility` with counter-paths | Volatility and spread sensitivities (not disclosed) | "Volatility is good for MS" | `test_shared_driver_responses_are_parallel_branches` | MC |
| G10 | Compensation ratio and operating leverage: incentive accruals, the advisor payout, carried interest, deferred cash-based plans, clearing costs, inflation | Internal: none | `ms.comp.expense`, revenue-linked pay links, the deferred-plan counter-path, `ms.path.expense_inflation` | Payout grid (not disclosed); comp ratios (found) | Pretax sensitivity to revenue | `test_deferred_pay_offsets_its_hedge_and_pay_follows_revenue` | MC |
| G11 | Credit: CECL provisions on spreads and unemployment; corporate-loan marks in ISG other | Internal: none | Provision value, `ms.path.credit_spreads`, `ms.path.recession` | CECL sensitivities (not disclosed) | Recession conclusions | `test_required_paths_exist` | MC |
| G12 | Capital and payout: CET1 capital, RWA, requirement (stress capital buffer), SLR, AOCI, buybacks, dividends; financing balances consume balance sheet | Internal: none | Capital values, non-additive `ms.comp.capital_sources_uses`, `ms.path.capital_payout`, `ms.path.capital_requirements`, `ms.path.balance_sheet`, `ms.path.long_end` | Leverage exposure, AFS duration, management target (not disclosed); requirement, SLR, authorization (found) | Buyback capacity | `test_capital_is_a_stock_with_flows_and_the_leverage_ratio_can_bind`, `test_marks_reach_capital_not_income` | MC |
| G13 | The reported income-statement lines (firm NII, trading, IB, commissions, asset management) are a second view of net revenues; firm NII is a small net of matched-book flows | Internal: none | `ms.comp.revenue_by_line` and `ms.comp.nii`, reconciled but undriven, bridged by size-free links | Line tables (found) | Reading firm NII as a rate sensitivity | `test_the_segment_view_is_driven_and_eliminates_intersegment_revenue` | MC |
| G14 | Segment pretax (the WM margin) with eliminations | Internal: none | `ms.comp.pretax_by_segment`, reconciled but undriven, bridged | Segment pretax (found) | Segment contribution | `test_the_segment_view_is_driven_and_eliminates_intersegment_revenue` | MC |
| G15 | The yen: income from the Japanese securities joint venture is earned in yen | Internal: none | `ms-c-usdjpy-isgother` (a translation identity) | JV income (found) | FX theses | generalization trace | MC |
| G16 | New objects absent from the export | Export: none | Transitions in relationship properties, `financial_bridge`, `business_construction` paths | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G17 | New node ids not retrievable | Internal API: none | `/v1/world-models/sally_demo/graph`, `…/entities/morgan_stanley/construction` and its traces | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G18 | A results release reports the segment and line views (and segment and firm pretax) on the same day; the import guard folds one view per total and day | Import: `intake/overlap.py` | Baselines split into two bundles (driven views; reported views) so each imports whole | A matrix (segments × lines) reconciliation | Importing a full set of actuals at once | `bundles.py check` on both bundles | RET |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, kind, memberships, share-price kind default, templates (`morgan_stanley`) | Already owned | entities.yaml, taxonomy, templates.yaml | untouched |
| s13, s15, s17 (statistical records on Morgan Stanley's values) | Already owned → Modify lightly | interactions.yaml | ids, sizes and kernels kept; transitions added (scope, reduced form, evidence, inputs with search status) |
| s75 (Fed → WM revenue) | Modify lightly, with separate justification | interactions.yaml | transition added; resized from the company's disclosed WM NII sensitivity (0.15 → 0.034 sd/sd, documented); id, sign, kernel kept; Sally's expected paths still pass |
| s23, s24 and the trading revenue → share price kind default | Do not touch | interactions.yaml, taxonomy | untouched |
| `trading_revenue`, `ib_fees`, `wealth_revenue` definitions | Modify lightly | entities.yaml | `features.view/basis/metric` added; ids and priors kept |
| Compositions, operating states, connected paths, financial mappings, capital values, bindings | Missing | construction/morgan_stanley.yaml; local sources, citations, baselines | built |
| Shared macro links (m01–m18, s09, s10, s74) and JPMorgan's shared market values and links | Do not touch | interactions.yaml, construction/jpmorgan.yaml | reused as path steps where they carry a transition; s09 and s74 (no transition) left beside the paths |
| Import overlap guard | Do not touch (shared code) | `src/axelrod_wm/intake/overlap.py` | first round: two baseline bundles; after the conversion the reconciling views fold whole, so one bundle |

## Definitions and bases

- **US GAAP as reported** (`features.basis`). Segment net revenues include intersegment amounts, eliminated once
  (`morgan_stanley.intersegment_eliminations`, negative) in the segment view; the same holds for segment pretax
  (`morgan_stanley.elim_pretax`).
- **Sales and trading** (`morgan_stanley.trading_revenue`) is ISG Equity plus Fixed Income, each including its own fees
  and net interest (Equity financing books its funding cost as negative net interest). It excludes ISG other, and it is
  not the firm trading line (`morgan_stanley.trading_line`).
- **Investment banking** (`morgan_stanley.ib_fees`) is ISG advisory plus equity and fixed income underwriting; the firm
  investment banking line (`morgan_stanley.ib_line`) also holds WM's distribution of underwritings.
- **WM NII** (`morgan_stanley.wm_nii`) is the rate-sensitive part of firm NII (`morgan_stanley.firm_nii`), which also
  holds ISG's financing cost; firm NII is interest income less interest expense, mostly ISG's matched book.
- **The driven view** is the segment view (`ms.comp.revenue_by_segment`): ISG + WM + IM + eliminations. **The line
  view** (`ms.comp.revenue_by_line`) totals the same net revenues by income-statement line; it is reconciled but
  undriven, and reached only by size-free bridges (`ms-c-bridge-*`). The two are never added.
- **Costs and charges are negative values** (expenses, provision, tax, noncontrolling interests, interest expense), so
  every part adds to its total with a positive weight. A cost link's sign "−" means "a larger charge".
- **Stocks and flows**: client assets, fee-based assets, AUM and CET1 capital accumulate (next period = this period +
  flows + market impact): declared as `stock_flows` (after the conversion below); market impact stays a sign.
- **Identities** (fees = assets × fee rate, NII = balances × rates, advisory = completed volume × fee rate, pay = ratio
  × revenue, tax = rate × pretax, ratios = capital / RWA or exposure) are declared as `identities` with derived weights
  (after the conversion below). The line view and segment pretax reconcile without driving (`drives: false`).
- Fiscal year = calendar year. Balances (client assets, AUM, deposits, loans, RWA, exposure) are period-end $bn unless
  the basis says average; flows are $bn per year.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities morgan_stanley` from the loaded model (the same objects the API serves at `/v1/world-models/sally_demo/entities/morgan_stanley/construction`). A `?` marks a step whose size is unknown (uncalibrated). Levels are left out here; the local copy adds them.

139 links touch its values: 74 calibrated, 65 uncalibrated (represented, size unknown), 48 accounting, 22 identity, 6 stock-flow; 1 state-dependent; 136 carry a transition.

### Business composition

#### capital: CET1 capital roll-forward: earnings in, distributions out, AOCI marks (not an additive partition: flows into a stock) ($bn)

| Part | Value |
|---|---|
| Morgan Stanley net income | `morgan_stanley.net_income` |
| Morgan Stanley common dividends | `morgan_stanley.common_dividends` |
| Morgan Stanley share buybacks | `morgan_stanley.buybacks` |
| Morgan Stanley AOCI | `morgan_stanley.aoci` |
| **Total: Morgan Stanley CET1 capital** | `morgan_stanley.cet1_capital` |

A non-additive view: its parts overlap.
Capital accumulates: next period's CET1 is this period's plus net income (less preferred dividends) less common dividends and buybacks plus the change in AOCI. Net income, dividends and buybacks are the stock-flow ms.sf.cet1 (accumulating links); the AOCI change is a stock inside a stock and stays a signed link (ms-c-aoci-cet1).

#### product: Equity net revenues by business: financing and execution services ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley Equity financing revenue | `morgan_stanley.equity_financing` |
| Morgan Stanley Equity execution services revenue | `morgan_stanley.equity_execution` |
| **Total: Morgan Stanley Equity sales and trading revenue** | `morgan_stanley.equity_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported (the sum of the businesses' trading, fees, net interest and other). Financing earns on prime balances; execution on volumes and volatility.

#### reporting segments: non-interest expenses by type (negative values) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley compensation and benefits | `morgan_stanley.compensation_expense` |
| Morgan Stanley brokerage, clearing and exchange fees | `morgan_stanley.brokerage_clearing_expense` |
| Morgan Stanley information processing and communications | `morgan_stanley.technology_expense` |
| Residual: Morgan Stanley other non-compensation expenses | `morgan_stanley.other_noncomp_expense` |
| **Total: Morgan Stanley non-interest expenses** | `morgan_stanley.noninterest_expense` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Compensation is the variable part (incentive accruals on ISG revenue, the advisor payout on WM revenue, deferred cash-based plans that follow markets); brokerage and clearing follows volumes.

#### product: ISG investment banking revenues by product ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley advisory revenue | `morgan_stanley.advisory_fees` |
| Morgan Stanley equity underwriting revenue | `morgan_stanley.ecm_fees` |
| Morgan Stanley fixed income underwriting revenue | `morgan_stanley.dcm_fees` |
| **Total: Morgan Stanley investment banking revenue** | `morgan_stanley.ib_fees` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual.

#### reporting segments: Investment Management net revenues by line ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley IM asset management fees | `morgan_stanley.im_mgmt_fees` |
| Morgan Stanley IM performance-based income | `morgan_stanley.im_performance_fees` |
| **Total: Morgan Stanley Investment Management net revenues** | `morgan_stanley.im_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: management fees on AUM, and performance-based income and other (which can be negative when carried interest reverses).

#### reporting segments: Institutional Securities net revenues by business ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley trading revenue | `morgan_stanley.trading_revenue` |
| Morgan Stanley investment banking revenue | `morgan_stanley.ib_fees` |
| Residual: Morgan Stanley ISG other revenue | `morgan_stanley.isg_other_revenue` |
| **Total: Morgan Stanley Institutional Securities net revenues** | `morgan_stanley.isg_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Sales and trading (Equity and Fixed Income) plus investment banking; the residual is ISG other (investments, the Japanese securities joint venture, lending fees and corporate-loan marks).

#### reporting segments: net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley income before taxes | `morgan_stanley.pretax_income` |
| Morgan Stanley provision for income taxes | `morgan_stanley.income_tax` |
| Residual: Morgan Stanley net income to noncontrolling interests | `morgan_stanley.noncontrolling_interests` |
| **Total: Morgan Stanley net income** | `morgan_stanley.net_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity; preferred dividends come after this line (net income to common).

#### investment assets: firm net interest income: interest income less interest expense ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley interest income | `morgan_stanley.interest_income` |
| Morgan Stanley interest expense | `morgan_stanley.interest_expense` |
| **Total: Morgan Stanley net interest income (firm)** | `morgan_stanley.firm_nii` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity. Most gross interest is ISG's matched book (resale/repo, securities borrowed/loaned, customer receivables/payables), so firm NII is a small net of large flows; WM NII is the rate-sensitive part.

#### reporting segments: pretax income: net revenues less non-interest expenses less provision ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley net revenues | `morgan_stanley.net_revenue` |
| Morgan Stanley non-interest expenses | `morgan_stanley.noninterest_expense` |
| Morgan Stanley provision for credit losses | `morgan_stanley.provision_for_credit_losses` |
| **Total: Morgan Stanley income before taxes** | `morgan_stanley.pretax_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity: expenses and provision are negative values. Operating leverage is revenue growth less expense growth.

#### reporting segments: pretax income by reporting segment, with intersegment eliminations ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley ISG pretax income | `morgan_stanley.isg_pretax` |
| Morgan Stanley WM pretax income | `morgan_stanley.wm_pretax` |
| Morgan Stanley IM pretax income | `morgan_stanley.im_pretax` |
| Eliminations: Morgan Stanley intersegment eliminations (pretax) | `morgan_stanley.elim_pretax` |
| **Total: Morgan Stanley income before taxes** | `morgan_stanley.pretax_income` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reported view, reconciled but undriven: segment revenue reaches segment pretax only by size-free bridges (the segment expense split is not modelled). Never added to ms.comp.pretax.

#### product: net revenues by reported income-statement line, firm ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley net interest income (firm) | `morgan_stanley.firm_nii` |
| Morgan Stanley trading revenues (line) | `morgan_stanley.trading_line` |
| Morgan Stanley investment banking revenues (line) | `morgan_stanley.ib_line` |
| Morgan Stanley commissions and fees (line) | `morgan_stanley.commissions_line` |
| Morgan Stanley asset management, distribution and administration fees (line) | `morgan_stanley.am_fees_line` |
| Residual: Morgan Stanley investments and other revenues (line) | `morgan_stanley.other_revenue_lines` |
| **Total: Morgan Stanley net revenues** | `morgan_stanley.net_revenue` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reported view, reconciled but undriven: each line cuts across segments (firm NII holds WM NII and ISG's financing cost; the trading line is not ISG sales and trading). Bridged to the segment view by size-free links only; never added to it.

#### reporting segments: net revenues by reporting segment, US GAAP, with intersegment eliminations ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley Institutional Securities net revenues | `morgan_stanley.isg_revenue` |
| Morgan Stanley wealth management revenue | `morgan_stanley.wealth_revenue` |
| Morgan Stanley Investment Management net revenues | `morgan_stanley.im_revenue` |
| Eliminations: Morgan Stanley intersegment eliminations (revenue) | `morgan_stanley.intersegment_eliminations` |
| **Total: Morgan Stanley net revenues** | `morgan_stanley.net_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driven view: Morgan Stanley's segments follow its drivers (markets and deals in ISG, client assets and rates in WM, AUM in IM). Segment revenues include intersegment amounts, eliminated once. Not the line view (ms.comp.revenue_by_line): never added to it.

#### capital: tier 1 capital: CET1 plus preferred ($bn, period end)

| Part | Value |
|---|---|
| Morgan Stanley CET1 capital | `morgan_stanley.cet1_capital` |
| Morgan Stanley preferred equity | `morgan_stanley.preferred_equity` |
| **Total: Morgan Stanley tier 1 capital** | `morgan_stanley.tier1_capital` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split.

#### product: ISG sales and trading net revenues by product ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley Equity sales and trading revenue | `morgan_stanley.equity_revenue` |
| Morgan Stanley Fixed Income sales and trading revenue | `morgan_stanley.ficc_revenue` |
| **Total: Morgan Stanley trading revenue** | `morgan_stanley.trading_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual. Each product includes its own fees and net interest.

#### reporting segments: Wealth Management net revenues by line ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley WM asset management fees | `morgan_stanley.wm_asset_mgmt_fees` |
| Morgan Stanley WM transactional revenue | `morgan_stanley.wm_transactional` |
| Morgan Stanley WM net interest income | `morgan_stanley.wm_nii` |
| Residual: Morgan Stanley WM other revenue | `morgan_stanley.wm_other_revenue` |
| **Total: Morgan Stanley wealth management revenue** | `morgan_stanley.wealth_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Asset-based fees (fee-based assets times the fee rate), transactional revenue, and net interest on bank deposits; the residual is WM other.

#### liabilities: Wealth Management deposits by type, period end ($bn, period end)

| Part | Value |
|---|---|
| Morgan Stanley WM brokerage sweep deposits | `morgan_stanley.wm_sweep_deposits` |
| Morgan Stanley WM savings and other deposits | `morgan_stanley.wm_other_deposits` |
| **Total: Morgan Stanley WM deposits** | `morgan_stanley.wm_deposits` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split: brokerage sweep (low administered rate) and savings and other (priced nearer market). Cash sorting moves balances between them and off the balance sheet.

#### investment assets: WM interest income: loans plus securities and cash ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| Morgan Stanley WM interest earned on loans | `morgan_stanley.wm_loan_interest_income` |
| Residual: Morgan Stanley WM interest on securities and cash | `morgan_stanley.wm_other_interest_income` |
| **Total: Morgan Stanley WM interest income** | `morgan_stanley.wm_interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Loan interest is an identity (loans x rate); securities and cash interest is the residual.

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `ms.id.advisory` (product) | Morgan Stanley advisory revenue = 0.0001 x Morgan Stanley completed M&A volume x Morgan Stanley advisory fee rate | Morgan Stanley completed M&A volume (factor, +1.000); Morgan Stanley advisory fee rate (factor, +0.801) | $bn/yr = $bn/yr x bp x 0.0001 |
| `ms.id.cet1_ratio` (ratio) | Morgan Stanley CET1 ratio = 100 x Morgan Stanley CET1 capital / Morgan Stanley risk-weighted assets | Morgan Stanley CET1 capital (numerator, +1.818); Morgan Stanley risk-weighted assets (denominator, -2.000) | pct = 100 x $bn / $bn |
| `ms.id.compensation` (product) | Morgan Stanley compensation and benefits = -0.01 x Morgan Stanley compensation ratio x Morgan Stanley net revenues | Morgan Stanley compensation ratio (factor, -0.505); Morgan Stanley net revenues (factor, -1.036) | $bn/yr (negative) = -0.01 x pct x $bn/yr |
| `ms.id.financing` (product) | Morgan Stanley Equity financing revenue = 0.01 x Morgan Stanley prime brokerage balances x Morgan Stanley financing revenue rate | Morgan Stanley prime brokerage balances (factor, +1.000); Morgan Stanley financing revenue rate (factor, +1.250) | $bn/yr = $bn x pct x 0.01 |
| `ms.id.im_fees` (product) | Morgan Stanley IM asset management fees = 0.0001 x Morgan Stanley IM assets under management x Morgan Stanley IM fee rate | Morgan Stanley IM assets under management (factor, +1.000); Morgan Stanley IM fee rate (factor, +0.949) | $bn/yr = $bn x bp x 0.0001 |
| `ms.id.slr` (ratio) | Morgan Stanley supplementary leverage ratio = 100 x Morgan Stanley tier 1 capital / Morgan Stanley total leverage exposure | Morgan Stanley tier 1 capital (numerator, +0.882); Morgan Stanley total leverage exposure (denominator, -1.360) | pct = 100 x $bn / $bn |
| `ms.id.tax` (product) | Morgan Stanley provision for income taxes = -0.01 x Morgan Stanley effective tax rate x Morgan Stanley income before taxes | Morgan Stanley effective tax rate (factor, -0.440); Morgan Stanley income before taxes (factor, -0.980) | $bn/yr (negative) = -0.01 x pct x $bn/yr |
| `ms.id.wm_am_fees` (product) | Morgan Stanley WM asset management fees = 0.0001 x Morgan Stanley WM fee-based client assets x Morgan Stanley WM fee rate on fee-based assets | Morgan Stanley WM fee-based client assets (factor, +1.200); Morgan Stanley WM fee rate on fee-based assets (factor, +0.611) | $bn/yr = $bn x bp x 0.0001 |
| `ms.id.wm_deposit_interest` (product) | Morgan Stanley WM interest paid on deposits = 0.01 x Morgan Stanley WM deposits x Morgan Stanley WM cost of deposits | Morgan Stanley WM deposits (factor, +0.571); Morgan Stanley WM cost of deposits (factor, +0.794) | $bn/yr = $bn x pct x 0.01 |
| `ms.id.wm_loan_interest` (product) | Morgan Stanley WM interest earned on loans = 0.01 x Morgan Stanley WM loans x Morgan Stanley interest rate earned on loans | Morgan Stanley WM loans (factor, +0.667); Morgan Stanley interest rate earned on loans (factor, +0.772) | $bn/yr = $bn x pct x 0.01 |
| `ms.id.wm_nii` (difference) | Morgan Stanley WM net interest income = Morgan Stanley WM interest income - Morgan Stanley WM interest paid on deposits | Morgan Stanley WM interest income (total, +2.151); Morgan Stanley WM interest paid on deposits (deduction, -1.845) | unknown |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `ms.sf.cet1` | Morgan Stanley CET1 capital (closing) = Morgan Stanley CET1 capital (opening) + Morgan Stanley net income - Morgan Stanley common dividends - Morgan Stanley share buybacks, per 365 days | Morgan Stanley net income (inflow, +0.563); Morgan Stanley common dividends (outflow, -0.133); Morgan Stanley share buybacks (outflow, -0.500) |
| `ms.sf.client_assets` | Morgan Stanley WM total client assets (closing) = Morgan Stanley WM total client assets (opening) + Morgan Stanley WM net new assets, per 365 days | Morgan Stanley WM net new assets (inflow, +0.135) |
| `ms.sf.fee_based_assets` | Morgan Stanley WM fee-based client assets (closing) = Morgan Stanley WM fee-based client assets (opening) + Morgan Stanley WM fee-based asset flows, per 365 days | Morgan Stanley WM fee-based asset flows (inflow, +0.182) |
| `ms.sf.im_aum` | Morgan Stanley IM assets under management (closing) = Morgan Stanley IM assets under management (opening) + Morgan Stanley IM net flows, per 365 days | Morgan Stanley IM net flows (inflow, +0.421) |

### Operating and financial paths

#### Morgan Stanley financing balances, leverage and buybacks

**Trigger:** client financing (prime brokerage) balances grow. **Endpoint:** Morgan Stanley share buybacks.

Morgan Stanley prime brokerage balances → [revenue] Morgan Stanley Equity financing revenue → [rwa] Morgan Stanley risk-weighted assets? → [leverage] Morgan Stanley total leverage exposure? → Morgan Stanley Equity sales and trading revenue → Morgan Stanley trading revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley net revenues → Morgan Stanley income before taxes → Morgan Stanley net income → Morgan Stanley CET1 capital → Morgan Stanley CET1 ratio → Morgan Stanley CET1 ratio → Morgan Stanley supplementary leverage ratio → Morgan Stanley tier 1 capital → Morgan Stanley supplementary leverage ratio → Morgan Stanley share buybacks? → Morgan Stanley share buybacks?  (? marks a step whose size is unknown)

Financing balances earn the financing spread but consume RWA and leverage exposure; when the leverage ratio binds, its headroom, not the CET1 ratio, limits buybacks.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [revenue] `ms-c-prime-financing` | Equity financing revenue is roughly balances times the financing spread (net of the funding cost booked as negative net interest) (ISG Equity financing desks) | spread unchanged; funding cost passed on; observable: Equity financing revenue; customer receivables | onset same quarter; build none; persists while balances hold; recognized daily accruals | documented / broker / model / inferred | spread compression; funding-cost spikes | Equity financing revenue | +1.00 sd/sd (identity) |
| 2 [rwa] `ms-c-prime-rwa` | Prime brokerage and other financing balances add counterparty and market risk-weighted assets (group) | balances grow at unchanged risk weights; observable: RWA against financing balances | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / inferred / unknown / documented | netting and collateral | risk-weighted assets | unknown |
| 3 [leverage] `ms-c-prime-leverage` | Financing balances enlarge the balance sheet and securities-financing exposures, unweighted (group) | balances on balance sheet; observable: total assets against financing balances | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / inferred / unknown / documented | netting | total leverage exposure | unknown |
| 4 `ms-a-eq-equity-financing` | Morgan Stanley Equity financing revenue is one part of Morgan Stanley Equity sales and trading revenue (Equity net revenues by business: financing and execution services); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Equity sales and trading revenue | +0.44 sd/sd (accounting) |
| 5 `ms-a-trd-equity-revenue` | Morgan Stanley Equity sales and trading revenue is one part of Morgan Stanley trading revenue (ISG sales and trading net revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | trading revenue | +0.76 sd/sd (accounting) |
| 6 `ms-a-isg-trading-revenue` | Morgan Stanley trading revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.80 sd/sd (accounting) |
| 7 `ms-a-seg-isg-revenue` | Morgan Stanley Institutional Securities net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.79 sd/sd (accounting) |
| 8 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 9 `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 10 `ms-c-ni-cet1` | Net income (after preferred dividends) adds to retained earnings and so to CET1 capital (group) | accumulation over the period; observable: CET1 capital roll-forward | onset quarter end; build cumulative; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | distributions above earnings | CET1 capital | +0.56 sd/sd (stock-flow, accumulates per 365 days) |
| 11 `ms-c-rwa-ratio` | More risk-weighted assets at the same capital lower the CET1 ratio (group) | capital unchanged; observable: RWA and the CET1 ratio | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | -2.00 sd/sd (identity) |
| 12 `ms-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets; more capital at the same RWA raises it (group) | RWA unchanged; observable: CET1 ratio, capital and RWA | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | +1.82 sd/sd (identity) |
| 13 `ms-c-leverage-slr` | More unweighted exposure (financing, inventory, deposits invested) at the same capital lowers the SLR (group) | capital unchanged; observable: SLR and total assets | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | supplementary leverage ratio | -1.36 sd/sd (identity) |
| 14 `ms-a-t1-cet1-capital` | Morgan Stanley CET1 capital is one part of Morgan Stanley tier 1 capital (tier 1 capital: CET1 plus preferred); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | tier 1 capital | +1.00 sd/sd (accounting) |
| 15 `ms-c-tier1-slr` | The supplementary leverage ratio is tier 1 capital over total leverage exposure (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | supplementary leverage ratio | +0.88 sd/sd (identity) |
| 16 `ms-c-ratio-buybacks` | Capital above the requirement and management's buffer is returned through buybacks under the multi-year authorization (board and management) | the ratio above requirement plus buffer; observable: CET1 ratio against requirement; buybacks executed | onset next quarter; build through the year; persists while excess lasts; recognized quarterly buybacks | documented / documented / unknown / documented | growth opportunities absorb capital; pending capital rules | share buybacks | unknown |
| 17 `ms-c-slr-buybacks` | When the SLR is the binding constraint, its headroom over the requirement limits buybacks and balance-sheet growth (board and management) | the SLR binds before the CET1 ratio; observable: SLR against its requirement | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / unknown / documented | leverage-rule reform loosens it | share buybacks | unknown |

Unresolved inputs: Equity financing revenue split (trading, fees, net interest) (found connected); RWA sensitivity to financing balances (not disclosed in reviewed sources); SLR as the binding constraint (found connected); capital cushion over the requirement and the authorization (found connected); exposure sensitivity to financing balances (not disclosed in reviewed sources); management CET1 target (not disclosed in reviewed sources); total leverage exposure (not disclosed in reviewed sources).

#### Morgan Stanley capital and payout

**Trigger:** earnings accumulate. **Endpoint:** Morgan Stanley share buybacks.

Morgan Stanley net income → [retain] Morgan Stanley CET1 capital → [dividend] Morgan Stanley common dividends? → Morgan Stanley CET1 capital → Morgan Stanley CET1 ratio → Morgan Stanley tier 1 capital → Morgan Stanley supplementary leverage ratio → Morgan Stanley share buybacks? → Morgan Stanley share buybacks? → Morgan Stanley CET1 capital  (? marks a step whose size is unknown)

Net income adds to CET1 and supports the dividend; the excess over the requirement and buffer (or the leverage headroom when it binds) funds buybacks, which use capital in turn.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [retain] `ms-c-ni-cet1` | Net income (after preferred dividends) adds to retained earnings and so to CET1 capital (group) | accumulation over the period; observable: CET1 capital roll-forward | onset quarter end; build cumulative; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | distributions above earnings | CET1 capital | +0.56 sd/sd (stock-flow, accumulates per 365 days) |
| 2 [dividend] `ms-c-ni-dividends` | The board sets the dividend on sustainable earnings; it was raised after the latest stress test (group) | earnings and the stress-test result; observable: dividends per share; payout ratio | onset annual, after the stress test; build none; persists a year; recognized dividends declared | documented / documented / unknown / documented | a weak stress-test result | common dividends | unknown |
| 3 `ms-c-dividends-cet1` | Common dividends declared reduce retained earnings and CET1 capital (group) | declared in the period; observable: CET1 roll-forward | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity of the roll-forward) | CET1 capital | -0.13 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `ms-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets; more capital at the same RWA raises it (group) | RWA unchanged; observable: CET1 ratio, capital and RWA | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | +1.82 sd/sd (identity) |
| 5 `ms-a-t1-cet1-capital` | Morgan Stanley CET1 capital is one part of Morgan Stanley tier 1 capital (tier 1 capital: CET1 plus preferred); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | tier 1 capital | +1.00 sd/sd (accounting) |
| 6 `ms-c-tier1-slr` | The supplementary leverage ratio is tier 1 capital over total leverage exposure (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | supplementary leverage ratio | +0.88 sd/sd (identity) |
| 7 `ms-c-ratio-buybacks` | Capital above the requirement and management's buffer is returned through buybacks under the multi-year authorization (board and management) | the ratio above requirement plus buffer; observable: CET1 ratio against requirement; buybacks executed | onset next quarter; build through the year; persists while excess lasts; recognized quarterly buybacks | documented / documented / unknown / documented | growth opportunities absorb capital; pending capital rules | share buybacks | unknown |
| 8 `ms-c-slr-buybacks` | When the SLR is the binding constraint, its headroom over the requirement limits buybacks and balance-sheet growth (board and management) | the SLR binds before the CET1 ratio; observable: SLR against its requirement | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / unknown / documented | leverage-rule reform loosens it | share buybacks | unknown |
| 9 `ms-c-buyback-cet1` | Share repurchases reduce common equity and CET1 capital dollar for dollar (group) | executed under the authorization; observable: treasury stock purchased; CET1 roll-forward | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity of the roll-forward) | CET1 capital | -0.50 sd/sd (stock-flow, accumulates per 365 days) |

Unresolved inputs: SLR as the binding constraint (found connected); capital cushion over the requirement and the authorization (found connected); dividend history and the latest increase (found connected); management CET1 target (not disclosed in reviewed sources).

#### Morgan Stanley capital requirements

**Trigger:** the stress capital buffer or surcharge rises. **Endpoint:** Morgan Stanley CET1 ratio.

Morgan Stanley CET1 requirement → Morgan Stanley share buybacks? → Morgan Stanley CET1 capital → Morgan Stanley CET1 ratio → Morgan Stanley tier 1 capital → Morgan Stanley supplementary leverage ratio  (? marks a step whose size is unknown)

A higher requirement (stress capital buffer from the annual stress test, or surcharge) leaves less excess to return; fewer buybacks keep CET1 and the ratio higher.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ms-c-req-buybacks` | A higher stress capital buffer (from the annual stress test) or surcharge raises the requirement and absorbs capital that would be returned (regulators (stress test); board) | binding requirement; observable: requirement against the ratio | onset from the start of the stress-test year; build none; persists a year; recognized quarterly buybacks | documented / documented / unknown / documented | a lower requirement releases capital | share buybacks | unknown |
| 2 `ms-c-buyback-cet1` | Share repurchases reduce common equity and CET1 capital dollar for dollar (group) | executed under the authorization; observable: treasury stock purchased; CET1 roll-forward | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity of the roll-forward) | CET1 capital | -0.50 sd/sd (stock-flow, accumulates per 365 days) |
| 3 `ms-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets; more capital at the same RWA raises it (group) | RWA unchanged; observable: CET1 ratio, capital and RWA | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | +1.82 sd/sd (identity) |
| 4 `ms-a-t1-cet1-capital` | Morgan Stanley CET1 capital is one part of Morgan Stanley tier 1 capital (tier 1 capital: CET1 plus preferred); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | tier 1 capital | +1.00 sd/sd (accounting) |
| 5 `ms-c-tier1-slr` | The supplementary leverage ratio is tier 1 capital over total leverage exposure (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | supplementary leverage ratio | +0.88 sd/sd (identity) |

Unresolved inputs: CET1 requirement (found connected).

#### Morgan Stanley credit spreads to provisions, marks and issuance

**Trigger:** credit spreads widen. **Endpoint:** Morgan Stanley net income.

US high-yield credit spread → [reserves] Morgan Stanley provision for credit losses? → [inventory] Morgan Stanley Fixed Income sales and trading revenue? → [loan_marks] Morgan Stanley ISG other revenue? → [issuance] Morgan Stanley fixed income underwriting revenue? → [deals] Deal and issuance activity? → Morgan Stanley completed M&A volume? → Morgan Stanley advisory revenue → Morgan Stanley trading revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley investment banking revenue → Morgan Stanley investment banking revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley Institutional Securities net revenues → Morgan Stanley net revenues → Morgan Stanley income before taxes → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

One widening, parallel responses: CECL reserves rise at once, credit inventory and fair-value loans mark down, debt issuance and leveraged finance slow, and deal activity falls.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [reserves] `ms-c-spread-provision` | Wider credit spreads come with a weaker outlook: CECL reserves on corporate and commercial real estate loans rise at once (provision more negative) (Morgan Stanley (credit risk)) | CECL outlook deteriorates; observable: provision; allowance for credit losses | onset same quarter (CECL); build none; persists until the outlook improves; recognized provision in the quarter | documented / inferred / unknown / inferred | a recovery releases reserves | provision for credit losses | unknown |
| 2 [inventory] `ms-c-spread-ficc` | Spread widening marks down credit inventory and slows structured credit and securitized products activity (fixed income desks) | a disorderly widening, not a gradual one; observable: FICC revenue against credit spreads | onset days; build none; persists while spreads stay wide; recognized trading revenue daily | documented / documented / unknown / inferred | wider spreads also raise client hedging | Fixed Income revenue | unknown |
| 3 [loan_marks] `ms-c-spread-isgother` | Corporate loans held for sale or at fair value, and their hedges, are marked to market: wider spreads cut ISG other revenue (ISG lending) | loans at fair value or held for sale; observable: ISG other revenue; mark-to-market on loans | onset same quarter; build none; persists until spreads tighten; recognized quarterly results | documented / documented / unknown / inferred | hedges; pull to par | ISG other revenue | unknown |
| 4 [issuance] `ms-c-spread-dcm` | Wider spreads raise borrowing costs and shut leveraged finance, so debt issuance and its fees fall (issuers) | a sustained widening; observable: DCM volumes against spreads | onset weeks; build until spreads tighten; persists while spreads stay wide; recognized fees at pricing | documented / documented / unknown / inferred | refinancing needs force issuance | fixed income underwriting revenue | unknown |
| 5 [deals] `jpm-c-spread-deals` | Wider spreads raise acquisition-finance costs and close the high-yield and leveraged-loan markets, so issuance and sponsor deals fall (issuers and financial sponsors) | spreads wide enough to break deal economics; observable: high-yield and leveraged-loan issuance; announced sponsor M&A | onset weeks; build 1-2 quarters; persists while spreads stay wide; recognized fees at completion | inferred / inferred / unknown / unknown | private credit fills the gap (fees lost to the bank) | deal and issuance activity | unknown |
| 6 `ms-c-deals-completedma` | Announced M&A completes two to four quarters later (regulatory and financing steps), and advisory fees are booked at completion (corporates and sponsors; regulators) | deals not withdrawn; observable: completed M&A volume against announcements | onset 2-4 quarters; build over the closing period; persists as the backlog completes; recognized advisory fees at completion | documented / documented / unknown / documented | deals pulled or blocked | completed M&A volume | unknown |
| 7 `ms-c-completedma-advisory` | Advisory revenue is completed volume times the realized fee rate (ISG advisory) | fee rate and share unchanged; observable: implied advisory fee rate | onset at completion; build none; persists event-driven; recognized quarterly results | documented / documented / model / documented | mix toward large deals at lower fee rates; share loss | advisory revenue | +1.00 sd/sd (identity) |
| 8 `ms-a-trd-ficc-revenue` | Morgan Stanley Fixed Income sales and trading revenue is one part of Morgan Stanley trading revenue (ISG sales and trading net revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | trading revenue | +0.40 sd/sd (accounting) |
| 9 `ms-a-isg-trading-revenue` | Morgan Stanley trading revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.80 sd/sd (accounting) |
| 10 `ms-a-ib-dcm-fees` | Morgan Stanley fixed income underwriting revenue is one part of Morgan Stanley investment banking revenue (ISG investment banking revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | investment banking revenue | +0.45 sd/sd (accounting) |
| 11 `ms-a-ib-advisory-fees` | Morgan Stanley advisory revenue is one part of Morgan Stanley investment banking revenue (ISG investment banking revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | investment banking revenue | +0.64 sd/sd (accounting) |
| 12 `ms-a-isg-ib-fees` | Morgan Stanley investment banking revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.21 sd/sd (accounting) |
| 13 `ms-a-isg-isg-other-revenue` | Morgan Stanley ISG other revenue is the residual of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.14 sd/sd (accounting) |
| 14 `ms-a-seg-isg-revenue` | Morgan Stanley Institutional Securities net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.79 sd/sd (accounting) |
| 15 `ms-a-pretax-provision-for-credit-losses` | Morgan Stanley provision for credit losses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.07 sd/sd (accounting) |
| 16 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 17 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 18 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 19 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: CECL scenario sensitivity (not disclosed in reviewed sources); DCM sensitivity to spreads (not disclosed in reviewed sources); FICC sensitivity to credit spreads (not disclosed in reviewed sources); advisory backlog (not disclosed in reviewed sources); completed M&A volume (found connected); effective tax rate (found connected); fair-value loan exposure and hedge ratio (not disclosed in reviewed sources); implied advisory fee rate (found connected); provision and allowance history (found connected).

#### Morgan Stanley deal activity to investment banking fees

**Trigger:** deal and issuance activity picks up. **Endpoint:** Morgan Stanley net income.

Deal and issuance activity → [advisory] Morgan Stanley completed M&A volume? → [ecm] Morgan Stanley equity underwriting revenue? → [dcm] Morgan Stanley fixed income underwriting revenue? → Morgan Stanley advisory revenue → Morgan Stanley investment banking revenue → Morgan Stanley investment banking revenue → Morgan Stanley investment banking revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley net revenues → Morgan Stanley compensation and benefits → Morgan Stanley non-interest expenses → Morgan Stanley income before taxes → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

Announced M&A completes two to four quarters later and pays advisory fees at completion; equity and debt issuance pay underwriting fees in the quarter priced; incentive pay takes a share. s13 is the reduced form on investment banking revenue and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [advisory] `ms-c-deals-completedma` | Announced M&A completes two to four quarters later (regulatory and financing steps), and advisory fees are booked at completion (corporates and sponsors; regulators) | deals not withdrawn; observable: completed M&A volume against announcements | onset 2-4 quarters; build over the closing period; persists as the backlog completes; recognized advisory fees at completion | documented / documented / unknown / documented | deals pulled or blocked | completed M&A volume | unknown |
| 2 [ecm] `ms-c-deals-ecm` | Equity underwriting fees track issuance volume priced in the quarter (issuers; ECM desk) | the window is open; observable: ECM volume; implied fee rate | onset same quarter; build none; persists event-driven; recognized fees at pricing | documented / documented / unknown / documented | volatility; a closed window | equity underwriting revenue | unknown |
| 3 [dcm] `ms-c-deals-dcm` | Debt underwriting fees track investment-grade, high-yield and leveraged-loan issuance (issuers; DCM desk) | credit markets open; observable: DCM volume; implied fee rate | onset same quarter; build none; persists event-driven; recognized fees at pricing | documented / documented / unknown / documented | wider spreads (ms-c-spread-dcm); higher all-in yields (ms-c-ust10-dcm) | fixed income underwriting revenue | unknown |
| 4 `ms-c-completedma-advisory` | Advisory revenue is completed volume times the realized fee rate (ISG advisory) | fee rate and share unchanged; observable: implied advisory fee rate | onset at completion; build none; persists event-driven; recognized quarterly results | documented / documented / model / documented | mix toward large deals at lower fee rates; share loss | advisory revenue | +1.00 sd/sd (identity) |
| 5 `ms-a-ib-advisory-fees` | Morgan Stanley advisory revenue is one part of Morgan Stanley investment banking revenue (ISG investment banking revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | investment banking revenue | +0.64 sd/sd (accounting) |
| 6 `ms-a-ib-ecm-fees` | Morgan Stanley equity underwriting revenue is one part of Morgan Stanley investment banking revenue (ISG investment banking revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | investment banking revenue | +0.61 sd/sd (accounting) |
| 7 `ms-a-ib-dcm-fees` | Morgan Stanley fixed income underwriting revenue is one part of Morgan Stanley investment banking revenue (ISG investment banking revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | investment banking revenue | +0.45 sd/sd (accounting) |
| 8 `ms-a-isg-ib-fees` | Morgan Stanley investment banking revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.21 sd/sd (accounting) |
| 9 `ms-a-seg-isg-revenue` | Morgan Stanley Institutional Securities net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.79 sd/sd (accounting) |
| 10 `ms-c-revenue-comp` | Compensation is the compensation ratio times net revenues (held negative): more revenue, a larger charge at the same ratio (incentive accruals, the advisor payout, carried interest) (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | compensation and benefits | -1.04 sd/sd (identity) |
| 11 `ms-a-exp-compensation-expense` | Morgan Stanley compensation and benefits is one part of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.70 sd/sd (accounting) |
| 12 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 13 `ms-a-pretax-noninterest-expense` | Morgan Stanley non-interest expenses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.91 sd/sd (accounting) |
| 14 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 15 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 16 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: DCM fee elasticity to issuance volume (not disclosed in reviewed sources); ECM fee elasticity to issuance volume (not disclosed in reviewed sources); advisor payout grid (not disclosed in reviewed sources); advisory backlog (not disclosed in reviewed sources); compensation ratio (found connected); completed M&A volume (found connected); effective tax rate (found connected); implied advisory fee rate (found connected).

#### Morgan Stanley expense inflation and operating leverage

**Trigger:** core inflation rises. **Endpoint:** Morgan Stanley net income.

US core CPI → [wages] Morgan Stanley compensation and benefits? → [vendors] Morgan Stanley other non-compensation expenses? → Morgan Stanley non-interest expenses → Morgan Stanley non-interest expenses → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

Wage and vendor inflation raise the fixed costs; revenue-linked pay (incentives, the advisor payout) is the variable part and runs through the revenue paths. Operating leverage is revenue growth less expense growth.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [wages] `ms-c-cpi-comp` | Wage inflation raises salaries and benefits (the fixed part of compensation) (labour market) | persistent core inflation; observable: compensation per employee | onset annual pay cycle; build a year; persists persistent; recognized quarterly results | inferred / inferred / unknown / inferred | headcount actions; automation | compensation and benefits | unknown |
| 2 [vendors] `ms-c-cpi-othernoncomp` | Inflation raises occupancy, professional services and other vendor costs (vendors) | contracts reprice; observable: non-compensation expenses | onset as contracts renew; build a year; persists persistent; recognized quarterly results | inferred / inferred / unknown / inferred | efficiency programmes | other non-compensation expenses | unknown |
| 3 `ms-a-exp-compensation-expense` | Morgan Stanley compensation and benefits is one part of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.70 sd/sd (accounting) |
| 4 `ms-a-exp-other-noncomp-expense` | Morgan Stanley other non-compensation expenses is the residual of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.35 sd/sd (accounting) |
| 5 `ms-a-pretax-noninterest-expense` | Morgan Stanley non-interest expenses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.91 sd/sd (accounting) |
| 6 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 7 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 8 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: effective tax rate (found connected).

#### Morgan Stanley IM flows to management fees

**Trigger:** clients add net flows to Investment Management. **Endpoint:** Morgan Stanley net income.

Morgan Stanley IM net flows → Morgan Stanley IM assets under management → Morgan Stanley IM asset management fees → Morgan Stanley Investment Management net revenues → [firm] Morgan Stanley net revenues → [segment] Morgan Stanley IM pretax income? → Morgan Stanley compensation and benefits → Morgan Stanley non-interest expenses → Morgan Stanley income before taxes → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

Flows accumulate into AUM (ms.sf.im_aum) and fees are AUM times the fee rate (ms.id.im_fees), so a flow reaches fees exactly (mix toward liquidity lowers the rate). Market impact on AUM and fund marks runs through ms.path.market_levels.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ms-c-imflows-aum` | AUM accumulates: beginning plus net flows less distributions plus market impact (IM clients) | accumulation over the period; observable: AUM roll-forward | onset same quarter; build cumulative; persists permanent; recognized period-end statistics | documented / documented / model / documented | none (roll-forward) | IM AUM | +0.42 sd/sd (stock-flow, accumulates per 365 days) |
| 2 `ms-c-aum-imfees` | IM management fees are average AUM times the fee rate (Investment Management) | fee rate and mix unchanged; observable: IM fees; average AUM | onset same quarter; build none; persists while AUM holds; recognized quarterly results | documented / documented / model / documented | mix shift to liquidity (low fee) and passive | IM asset management fees | +1.00 sd/sd (identity) |
| 3 `ms-a-im-im-mgmt-fees` | Morgan Stanley IM asset management fees is one part of Morgan Stanley Investment Management net revenues (Investment Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Investment Management net revenues | +0.66 sd/sd (accounting) |
| 4 [firm] `ms-a-seg-im-revenue` | Morgan Stanley Investment Management net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.13 sd/sd (accounting) |
| 5 [segment] `ms-c-bridge-im-pretax` | Bridge to the segment pretax view: IM revenue less IM expenses is IM pretax. No size; never added (none (reporting)) | same basis and period; observable: segment and line tables in the supplement | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / unknown / documented | other segments' amounts in the same line | IM pretax income | unknown |
| 6 `ms-c-revenue-comp` | Compensation is the compensation ratio times net revenues (held negative): more revenue, a larger charge at the same ratio (incentive accruals, the advisor payout, carried interest) (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | compensation and benefits | -1.04 sd/sd (identity) |
| 7 `ms-a-exp-compensation-expense` | Morgan Stanley compensation and benefits is one part of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.70 sd/sd (accounting) |
| 8 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 9 `ms-a-pretax-noninterest-expense` | Morgan Stanley non-interest expenses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.91 sd/sd (accounting) |
| 10 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 11 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 12 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: advisor payout grid (not disclosed in reviewed sources); compensation ratio (found connected); effective tax rate (found connected).

#### Morgan Stanley long-end yields to capital, fees and issuance

**Trigger:** long-end Treasury yields rise. **Endpoint:** Morgan Stanley CET1 ratio.

UST 10Y yield → [marks] Morgan Stanley AOCI? → [bond_sleeve] Morgan Stanley WM fee-based client assets? → [carry] Morgan Stanley IM performance-based income? → [issuance] Morgan Stanley fixed income underwriting revenue? → Morgan Stanley WM asset management fees → Morgan Stanley wealth management revenue → Morgan Stanley Investment Management net revenues → Morgan Stanley investment banking revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley net revenues → Morgan Stanley net revenues → Morgan Stanley net revenues → Morgan Stanley income before taxes → Morgan Stanley net income → Morgan Stanley CET1 capital? → Morgan Stanley CET1 capital → Morgan Stanley CET1 ratio  (? marks a step whose size is unknown)

One move, parallel responses: AFS securities mark down into AOCI and CET1, the bond sleeve of fee-based assets falls, real-asset fund marks reverse carried interest, and refinancing is deferred. Dearer financing also defers deals through s74, a shared statistical record without a transition that is left untouched (its fees run through ms.path.deals_ib).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [marks] `ms-c-ust10-aoci` | Higher long yields mark down available-for-sale securities; the after-tax loss in AOCI counts in CET1 for this firm (market; regulation (AOCI in CET1)) | AFS duration after hedges; observable: AOCI and AFS unrealized losses each quarter | onset immediate; build none; persists pulls to par as securities mature; recognized quarter-end capital | documented / documented / unknown / documented | short duration, swaps and held-to-maturity classification | AOCI | unknown |
| 2 [bond_sleeve] `ms-c-ust10-feeassets` | Higher long yields lower bond prices in the fixed income and cash share of fee-based assets (markets) | the fixed income share of fee-based assets; observable: fee-based asset market impact | onset immediate; build none; persists while yields hold; recognized fees billed on prior month-end values | documented / documented / unknown / documented | short duration of the bond sleeve; cash earns more | WM fee-based assets | unknown |
| 3 [carry] `ms-c-ust10-perf` | Higher discount rates lower infrastructure and real-asset fund marks, reversing accrued carried interest (Investment Management (private funds)) | real-asset funds above hurdle; observable: fund marks; performance-based income | onset 1 quarter; build none; persists until marks recover; recognized quarterly marks | documented / documented / unknown / documented | fund-specific events dominate | IM performance-based income | unknown |
| 4 [issuance] `ms-c-ust10-dcm` | Higher long yields raise all-in borrowing costs, so issuers defer refinancing (issuers) | issuers can wait; observable: DCM volumes against yields | onset weeks; build quarters; persists while yields stay high; recognized fees at pricing | documented / documented / unknown / inferred | maturity walls force issuance | fixed income underwriting revenue | unknown |
| 5 `ms-c-feeassets-amfees` | Asset management fees are fee-based assets times the fee rate, billed off prior month-end values (Morgan Stanley (advisory programmes)) | pricing unchanged; observable: WM asset management revenues; average fee-based assets | onset one month (billing lag); build none; persists while assets hold; recognized monthly billing, quarterly results | documented / documented / model / documented | fee-rate compression; mix toward cash management at low fees | WM asset management fees | +1.20 sd/sd (identity) |
| 6 `ms-a-wm-wm-asset-mgmt-fees` | Morgan Stanley WM asset management fees is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.60 sd/sd (accounting) |
| 7 `ms-a-im-im-performance-fees` | Morgan Stanley IM performance-based income is one part of Morgan Stanley Investment Management net revenues (Investment Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Investment Management net revenues | +0.66 sd/sd (accounting) |
| 8 `ms-a-ib-dcm-fees` | Morgan Stanley fixed income underwriting revenue is one part of Morgan Stanley investment banking revenue (ISG investment banking revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | investment banking revenue | +0.45 sd/sd (accounting) |
| 9 `ms-a-isg-ib-fees` | Morgan Stanley investment banking revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.21 sd/sd (accounting) |
| 10 `ms-a-seg-wealth-revenue` | Morgan Stanley wealth management revenue is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.42 sd/sd (accounting) |
| 11 `ms-a-seg-im-revenue` | Morgan Stanley Investment Management net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.13 sd/sd (accounting) |
| 12 `ms-a-seg-isg-revenue` | Morgan Stanley Institutional Securities net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.79 sd/sd (accounting) |
| 13 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 14 `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 15 `ms-c-aoci-cet1` | Unrealized gains and losses on AFS securities in AOCI are included in CET1 for this firm (a category I institution) (group) | AOCI included in CET1; observable: AOCI and CET1 capital | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / unknown / documented | regulatory change to the AOCI treatment | CET1 capital | unknown |
| 16 `ms-c-ni-cet1` | Net income (after preferred dividends) adds to retained earnings and so to CET1 capital (group) | accumulation over the period; observable: CET1 capital roll-forward | onset quarter end; build cumulative; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | distributions above earnings | CET1 capital | +0.56 sd/sd (stock-flow, accumulates per 365 days) |
| 17 `ms-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets; more capital at the same RWA raises it (group) | RWA unchanged; observable: CET1 ratio, capital and RWA | onset quarter end; build none; persists while it holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | +1.82 sd/sd (identity) |

Unresolved inputs: AFS book and unrealized losses (found connected); AFS duration and the AOCI sensitivity (not disclosed in reviewed sources); DCM sensitivity to long yields (not disclosed in reviewed sources); fee sensitivity to long yields (not disclosed in reviewed sources); fee-based asset averages and fee rate (found connected); performance-fee sensitivity to rates (not disclosed in reviewed sources).

#### Morgan Stanley market levels to asset-based fees

**Trigger:** US equity markets rise. **Endpoint:** Morgan Stanley net income.

US equity market level → [wm_fees] Morgan Stanley WM fee-based client assets? → [client_assets] Morgan Stanley WM total client assets? → [im_aum] Morgan Stanley IM assets under management? → [carry] Morgan Stanley IM performance-based income? → [prime] Morgan Stanley prime brokerage balances? → [activity] Morgan Stanley WM transactional revenue? → [deferred_pay] Morgan Stanley compensation and benefits? → [ipo_window] Morgan Stanley equity underwriting revenue? → Morgan Stanley WM asset management fees → Morgan Stanley WM loans? → Morgan Stanley WM interest earned on loans → Morgan Stanley WM interest income → Morgan Stanley WM net interest income → Morgan Stanley IM asset management fees → Morgan Stanley Equity financing revenue → Morgan Stanley wealth management revenue → Morgan Stanley wealth management revenue → Morgan Stanley wealth management revenue → Morgan Stanley Investment Management net revenues → Morgan Stanley Investment Management net revenues → Morgan Stanley Equity sales and trading revenue → Morgan Stanley trading revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley investment banking revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley net revenues → Morgan Stanley net revenues → Morgan Stanley net revenues → Morgan Stanley compensation and benefits → Morgan Stanley non-interest expenses → Morgan Stanley income before taxes → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

One market move, parallel responses: fee-based assets reprice (fees a month later), client assets and lending capacity rise, IM AUM and fund marks rise, prime balances grow, retail activity and deferred-plan hedges lift transactional revenue while the same plans raise pay (an offset), and the IPO window opens. ms-c-equity-amfees (calibrated from management's asset mix) is the reduced form on WM asset management fees and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [wm_fees] `ms-c-equity-feeassets` | Market moves revalue advisory accounts; the fee base is mostly equities with a fixed income and cash sleeve (management's stated mix), so it moves by a fraction of an equity-market move set by that share, besides flows (markets; WM clients) | the equity share of fee-based assets; observable: fee-based asset roll-forward: market impact versus flows | onset immediate; build none; persists while levels hold; recognized fees billed on prior month-end values | documented / documented / unknown / documented | outflows in a sell-off; clients de-risk into cash | WM fee-based assets | unknown |
| 2 [client_assets] `ms-c-equity-clientassets` | Total client assets (advisor-led, self-directed, workplace stock plans) mark with markets (markets) | the equity share of client assets; observable: client assets roll-forward | onset immediate; build none; persists while levels hold; recognized period-end statistics | documented / documented / unknown / documented | outflows; unvested stock-plan assets are partly outside client assets | WM client assets | unknown |
| 3 [im_aum] `ms-c-equity-aum` | Market moves revalue IM's equity and part of its alternatives and solutions AUM; fixed income and liquidity move little (markets) | the market-sensitive share of AUM; observable: AUM roll-forward: market impact versus flows | onset immediate; build none; persists while levels hold; recognized fees on average AUM | documented / documented / unknown / documented | outflows; liquidity AUM grows when markets fall | IM AUM | unknown |
| 4 [carry] `ms-c-equity-perf` | Carried interest accrues on private-fund marks and reverses when asset values fall; performance-based income follows market and private-asset valuations (Investment Management (private funds)) | funds above their hurdle; marks follow public comparables; observable: performance-based income; fund marks | onset same quarter; build none; persists until realized or reversed; recognized quarterly marks | documented / documented / unknown / inferred | reversals on specific funds (a broker records one in the latest quarter) | IM performance-based income | unknown |
| 5 [prime] `ms-c-equity-prime` | Prime brokerage financing balances scale with the market value of hedge-fund portfolios and client leverage (hedge funds (prime clients)) | client gross leverage holds; observable: customer receivables; prime balances | onset same quarter; build none; persists while levels hold; recognized daily financing accruals | documented / broker / unknown / inferred | forced deleveraging | prime brokerage balances | unknown |
| 6 [activity] `ms-c-equity-transactional` | Higher equity prices lift retail and self-directed activity, and the hedges of deferred cash-based compensation plans gain in transactional revenue (offset in compensation, ms-c-equity-dcpcomp) (WM clients; Morgan Stanley (plan hedges)) | client risk appetite; observable: transactional revenues; plan mark-to-market | onset same quarter; build none; persists while levels hold; recognized quarterly results | documented / documented / unknown / documented | a falling market reverses the plan marks | WM transactional revenue | unknown |
| 7 [deferred_pay] `ms-c-equity-dcpcomp` | Counter-path: deferred cash-based compensation plans are referenced to market investments, so higher markets raise compensation expense, offsetting the hedge gains in transactional revenue (roughly pretax-neutral) (Morgan Stanley (compensation plans)) | plan liabilities hedged; observable: compensation and transactional plan marks | onset same quarter; build none; persists while levels hold; recognized quarterly results | documented / documented / unknown / documented | unhedged plans; vesting | compensation and benefits | unknown |
| 8 [ipo_window] `ms-c-equity-ecm` | Higher and steadier equity markets open the IPO and follow-on window, and issuers price in the quarter (issuers; ECM desk) | low volatility with rising prices; observable: ECM volumes; IPO pricing | onset same quarter; build 1-2 quarters as the backlog prices; persists while the window holds; recognized fees at pricing | documented / documented / unknown / inferred | volatility closes the window (ms-c-vol-ecm) | equity underwriting revenue | unknown |
| 9 `ms-c-feeassets-amfees` | Asset management fees are fee-based assets times the fee rate, billed off prior month-end values (Morgan Stanley (advisory programmes)) | pricing unchanged; observable: WM asset management revenues; average fee-based assets | onset one month (billing lag); build none; persists while assets hold; recognized monthly billing, quarterly results | documented / documented / model / documented | fee-rate compression; mix toward cash management at low fees | WM asset management fees | +1.20 sd/sd (identity) |
| 10 `ms-c-clientassets-loans` | Securities-based lending is secured by client portfolios; higher asset values raise borrowing capacity and demand (WM clients; Morgan Stanley (lending)) | client demand for liquidity; advance rates unchanged; observable: securities-based loans against client assets | onset 1-2 quarters; build several quarters; persists while assets hold; recognized average balances | documented / inferred / unknown / unknown | margin calls and pay-downs in a sell-off; rate costs of borrowing | WM loans | unknown |
| 11 `ms-c-loans-loaninterest` | WM loan interest is loans times the loan rate; more loans earn more (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM loan interest | +0.67 sd/sd (identity) |
| 12 `ms-a-wmii-wm-loan-interest-income` | Morgan Stanley WM interest earned on loans is one part of Morgan Stanley WM interest income (WM interest income: loans plus securities and cash); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | WM interest income | +0.65 sd/sd (accounting) |
| 13 `ms-c-wmii-wmnii` | WM NII is WM interest income less interest paid on deposits (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM net interest income | +2.15 sd/sd (identity) |
| 14 `ms-c-aum-imfees` | IM management fees are average AUM times the fee rate (Investment Management) | fee rate and mix unchanged; observable: IM fees; average AUM | onset same quarter; build none; persists while AUM holds; recognized quarterly results | documented / documented / model / documented | mix shift to liquidity (low fee) and passive | IM asset management fees | +1.00 sd/sd (identity) |
| 15 `ms-c-prime-financing` | Equity financing revenue is roughly balances times the financing spread (net of the funding cost booked as negative net interest) (ISG Equity financing desks) | spread unchanged; funding cost passed on; observable: Equity financing revenue; customer receivables | onset same quarter; build none; persists while balances hold; recognized daily accruals | documented / broker / model / inferred | spread compression; funding-cost spikes | Equity financing revenue | +1.00 sd/sd (identity) |
| 16 `ms-a-wm-wm-asset-mgmt-fees` | Morgan Stanley WM asset management fees is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.60 sd/sd (accounting) |
| 17 `ms-a-wm-wm-transactional` | Morgan Stanley WM transactional revenue is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.30 sd/sd (accounting) |
| 18 `ms-a-wm-wm-nii` | Morgan Stanley WM net interest income is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.28 sd/sd (accounting) |
| 19 `ms-a-im-im-mgmt-fees` | Morgan Stanley IM asset management fees is one part of Morgan Stanley Investment Management net revenues (Investment Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Investment Management net revenues | +0.66 sd/sd (accounting) |
| 20 `ms-a-im-im-performance-fees` | Morgan Stanley IM performance-based income is one part of Morgan Stanley Investment Management net revenues (Investment Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Investment Management net revenues | +0.66 sd/sd (accounting) |
| 21 `ms-a-eq-equity-financing` | Morgan Stanley Equity financing revenue is one part of Morgan Stanley Equity sales and trading revenue (Equity net revenues by business: financing and execution services); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Equity sales and trading revenue | +0.44 sd/sd (accounting) |
| 22 `ms-a-trd-equity-revenue` | Morgan Stanley Equity sales and trading revenue is one part of Morgan Stanley trading revenue (ISG sales and trading net revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | trading revenue | +0.76 sd/sd (accounting) |
| 23 `ms-a-isg-trading-revenue` | Morgan Stanley trading revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.80 sd/sd (accounting) |
| 24 `ms-a-ib-ecm-fees` | Morgan Stanley equity underwriting revenue is one part of Morgan Stanley investment banking revenue (ISG investment banking revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | investment banking revenue | +0.61 sd/sd (accounting) |
| 25 `ms-a-isg-ib-fees` | Morgan Stanley investment banking revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.21 sd/sd (accounting) |
| 26 `ms-a-seg-wealth-revenue` | Morgan Stanley wealth management revenue is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.42 sd/sd (accounting) |
| 27 `ms-a-seg-im-revenue` | Morgan Stanley Investment Management net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.13 sd/sd (accounting) |
| 28 `ms-a-seg-isg-revenue` | Morgan Stanley Institutional Securities net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.79 sd/sd (accounting) |
| 29 `ms-c-revenue-comp` | Compensation is the compensation ratio times net revenues (held negative): more revenue, a larger charge at the same ratio (incentive accruals, the advisor payout, carried interest) (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | compensation and benefits | -1.04 sd/sd (identity) |
| 30 `ms-a-exp-compensation-expense` | Morgan Stanley compensation and benefits is one part of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.70 sd/sd (accounting) |
| 31 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 32 `ms-a-pretax-noninterest-expense` | Morgan Stanley non-interest expenses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.91 sd/sd (accounting) |
| 33 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 34 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 35 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: AUM by asset class and market impact (found connected); ECM fee sensitivity to equity levels (not disclosed in reviewed sources); Equity financing revenue split (trading, fees, net interest) (found connected); advisor payout grid (not disclosed in reviewed sources); compensation ratio (found connected); deferred-compensation plan marks (found connected); deferred-compensation plan marks in transactional (found connected); effective tax rate (found connected); equity share of fee-based assets (found connected); equity weight of total client assets (not disclosed in reviewed sources); fee-based asset averages and fee rate (found connected); fee-based asset roll-forward (market impact) (found connected); lending penetration of client assets (not disclosed in reviewed sources); performance-fee sensitivity to markets (not disclosed in reviewed sources); prime balance proxy (customer receivables) (found connected); prime balance sensitivity to equity levels (not disclosed in reviewed sources); transactional sensitivity to equity levels (not disclosed in reviewed sources).

#### Morgan Stanley net new assets: the workplace and advisory funnel

**Trigger:** IPOs and liquidity events release stock-plan assets into workplace accounts. **Endpoint:** Morgan Stanley net income.

Deal and issuance activity → Morgan Stanley WM net new assets? → [advisory] Morgan Stanley WM fee-based asset flows? → [assets] Morgan Stanley WM total client assets → [cash] Morgan Stanley WM brokerage sweep deposits? → Morgan Stanley WM fee-based client assets → Morgan Stanley WM asset management fees → Morgan Stanley WM loans? → Morgan Stanley WM interest earned on loans → Morgan Stanley WM interest income → Morgan Stanley WM net interest income → Morgan Stanley WM cost of deposits? → Morgan Stanley WM interest paid on deposits → Morgan Stanley WM net interest income → Morgan Stanley WM deposits → Morgan Stanley WM interest paid on deposits → Morgan Stanley wealth management revenue → Morgan Stanley wealth management revenue → Morgan Stanley net revenues → Morgan Stanley compensation and benefits → Morgan Stanley non-interest expenses → Morgan Stanley income before taxes → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

Net new assets arrive through workplace stock plans and self-directed accounts, convert over years into fee-based advisory accounts, and bring cash that sweeps into the banks. Client assets and fee-based assets accumulate their flows (ms.sf.client_assets, ms.sf.fee_based_assets) and fees are assets times the fee rate (ms.id.wm_am_fees), so a fee-based flow reaches fees exactly; the funnel's own conversions are sign-only.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ms-c-deals-nna` | IPOs and corporate liquidity events release stock-plan shares into workplace accounts, and the firm converts part into net new assets (issuers and their employees (workplace stock plans)) | the firm administers the issuers' stock plans; observable: net new assets; the IPO share of NNA | onset vesting and lock-up expiry; build 1-3 quarters; persists event-driven; recognized quarterly NNA | documented / broker / unknown / inferred | lock-ups; assets leave once sold | WM net new assets | unknown |
| 2 [advisory] `ms-c-nna-feeflows` | Net new assets in workplace and self-directed channels are converted over time into advisor-led and fee-based accounts (the funnel) (WM advisors) | advisor capacity; client adoption; observable: fee-based flows against NNA | onset 1-4 quarters; build several years; persists persistent; recognized quarterly flows | documented / broker / unknown / unknown | assets stay self-directed or in cash | WM fee-based flows | unknown |
| 3 [assets] `ms-c-nna-clientassets` | Client assets accumulate: next period's are this period's plus net new assets plus market impact (WM clients) | accumulation over the period; observable: client assets roll-forward | onset same quarter; build cumulative; persists permanent; recognized period-end statistics | documented / documented / model / documented | none (roll-forward) | WM client assets | +0.14 sd/sd (stock-flow, accumulates per 365 days) |
| 4 [cash] `ms-c-nna-sweep` | New accounts arrive partly in cash, which sweeps into the banks (WM clients) | cash share of new assets; observable: sweep deposits against NNA | onset same quarter; build none; persists until deployed; recognized average balances | inferred / inferred / unknown / unknown | clients invest the cash or move it to money funds | WM brokerage sweep deposits | unknown |
| 5 `ms-c-feeflows-feeassets` | Fee-based assets accumulate: beginning plus inflows less outflows plus market impact (WM clients) | accumulation over the period; observable: fee-based asset roll-forward | onset same quarter; build cumulative; persists permanent; recognized period-end statistics | documented / documented / model / documented | none (roll-forward) | WM fee-based assets | +0.18 sd/sd (stock-flow, accumulates per 365 days) |
| 6 `ms-c-feeassets-amfees` | Asset management fees are fee-based assets times the fee rate, billed off prior month-end values (Morgan Stanley (advisory programmes)) | pricing unchanged; observable: WM asset management revenues; average fee-based assets | onset one month (billing lag); build none; persists while assets hold; recognized monthly billing, quarterly results | documented / documented / model / documented | fee-rate compression; mix toward cash management at low fees | WM asset management fees | +1.20 sd/sd (identity) |
| 7 `ms-c-clientassets-loans` | Securities-based lending is secured by client portfolios; higher asset values raise borrowing capacity and demand (WM clients; Morgan Stanley (lending)) | client demand for liquidity; advance rates unchanged; observable: securities-based loans against client assets | onset 1-2 quarters; build several quarters; persists while assets hold; recognized average balances | documented / inferred / unknown / unknown | margin calls and pay-downs in a sell-off; rate costs of borrowing | WM loans | unknown |
| 8 `ms-c-loans-loaninterest` | WM loan interest is loans times the loan rate; more loans earn more (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM loan interest | +0.67 sd/sd (identity) |
| 9 `ms-a-wmii-wm-loan-interest-income` | Morgan Stanley WM interest earned on loans is one part of Morgan Stanley WM interest income (WM interest income: loans plus securities and cash); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | WM interest income | +0.65 sd/sd (accounting) |
| 10 `ms-c-wmii-wmnii` | WM NII is WM interest income less interest paid on deposits (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM net interest income | +2.15 sd/sd (identity) |
| 11 `ms-c-sweep-depcost` | Sweep is the cheapest funding; as its share falls the weighted cost of deposits rises (mix), even at unchanged product rates (WM deposits (mix)) | the cost is a balance-weighted average of products (an identity of the mix); observable: sweep share of WM deposits; cost of deposits | onset same quarter; build none; persists while the mix holds; recognized net interest each quarter | documented / inferred / unknown / documented | sweep pricing changes | WM cost of deposits | unknown |
| 12 `ms-c-depcost-depinterest` | Interest paid on WM deposits is deposits times their cost; a beta passes part of a rate move into the cost (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM deposit interest | +0.79 sd/sd (identity) |
| 13 `ms-c-depinterest-wmnii` | WM NII is WM interest income less interest paid on deposits; deposit costs reduce it (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM net interest income | -1.84 sd/sd (identity) |
| 14 `ms-a-dep-wm-sweep-deposits` | Morgan Stanley WM brokerage sweep deposits is one part of Morgan Stanley WM deposits (Wealth Management deposits by type, period end); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | WM deposits | +0.51 sd/sd (accounting) |
| 15 `ms-c-deposits-depinterest` | Interest paid on WM deposits is deposits times their cost (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM deposit interest | +0.57 sd/sd (identity) |
| 16 `ms-a-wm-wm-asset-mgmt-fees` | Morgan Stanley WM asset management fees is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.60 sd/sd (accounting) |
| 17 `ms-a-wm-wm-nii` | Morgan Stanley WM net interest income is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.28 sd/sd (accounting) |
| 18 `ms-a-seg-wealth-revenue` | Morgan Stanley wealth management revenue is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.42 sd/sd (accounting) |
| 19 `ms-c-revenue-comp` | Compensation is the compensation ratio times net revenues (held negative): more revenue, a larger charge at the same ratio (incentive accruals, the advisor payout, carried interest) (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | compensation and benefits | -1.04 sd/sd (identity) |
| 20 `ms-a-exp-compensation-expense` | Morgan Stanley compensation and benefits is one part of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.70 sd/sd (accounting) |
| 21 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 22 `ms-a-pretax-noninterest-expense` | Morgan Stanley non-interest expenses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.91 sd/sd (accounting) |
| 23 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 24 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 25 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: IPO-related share of net new assets (found connected); advisor payout grid (not disclosed in reviewed sources); cash share of net new assets (not disclosed in reviewed sources); compensation ratio (found connected); conversion rate of new assets to fee-based (not disclosed in reviewed sources); effective tax rate (found connected); fee-based asset averages and fee rate (found connected); lending penetration of client assets (not disclosed in reviewed sources); net new asset sensitivity to IPO activity (not disclosed in reviewed sources); sweep and total deposit balances (found connected).

#### Morgan Stanley policy rate to WM net interest income

**Trigger:** the Fed raises the policy rate. **Endpoint:** Morgan Stanley net income.

Fed funds rate (midpoint) → [beta] Morgan Stanley WM cost of deposits? → [sorting] Morgan Stanley WM brokerage sweep deposits? → [savings] Morgan Stanley WM savings and other deposits? → [loans] Morgan Stanley interest rate earned on loans? → Morgan Stanley WM cost of deposits? → Morgan Stanley WM deposits → Morgan Stanley WM deposits → Morgan Stanley WM interest paid on deposits → Morgan Stanley WM net interest income → Morgan Stanley WM interest paid on deposits → Morgan Stanley WM interest earned on loans → Morgan Stanley WM interest income → Morgan Stanley WM net interest income → Morgan Stanley wealth management revenue → Morgan Stanley net revenues → Morgan Stanley compensation and benefits → Morgan Stanley non-interest expenses → Morgan Stanley income before taxes → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

Parallel responses of one rate move inside Wealth Management: savings and sweep rates follow by the beta, clients move cash out of sweep (cash sorting) partly into the firm's savings products, and floating securities-based loans reprice at once. WM NII is loan interest plus securities interest less deposit interest, each balance times rate an identity (ms.id.wm_loan_interest, ms.id.wm_deposit_interest, ms.id.wm_nii), so those steps are exact; the rate responses themselves (beta, sorting, repricing) are sign-only. s75 is the reduced form on WM revenue (calibrated from the disclosed WM NII sensitivity) and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [beta] `ms-c-fed-depcost` | The banks reprice savings and sweep deposits by a fraction of a policy-rate move (the deposit beta); savings products track market rates closely, sweep rates are administered and move little (Morgan Stanley (deposit pricing, WM banks)) | competition for client cash (money funds, other brokers' sweep and savings rates); the firm's funding need; observable: cost of deposits against the fed funds rate, quarterly | onset within the quarter of the move; build 1-3 quarters; persists while the policy rate holds; recognized net interest each quarter | documented / documented / unknown / inferred | cash sorting raises the average cost even without a rate move (ms-c-sweep-depcost); a cut lowers savings rates faster than sweep rates can fall (floors) | WM cost of deposits | unknown |
| 2 [sorting] `ms-c-fed-sweep` | Higher rates widen the gap between administered sweep rates and money funds or savings, so clients move cash out of brokerage sweep (cash sorting): part into the firm's savings products, part off the balance sheet (WM clients and advisors) | the gap between sweep rates and money-fund yields is noticed; transactional cash stays; observable: brokerage sweep deposits, quarterly | onset 1-2 quarters; build several quarters; persists reverses slowly when rates fall; recognized average balances and net interest | documented / inferred / unknown / unknown | sweep balances near a floor of operating cash; new accounts bring cash (ms-c-nna-sweep) | WM brokerage sweep deposits | unknown |
| 3 [savings] `ms-c-fed-savings` | Higher rates make the firm's savings and CD offerings competitive, capturing part of the cash that leaves sweep (at a higher cost) (Morgan Stanley (bank deposit programmes); WM clients) | the firm prices savings near market to keep balances on its balance sheet; observable: savings and other deposits, quarterly | onset 1-2 quarters; build several quarters; persists while rates hold; recognized average balances and interest expense | inferred / inferred / unknown / unknown | money funds and Treasury bills outbid the savings rate; the firm lets balances run off | WM savings and other deposits | unknown |
| 4 [loans] `ms-c-fed-loanyield` | Securities-based loans are mostly floating and reprice with short rates within weeks; mortgages reprice only as they are originated (Morgan Stanley (WM lending)) | the floating share of the loan book and any swaps converting it; observable: loan yield against SOFR, quarterly | onset within the month; build one reset cycle; persists while the rate holds; recognized net interest each quarter | documented / documented / unknown / inferred | receive-fixed hedges; spread compression on securities-based lending | loan yield | unknown |
| 5 `ms-c-sweep-depcost` | Sweep is the cheapest funding; as its share falls the weighted cost of deposits rises (mix), even at unchanged product rates (WM deposits (mix)) | the cost is a balance-weighted average of products (an identity of the mix); observable: sweep share of WM deposits; cost of deposits | onset same quarter; build none; persists while the mix holds; recognized net interest each quarter | documented / inferred / unknown / documented | sweep pricing changes | WM cost of deposits | unknown |
| 6 `ms-a-dep-wm-sweep-deposits` | Morgan Stanley WM brokerage sweep deposits is one part of Morgan Stanley WM deposits (Wealth Management deposits by type, period end); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | WM deposits | +0.51 sd/sd (accounting) |
| 7 `ms-a-dep-wm-other-deposits` | Morgan Stanley WM savings and other deposits is one part of Morgan Stanley WM deposits (Wealth Management deposits by type, period end); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | WM deposits | +0.82 sd/sd (accounting) |
| 8 `ms-c-deposits-depinterest` | Interest paid on WM deposits is deposits times their cost (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM deposit interest | +0.57 sd/sd (identity) |
| 9 `ms-c-depinterest-wmnii` | WM NII is WM interest income less interest paid on deposits; deposit costs reduce it (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM net interest income | -1.84 sd/sd (identity) |
| 10 `ms-c-depcost-depinterest` | Interest paid on WM deposits is deposits times their cost; a beta passes part of a rate move into the cost (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM deposit interest | +0.79 sd/sd (identity) |
| 11 `ms-c-loanrate-loaninterest` | WM loan interest is loans times the loan rate; floating securities-based loans reprice with short rates (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM loan interest | +0.77 sd/sd (identity) |
| 12 `ms-a-wmii-wm-loan-interest-income` | Morgan Stanley WM interest earned on loans is one part of Morgan Stanley WM interest income (WM interest income: loans plus securities and cash); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | WM interest income | +0.65 sd/sd (accounting) |
| 13 `ms-c-wmii-wmnii` | WM NII is WM interest income less interest paid on deposits (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | WM net interest income | +2.15 sd/sd (identity) |
| 14 `ms-a-wm-wm-nii` | Morgan Stanley WM net interest income is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.28 sd/sd (accounting) |
| 15 `ms-a-seg-wealth-revenue` | Morgan Stanley wealth management revenue is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.42 sd/sd (accounting) |
| 16 `ms-c-revenue-comp` | Compensation is the compensation ratio times net revenues (held negative): more revenue, a larger charge at the same ratio (incentive accruals, the advisor payout, carried interest) (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | compensation and benefits | -1.04 sd/sd (identity) |
| 17 `ms-a-exp-compensation-expense` | Morgan Stanley compensation and benefits is one part of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.70 sd/sd (accounting) |
| 18 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 19 `ms-a-pretax-noninterest-expense` | Morgan Stanley non-interest expenses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.91 sd/sd (accounting) |
| 20 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 21 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 22 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: advisor payout grid (not disclosed in reviewed sources); compensation ratio (found connected); cost of deposits history (found connected); deposit beta by product (sweep versus savings) (not disclosed in reviewed sources); effective tax rate (found connected); floating share of WM loans (not disclosed in reviewed sources); loan yield history (found connected); savings balance sensitivity to the policy rate (not disclosed in reviewed sources); sweep and total deposit balances (found connected); sweep balance sensitivity to the policy rate (not disclosed in reviewed sources).

#### Morgan Stanley slower growth to credit costs

**Trigger:** US growth slows. **Endpoint:** Morgan Stanley net income.

US real GDP growth → [labour] US unemployment rate? → Morgan Stanley provision for credit losses? → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

Slower growth raises unemployment, and CECL reserves on mortgages and corporate loans rise at once (securities-based loans are over-collateralized, so losses stay small). Growth also slows dealmaking through s09, a shared statistical record without a transition that is left untouched; its effect on fees runs through ms.path.deals_ib.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [labour] `jpm-c-gdp-unemp` | Growth below trend raises the unemployment rate with a lag (Okun's relation) (employers) | growth below potential for several quarters; observable: monthly payrolls and the unemployment rate | onset 1-2 quarters; build several quarters; persists while growth is weak; recognized monthly data | inferred / inferred / unknown / unknown | labour hoarding; falling participation | US unemployment rate | unknown |
| 2 `ms-c-unemp-provision` | Higher unemployment raises CECL reserves on mortgages and corporate loans (Morgan Stanley (credit risk)) | CECL outlook uses unemployment; observable: provision; allowance | onset same quarter (CECL); build none; persists until the outlook improves; recognized provision in the quarter | documented / documented / unknown / inferred | securities-based loans are over-collateralized, so losses stay small | provision for credit losses | unknown |
| 3 `ms-a-pretax-provision-for-credit-losses` | Morgan Stanley provision for credit losses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.07 sd/sd (accounting) |
| 4 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 5 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 6 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: effective tax rate (found connected); provision sensitivity to unemployment (not disclosed in reviewed sources).

#### Morgan Stanley volatility to trading and wealth activity

**Trigger:** market volatility rises. **Endpoint:** Morgan Stanley net income.

Rates and FX volatility → [execution] Morgan Stanley Equity execution services revenue? → [ficc] Morgan Stanley Fixed Income sales and trading revenue? → [retail] Morgan Stanley daily average revenue trades? → [ipo_window] Morgan Stanley equity underwriting revenue? → [risk_off] US equity market level? → [credit] US high-yield credit spread? → [costs] Morgan Stanley brokerage, clearing and exchange fees? → Morgan Stanley WM transactional revenue? → Morgan Stanley WM fee-based client assets? → Morgan Stanley WM asset management fees → Morgan Stanley prime brokerage balances? → Morgan Stanley Equity financing revenue → Morgan Stanley Fixed Income sales and trading revenue? → Morgan Stanley Equity sales and trading revenue → Morgan Stanley Equity sales and trading revenue → Morgan Stanley trading revenue → Morgan Stanley trading revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley investment banking revenue → Morgan Stanley Institutional Securities net revenues → Morgan Stanley wealth management revenue → Morgan Stanley wealth management revenue → Morgan Stanley net revenues → Morgan Stanley net revenues → Morgan Stanley compensation and benefits → Morgan Stanley non-interest expenses → Morgan Stanley non-interest expenses → Morgan Stanley income before taxes → Morgan Stanley income before taxes → [earnings] Morgan Stanley net income → [tax] Morgan Stanley provision for income taxes → Morgan Stanley net income  (? marks a step whose size is unknown)

Volatility lifts equity execution, macro FICC and retail trading, but the same shock usually lowers equity prices (fee-based assets and prime balances fall), widens spreads (inventory marks), shuts the IPO window and raises clearing costs; incentive pay takes a share of revenue. s15 (sales and trading) and s17 (WM revenue) are the reduced forms and are never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [execution] `ms-c-vol-execution` | Volatility drives client hedging and derivatives and cash volumes in equity execution; s15 is the reduced form on sales and trading and is never added to this path (institutional clients; equity desks) | orderly volatility with client activity; observable: equity execution revenue against volatility and volumes | onset same quarter; build none; persists while volatility lasts; recognized trading revenue daily | documented / documented / unknown / inferred | disorderly markets: inventory losses | Equity execution revenue | unknown |
| 2 [ficc] `ms-c-vol-ficc` | Rate and FX volatility and curve moves drive macro client activity in fixed income (institutional and corporate clients) | orderly volatility; observable: FICC revenue against rates and FX volatility | onset same quarter; build none; persists while volatility lasts; recognized trading revenue daily | documented / documented / unknown / inferred | low volatility across asset classes (the research notes it for the latest quarter); inventory marks | Fixed Income revenue | unknown |
| 3 [retail] `ms-c-vol-darts` | Retail and self-directed clients trade more when markets move (self-directed clients) | retail engagement; observable: daily average revenue trades | onset same month; build none; persists while volatility lasts; recognized quarterly results | documented / documented / unknown / inferred | a crash that drives retail out | daily average revenue trades | unknown |
| 4 [ipo_window] `ms-c-vol-ecm` | Counter-path: equity volatility makes issuers postpone IPOs and follow-ons (issuers) | volatility above issuers' tolerance; observable: ECM volumes against volatility | onset weeks; build until volatility subsides; persists the backlog waits; recognized fees at pricing | documented / documented / unknown / inferred | the backlog prices once volatility falls | equity underwriting revenue | unknown |
| 5 [risk_off] `jpm-c-vol-equityindex` | A volatility shock usually comes with falling equity prices (investors) | a risk-off shock rather than an upside repricing; observable: equity index against volatility | onset days; build weeks; persists while risk-off lasts; recognized market prices | inferred / inferred / unknown / unknown | volatility from a melt-up | US equity market level | unknown |
| 6 [credit] `jpm-c-vol-spread` | A volatility shock (a forced deleveraging) widens credit spreads as investors demand more compensation for risk (credit investors) | the shock is broad rather than rates-only; observable: high-yield spread against volatility indices | onset days; build weeks; persists while risk-off lasts; recognized market prices | inferred / inferred / unknown / unknown | central-bank liquidity | US high-yield credit spread | unknown |
| 7 [costs] `ms-c-vol-clearing` | Brokerage, clearing and exchange fees are paid per trade, so higher volumes raise them (expense more negative) (exchanges and clearing houses) | volume-based fee schedules; observable: brokerage, clearing and exchange fees against volumes | onset same quarter; build none; persists while volumes last; recognized quarterly results | documented / inferred / unknown / inferred | fee schedule changes | brokerage, clearing and exchange fees | unknown |
| 8 `ms-c-darts-transactional` | Transactional revenue is trades times revenue per trade, plus order flow and margin income (WM self-directed) | pricing unchanged; observable: DARTs; revenue per trade | onset same quarter; build none; persists while activity lasts; recognized quarterly results | documented / documented / unknown / documented | zero-commission pricing | WM transactional revenue | unknown |
| 9 `ms-c-equity-feeassets` | Market moves revalue advisory accounts; the fee base is mostly equities with a fixed income and cash sleeve (management's stated mix), so it moves by a fraction of an equity-market move set by that share, besides flows (markets; WM clients) | the equity share of fee-based assets; observable: fee-based asset roll-forward: market impact versus flows | onset immediate; build none; persists while levels hold; recognized fees billed on prior month-end values | documented / documented / unknown / documented | outflows in a sell-off; clients de-risk into cash | WM fee-based assets | unknown |
| 10 `ms-c-feeassets-amfees` | Asset management fees are fee-based assets times the fee rate, billed off prior month-end values (Morgan Stanley (advisory programmes)) | pricing unchanged; observable: WM asset management revenues; average fee-based assets | onset one month (billing lag); build none; persists while assets hold; recognized monthly billing, quarterly results | documented / documented / model / documented | fee-rate compression; mix toward cash management at low fees | WM asset management fees | +1.20 sd/sd (identity) |
| 11 `ms-c-equity-prime` | Prime brokerage financing balances scale with the market value of hedge-fund portfolios and client leverage (hedge funds (prime clients)) | client gross leverage holds; observable: customer receivables; prime balances | onset same quarter; build none; persists while levels hold; recognized daily financing accruals | documented / broker / unknown / inferred | forced deleveraging | prime brokerage balances | unknown |
| 12 `ms-c-prime-financing` | Equity financing revenue is roughly balances times the financing spread (net of the funding cost booked as negative net interest) (ISG Equity financing desks) | spread unchanged; funding cost passed on; observable: Equity financing revenue; customer receivables | onset same quarter; build none; persists while balances hold; recognized daily accruals | documented / broker / model / inferred | spread compression; funding-cost spikes | Equity financing revenue | +1.00 sd/sd (identity) |
| 13 `ms-c-spread-ficc` | Spread widening marks down credit inventory and slows structured credit and securitized products activity (fixed income desks) | a disorderly widening, not a gradual one; observable: FICC revenue against credit spreads | onset days; build none; persists while spreads stay wide; recognized trading revenue daily | documented / documented / unknown / inferred | wider spreads also raise client hedging | Fixed Income revenue | unknown |
| 14 `ms-a-eq-equity-execution` | Morgan Stanley Equity execution services revenue is one part of Morgan Stanley Equity sales and trading revenue (Equity net revenues by business: financing and execution services); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Equity sales and trading revenue | +0.56 sd/sd (accounting) |
| 15 `ms-a-eq-equity-financing` | Morgan Stanley Equity financing revenue is one part of Morgan Stanley Equity sales and trading revenue (Equity net revenues by business: financing and execution services); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Equity sales and trading revenue | +0.44 sd/sd (accounting) |
| 16 `ms-a-trd-equity-revenue` | Morgan Stanley Equity sales and trading revenue is one part of Morgan Stanley trading revenue (ISG sales and trading net revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | trading revenue | +0.76 sd/sd (accounting) |
| 17 `ms-a-trd-ficc-revenue` | Morgan Stanley Fixed Income sales and trading revenue is one part of Morgan Stanley trading revenue (ISG sales and trading net revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | trading revenue | +0.40 sd/sd (accounting) |
| 18 `ms-a-isg-trading-revenue` | Morgan Stanley trading revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.80 sd/sd (accounting) |
| 19 `ms-a-ib-ecm-fees` | Morgan Stanley equity underwriting revenue is one part of Morgan Stanley investment banking revenue (ISG investment banking revenues by product); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | investment banking revenue | +0.61 sd/sd (accounting) |
| 20 `ms-a-isg-ib-fees` | Morgan Stanley investment banking revenue is one part of Morgan Stanley Institutional Securities net revenues (Institutional Securities net revenues by business); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | Institutional Securities net revenues | +0.21 sd/sd (accounting) |
| 21 `ms-a-wm-wm-transactional` | Morgan Stanley WM transactional revenue is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.30 sd/sd (accounting) |
| 22 `ms-a-wm-wm-asset-mgmt-fees` | Morgan Stanley WM asset management fees is one part of Morgan Stanley wealth management revenue (Wealth Management net revenues by line); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wealth management revenue | +0.60 sd/sd (accounting) |
| 23 `ms-a-seg-isg-revenue` | Morgan Stanley Institutional Securities net revenues is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.79 sd/sd (accounting) |
| 24 `ms-a-seg-wealth-revenue` | Morgan Stanley wealth management revenue is one part of Morgan Stanley net revenues (net revenues by reporting segment, US GAAP, with intersegment eliminations); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenues | +0.42 sd/sd (accounting) |
| 25 `ms-c-revenue-comp` | Compensation is the compensation ratio times net revenues (held negative): more revenue, a larger charge at the same ratio (incentive accruals, the advisor payout, carried interest) (Morgan Stanley) | near the construction levels (the weight is linearized there); observable: the identity's terms each period | onset same period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | none (identity) | compensation and benefits | -1.04 sd/sd (identity) |
| 26 `ms-a-exp-compensation-expense` | Morgan Stanley compensation and benefits is one part of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.70 sd/sd (accounting) |
| 27 `ms-a-exp-brokerage-clearing-expense` | Morgan Stanley brokerage, clearing and exchange fees is one part of Morgan Stanley non-interest expenses (non-interest expenses by type (negative values)); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | non-interest expenses | +0.15 sd/sd (accounting) |
| 28 `ms-a-pretax-net-revenue` | Morgan Stanley net revenues is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +1.61 sd/sd (accounting) |
| 29 `ms-a-pretax-noninterest-expense` | Morgan Stanley non-interest expenses is one part of Morgan Stanley income before taxes (pretax income: net revenues less non-interest expenses less provision); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | income before taxes | +0.91 sd/sd (accounting) |
| 30 [earnings] `ms-a-ni-pretax-income` | Morgan Stanley income before taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.30 sd/sd (accounting) |
| 31 [tax] `ms-c-pretax-tax` | Income tax is pretax income times the effective rate (with discrete items); higher pretax income raises the charge (tax authorities) | rate unchanged; observable: effective tax rate | onset same quarter; build none; persists permanent; recognized quarterly results | documented / documented / model / documented | discrete tax items (stock-based compensation vesting) | provision for income taxes | -0.98 sd/sd (identity) |
| 32 `ms-a-ni-income-tax` | Morgan Stanley provision for income taxes is one part of Morgan Stanley net income (net income applicable to Morgan Stanley: pretax income less income tax less noncontrolling interests); weight is its scale over the total's | US GAAP as reported, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +0.30 sd/sd (accounting) |

Unresolved inputs: ECM sensitivity to volatility (not disclosed in reviewed sources); Equity financing revenue split (trading, fees, net interest) (found connected); FICC sensitivity to credit spreads (not disclosed in reviewed sources); FICC sensitivity to volatility (not disclosed in reviewed sources); advisor payout grid (not disclosed in reviewed sources); compensation ratio (found connected); cost per trade (not disclosed in reviewed sources); daily average revenue trades (found connected); effective tax rate (found connected); equity share of fee-based assets (found connected); fee-based asset averages and fee rate (found connected); fee-based asset roll-forward (market impact) (found connected); prime balance proxy (customer receivables) (found connected); prime balance sensitivity to equity levels (not disclosed in reviewed sources); revenue per trade (not disclosed in reviewed sources); trade sensitivity to volatility (not disclosed in reviewed sources); trading revenue sensitivity to volatility (not disclosed in reviewed sources).

## Validation

`tests/scenario/test_construction_morgan_stanley.py` (loads sally_demo once; reads no client data; 21 tests):

- Structure: no `validate_construction` problems for the company; the fifteen compositions and thirteen paths exist;
  every path step has a transition, every uncalibrated step a sign and an "unknown" magnitude; the parallel responses
  of one move are branches from it (the policy rate: beta, cash sorting, savings, loans; the equity level: fee base,
  client assets, AUM, carry, prime, activity, deferred pay, IPO window; volatility; the 10Y; deal activity); the
  reduced forms (s75, s13, s15, s17, `ms-c-equity-amfees`) are never steps of their structural paths.
- Financial integrity: every part of an additive view has a fixed-weight accounting link equal to its native sd over
  the total's; one unit per view; the views that leave something out keep a residual or eliminations; the priors of
  every additive view reconcile within 0.5% (exactly); the segment view is driven, eliminates intersegment revenue,
  and shares no part with the line view, which only size-free bridges reach; AFS marks reach CET1 and never income;
  capital is a stock with signed flows, not an additive view, and the leverage ratio can bind buybacks.
- Economics: WM NII steps are identities held without a size and the reduced form s75 carries the disclosed
  sensitivity; asset-based fees follow markets with a month's lag (calibrated from management's stated mix, less than
  one for one); deferred pay offsets its hedge, and pay follows each segment's revenue; advisory waits for completion;
  every conversion tag (identity, stock-flow, matrix, state) is used.
- Calibration: the only new size on an `ms-c-` link is `ms-c-equity-amfees` (broker-supported mix); s75 is resized
  from the disclosure (documented); s13, s15 and s17 keep their sizes with magnitude "assumption" and named inputs;
  every missing input says whether the supplied material was searched (no `not_yet_reviewed`).
- Conversion: the driving and reconciling views, the eleven identities and four stock-flows exist and reconcile
  (`reconcile_identities`, `reconcile_stock_flows`), and no `identity:`, `stock-flow:` or `matrix:` tag is left unconverted.
- Generalization: a yen carry unwind, for which no Morgan Stanley path was written, traced through every link (below).
- Delivery: compositions in `financial_bridge`, named paths as `business_construction` transmission paths, the segment
  view's links as `accounting_identity`, uncalibrated links as `represented_uncalibrated` with their sign, s75's
  transition in the export; new node ids returned by `/v1/world-models/sally_demo/graph`, the construction and trace endpoints.

Sally's expected paths (`tests/scenario/test_sally_expected_paths.py`) still pass with s75 resized: `trading_revenue`,
`ib_fees` and `wealth_revenue` keep their ids and priors, s13, s15 and s17 their sizes, and s75 its sign. The Toyota,
Tokio Marine and JPMorgan tests pass unchanged.

**Generalization trace (yen carry unwind).** `trace(g, "dollar_yen.carry_positioning", "morgan_stanley")`: 39 routes,
38 reach a financial endpoint. Calibrated end to end: carry → volatility (s10) → sales and trading (s15) and → WM revenue
(s17). Calibrated after one uncalibrated step: volatility → lower equity prices (`jpm-c-vol-equityindex`, sign only) →
WM asset management fees (`ms-c-equity-amfees`). Represented with sign but no size: equity execution, FICC and retail
trading rise; the IPO window shuts; clearing costs rise; the fee base, IM AUM and fund marks fall, carry reverses,
prime balances and deferred pay fall; wider spreads (`jpm-c-vol-spread`) raise CECL provisions, mark down FICC
inventory and ISG loans, and slow issuance and deals (and, through IPO liquidity, workplace net new assets); a stronger
yen (m18) raises the dollar value of the joint venture's income in ISG other; lower prime balances free RWA and leverage
exposure, so the CET1 ratio and the SLR rise and buybacks can too. Where it stops: at the first composition total each
route reaches (the trace does not continue through totals), and once at the trace depth of eight links (the
net-new-asset funnel into the firm asset management line). The trace reaches every segment, expenses, provision,
capital and payout.

## Completion report

Outcomes map to the release outcomes: built and verified (**BV**), built but uncalibrated (**BU**), blocked by a named
input (**BL**), not built (**NB**).

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | Segment view with eliminations (driven), ISG, trading, Equity, IB, WM and IM views, the P&L bridge; 44 accounting links with sd-ratio weights | — |
| G02 | BV | Basis and export metric on every Morgan Stanley value | — |
| G03 | BV | s75 scoped as the reduced form and resized from the disclosed WM NII sensitivity (documented) | the asymmetry (a down shock is larger) is a note; the beta inside it is not disclosed |
| G04 | BU | `ms.comp.wm_deposits`, rate and balance states, `ms.path.rates_wm_nii` with four parallel branches | beta by product, sweep and savings sensitivities, floating share of loans |
| G05 | BV (reduced form) / BU (structure) | `ms-c-equity-amfees` calibrated from management's mix (broker), one-month kernel; `ms.path.market_levels`; s17 scoped | flows and fee-rate drift as drivers |
| G06 | BU | NNA, fee-based flows and client assets as signed stock-flow links; `ms.path.net_new_assets` | NNA sensitivity to IPOs, conversion rate, cash share |
| G07 | BU | IM view, AUM and fee-rate identity, flows, performance fees on markets and the 10Y | performance-fee sensitivities |
| G08 | BU (structure) / scoped (s13) | `ms.comp.ib`, completed-M&A state with its lag, `ms.path.deals_ib`; s13 scoped | fee elasticities to volumes |
| G09 | BU | `ms.comp.trading`, `ms.comp.equity`, prime balances, `ms.path.volatility` with counter-paths; s15 scoped | volatility and spread sensitivities |
| G10 | BU | `ms.comp.expense`, revenue-linked pay from each segment, the deferred-plan offset, clearing costs, `ms.path.expense_inflation` | the payout grid; comp ratios found but not linkable as a ratio |
| G11 | BU | provision, `ms.path.credit_spreads`, `ms.path.recession`, ISG loan marks | CECL sensitivities |
| G12 | BU | capital values, non-additive capital view, four capital paths, the SLR channel | leverage exposure, AFS duration, management target |
| G13 | BV (structure; undriven) | `ms.comp.revenue_by_line`, `ms.comp.nii`, size-free bridges | line drivers: the drivers act on segments |
| G14 | BV (structure; undriven) | `ms.comp.pretax_by_segment` with eliminations, size-free bridges | the segment expense split |
| G15 | BU | `ms-c-usdjpy-isgother` | — (a translation identity) |
| G16 | BV | objects present in the v4.1.4 export | — |
| G17 | BV | node ids served by the query, construction and trace endpoints | — |
| G18 | BL (worked around) | two baseline bundles, each importing whole | a matrix reconciliation (one results release, both views) |

Counts: 18 gaps. By category (a gap can carry two): MC 13, CAL 4, MAP 2, EXP 1, RET 2. By outcome: BV 7 (G01, G02, G03,
G13, G14, G16, G17), BV in part 1 (G05), BU 9 (G04, G06–G12, G15), BL 1 (G18), NB 0.

**Links.** 130 links touch Morgan Stanley's values: 44 accounting (fixed weights), 8 calibrated causal (s13, s15, s17,
s23, s24, s75, the trading-revenue kind default to the share price, and the new `ms-c-equity-amfees`), 78 uncalibrated
(mechanism and sign). 127 carry a transition (not s23, s24 and the kind default).

**Reconciliation.** At the priors (medians), every one of the fourteen additive views adds up exactly (0.0%): the
synthetic levels were set to reconcile, and each residual says what it holds. At the FY2025 baselines (workbook and
vendor-model actuals, local `reconciliation.md`), all fourteen add up exactly with no unexplained difference; every part
and total of each view is observed. Three parts are derived, not read: other non-compensation expense (non-compensation
less brokerage and technology), the investments-and-other revenue lines, and common dividends (dividends paid less
preferred). Units are one per view (tested). `check.py sally_demo --entities morgan_stanley --reconcile --statistic
median` reports 0 flags; the baselines are two bundles (see G18), reconciled together by `bundle_levels` of both.

**Sources and citations.** `check.py --sources <local construction folder>`: 10 source ids resolve, 0 do not; 127 links
and 67 values are cited (sheet and cell, or page and line, with the passage); 0 material claims without a citation.

**Inputs by status** (distinct input and status pairs named in transitions, after `scripts/construction/inputs.py`
searched the 10 supplied Morgan Stanley files for each): 29 found and connected (bound as a baseline or a citation), 0
found but not connected, 42 not disclosed in the reviewed sources (each with the sources and corpus queries searched;
the keyword candidates were read and were the workbook's own "not disclosed" rows, qualitative passages or other
measures), 0 not yet reviewed.

**Forecast coverage (Sally's theses).** The Fed-cut thesis (S-T2) reaches Morgan Stanley through 13 quantified links
(s13, s15, s17, s75, the share-price links, and the segment and P&L accounting links) and excludes 27 uncalibrated ones
(the deposit, sweep, loan-yield, deal, volatility, long-end, compensation and capital steps, each with its sign); a
quarter of its routes to sales and trading are fully quantified; 29 inputs block a size (18 not disclosed, 11 found and
connected). The volatility theses (S-T1, S-T3) quantify s15 and s17 and exclude the uncalibrated volatility branches
(execution, FICC, retail trading, the IPO window, clearing costs) and the pay offsets; a fifth of S-T3's routes to sales
and trading are fully quantified.

**Calculation coverage by path.** "Calculated" contributes a size; accounting links carry it to the endpoint at fixed
weights; uncalibrated steps carry a sign only and are listed as unquantified by any forecast that reaches them. No
structural path has a calibrated causal step: the calculated sizes sit on the reduced forms beside them (s75 beside the
rates path, `ms-c-equity-amfees` beside the market-levels path, s13 beside deals, s15 and s17 beside volatility).

| Path | Calculated (calibrated causal) | Accounting | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|
| (first round, superseded) | see [the conversion](#conversion-to-the-new-method-forms-oct-18) | | | |

**What a downstream agent can now trace or calculate.** Net revenues as the sum of the three segments less
intersegment eliminations, each segment by its businesses (Equity financing and execution, FICC, advisory and
underwriting, ISG other; WM asset fees, transactional, NII, other; IM management and performance fees), and on to
pretax and net income through expenses (compensation the variable part) and provision; the same totals by
income-statement line and by segment pretax (reconciled, not driven); WM deposits by sweep and savings; a calculated size
for a policy-rate move on WM revenue (s75, from the disclosed WM NII sensitivity), for an equity-market move on WM asset
fees (from management's mix, a month later), for deal activity on IB fees and for volatility on sales and trading and on
WM revenue (statistical records, scoped); and, as signed mechanisms with conditions, timing, evidence and breakers:
deposit betas and cash sorting, floating loan repricing, the net-new-asset funnel, AUM and fund marks, prime balances
and their balance-sheet cost, the advisory completion lag, the IPO window, credit provisions and loan marks, the
joint venture's yen income, deferred pay and its hedge, the advisor payout, AOCI marks, the stress capital buffer, the
SLR and buybacks.

**What remains unsupported.** Any size along the structural WM NII, fee, funnel, IB, trading, credit and capital paths
(each step is a product of a balance and a rate, a ratio, an accumulation or an undisclosed elasticity; see below);
deposit betas by product; activity elasticities; leverage exposure and AFS duration; the asymmetry of the rate
sensitivity; importing a results release's segment and line views in one bundle (G18).

## Conversion to the new method forms (Oct 18)

The method gained identities that are not sums, stocks fed by flows, one driving view per total, state-dependent
responses and scenario calibration (see [the README](README.md)). Morgan Stanley's construction was converted on branch
`morgan_stanley-conversion`.

**One driving view per total.**

| Total | Driving view (paths and reduced forms feed it) | Reconciling view (`drives: false`) | Why not a matrix |
|---|---|---|---|
| `morgan_stanley.net_revenue` | `ms.comp.revenue_by_segment` (ISG + WM + IM + eliminations) | `ms.comp.revenue_by_line` (firm NII, trading, IB, commissions, asset management lines) | the supplied segment tables give the lines by segment only in part; a matrix needs every cell as a value |
| `morgan_stanley.pretax_income` | `ms.comp.pretax` (net revenues + expenses + provision) | `ms.comp.pretax_by_segment` | the segment expense split is not modelled, so there are no cells |

The reconciling views' accounting links are kept as size-free (uncalibrated) links with a sign, so the views still
read and reconcile (`--reconcile`), and a results day that reports every view now imports whole: the baselines are back
in one bundle (73 items), which `bundles.py check` passes.

**Converted steps, by form.**

| Form | Declared | Links | What it replaced |
|---|---|---|---|
| product identity | `ms.id.wm_loan_interest` (loans x rate), `ms.id.wm_deposit_interest` (deposits x cost), `ms.id.wm_am_fees` (fee-based assets x fee rate), `ms.id.im_fees` (AUM x fee rate), `ms.id.advisory` (completed volume x fee rate), `ms.id.financing` (prime balances x revenue yield), `ms.id.compensation` (−0.01 x compensation ratio x net revenues), `ms.id.tax` (−0.01 x effective rate x pretax) | 16 | the sign-only steps tagged `identity: product`; the three segment-revenue-to-pay links (now one exact link from net revenues at the ratio) |
| ratio identity | `ms.id.cet1_ratio` (100 x CET1 / RWA), `ms.id.slr` (100 x tier 1 / leverage exposure) | 4 | the sign-only ratio links; tier 1 is a new exact view (`ms.comp.tier1`: CET1 + preferred) |
| difference identity | `ms.id.wm_nii` (WM interest income − deposit interest) | 2 | the four sign-only balance-and-rate links into WM NII; loan interest plus securities interest add to WM interest income (`ms.comp.wm_interest_income`) |
| stock-flow | `ms.sf.client_assets` (+ net new assets), `ms.sf.fee_based_assets` (+ fee-based flows), `ms.sf.im_aum` (+ net flows), `ms.sf.cet1` (+ net income − dividends − buybacks), each over 365 days | 6 | the sign-only accumulation links tagged `stock-flow:` |
| state (asymmetry) | s75 sized separately for rises and falls by least squares over the company's four disclosed parallel scenarios (`calibrate.py --disclosure`, local file) | 1 | s75's single size; a cut now costs more than a hike earns |

New values the identities need (synthetic round priors, set so every identity reconciles): WM loan interest, WM
securities and cash interest (residual), WM interest income, WM deposit interest, the compensation ratio, the effective
tax rate, the advisory fee rate, the financing revenue rate, preferred equity and tier 1 capital. Two priors moved to
make the identities hold (the WM and IM fee rates now on period-end assets; CET1 capital and the SLR by less than 1%).
Two values were renamed for the extraction gazetteer (`noncontrolling_interests`; the IM performance value's name), and
the loan rate is `wm_loan_rate`.

**Still sign-only, and why** (each says so in its `note`): the deposit beta and its asymmetry (`ms-c-fed-depcost`: no
size for either side; the disclosure sizes s75), the sweep mix (`ms-c-sweep-depcost`: a weighted average whose weights
are values), fund-mark reversals, the IPO-window threshold, the annual dividend reset, the three buyback constraints
(thresholds and a minimum of two headrooms, no size), transactional revenue from trades (not trades x price alone), the
joint venture's yen income (not a value of its own), AOCI into CET1 (a stock change inside a stock), the bridges into
the reconciling views, and the response of the compensation ratio to revenue.

**Links before → after** (links touching Morgan Stanley's values):

| | Before | After |
|---|---|---|
| total | 130 | 139 |
| calibrated causal | 8 | 8 (s75 now asymmetric) |
| identity | 0 | 22 |
| stock-flow | 0 | 6 |
| accounting, quantified | 44 | 38 |
| accounting, size-free (reconciling views) | 0 | 10 |
| uncalibrated causal | 78 | 55 |

**Reconciliation now.** At the priors (medians): all sixteen additive views and all eleven identities reconcile (the
largest identity gap is 0.12%, the tax identity). At the FY2025 baselines (one bundle): fifteen views reconcile exactly;
`ms.comp.wm_interest_income` is blocked (its parts are not observed); seven identities reconcile exactly (compensation,
tax, advisory, financing, IM and WM fees, CET1 ratio); four are blocked by an unobserved level (leverage exposure for the
SLR; the WM interest decomposition, because the segment's reported interest lines are on a transfer-pricing basis, not
balances times the disclosed cost of deposits, so they are not bound). The stock-flow roll-forwards are declared and
tested on synthetic dated levels; the baselines hold one date per stock, so no roll-forward is checked on actuals (market
impact is not a flow the model holds; see below).

**Coverage per path now** ("exact" = calibrated causal, identity, stock-flow and quantified accounting steps over all
steps; identity and stock-flow steps carry derived weights):

| Path | Exact / steps | Calibrated causal | Identity and stock-flow | Accounting | Sign-only, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|---|---|
| `ms.path.balance_sheet` | 13/17 | none | `ms-c-prime-financing`, `ms-c-ni-cet1`, `ms-c-rwa-ratio`, `ms-c-cet1cap-ratio`, `ms-c-leverage-slr`, `ms-c-tier1-slr` | 7 | `ms-c-prime-rwa` (+), `ms-c-prime-leverage` (+), `ms-c-ratio-buybacks` (+), `ms-c-slr-buybacks` (+) | SLR as the binding constraint, capital cushion over the requirement and the authorization (found, connected); RWA sensitivity to financing balances, exposure sensitivity to financing balances, management CET1 target (not disclosed) |
| `ms.path.capital_payout` | 6/9 | none | `ms-c-ni-cet1`, `ms-c-dividends-cet1`, `ms-c-cet1cap-ratio`, `ms-c-tier1-slr`, `ms-c-buyback-cet1` | 1 | `ms-c-ni-dividends` (+), `ms-c-ratio-buybacks` (+), `ms-c-slr-buybacks` (+) | SLR as the binding constraint, capital cushion over the requirement and the authorization, dividend history and the latest increase (found, connected); management CET1 target (not disclosed) |
| `ms.path.capital_requirements` | 4/5 | none | `ms-c-buyback-cet1`, `ms-c-cet1cap-ratio`, `ms-c-tier1-slr` | 1 | `ms-c-req-buybacks` (-) | CET1 requirement (found, connected) |
| `ms.path.credit_spreads` | 13/19 | none | `ms-c-completedma-advisory`, `ms-c-pretax-tax` | 11 | `ms-c-spread-provision` (-), `ms-c-spread-ficc` (-), `ms-c-spread-isgother` (-), `ms-c-spread-dcm` (-), `jpm-c-spread-deals` (-), `ms-c-deals-completedma` (+) | completed M&A volume, provision and allowance history (found, connected); CECL scenario sensitivity, DCM sensitivity to spreads, FICC sensitivity to credit spreads, advisory backlog, fair-value loan exposure and hedge ratio (not disclosed) |
| `ms.path.deals_ib` | 13/16 | none | `ms-c-completedma-advisory`, `ms-c-revenue-comp`, `ms-c-pretax-tax` | 10 | `ms-c-deals-completedma` (+), `ms-c-deals-ecm` (+), `ms-c-deals-dcm` (+) | completed M&A volume (found, connected); DCM fee elasticity to issuance volume, ECM fee elasticity to issuance volume, advisory backlog (not disclosed) |
| `ms.path.expense_inflation` | 6/8 | none | `ms-c-pretax-tax` | 5 | `ms-c-cpi-comp` (-), `ms-c-cpi-othernoncomp` (-) | none named |
| `ms.path.investment_management` | 11/12 | none | `ms-c-imflows-aum`, `ms-c-aum-imfees`, `ms-c-revenue-comp`, `ms-c-pretax-tax` | 7 | `ms-c-bridge-im-pretax` (+) | none named |
| `ms.path.long_end` | 12/17 | none | `ms-c-feeassets-amfees`, `ms-c-ni-cet1`, `ms-c-cet1cap-ratio` | 9 | `ms-c-ust10-aoci` (-), `ms-c-ust10-feeassets` (-), `ms-c-ust10-perf` (-), `ms-c-ust10-dcm` (-), `ms-c-aoci-cet1` (+) | AFS book and unrealized losses (found, connected); AFS duration and the AOCI sensitivity, DCM sensitivity to long yields, fee sensitivity to long yields, performance-fee sensitivity to rates (not disclosed) |
| `ms.path.market_levels` | 26/35 | none | `ms-c-feeassets-amfees`, `ms-c-loans-loaninterest`, `ms-c-wmii-wmnii`, `ms-c-aum-imfees`, `ms-c-prime-financing`, `ms-c-revenue-comp`, `ms-c-pretax-tax` | 19 | `ms-c-equity-feeassets` (+), `ms-c-equity-clientassets` (+), `ms-c-equity-aum` (+), `ms-c-equity-perf` (+), `ms-c-equity-prime` (+), `ms-c-equity-transactional` (+), `ms-c-equity-dcpcomp` (-), `ms-c-equity-ecm` (+), `ms-c-clientassets-loans` (+) | AUM by asset class and market impact, deferred-compensation plan marks, deferred-compensation plan marks in transactional, equity share of fee-based assets, fee-based asset roll-forward (market impact), prime balance proxy (customer receivables) (found, connected); ECM fee sensitivity to equity levels, equity weight of total client assets, lending penetration of client assets, performance-fee sensitivity to markets, prime balance sensitivity to equity levels, transactional sensitivity to equity levels (not disclosed) |
| `ms.path.net_new_assets` | 20/25 | none | `ms-c-nna-clientassets`, `ms-c-feeflows-feeassets`, `ms-c-feeassets-amfees`, `ms-c-loans-loaninterest`, `ms-c-wmii-wmnii`, `ms-c-depcost-depinterest`, `ms-c-depinterest-wmnii`, `ms-c-deposits-depinterest`, `ms-c-revenue-comp`, `ms-c-pretax-tax` | 10 | `ms-c-deals-nna` (+), `ms-c-nna-feeflows` (+), `ms-c-nna-sweep` (+), `ms-c-clientassets-loans` (+), `ms-c-sweep-depcost` (-) | IPO-related share of net new assets, sweep and total deposit balances (found, connected); cash share of net new assets, conversion rate of new assets to fee-based, lending penetration of client assets, net new asset sensitivity to IPO activity (not disclosed) |
| `ms.path.rates_wm_nii` | 17/22 | none | `ms-c-deposits-depinterest`, `ms-c-depinterest-wmnii`, `ms-c-depcost-depinterest`, `ms-c-loanrate-loaninterest`, `ms-c-wmii-wmnii`, `ms-c-revenue-comp`, `ms-c-pretax-tax` | 10 | `ms-c-fed-depcost` (+), `ms-c-fed-sweep` (-), `ms-c-fed-savings` (+), `ms-c-fed-loanyield` (+), `ms-c-sweep-depcost` (-) | cost of deposits history, loan yield history, sweep and total deposit balances (found, connected); deposit beta by product (sweep versus savings), floating share of WM loans, savings balance sensitivity to the policy rate, sweep balance sensitivity to the policy rate (not disclosed) |
| `ms.path.recession` | 4/6 | none | `ms-c-pretax-tax` | 3 | `jpm-c-gdp-unemp` (-), `ms-c-unemp-provision` (-) | provision sensitivity to unemployment (not disclosed) |
| `ms.path.volatility` | 21/32 | none | `ms-c-feeassets-amfees`, `ms-c-prime-financing`, `ms-c-revenue-comp`, `ms-c-pretax-tax` | 17 | `ms-c-vol-execution` (+), `ms-c-vol-ficc` (+), `ms-c-vol-darts` (+), `ms-c-vol-ecm` (-), `jpm-c-vol-equityindex` (-), `jpm-c-vol-spread` (+), `ms-c-vol-clearing` (-), `ms-c-darts-transactional` (+), `ms-c-equity-feeassets` (+), `ms-c-equity-prime` (+), `ms-c-spread-ficc` (-) | daily average revenue trades, equity share of fee-based assets, fee-based asset roll-forward (market impact), prime balance proxy (customer receivables) (found, connected); ECM sensitivity to volatility, FICC sensitivity to credit spreads, FICC sensitivity to volatility, cost per trade, prime balance sensitivity to equity levels, revenue per trade, trade sensitivity to volatility, trading revenue sensitivity to volatility (not disclosed) |
| Generalization (yen carry) | 2/31 routes fully quantified | s10 (shared), then s15, s17 | the ratio, tax and capital identities downstream of each total | the segment and P&L views | every first step from volatility, prices, spreads and the yen | as for the paths above |

What changed for a forecast: a balance or rate move now reaches WM NII exactly through the products and the difference;
a flow (net new assets into fee-based assets, IM net flows) reaches fees exactly; any revenue move reaches compensation,
pretax income, tax and net income exactly through the ratio identities, and net income accumulates into CET1 and the
CET1 ratio and SLR. What still carries no size is the first step from a market or macro driver into the operating states
(betas, elasticities, market impact), apart from the reduced forms beside the paths (s75, `ms-c-equity-amfees`, s13,
s15, s17).

**What still cannot be expressed.**
1. **Market impact as a flow from a level.** A fee base moves with the market level (a level effect) and with flows (an
   accumulation). The stock-flow takes flows; turning a market level into a period's market impact (a change, the
   derivative of the level) has no form, so the roll-forward on actuals cannot close and the market step stays a sign.
2. **Weighted averages with moving weights.** The cost of deposits is a balance-weighted mix of sweep and savings rates;
   with value weights it is a sum of products, held only as a sign.
3. **A ratio that responds.** The compensation ratio is now exact as a factor, but its response to revenue (sticky pay,
   higher when revenue falls) has no size and no state form tied to a level of revenue.
4. **Minimum of two constraints, dated resets.** Buybacks are bound by the tighter of CET1 and SLR headroom, and the
   requirement and dividend reset once a year; thresholds exist, a minimum and a calendar reset do not.
5. **Segment interest on a transfer-pricing basis.** The economic identity (deposits x cost) and the reported segment
   interest lines differ by internal funds-transfer pricing, which has no object, so the WM NII identities cannot be
   checked against reported segment interest.
6. **Segments x lines.** A matrix would make the line view driven from cells; the cells are not supplied, so the line
   view only reconciles.

## What the method could not express for an investment bank and wealth manager

This is the feedback the build was for. The method carried over again (gap register, compositions with eliminations,
transitions, branches, counter-paths, reduced forms beside structural paths, evidence, calibration from disclosure,
generalization trace), and Morgan Stanley's segments, unlike JPMorgan's, follow its drivers, so the matrix problem is
smaller here. What it could not express:

1. **Fees on a stock, billed with a lag.** WM and IM fees are a stock (fee-based assets, AUM) times a rate, and the
   stock is last period's plus flows plus market impact. The method has neither a product nor an accumulation link,
   so the one calibrated market step had to be a reduced form (equity level → fees) beside the structure; flows (net new
   assets, IM flows) reach fees only as signs. Needed: an accumulation link (flow into stock) and a product identity,
   so a flow shock and a market shock compose into fees through the same stock.
2. **A disclosed sensitivity on a different basis from the link.** The company discloses a 12-month WM NII sensitivity
   to an instantaneous parallel shift (a static balance sheet with modelled deposit pricing). `calibrate.py` puts it on
   one link from the policy rate to WM revenue; the long end's share of the parallel shift, the 12-month horizon versus
   the link's kernel, and the asymmetry (a cut costs more than a hike earns, because deposit rates floor) cannot be
   represented. Needed: scenario-disclosure calibration and state-dependent (asymmetric) effects.
3. **Pay as a ratio of revenue.** Compensation is an accrual ratio of each segment's revenue (the advisor payout grid,
   ISG incentives, carried interest), and the ratio itself moves (it rises when revenue falls). It is held as signed
   links from each segment to compensation; the comp ratio and operating leverage cannot be calculated. Needed: a ratio
   identity with a state-dependent ratio.
4. **Offsetting legs of one hedge.** Deferred cash-based plans raise compensation and their hedges raise transactional
   revenue on the same market move, roughly pretax-neutral. Both are represented with opposite signs, but nothing ties
   their sizes together, so a forecast cannot show the net as near zero. Needed: a linked pair (one size, two legs).
5. **Two binding constraints.** Buybacks are limited by whichever binds: the CET1 ratio over its requirement (with a
   stress capital buffer that resets once a year) or the leverage ratio (which the research reads as binding). Both
   enter buybacks as linear signed links; a minimum of two headrooms, and a requirement that steps annually, are not
   expressible. Needed: threshold and min-of-constraints forms.
6. **Cross-classified results again.** Net revenues by segment and by line, and pretax by segment and firm-wide, are
   reported together. A value can sit in one additive view, so the line view and segment pretax are reconciled but
   undriven, bridged by size-free links; the import guard folds one view per total and day, so the baselines had to be
   split into two bundles. Firm NII (what brokers forecast) cannot be driven from WM NII. Needed: a matrix composition.
7. **Advisory at completion.** Advisory fees are booked when announced deals complete, two to four quarters later; the
   lag sits on an uncalibrated link, so timing carries no weight in a forecast. Needed: timing that propagates on a
   signed link, or a delay distribution calibratable from a pipeline.
8. **Shared links without transitions cannot be path steps.** s09 (growth → deals) and s74 (10Y → deals) are shared
   statistical records with no transition; adding one would touch shared objects, so the recession and long-end paths
   stop short of deals and point to the deals path instead. The trace still follows them.
9. **Smaller frictions.** The `note` that carries the conversion tags is not kept on the loaded interaction, so tests
   read it from the file; the view vocabulary has no "funding" or "client assets" view (`liabilities` and
   `operating_state` were used); prime balances exist only as a proxy (customer receivables); the trace stops at the
   first composition total and at eight links.
