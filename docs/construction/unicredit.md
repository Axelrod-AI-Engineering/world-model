# UniCredit: business construction

<!-- toc -->
**Contents**

- [Gap register](#gap-register)
- [Audit before modifying](#audit-before-modifying)
- [Definitions and bases](#definitions-and-bases)
- [Readable view](#readable-view)
  - [Business composition](#business-composition)
  - [Identities](#identities)
  - [Stocks and flows](#stocks-and-flows)
  - [Matrix `ucg.mx.revenue`: ucg.comp.revenue_by_line x ucg.comp.revenue_by_division (the rows drive the total; ucg.comp.revenue_by_division reconciles)](#matrix-ucgmxrevenue-ucgcomprevenuebyline-x-ucgcomprevenuebydivision-the-rows-drive-the-total-ucgcomprevenuebydivision-reconciles)
  - [Operating and financial paths](#operating-and-financial-paths)
- [Validation](#validation)
- [Completion report](#completion-report)
- [Conversion round](#conversion-round)
- [What the method could not express for UniCredit](#what-the-method-could-not-express-for-unicredit)
<!-- /toc -->

The fourth build of the method and the second bank, after [JPMorgan](jpmorgan.md): a European bank reporting under IFRS
on its own reclassified income statement, by geographic division. Its economics are the deposit margin set by the ECB
deposit rate and Euribor (with a pass-through to deposit rates and a structural hedge of core deposits that reprices
with the long end), fees on market levels, cost of risk, CET1 capital and a distribution policy (cash dividends
and buybacks), the Italian sovereign book, and its stakes (Commerzbank, Alpha Bank) and the Russia wind-down.

The construction lives in `data/worlds/sally_demo/construction/unicredit.yaml` (values, links with their transitions, named paths, compositions; generated from composition specs so accounting weights are exact) plus light edits to the `unicredit` block of entities.yaml (features on two values) and to m28, s33, s34, s76 in interactions.yaml (transitions; sizes kept). This page is structure only: object ids, bases, categories, tests. The client-derived side stays local under `data/sally_data/construction/unicredit/` (`gap_evidence.md`, `sources.json`, `citations.json`, `baselines.json`, `baselines_divisions.json`, `baselines_all.json`, `estimates.json`, `input_search.*`, `reconciliation.*`, `coverage.json`, and the view with levels in `view/`).

Source ids used in transitions (each resolves locally in `sources.json` to a file, and in `citations.json` to the cell or page with the passage): `ucg.wb` the supplied company model workbook (reclassified P&L history by division, broker estimates, the company's disclosed sensitivities as recorded with their page); `ucg.co` company disclosures as recorded in the workbook (not read directly); `ucg.r1`–`ucg.r7` broker notes (`ucg.r6` read, not used); `ucg.peer` peer bank dashboard; `ucg.macro` an economics note; `ucg.pub` public business and accounting knowledge (IFRS 9, FVOCI in CET1, equity accounting, translation).

## Gap register

Written before the model was changed. "Internal" is the loaded sally_demo graph and its YAML; "export" is the v4.1.4
pack (036, state 432). UniCredit was not one of the reviewer's worked companies, so the export side is "not represented
in the inspected export" throughout. Categories: **MC** missing construction, **CAL** missing calibration, **MAP**
incorrect mapping, **EXP** export omission, **RET** retrieval omission. Outcomes are in the
[completion report](#completion-report).

| # | Gap (missing or incorrect structure) | Present now (internal / export) | Add or correct | Evidence or input needed | Conclusions affected | Test that shows it done | Cat. |
|---|---|---|---|---|---|---|---|
| G01 | No business composition: the pack jumps from the ECB to NII and from the Bund to the CET1 ratio; no revenue, cost, provision or profit | Internal: two values (`unicredit.net_interest_income`, `unicredit.cet1_ratio`), links m28, s33, s34, s68, s76, s79, s81 and the NII kind default to the share price; no compositions. Export: the same broad relations | The driven line view of revenue (`ucg.comp.revenue_by_line`), the P&L bridge to profit before tax and net profit (`ucg.comp.pretax`, `ucg.comp.net_profit`) | Reclassified P&L history and broker P&L (`ucg.wb`, `ucg.r4`, `ucg.r7`) | Any group revenue or earnings conclusion; "rates up is good" | `test_required_compositions_exist`, `test_composition_parts_have_fixed_weight_accounting_links`, `test_priors_reconcile_within_half_a_percent` | MC |
| G02 | Undefined bases: NII as reported versus restated quarters; standalone versus Commerzbank-consolidated estimates; fees with or without the net insurance result; CET1 before the Commerzbank consolidation | Internal: values without features. Export: metrics named by id suffix | `features.view/basis/metric` on both values and on every new one | Workbook definitions (`ucg.wb`) | Mixing bases moves NII and CET1 by the size of a consolidation | `test_values_name_their_basis` | MAP |
| G03 | m28 (ECB → NII) has no scope; its size is not tied to the disclosed parallel-shift NII sensitivity | Internal: calibrated, no transition | Keep id and size (Sally's expected paths); a transition naming it the reduced form of `ucg.path.rates_nii`, magnitude "assumption", with the cross-check against the disclosure | The split of the disclosed parallel sensitivity between the short end and the long end | Size of any ECB-driven NII change | `test_only_evidenced_links_carry_new_sizes`, `test_reduced_forms_are_never_steps_of_their_structural_paths` | MAP / CAL |
| G04 | NII drivers absent: Euribor, deposit pass-through and its lag, the sight-deposit mix, floating-rate loan repricing, the divisional split | Internal: none; no Euribor in the world | `euro_money_markets.euribor_3m`, operating states and `ucg.path.rates_nii` (parallel branches of one rate move) into NII by division | Pass-through, NII by division, deposits by division | Whether and when a hike raises NII | `test_shared_driver_responses_are_parallel_branches` | MC |
| G05 | Deposit pass-through size | Internal: none | Calibrate ECB → deposit cost from the company's pass-through, lagged | Company pass-through (`ucg.co` via `ucg.wb`) | NII path timing and size | `test_deposit_pass_through_is_calibrated_and_lags` | CAL |
| G06 | The structural hedge of core deposits and the long end: s76 unscoped; hedge notional, yield and maturity not represented | Internal: s76 only | `ucg.path.long_end`: hedge yield (calibrated from notional and maturity) into NII, FVOCI marks into CET1 | Hedge notional, yield, maturity (`ucg.co` via `ucg.wb`) | "Higher long rates lift NII" versus "hurt capital" | `test_hedge_roll_is_calibrated_from_the_disclosed_hedge`, `test_marks_reach_capital_not_income` | MC / CAL |
| G07 | The Italian sovereign book: BTP-Bund spread → FVOCI reserve → CET1; spread → funding cost; s33 unscoped | Internal: s33 (Bund → CET1 ratio) only; no BTP spread in the world | `btps.bund_spread_10y`, `ucg.path.sovereign_spread`; s33 scoped as the reduced form | FVOCI sovereign book size and duration | Capital in an Italian spread shock | `test_required_paths_exist`, `test_marks_reach_capital_not_income` | MC / MAP |
| G08 | Geographic divisions (Italy, Germany, Austria, Central & Eastern Europe, Russia, Group Corporate Centre) and their lines | Internal: none | Division views of revenue, NII, fees, costs, provisions and net profit; GCC as the residual | Divisional tables (`ucg.wb`) | Divisional mix and contribution | `test_division_views_are_separate_from_the_driven_view` | MC |
| G09 | Fees on market levels (investment fees on assets under management and custody) | Internal: none | `ucg.path.fees_markets` from `europe_capital_markets.equity_index` into fees by division | Investment-fee share, market beta | Fee forecasts | `test_required_paths_exist` | MC |
| G10 | Cost of risk and the credit cycle: unemployment, default rates, IFRS 9 overlays | Internal: none; no euro-area unemployment or GDP in the world | `euro_economy.gdp_growth`, `euro_economy.unemployment_rate`; provisions by division; `ucg.path.credit_cycle` with the overlay counter-path | Cost-of-risk guidance (found), unemployment sensitivity, overlay stock | Any recession conclusion | `test_overlays_absorb_before_provisions_rise` | MC / CAL |
| G11 | Costs and inflation | Internal: none | Costs by division; `ucg.path.cost_inflation` | Cost guidance (found), wage indexation | Operating leverage | `test_required_paths_exist` | MC |
| G12 | Capital and distribution: CET1 capital, RWA, management target, the ordinary payout split between cash dividends and buybacks; s34 unscoped | Internal: `cet1_ratio`, s33, s34 | Capital values; `ucg.path.capital_distribution`, `ucg.path.capital_requirements`; non-additive `ucg.comp.capital_roll_forward`; additive `ucg.comp.distributions` | Payout policy, target range, MDA requirement (found) | Distribution capacity | `test_capital_is_a_stock_with_flows_not_an_additive_view`, `test_distributions_split_into_dividends_and_buybacks` | MC / MAP |
| G13 | Stakes and M&A: Commerzbank (equity-accounted income; control and full consolidation with a CET1 cost), Alpha Bank, other equity investments | Internal: none | `ucg.comp.equity_investments`, stake state, `ucg.path.commerzbank` | Stake size, consolidation CET1 impact (found) | Distributions and the earnings basis after control | `test_commerzbank_consolidation_reaches_capital_and_distributions` | MC |
| G14 | Russia wind-down: RUB translation, the CET1 at risk in an extreme-loss case, the partial sale | Internal: none; no EUR/RUB in the world | `eur_rub.rate`; Russia values in the division views; `ucg.path.russia` | Maximum CET1 loss (found), RUB sensitivity | Capital tail risk | `test_required_paths_exist` | MC |
| G15 | Loan growth and RWA growth | Internal: none | `ucg.path.loan_growth` | Loan growth guidance relative to nominal GDP | Volume-driven NII; RWA inflation | `test_required_paths_exist` | MC |
| G16 | New objects absent from the export | Export: none | Transitions in relationship properties, `financial_bridge`, `business_construction` paths | none | Downstream agent context | `test_new_objects_reach_the_export` | EXP |
| G17 | New node ids not retrievable | Internal API: none | `/v1/world-models/sally_demo/graph`, `…/entities/unicredit/construction` and its traces | none | Agent retrieval | `test_new_objects_reach_the_api` | RET |
| G18 | Estimates on two bases (standalone and Commerzbank-consolidated) and a restated FY2025 NII; a consolidation is a change of basis, not a driver | Internal: one NII value, no basis | Baselines on one basis (standalone, as reported); the consolidation as a stake state with signed effects | A basis-switch object (not in the method) | Any forecast spanning the consolidation date | listed as blocked | MAP / RET |

## Audit before modifying

| Requirement or object | Class | Controlling object | Action |
|---|---|---|---|
| Identity, aliases, kind, memberships, share-price kind default (`unicredit`) | Already owned | entities.yaml `unicredit` | untouched |
| m28, s33, s34, s76 (statistical records on UniCredit's values) | Already owned → Modify lightly | interactions.yaml | ids, sizes and kernels kept; transitions added (scope, reduced form, evidence, unresolved inputs) |
| s68, s79, s81 and the NII → share price kind default | Do not touch | interactions.yaml, taxonomy | untouched |
| `net_interest_income`, `cet1_ratio` definitions | Modify lightly | entities.yaml | `features.view/basis/metric` added; ids and priors kept for Sally's expected paths |
| Compositions, operating states, connected paths, financial mappings, euro credit-cycle, money-market, sovereign-spread and RUB values, bindings | Missing | construction/unicredit.yaml; local sources, citations, baselines | built |
| Shared macro links (m03, m10, s05, s06, s52, s66, s67) and other banks' objects (AIB Group, JPMorgan) | Do not touch | interactions.yaml, entities.yaml | untouched; UniCredit paths start below them |

## Definitions and bases

- **Reclassified P&L** (`features.basis` "reclassified P&L"): UniCredit's own reclassified income statement under IFRS, in
  euros, standalone: Commerzbank is equity-accounted, not consolidated. Revenue is NII + fees and net insurance result +
  trading income + dividends and equity investments + other (residual). Profit before tax adds operating costs, loan
  loss provisions and other items (systemic charges, integration costs, gains on investments and disposals); stated net
  profit deducts tax and minorities, discontinued operations and AT1 coupons.
- **Divisions** (`features.basis` "division"): Italy, Germany, Austria, Central & Eastern Europe, Russia, with the Group
  Corporate Centre as the residual of every division view. The brief's Central and Eastern Europe split is not reported
  separately since the 2024 restatement; the build follows the disclosure. CEE and Russia are shown at constant FX.
  Corporate-centre NII and fees are not reported: they are the group less the divisions.
- **Fees** include the net insurance result, because the divisional tables combine them; the group fee line without
  insurance exists in the estimates and is kept apart there.
- **One driving view per total**: revenue is driven by line (`ucg.comp.revenue_by_line`: rates enter through NII by
  division, market levels through fees by division, the stakes through dividends and equity investments); the division
  view of revenue is the passive (column) view of the matrix `ucg.mx.revenue`, whose cells are divisional NII and fees.
  Net profit is driven through the P&L bridge (`ucg.comp.net_profit`); net profit by division reconciles
  (`drives: false`). Loan loss provisions are driven by the identity loans × cost of risk (`ucg.id.llp`); provisions by
  division reconcile.
- **Costs, provisions and tax are negative values**, so every part adds to its total with a positive weight. A cost
  link's sign "−" means "a larger charge".
- **Capital**: CET1 capital is the capital stock before the FVOCI reserve plus the reserve (`ucg.comp.cet1_capital`);
  the stock accumulates net profit and draws down distributions (`ucg.sf.core_cet1`, annual flows); the CET1 ratio is
  capital over RWA (`ucg.id.cet1_ratio`). Rouble translation moves the stock (signed, no form for a revaluation).
- **Distributions**: net profit times a cash payout ratio and a buyback payout ratio (`ucg.id.cash_dividends`,
  `ucg.id.ordinary_buybacks`; the two ratios add to the ordinary payout, `ucg.comp.payout`), plus extra buybacks from
  capital above the management target (a threshold with no disclosed size). Distributions are accrued against CET1.
- **Stakes**: Commerzbank's share of profit sits inside dividends and equity investments until control; at control
  (with regulatory approval) it is fully consolidated into every line and its RWA join the group's. That is a change of
  basis; the model holds it as a stake state with signed effects (`ucg-c-cbkstake-rwa`, a `state:` note).
- **Converted forms (conversion round)**: the steps first tagged `identity:`, `stock-flow:` and `matrix:` are now
  identities, a stock-flow and a matrix with derived weights; those that fit no form stay uncalibrated and their `note`
  says why (see [Conversion round](#conversion-round)).
- Fiscal year = calendar year. Priors are synthetic round levels; FY2025 baselines and their sources are local.

## Readable view

Generated by `uv run python scripts/construction/check.py sally_demo --entities unicredit` from the loaded model after the conversion round (the same objects the API serves at `/v1/world-models/sally_demo/entities/unicredit/construction`). A `?` marks a step whose size is unknown (uncalibrated). Levels are left out here; the local copy adds them.

109 links touch its values: 75 calibrated, 34 uncalibrated (represented, size unknown), 48 accounting, 16 identity, 2 stock-flow; 0 state-dependent; 106 carry a transition.

### Business composition

#### capital: CET1 capital: the capital stock before the FVOCI reserve plus the reserve (€bn)

| Part | Value |
|---|---|
| UniCredit CET1 capital before the FVOCI reserve | `unicredit.core_cet1_capital` |
| UniCredit FVOCI reserve on debt securities | `unicredit.fvoci_reserve` |
| **Total: UniCredit CET1 capital** | `unicredit.cet1_capital` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split: the reserve's marks enter capital at once; the stock moves with earnings and distributions (ucg.sf.core_cet1).

#### reporting segments: operating costs by division (negative values) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit Italy operating costs | `unicredit.italy_costs` |
| UniCredit Germany operating costs | `unicredit.germany_costs` |
| UniCredit Austria operating costs | `unicredit.austria_costs` |
| UniCredit Central & Eastern Europe operating costs | `unicredit.cee_costs` |
| UniCredit Russia operating costs | `unicredit.russia_costs` |
| Residual: UniCredit Group Corporate Centre operating costs | `unicredit.gcc_costs` |
| **Total: UniCredit operating costs** | `unicredit.operating_costs` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Costs are negative values, so every part adds with a positive weight.

#### capital: distributions for the year: cash dividends plus share buybacks (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit cash dividends | `unicredit.cash_dividends` |
| UniCredit share buybacks | `unicredit.buybacks` |
| **Total: UniCredit total distributions** | `unicredit.total_distributions` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split: the ordinary payout is a cash dividend and buybacks (each a stated share of net profit); extra buybacks distribute capital above target.

#### reporting segments: fees and net insurance result by division (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit Italy fees and net insurance result | `unicredit.italy_fees` |
| UniCredit Germany fees and net insurance result | `unicredit.germany_fees` |
| UniCredit Austria fees and net insurance result | `unicredit.austria_fees` |
| UniCredit Central & Eastern Europe fees and net insurance result | `unicredit.cee_fees` |
| UniCredit Russia fees and net insurance result | `unicredit.russia_fees` |
| Residual: UniCredit Group Corporate Centre fees and net insurance result | `unicredit.gcc_fees` |
| **Total: UniCredit fees and net insurance result** | `unicredit.fees_insurance` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Investment fees follow market levels; the corporate centre's residual is the group less the divisions.

#### credit: loan loss provisions by division (negative values) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit Italy loan loss provisions | `unicredit.italy_llp` |
| UniCredit Germany loan loss provisions | `unicredit.germany_llp` |
| UniCredit Austria loan loss provisions | `unicredit.austria_llp` |
| UniCredit Central & Eastern Europe loan loss provisions | `unicredit.cee_llp` |
| UniCredit Russia loan loss provisions | `unicredit.russia_llp` |
| Residual: UniCredit Group Corporate Centre loan loss provisions | `unicredit.gcc_llp` |
| **Total: UniCredit loan loss provisions** | `unicredit.loan_loss_provisions` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling: group provisions are loans times the cost of risk (ucg.id.llp); the divisional split is reported, not driven.

#### reporting segments: stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit profit before tax | `unicredit.profit_before_tax` |
| UniCredit income tax | `unicredit.income_tax` |
| Residual: UniCredit minorities, discontinued operations and other items after tax | `unicredit.other_below_pretax` |
| **Total: UniCredit net profit** | `unicredit.net_profit` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity; the residual holds minorities, the Russia disposal in discontinued operations, AT1 coupons and adjustments to stated profit.

#### reporting segments: stated net profit by division (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit Italy net profit | `unicredit.italy_net_profit` |
| UniCredit Germany net profit | `unicredit.germany_net_profit` |
| UniCredit Austria net profit | `unicredit.austria_net_profit` |
| UniCredit Central & Eastern Europe net profit | `unicredit.cee_net_profit` |
| UniCredit Russia net profit | `unicredit.russia_net_profit` |
| Residual: UniCredit Group Corporate Centre net profit | `unicredit.gcc_net_profit` |
| **Total: UniCredit net profit** | `unicredit.net_profit` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
Reconciling: net profit is driven through the P&L bridge (ucg.comp.net_profit); the divisional split is reported, not driven.

#### reporting segments: net interest income by division (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit Italy net interest income | `unicredit.italy_nii` |
| UniCredit Germany net interest income | `unicredit.germany_nii` |
| UniCredit Austria net interest income | `unicredit.austria_nii` |
| UniCredit Central & Eastern Europe net interest income | `unicredit.cee_nii` |
| UniCredit Russia net interest income | `unicredit.russia_nii` |
| Residual: UniCredit Group Corporate Centre net interest income | `unicredit.gcc_nii` |
| **Total: UniCredit net interest income** | `unicredit.net_interest_income` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
Rates act on the euro divisions (Italy, Germany, Austria) through loan yields and deposit costs; CEE prices off local policy rates (not in the world); the corporate centre's residual holds funding and the part of the hedge not allocated.

#### capital: ordinary payout ratio: cash dividends plus buybacks, each over net profit (pct)

| Part | Value |
|---|---|
| UniCredit cash dividend payout ratio | `unicredit.cash_payout_ratio` |
| UniCredit buyback payout ratio | `unicredit.buyback_payout_ratio` |
| **Total: UniCredit ordinary payout ratio** | `unicredit.payout_ratio` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An exact split: the payout policy states a cash share and a buyback share; the split differs between years.

#### reporting segments: profit before tax: revenue less operating costs less loan loss provisions, plus other items (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit revenue | `unicredit.revenue` |
| UniCredit operating costs | `unicredit.operating_costs` |
| UniCredit loan loss provisions | `unicredit.loan_loss_provisions` |
| Residual: UniCredit other charges and items before tax | `unicredit.other_pretax_items` |
| **Total: UniCredit profit before tax** | `unicredit.profit_before_tax` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
An identity: costs and provisions are negative values; the residual holds systemic charges, integration costs, gains on investments and disposals.

#### reporting segments: revenue by division (reclassified, IFRS; CEE and Russia at constant FX) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit Italy revenue | `unicredit.italy_revenue` |
| UniCredit Germany revenue | `unicredit.germany_revenue` |
| UniCredit Austria revenue | `unicredit.austria_revenue` |
| UniCredit Central & Eastern Europe revenue | `unicredit.cee_revenue` |
| UniCredit Russia revenue | `unicredit.russia_revenue` |
| Residual: UniCredit Group Corporate Centre revenue | `unicredit.gcc_revenue` |
| **Total: UniCredit revenue** | `unicredit.revenue` |

A reconciling view: its parts are observed and reconciled against the total but carry nothing into it, so it can be imported alongside the driving view without counting a change twice.
The passive (column) view of matrix ucg.mx.revenue: reconciled, not driven; divisional NII and fees reach it as cells.

#### product: revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS) (€bn/yr, fiscal year ending December)

| Part | Value |
|---|---|
| UniCredit net interest income | `unicredit.net_interest_income` |
| UniCredit fees and net insurance result | `unicredit.fees_insurance` |
| UniCredit trading income | `unicredit.trading_income` |
| UniCredit dividends and equity investments | `unicredit.dividends_equity_income` |
| Residual: UniCredit other revenue | `unicredit.other_revenue` |
| **Total: UniCredit revenue** | `unicredit.revenue` |

Parts add to the total on this basis only, and carry changes into it; other views of the same business overlap and are never added to it.
The driven view: rates enter through NII, market levels through fees, the stakes through equity investments. Not the division view (ucg.comp.revenue_by_division): never added to it. The residual holds other income and rounding.

### Identities

Each weight is derived from the values' levels and scales at construction (sd of the target per sd of the term), never estimated.

| Identity | Formula | Terms (weight, sd/sd) | Unit check |
|---|---|---|---|
| `ucg.id.cash_dividends` (product) | UniCredit cash dividends = 0.01 x UniCredit net profit x UniCredit cash dividend payout ratio | UniCredit net profit (factor, +0.690); UniCredit cash dividend payout ratio (factor, +0.690) | €bn/yr = €bn/yr x % x 0.01 |
| `ucg.id.cbk_income` (product) | UniCredit share of Commerzbank profit = 0.01 x UniCredit stake in Commerzbank x Commerzbank net profit (as UniCredit's stake earns it) | UniCredit stake in Commerzbank (factor, +0.667); Commerzbank net profit (as UniCredit's stake earns it) (factor, +0.333) | €bn/yr = % x €bn/yr x 0.01 |
| `ucg.id.cet1_ratio` (ratio) | UniCredit CET1 ratio = 100 x UniCredit CET1 capital / UniCredit risk-weighted assets | UniCredit CET1 capital (numerator, +1.667); UniCredit risk-weighted assets (denominator, -1.590) | % = €bn / €bn x 100 |
| `ucg.id.deposit_interest` (product) | UniCredit interest paid on commercial deposits = 0.01 x UniCredit commercial deposits x UniCredit commercial deposit cost | UniCredit commercial deposits (factor, +0.250); UniCredit commercial deposit cost (factor, +0.952) | €bn/yr = €bn x % x 0.01 |
| `ucg.id.hedge_income` (product) | UniCredit structural hedge income = 0.01 x UniCredit structural hedge notional x UniCredit structural hedge yield | UniCredit structural hedge notional (factor, +0.429); UniCredit structural hedge yield (factor, +0.893) | €bn/yr = €bn x % x 0.01 |
| `ucg.id.llp` (product) | UniCredit loan loss provisions = -0.0001 x UniCredit customer loans x UniCredit cost of risk | UniCredit customer loans (factor, -0.096); UniCredit cost of risk (factor, -0.703) | €bn/yr = - €bn x bp x 0.0001 (a charge, negative) |
| `ucg.id.loan_interest` (product) | UniCredit interest income on customer loans = 0.01 x UniCredit customer loans x UniCredit customer loan yield | UniCredit customer loans (factor, +0.600); UniCredit customer loan yield (factor, +1.000) | €bn/yr = €bn x % x 0.01 |
| `ucg.id.ordinary_buybacks` (product) | UniCredit share buybacks = 0.01 x UniCredit net profit x UniCredit buyback payout ratio | UniCredit net profit (factor, +0.259); UniCredit buyback payout ratio (factor, +0.575) | €bn/yr = €bn/yr x % x 0.01 |

### Stocks and flows

A flow held one sd above its level adds its weight to the stock every period: the stock accumulates it.

| Stock-flow | Roll-forward | Flows (weight per period, sd/sd) |
|---|---|---|
| `ucg.sf.core_cet1` | UniCredit CET1 capital before the FVOCI reserve (closing) = UniCredit CET1 capital before the FVOCI reserve (opening) + UniCredit net profit - UniCredit total distributions, per 365 days | UniCredit net profit (inflow, +0.460); UniCredit total distributions (outflow, -0.667) |

### Matrix `ucg.mx.revenue`: ucg.comp.revenue_by_line x ucg.comp.revenue_by_division (the rows drive the total; ucg.comp.revenue_by_division reconciles)

| | UniCredit Austria revenue | UniCredit Central & Eastern Europe revenue | UniCredit Group Corporate Centre revenue | UniCredit Germany revenue | UniCredit Italy revenue | UniCredit Russia revenue |
|---|---|---|---|---|---|---|
| UniCredit fees and net insurance result | `unicredit.austria_fees` | `unicredit.cee_fees` | `unicredit.gcc_fees` | `unicredit.germany_fees` | `unicredit.italy_fees` | `unicredit.russia_fees` |
| UniCredit net interest income | `unicredit.austria_nii` | `unicredit.cee_nii` | `unicredit.gcc_nii` | `unicredit.germany_nii` | `unicredit.italy_nii` | `unicredit.russia_nii` |

Lines drive revenue; divisions reconcile. NII and fees are the cells held (their divisional values); trading, dividends and other income by division are not represented, so a division's revenue is not complete from its cells.

### Operating and financial paths

#### UniCredit earnings to capital and distributions

**Trigger:** net profit rises. **Endpoint:** UniCredit total distributions.

UniCredit net profit → [capital] UniCredit CET1 capital before the FVOCI reserve → [dividends] UniCredit cash dividends → [buybacks] UniCredit share buybacks → UniCredit CET1 capital → UniCredit CET1 ratio → UniCredit share buybacks? → UniCredit total distributions → UniCredit total distributions → UniCredit CET1 capital before the FVOCI reserve  (? marks a step whose size is unknown)

Earnings build the capital stock (a stock-flow) and set the ordinary distribution (payout x net profit, split into a cash dividend and buybacks: exact products), which is accrued against capital; the ratio above target funds extra buybacks (a threshold, uncalibrated).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [capital] `ucg-c-np-cet1cap` | Net profit adds to CET1 capital as it is earned (after the accrual of distributions, which leaves through its own link) (UniCredit) | profit recognised in the period; observable: CET1 capital walk (organic generation) | onset quarter end; build none; persists accumulates; recognized CET1 at the quarter end | documented / documented / model / documented | losses | CET1 capital | +0.46 sd/sd (stock-flow, accumulates per 365 days) |
| 2 [dividends] `ucg-c-np-dividends` | The ordinary distribution is a fixed share of net profit; the cash dividend is the larger part in the current plan (UniCredit (board)) | the payout policy holds; observable: dividend per share and the accrual | onset accrued quarterly; build none; persists annual policy; recognized paid as interim and final dividends | guidance / guidance / model / documented | the regulator's distribution limits (MDA); a policy change | cash dividends | +0.69 sd/sd (identity) |
| 3 [buybacks] `ucg-c-np-buybacks` | The rest of the ordinary distribution is executed as share buybacks, subject to supervisory authorisation (UniCredit (board) and the ECB (authorisation)) | authorisation granted; capital above target; observable: buyback authorisations and execution | onset after authorisation; build over the programme; persists annual policy; recognized deducted from CET1 when accrued | guidance / guidance / model / documented | authorisation withheld; buyback cancelled to fund an acquisition | share buybacks | +0.26 sd/sd (identity) |
| 4 `ucg-a-cet1-core-cet1-capital` | UniCredit CET1 capital before the FVOCI reserve is one part of CET1 capital (CET1 capital: the capital stock before the FVOCI reserve plus the reserve); weight is its scale over the total's | same date; the FVOCI reserve counts in CET1 (no prudential filter) | onset quarter end; build none; persists identity; recognized CET1 at the quarter end | documented / documented / model / documented | unknown | CET1 capital | +1.00 sd/sd (accounting) |
| 5 `ucg-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (none (regulatory ratio)) | risk-weighted assets unchanged; observable: CET1 ratio | onset quarter end; build none; persists identity; recognized CET1 ratio at the quarter end | documented / documented / model / documented | none | CET1 ratio | +1.67 sd/sd (identity) |
| 6 `ucg-c-ratio-buybacks` | Capital above the management target is distributable: the bank adds excess-capital buybacks when the ratio sits above the target range, and stops them when it does not (UniCredit (board)) | state: only the excess over the management target range is distributed; below it, extra buybacks stop and organic generation rebuilds the buffer; observable: CET1 ratio against the target range; announced extra distributions | onset annual (with results); build none; persists while the excess lasts; recognized deducted from CET1 when announced | guidance / guidance / unknown / guidance | M&A uses the excess capital first (Commerzbank consolidation); supervisory authorisation | share buybacks | unknown |
| 7 `ucg-a-dist-cash-dividends` | UniCredit cash dividends is one part of UniCredit total distributions (distributions for the year: cash dividends plus share buybacks); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total distributions | +0.50 sd/sd (accounting) |
| 8 `ucg-a-dist-buybacks` | UniCredit share buybacks is one part of UniCredit total distributions (distributions for the year: cash dividends plus share buybacks); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total distributions | +0.80 sd/sd (accounting) |
| 9 `ucg-c-dist-cet1cap` | Distributions are accrued against CET1 as profit is earned (dividend accrual and the buyback deduction), so a larger distribution lowers capital (UniCredit (board)) | distribution accrued at the policy payout; observable: CET1 capital walk (distributions) | onset quarter end (accrual); build none; persists accumulates; recognized CET1 at the quarter end | documented / documented / model / documented | a buyback not executed is added back (cancellation) | CET1 capital | -0.67 sd/sd (stock-flow, accumulates per 365 days) |

Unresolved inputs: management buffer above requirements and the use of excess capital (found connected); ordinary payout ratio and its cash share (found connected).

#### UniCredit CET1 target to buybacks

**Trigger:** the management target or requirement rises. **Endpoint:** UniCredit CET1 ratio.

UniCredit CET1 management target → UniCredit share buybacks? → UniCredit total distributions → UniCredit CET1 capital before the FVOCI reserve → UniCredit CET1 capital → UniCredit CET1 ratio  (? marks a step whose size is unknown)

A higher target leaves less capital to distribute: extra buybacks shrink and the capital stock keeps more.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ucg-c-target-buybacks` | A higher management target or requirement raises the capital the bank keeps, so excess-capital buybacks shrink (UniCredit (board) and the ECB (SREP)) | the ratio near the target; observable: CET1 target and the MDA buffer | onset next distribution decision; build none; persists while the target holds; recognized deducted from CET1 when announced | guidance / inferred / unknown / inferred | a falling requirement; regulatory relief | share buybacks | unknown |
| 2 `ucg-a-dist-buybacks` | UniCredit share buybacks is one part of UniCredit total distributions (distributions for the year: cash dividends plus share buybacks); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total distributions | +0.80 sd/sd (accounting) |
| 3 `ucg-c-dist-cet1cap` | Distributions are accrued against CET1 as profit is earned (dividend accrual and the buyback deduction), so a larger distribution lowers capital (UniCredit (board)) | distribution accrued at the policy payout; observable: CET1 capital walk (distributions) | onset quarter end (accrual); build none; persists accumulates; recognized CET1 at the quarter end | documented / documented / model / documented | a buyback not executed is added back (cancellation) | CET1 capital | -0.67 sd/sd (stock-flow, accumulates per 365 days) |
| 4 `ucg-a-cet1-core-cet1-capital` | UniCredit CET1 capital before the FVOCI reserve is one part of CET1 capital (CET1 capital: the capital stock before the FVOCI reserve plus the reserve); weight is its scale over the total's | same date; the FVOCI reserve counts in CET1 (no prudential filter) | onset quarter end; build none; persists identity; recognized CET1 at the quarter end | documented / documented / model / documented | unknown | CET1 capital | +1.00 sd/sd (accounting) |
| 5 `ucg-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (none (regulatory ratio)) | risk-weighted assets unchanged; observable: CET1 ratio | onset quarter end; build none; persists identity; recognized CET1 ratio at the quarter end | documented / documented / model / documented | none | CET1 ratio | +1.67 sd/sd (identity) |

Unresolved inputs: management buffer above requirements and the use of excess capital (found connected).

#### UniCredit Commerzbank stake to earnings, capital and distributions

**Trigger:** UniCredit raises its Commerzbank stake or gains control. **Endpoint:** UniCredit total distributions.

UniCredit stake in Commerzbank → [earnings] UniCredit share of Commerzbank profit → [consolidation] UniCredit risk-weighted assets? → UniCredit dividends and equity investments? → UniCredit revenue → UniCredit profit before tax → UniCredit net profit → UniCredit share buybacks → UniCredit CET1 ratio → UniCredit share buybacks? → UniCredit total distributions  (? marks a step whose size is unknown)

Below control, a larger stake books more of Commerzbank's profit (stake x profit, exact) in the equity-investments line; at control, full consolidation moves Commerzbank into every line (a change of basis) and its RWA onto the balance sheet, which lowers the CET1 ratio and the capital left for buybacks.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [earnings] `ucg-c-cbkstake-income` | Equity-accounted income is the stake times the associate's net profit (UniCredit (M&A)) | state: equity-accounted while below control; at control the stake is consolidated line by line and this income disappears into the lines; observable: stake disclosures and the equity-investments line | onset on purchase; build as shares are bought; persists while held; recognized dividends and equity investments each quarter | documented / documented / model / documented | control and full consolidation (a basis change, not a driver) | UniCredit share of Commerzbank profit | +0.67 sd/sd (identity) |
| 2 [consolidation] `ucg-c-cbkstake-rwa` | A larger stake raises the capital deduction and risk weight of the holding; at control (with regulatory approval) Commerzbank is fully consolidated and its RWA join the group's, which lowers the CET1 ratio by the consolidation's announced impact (UniCredit (M&A) and the ECB (approval)) | state: below control, a holding risk-weighted or deducted; at control, full consolidation (a step change); observable: regulatory approval; announced CET1 impact of consolidation | onset at approval; build a step at consolidation; persists permanent; recognized RWA and CET1 at the quarter of consolidation | guidance / guidance / unknown / guidance | approval withheld; a partial sale of stakes | risk-weighted assets | unknown |
| 3 `ucg-c-cbkincome-divline` | UniCredit's share of Commerzbank's profit is booked in the dividends and equity investments line of revenue, beside Alpha Bank at equity and dividends from financial stakes; the split of the line is not disclosed, so this is a signed link, not an accounting part (none (equity accounting)) | state: equity-accounted while below control; observable: dividends and equity investments line | onset same quarter; build none; persists while equity-accounted; recognized revenue each quarter | documented / documented / unknown / documented | full consolidation moves Commerzbank out of this line into every line (a change of basis) | dividends and equity investments | unknown |
| 4 `ucg-a-rev-dividends-equity-income` | UniCredit dividends and equity investments is one part of UniCredit revenue (revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | revenue | +0.39 sd/sd (accounting) |
| 5 `ucg-a-pbt-revenue` | UniCredit revenue is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +1.12 sd/sd (accounting) |
| 6 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |
| 7 `ucg-c-np-buybacks` | The rest of the ordinary distribution is executed as share buybacks, subject to supervisory authorisation (UniCredit (board) and the ECB (authorisation)) | authorisation granted; capital above target; observable: buyback authorisations and execution | onset after authorisation; build over the programme; persists annual policy; recognized deducted from CET1 when accrued | guidance / guidance / model / documented | authorisation withheld; buyback cancelled to fund an acquisition | share buybacks | +0.26 sd/sd (identity) |
| 8 `ucg-c-rwa-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets, so RWA growth lowers it (none (regulatory ratio)) | CET1 capital unchanged; observable: CET1 ratio and RWA | onset quarter end; build none; persists identity; recognized CET1 ratio at the quarter end | documented / documented / model / documented | regulatory relief (e.g. the Danish compromise on insurance holdings) lowers RWA | CET1 ratio | -1.59 sd/sd (identity) |
| 9 `ucg-c-ratio-buybacks` | Capital above the management target is distributable: the bank adds excess-capital buybacks when the ratio sits above the target range, and stops them when it does not (UniCredit (board)) | state: only the excess over the management target range is distributed; below it, extra buybacks stop and organic generation rebuilds the buffer; observable: CET1 ratio against the target range; announced extra distributions | onset annual (with results); build none; persists while the excess lasts; recognized deducted from CET1 when announced | guidance / guidance / unknown / guidance | M&A uses the excess capital first (Commerzbank consolidation); supervisory authorisation | share buybacks | unknown |
| 10 `ucg-a-dist-buybacks` | UniCredit share buybacks is one part of UniCredit total distributions (distributions for the year: cash dividends plus share buybacks); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total distributions | +0.80 sd/sd (accounting) |

Unresolved inputs: Commerzbank net profit (not disclosed in reviewed sources); Commerzbank share of the dividends and equity investments line (not disclosed in reviewed sources); consolidation CET1 impact (found connected); management buffer above requirements and the use of excess capital (found connected); ordinary payout ratio and its cash share (found connected); stake share in Commerzbank (found connected).

#### UniCredit inflation to operating costs

**Trigger:** euro-area inflation rises. **Endpoint:** UniCredit net profit.

Euro area inflation → UniCredit Italy operating costs? → UniCredit Germany operating costs? → UniCredit Austria operating costs? → UniCredit operating costs → UniCredit operating costs → UniCredit operating costs → UniCredit profit before tax → UniCredit net profit  (? marks a step whose size is unknown)

Wage settlements and administrative contracts index to inflation with a lag.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ucg-c-cpi-italycosts` | Wage settlements and administrative contracts in Italy index to inflation with a lag, so higher inflation makes operating costs more negative (employees and suppliers in Italy) | collective agreements renegotiated; no offsetting efficiency; observable: staff and other administrative expenses | onset 2-4 quarters; build a year; persists permanent; recognized operating costs | inferred / inferred / unknown / unknown | efficiency programmes; headcount reductions | Italy operating costs | unknown |
| 2 `ucg-c-cpi-germanycosts` | Wage settlements and administrative contracts in Germany index to inflation with a lag, so higher inflation makes operating costs more negative (employees and suppliers in Germany) | collective agreements renegotiated; no offsetting efficiency; observable: staff and other administrative expenses | onset 2-4 quarters; build a year; persists permanent; recognized operating costs | inferred / inferred / unknown / unknown | efficiency programmes; headcount reductions | Germany operating costs | unknown |
| 3 `ucg-c-cpi-austriacosts` | Wage settlements and administrative contracts in Austria index to inflation with a lag, so higher inflation makes operating costs more negative (employees and suppliers in Austria) | collective agreements renegotiated; no offsetting efficiency; observable: staff and other administrative expenses | onset 2-4 quarters; build a year; persists permanent; recognized operating costs | inferred / inferred / unknown / unknown | efficiency programmes; headcount reductions | Austria operating costs | unknown |
| 4 `ucg-a-costs-italy-costs` | UniCredit Italy operating costs is one part of UniCredit operating costs (operating costs by division (negative values)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating costs | +0.50 sd/sd (accounting) |
| 5 `ucg-a-costs-germany-costs` | UniCredit Germany operating costs is one part of UniCredit operating costs (operating costs by division (negative values)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating costs | +0.35 sd/sd (accounting) |
| 6 `ucg-a-costs-austria-costs` | UniCredit Austria operating costs is one part of UniCredit operating costs (operating costs by division (negative values)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | operating costs | +0.20 sd/sd (accounting) |
| 7 `ucg-a-pbt-operating-costs` | UniCredit operating costs is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.21 sd/sd (accounting) |
| 8 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |

Unresolved inputs: wage indexation and cost sensitivity to inflation (not disclosed in reviewed sources).

#### UniCredit growth and unemployment to cost of risk

**Trigger:** euro-area growth slows and unemployment rises. **Endpoint:** UniCredit net profit.

Euro area real GDP growth → Euro area unemployment rate? → [defaults] UniCredit cost of risk? → [overlays] UniCredit credit overlays? → UniCredit loan loss provisions → UniCredit loan loss provisions? → UniCredit profit before tax → UniCredit net profit  (? marks a step whose size is unknown)

Unemployment raises defaults and stage migration (the cost of risk; provisions = loans x cost of risk, exact), while overlays held for this are released first and offset part of the rise (a counter-path).

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ucg-m-gdp-unemp` | Weaker output growth lowers hiring and raises unemployment with a lag (Okun's relation) (euro-area employers) | growth below potential for several quarters; observable: euro area unemployment rate, monthly | onset 2-3 quarters; build several quarters; persists until growth recovers; recognized labour statistics | inferred / inferred / unknown / inferred | labour hoarding and short-time work schemes | euro area unemployment | unknown |
| 2 [defaults] `ucg-c-unemp-cor` | Higher unemployment raises default rates and moves loans into stage 2 (lifetime expected loss), so the cost of risk rises; IFRS 9's forward-looking scenarios book part of it when the outlook changes, the rest as defaults arrive (borrowers (households, SMEs)) | unemployment above its trend for several quarters; observable: cost of risk, default rate and stage 2 share, quarterly | onset 1-2 quarters (scenario update); 2-4 quarters (defaults); build several quarters; persists until unemployment falls; recognized loan loss provisions each quarter | documented / documented / unknown / inferred | overlays are released first (ucg-c-unemp-overlays); collateral and state guarantees cap losses | cost of risk | unknown |
| 3 [overlays] `ucg-c-unemp-overlays` | Counter-path: the bank holds management overlays above model provisions; when the deterioration it provisioned for arrives, overlays are released or used, which offsets the first rise in provisions (UniCredit (risk management)) | overlay stock above zero; observable: overlay stock in the results presentation | onset 1-2 quarters; build as losses arrive; persists until the stock is used; recognized loan loss provisions (release) | documented / inferred / unknown / unknown | the stock is exhausted; the regulator asks to keep it | credit overlays | unknown |
| 4 `ucg-c-cor-llp` | Loan loss provisions are customer loans times the cost of risk, so a higher cost of risk makes them more negative (UniCredit (risk management)) | loan book held; observable: provisions and cost of risk | onset same quarter; build none; persists while the cost of risk holds; recognized loan loss provisions each quarter | documented / documented / model / documented | overlay releases offset the first rise (ucg-c-overlays-llp) | loan loss provisions | -0.70 sd/sd (identity) |
| 5 `ucg-c-overlays-llp` | A release of overlays is credited to the provision line, so a smaller overlay stock (a release) makes provisions less negative (UniCredit (risk management)) | release booked in the period; observable: provisions and the overlay stock | onset same quarter; build none; persists one-off per release; recognized loan loss provisions | documented / documented / unknown / documented | none | loan loss provisions | unknown |
| 6 `ucg-a-pbt-loan-loss-provisions` | UniCredit loan loss provisions is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +0.27 sd/sd (accounting) |
| 7 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |

Unresolved inputs: IFRS 9 scenario weights (not disclosed in reviewed sources); cost-of-risk sensitivity to unemployment (not disclosed in reviewed sources); overlay stock and its release policy (found connected).

#### UniCredit market levels to fees

**Trigger:** European equity markets rise. **Endpoint:** UniCredit net profit.

Europe equity index (Euro Stoxx 50) → UniCredit Italy fees and net insurance result? → UniCredit Germany fees and net insurance result? → UniCredit Austria fees and net insurance result? → UniCredit Central & Eastern Europe fees and net insurance result? → UniCredit fees and net insurance result → UniCredit fees and net insurance result → UniCredit fees and net insurance result → UniCredit fees and net insurance result → UniCredit revenue → UniCredit profit before tax → UniCredit net profit  (? marks a step whose size is unknown)

Market levels lift investment fees on assets under management and custody in each division.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ucg-c-equity-italyfees` | Investment fees on assets under management and custody in Italy rise with market levels (fees on average balances) and with client activity (clients and UniCredit Italy (wealth and asset distribution)) | the investment-fee share of fees; markets hold their level; observable: investment fees and assets under management in results presentations | onset same quarter; build as average balances reprice; persists while levels hold; recognized fee income each quarter | documented / documented / unknown / inferred | outflows in a sell-off; transactional and lending fees do not move with markets | Italy fees and net insurance result | unknown |
| 2 `ucg-c-equity-germanyfees` | Investment fees on assets under management and custody in Germany rise with market levels (fees on average balances) and with client activity (clients and UniCredit Germany (wealth and asset distribution)) | the investment-fee share of fees; markets hold their level; observable: investment fees and assets under management in results presentations | onset same quarter; build as average balances reprice; persists while levels hold; recognized fee income each quarter | documented / documented / unknown / inferred | outflows in a sell-off; transactional and lending fees do not move with markets | Germany fees and net insurance result | unknown |
| 3 `ucg-c-equity-austriafees` | Investment fees on assets under management and custody in Austria rise with market levels (fees on average balances) and with client activity (clients and UniCredit Austria (wealth and asset distribution)) | the investment-fee share of fees; markets hold their level; observable: investment fees and assets under management in results presentations | onset same quarter; build as average balances reprice; persists while levels hold; recognized fee income each quarter | documented / documented / unknown / inferred | outflows in a sell-off; transactional and lending fees do not move with markets | Austria fees and net insurance result | unknown |
| 4 `ucg-c-equity-ceefees` | Investment fees on assets under management and custody in Central & Eastern Europe rise with market levels (fees on average balances) and with client activity (clients and UniCredit Central & Eastern Europe (wealth and asset distribution)) | the investment-fee share of fees; markets hold their level; observable: investment fees and assets under management in results presentations | onset same quarter; build as average balances reprice; persists while levels hold; recognized fee income each quarter | documented / documented / unknown / inferred | outflows in a sell-off; transactional and lending fees do not move with markets | Central & Eastern Europe fees and net insurance result | unknown |
| 5 `ucg-a-fees-italy-fees` | UniCredit Italy fees and net insurance result is one part of UniCredit fees and net insurance result (fees and net insurance result by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | fees and net insurance result | +0.54 sd/sd (accounting) |
| 6 `ucg-a-fees-germany-fees` | UniCredit Germany fees and net insurance result is one part of UniCredit fees and net insurance result (fees and net insurance result by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | fees and net insurance result | +0.20 sd/sd (accounting) |
| 7 `ucg-a-fees-austria-fees` | UniCredit Austria fees and net insurance result is one part of UniCredit fees and net insurance result (fees and net insurance result by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | fees and net insurance result | +0.09 sd/sd (accounting) |
| 8 `ucg-a-fees-cee-fees` | UniCredit Central & Eastern Europe fees and net insurance result is one part of UniCredit fees and net insurance result (fees and net insurance result by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | fees and net insurance result | +0.16 sd/sd (accounting) |
| 9 `ucg-a-rev-fees-insurance` | UniCredit fees and net insurance result is one part of UniCredit revenue (revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | revenue | +0.43 sd/sd (accounting) |
| 10 `ucg-a-pbt-revenue` | UniCredit revenue is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +1.12 sd/sd (accounting) |
| 11 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |

Unresolved inputs: investment-fee share and market beta of fees (not disclosed in reviewed sources).

#### UniCredit growth to loan volumes, NII and RWA

**Trigger:** euro-area growth picks up. **Endpoint:** UniCredit CET1 ratio.

Euro area real GDP growth → UniCredit customer loans? → UniCredit interest income on customer loans → UniCredit risk-weighted assets? → UniCredit Italy net interest income? → UniCredit Germany net interest income? → UniCredit net interest income → UniCredit net interest income → UniCredit revenue → UniCredit profit before tax → UniCredit net profit → UniCredit CET1 capital before the FVOCI reserve → UniCredit CET1 capital → UniCredit CET1 ratio → UniCredit CET1 ratio  (? marks a step whose size is unknown)

Loan demand follows nominal growth: more loans earn more interest (exact) and are booked in Italy and Germany, but add risk-weighted assets, which lowers the CET1 ratio (exact) until earnings rebuild capital.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 `ucg-c-gdp-loans` | Loan demand follows nominal activity: the bank guides loan growth above nominal GDP in Italy and Germany (corporate and household borrowers) | credit standards unchanged; demand not met by capital markets; observable: loans to customers, quarterly | onset 1-2 quarters; build several quarters; persists while growth holds; recognized average balances | broker / guidance / unknown / unknown | deleveraging; repayments of state-guaranteed loans | customer loans | unknown |
| 2 `ucg-c-loans-interest` | A larger loan book earns more interest at the prevailing yield (UniCredit (lending)) | yield held; observable: loan volumes and interest income | onset same quarter; build as loans are drawn; persists while held; recognized interest income and expense each quarter | documented / documented / model / documented | low-margin growth | interest income on customer loans | +0.60 sd/sd (identity) |
| 3 `ucg-c-loans-rwa` | Loan growth adds risk-weighted assets at the book's average risk weight (UniCredit) | risk weights unchanged; no securitisation or risk transfer; observable: RWA walk (business growth) | onset same quarter; build none; persists while held; recognized RWA at the quarter end | documented / documented / unknown / documented | risk transfer and securitisation; model changes | risk-weighted assets | unknown |
| 4 `ucg-c-loanint-italynii` | Italy's net interest income includes the interest on its customer loans (UniCredit Italy) | the division's share of loans held; observable: Italy NII | onset same quarter; build none; persists while held; recognized interest income and expense each quarter | documented / documented / unknown / documented | funds-transfer pricing reallocates margin to the centre | Italy net interest income | unknown |
| 5 `ucg-c-loanint-germanynii` | Germany's net interest income includes the interest on its customer loans (UniCredit Germany) | the division's share of loans held; observable: Germany NII | onset same quarter; build none; persists while held; recognized interest income and expense each quarter | documented / documented / unknown / documented | funds-transfer pricing reallocates margin to the centre | Germany net interest income | unknown |
| 6 `ucg-a-nii-italy-nii` | UniCredit Italy net interest income is one part of unicredit.net_interest_income (net interest income by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | unicredit.net_interest_income | +0.46 sd/sd (accounting) |
| 7 `ucg-a-nii-germany-nii` | UniCredit Germany net interest income is one part of unicredit.net_interest_income (net interest income by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | unicredit.net_interest_income | +0.26 sd/sd (accounting) |
| 8 `ucg-a-rev-net-interest-income` | unicredit.net_interest_income is one part of UniCredit revenue (revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | revenue | +0.56 sd/sd (accounting) |
| 9 `ucg-a-pbt-revenue` | UniCredit revenue is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +1.12 sd/sd (accounting) |
| 10 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |
| 11 `ucg-c-np-cet1cap` | Net profit adds to CET1 capital as it is earned (after the accrual of distributions, which leaves through its own link) (UniCredit) | profit recognised in the period; observable: CET1 capital walk (organic generation) | onset quarter end; build none; persists accumulates; recognized CET1 at the quarter end | documented / documented / model / documented | losses | CET1 capital | +0.46 sd/sd (stock-flow, accumulates per 365 days) |
| 12 `ucg-a-cet1-core-cet1-capital` | UniCredit CET1 capital before the FVOCI reserve is one part of CET1 capital (CET1 capital: the capital stock before the FVOCI reserve plus the reserve); weight is its scale over the total's | same date; the FVOCI reserve counts in CET1 (no prudential filter) | onset quarter end; build none; persists identity; recognized CET1 at the quarter end | documented / documented / model / documented | unknown | CET1 capital | +1.00 sd/sd (accounting) |
| 13 `ucg-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (none (regulatory ratio)) | risk-weighted assets unchanged; observable: CET1 ratio | onset quarter end; build none; persists identity; recognized CET1 ratio at the quarter end | documented / documented / model / documented | none | CET1 ratio | +1.67 sd/sd (identity) |
| 14 `ucg-c-rwa-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets, so RWA growth lowers it (none (regulatory ratio)) | CET1 capital unchanged; observable: CET1 ratio and RWA | onset quarter end; build none; persists identity; recognized CET1 ratio at the quarter end | documented / documented / model / documented | regulatory relief (e.g. the Danish compromise on insurance holdings) lowers RWA | CET1 ratio | -1.59 sd/sd (identity) |

Unresolved inputs: loan growth elasticity to GDP (not disclosed in reviewed sources); loan yield by division (not disclosed in reviewed sources).

#### UniCredit long-end yields to the structural hedge and capital

**Trigger:** long-end euro yields rise (a steeper curve). **Endpoint:** UniCredit CET1 ratio.

Bund 10Y yield → [hedge] UniCredit structural hedge yield → [marks] UniCredit FVOCI reserve on debt securities? → UniCredit structural hedge income → UniCredit net interest income? → UniCredit revenue → UniCredit profit before tax → UniCredit net profit → UniCredit CET1 capital before the FVOCI reserve → UniCredit CET1 capital → UniCredit CET1 capital → UniCredit CET1 ratio  (? marks a step whose size is unknown)

One move, two parallel responses: the structural hedge reinvests its maturing part at the new yield (hedge income = notional x yield, exact), and FVOCI bonds mark down into CET1 at once. s76 and s33 are the summary links on NII and the CET1 ratio; never added to these steps.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [hedge] `ucg-c-bund-hedgeyield` | The bank invests the stable part of its sight deposits in a rolling ladder of receive-fixed swaps and bonds (the structural hedge); each year the part that matures (one over the hedge's maturity) is reinvested at the current medium-term swap rate, so the hedge yield moves toward market yields slowly (UniCredit Group treasury (ALM)) | the hedge notional and its maturity are kept; the Bund 10Y stands in for the five-year euro swap rate; observable: the hedge's average yield against swap rates, quarterly | onset next quarter; build one over the maturity of the notional per year; cumulative over the hedge's maturity; persists while the curve holds; recognized interest income and expense each quarter | documented / documented / model / documented | management can shorten or lengthen the hedge; a fall in core deposits shrinks the notional | structural hedge yield | +0.30 sd/sd |
| 2 [marks] `ucg-c-bund-fvoci` | Debt securities held at fair value through OCI lose value as yields rise; the after-tax loss enters the FVOCI reserve and CET1, never income (market) | bonds held at FVOCI rather than amortised cost; hedge accounting does not offset them; observable: FVOCI reserve in the capital walk | onset immediate; build none; persists until the bonds pull to par; recognized OCI and CET1 at the quarter end | documented / documented / unknown / documented | interest-rate hedges of the FVOCI book; bonds reclassified to amortised cost | FVOCI reserve | unknown |
| 3 `ucg-c-hedgeyield-nii` | The hedge result is the notional times the hedge yield; it is allocated to the deposit-gathering divisions by funds-transfer pricing, so the link enters group NII rather than one division (Group treasury) | notional held; observable: hedge contribution in results presentations | onset same quarter; build none; persists while the yield holds; recognized interest income and expense each quarter | documented / documented / model / documented | notional cut as core deposits shrink | net interest income | +0.89 sd/sd (identity) |
| 4 `ucg-c-hedgeincome-nii` | The structural hedge's income is part of net interest income, allocated to the deposit-gathering divisions by funds-transfer pricing (Group treasury) | the allocation by division is not disclosed; observable: hedge contribution in results presentations | onset same quarter; build none; persists while the income holds; recognized interest income and expense each quarter | documented / documented / unknown / documented | none | net interest income | unknown |
| 5 `ucg-a-rev-net-interest-income` | unicredit.net_interest_income is one part of UniCredit revenue (revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | revenue | +0.56 sd/sd (accounting) |
| 6 `ucg-a-pbt-revenue` | UniCredit revenue is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +1.12 sd/sd (accounting) |
| 7 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |
| 8 `ucg-c-np-cet1cap` | Net profit adds to CET1 capital as it is earned (after the accrual of distributions, which leaves through its own link) (UniCredit) | profit recognised in the period; observable: CET1 capital walk (organic generation) | onset quarter end; build none; persists accumulates; recognized CET1 at the quarter end | documented / documented / model / documented | losses | CET1 capital | +0.46 sd/sd (stock-flow, accumulates per 365 days) |
| 9 `ucg-a-cet1-core-cet1-capital` | UniCredit CET1 capital before the FVOCI reserve is one part of CET1 capital (CET1 capital: the capital stock before the FVOCI reserve plus the reserve); weight is its scale over the total's | same date; the FVOCI reserve counts in CET1 (no prudential filter) | onset quarter end; build none; persists identity; recognized CET1 at the quarter end | documented / documented / model / documented | unknown | CET1 capital | +1.00 sd/sd (accounting) |
| 10 `ucg-a-cet1-fvoci-reserve` | UniCredit FVOCI reserve on debt securities is one part of CET1 capital (CET1 capital: the capital stock before the FVOCI reserve plus the reserve); weight is its scale over the total's | same date; the FVOCI reserve counts in CET1 (no prudential filter) | onset quarter end; build none; persists identity; recognized CET1 at the quarter end | documented / documented / model / documented | unknown | CET1 capital | +0.53 sd/sd (accounting) |
| 11 `ucg-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (none (regulatory ratio)) | risk-weighted assets unchanged; observable: CET1 ratio | onset quarter end; build none; persists identity; recognized CET1 ratio at the quarter end | documented / documented / model / documented | none | CET1 ratio | +1.67 sd/sd (identity) |

Unresolved inputs: FVOCI book size and duration (not disclosed in reviewed sources); five-year euro swap rate (not disclosed in reviewed sources); hedge allocation across divisions (not disclosed in reviewed sources); hedge notional, yield and maturity (found connected).

#### UniCredit ECB deposit rate to net interest income

**Trigger:** the ECB raises its deposit rate. **Endpoint:** UniCredit net profit.

ECB deposit rate → [euribor] Euribor 3M? → [pass_through] UniCredit commercial deposit cost → [migration] UniCredit sight deposit share? → [stake] Commerzbank net profit (as UniCredit's stake earns it)? → UniCredit customer loan yield? → UniCredit commercial deposit cost? → UniCredit interest income on customer loans → UniCredit interest paid on commercial deposits → UniCredit Italy net interest income? → UniCredit Germany net interest income? → UniCredit Austria net interest income? → UniCredit Italy net interest income? → UniCredit Germany net interest income? → UniCredit Austria net interest income? → UniCredit net interest income → UniCredit net interest income → UniCredit net interest income → UniCredit share of Commerzbank profit → UniCredit dividends and equity investments? → UniCredit revenue → UniCredit revenue → UniCredit profit before tax → UniCredit net profit  (? marks a step whose size is unknown)

Parallel responses of one rate move: Euribor and the floating-rate loan yield reprice within a reset (loan interest = loans x yield), deposit costs follow by the pass-through with a lag (interest paid = deposits x cost), balances migrate out of sight accounts, and the Commerzbank stake earns more. m28 is the summary link on group NII (sized with s76 from the disclosed scenarios) and is never added to these steps; the allocation of interest to the divisions stays uncalibrated so it is not counted twice.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [euribor] `ucg-m-ecb-euribor` | Three-month Euribor prices the expected ECB deposit rate over the next three months plus a small term and credit premium, so it follows the policy rate and moves ahead of a decision that is priced (money markets) | the corridor and excess liquidity keep Euribor close to the deposit rate; observable: Euribor 3M against the deposit facility rate, daily | onset ahead of and at the decision; build none; persists while the rate holds; recognized loan repricing at the next reset | documented / documented / unknown / inferred | liquidity shocks widen the Euribor-OIS spread | Euribor 3M | unknown |
| 2 [pass_through] `ucg-c-ecb-depcost` | The bank reprices commercial deposits by a fraction of an ECB move (the pass-through, or deposit beta): term and indexed deposits follow, sight deposits barely move; the fraction builds over quarters (UniCredit (deposit pricing in each division)) | state: the pass-through rises with the rate level and with competition for deposits; it is lower on the way down while sight balances stay unremunerated; observable: cumulative pass-through and the cost of commercial deposits, quarterly | onset within the quarter; build 2-4 quarters to the cumulative pass-through; persists while the rate holds; recognized interest expense each quarter | documented / documented / documented / inferred | excess liquidity and low loan demand hold the pass-through down; a deposit-share contest raises it; it is capped by the policy rate | commercial deposit cost | +0.94 sd/sd |
| 3 [migration] `ucg-c-ecb-sightshare` | Higher rates raise the cost of idle balances, so clients move money from sight accounts into term deposits and investment products (mix migration) (depositors (households and corporates)) | rates high enough for the opportunity cost to be noticed; transactional balances are sticky; observable: sight deposits as a share of commercial deposits, quarterly | onset 1-2 quarters; build several quarters; persists reverses slowly when rates fall; recognized interest expense as balances migrate | broker / inferred / unknown / unknown | operating balances clients cannot move; asset-management products absorb the flows (fees instead of deposits) | sight deposit share | unknown |
| 4 [stake] `ucg-c-ecb-cbkincome` | Commerzbank is itself a deposit-rich, rate-sensitive bank; higher ECB rates raise its NII and profit, and UniCredit books its share of that profit in the equity-investments line (Commerzbank (balance sheet) and UniCredit (equity accounting)) | the stake is equity-accounted, not consolidated; observable: Commerzbank NII sensitivity and UniCredit's equity-investment income | onset 1-2 quarters; build as Commerzbank's deposits reprice; persists while the rate holds; recognized dividends and equity investments each quarter | broker / broker / unknown / inferred | full consolidation moves Commerzbank into every line (a change of basis); Commerzbank's own deposit beta | UniCredit share of Commerzbank profit | unknown |
| 5 `ucg-c-euribor-loanyield` | Floating-rate corporate and mortgage loans reset off Euribor, so the loan yield follows Euribor at each reset; fixed-rate loans reprice only as they are originated (UniCredit (lending)) | the floating share of the book and any receive-fixed swaps that convert it; observable: loan yield against Euribor, quarterly | onset at the next reset (1-3 months); build one reset cycle; persists while Euribor holds; recognized interest income and expense each quarter | documented / documented / unknown / inferred | the structural hedge converts part of the floating exposure; loan-spread competition | customer loan yield | unknown |
| 6 `ucg-c-sightshare-depcost` | Sight deposits pay little or nothing, so a larger sight share lowers the average cost of commercial deposits at a given policy rate (depositors) | total deposits unchanged; observable: sight share and the cost of commercial deposits | onset same quarter; build none; persists while the mix holds; recognized interest expense each quarter | documented / documented / unknown / documented | rising remuneration of sight balances | commercial deposit cost | unknown |
| 7 `ucg-c-loanyield-interest` | Interest income on customer loans is the balance times the loan yield (UniCredit (lending)) | balances held; observable: interest income on customer loans | onset same quarter; build none; persists while the yield holds; recognized interest income and expense each quarter | documented / documented / model / documented | loan balances shrink | interest income on customer loans | +1.00 sd/sd (identity) |
| 8 `ucg-c-depcost-interest` | Interest paid on commercial deposits is the balance times the average deposit cost (UniCredit (deposit pricing)) | balances held; observable: interest expense on customer deposits | onset same quarter; build none; persists while the cost holds; recognized interest income and expense each quarter | documented / documented / model / documented | falling balances | interest paid on commercial deposits | +0.95 sd/sd (identity) |
| 9 `ucg-c-loanint-italynii` | Italy's net interest income includes the interest on its customer loans (UniCredit Italy) | the division's share of loans held; observable: Italy NII | onset same quarter; build none; persists while held; recognized interest income and expense each quarter | documented / documented / unknown / documented | funds-transfer pricing reallocates margin to the centre | Italy net interest income | unknown |
| 10 `ucg-c-loanint-germanynii` | Germany's net interest income includes the interest on its customer loans (UniCredit Germany) | the division's share of loans held; observable: Germany NII | onset same quarter; build none; persists while held; recognized interest income and expense each quarter | documented / documented / unknown / documented | funds-transfer pricing reallocates margin to the centre | Germany net interest income | unknown |
| 11 `ucg-c-loanint-austrianii` | Austria's net interest income includes the interest on its customer loans (UniCredit Austria) | the division's share of loans held; observable: Austria NII | onset same quarter; build none; persists while held; recognized interest income and expense each quarter | documented / documented / unknown / documented | funds-transfer pricing reallocates margin to the centre | Austria net interest income | unknown |
| 12 `ucg-c-depint-italynii` | Italy's net interest income is net of the interest paid on its commercial deposits (UniCredit Italy) | the division's share of deposits held; observable: Italy NII | onset same quarter; build none; persists while held; recognized interest income and expense each quarter | documented / documented / unknown / documented | falling balances | Italy net interest income | unknown |
| 13 `ucg-c-depint-germanynii` | Germany's net interest income is net of the interest paid on its commercial deposits (UniCredit Germany) | the division's share of deposits held; observable: Germany NII | onset same quarter; build none; persists while held; recognized interest income and expense each quarter | documented / documented / unknown / documented | falling balances | Germany net interest income | unknown |
| 14 `ucg-c-depint-austrianii` | Austria's net interest income is net of the interest paid on its commercial deposits (UniCredit Austria) | the division's share of deposits held; observable: Austria NII | onset same quarter; build none; persists while held; recognized interest income and expense each quarter | documented / documented / unknown / documented | falling balances | Austria net interest income | unknown |
| 15 `ucg-a-nii-italy-nii` | UniCredit Italy net interest income is one part of unicredit.net_interest_income (net interest income by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | unicredit.net_interest_income | +0.46 sd/sd (accounting) |
| 16 `ucg-a-nii-germany-nii` | UniCredit Germany net interest income is one part of unicredit.net_interest_income (net interest income by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | unicredit.net_interest_income | +0.26 sd/sd (accounting) |
| 17 `ucg-a-nii-austria-nii` | UniCredit Austria net interest income is one part of unicredit.net_interest_income (net interest income by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | unicredit.net_interest_income | +0.13 sd/sd (accounting) |
| 18 `ucg-c-cbknp-income` | UniCredit's equity-accounted income is its stake times Commerzbank's net profit (UniCredit (equity accounting)) | state: equity-accounted while below control; observable: the equity-investments line | onset same quarter; build none; persists while equity-accounted; recognized revenue each quarter | documented / documented / model / documented | full consolidation (a change of basis) | UniCredit share of Commerzbank profit | +0.33 sd/sd (identity) |
| 19 `ucg-c-cbkincome-divline` | UniCredit's share of Commerzbank's profit is booked in the dividends and equity investments line of revenue, beside Alpha Bank at equity and dividends from financial stakes; the split of the line is not disclosed, so this is a signed link, not an accounting part (none (equity accounting)) | state: equity-accounted while below control; observable: dividends and equity investments line | onset same quarter; build none; persists while equity-accounted; recognized revenue each quarter | documented / documented / unknown / documented | full consolidation moves Commerzbank out of this line into every line (a change of basis) | dividends and equity investments | unknown |
| 20 `ucg-a-rev-dividends-equity-income` | UniCredit dividends and equity investments is one part of UniCredit revenue (revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | revenue | +0.39 sd/sd (accounting) |
| 21 `ucg-a-rev-net-interest-income` | unicredit.net_interest_income is one part of UniCredit revenue (revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | revenue | +0.56 sd/sd (accounting) |
| 22 `ucg-a-pbt-revenue` | UniCredit revenue is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +1.12 sd/sd (accounting) |
| 23 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |

Unresolved inputs: Commerzbank NII sensitivity (found connected); Commerzbank net profit (not disclosed in reviewed sources); Commerzbank share of the dividends and equity investments line (not disclosed in reviewed sources); Euribor 3M history (not disclosed in reviewed sources); average commercial deposits by division (found connected); loan yield by division (not disclosed in reviewed sources); migration elasticity of sight balances to rates (not disclosed in reviewed sources); pass-through by division and by deposit type (not disclosed in reviewed sources); share of floating-rate loans (not disclosed in reviewed sources); stake share in Commerzbank (found connected).

#### UniCredit rouble and Russia wind-down to profit and capital

**Trigger:** the rouble weakens (EUR/RUB rises) while Russia is wound down. **Endpoint:** UniCredit CET1 ratio.

EUR/RUB → [income] UniCredit Russia net interest income? → [capital] UniCredit CET1 capital before the FVOCI reserve? → UniCredit net interest income → UniCredit revenue → UniCredit profit before tax → UniCredit net profit → UniCredit CET1 capital before the FVOCI reserve → UniCredit CET1 capital → UniCredit CET1 ratio  (? marks a step whose size is unknown)

A weaker rouble shrinks Russian NII and profit in euros and the translated equity in CET1; the extreme-loss scenario (zero value) is a separate capital tail, reduced by the partial sale.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [income] `ucg-c-rub-russianii` | Russian NII is earned in roubles; a weaker rouble (EUR/RUB up) lowers its euro value at translation (the divisional table also shows it at constant FX) (market (translation)) | the subsidiary still earns rouble income while it is wound down; observable: Russia NII at current and constant FX | onset same quarter; build none; persists while the rate holds; recognized translation each quarter | documented / documented / unknown / documented | the wind-down and the partial sale shrink the base | Russia net interest income | unknown |
| 2 [capital] `ucg-c-rub-cet1cap` | The rouble equity of the Russian subsidiary is translated into euros at the closing rate; a weaker rouble lowers the translation reserve and CET1 (market (translation)) | Russian equity unhedged; observable: CET1 walk (FX) | onset quarter end; build none; persists while the rate holds; recognized CET1 at the quarter end | broker / documented / unknown / documented | the partial sale and deconsolidation | CET1 capital | unknown |
| 3 `ucg-a-nii-russia-nii` | UniCredit Russia net interest income is one part of unicredit.net_interest_income (net interest income by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | unicredit.net_interest_income | +0.26 sd/sd (accounting) |
| 4 `ucg-a-rev-net-interest-income` | unicredit.net_interest_income is one part of UniCredit revenue (revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | revenue | +0.56 sd/sd (accounting) |
| 5 `ucg-a-pbt-revenue` | UniCredit revenue is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +1.12 sd/sd (accounting) |
| 6 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |
| 7 `ucg-c-np-cet1cap` | Net profit adds to CET1 capital as it is earned (after the accrual of distributions, which leaves through its own link) (UniCredit) | profit recognised in the period; observable: CET1 capital walk (organic generation) | onset quarter end; build none; persists accumulates; recognized CET1 at the quarter end | documented / documented / model / documented | losses | CET1 capital | +0.46 sd/sd (stock-flow, accumulates per 365 days) |
| 8 `ucg-a-cet1-core-cet1-capital` | UniCredit CET1 capital before the FVOCI reserve is one part of CET1 capital (CET1 capital: the capital stock before the FVOCI reserve plus the reserve); weight is its scale over the total's | same date; the FVOCI reserve counts in CET1 (no prudential filter) | onset quarter end; build none; persists identity; recognized CET1 at the quarter end | documented / documented / model / documented | unknown | CET1 capital | +1.00 sd/sd (accounting) |
| 9 `ucg-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (none (regulatory ratio)) | risk-weighted assets unchanged; observable: CET1 ratio | onset quarter end; build none; persists identity; recognized CET1 ratio at the quarter end | documented / documented / model / documented | none | CET1 ratio | +1.67 sd/sd (identity) |

Unresolved inputs: CET1 sensitivity to the rouble (not disclosed in reviewed sources); EUR/RUB history and Russia's rouble earnings (not disclosed in reviewed sources).

#### UniCredit Italian sovereign spread to capital and distributions

**Trigger:** the BTP-Bund spread widens. **Endpoint:** UniCredit total distributions.

BTP-Bund 10Y spread → [marks] UniCredit FVOCI reserve on debt securities? → [funding] UniCredit Group Corporate Centre net interest income? → UniCredit CET1 capital → UniCredit CET1 ratio → UniCredit share buybacks? → UniCredit total distributions → UniCredit net interest income → UniCredit revenue → UniCredit profit before tax → UniCredit net profit  (? marks a step whose size is unknown)

A wider spread marks the Italian sovereign book down through the FVOCI reserve into CET1 (exact from the reserve on), which leaves less capital above target for extra buybacks; it also raises the corporate centre's wholesale funding cost as debt rolls.

| Step | Mechanism and actor | Condition and observable | Timing | Evidence (existence / direction / magnitude / timing) | Breaker | Next state | Size |
|---|---|---|---|---|---|---|---|
| 1 [marks] `ucg-c-btp-fvoci` | A wider BTP-Bund spread lowers the value of the Italian government bonds held at FVOCI; the loss enters the FVOCI reserve and CET1 (market) | BTPs held at FVOCI; spread widening not hedged; observable: FVOCI reserve; Italian sovereign exposure | onset immediate; build none; persists while the spread holds; recognized OCI and CET1 at the quarter end | broker / documented / unknown / documented | reduction of the Italian sovereign book; ECB backstop narrowing the spread | FVOCI reserve | unknown |
| 2 [funding] `ucg-c-btp-gccnii` | MREL and senior issuance spreads of an Italian bank track the sovereign, so a wider BTP spread raises the cost of wholesale funding booked in the corporate centre as debt rolls (bond investors) | issuance or refinancing in the period; observable: new-issue spreads of senior and MREL debt | onset at the next issues; build as debt rolls (years); persists while the spread holds; recognized interest income and expense each quarter | documented / inferred / unknown / inferred | a funding surplus that limits issuance; German and Austrian issuers price off their own curves | Group Corporate Centre NII | unknown |
| 3 `ucg-a-cet1-fvoci-reserve` | UniCredit FVOCI reserve on debt securities is one part of CET1 capital (CET1 capital: the capital stock before the FVOCI reserve plus the reserve); weight is its scale over the total's | same date; the FVOCI reserve counts in CET1 (no prudential filter) | onset quarter end; build none; persists identity; recognized CET1 at the quarter end | documented / documented / model / documented | unknown | CET1 capital | +0.53 sd/sd (accounting) |
| 4 `ucg-c-cet1cap-ratio` | The CET1 ratio is CET1 capital over risk-weighted assets (none (regulatory ratio)) | risk-weighted assets unchanged; observable: CET1 ratio | onset quarter end; build none; persists identity; recognized CET1 ratio at the quarter end | documented / documented / model / documented | none | CET1 ratio | +1.67 sd/sd (identity) |
| 5 `ucg-c-ratio-buybacks` | Capital above the management target is distributable: the bank adds excess-capital buybacks when the ratio sits above the target range, and stops them when it does not (UniCredit (board)) | state: only the excess over the management target range is distributed; below it, extra buybacks stop and organic generation rebuilds the buffer; observable: CET1 ratio against the target range; announced extra distributions | onset annual (with results); build none; persists while the excess lasts; recognized deducted from CET1 when announced | guidance / guidance / unknown / guidance | M&A uses the excess capital first (Commerzbank consolidation); supervisory authorisation | share buybacks | unknown |
| 6 `ucg-a-dist-buybacks` | UniCredit share buybacks is one part of UniCredit total distributions (distributions for the year: cash dividends plus share buybacks); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | total distributions | +0.80 sd/sd (accounting) |
| 7 `ucg-a-nii-gcc-nii` | UniCredit Group Corporate Centre net interest income is one part of unicredit.net_interest_income (net interest income by division); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | unicredit.net_interest_income | +0.34 sd/sd (accounting) |
| 8 `ucg-a-rev-net-interest-income` | unicredit.net_interest_income is one part of UniCredit revenue (revenue by line: NII, fees and net insurance result, trading, dividends and equity investments (reclassified P&L, IFRS)); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | revenue | +0.56 sd/sd (accounting) |
| 9 `ucg-a-pbt-revenue` | UniCredit revenue is one part of UniCredit profit before tax (profit before tax: revenue less operating costs less loan loss provisions, plus other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | profit before tax | +1.12 sd/sd (accounting) |
| 10 `ucg-a-np-profit-before-tax` | UniCredit profit before tax is one part of UniCredit net profit (stated net profit: profit before tax less income tax, less minorities, discontinued operations and other items); weight is its scale over the total's | UniCredit reclassified basis, same period, EUR; never added to another view of the same total | onset same reporting period; build none; persists identity; recognized quarterly results | documented / documented / model / documented | unknown | net profit | +1.35 sd/sd (accounting) |

Unresolved inputs: CET1 sensitivity to the BTP-Bund spread (not disclosed in reviewed sources); Italian sovereign FVOCI book size (not disclosed in reviewed sources); management buffer above requirements and the use of excess capital (found connected).

## Validation

*First round. The conversion round below supersedes the structure and counts.*

`tests/scenario/test_construction_unicredit.py` (loads sally_demo once; reads no client data):

- Structure: no `validate_construction` problems for the company; the eleven compositions and eleven paths exist; every
  path step has a transition, every uncalibrated step a sign and an "unknown" magnitude; the parallel responses of one
  ECB move (Euribor, pass-through, mix migration, the Commerzbank stake) are branches from the deposit rate, the long-end
  responses (hedge, marks) branches from the Bund, and the credit responses (defaults, overlays) branches from
  unemployment; the reduced forms (m28, s76, s33) are never steps of their structural paths.
- Financial integrity: every part of an additive view has a fixed-weight accounting link equal to its native sd over
  the total's; one unit per view; every view but the exact distribution split keeps a residual; the priors of every
  additive view reconcile within 0.5% (exactly, in fact); the division views list the five reported divisions with the
  Group Corporate Centre as residual; the division and line views share no part and only size-free `matrix:` bridges
  cross them; FVOCI marks reach CET1 and never income; capital is a stock with signed `stock-flow:` links, not an
  additive view; distributions split into cash dividends and buybacks with the excess-capital step tagged `state:`.
- Calibration: the only new sizes are the deposit pass-through (documented, lagged) and the hedge roll (from the
  disclosed hedge, magnitude "model"); m28, s33, s34 and s76 keep their sizes with magnitude "assumption" and named
  inputs; every missing input says whether the supplied material was searched (no `not_yet_reviewed` remains); at least
  thirty links carry a pending-form tag.
- Bank specifics: overlays are released before provisions rise (counter-path); the Commerzbank stake reaches RWA, the
  CET1 ratio, buybacks and revenue, with the consolidation step tagged `state:`.
- Generalization: an oil-price shock, for which no UniCredit path was written, traced through every link (below).
- Delivery: compositions in `financial_bridge`, named paths as `business_construction` transmission paths, the line
  view's links as `accounting_identity`, uncalibrated links as `represented_uncalibrated` with their sign, m28's
  transition in the export; new node ids returned by `/v1/world-models/sally_demo/graph`, the construction and trace endpoints.

Sally's expected paths (`tests/scenario/test_sally_expected_paths.py`) still pass: `net_interest_income`, `cet1_ratio`
and the share price keep their ids, m28, s33, s34 and s76 keep their sizes and signs, and the two new calibrated links
end at operating states whose onward steps are uncalibrated, so they move no output of Sally's theses. The Toyota, Tokio
Marine and JPMorgan tests pass unchanged.

**Generalization trace (oil-price shock).** `trace(g, "oil.brent", "unicredit")`: 68 routes, 59 reach a
financial endpoint. Calibrated end to end: oil → euro inflation → ECB (m03, m10) → m28 → group NII; ECB → Bund (s05)
→ s76 → NII and → s33 → CET1 ratio; the US route (m04, m07, m11, m12, s06) into the same two; ECB → deposit cost (the
calibrated pass-through) and Bund → hedge yield (the calibrated roll), each one step short of NII. Represented with sign
but no size: deposit cost and loan yield into divisional NII; inflation into divisional costs; ECB and Bund into equity
markets (s66, s67) and divisional investment fees; ECB into the Commerzbank stake's income and the equity-investments
line; Bund into FVOCI marks and CET1 capital; and, through slower euro growth, unemployment into the cost of risk by
division and the overlay release, loan volumes into NII and RWA, and the Italian spread into FVOCI and corporate-centre
funding. Where it stops: the share price (nothing leads on from it), and, at the trace depth of eight links, inside the
fee chains reached through the US curve. The trace reaches the bank through every business: rates, the hedge, fees,
credit, costs, the stake, and capital.

## Completion report

*First round (before the conversion). For the current state see [Conversion round](#conversion-round).*

Outcomes map to the release outcomes: built and verified (**BV**), built but uncalibrated (**BU**), blocked by a named
input (**BL**), not built (**NB**).

| # | Outcome | What is in the model now | What remains |
|---|---|---|---|
| G01 | BV | Line view, P&L bridge to PBT and net profit, division views of revenue, NII, fees, costs, provisions and net profit; 50 accounting links with sd-ratio weights | — |
| G02 | BV | Basis and export metric on every UniCredit value (standalone, reclassified, constant FX where reported) | — |
| G03 | BL | m28 scoped as the reduced form, magnitude "assumption", cross-checked against the disclosed parallel-shift sensitivity: at the priors m28 alone implies more than the disclosure covers for the whole curve, and s76 adds the long end on top | the split of the disclosed parallel sensitivity between the short end and the hedge (not disclosed; the IRRBB tables were not in the material) |
| G04 | BU | `euro_money_markets.euribor_3m`, deposit cost, sight share, loan yield; `ucg.path.rates_nii` with four parallel branches into NII by division | floating-rate share, loan yield by division, migration elasticity, Euribor history (not disclosed) |
| G05 | BV | `ucg-c-ecb-depcost` calibrated from the company's pass-through, lagged two quarters; the asymmetry tagged `state:` | pass-through by division and deposit type (not disclosed) |
| G06 | BU (structure) / BV (hedge roll) | `ucg.path.long_end`; `ucg-c-bund-hedgeyield` calibrated from the disclosed notional and maturity (magnitude "model"); s76 scoped | FVOCI book size and duration (not disclosed) |
| G07 | BU | `btps.bund_spread_10y`, `ucg.path.sovereign_spread`; s33 scoped | Italian sovereign FVOCI book, CET1 sensitivity to the spread (not disclosed) |
| G08 | BV (structure; driven through NII, fees, costs, provisions) | six division views, GCC as residual; size-free bridges between the division and line views | divisional rate sensitivity; CEE local policy rates (not in the world) |
| G09 | BU | `ucg.path.fees_markets` | investment-fee share and market beta (not disclosed) |
| G10 | BU | `euro_economy.gdp_growth`, `euro_economy.unemployment_rate`, cost of risk, overlays, `ucg.path.credit_cycle` with the overlay counter-path | unemployment sensitivity, IFRS 9 scenario weights, cost of risk by division (not disclosed); overlay stock (found, connected) |
| G11 | BU | `ucg.path.cost_inflation` | wage indexation (not disclosed) |
| G12 | BU | capital values, `ucg.comp.distributions`, `ucg.comp.capital_roll_forward`, two capital paths; s34 scoped | every step is a product, ratio or stock-flow identity; payout, target and buffer found and connected |
| G13 | BU | stake state, equity-investments link, `ucg.path.commerzbank` with the consolidation step | Commerzbank's own profit and its share of the equity-investments line (not disclosed); the basis switch at control (see G18) |
| G14 | BU | `eur_rub.rate`, `ucg.path.russia`, the extreme-loss capital tail | EUR/RUB history, CET1 sensitivity to the rouble (not disclosed); the maximum loss (found, connected) |
| G15 | BU | `ucg.path.loan_growth` | loan growth elasticity to GDP (not disclosed; guidance is qualitative) |
| G16 | BV | objects present in the v4.1.4 export | — |
| G17 | BV | node ids served by the query, construction and trace endpoints | — |
| G18 | BL | baselines on one basis (standalone, as reported); the consolidation as a stake state with signed effects | a basis-switch object (not in the method); see below |

Counts: 18 gaps. By category (a gap can carry two): MC 12, CAL 4, MAP 5, EXP 1, RET 2. By outcome: BV 6 (G01, G02, G05,
G08, G16, G17), BV in part 1 (G06), BU 9, BL 2 (G03, G18), NB 0.

**Links.** 114 links touch UniCredit's values: 50 accounting (fixed weights), 9 calibrated causal (m28, s33, s34, s68,
s76, s79, s81 and the two new ones from evidence: `ucg-c-ecb-depcost`, `ucg-c-bund-hedgeyield`), 55 uncalibrated
(mechanism and sign). 111 carry a transition (not s68, s79, s81). Four more uncalibrated links sit between the new macro
values (`ucg-m-*`). 40 links carry a pending-form tag in their `note` (identity, stock-flow, matrix, state).

**Reconciliation.** At the priors (model medians), every one of the ten additive views adds up exactly (0.0%): the
synthetic levels were set to reconcile, and each residual says what it holds. At the FY2025 baselines (local
`baselines_all.json`, workbook actuals), all ten reconcile within 0.5%: seven exactly, and three with a rounding
difference in the company's divisional tables that the residual leaves unexplained (revenue by division +0.004%, costs
by division −0.01%, net profit by division −0.01% of the total). Four levels are derived, not read, so their views
reconcile by construction: other revenue (revenue less the four lines), other items before tax (PBT less revenue,
costs and provisions), the items after tax (stated net profit less PBT and tax) and CET1 capital (ratio times RWA).
PBT and tax are FY2025 actuals as recorded by two brokers (the workbook has no PBT history). Units are one per view
(tested). The builder check agrees: `check.py sally_demo --entities unicredit --reconcile --statistic median` and
`--reconcile --baselines <local baselines_all.json>` report 0 flags. The importable halves (`baselines.json`, group;
`baselines_divisions.json`, divisions) each pass `scripts/imports/bundles.py check`; the merged bundle does not, because
the import folds one view per total and day (see the method findings).

**Sources and citations.** `check.py --sources <local construction folder>`: 9 source ids resolve, 0 do not; 111
links and 61 values are cited (sheet and cell or row, or page and paragraph, with the passage); 0 material claims
without a citation.

**Inputs by status** (28 distinct inputs named in transitions, after `scripts/construction/inputs.py` searched ten
supplied files for each, and the candidates were read): 9 found and connected (bound as a baseline, a citation or a
calibration), 0 found but not connected, 19 not disclosed in the reviewed sources (each with the sources and corpus
queries searched; where the keyword search returned candidates, they were read and found to be the workbook's own
"not disclosed" notes, mechanism text, or about other banks, and the note says so), 0 not yet reviewed.

**Forecast coverage (Sally's theses).** The ECB-cut thesis (S-T5) reaches UniCredit through 12 quantified links (m28,
the calibrated pass-through, s76, the calibrated hedge roll, s33, s34, s68, s79, s81 and the NII → revenue → PBT →
net profit accounting links) and excludes 16 uncalibrated ones (Euribor, migration, the divisional deposit-cost steps,
the Commerzbank stake, hedge income, FVOCI marks, fees, capital and buybacks, each with its sign); 2 of its 12 routes to
NII and 6 of 17 to the share price are fully quantified; 11 inputs block a size (6 found and connected, 5 not
disclosed). The global-yields thesis (S-T2) reaches UniCredit through the Bund: 6 quantified links, 8 excluded.

**Calculation coverage by path.** "Calculated" contributes a size; accounting links carry it to the endpoint at fixed
weights; uncalibrated steps carry a sign only and are listed as unquantified by any forecast that reaches them.

| Path | Calculated (calibrated causal) | Accounting | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|
| `ucg.path.rates_nii` | `ucg-c-ecb-depcost`; m28 is the reduced form beside the path | 7 | `ucg-m-ecb-euribor` (+), `ucg-c-ecb-sightshare` (-), `ucg-c-ecb-cbkincome` (+), `ucg-c-euribor-loanyield` (+), `ucg-c-sightshare-depcost` (-), `ucg-c-loanyield-italynii` (+), `ucg-c-loanyield-germanynii` (+), `ucg-c-loanyield-austrianii` (+), `ucg-c-depcost-italynii` (-), `ucg-c-depcost-germanynii` (-), `ucg-c-depcost-austrianii` (-), `ucg-c-cbkincome-divline` (+) | Commerzbank NII sensitivity (found, connected); Commerzbank net profit (not disclosed); Commerzbank share of the dividends and equity investments line (not disclosed); Euribor 3M history (not disclosed); average commercial deposits by division (found, connected); loan yield by division (not disclosed); migration elasticity of sight balances to rates (not disclosed); share of floating-rate loans (not disclosed); stake share in Commerzbank (found, connected) |
| `ucg.path.long_end` | `ucg-c-bund-hedgeyield`; s76 and s33 are the reduced forms beside it | 3 | `ucg-c-bund-fvoci` (-), `ucg-c-hedgeyield-nii` (+), `ucg-c-np-cet1cap` (+), `ucg-c-fvoci-cet1cap` (+), `ucg-c-cet1cap-ratio` (+) | FVOCI book size and duration (not disclosed); hedge notional, yield and maturity (found, connected) |
| `ucg.path.sovereign_spread` | none; s33 (Bund only) beside it | 5 | `ucg-c-btp-fvoci` (-), `ucg-c-btp-gccnii` (-), `ucg-c-fvoci-cet1cap` (+), `ucg-c-cet1cap-ratio` (+), `ucg-c-ratio-buybacks` (+) | CET1 sensitivity to the BTP-Bund spread (not disclosed); Italian sovereign FVOCI book size (not disclosed); management buffer above requirements and the use of excess capital (found, connected) |
| `ucg.path.credit_cycle` | none | 6 | `ucg-m-gdp-unemp` (-), `ucg-c-unemp-cor` (+), `ucg-c-unemp-overlays` (-), `ucg-c-cor-italyllp` (-), `ucg-c-cor-germanyllp` (-), `ucg-c-cor-austriallp` (-), `ucg-c-cor-ceellp` (-), `ucg-c-overlays-llp` (-) | IFRS 9 scenario weights (not disclosed); cost of risk by division (not disclosed); cost-of-risk sensitivity to unemployment (not disclosed); overlay stock and its release policy (found, connected) |
| `ucg.path.loan_growth` | none | 5 | `ucg-c-gdp-loans` (+), `ucg-c-loans-italynii` (+), `ucg-c-loans-germanynii` (+), `ucg-c-loans-rwa` (+), `ucg-c-np-cet1cap` (+), `ucg-c-cet1cap-ratio` (+), `ucg-c-rwa-ratio` (-) | loan growth elasticity to GDP (not disclosed); loan yield by division (not disclosed) |
| `ucg.path.fees_markets` | none | 7 | `ucg-c-equity-italyfees` (+), `ucg-c-equity-germanyfees` (+), `ucg-c-equity-austriafees` (+), `ucg-c-equity-ceefees` (+) | investment-fee share and market beta of fees (not disclosed) |
| `ucg.path.cost_inflation` | none | 5 | `ucg-c-cpi-italycosts` (-), `ucg-c-cpi-germanycosts` (-), `ucg-c-cpi-austriacosts` (-) | wage indexation and cost sensitivity to inflation (not disclosed) |
| `ucg.path.capital_distribution` | none; s34 (ratio to share price) beside it | 2 | `ucg-c-np-cet1cap` (+), `ucg-c-np-dividends` (+), `ucg-c-np-buybacks` (+), `ucg-c-cet1cap-ratio` (+), `ucg-c-ratio-buybacks` (+), `ucg-c-dist-cet1cap` (-) | management buffer above requirements and the use of excess capital (found, connected); ordinary payout ratio and its cash share (found, connected) |
| `ucg.path.capital_requirements` | none | 1 | `ucg-c-target-buybacks` (-), `ucg-c-dist-cet1cap` (-), `ucg-c-cet1cap-ratio` (+) | management buffer above requirements and the use of excess capital (found, connected) |
| `ucg.path.commerzbank` | none | 4 | `ucg-c-cbkstake-income` (+), `ucg-c-cbkstake-rwa` (+), `ucg-c-cbkincome-divline` (+), `ucg-c-np-buybacks` (+), `ucg-c-rwa-ratio` (-), `ucg-c-ratio-buybacks` (+) | Commerzbank net profit (not disclosed); Commerzbank share of the dividends and equity investments line (not disclosed); consolidation CET1 impact (found, connected); management buffer above requirements and the use of excess capital (found, connected); ordinary payout ratio and its cash share (found, connected); stake share in Commerzbank (found, connected) |
| `ucg.path.russia` | none | 4 | `ucg-c-rub-russianii` (-), `ucg-c-rub-cet1cap` (-), `ucg-c-np-cet1cap` (+), `ucg-c-cet1cap-ratio` (+) | CET1 sensitivity to the rouble (not disclosed); EUR/RUB history and Russia's rouble earnings (not disclosed) |
| Generalization (oil) | m03, m10, s05, m04, m07, m11, m12, s06 (shared macro links), then m28, s76, s33, `ucg-c-ecb-depcost`, `ucg-c-bund-hedgeyield` | the line, division and P&L views | every divisional NII, fee, cost, credit, stake, FVOCI and capital step | as for the paths above |

**What a downstream agent can now trace or calculate.** Revenue as NII, fees and net insurance, trading, and
dividends and equity investments, and on to profit before tax and stated net profit through costs, provisions and
other items; the same totals by division (reconciled, not driven) and NII, fees, costs and provisions by division
(driven); capital as a stock with its flows and the distribution policy split into dividends and buybacks; a
calculated size for an ECB move on group NII (m28, scoped), for the long end on NII and the CET1 ratio (s76, s33), for
the deposit pass-through on the deposit cost (from the company's figure, lagged) and for the long end on the hedge
yield (from the disclosed hedge); and, as signed mechanisms with conditions, timing, evidence and breakers: Euribor
and floating loans, mix migration, divisional deposit margins, hedge income, FVOCI marks from the Bund and the Italian
spread, corporate-centre funding, investment fees, wage inflation, unemployment into the cost of risk with the overlay
release first, loan growth into NII and RWA, the Commerzbank stake's income and consolidation step, rouble translation
and the Russia extreme-loss tail, and excess-capital buybacks above the target.

**What remains unsupported.** Any size along the structural NII, hedge-income, credit, fee, cost and capital steps
(each is a product of a balance and a rate, a ratio, or a stock-flow accumulation); the short-end/long-end split of
the disclosed sensitivity; divisional sensitivities and CEE's local rates; the sovereign FVOCI book; IFRS 9 scenarios;
the Commerzbank consolidation as a change of basis; importing a full results release in one item (G18).

**New shared macro values** (uncalibrated, so no other company's output moves; other European bank builds should
reuse them): `euro_money_markets.euribor_3m` (new market entity `euro_money_markets`), `btps.bund_spread_10y` (new
market entity `btps`), `eur_rub.rate` (new market entity `eur_rub`), `euro_economy.gdp_growth`,
`euro_economy.unemployment_rate`; macro links `ucg-m-ecb-euribor`, `ucg-m-oil-eurogdp`, `ucg-m-gdp-unemp`,
`ucg-m-gdp-btpspread`.

## Conversion round

Oct 18, after the method extension (identities, stock-flows, matrices and reconciling views, state-dependent
responses, scenario calibration). The steps first tagged `identity:`, `stock-flow:` and `matrix:` are converted; the
rest stay uncalibrated and their `note` says why.

**One driving view per total.**

| Total | Driving | Reconciling (observed, never driving) |
|---|---|---|
| `unicredit.revenue` | `ucg.comp.revenue_by_line` (the rows of matrix `ucg.mx.revenue`) | `ucg.comp.revenue_by_division` (its columns; cells: NII and fees by division, twelve accounting cell links replace the five size-free bridges) |
| `unicredit.net_profit` | `ucg.comp.net_profit` (the P&L bridge) | `ucg.comp.net_profit_by_division` (`drives: false`) |
| `unicredit.loan_loss_provisions` | the identity `ucg.id.llp` (loans × cost of risk) | `ucg.comp.llp_by_division` (`drives: false`) |

A reconciling view's parts have no link into the total, so a results day that reports every view folds whole: the
FY2025 baselines are again one bundle (`baselines.json`, both views) and pass `scripts/imports/bundles.py check`.

**Links converted, by form.**

| Form | Object | Links (written to carry the transition; the weights are derived) | Replaces |
|---|---|---|---|
| identity, product | `ucg.id.hedge_income` = notional × hedge yield | `ucg-c-hedgeyield-nii` (+ the notional term) | the hedge yield → NII step |
| identity, product | `ucg.id.deposit_interest` = commercial deposits × deposit cost | `ucg-c-depcost-interest` (+ the balance term) | three deposit cost → divisional NII steps |
| identity, product | `ucg.id.loan_interest` = customer loans × loan yield | `ucg-c-loanyield-interest`, `ucg-c-loans-interest` | three loan yield → divisional NII and two loans → divisional NII steps |
| identity, product | `ucg.id.cbk_income` = stake × Commerzbank net profit | `ucg-c-cbkstake-income`, `ucg-c-cbknp-income` | the stake → income step |
| identity, product | `ucg.id.llp` = − loans × cost of risk | `ucg-c-cor-llp` (+ the loans term) | four cost of risk → divisional provision steps |
| identity, ratio | `ucg.id.cet1_ratio` = CET1 capital / RWA | `ucg-c-cet1cap-ratio`, `ucg-c-rwa-ratio` | the two ratio steps |
| identity, product | `ucg.id.cash_dividends` = net profit × cash payout ratio | `ucg-c-np-dividends`, `ucg-c-payout-dividends` | the payout steps |
| identity, product | `ucg.id.ordinary_buybacks` = net profit × buyback payout ratio | `ucg-c-np-buybacks`, `ucg-c-payout-buybacks` | the payout steps |
| stock-flow | `ucg.sf.core_cet1`: capital stock += net profit − distributions (annual flows) | `ucg-c-np-cet1cap`, `ucg-c-dist-cet1cap` | the two capital flow steps |
| composition | `ucg.comp.cet1_capital` = stock + FVOCI reserve; `ucg.comp.payout` = cash + buyback payout ratios | accounting links | the FVOCI → capital step; a single payout ratio |
| matrix | `ucg.mx.revenue` | 12 cell links | five bridges |
| state | none | — | no response has a size by side or a sized threshold (below) |

**Left uncalibrated, with the reason in the note.** The allocation steps into divisional NII (loan interest, interest
paid) and hedge income into NII: their sizes would count twice what the summary links m28 and s76 carry, and the
allocation by division is not disclosed. The sight-share step (a weighted average whose weights are values). The
overlay release (a stock's change entering a flow). Loans into RWA (not one product). Rouble translation of the
capital stock (a revaluation). The Commerzbank share of the equity-investments line (a part whose level is not
disclosed). The consolidation step and the excess-capital buybacks (thresholds with no disclosed size). The pass-through
keeps one linear size: the company gives no size by side.

**New calibration.** m28 and s76 are sized jointly by `calibrate.py --disclosure` over the company's parallel-shift NII
sensitivity (up and down) and a long-end scenario derived from the disclosed hedge (its year-one roll), magnitude
"model" because the split between them is derived, not disclosed. Both fall well below their original records (m28
from 0.5 to about 0.12 sd/sd, s76 from 0.2 to about 0.11), so the model's parallel-shift response now matches the
disclosure (the scenarios stay local). Sally's expected paths still pass.

**Links touching UniCredit's values, before → after.** Total 114 → 109; accounting 50 → 48; identity 0 → 16; stock-flow
0 → 2; calibrated causal 9 → 9 (m28 and s76 re-sized); uncalibrated 55 → 34; with a transition 111 → 106.

**Reconciliation now.** At the priors (medians): the twelve additive views, the eight identities and the matrix's two
complete rows reconcile exactly. At the FY2025 baselines (one bundle): eleven views reconcile (three within rounding of
the company's divisional tables), CET1 capital is blocked (the FVOCI reserve and the stock before it are not disclosed:
blocked, not a discrepancy); four identities reconcile (CET1 ratio, provisions, cash dividends, ordinary buybacks; the
cost of risk and the payout ratios are derived on the identities' basis, the reported figures kept in estimates) and
four are blocked by undisclosed levels (hedge income, interest paid, loan interest, Commerzbank income); the matrix's
NII and fee rows reconcile. The stock-flow cannot be checked at the baselines: the stock before the FVOCI reserve is
not observed on two dates. 0 flags.

**Coverage per path now.** "Sized causal" are calibrated causal steps; the exact column counts the steps whose weight
is an identity, a stock-flow or an accounting relation (they carry any change they receive).

| Path | Sized causal | Exact: identity / stock-flow / accounting | Excluded: uncalibrated, with sign | Inputs blocking a size (status) |
|---|---|---|---|---|
| `ucg.path.rates_nii` | `ucg-c-ecb-depcost`; summary link m28 beside it | 3 / 0 / 7 | `ucg-m-ecb-euribor` (+), `ucg-c-ecb-sightshare` (-), `ucg-c-ecb-cbkincome` (+), `ucg-c-euribor-loanyield` (+), `ucg-c-sightshare-depcost` (-), `ucg-c-loanint-italynii` (+), `ucg-c-loanint-germanynii` (+), `ucg-c-loanint-austrianii` (+), `ucg-c-depint-italynii` (-), `ucg-c-depint-germanynii` (-), `ucg-c-depint-austrianii` (-), `ucg-c-cbkincome-divline` (+) | Commerzbank NII sensitivity (found, connected); Commerzbank net profit (not disclosed); Commerzbank share of the dividends and equity investments line (not disclosed); Euribor 3M history (not disclosed); average commercial deposits by division (found, connected); loan yield by division (not disclosed); migration elasticity of sight balances to rates (not disclosed); share of floating-rate loans (not disclosed); stake share in Commerzbank (found, connected) |
| `ucg.path.long_end` | `ucg-c-bund-hedgeyield`; summary links s76, s33 beside it | 2 / 1 / 5 | `ucg-c-bund-fvoci` (-), `ucg-c-hedgeincome-nii` (+) | FVOCI book size and duration (not disclosed); hedge allocation across divisions (not disclosed) |
| `ucg.path.sovereign_spread` | none; s33 (Bund only) beside it | 1 / 0 / 6 | `ucg-c-btp-fvoci` (-), `ucg-c-btp-gccnii` (-), `ucg-c-ratio-buybacks` (+) | CET1 sensitivity to the BTP-Bund spread (not disclosed); Italian sovereign FVOCI book size (not disclosed); management buffer above requirements and the use of excess capital (found, connected) |
| `ucg.path.credit_cycle` | none | 1 / 0 / 2 | `ucg-m-gdp-unemp` (-), `ucg-c-unemp-cor` (+), `ucg-c-unemp-overlays` (-), `ucg-c-overlays-llp` (-) | IFRS 9 scenario weights (not disclosed); cost-of-risk sensitivity to unemployment (not disclosed); overlay stock and its release policy (found, connected) |
| `ucg.path.loan_growth` | none | 3 / 1 / 6 | `ucg-c-gdp-loans` (+), `ucg-c-loans-rwa` (+), `ucg-c-loanint-italynii` (+), `ucg-c-loanint-germanynii` (+) | loan growth elasticity to GDP (not disclosed); loan yield by division (not disclosed) |
| `ucg.path.fees_markets` | none | 0 / 0 / 7 | `ucg-c-equity-italyfees` (+), `ucg-c-equity-germanyfees` (+), `ucg-c-equity-austriafees` (+), `ucg-c-equity-ceefees` (+) | investment-fee share and market beta of fees (not disclosed) |
| `ucg.path.cost_inflation` | none | 0 / 0 / 5 | `ucg-c-cpi-italycosts` (-), `ucg-c-cpi-germanycosts` (-), `ucg-c-cpi-austriacosts` (-) | wage indexation and cost sensitivity to inflation (not disclosed) |
| `ucg.path.capital_distribution` | none; s34 beside it | 3 / 2 / 3 | `ucg-c-ratio-buybacks` (+) | management buffer above requirements and the use of excess capital (found, connected) |
| `ucg.path.capital_requirements` | none | 1 / 1 / 2 | `ucg-c-target-buybacks` (-) | management buffer above requirements and the use of excess capital (found, connected) |
| `ucg.path.commerzbank` | none | 3 / 0 / 4 | `ucg-c-cbkstake-rwa` (+), `ucg-c-cbkincome-divline` (+), `ucg-c-ratio-buybacks` (+) | Commerzbank share of the dividends and equity investments line (not disclosed); consolidation CET1 impact (found, connected); management buffer above requirements and the use of excess capital (found, connected) |
| `ucg.path.russia` | none | 1 / 1 / 5 | `ucg-c-rub-russianii` (-), `ucg-c-rub-cet1cap` (-) | CET1 sensitivity to the rouble (not disclosed); EUR/RUB history and Russia's rouble earnings (not disclosed) |

**Forecast coverage (Sally's theses) now.** The ECB-cut thesis (S-T5) now reaches UniCredit through 17 quantified links: 9 causal (m28, s76, s33, s34, s68, s79, s81, the calibrated pass-through and hedge roll), 4 identity (interest paid = deposits × cost, hedge income, cash dividends and ordinary buybacks from net profit) and 4 accounting (NII → revenue → profit before tax → net profit, cash dividends → distributions); it was 12 before the conversion. 16 links are excluded: 13 uncalibrated (each with its sign) and 3 quantified but outside the forecast's isolated networks (the two capital stock-flow links and the buyback accounting link). The forecast now separates own steps from summary links: of the 12 routes to NII, 2 are fully quantified and both run through the summary link m28 or s76 only (2 of 14 own steps quantified: the structure is exact up to the operating states and signed into NII, so the summary links carry the number); of the 17 routes to the share price, 6 are quantified, 3 through own steps (the payout identities). 10 inputs block a size (4 found and connected, 6 not disclosed). The global-yields thesis (S-T2) reaches UniCredit through the Bund: 6 quantified links (s33, s34, s68, s76, s79 and the hedge roll), 8 excluded (NII into revenue among them, outside that forecast's networks).

## What the method could not express for UniCredit

After the conversion round. The first round's list asked for scenario calibration over two links, product and ratio
identities, a division × line matrix, stock-flows, loaded notes and an import that folds a reconciling view; all are
now in the method and used here. What remains:

1. **Summary and structure side by side.** The disclosed sensitivity sizes the summary links (m28, s76); the structural
   steps it would size (interest paid and loan interest by division) cannot be sized from a group disclosure without
   counting twice, so the paths stay "exact to the operating state, signed into NII". Needed: a way to declare that a
   summary link is the sum of structural routes, so one can be sized and the other derived.
2. **Allocation.** Group products (hedge income, interest paid, loan interest) are allocated to divisions by
   funds-transfer pricing that is not disclosed. A weighted average needs stated weights; shares that are values (a
   portfolio sum of products) are not held.
3. **A stock's change.** The overlay release and the FVOCI mark are changes of a stock entering a flow or another
   stock; stock-flows integrate flows but nothing differentiates a stock.
4. **Thresholds and events without a size.** Extra buybacks above the target, the Commerzbank consolidation step and
   the Russia extreme loss are disclosed as conditions or one-off amounts, not sensitivities; `state:` needs an effect.
5. **A change of basis.** Control of Commerzbank moves its income from one line to every line; no object holds it.
6. **Undisclosed parts.** Commerzbank's share of the equity-investments line, the hedge's allocation and the FVOCI
   reserve's level stay unknown, so their identities and the capital composition are blocked at the baselines.
7. **Currency bases.** Constant-FX divisional tables and CEE's local policy rates remain outside the method.
8. **Smaller.** Deriving a stock-flow's annual flows against a stock observed quarterly needs dated stock levels the
   material gives only as ratios; the trace stops at identity targets and at the matrix's passive columns, so routes
   look shorter than the accounts are.
