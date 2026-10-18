# JPMorgan Chase: business construction

<!-- toc -->
**Contents**

- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Identities](#identities)
  - [Stocks and flows](#stocks-and-flows)
  - [Matrix `jpm.mx.revenue`: jpm.comp.revenue_by_line x jpm.comp.revenue_by_segment (the rows drive the total; jpm.comp.revenue_by_segment reconciles)](#matrix-jpmmxrevenue-jpmcomprevenuebyline-x-jpmcomprevenuebysegment-the-rows-drive-the-total-jpmcomprevenuebysegment-reconciles)
  - [Operating and financial paths](#operating-and-financial-paths)
- [Validation](#validation)
- [Completion report](#completion-report)
  - [Conversion: counts before and after](#conversion-counts-before-and-after)
- [What the method could not express for a bank](#what-the-method-could-not-express-for-a-bank)
<!-- /toc -->

The third build of the method, after an automaker ([Toyota](toyota.md)) and an insurer ([Tokio Marine](tokio_marine.md)):
a bank, whose economics are a balance sheet (NII from balances times rates, deposit betas, securities repricing),
fees and trading, credit costs, and capital and payout. The construction lives in
`data/worlds/sally_demo/construction/jpmorgan.yaml` (values, links with their transitions, named paths, compositions)
plus light edits to the `jpmorgan` block of entities.yaml (features on four values) and to m25, s12, s14, s18 in
interactions.yaml (transitions; s12, s14, s18 keep their sizes; m25 was resized at the conversion). This page is structure only: object ids, bases, categories, tests. The
client-derived side (workbook cells, broker passages, guidance, dated baselines) stays local under
`data/sally_data/construction/jpmorgan/` (`gap_evidence.md`, `sources.json`, `citations.json`, `baselines.json`,
`estimates.json`, `reconciliation.md`, `coverage.md`, and the readable view with levels in `view/`).

Source ids used in transitions (each resolves locally in `sources.json` to a file, and in `citations.json` to the cell
or the page and paragraph with the passage): `jpm.wb` sell-side company model workbook (history to Q2-2026, the analyst's
forecast, a guidance tab); `jpm.co` company disclosures as cited in the broker notes (earnings-at-risk scenarios,
outlook, capital requirement; not read directly); `jpm.r1`–`jpm.r11` broker notes (company previews, sector previews
with deposit-beta, rate-sensitivity, capital and AOCI tables); `jpm.x1` expert call on card losses and payments (no
names recorded; `jpm.x2`, an expert call on IP management, was read and not used); `jpm.macro` rates strategy and Fed
notes; `jpm.peer` peer bank dashboard; `jpm.pub` public business and accounting knowledge (CECL, AOCI in CET1 for the
largest banks, interchange net of rewards). The supplied `spreadsheets/` folder holds no JPMorgan workbook; the company
workbook is the one in the sell-side JPMorgan folder.

## Gap register

Written before the model was changed; the test names are the ones after the conversion (Oct 18). "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack (036, state 432). JPMorgan was not one of the reviewer's worked companies, so the export side is "not represented
in the inspected export" throughout. Categories: **MC** missing construction, **CAL** missing calibration, **MAP**
incorrect mapping, **EXP** export omission, **RET** retrieval omission. Outcomes are in the
[completion report](#completion-report).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | No business composition: the pack jumps from the Fed to NII, from deals to IB fees, from volatility to Markets revenue, from the 10Y to CET1 | Internal: four values (`net_interest_income`, `ib_fees`, `markets_revenue`, `cet1_ratio`), links m25, s12, s14, s18, s20–s22 and the NII kind default to the share price; no compositions. Export: the same broad relations | A driven line view of managed revenue (`jpm.comp.revenue_by_line`), the P&L bridge to pretax and net income (`jpm.comp.pretax`, `jpm.comp.net_income`), expense and credit-cost views, NII by balance-sheet line | Workbook income statement, managed adjustments, supplement (`jpm.wb`) | Any group revenue or earnings conclusion; "rates up is good" | `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links`, `test_priors_reconcile_within_half_a_percent` | MC |
| G02 | Undefined bases: NII (reported, managed, ex-Markets?), Markets revenue (a CIB product incl. Markets NII, not the principal-transactions line), IB fees (firmwide line vs CIB) | Internal: values without features. Export: metrics named by id suffix | `features.view/basis/metric` on the four values and every new one | Workbook definitions (`jpm.wb`) | Adding Markets revenue to firmwide NII double counts Markets NII | `test_values_name_their_basis` | MAP |
| G03 | m25 (Fed → NII) has no scope; its size is not tied to the disclosed sensitivity | Internal: calibrated, no transition | Keep id and size (Sally's expected paths); add a transition naming it the reduced form of `jpm.path.rates_nii`, magnitude "assumption", and the cross-check against the disclosed scenarios | Short-end-only earnings sensitivity on the firmwide basis | Size of any Fed-driven NII change | `test_only_evidenced_links_carry_new_sizes`, `test_the_reduced_form_carries_only_what_the_identities_do_not` | MAP / CAL |
| G04 | NII drivers absent: deposit and loan balances and rates, deposit beta and its lag, noninterest-bearing mix, floating-rate loans, cash at the Fed | Internal: none | Operating states and `jpm.path.rates_nii` (parallel branches of one rate move) into the NII balance-sheet view | Deposit beta (by segment), floating-rate share, mix elasticity | Whether and when a hike raises NII; deposit-beta catch-up | `test_shared_driver_responses_are_parallel_branches` | MC |
| G05 | Deposit-beta size | Internal: none | Calibrate Fed → interest-bearing deposit cost from the broker's JPMorgan beta, with a quarters-long kernel | Broker beta table (`jpm.r6`), industry betas (`jpm.r2`, `jpm.r4`) | NII path timing and size | `test_deposit_beta_is_calibrated_from_the_research_asymmetric_and_lags` | CAL |
| G06 | Securities repricing and the long end: maturities → reinvestment decision → book yield → NII; prepayment extension; AFS marks to AOCI and CET1 | Internal: s18 only (10Y → CET1) | `jpm.path.securities_reinvestment`, `jpm.path.long_end`; a calibrated long-end reduced form from the disclosed steeper-curve scenario | Maturity ladder, purchase allocation and yields, MBS share, AFS duration | "Higher long rates lift NII" vs "hurt capital" | `test_required_paths_exist`, `test_marks_reach_capital_not_income` | MC / CAL |
| G07 | Markets NII sits in firmwide NII and in Markets revenue; its rate sensitivity is offset inside Markets | Internal: none | NII ex Markets as a difference identity (firmwide NII − Markets NII) in the line view, so Markets NII is counted once inside Markets revenue; counter-paths Fed → Markets funding (−) and Fed → Markets NII (−) | Markets NII history and guidance (`jpm.wb`, `jpm.r9`) | Firmwide NII sensitivity; double counting | `test_markets_nii_is_counted_once_through_a_difference_identity` | MC |
| G08 | Markets products and volatility counter-paths (equity levels, spreads, market-risk RWA, incentive pay) | Internal: s14 only | `jpm.comp.markets`, `jpm.path.markets`; s14 scoped as the reduced form | Revenue sensitivity to volatility | "Volatility is good for JPMorgan" | `test_required_paths_exist` | MC / CAL |
| G09 | IB fees as wallet times share; the compensation offset | Internal: s12 only | `jpm.path.deals_ib`; s12 transition (wallet × share) | Pipeline/backlog | IB fee forecasts | `test_required_paths_exist` | MC |
| G10 | Card and payments: spend → interchange net of rewards; balances → NII; day-one reserves | Internal: none | `jpm.path.card_growth` with its counter-paths | Rewards share (found), revolve rate | Card growth as pure upside | `test_two_credit_clocks` | MC |
| G11 | Asset management fees on market levels | Internal: none; no US equity value in the world | `us_capital_markets.equity_index`, `jpm.path.asset_management` | AUM roll-forward (found) | AWM revenue | `test_required_paths_exist` | MC |
| G12 | Credit costs and the credit cycle: provision = charge-offs + reserve build, card vs wholesale, CECL timing | Internal: none; no unemployment or credit spread in the world | `us_economy.unemployment_rate`, `us_capital_markets.credit_spread`; credit views; `jpm.path.card_credit`, `jpm.path.wholesale_credit` (two clocks) | CECL scenarios, roll rates, wholesale exposure by industry | Any recession conclusion | `test_two_credit_clocks` | MC / CAL |
| G13 | Expenses and operating leverage | Internal: none | `jpm.comp.expense`; revenue-linked pay offsets in the Markets, IB and AWM paths; `jpm.path.expense_inflation` | Comp ratios (found) | Operating leverage | `test_required_paths_exist` | MC |
| G14 | Capital and payout: CET1 capital, RWA, requirement, buybacks, dividends; s18 unscoped | Internal: `cet1_ratio`, s18, s22 | Capital values and `jpm.path.capital_payout`, `jpm.path.capital_requirements`, `jpm.path.balance_sheet_growth`; the CET1 stock-flow `jpm.sf.cet1` and the ratio identity `jpm.id.cet1_ratio`; s18 scoped | AOCI sensitivity, management buffer, capital-rule RWA | Buyback capacity | `test_capital_is_a_stock_that_rolls_forward` | MC / MAP |
| G15 | Reporting segments (CCB, CIB, AWM, Corporate) and their lines of business; segment net income | Internal: none | `jpm.comp.revenue_by_segment`, `jpm.comp.ccb_lines`, `jpm.comp.cib_businesses`, `jpm.comp.awm_businesses`, `jpm.comp.net_income_by_segment` (Corporate as residual; no intersegment eliminations line is reported) | Supplement segment tables (found) | Segment mix and contribution | `test_segment_views_are_separate_from_the_driven_view`, `test_one_driving_view_per_total_and_the_segments_reconcile` | MC |
| G16 | New objects absent from the export | Export: none | Transitions in relationship properties, `financial_bridge`, `business_construction` paths | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G17 | New node ids not retrievable | Internal API: none | `/v1/world-models/sally_demo/graph`, `…/entities/jpmorgan/construction` and its traces | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G18 | A results release reports the segment and line views on the same day; the import guard folds one view per total and day | Import: `intake/overlap.py` | Not built here (shared code): see the completion report | A fix to the guard (it over-drops) and a two-way (matrix) reconciliation | Importing a full set of actuals | listed as blocked | RET |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, kind, memberships, share-price kind default (`jpmorgan`) | Already owned | entities.yaml `jpmorgan` | untouched |
| m25, s12, s14, s18 (statistical records on JPMorgan's values) | Already owned → Modify lightly | interactions.yaml | ids, sizes and kernels kept; transitions added (scope, reduced form, evidence, unresolved inputs) |
| s20, s21, s22 and the NII → share price kind default | Do not touch | interactions.yaml, taxonomy | untouched |
| `net_interest_income`, `ib_fees`, `markets_revenue`, `cet1_ratio` definitions | Modify lightly | entities.yaml | `features.view/basis/metric` added; ids and priors kept for Sally's expected paths |
| Compositions, operating states, connected paths, financial mappings, credit-cycle and equity-market values, bindings | Missing | construction/jpmorgan.yaml; local sources, citations, baselines | built |
| Shared macro links (m01–m12, s08–s11) and other banks' objects (Citigroup, Morgan Stanley) | Do not touch | interactions.yaml, entities.yaml | untouched; JPMorgan paths start below them |
| Import overlap guard | Do not touch (shared code) | `src/axelrod_wm/intake/overlap.py` | finding reported, not edited |

## Definitions and bases

- **Managed basis** (`features.basis` "managed"): revenue on a fully taxable-equivalent basis, the basis on which the
  reporting segments add up. Net revenue, NII, pretax income and tax are managed; net income is the same on both bases.
  The managed-to-reported (FTE) reconciliation is not represented as a value.
- **Firmwide NII** (`jpmorgan.net_interest_income`) includes CIB Markets NII (`jpmorgan.markets_nii`). The company
  guides **NII ex Markets** (`jpmorgan.nii_ex_markets`), held as a difference identity (`jpm.id.nii_ex_markets`):
  firmwide NII less Markets NII.
- **Markets revenue** (`jpmorgan.markets_revenue`) is a CIB product total (Fixed Income plus Equity Markets, incl.
  Markets NII); it is not the principal-transactions line.
- **The line view** (`jpm.comp.revenue_by_line`, the driving view of net revenue): NII ex Markets + Markets revenue
  (incl. Markets NII) + IB fees + asset management fees + card income + lending and deposit fees + mortgage fees +
  other (residual). **The segment view** (`jpm.comp.revenue_by_segment`): CCB + CIB + AWM + Corporate (residual),
  marked `drives: false` and held as the reconciling columns of the matrix `jpm.mx.revenue` (lines × segments). Net
  income is driven by the P&L bridge (`jpm.comp.net_income`); segment net income (`jpm.comp.net_income_by_segment`) is
  reconciling. A reconciling view is observed and checked against its total but carries no accounting links into it.
- **Costs and charges are negative values** (expense, provision, charge-offs, reserve builds, interest expense, tax),
  so every part adds to its total with a positive weight. A cost link's sign "−" means "a larger charge".
- **Credit**: provision = net charge-offs + reserve build (the allowance roll-forward), by portfolio. Reserve builds
  follow the CECL outlook (and growth); charge-offs follow realized losses.
- **Balances times rates**: interest lines, charge-offs, asset management fees and card income are product identities
  (balance × rate × 0.01, rates held in %); interest-bearing deposits are average deposits less noninterest-bearing
  ones (a difference identity), noninterest-bearing deposits the average times their share.
- **Capital**: CET1 capital is a stock (`jpm.sf.cet1`: net income in, dividends and buybacks out, per year); AOCI marks
  enter as a signed link (a level, not a flow). The CET1 ratio is capital over RWA × 100 (`jpm.id.cet1_ratio`).
- Fiscal year = calendar year. Segment history is restated for the combination of the corporate and commercial banks.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities jpmorgan` from the loaded model (the
same objects the API serves at `/v1/world-models/sally_demo/entities/jpmorgan/construction`). A `?` marks a step whose size is unknown
(uncalibrated). Levels are left out here; the local copy adds them.

130 links touch its values: 87 calibrated, 43 uncalibrated (represented, size unknown), 49 accounting, 24 identity, 3 stock-flow; 4 state-dependent; 126 carry a transition.

### Business composition

#### reporting segments: AWM net revenue by business, managed ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan AWM Asset Management revenue | `jpmorgan.awm_asset_management` |
| JPMorgan AWM Global Private Bank revenue | `jpmorgan.awm_private_bank` |
| **Total: JPMorgan Asset & Wealth Management revenue** | `jpmorgan.awm_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual.

#### credit: card provision: net charge-offs plus reserve build (allowance roll-forward) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan card net charge-offs | `jpmorgan.card_net_charge_offs` |
| JPMorgan card reserve build | `jpmorgan.card_reserve_build` |
| **Total: JPMorgan card provision** | `jpmorgan.card_provision` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Charge-offs are loans times the loss rate (jpm.id.card_nco); the reserve build follows the CECL outlook and growth.

#### reporting segments: CCB net revenue by line of business, managed ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan CCB Banking & Wealth Management revenue | `jpmorgan.ccb_banking_wealth` |
| JPMorgan CCB Home Lending revenue | `jpmorgan.ccb_home_lending` |
| JPMorgan CCB Card Services & Auto revenue | `jpmorgan.ccb_card_auto` |
| **Total: JPMorgan Consumer & Community Banking revenue** | `jpmorgan.ccb_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual.

#### reporting segments: CIB net revenue by business, managed ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan CIB Banking & Payments revenue | `jpmorgan.cib_banking_payments` |
| JPMorgan CIB Securities Services revenue | `jpmorgan.cib_securities_services` |
| Residual: JPMorgan CIB Markets and credit adjustments | `jpmorgan.cib_markets_adjustments` |
| **Total: JPMorgan Commercial & Investment Bank revenue** | `jpmorgan.cib_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Markets revenue is held in the line view; the residual here is Markets plus credit adjustments, bridged by jpm-c-bridge-markets-cib (no size).

#### credit: provision for credit losses by portfolio (negative values) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan card provision | `jpmorgan.card_provision` |
| JPMorgan consumer ex-card provision | `jpmorgan.consumer_ex_card_provision` |
| JPMorgan wholesale loan provision | `jpmorgan.wholesale_provision` |
| Residual: JPMorgan lending-commitment and securities provision | `jpmorgan.commitments_other_provision` |
| **Total: JPMorgan provision for credit losses** | `jpmorgan.provision_for_credit_losses` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Card is most of the provision; wholesale is small but lumpy.

#### reporting segments: noninterest expense by type (negative values) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan compensation expense | `jpmorgan.compensation_expense` |
| JPMorgan technology expense | `jpmorgan.technology_expense` |
| JPMorgan marketing expense | `jpmorgan.marketing_expense` |
| Residual: JPMorgan other noninterest expense | `jpmorgan.other_expense` |
| **Total: JPMorgan noninterest expense** | `jpmorgan.noninterest_expense` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Operating leverage is revenue growth less expense growth: revenue-linked compensation is the variable part.

#### liabilities: interest expense by funding source (negative values) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan interest expense on deposits | `jpmorgan.deposit_interest_expense` |
| JPMorgan interest expense on Markets funding | `jpmorgan.markets_funding_expense` |
| JPMorgan interest expense on long-term debt | `jpmorgan.long_term_debt_expense` |
| Residual: JPMorgan other interest expense | `jpmorgan.other_funding_expense` |
| **Total: JPMorgan interest expense** | `jpmorgan.interest_expense` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Deposits are interest-bearing balances times the deposit cost (jpm.id.deposit_expense); Markets funding has no balance in the model.

#### investment assets: interest income by earning asset, managed (FTE) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan interest income on loans | `jpmorgan.loan_interest_income` |
| JPMorgan interest income on investment securities | `jpmorgan.securities_interest_income` |
| JPMorgan interest income on cash and deposits with banks | `jpmorgan.cash_interest_income` |
| JPMorgan interest income on Markets assets | `jpmorgan.markets_interest_income` |
| Residual: JPMorgan other interest income | `jpmorgan.other_interest_income` |
| **Total: JPMorgan interest income** | `jpmorgan.interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Loans, securities and cash are balance times yield (jpm.id.loan_income, jpm.id.securities_income, jpm.id.cash_income).

#### operating state: average loans by portfolio ($bn, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan card loans | `jpmorgan.card_loans` |
| JPMorgan wholesale loans | `jpmorgan.wholesale_loans` |
| Residual: JPMorgan consumer ex-card and held-for-sale loans | `jpmorgan.consumer_ex_card_loans` |
| **Total: JPMorgan average loans** | `jpmorgan.avg_loans` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Card balances earn the card yield inside the loan yield; their own yield is not split out.

#### product: CIB Markets revenue by product, managed (incl. Markets NII) ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan Fixed Income Markets revenue | `jpmorgan.fixed_income_markets` |
| JPMorgan Equity Markets revenue | `jpmorgan.equity_markets` |
| **Total: JPMorgan markets revenue** | `jpmorgan.markets_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split as reported: no residual.

#### reporting segments: net income: managed pretax income less managed income tax ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan pretax income (managed) | `jpmorgan.pretax_income` |
| JPMorgan income tax (managed) | `jpmorgan.income_tax` |
| **Total: JPMorgan net income** | `jpmorgan.net_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driving view of net income. An identity; the FTE adjustment cancels between managed revenue and managed tax.

#### reporting segments: net income by reporting segment ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan CCB net income | `jpmorgan.ccb_net_income` |
| JPMorgan CIB net income | `jpmorgan.cib_net_income` |
| JPMorgan AWM net income | `jpmorgan.awm_net_income` |
| Residual: JPMorgan Corporate net income | `jpmorgan.corporate_net_income` |
| **Total: JPMorgan net income** | `jpmorgan.net_income` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling: reported and checked against the total, never driving it (jpm.comp.net_income drives).

#### investment assets: firmwide NII, managed: interest income less interest expense ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan interest income | `jpmorgan.interest_income` |
| JPMorgan interest expense | `jpmorgan.interest_expense` |
| **Total: JPMorgan net interest income** | `jpmorgan.net_interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity. Each line below is a balance times a rate (product identities).

#### reporting segments: managed pretax income: net revenue less noninterest expense less provision for credit losses ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan net revenue (managed) | `jpmorgan.net_revenue` |
| JPMorgan noninterest expense | `jpmorgan.noninterest_expense` |
| JPMorgan provision for credit losses | `jpmorgan.provision_for_credit_losses` |
| **Total: JPMorgan pretax income (managed)** | `jpmorgan.pretax_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity: expense and provision are negative values.

#### product: managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan NII ex Markets | `jpmorgan.nii_ex_markets` |
| JPMorgan markets revenue | `jpmorgan.markets_revenue` |
| JPMorgan investment banking fees | `jpmorgan.ib_fees` |
| JPMorgan asset management fees | `jpmorgan.asset_mgmt_fees` |
| JPMorgan card income | `jpmorgan.card_income` |
| JPMorgan lending and deposit fees | `jpmorgan.lending_deposit_fees` |
| JPMorgan mortgage fees | `jpmorgan.mortgage_fees` |
| Residual: JPMorgan other revenue | `jpmorgan.other_revenue` |
| **Total: JPMorgan net revenue (managed)** | `jpmorgan.net_revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driving view of net revenue: rates enter through NII ex Markets (firmwide NII less Markets NII, a difference identity), volatility through Markets, deals through IB fees; Markets NII is counted once, inside Markets revenue. The segment view is the matrix's reconciling columns (jpm.mx.revenue).

#### reporting segments: managed net revenue by reporting segment ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan Consumer & Community Banking revenue | `jpmorgan.ccb_revenue` |
| JPMorgan Commercial & Investment Bank revenue | `jpmorgan.cib_revenue` |
| JPMorgan Asset & Wealth Management revenue | `jpmorgan.awm_revenue` |
| Residual: JPMorgan Corporate revenue | `jpmorgan.corporate_revenue` |
| **Total: JPMorgan net revenue (managed)** | `jpmorgan.net_revenue` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling (the columns of jpm.mx.revenue): reported and checked against the total, never driving it. No intersegment eliminations line is reported; Corporate is the residual.

#### credit: wholesale loan provision: net charge-offs plus reserve build ($bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| JPMorgan wholesale net charge-offs | `jpmorgan.wholesale_net_charge_offs` |
| JPMorgan wholesale reserve build | `jpmorgan.wholesale_reserve_build` |
| **Total: JPMorgan wholesale loan provision** | `jpmorgan.wholesale_provision` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity of the allowance roll-forward.

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `jpm.id.am_fees` (product) | JPMorgan asset management fees = 0.01 x JPMorgan assets under management x JPMorgan asset management fee rate | JPMorgan assets under management (factor, +1.000); JPMorgan asset management fee rate (factor, +0.833) | $bn/yr = $bn x %/yr x 0.01 |
| `jpm.id.card_income` (product) | JPMorgan card income = 0.01 x JPMorgan debit and credit card sales volume x JPMorgan net card income rate | JPMorgan debit and credit card sales volume (factor, +0.267); JPMorgan net card income rate (factor, +1.067) | $bn/yr = $bn/yr x % x 0.01 |
| `jpm.id.card_nco` (product) | JPMorgan card net charge-offs = -0.01 x JPMorgan card loans x JPMorgan card net charge-off rate | JPMorgan card loans (factor, -0.400); JPMorgan card net charge-off rate (factor, -0.938) | $bn/yr (negative) = -($bn x %/yr x 0.01) |
| `jpm.id.cash_income` (product) | JPMorgan interest income on cash and deposits with banks = 0.01 x JPMorgan cash and deposits with banks x JPMorgan yield on cash and deposits with banks | JPMorgan cash and deposits with banks (factor, +1.000); JPMorgan yield on cash and deposits with banks (factor, +0.444) | $bn/yr = $bn x %/yr x 0.01 |
| `jpm.id.cet1_ratio` (ratio) | JPMorgan CET1 ratio = 100 x JPMorgan CET1 capital / JPMorgan risk-weighted assets | JPMorgan CET1 capital (numerator, +1.667); JPMorgan risk-weighted assets (denominator, -1.550) | % = $bn / $bn x 100 |
| `jpm.id.deposit_expense` (product) | JPMorgan interest expense on deposits = -0.01 x JPMorgan interest-bearing deposits x JPMorgan interest-bearing deposit cost | JPMorgan interest-bearing deposits (factor, -0.513); JPMorgan interest-bearing deposit cost (factor, -1.000) | $bn/yr (negative) = -($bn x %/yr x 0.01) |
| `jpm.id.ib_deposits` (difference) | JPMorgan interest-bearing deposits = JPMorgan average deposits - JPMorgan noninterest-bearing deposits | JPMorgan average deposits (total, +1.071); JPMorgan noninterest-bearing deposits (deduction, -0.571) | unknown |
| `jpm.id.loan_income` (product) | JPMorgan interest income on loans = 0.01 x JPMorgan average loans x JPMorgan loan yield | JPMorgan average loans (factor, +0.750); JPMorgan loan yield (factor, +0.769) | $bn/yr = $bn x %/yr x 0.01 |
| `jpm.id.nib_deposits` (product) | JPMorgan noninterest-bearing deposits = 0.01 x JPMorgan average deposits x JPMorgan noninterest-bearing deposit share | JPMorgan average deposits (factor, +0.375); JPMorgan noninterest-bearing deposit share (factor, +0.938) | $bn = $bn x % x 0.01 |
| `jpm.id.nii_ex_markets` (difference) | JPMorgan NII ex Markets = JPMorgan net interest income - JPMorgan Markets net interest income | JPMorgan net interest income (total, +0.987); JPMorgan Markets net interest income (deduction, -0.309) | unknown |
| `jpm.id.securities_income` (product) | JPMorgan interest income on investment securities = 0.01 x JPMorgan investment securities x JPMorgan investment securities yield | JPMorgan investment securities (factor, +0.667); JPMorgan investment securities yield (factor, +0.685) | $bn/yr = $bn x %/yr x 0.01 |
| `jpm.id.wholesale_nco` (product) | JPMorgan wholesale net charge-offs = -0.01 x JPMorgan wholesale loans x JPMorgan wholesale net charge-off rate | JPMorgan wholesale loans (factor, -0.080); JPMorgan wholesale net charge-off rate (factor, -0.800) | $bn/yr (negative) = -($bn x %/yr x 0.01) |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `jpm.sf.cet1` | JPMorgan CET1 capital (closing) = JPMorgan CET1 capital (opening) + JPMorgan net income - JPMorgan common dividends - JPMorgan share buybacks, per 365 days | JPMorgan net income (inflow, +0.420); JPMorgan common dividends (outflow, -0.100); JPMorgan share buybacks (outflow, -0.800) |

### Matrix `jpm.mx.revenue`: jpm.comp.revenue_by_line x jpm.comp.revenue_by_segment (the rows drive the total; jpm.comp.revenue_by_segment reconciles)

No cells are given: the views reconcile to the total only.

Managed net revenue as lines x segments. The lines drive (rates, volatility and deals act on lines that cut across segments); the segments reconcile. Cells are not built: the segment split of each line is disclosed only for NII and noninterest revenue in total, not for the line view's lines.

### Operating and financial paths

#### JPMorgan market levels to asset management fees

**Trigger:** US equity markets rise. **Endpoint:** JPMorgan net income.

US equity market level → [aum] JPMorgan assets under management? → [prime] JPMorgan Equity Markets revenue? → JPMorgan asset management fees → JPMorgan net revenue (managed) → JPMorgan compensation expense? → JPMorgan markets revenue → JPMorgan net revenue (managed) → JPMorgan noninterest expense → JPMorgan pretax income (managed) → JPMorgan pretax income (managed) → JPMorgan net income  (? marks a step whose size is unknown)

Market levels revalue AUM (fees on average AUM) and lift prime balances in Equity Markets; advisor pay takes a share.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [aum] `jpm-c-equity-aum` | Market moves revalue client assets; AUM rises with equity and multi-asset markets, besides net flows (markets; clients (flows)) | the equity and multi-asset share of AUM; observable: AUM roll-forward: market/performance impacts versus net flows | onset immediate; build none; persists while levels hold; recognized fees on average AUM | documented / documented / unknown / documented | outflows in a sell-off; liquidity funds grow when markets fall | assets under management | unknown |
| 2 [prime] `jpm-c-equity-eqmkts` | Prime brokerage financing balances and cash volumes rise with equity market levels and hedge-fund leverage (hedge funds (prime clients)) | client leverage holds; observable: prime balances; gross leverage | onset same quarter; build none; persists while levels hold; recognized daily | broker / broker / unknown / unknown | forced deleveraging | Equity Markets revenue | unknown |
| 3 `jpm-c-aum-fees` | Asset management fees are average AUM times the fee rate (lower for liquidity and fixed income than for equity and alternatives) (AWM) | bilinear: AUM times fee rate; mix changes the rate; observable: asset management fees and the implied fee rate (workbook) | onset same quarter on average AUM; build none; persists while AUM holds; recognized fees monthly or quarterly | documented / documented / model / documented | mix shift to liquidity and passive; fee compression | asset management fees | +1.00 sd/sd (identity) |
| 4 `jpm-a-rev-asset-mgmt-fees` | JPMorgan asset management fees is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.24 sd/sd (accounting) |
| 5 `jpm-c-amfees-comp` | Offset: advisor and portfolio-manager pay accrues with AWM revenue (management) | accrual ratio held; observable: AWM compensation over AWM revenue | onset same quarter; build year-end; persists annual; recognized compensation expense each quarter | documented / documented / unknown / inferred | fixed pay | compensation expense | unknown |
| 6 `jpm-a-mkts-equity-markets` | JPMorgan Equity Markets revenue is one part of JPMorgan markets revenue (CIB Markets revenue by product, managed (incl. Markets NII)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | markets revenue | +0.49 sd/sd (accounting) |
| 7 `jpm-a-rev-markets-revenue` | JPMorgan markets revenue is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.30 sd/sd (accounting) |
| 8 `jpm-a-exp-compensation-expense` | JPMorgan compensation expense is one part of JPMorgan noninterest expense (noninterest expense by type (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | noninterest expense | +0.67 sd/sd (accounting) |
| 9 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 10 `jpm-a-pretax-noninterest-expense` | JPMorgan noninterest expense is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +0.47 sd/sd (accounting) |
| 11 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |

Unresolved inputs: AUM by asset class and market impact (found connected).

#### JPMorgan loan growth, NII and capital

**Trigger:** wholesale loans grow. **Endpoint:** JPMorgan CET1 ratio.

JPMorgan wholesale loans → [balances] JPMorgan average loans → [reserve] JPMorgan wholesale reserve build? → [losses] JPMorgan wholesale net charge-offs → [nii] JPMorgan interest income on loans → [rwa] JPMorgan risk-weighted assets? → JPMorgan interest income → JPMorgan net interest income → JPMorgan NII ex Markets → JPMorgan net revenue (managed) → JPMorgan wholesale loan provision → JPMorgan wholesale loan provision → JPMorgan provision for credit losses → JPMorgan pretax income (managed) → JPMorgan pretax income (managed) → JPMorgan net income → JPMorgan CET1 capital → JPMorgan CET1 ratio → JPMorgan CET1 ratio  (? marks a step whose size is unknown)

Counter-paths: wholesale loan growth adds NII (loans times yield) but needs a day-one reserve, charges off more dollars, and consumes RWA, so it competes with buybacks for capital.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [balances] `jpm-a-loans-wholesale-loans` | JPMorgan wholesale loans is one part of JPMorgan average loans (average loans by portfolio); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | average loans | +0.71 sd/sd (accounting) |
| 2 [reserve] `jpm-c-loans-wreserve` | Counter-path to loan growth: new wholesale loans carry a day-one CECL reserve (JPMorgan (allowance process)) | growth in retained loans (not held-for-sale); observable: wholesale allowance against wholesale loans | onset quarter of growth; build none; persists while held; recognized provision that quarter | documented / documented / unknown / documented | a coverage release | wholesale reserve build | unknown |
| 3 [losses] `jpm.id.wholesale_nco:jpmorgan.wholesale_loans` | JPMorgan wholesale net charge-offs = -0.01 x JPMorgan wholesale loans x JPMorgan wholesale net charge-off rate: JPMorgan wholesale loans is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.08 sd/sd (identity) |
| 4 [nii] `jpm-c-loans-income` | A larger average loan book earns more interest at the prevailing yield (JPMorgan (lending)) | bilinear: balance times yield; growth funded by deposits rather than by wholesale debt; observable: average loans and loan interest income | onset same quarter; build as loans are drawn; persists while held; recognized interest income each quarter | documented / documented / model / documented | growth in low-spread loans (securities-based, markets lending) adds less | interest income on loans | +0.75 sd/sd (identity) |
| 5 [rwa] `jpm-c-loans-rwa` | Counter-path to NII growth: new loans carry risk weights, so loan growth raises RWA and uses capital that would otherwise fund buybacks (lending businesses) | growth in risk-weighted (not zero-weight) assets; observable: RWA as a share of earning assets | onset as loans are booked; build none; persists while held; recognized quarterly capital reporting | documented / documented / unknown / documented | risk transfer and securitization; low-weight lending | risk-weighted assets | unknown |
| 6 `jpm-a-ii-loan-interest-income` | JPMorgan interest income on loans is one part of JPMorgan interest income (interest income by earning asset, managed (FTE)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | interest income | +0.49 sd/sd (accounting) |
| 7 `jpm-a-nii-interest-income` | JPMorgan interest income is one part of JPMorgan net interest income (firmwide NII, managed: interest income less interest expense); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net interest income | +1.57 sd/sd (accounting) |
| 8 `jpm.id.nii_ex_markets:jpmorgan.net_interest_income` | JPMorgan NII ex Markets = JPMorgan net interest income - JPMorgan Markets net interest income: JPMorgan net interest income is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.99 sd/sd (identity) |
| 9 `jpm-a-rev-nii-ex-markets` | JPMorgan NII ex Markets is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.69 sd/sd (accounting) |
| 10 `jpm-a-wprov-wholesale-reserve-build` | JPMorgan wholesale reserve build is one part of JPMorgan wholesale loan provision (wholesale loan provision: net charge-offs plus reserve build); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wholesale loan provision | +0.80 sd/sd (accounting) |
| 11 `jpm-a-wprov-wholesale-net-charge-offs` | JPMorgan wholesale net charge-offs is one part of JPMorgan wholesale loan provision (wholesale loan provision: net charge-offs plus reserve build); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wholesale loan provision | +0.50 sd/sd (accounting) |
| 12 `jpm-a-prov-wholesale-provision` | JPMorgan wholesale loan provision is one part of JPMorgan provision for credit losses (provision for credit losses by portfolio (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | provision for credit losses | +0.50 sd/sd (accounting) |
| 13 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 14 `jpm-a-pretax-provision-for-credit-losses` | JPMorgan provision for credit losses is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +0.31 sd/sd (accounting) |
| 15 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |
| 16 `jpm-c-ni-cet1` | Net income adds to retained earnings and so to CET1 capital (a flow into a stock: next period's capital is this period's plus earnings less distributions) (group) | accumulation over the period; preferred dividends come out first; observable: CET1 capital roll-forward | onset quarter end; build cumulative; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | distributions above earnings | CET1 capital | +0.42 sd/sd (stock-flow, accumulates per 365 days) |
| 17 `jpm-c-rwa-ratio` | More risk-weighted assets at the same capital lower the CET1 ratio (group) | capital unchanged; observable: RWA and the CET1 ratio | onset quarter end; build none; persists while RWA holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | -1.55 sd/sd (identity) |
| 18 `jpm-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets; more capital at the same RWA raises it (a ratio identity, linear only near current levels) (group) | RWA unchanged; observable: CET1 ratio, CET1 capital and RWA | onset quarter end; build none; persists while capital holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | +1.67 sd/sd (identity) |

#### JPMorgan capital and payout

**Trigger:** earnings are retained. **Endpoint:** JPMorgan share buybacks.

JPMorgan net income → [capital] JPMorgan CET1 capital → [dividend] JPMorgan common dividends? → JPMorgan CET1 ratio → JPMorgan share buybacks? → JPMorgan CET1 capital → JPMorgan CET1 capital  (? marks a step whose size is unknown)

Earnings add to CET1; dividends follow earnings; capital above the requirement and buffer funds buybacks, which use capital in turn (a feedback loop).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [capital] `jpm-c-ni-cet1` | Net income adds to retained earnings and so to CET1 capital (a flow into a stock: next period's capital is this period's plus earnings less distributions) (group) | accumulation over the period; preferred dividends come out first; observable: CET1 capital roll-forward | onset quarter end; build cumulative; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | distributions above earnings | CET1 capital | +0.42 sd/sd (stock-flow, accumulates per 365 days) |
| 2 [dividend] `jpm-c-ni-dividends` | The board sets a progressive dividend at a payout of earnings; higher sustained earnings support a higher dividend (board) | earnings seen as sustainable; capital above requirement; observable: dividend per share and payout ratio | onset next declaration; build annual review; persists sticky (cuts are rare); recognized on declaration | documented / documented / unknown / documented | capital stress; regulators restrict distributions | common dividends | unknown |
| 3 `jpm-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets; more capital at the same RWA raises it (a ratio identity, linear only near current levels) (group) | RWA unchanged; observable: CET1 ratio, CET1 capital and RWA | onset quarter end; build none; persists while capital holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | +1.67 sd/sd (identity) |
| 4 `jpm-c-ratio-buybacks` | Capital above the requirement plus the management buffer is returned through buybacks, after organic growth; the board sets the pace under its authorization (board and management (capital allocation)) | the ratio is above requirement plus management buffer; growth opportunities do not absorb the capital first; observable: CET1 ratio against the requirement; buybacks executed each quarter | onset next quarter; build through the year; persists while excess lasts; recognized equity at execution | documented / documented / unknown / broker | AOCI losses, G-SIB surcharge increases or pending capital rules shrink the excess; management chooses growth over buybacks | share buybacks | unknown; acts only while JPMorgan CET1 ratio is above 12.5 |
| 5 `jpm-c-buyback-cet1` | Share repurchases reduce common equity and CET1 capital dollar for dollar (a feedback: capacity funds buybacks, buybacks use capacity) (board and management) | executed under the authorization; observable: treasury stock purchased; CET1 roll-forward | onset execution; build through the quarter; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | none (identity of the roll-forward) | CET1 capital | -0.80 sd/sd (stock-flow, accumulates per 365 days) |
| 6 `jpm-c-dividends-cet1` | Common dividends declared reduce retained earnings and CET1 capital (board) | declared in the period; observable: dividends declared; CET1 roll-forward | onset declaration; build none; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | none (identity of the roll-forward) | CET1 capital | -0.10 sd/sd (stock-flow, accumulates per 365 days) |

Unresolved inputs: buyback authorization (found connected); management CET1 target and buffer (found not connected).

#### JPMorgan capital requirements

**Trigger:** the CET1 requirement rises (stress capital buffer, G-SIB surcharge, a capital rule). **Endpoint:** JPMorgan share buybacks.

JPMorgan CET1 requirement → JPMorgan share buybacks? → JPMorgan CET1 capital → JPMorgan CET1 ratio  (? marks a step whose size is unknown)

A higher floor shrinks the excess; buybacks slow and capital is retained.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `jpm-c-req-buybacks` | A higher requirement (stress capital buffer from the stress test, G-SIB surcharge, a capital rule) raises the floor and shrinks the excess available for buybacks (regulators (Fed stress test, G-SIB framework, capital rules)) | the requirement binds within the planning horizon; observable: stress capital buffer announcement; G-SIB score and surcharge; final capital rules | onset announcement; build phase-in; persists until the next reset; recognized capital planning | documented / documented / unknown / documented | rules that lower the requirement (the research expects capital reform to be neutral to positive) | share buybacks | unknown |
| 2 `jpm-c-buyback-cet1` | Share repurchases reduce common equity and CET1 capital dollar for dollar (a feedback: capacity funds buybacks, buybacks use capacity) (board and management) | executed under the authorization; observable: treasury stock purchased; CET1 roll-forward | onset execution; build through the quarter; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | none (identity of the roll-forward) | CET1 capital | -0.80 sd/sd (stock-flow, accumulates per 365 days) |
| 3 `jpm-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets; more capital at the same RWA raises it (a ratio identity, linear only near current levels) (group) | RWA unchanged; observable: CET1 ratio, CET1 capital and RWA | onset quarter end; build none; persists while capital holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | +1.67 sd/sd (identity) |

Unresolved inputs: CET1 requirement and G-SIB surcharge (found connected); RWA effect of the pending capital rules for this bank (not disclosed in reviewed sources).

#### JPMorgan consumer credit cycle (card)

**Trigger:** US growth slows and unemployment rises. **Endpoint:** JPMorgan net income.

US real GDP growth → US unemployment rate? → [spend_growth] JPMorgan debit and credit card sales volume? → [losses] JPMorgan card 30+ day delinquency rate? → [reserve] JPMorgan card reserve build? → [spend] JPMorgan debit and credit card sales volume? → JPMorgan card net charge-off rate? → JPMorgan card net charge-offs → JPMorgan card provision → JPMorgan card provision → JPMorgan card income → JPMorgan net revenue (managed) → JPMorgan provision for credit losses → JPMorgan pretax income (managed) → JPMorgan pretax income (managed) → JPMorgan net income  (? marks a step whose size is unknown)

Two clocks: CECL builds reserves in the quarter the unemployment outlook worsens; charge-offs follow delinquencies about two quarters later. Spending (card income) falls at the same time.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `jpm-c-gdp-unemp` | Growth below trend raises the unemployment rate with a lag (Okun's relation) (employers) | growth below potential for several quarters; observable: monthly payrolls and the unemployment rate | onset 1-2 quarters; build several quarters; persists while growth is weak; recognized monthly data | inferred / inferred / unknown / unknown | labour hoarding; falling participation | US unemployment rate | unknown |
| 2 [spend_growth] `jpm-c-gdp-spend` | Real consumption growth raises card purchase volume (consumers) | consumption grows with output; observable: card sales volume growth | onset same quarter; build none; persists while growth lasts; recognized interchange monthly | documented / inferred / unknown / unknown | share loss to other networks and wallets | card sales volume | unknown |
| 3 [losses] `jpm-c-unemp-delinq` | Borrowers who lose income miss card payments first; early-stage delinquencies rise within one or two quarters of job losses (card borrowers) | income shock not cushioned by savings or transfers; observable: 30+ day card delinquency rate (monthly master trust data) | onset 1-2 quarters; build 2-3 quarters; persists while unemployment stays high; recognized monthly trust data | inferred / inferred / unknown / broker | tighter underwriting on recent vintages; household savings buffers | card 30+ day delinquency rate | unknown |
| 4 [reserve] `jpm-c-unemp-cardreserve` | Under CECL the card allowance covers lifetime expected losses under weighted macro scenarios; a worse unemployment outlook builds reserves in the quarter the forecast changes, before charge-offs rise (a charge, more negative) (JPMorgan (allowance process, risk management)) | the forecast unemployment path in the weighted scenarios moves; recognized at quarter end; observable: reserve build in the card allowance; the bank's central-case unemployment assumption (not in the sources read) | onset quarter end of the forecast change; build one or two quarters; persists released when the outlook improves or losses are realized; recognized provision in that quarter | documented / documented / unknown / inferred | management overlays; scenario weights; an outlook change already reserved | card reserve build | unknown |
| 5 [spend] `jpm-c-unemp-spend` | Households that lose income spend less on cards (consumers) | income loss not offset by transfers; observable: debit and credit card sales volume | onset 1 quarter; build several quarters; persists while unemployment stays high; recognized interchange monthly | inferred / inferred / unknown / unknown | nominal inflation keeps volumes up | card sales volume | unknown |
| 6 `jpm-c-delinq-nco` | Delinquent card balances that are not cured are charged off at 180 days past due; charge-offs follow delinquencies by about two quarters (roll rates) (card borrowers; collections) | cure rates unchanged; observable: card net charge-off rate against lagged delinquencies | onset 2 quarters; build 1-2 quarters; persists while delinquencies stay high; recognized charge-offs each month | documented / documented / unknown / inferred | collections and hardship programmes raise cure rates | card net charge-off rate | unknown |
| 7 `jpm-c-ncorate-nco` | Card net charge-offs are the loss rate times average card loans (a charge: more negative) (card borrowers) | bilinear: rate times balance; observable: card net charge-offs and the NCO rate | onset same month; build none; persists while the rate holds; recognized provision each quarter | documented / documented / model / documented | recoveries | card net charge-offs | -0.94 sd/sd (identity) |
| 8 `jpm-a-cardprov-card-net-charge-offs` | JPMorgan card net charge-offs is one part of JPMorgan card provision (card provision: net charge-offs plus reserve build (allowance roll-forward)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | card provision | +0.67 sd/sd (accounting) |
| 9 `jpm-a-cardprov-card-reserve-build` | JPMorgan card reserve build is one part of JPMorgan card provision (card provision: net charge-offs plus reserve build (allowance roll-forward)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | card provision | +0.67 sd/sd (accounting) |
| 10 `jpm-c-spend-cardincome` | Interchange is earned on each purchase, but most of it is paid back as rewards and partner payments, so net card income moves by a fraction of interchange (card networks, merchants, cardholders (rewards)) | the rewards rate holds; competitive card launches raise it; observable: interchange income, rewards costs and their ratio (workbook) | onset same month; build none; persists while volumes hold; recognized card income monthly | documented / documented / model / documented | rewards competition; interchange regulation | card income | +0.27 sd/sd (identity) |
| 11 `jpm-a-rev-card-income` | JPMorgan card income is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.10 sd/sd (accounting) |
| 12 `jpm-a-prov-card-provision` | JPMorgan card provision is one part of JPMorgan provision for credit losses (provision for credit losses by portfolio (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | provision for credit losses | +0.60 sd/sd (accounting) |
| 13 `jpm-a-pretax-provision-for-credit-losses` | JPMorgan provision for credit losses is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +0.31 sd/sd (accounting) |
| 14 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 15 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |

Unresolved inputs: CECL scenario weights and the unemployment assumption (not disclosed in reviewed sources); card NCO rate guidance (found connected); card delinquency and charge-off rates (history) (found connected); card delinquency sensitivity to unemployment (not disclosed in reviewed sources); rewards costs as a share of interchange (found connected); roll rates from delinquency to charge-off (not disclosed in reviewed sources).

#### JPMorgan card growth and its reserve cost

**Trigger:** consumer card spending grows. **Endpoint:** JPMorgan pretax income (managed).

JPMorgan debit and credit card sales volume → [fees] JPMorgan card income → [balances] JPMorgan card loans? → [nii] JPMorgan average loans → [reserve] JPMorgan card reserve build? → [losses] JPMorgan card net charge-offs → JPMorgan interest income on loans → JPMorgan net revenue (managed) → JPMorgan interest income → JPMorgan net interest income → JPMorgan NII ex Markets → JPMorgan net revenue (managed) → JPMorgan card provision → JPMorgan card provision → JPMorgan provision for credit losses → JPMorgan pretax income (managed) → JPMorgan pretax income (managed)  (? marks a step whose size is unknown)

Growth pays twice and costs twice: net interchange and balance NII rise, but new balances need a day-one CECL reserve and charge off more dollars as they season.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [fees] `jpm-c-spend-cardincome` | Interchange is earned on each purchase, but most of it is paid back as rewards and partner payments, so net card income moves by a fraction of interchange (card networks, merchants, cardholders (rewards)) | the rewards rate holds; competitive card launches raise it; observable: interchange income, rewards costs and their ratio (workbook) | onset same month; build none; persists while volumes hold; recognized card income monthly | documented / documented / model / documented | rewards competition; interchange regulation | card income | +0.27 sd/sd (identity) |
| 2 [balances] `jpm-c-spend-cardloans` | Part of purchase volume revolves and becomes interest-earning card loans (cardholders) | revolve rate unchanged (transactors pay in full); observable: card loans against sales volume | onset 1-2 months; build quarters; persists while balances revolve; recognized average balances | documented / inferred / unknown / unknown | higher payment rates | card loans | unknown |
| 3 [nii] `jpm-a-loans-card-loans` | JPMorgan card loans is one part of JPMorgan average loans (average loans by portfolio); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | average loans | +0.22 sd/sd (accounting) |
| 4 [reserve] `jpm-c-cardloans-reserve` | Counter-path to card growth: CECL requires a lifetime loss reserve on new balances when booked, so growth itself builds reserves (seasonal balance growth in the second half does too) (JPMorgan (allowance process)) | loss rates and outlook unchanged; observable: card allowance against card loans (coverage ratio) | onset quarter of growth; build none; persists while balances hold; recognized provision that quarter | documented / documented / unknown / documented | a coverage release as the book seasons | card reserve build | unknown |
| 5 [losses] `jpm-c-cardloans-nco` | At a given loss rate, a larger card book produces more dollars of charge-offs, with a seasoning lag on new accounts (card borrowers) | bilinear: rate times balance; new vintages season over 18-24 months; observable: average card loans and charge-offs | onset 2-4 quarters; build seasoning; persists while held; recognized provision each quarter | documented / documented / model / inferred | growth concentrated in prime transactors | card net charge-offs | -0.40 sd/sd (identity) |
| 6 `jpm-c-loans-income` | A larger average loan book earns more interest at the prevailing yield (JPMorgan (lending)) | bilinear: balance times yield; growth funded by deposits rather than by wholesale debt; observable: average loans and loan interest income | onset same quarter; build as loans are drawn; persists while held; recognized interest income each quarter | documented / documented / model / documented | growth in low-spread loans (securities-based, markets lending) adds less | interest income on loans | +0.75 sd/sd (identity) |
| 7 `jpm-a-rev-card-income` | JPMorgan card income is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.10 sd/sd (accounting) |
| 8 `jpm-a-ii-loan-interest-income` | JPMorgan interest income on loans is one part of JPMorgan interest income (interest income by earning asset, managed (FTE)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | interest income | +0.49 sd/sd (accounting) |
| 9 `jpm-a-nii-interest-income` | JPMorgan interest income is one part of JPMorgan net interest income (firmwide NII, managed: interest income less interest expense); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net interest income | +1.57 sd/sd (accounting) |
| 10 `jpm.id.nii_ex_markets:jpmorgan.net_interest_income` | JPMorgan NII ex Markets = JPMorgan net interest income - JPMorgan Markets net interest income: JPMorgan net interest income is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.99 sd/sd (identity) |
| 11 `jpm-a-rev-nii-ex-markets` | JPMorgan NII ex Markets is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.69 sd/sd (accounting) |
| 12 `jpm-a-cardprov-card-reserve-build` | JPMorgan card reserve build is one part of JPMorgan card provision (card provision: net charge-offs plus reserve build (allowance roll-forward)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | card provision | +0.67 sd/sd (accounting) |
| 13 `jpm-a-cardprov-card-net-charge-offs` | JPMorgan card net charge-offs is one part of JPMorgan card provision (card provision: net charge-offs plus reserve build (allowance roll-forward)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | card provision | +0.67 sd/sd (accounting) |
| 14 `jpm-a-prov-card-provision` | JPMorgan card provision is one part of JPMorgan provision for credit losses (provision for credit losses by portfolio (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | provision for credit losses | +0.60 sd/sd (accounting) |
| 15 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 16 `jpm-a-pretax-provision-for-credit-losses` | JPMorgan provision for credit losses is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +0.31 sd/sd (accounting) |

Unresolved inputs: rewards costs as a share of interchange (found connected).

#### JPMorgan deal activity to investment banking fees

**Trigger:** deal and issuance activity rises. **Endpoint:** JPMorgan net income.

Deal and issuance activity → JPMorgan investment banking fees → JPMorgan net revenue (managed) → JPMorgan compensation expense? → JPMorgan noninterest expense → JPMorgan pretax income (managed) → JPMorgan pretax income (managed) → JPMorgan net income  (? marks a step whose size is unknown)

Fees are the market fee wallet times the bank's share of it; bankers' incentive pay takes a share. s12 is the mechanism itself (calibrated); no pipeline value is disclosed to stand between activity and fees.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `s12` | Advisory and underwriting fees are the market fee wallet times the bank's share of it; more completed deals and issuance raise the wallet (fees are recognized at completion or pricing) (issuers, acquirers and sponsors; CIB bankers) | wallet share roughly stable (its history is bound locally); observable: industry fee wallet (Dealogic-type data) and the bank's wallet share | onset at completion or pricing; build 1-2 quarters from announcement; persists while activity holds; recognized fees each quarter | documented / documented / assumption / broker | share loss; deals pulled when markets close; private credit replacing syndicated financing | investment banking fees | +0.60 sd/sd |
| 2 `jpm-a-rev-ib-fees` | JPMorgan investment banking fees is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.10 sd/sd (accounting) |
| 3 `jpm-c-ib-comp` | Offset: bankers' incentive pay accrues with fees (management (compensation accrual)) | accrual ratio held; observable: CIB compensation over CIB revenue | onset same quarter; build year-end true-up; persists annual; recognized compensation expense each quarter | documented / documented / unknown / inferred | fixed pay | compensation expense | unknown |
| 4 `jpm-a-exp-compensation-expense` | JPMorgan compensation expense is one part of JPMorgan noninterest expense (noninterest expense by type (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | noninterest expense | +0.67 sd/sd (accounting) |
| 5 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 6 `jpm-a-pretax-noninterest-expense` | JPMorgan noninterest expense is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +0.47 sd/sd (accounting) |
| 7 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |

Unresolved inputs: investment banking pipeline or backlog (not disclosed in reviewed sources); wallet share history (found connected).

#### JPMorgan expense inflation and operating leverage

**Trigger:** wage and price inflation. **Endpoint:** JPMorgan net income.

US core CPI → [wages] JPMorgan compensation expense? → [vendors] JPMorgan other noninterest expense? → JPMorgan noninterest expense → JPMorgan noninterest expense → JPMorgan pretax income (managed) → JPMorgan net income  (? marks a step whose size is unknown)

Operating leverage is revenue growth less expense growth: fixed pay and vendor costs rise with inflation, revenue-linked pay with revenue (Markets, IB and AWM paths).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [wages] `jpm-c-cpi-comp` | Wage inflation raises fixed compensation across the workforce (expense more negative), with a lag through annual pay reviews (employees; management) | a tight labour market; observable: average compensation per employee and headcount (workbook) | onset annual pay cycle; build a year; persists permanent; recognized compensation expense | inferred / inferred / unknown / unknown | headcount reduction and automation | compensation expense | unknown |
| 2 [vendors] `jpm-c-cpi-other` | Inflation raises occupancy, vendor and professional-services costs (expense more negative) (vendors and landlords) | contracts reprice; observable: occupancy and professional services expense | onset contract renewals; build a year; persists permanent; recognized expense | inferred / inferred / unknown / unknown | efficiency programmes | other noninterest expense | unknown |
| 3 `jpm-a-exp-compensation-expense` | JPMorgan compensation expense is one part of JPMorgan noninterest expense (noninterest expense by type (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | noninterest expense | +0.67 sd/sd (accounting) |
| 4 `jpm-a-exp-other-expense` | JPMorgan other noninterest expense is the residual of JPMorgan noninterest expense: what the named parts leave out, stated in its basis (noninterest expense by type (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | noninterest expense | +0.50 sd/sd (accounting) |
| 5 `jpm-a-pretax-noninterest-expense` | JPMorgan noninterest expense is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +0.47 sd/sd (accounting) |
| 6 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |

#### JPMorgan long-end yields to NII, fees and capital

**Trigger:** long-end Treasury yields rise (a steeper curve). **Endpoint:** JPMorgan CET1 ratio.

UST 10Y yield → [yield] JPMorgan securities new-purchase yield? → [prepayments] JPMorgan securities maturities and paydowns? → [marks] JPMorgan AOCI on AFS securities? → [mortgage] JPMorgan mortgage fees? → JPMorgan investment securities yield? → JPMorgan securities purchases? → JPMorgan investment securities yield? → JPMorgan interest income on investment securities → JPMorgan interest income → JPMorgan net interest income → JPMorgan NII ex Markets → JPMorgan net revenue (managed) → JPMorgan net revenue (managed) → JPMorgan pretax income (managed) → JPMorgan net income → JPMorgan CET1 capital? → JPMorgan CET1 capital → JPMorgan CET1 ratio  (? marks a step whose size is unknown)

One move, four parallel responses: new purchases earn more, mortgage prepayments slow (less cash to reinvest), AFS securities mark down into AOCI and CET1, and mortgage origination falls. jpm-c-ust10-nii (calibrated from the disclosed steeper-curve scenario) and s18 are the reduced forms on NII and the CET1 ratio; never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [yield] `jpm-c-ust10-npy` | Purchases are priced off the Treasury and agency MBS curve; a higher long end raises the yield of what is bought (market) | purchases in the tenors that moved (belly and long end); observable: yield on purchases (not disclosed); MBS current-coupon yields | onset immediate; build none; persists while rates hold; recognized none until purchased | inferred / inferred / unknown / inferred | purchases concentrated at the front end | new-purchase yield | unknown |
| 2 [prepayments] `jpm-c-ust10-prepay` | Higher long rates raise mortgage rates, so refinancing slows and MBS paydowns fall: less cash to reinvest just when reinvestment yields are higher (extension) (mortgage borrowers) | the book holds prepayable MBS; observable: MBS paydowns; prepayment speeds | onset 1-2 months; build 1-2 quarters; persists while rates hold; recognized cash flow | inferred / inferred / unknown / unknown | a book weighted to Treasuries and fixed maturities | securities maturities and paydowns | unknown |
| 3 [marks] `jpm-c-ust10-aoci` | Higher yields lower the market value of AFS securities; the after-tax loss goes to AOCI (HTM securities are not marked); income is unaffected (market) | AFS duration net of hedges; fair-value hedges offset part; observable: AOCI on AFS securities, quarterly | onset immediate; build none; persists pulls to par as securities near maturity; recognized quarter-end balance sheet | documented / documented / unknown / documented | short AFS duration, swaps, HTM classification | AOCI on AFS securities | unknown |
| 4 [mortgage] `jpm-c-ust10-mortgage` | Higher long rates raise mortgage rates, cutting refinancing and origination volume and production revenue; the servicing asset gains value, largely hedged (mortgage borrowers) | origination is rate sensitive (refinancing share); observable: mortgage origination volume and production margin; MSR valuation changes | onset 1-2 months; build 1-2 quarters; persists while rates hold; recognized fees each quarter | documented / inferred / unknown / unknown | MSR value gains (net of hedges) offset part | mortgage fees | unknown |
| 5 `jpm-c-npy-secyield` | The book yield moves toward the new-purchase yield in proportion to the share of the book replaced each year (Treasury and CIO) | purchases in the period (turnover); observable: securities yield | onset from settlement; build years (the book turns over slowly); persists to maturity; recognized accrual each quarter | inferred / inferred / unknown / inferred | low turnover | investment securities yield | unknown |
| 6 `jpm-c-cashflow-purchases` | The Treasury decides whether runoff is reinvested in securities, held as cash, or used to fund loans; reinvestment sets how fast the book reprices (Treasury and CIO (investment decision)) | liquidity and capital limits allow it; loans do not absorb the cash first; observable: purchases of HTM and AFS securities against runoff | onset execution dates; build unknown; persists holding period; recognized none until income accrues | documented / inferred / unknown / unknown | the Treasury holds cash at the Fed when short rates pay as well; AOCI risk appetite | securities purchases | unknown |
| 7 `jpm-c-purchases-secyield` | Each purchase cohort enters the book at its own yield, replacing the runoff's: the book yield rises when new-money yields exceed the yields of what matured (the sign holds only then) (Treasury and CIO) | new-purchase yield above the book yield of the runoff; observable: securities yield, quarterly | onset from settlement; build cohort by cohort; persists to maturity; recognized accrual each quarter | documented / inferred / unknown / inferred | new yields below book yields reverse the sign; AFS sales realize losses | investment securities yield | unknown; sign as stated while JPMorgan securities new-purchase yield is above 3.65, reversed otherwise |
| 8 `jpm-c-secyield-income` | Interest income on securities is the average balance times the book yield (Treasury and CIO) | bilinear: balance times yield; observable: securities yield and interest income | onset same quarter; build none; persists while held; recognized interest income each quarter | documented / documented / model / documented | a shrinking book | interest income on securities | +0.68 sd/sd (identity) |
| 9 `jpm-a-ii-securities-interest-income` | JPMorgan interest income on investment securities is one part of JPMorgan interest income (interest income by earning asset, managed (FTE)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | interest income | +0.23 sd/sd (accounting) |
| 10 `jpm-a-nii-interest-income` | JPMorgan interest income is one part of JPMorgan net interest income (firmwide NII, managed: interest income less interest expense); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net interest income | +1.57 sd/sd (accounting) |
| 11 `jpm.id.nii_ex_markets:jpmorgan.net_interest_income` | JPMorgan NII ex Markets = JPMorgan net interest income - JPMorgan Markets net interest income: JPMorgan net interest income is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.99 sd/sd (identity) |
| 12 `jpm-a-rev-nii-ex-markets` | JPMorgan NII ex Markets is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.69 sd/sd (accounting) |
| 13 `jpm-a-rev-mortgage-fees` | JPMorgan mortgage fees is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.03 sd/sd (accounting) |
| 14 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 15 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |
| 16 `jpm-c-aoci-cet1` | For this bank AOCI on AFS securities counts in CET1 capital, so an AFS mark moves regulatory capital one for one after tax (regulation (capital definition)) | AOCI included in CET1 (no opt-out for the largest banks); observable: CET1 capital roll-forward | onset quarter end; build none; persists until reversal or maturity; recognized quarterly capital reporting | documented / documented / unknown / documented | a rule change that filters AOCI out of CET1 | CET1 capital | unknown |
| 17 `jpm-c-ni-cet1` | Net income adds to retained earnings and so to CET1 capital (a flow into a stock: next period's capital is this period's plus earnings less distributions) (group) | accumulation over the period; preferred dividends come out first; observable: CET1 capital roll-forward | onset quarter end; build cumulative; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | distributions above earnings | CET1 capital | +0.42 sd/sd (stock-flow, accumulates per 365 days) |
| 18 `jpm-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets; more capital at the same RWA raises it (a ratio identity, linear only near current levels) (group) | RWA unchanged; observable: CET1 ratio, CET1 capital and RWA | onset quarter end; build none; persists while capital holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | +1.67 sd/sd (identity) |

Unresolved inputs: AFS duration after hedges and the AOCI sensitivity per 100bp (found not connected); MBS share and prepayment speeds (not disclosed in reviewed sources); allocation of purchases by tenor and product (not disclosed in reviewed sources); yield achieved on new purchases (not disclosed in reviewed sources).

#### JPMorgan volatility to Markets revenue

**Trigger:** market volatility rises. **Endpoint:** JPMorgan net income.

Rates and FX volatility → [ficc] JPMorgan Fixed Income Markets revenue? → [equities] JPMorgan Equity Markets revenue? → [levels] US equity market level? → [credit] US high-yield credit spread? → [rwa] JPMorgan risk-weighted assets? → JPMorgan markets revenue → JPMorgan markets revenue → JPMorgan Equity Markets revenue? → JPMorgan assets under management? → JPMorgan asset management fees → JPMorgan other revenue? → JPMorgan net revenue (managed) → JPMorgan net revenue (managed) → JPMorgan net revenue (managed) → JPMorgan compensation expense? → JPMorgan noninterest expense → JPMorgan pretax income (managed) → JPMorgan pretax income (managed) → JPMorgan net income → JPMorgan CET1 ratio  (? marks a step whose size is unknown)

Volatility lifts FICC and equities flow, but the same shock lowers equity levels (AUM fees), widens credit spreads (markdowns) and raises market-risk RWA; incentive pay takes a share of the revenue. s14 is the reduced form on Markets revenue and is never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [ficc] `jpm-c-vol-ficc` | More rate and FX volatility raises client hedging and repositioning, so flow volumes and bid-offer revenue rise in FICC; s14 is the reduced form on Markets revenue and is never added to this path (institutional and corporate clients; the desks) | orderly volatility with client activity; inventory risk contained; observable: FICC revenue against rates and FX volatility (MOVE, CVIX) and client volumes | onset same quarter; build none; persists while volatility lasts; recognized principal transactions daily | documented / broker / unknown / broker | disorderly markets: inventory losses and wider risk limits; low volatility at high volumes can still pay | Fixed Income Markets revenue | unknown |
| 2 [equities] `jpm-c-vol-equities` | Higher volatility lifts equity derivatives and cash trading volumes (institutional clients) | orderly markets; client risk appetite intact; observable: equities revenue against equity volatility and volumes | onset same quarter; build none; persists while volatility lasts; recognized principal transactions daily | documented / broker / unknown / broker | deleveraging cuts prime balances (jpm-c-equity-eqmkts) | Equity Markets revenue | unknown |
| 3 [levels] `jpm-c-vol-equityindex` | A volatility shock usually comes with falling equity prices (investors) | a risk-off shock rather than an upside repricing; observable: equity index against volatility | onset days; build weeks; persists while risk-off lasts; recognized market prices | inferred / inferred / unknown / unknown | volatility from a melt-up | US equity market level | unknown |
| 4 [credit] `jpm-c-vol-spread` | A volatility shock (a forced deleveraging) widens credit spreads as investors demand more compensation for risk (credit investors) | the shock is broad rather than rates-only; observable: high-yield spread against volatility indices | onset days; build weeks; persists while risk-off lasts; recognized market prices | inferred / inferred / unknown / unknown | central-bank liquidity | US high-yield credit spread | unknown |
| 5 [rwa] `jpm-c-vol-rwa` | Market-risk RWA scale with value-at-risk and stressed measures, so higher volatility and larger trading positions raise RWA (CIB Markets) | positions held through the volatility; observable: VaR and market-risk RWA | onset within the quarter; build VaR look-back windows; persists while volatility lasts; recognized quarterly capital reporting | documented / inferred / unknown / inferred | the desks cut risk | risk-weighted assets | unknown |
| 6 `jpm-a-mkts-fixed-income-markets` | JPMorgan Fixed Income Markets revenue is one part of JPMorgan markets revenue (CIB Markets revenue by product, managed (incl. Markets NII)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | markets revenue | +0.66 sd/sd (accounting) |
| 7 `jpm-a-mkts-equity-markets` | JPMorgan Equity Markets revenue is one part of JPMorgan markets revenue (CIB Markets revenue by product, managed (incl. Markets NII)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | markets revenue | +0.49 sd/sd (accounting) |
| 8 `jpm-c-equity-eqmkts` | Prime brokerage financing balances and cash volumes rise with equity market levels and hedge-fund leverage (hedge funds (prime clients)) | client leverage holds; observable: prime balances; gross leverage | onset same quarter; build none; persists while levels hold; recognized daily | broker / broker / unknown / unknown | forced deleveraging | Equity Markets revenue | unknown |
| 9 `jpm-c-equity-aum` | Market moves revalue client assets; AUM rises with equity and multi-asset markets, besides net flows (markets; clients (flows)) | the equity and multi-asset share of AUM; observable: AUM roll-forward: market/performance impacts versus net flows | onset immediate; build none; persists while levels hold; recognized fees on average AUM | documented / documented / unknown / documented | outflows in a sell-off; liquidity funds grow when markets fall | assets under management | unknown |
| 10 `jpm-c-aum-fees` | Asset management fees are average AUM times the fee rate (lower for liquidity and fixed income than for equity and alternatives) (AWM) | bilinear: AUM times fee rate; mix changes the rate; observable: asset management fees and the implied fee rate (workbook) | onset same quarter on average AUM; build none; persists while AUM holds; recognized fees monthly or quarterly | documented / documented / model / documented | mix shift to liquidity and passive; fee compression | asset management fees | +1.00 sd/sd (identity) |
| 11 `jpm-c-spread-markdown` | Counter-path: wider spreads mark down loans held for sale and unfunded bridge commitments (credit adjustments and other), before any credit loss (CIB (underwriting commitments)) | the bank holds committed but unsyndicated loans; observable: credit adjustments and other in CIB revenue; held-for-sale loans | onset quarter end; build none; persists reverses as loans are sold; recognized revenue that quarter | documented / inferred / unknown / inferred | hedges; small pipeline | other revenue | unknown |
| 12 `jpm-a-rev-markets-revenue` | JPMorgan markets revenue is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.30 sd/sd (accounting) |
| 13 `jpm-a-rev-asset-mgmt-fees` | JPMorgan asset management fees is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.24 sd/sd (accounting) |
| 14 `jpm-a-rev-other-revenue` | JPMorgan other revenue is the residual of JPMorgan net revenue (managed): what the named parts leave out, stated in its basis (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.27 sd/sd (accounting) |
| 15 `jpm-c-markets-comp` | Offset: incentive compensation accrues as a share of CIB revenue, so a part of any Markets revenue gain is paid away (expense more negative), the source of operating leverage being less than revenue growth (management (compensation accrual)) | accrual ratio held through the year; observable: CIB compensation over CIB revenue (workbook) | onset same quarter; build year-end true-up; persists annual; recognized compensation expense each quarter | documented / documented / unknown / inferred | fixed pay and deferrals; a year-end true-up | compensation expense | unknown |
| 16 `jpm-a-exp-compensation-expense` | JPMorgan compensation expense is one part of JPMorgan noninterest expense (noninterest expense by type (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | noninterest expense | +0.67 sd/sd (accounting) |
| 17 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 18 `jpm-a-pretax-noninterest-expense` | JPMorgan noninterest expense is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +0.47 sd/sd (accounting) |
| 19 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |
| 20 `jpm-c-rwa-ratio` | More risk-weighted assets at the same capital lower the CET1 ratio (group) | capital unchanged; observable: RWA and the CET1 ratio | onset quarter end; build none; persists while RWA holds; recognized quarterly capital reporting | documented / documented / model / documented | none (identity) | CET1 ratio | -1.55 sd/sd (identity) |

Unresolved inputs: AUM by asset class and market impact (found connected); CIB compensation ratio (found connected); FICC revenue sensitivity to volatility (not disclosed in reviewed sources); held-for-sale and bridge exposure (not disclosed in reviewed sources); market-risk RWA sensitivity to volatility (not disclosed in reviewed sources).

#### JPMorgan policy rate to net interest income

**Trigger:** the Fed raises the policy rate. **Endpoint:** JPMorgan net income.

Fed funds rate (midpoint) → [beta] JPMorgan interest-bearing deposit cost → [migration] JPMorgan noninterest-bearing deposit share? → [balances] JPMorgan average deposits? → [loans] JPMorgan loan yield? → [cash] JPMorgan yield on cash and deposits with banks → [markets] JPMorgan interest expense on Markets funding? → [markets_nii] JPMorgan Markets net interest income? → [unrepresented] JPMorgan net interest income → JPMorgan interest expense on deposits → JPMorgan noninterest-bearing deposits → JPMorgan noninterest-bearing deposits → JPMorgan interest-bearing deposits → JPMorgan interest-bearing deposits → JPMorgan interest expense on deposits → JPMorgan cash and deposits with banks? → JPMorgan interest income on cash and deposits with banks → JPMorgan interest income on cash and deposits with banks → JPMorgan interest income on loans → JPMorgan interest expense → JPMorgan interest expense → JPMorgan interest income → JPMorgan interest income → JPMorgan net interest income → JPMorgan net interest income → JPMorgan NII ex Markets → JPMorgan net revenue (managed) → JPMorgan NII ex Markets → JPMorgan pretax income (managed) → JPMorgan net income  (? marks a step whose size is unknown)

Parallel responses of one rate move: deposit costs follow by the beta (asymmetric, lagged) through interest-bearing balances (product and difference identities), cash at the Fed reprices one for one, balances migrate out of free funding, and Markets NII falls inside Markets revenue (excluded from NII ex Markets). m25 carries what the identities do not represent (floating loans, securities hedges, mix), sized jointly with the long end from the disclosed scenarios net of the represented channels.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [beta] `jpm-c-fed-depcost` | The bank reprices interest-bearing deposits by a fraction of a policy-rate move (the deposit beta); the fraction builds over several quarters and is higher for wholesale and wealth balances than for consumer checking (JPMorgan (deposit pricing, CCB, CIB and AWM)) | deposit competition and the bank's funding need set the pass-through; excess deposits keep it low, loan growth ahead of deposits raises it; observable: interest-bearing deposit cost against the fed funds rate, quarterly; cumulative beta since the cycle began | onset within the quarter of the move; build 2-4 quarters to the cumulative beta; persists while the policy rate holds; recognized interest expense each quarter | documented / documented / broker / broker | excess liquidity and low loan demand hold betas down; a deposit-share contest or quantitative tightening pushes them up; caps at the policy rate | interest-bearing deposit cost | +0.87 sd/sd; +0.87 sd/sd while Fed funds rate (midpoint) is above its construction level, +0.78 below |
| 2 [migration] `jpm-c-fed-nibshare` | Higher rates raise the cost of leaving cash idle, so clients move balances from noninterest-bearing into interest-bearing and investment products (deposit mix migration) (depositors (consumers, corporates, wealth clients)) | rates high enough that the opportunity cost of idle balances is noticed; operating balances are sticky; observable: noninterest-bearing deposits as a share of total deposits, quarterly | onset 1-2 quarters; build several quarters; persists reverses slowly when rates fall; recognized interest expense as balances migrate | documented / inferred / unknown / unknown | operating (transaction) balances that clients cannot move; deposit share gains | noninterest-bearing deposit share | unknown |
| 3 [balances] `jpm-c-fed-deposits` | Higher policy rates, with balance-sheet runoff, pull system deposits toward money-market funds and Treasury bills; the bank's balances grow more slowly unless it gains share (depositors and the Fed (balance-sheet policy)) | money-fund yields above deposit rates; reserves shrinking; observable: average deposits; industry deposit growth (H.8) | onset 1-2 quarters; build several quarters; persists while the gap lasts; recognized average balances | inferred / inferred / unknown / unknown | deposit share gains (the research expects them); flight to quality into large banks in stress | average deposits | unknown |
| 4 [loans] `jpm-c-fed-loanyield` | Floating-rate loans (card on prime, wholesale and commercial on SOFR) reprice within weeks of a policy move; fixed-rate mortgages and auto loans reprice only as they are originated (JPMorgan (lending)) | the floating share of the book and any receive-fixed swaps that convert it; observable: loan yield against SOFR and prime, quarterly | onset within the month; build one reset cycle; persists while the rate holds; recognized interest income each quarter | documented / documented / unknown / inferred | receive-fixed swaps on the loan book; loan-spread compression from competition | loan yield | unknown |
| 5 [cash] `jpm-c-fed-cashyield` | Reserves at the Fed earn the interest rate on reserve balances, which moves one for one with the policy rate the same day (Federal Reserve (IORB) and Treasury (liquidity)) | cash balances held at the Fed rather than invested; observable: yield on deposits with banks, quarterly | onset same day; build none; persists while the rate holds; recognized interest income each quarter | documented / documented / documented / documented | cash balance falls as deposits leave or are invested in securities | yield on cash and deposits with banks | +1.00 sd/sd |
| 6 [markets] `jpm-c-fed-mktfunding` | Repo, securities loaned and trading liabilities reprice at money-market rates, so a higher policy rate raises the interest paid to fund trading inventory (expense more negative) (CIB Markets (financing desks)) | inventory funded short; asset yields on the trading book reprice less than the funding; observable: Markets NII and Markets interest-bearing balances | onset within weeks; build none; persists while the rate holds; recognized interest expense each quarter | documented / inferred / unknown / inferred | the desk prices funding into client trades; the offset shows in principal transactions (Markets revenue is managed as a whole) | Markets funding expense | unknown |
| 7 [markets_nii] `jpm-c-fed-mktnii` | Counter-path: when funding reprices faster than the trading book, Markets NII falls, but the desks earn it back in principal transactions, so Markets revenue is roughly unchanged; NII ex Markets (firmwide NII less Markets NII, a difference identity) is unaffected by it, and net revenue counts Markets NII once, inside Markets revenue (CIB Markets) | Markets revenue is managed as a whole (NII and noninterest revenue together); observable: NII ex Markets against firmwide NII; Markets NII in the supplement | onset within weeks; build none; persists while the rate holds; recognized quarterly results | documented / inferred / unknown / inferred | a funding shock that the desks cannot pass on | Markets NII | unknown |
| 8 [unrepresented] `m25` | The part of the short-end response the identities do not carry: a higher policy rate raises firmwide NII through floating-rate loans, securities and swaps repricing and the funding mix; deposit costs (the beta through interest-bearing deposits) and cash at the Fed are represented exactly beside it in jpm.path.rates_nii (JPMorgan (balance sheet as a whole)) | deposit betas below one and lagged; balance sheet roughly static; observable: the company's earnings-at-risk scenarios (12-month pretax earnings, ex Markets) | onset within the quarter; build 2-4 quarters as deposit betas catch up; persists while the rate holds; recognized interest income and expense each quarter | documented / documented / inferred / inferred | receive-fixed swaps and a shrinking floating book; the size is the disclosed scenarios less the represented deposit and cash channels at construction levels, so it moves if those channels or levels change; the disclosure excludes Markets and assumes a static balance sheet | firmwide net interest income | +0.36 sd/sd; +0.36 sd/sd while Fed funds rate (midpoint) is above its construction level, +0.36 below |
| 9 `jpm-c-depcost-expense` | Interest expense on deposits is the interest-bearing balance times the deposit cost; a higher cost makes the (negative) expense larger (JPMorgan (deposit pricing)) | the change in expense is balance times rate change (bilinear): a fixed weight holds only near the current balance; observable: interest expense on interest-bearing deposits | onset same quarter; build none; persists while the cost holds; recognized interest expense each quarter | documented / documented / model / documented | a falling interest-bearing balance | interest expense on deposits | -1.00 sd/sd (identity) |
| 10 `jpm.id.nib_deposits:jpmorgan.nib_deposit_share` | JPMorgan noninterest-bearing deposits = 0.01 x JPMorgan average deposits x JPMorgan noninterest-bearing deposit share: JPMorgan noninterest-bearing deposit share is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.94 sd/sd (identity) |
| 11 `jpm.id.nib_deposits:jpmorgan.avg_deposits` | JPMorgan noninterest-bearing deposits = 0.01 x JPMorgan average deposits x JPMorgan noninterest-bearing deposit share: JPMorgan average deposits is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.38 sd/sd (identity) |
| 12 `jpm.id.ib_deposits:jpmorgan.avg_deposits` | JPMorgan interest-bearing deposits = JPMorgan average deposits - JPMorgan noninterest-bearing deposits: JPMorgan average deposits is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +1.07 sd/sd (identity) |
| 13 `jpm.id.ib_deposits:jpmorgan.nib_deposits` | JPMorgan interest-bearing deposits = JPMorgan average deposits - JPMorgan noninterest-bearing deposits: JPMorgan noninterest-bearing deposits is a deduction; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.57 sd/sd (identity) |
| 14 `jpm.id.deposit_expense:jpmorgan.ib_deposits` | JPMorgan interest expense on deposits = -0.01 x JPMorgan interest-bearing deposits x JPMorgan interest-bearing deposit cost: JPMorgan interest-bearing deposits is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.51 sd/sd (identity) |
| 15 `jpm-c-deposits-cash` | Deposits not lent out are held as cash at the Fed or invested in securities; a larger deposit base raises the cash balance (Treasury and CIO) | loan growth below deposit growth; liquidity rules (LCR) favour high-quality liquid assets; observable: deposits with banks and the loan-to-deposit ratio | onset same quarter; build none; persists while balances hold; recognized average balances | documented / inferred / unknown / inferred | Treasury invests the cash in securities instead (jpm-c-cash-purchases) | cash and deposits with banks | unknown |
| 16 `jpm-c-cash-income` | Interest income on cash is the balance times the rate on reserves (Treasury and CIO) | bilinear: balance times rate; observable: deposits with banks: balance, yield and income | onset same quarter; build none; persists while balances hold; recognized interest income each quarter | documented / documented / model / documented | IORB cut below market rates | interest income on cash | +1.00 sd/sd (identity) |
| 17 `jpm.id.cash_income:jpmorgan.cash_yield` | JPMorgan interest income on cash and deposits with banks = 0.01 x JPMorgan cash and deposits with banks x JPMorgan yield on cash and deposits with banks: JPMorgan yield on cash and deposits with banks is a factor; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.44 sd/sd (identity) |
| 18 `jpm-c-loanyield-income` | Interest income on loans is the average loan balance times the loan yield (JPMorgan (lending)) | bilinear: balance times yield; observable: loan yield and loan interest income | onset same quarter; build none; persists while the yield holds; recognized interest income each quarter | documented / documented / model / documented | loan balances shrink | interest income on loans | +0.77 sd/sd (identity) |
| 19 `jpm-a-ie-deposit-interest-expense` | JPMorgan interest expense on deposits is one part of JPMorgan interest expense (interest expense by funding source (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | interest expense | +0.60 sd/sd (accounting) |
| 20 `jpm-a-ie-markets-funding-expense` | JPMorgan interest expense on Markets funding is one part of JPMorgan interest expense (interest expense by funding source (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | interest expense | +0.60 sd/sd (accounting) |
| 21 `jpm-a-ii-loan-interest-income` | JPMorgan interest income on loans is one part of JPMorgan interest income (interest income by earning asset, managed (FTE)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | interest income | +0.49 sd/sd (accounting) |
| 22 `jpm-a-ii-cash-interest-income` | JPMorgan interest income on cash and deposits with banks is one part of JPMorgan interest income (interest income by earning asset, managed (FTE)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | interest income | +0.23 sd/sd (accounting) |
| 23 `jpm-a-nii-interest-income` | JPMorgan interest income is one part of JPMorgan net interest income (firmwide NII, managed: interest income less interest expense); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net interest income | +1.57 sd/sd (accounting) |
| 24 `jpm-a-nii-interest-expense` | JPMorgan interest expense is one part of JPMorgan net interest income (firmwide NII, managed: interest income less interest expense); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net interest income | +0.98 sd/sd (accounting) |
| 25 `jpm.id.nii_ex_markets:jpmorgan.net_interest_income` | JPMorgan NII ex Markets = JPMorgan net interest income - JPMorgan Markets net interest income: JPMorgan net interest income is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.99 sd/sd (identity) |
| 26 `jpm-a-rev-nii-ex-markets` | JPMorgan NII ex Markets is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.69 sd/sd (accounting) |
| 27 `jpm.id.nii_ex_markets:jpmorgan.markets_nii` | JPMorgan NII ex Markets = JPMorgan net interest income - JPMorgan Markets net interest income: JPMorgan Markets net interest income is a deduction; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | -0.31 sd/sd (identity) |
| 28 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 29 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |

Unresolved inputs: Markets NII rate sensitivity (not disclosed in reviewed sources); average interest-bearing deposits and their cost (found connected); cash balance by currency and the share at the Fed (not disclosed in reviewed sources); deposit balance sensitivity to the policy rate (not disclosed in reviewed sources); deposit beta by segment (consumer versus wholesale and wealth) (not disclosed in reviewed sources); migration elasticity of noninterest-bearing balances to rates (not disclosed in reviewed sources); share of floating-rate loans and swap hedges (not disclosed in reviewed sources); short-end-only earnings sensitivity on the firmwide (incl. Markets) basis (not disclosed in reviewed sources).

#### JPMorgan securities reinvestment

**Trigger:** securities mature or pay down while new-purchase yields differ from the book yield. **Endpoint:** JPMorgan net income.

JPMorgan investment securities → JPMorgan securities maturities and paydowns? → JPMorgan securities purchases? → JPMorgan investment securities yield? → JPMorgan interest income on investment securities → JPMorgan interest income → JPMorgan net interest income → JPMorgan NII ex Markets → JPMorgan net revenue (managed) → JPMorgan pretax income (managed) → JPMorgan net income → [capital] JPMorgan CET1 capital  (? marks a step whose size is unknown)

Existing securities -> cash released -> the Treasury's reinvestment decision -> book yield -> interest income -> NII -> net revenue -> earnings -> capital. Annual maturities and paydowns are disclosed; the ladder is not, so no new yield is applied to the whole book.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `jpm-c-sec-cashflow` | Maturities, calls and principal paydowns on held securities are the cash the Treasury can reinvest (Treasury and CIO) | securities actually mature or prepay in the period; observable: proceeds from paydowns and maturities of HTM and AFS securities (cash flow statement) | onset actual cash dates; build unknown; persists unknown; recognized not recognized in income until reinvested and earned | documented / documented / unknown / unknown | slower prepayments when mortgage rates rise (jpm-c-ust10-prepay) | securities maturities and paydowns | unknown |
| 2 `jpm-c-cashflow-purchases` | The Treasury decides whether runoff is reinvested in securities, held as cash, or used to fund loans; reinvestment sets how fast the book reprices (Treasury and CIO (investment decision)) | liquidity and capital limits allow it; loans do not absorb the cash first; observable: purchases of HTM and AFS securities against runoff | onset execution dates; build unknown; persists holding period; recognized none until income accrues | documented / inferred / unknown / unknown | the Treasury holds cash at the Fed when short rates pay as well; AOCI risk appetite | securities purchases | unknown |
| 3 `jpm-c-purchases-secyield` | Each purchase cohort enters the book at its own yield, replacing the runoff's: the book yield rises when new-money yields exceed the yields of what matured (the sign holds only then) (Treasury and CIO) | new-purchase yield above the book yield of the runoff; observable: securities yield, quarterly | onset from settlement; build cohort by cohort; persists to maturity; recognized accrual each quarter | documented / inferred / unknown / inferred | new yields below book yields reverse the sign; AFS sales realize losses | investment securities yield | unknown; sign as stated while JPMorgan securities new-purchase yield is above 3.65, reversed otherwise |
| 4 `jpm-c-secyield-income` | Interest income on securities is the average balance times the book yield (Treasury and CIO) | bilinear: balance times yield; observable: securities yield and interest income | onset same quarter; build none; persists while held; recognized interest income each quarter | documented / documented / model / documented | a shrinking book | interest income on securities | +0.68 sd/sd (identity) |
| 5 `jpm-a-ii-securities-interest-income` | JPMorgan interest income on investment securities is one part of JPMorgan interest income (interest income by earning asset, managed (FTE)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | interest income | +0.23 sd/sd (accounting) |
| 6 `jpm-a-nii-interest-income` | JPMorgan interest income is one part of JPMorgan net interest income (firmwide NII, managed: interest income less interest expense); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net interest income | +1.57 sd/sd (accounting) |
| 7 `jpm.id.nii_ex_markets:jpmorgan.net_interest_income` | JPMorgan NII ex Markets = JPMorgan net interest income - JPMorgan Markets net interest income: JPMorgan net interest income is a total; weight derived at the construction levels | unknown | onset same period; build none; persists identity; recognized unknown | inferred / inferred / inferred / inferred | unknown | unknown | +0.99 sd/sd (identity) |
| 8 `jpm-a-rev-nii-ex-markets` | JPMorgan NII ex Markets is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.69 sd/sd (accounting) |
| 9 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 10 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |
| 11 [capital] `jpm-c-ni-cet1` | Net income adds to retained earnings and so to CET1 capital (a flow into a stock: next period's capital is this period's plus earnings less distributions) (group) | accumulation over the period; preferred dividends come out first; observable: CET1 capital roll-forward | onset quarter end; build cumulative; persists permanent; recognized quarterly capital reporting | documented / documented / model / documented | distributions above earnings | CET1 capital | +0.42 sd/sd (stock-flow, accumulates per 365 days) |

Unresolved inputs: allocation of purchases by tenor and product (not disclosed in reviewed sources); maturity ladder and repricing schedule of the securities book (not disclosed in reviewed sources); securities maturities and paydowns (annual flows) (found connected).

#### JPMorgan wholesale credit cycle

**Trigger:** corporate credit spreads widen. **Endpoint:** JPMorgan net income.

US high-yield credit spread → [losses] JPMorgan wholesale net charge-off rate? → [reserve] JPMorgan wholesale reserve build? → [markdowns] JPMorgan other revenue? → [deals] Deal and issuance activity? → JPMorgan wholesale net charge-offs → JPMorgan wholesale loan provision → JPMorgan wholesale loan provision → JPMorgan provision for credit losses → JPMorgan investment banking fees → JPMorgan net revenue (managed) → JPMorgan net revenue (managed) → JPMorgan pretax income (managed) → JPMorgan pretax income (managed) → JPMorgan net income  (? marks a step whose size is unknown)

Spreads widen: reserves build first, charge-offs follow, held-for-sale loans mark down, and issuance and sponsor deals dry up (IB fees).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [losses] `jpm-c-spread-wnco` | Wider spreads signal corporate stress that turns into downgrades, nonaccruals and, a few quarters later, charge-offs on wholesale loans (lumpy, name by name) (corporate borrowers; CIB credit risk) | stress reaches borrowers in the book (real estate, leveraged sponsors, non-bank lenders); observable: wholesale nonaccrual loans and net charge-off rate | onset 2-4 quarters; build several quarters; persists credit cycle; recognized charge-offs when confirmed | inferred / inferred / unknown / unknown | collateral; syndication and risk transfer | wholesale net charge-off rate | unknown |
| 2 [reserve] `jpm-c-spread-wreserve` | Downgrades and a weaker macro outlook raise the lifetime expected loss on wholesale loans and commitments under CECL, built ahead of charge-offs (JPMorgan (allowance process)) | risk-rating migration or scenario change at quarter end; observable: wholesale allowance for loan losses and for lending-related commitments | onset quarter end; build 1-2 quarters; persists until released; recognized provision that quarter | documented / documented / unknown / inferred | overlays already held | wholesale reserve build | unknown |
| 3 [markdowns] `jpm-c-spread-markdown` | Counter-path: wider spreads mark down loans held for sale and unfunded bridge commitments (credit adjustments and other), before any credit loss (CIB (underwriting commitments)) | the bank holds committed but unsyndicated loans; observable: credit adjustments and other in CIB revenue; held-for-sale loans | onset quarter end; build none; persists reverses as loans are sold; recognized revenue that quarter | documented / inferred / unknown / inferred | hedges; small pipeline | other revenue | unknown |
| 4 [deals] `jpm-c-spread-deals` | Wider spreads raise acquisition-finance costs and close the high-yield and leveraged-loan markets, so issuance and sponsor deals fall (issuers and financial sponsors) | spreads wide enough to break deal economics; observable: high-yield and leveraged-loan issuance; announced sponsor M&A | onset weeks; build 1-2 quarters; persists while spreads stay wide; recognized fees at completion | inferred / inferred / unknown / unknown | private credit fills the gap (fees lost to the bank) | deal and issuance activity | unknown |
| 5 `jpm-c-wncorate-nco` | Wholesale net charge-offs are the loss rate times average wholesale loans (a charge: more negative) (corporate borrowers) | bilinear: rate times balance; observable: wholesale net charge-offs | onset same quarter; build none; persists while the rate holds; recognized provision each quarter | documented / documented / model / documented | recoveries | wholesale net charge-offs | -0.80 sd/sd (identity) |
| 6 `jpm-a-wprov-wholesale-net-charge-offs` | JPMorgan wholesale net charge-offs is one part of JPMorgan wholesale loan provision (wholesale loan provision: net charge-offs plus reserve build); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wholesale loan provision | +0.50 sd/sd (accounting) |
| 7 `jpm-a-wprov-wholesale-reserve-build` | JPMorgan wholesale reserve build is one part of JPMorgan wholesale loan provision (wholesale loan provision: net charge-offs plus reserve build); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | wholesale loan provision | +0.80 sd/sd (accounting) |
| 8 `jpm-a-prov-wholesale-provision` | JPMorgan wholesale loan provision is one part of JPMorgan provision for credit losses (provision for credit losses by portfolio (negative values)); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | provision for credit losses | +0.50 sd/sd (accounting) |
| 9 `s12` | Advisory and underwriting fees are the market fee wallet times the bank's share of it; more completed deals and issuance raise the wallet (fees are recognized at completion or pricing) (issuers, acquirers and sponsors; CIB bankers) | wallet share roughly stable (its history is bound locally); observable: industry fee wallet (Dealogic-type data) and the bank's wallet share | onset at completion or pricing; build 1-2 quarters from announcement; persists while activity holds; recognized fees each quarter | documented / documented / assumption / broker | share loss; deals pulled when markets close; private credit replacing syndicated financing | investment banking fees | +0.60 sd/sd |
| 10 `jpm-a-rev-ib-fees` | JPMorgan investment banking fees is one part of JPMorgan net revenue (managed) (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.10 sd/sd (accounting) |
| 11 `jpm-a-rev-other-revenue` | JPMorgan other revenue is the residual of JPMorgan net revenue (managed): what the named parts leave out, stated in its basis (managed net revenue by line: NII ex Markets, CIB Markets revenue (incl. Markets NII) and the fee lines); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net revenue (managed) | +0.27 sd/sd (accounting) |
| 12 `jpm-a-pretax-provision-for-credit-losses` | JPMorgan provision for credit losses is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +0.31 sd/sd (accounting) |
| 13 `jpm-a-pretax-net-revenue` | JPMorgan net revenue (managed) is one part of JPMorgan pretax income (managed) (managed pretax income: net revenue less noninterest expense less provision for credit losses); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | pretax income (managed) | +1.18 sd/sd (accounting) |
| 14 `jpm-a-ni-pretax-income` | JPMorgan pretax income (managed) is one part of JPMorgan net income (net income: managed pretax income less managed income tax); weight is its scale over the total's | managed basis, same period, USD; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net income | +1.52 sd/sd (accounting) |

Unresolved inputs: CECL scenario weights and the unemployment assumption (not disclosed in reviewed sources); held-for-sale and bridge exposure (not disclosed in reviewed sources); investment banking pipeline or backlog (not disclosed in reviewed sources); wallet share history (found connected); wholesale exposure by industry, incl. commercial real estate and non-bank lenders (not disclosed in reviewed sources).

## Validation

`tests/scenario/test_construction_jpmorgan.py` (loads sally_demo once; reads no client data):

- Structure: no `validate_construction` problems for the company; the seventeen compositions and thirteen paths exist;
  every path step has a transition, every uncalibrated step a sign and an "unknown" magnitude; the parallel responses
  of one rate move (deposit beta, mix migration, balances, floating loans, cash, Markets funding, Markets NII and the
  unrepresented remainder m25) are branches from the policy rate, and the long-end responses branches from the 10Y;
  m25 is the "unrepresented" branch of the rates path, sized net of the exact channels, and the other reduced forms
  (`jpm-c-ust10-nii`, s18, s14) are never steps of their structural paths.
- One driving view per total: the line view drives net revenue and the P&L bridge drives net income; the segment
  revenue and segment net income views are reconciling (no accounting links into their totals); the matrix
  `jpm.mx.revenue` holds lines as rows (driving) and segments as columns.
- Financial integrity: every part of a driving view has a fixed-weight accounting link equal to its native sd over the
  total's; one unit per view; the views that leave something out keep a residual; the priors of every additive view
  reconcile within 0.5%; Markets NII is counted once (NII ex Markets is a difference identity); the twelve identities
  have a term link per term and reconcile (`reconcile_identities` at the medians: all `ok`); the CET1 stock-flow has
  its three flow links and rolls forward (`reconcile_stock_flows` on a two-date series: `ok`; one dated level: no
  check); AFS marks reach CET1 and never income.
- Calibration: the only new causal sizes are the deposit beta (broker, asymmetric: lower in cuts than in hikes), the
  long-end NII effect and the cash yield's one-for-one repricing; m25 is asymmetric, magnitude "inferred"; s12, s14
  and s18 keep their sizes with magnitude "assumption"; the sign flip on reinvestment and the buyback threshold on the
  CET1 ratio are present; every missing input says whether the supplied material was searched.
- Generalization: an oil-price shock, for which no JPMorgan path was written, traced through every link (below).
- Delivery: compositions in `financial_bridge`, named paths as `business_construction` transmission paths, the line
  view's links as `accounting_identity`, uncalibrated links as `represented_uncalibrated` with their sign, m25's
  transition in the export; new node ids returned by `/v1/world-models/sally_demo/graph`, the construction and trace endpoints.

Sally's expected paths (`tests/scenario/test_sally_expected_paths.py`) still pass: `net_interest_income`,
`markets_revenue`, `ib_fees` and `cet1_ratio` keep their ids, and the policy rate still moves NII the way her research
expects.

**Generalization trace (oil-price shock).** `trace(g, "oil.brent", "jpmorgan")`: 118 routes, 100 reach a financial
endpoint, 20 of them with every step quantified (before the conversion: 116 routes, 89 reaching an endpoint).
Calibrated end to end: oil → US CPI → core CPI → Fed (m01, m05, m06) → m25 → firmwide NII and on through NII ex Markets
to net revenue; the Fed → deposit cost → deposit interest expense and Fed → cash yield → cash interest income chains
(now identities, so quantified); oil → Fed → 2Y → 10Y (m11, m12) → `jpm-c-ust10-nii` → NII and → s18 → CET1 ratio;
oil → growth → deals (m04, s09) → s12 → IB fees → net revenue. Represented with sign but no size: growth →
unemployment → card reserve build (CECL) and card charge-offs after delinquencies; CPI → wages and vendor costs; 10Y →
AFS marks → CET1 capital; 10Y → mortgage fees. It stops at the share price and, at the trace depth, inside the
securities, asset-management and wholesale-credit chains.

## Completion report

Outcomes map to the release outcomes: built and verified (**BV**), built but uncalibrated (**BU**), blocked by a named
input (**BL**), not built (**NB**). Updated after the conversion to the method extension (Oct 18).

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | Line view (driving), P&L bridge (driving), expense, credit, NII and loan views; 49 accounting links with sd-ratio weights | — |
| G02 | BV | Basis and export metric on every JPMorgan value | — |
| G03 | BV (inferred) | m25 is the remainder of the short-end response the identities do not carry, sized by least squares over the disclosed parallel and steeper-curve scenarios at two dates jointly with `jpm-c-ust10-nii`, after netting the represented deposit and cash channels; rises and falls sized separately | a firmwide (incl. Markets) short-end sensitivity; the netting depends on the construction levels |
| G04 | BV in part | `jpm.path.rates_nii`: noninterest-bearing and interest-bearing balances, deposit expense, cash income and loan income as identities; deposit beta and cash yield calibrated | floating-rate share (loan yield), migration and balance elasticities, Markets funding and Markets NII sensitivity |
| G05 | BV | `jpm-c-fed-depcost` calibrated from the broker's betas, asymmetric (cuts below hikes), lagged two quarters | segment betas (not disclosed) |
| G06 | BU (reinvestment) / BV (securities income identity, long-end reduced form) | securities income = book × yield; the yield's response to new purchases flips sign around the book yield; `jpm-c-ust10-nii` jointly calibrated | maturity ladder (runoff rate), purchase allocation and yields, MBS share, AFS duration |
| G07 | BV (structure) / BU (sensitivity) | NII ex Markets as a difference identity; Markets NII counted once inside Markets revenue | Markets NII rate sensitivity |
| G08 | BU | `jpm.comp.markets`, `jpm.path.markets`; s14 scoped | revenue sensitivity to volatility |
| G09 | BV (s12) / BU (offset) | `jpm.path.deals_ib`; s12 transition | pipeline/backlog |
| G10 | BV in part | card income = sales volume × net rate and card charge-offs = loans × loss rate (identities) | revolve rate; day-one reserve (CECL) |
| G11 | BV in part | asset management fees = AUM × fee rate (identity) | AUM market beta and fee mix |
| G12 | BV in part | charge-offs as identities (card, wholesale); credit views; two clocks | CECL scenarios and weights, roll rates, wholesale exposure by industry |
| G13 | BU | `jpm.comp.expense`, revenue-linked pay offsets, `jpm.path.expense_inflation` | variable-pay accrual rates |
| G14 | BV in part | CET1 stock-flow, CET1 ratio identity, buyback threshold on the ratio; s18 scoped | AOCI as a flow, management buffer, RWA density and capital-rule RWA |
| G15 | BV | segment and line-of-business views reconcile; segment revenue is the matrix's columns | matrix cells (the segment split of each line is not disclosed) |
| G16 | BV | objects present in the v4.1.4 export | — |
| G17 | BV | node ids served by the query, construction and trace endpoints | — |
| G18 | BV | reconciling views fold in the import; `bundles.py check` on the local baselines: OK, all items kept | — |

### Conversion: counts before and after

| Links touching JPMorgan's values | Before | After |
|---|---|---|
| Calibrated causal | 10 | 11 (adds `jpm-c-fed-cashyield`) |
| Accounting (fixed weights) | 55 | 49 |
| Identity (product, ratio, difference; weights derived) | 0 | 24 |
| Stock-flow | 0 | 3 |
| Uncalibrated (mechanism and sign) | 62 | 43 |
| Total | 127 | 130 |
| State-dependent (of the above) | 0 | 4 |

Of the 62 uncalibrated links: 13 became written identity links (deposit expense, cash income, loan income from both
balance and yield, securities income from both, card and wholesale charge-offs from rate and balance, AM fees, card
income, CET1 ratio from capital and RWA); 3 became stock-flow links (net income, dividends, buybacks into CET1
capital); 1 was redrawn and calibrated (Fed → cash yield, one for one); 2 were removed because an identity chain
replaced them (noninterest-bearing share → deposit expense now runs through the balance identities; card balances →
interest income through the loan composition and the loan-income identity). Another 11 identity links are generated
from the identities' terms (`<identity id>:<term>`). Accounting fell by 8 links from the two reconciling segment views
and 1 from the removed Markets NII elimination, and gained 3 from the new loan composition. State blocks: the deposit
beta and m25 (asymmetry), reinvestment (sign flip around the book yield), buybacks (threshold on the CET1 ratio).
Removed objects: the non-additive capital composition (now the stock-flow) and the Markets NII elimination value (now
Markets NII and NII ex Markets with a difference identity).

**Driving view per total.** Net revenue: `jpm.comp.revenue_by_line`; the segment view is the reconciling columns of
`jpm.mx.revenue`. Net income: `jpm.comp.net_income` (the P&L bridge); `jpm.comp.net_income_by_segment` is
`drives: false`. Every other total has one view.

**Reconciliation.** `check.py sally_demo --entities jpmorgan --reconcile --statistic median`: 0 flags across the
seventeen additive views, the twelve identities all `ok` (the largest gap 0.08%, securities income), the matrix `OK`
with its cells reported incomplete by design. With `--baselines <local baselines.json>`: 0 flags; two views keep an
unexplained difference within 0.5% (the line view, 0.01% of net revenue; credit costs by portfolio, 0.18% of the
provision) and every identity reconciles within 0.1% on the reported actuals. The CET1 stock-flow cannot be checked
against the baselines: they hold one dated capital level, and a roll-forward needs two. `bundles.py check` on the
baselines: OK, every item kept.

**Sources and citations.** `check.py --sources <local construction folder>`: 15 source ids resolve, 0 do not; 111
links and 87 values are cited; 0 material claims without a citation. No KEYWORD warnings.

**Inputs by status** (distinct inputs named in transitions): 11 found and connected, 2 found but not connected, 21 not
disclosed in the reviewed sources (each with the sources and corpus queries searched), 0 not yet reviewed.

**Forecast coverage (Sally's theses, forecast `coverage`).** The Fed-cut thesis (S-T2) now reaches JPMorgan through 25
quantified links (before: 15), adding the deposit-expense and cash-income identity chains, the cash yield, NII ex
Markets and the CET1 stock-flow and ratio; it excludes 19 uncalibrated ones (before: 22). To firmwide NII, 4 of its 10
routes are quantified (before: one in four): 2 through JPMorgan's own steps and 2 through summary links only (m25,
`jpm-c-ust10-nii`). Of the 16 own steps on those routes, 6 are quantified (37.5%); the rest wait on an uncalibrated
step upstream (the mix migration and deposit balances feeding the balance identities, the floating-loan yield, cash
allocation, Markets funding). Inputs blocking a size: 8 not disclosed, 2 found and connected, 2 found but not
connected. The volatility theses (S-T1, S-T3) are unchanged: one route in four to Markets revenue is quantified, through
the summary link s14 only; its two own steps (the Markets product split) are reached by no quantified route, and the
seven volatility branches stay excluded.

**Calculation coverage by path (own steps).** "Calculated" are calibrated causal steps; "exact" are accounting,
identity and stock-flow steps, which carry a size at weights derived from the levels; uncalibrated steps carry a sign
only and are excluded by any forecast that reaches them. The summary links beside the paths (m25 inside the rates
path as its remainder; `jpm-c-ust10-nii`, s18, s14, s12 beside theirs) are listed where they apply.

| Path | Calculated | Exact (accounting / identity / stock-flow) | Excluded: uncalibrated, with sign |
|---|---|---|---|
| `jpm.path.rates_nii` | `jpm-c-fed-depcost`, `jpm-c-fed-cashyield`, m25 | 9 / 11 / 0 | `jpm-c-fed-nibshare` (−), `jpm-c-fed-deposits` (−), `jpm-c-fed-loanyield` (+), `jpm-c-fed-mktfunding` (−), `jpm-c-fed-mktnii` (−), `jpm-c-deposits-cash` (+) |
| `jpm.path.securities_reinvestment` | none | 5 / 2 / 1 | `jpm-c-sec-cashflow` (+), `jpm-c-cashflow-purchases` (+), `jpm-c-purchases-secyield` (+, flips below the book yield) |
| `jpm.path.long_end` | none on the path; `jpm-c-ust10-nii` and s18 beside it | 6 / 3 / 1 | `jpm-c-ust10-npy` (+), `jpm-c-ust10-prepay` (−), `jpm-c-ust10-aoci` (−), `jpm-c-ust10-mortgage` (−), `jpm-c-npy-secyield` (+), `jpm-c-cashflow-purchases` (+), `jpm-c-purchases-secyield` (+), `jpm-c-aoci-cet1` (+) |
| `jpm.path.markets` | none on the path; s14 beside it | 9 / 2 / 0 | `jpm-c-vol-ficc` (+), `jpm-c-vol-equities` (+), `jpm-c-vol-equityindex` (−), `jpm-c-vol-spread` (+), `jpm-c-vol-rwa` (+), `jpm-c-equity-eqmkts` (+), `jpm-c-equity-aum` (+), `jpm-c-spread-markdown` (−), `jpm-c-markets-comp` (−) |
| `jpm.path.deals_ib` | s12 | 5 / 0 / 0 | `jpm-c-ib-comp` (−) |
| `jpm.path.card_credit` | none | 7 / 2 / 0 | `jpm-c-gdp-unemp` (−), `jpm-c-gdp-spend` (+), `jpm-c-unemp-delinq` (+), `jpm-c-unemp-cardreserve` (−), `jpm-c-unemp-spend` (−), `jpm-c-delinq-nco` (+) |
| `jpm.path.card_growth` | none | 10 / 4 / 0 | `jpm-c-spend-cardloans` (+), `jpm-c-cardloans-reserve` (−) |
| `jpm.path.wholesale_credit` | s12 (the deal branch) | 8 / 1 / 0 | `jpm-c-spread-wnco` (+), `jpm-c-spread-wreserve` (−), `jpm-c-spread-markdown` (−), `jpm-c-spread-deals` (−) |
| `jpm.path.asset_management` | none | 7 / 1 / 0 | `jpm-c-equity-aum` (+), `jpm-c-equity-eqmkts` (+), `jpm-c-amfees-comp` (−) |
| `jpm.path.expense_inflation` | none | 4 / 0 / 0 | `jpm-c-cpi-comp` (−), `jpm-c-cpi-other` (−) |
| `jpm.path.capital_payout` | none | 0 / 1 / 3 | `jpm-c-ni-dividends` (+), `jpm-c-ratio-buybacks` (+, only above the threshold) |
| `jpm.path.capital_requirements` | none | 0 / 1 / 1 | `jpm-c-req-buybacks` (−) |
| `jpm.path.balance_sheet_growth` | none | 10 / 5 / 1 | `jpm-c-loans-wreserve` (−), `jpm-c-loans-rwa` (+) |

Before the conversion the only calculated step on a path was the deposit beta (to the deposit cost, where the chain
stopped); the balance-times-rate, ratio and capital steps were all excluded.

**What a downstream agent can now trace or calculate.** Managed net revenue as NII ex Markets, Markets revenue and the
fee lines, on to pretax and net income; segment revenue and net income reconciled, never driven; NII by earning asset
and funding source with each line a balance times a rate; a policy-rate move on NII through the deposit beta
(asymmetric, lagged) into deposit expense, through cash at the Fed into cash income, and through m25 for the rest;
charge-offs as loans times loss rates; AM fees and card income as volume times rate; CET1 capital accumulating net
income less payout, and the CET1 ratio as capital over RWA; buybacks gated by the ratio; and, as signed mechanisms,
everything listed in the path table.

**What still cannot be expressed.**

1. **Balance-sheet allocation.** Cash is what deposits leave after loans, securities and other uses, a Treasury
   decision; it is neither a product nor a difference of represented values (`jpm-c-deposits-cash` stays signed).
2. **Undisclosed factors.** Securities runoff = book × runoff rate, RWA = exposures × risk density, Markets funding =
   balance × money-market rate: the identity form exists, but the runoff rate, the loans' risk density and the Markets
   funding balance are not disclosed, so writing the product would invent a factor.
3. **A level feeding a stock.** AOCI is held as a level; CET1 moves by its change. A stock-flow takes flows, so the
   AOCI link stays a signed causal link: the method has no "change of a level" term.
4. **CECL.** The reserve build follows the change in the economic forecast and the scenario weights, not a level; the
   day-one reserve on new card balances needs lifetime loss rates. Neither is a product, threshold or asymmetry of
   represented values.
5. **The roll-forward cannot be checked.** The stock-flow is defined, but the baselines hold one dated CET1 level;
   `reconcile_stock_flows` needs two.
6. **Matrix cells.** The matrix holds lines × segments, but the segment split of each line is not disclosed (only NII
   and noninterest revenue by segment), so the cells are not built and drivers cannot attach to them.
7. **m25 depends on construction levels.** It is the disclosed scenarios less the represented channels evaluated at
   the construction balances and betas; when those levels move, the remainder should be re-solved
   (`calibrate.py --disclosure`), and nothing does that automatically. The disclosure basis (12-month pretax earnings
   ex Markets, static balance sheet) is still not the basis of any one value.
8. **Timing on uncalibrated links** still carries no weight, so the CECL-now versus charge-offs-later clocks show in
   structure but not in a forecast.

## What the method could not express for a bank

This is the feedback the build was for. The method carried over (gap register, compositions, transitions, paths,
counter-paths, evidence, calibration from disclosure, generalization trace), but a bank's economics are mostly
identities that are not sums, and the method's only identity was "a part adds to its total".

**Status after the conversion (Oct 18).** The method extension answered items 1–6 and 8 below, and the construction
now uses each answer: product identities (1), the CET1 ratio identity (2), the CET1 stock-flow (3), one driving view
per total with the segment views reconciling and the lines × segments matrix (4), asymmetric, threshold and sign-flip
responses (5), joint least squares over the disclosed scenarios with separate rises and falls (6), and reconciling
views that the import keeps (8). What remains is listed under "What still cannot be expressed" in the
[completion report](#completion-report). The original findings follow as written.

1. **Products of two states.** NII is Σ balance × rate; charge-offs are loss rate × loans; deposit expense is
   balance × cost; AM fees are AUM × fee rate. Both inputs are often known (the workbook has every balance and yield),
   yet the step cannot be an accounting link (fixed weight on one source) and is not a statistical effect either, so
   it is held as uncalibrated: a calculable quantity the model cannot calculate. Needed: a product (bilinear) identity
   link, linearized at the current levels and re-linearized as they move. This one gap accounts for most of the 62
   uncalibrated links.
2. **Ratios.** The CET1 ratio (capital / RWA), NIM, the efficiency ratio and NCO rates are ratio identities; the model
   can only say "capital up, ratio up" with a sign. Needed: a ratio identity link.
3. **Stocks and flows.** CET1 capital, the loan-loss allowance and AUM accumulate (next period = this period + flows).
   An accounting link is a same-period part of a total, so earnings, buybacks, dividends and AOCI enter capital as
   signed causal links and a non-additive composition. Needed: an accumulation link (flow into stock with a period).
4. **Cross-classified results.** The P&L is a matrix (segments × lines). A value may sit in one additive view, so the
   driven line view and the segment view both total net revenue but only one can be driven; the segment views stay
   reconciled but undriven. Markets NII sits in two lines (firmwide NII and Markets revenue): it had to be modelled as a
   separate negative "elimination" value with its own causal driver, and the company's guided measure, NII ex
   Markets, cannot be a value at all. Needed: a matrix composition that reconciles rows and columns, with drivers
   attached to cells.
5. **State-dependent and asymmetric responses.** The deposit beta differs between hikes and cuts and rises with the
   rate level; the disclosed earnings sensitivity is asymmetric (up versus down); the reinvestment sign flips when new
   yields fall below book yields; buybacks stop at a requirement threshold. A link has one linear effect and a text
   breaker; the moderator forms that exist in the interaction model (threshold, multiplicative) are not reachable from
   the construction schema or `calibrate.py`.
6. **Scenario disclosures.** Banks disclose earnings-at-risk as scenarios (parallel shift, steeper curve) on 12-month
   pretax earnings of a static balance sheet, ex Markets. `calibrate.py` takes one source change and one target change;
   splitting a parallel scenario into its short- and long-end parts is an inference outside the tool, and the basis
   (pretax earnings ex Markets) does not match any one value.
7. **Two clocks in one account.** CECL books the expected loss when the outlook changes; charge-offs arrive quarters
   later through delinquency roll rates. Both are represented, but timing on an uncalibrated link carries no weight, so
   the model cannot show the front-loaded provision versus the lagged loss in a forecast.
8. **Importing a results release.** A bank's results report the segment and line views on the same day; the overlap
   guard folds one view per total and day, so a full set of actuals can never be imported for both. Worse, the guard
   currently drops every composition part touched that day, not only the overlapping total's other views (in
   `intake/overlap.py`, `resolve` skips signals not in the kept view without checking that they belong to that total):
   about 70 of 79 baseline items are held back, against 6 under the documented rule. A one-line condition (drop a
   signal only if one of its views is a view of the overlapping total) restores the documented behaviour; it is shared
   code and was not edited here.
9. **The world lacked a credit cycle.** Sally's world had no unemployment rate, credit spread or US equity level; they
   were added (`us_economy.unemployment_rate`, `us_capital_markets.credit_spread`, `us_capital_markets.equity_index`),
   uncalibrated so no other company's output moves. Other bank builds may add the same macro values: a merge must
   keep one definition of each.
10. **Smaller frictions.** The view vocabulary has no credit or funding view (`credit` was used); costs must be held as
    negative values to keep weights positive; the managed-to-reported (FTE) conversion is a basis note, not an object;
    the trace stops at the first composition total and at eight links, so macro-origin routes look truncated.
